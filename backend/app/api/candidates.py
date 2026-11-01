import hashlib
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import PlainTextResponse
from openai import APIError
from pydantic import BaseModel, Field

from app.agents.critique import View, evidence_pack, run_critique
from app.agents.loop import Audience
from app.agents.muse import ModelAPIKeyMissing, create_client
from app.api.deps import CodDep, LiteratureDep, OptionalMPDep, SettingsDep, StoreDep, client_id
from app.api.materials import to_http
from app.models.candidates import (
    Candidate,
    Credit,
    Decision,
    DecisionKind,
    ExperimentRecord,
    Publication,
    Relaxation,
    StructuralAssessment,
    Substitution,
    Visibility,
)
from app.models.evidence import Provenance
from app.storage.memory import add_decision
from app.storage.scoped import NotOwner
from app.tools.candidates import assess_host, create_candidate, load_host
from app.tools.export import CandidateRecord, SpatialRecord, ancestry, build_record, cif_text
from app.tools.goals import Goal, GoalScore, score_candidate, score_formula
from app.tools.novelty import Novelty, check_novelty
from app.tools.reference_db import get_reference_db
from app.tools.registry import ToolError, UpstreamError
from app.tools.relaxation import displacement_summary, relax, relaxation_available
from app.tools.scorecard import Scorecard, build_scorecard
from app.tools.spatial import SpatialAnalysis, analyze, before_substitution
from app.tools.structures import parse_cif_structure, structure_payload
from app.tools.usage import AGENT_CAP, AGENT_RATE
from app.tools.validation import RELAXED_NOTE, assess

router = APIRouter(prefix="/api")


class HostRef(BaseModel):
    """Exactly one host source: a Materials Project ID, an earlier candidate, or CIF text."""

    material_id: str | None = Field(default=None, max_length=40)
    candidate_id: str | None = Field(default=None, max_length=20)
    cif: str | None = Field(default=None, max_length=2_000_000)
    filename: str = Field(default="upload.cif", max_length=200)


class CandidateRequest(BaseModel):
    host: HostRef
    substitutions: list[Substitution] = Field(min_length=1, max_length=4)
    arrangement: Literal["spread", "lowest_ewald"] = "spread"


def not_found(candidate_id: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"No candidate {candidate_id}.")


@router.post("/candidates")
def new_candidate(request: CandidateRequest, mp: OptionalMPDep, store: StoreDep) -> Candidate:
    try:
        host, host_ref, parent_id = load_host(store, mp, **request.host.model_dump())
        return create_candidate(
            store,
            host,
            host_ref,
            request.substitutions,
            parent_id,
            mp,
            arrangement=request.arrangement,
        )
    except ToolError as exc:
        raise to_http(exc) from exc


@router.get("/candidates")
def list_candidates(store: StoreDep) -> list[Candidate]:
    return store.all()


@router.get("/candidates/{candidate_id}")
def get_candidate(candidate_id: str, store: StoreDep) -> Candidate:
    stored = store.get(candidate_id)
    if stored is None:
        raise not_found(candidate_id)
    return stored[0]


class DecisionRequest(BaseModel):
    decision: DecisionKind
    reason: str = Field(default="", max_length=2000)


@router.post("/candidates/{candidate_id}/decisions")
def record_decision(candidate_id: str, request: DecisionRequest, store: StoreDep) -> Candidate:
    decision = Decision(
        decision=request.decision, reason=request.reason.strip(), created_at=datetime.now(UTC)
    )
    updated = add_decision(store, candidate_id, decision)
    if updated is None:
        raise not_found(candidate_id)
    return updated


PUBLISHED_LICENSE = "CC BY 4.0"


class VisibilityRequest(BaseModel):
    visibility: Visibility
    credit_display: Literal["name", "anonymous"] = "anonymous"
    display_name: str | None = Field(default=None, max_length=200)
    consent: bool = False


@router.post("/candidates/{candidate_id}/visibility")
def set_visibility(
    candidate_id: str, request: VisibilityRequest, store: StoreDep, settings: SettingsDep
) -> Candidate:
    """Not published by default; publishing needs explicit consent and a credit choice.

    With sign-in on, only an owner can publish, and the credit name is the signed-in account. A
    candidate from public mode has no owner, so nobody can claim it.
    """
    stored = store.get(candidate_id)
    if stored is None:
        raise not_found(candidate_id)
    candidate = stored[0]
    if not candidate.editable:
        raise NotOwner(candidate_id)
    if settings.auth_secret and not candidate.mine:
        raise HTTPException(
            status_code=403,
            detail="Anyone can already read a public-mode candidate. "
            "Make it in private mode to publish it with your name.",
        )
    now = datetime.now(UTC)
    if request.visibility == "private":
        changes = {
            "visibility": "private",
            "credit": None,
            "publications": [*candidate.publications, Publication(action="unpublished", at=now)],
        }
    else:
        if not request.consent:
            raise HTTPException(status_code=400, detail="Publishing needs explicit consent.")
        if candidate.mine and store.viewer:
            # The name is the signed-in account, so nobody can publish under another person's name.
            credit = Credit(
                display=request.credit_display,
                name=store.viewer.login if request.credit_display == "name" else None,
                published_at=now,
                verified=request.credit_display == "name",
                license=PUBLISHED_LICENSE,
                content_sha256=hashlib.sha256(candidate.structure.cif.encode()).hexdigest(),
            )
        else:
            name = (request.display_name or "").strip()
            if request.credit_display == "name" and not name:
                raise HTTPException(
                    status_code=400, detail="Give a name, or choose anonymous credit."
                )
            credit = Credit(
                display=request.credit_display,
                name=name if request.credit_display == "name" else None,
                published_at=now,
            )
        changes = {
            "visibility": "published",
            "credit": credit,
            "publications": [
                *candidate.publications,
                Publication(action="published", at=now, credit=credit),
            ],
        }
    updated = store.update(candidate_id, changes)
    if updated is None:
        raise not_found(candidate_id)
    return updated


class ExperimentRequest(BaseModel):
    property: Literal["refractive_index", "band_gap"]
    value: float = Field(gt=0, le=100)
    wavelength_nm: float | None = Field(default=None, gt=0, le=20000)
    sample: Literal["bulk", "thin film", "powder", "other"] = "bulk"
    method: str = Field(default="", max_length=200)
    reference: str | None = Field(default=None, max_length=300)
    notes: str = Field(default="", max_length=1000)


@router.post("/candidates/{candidate_id}/experiments")
def add_experiment(candidate_id: str, request: ExperimentRequest, store: StoreDep) -> Candidate:
    """Attach a researcher's measurement, so prediction and experiment can be compared."""
    if request.property == "refractive_index" and request.wavelength_nm is None:
        raise HTTPException(status_code=400, detail="Give the wavelength for a refractive index.")
    stored = store.get(candidate_id)
    if stored is None:
        raise not_found(candidate_id)
    record = ExperimentRecord(**request.model_dump(), created_at=datetime.now(UTC))
    return store.update(candidate_id, {"experiments": [*stored[0].experiments, record]})


@router.post("/candidates/{candidate_id}/relax")
def relax_candidate(candidate_id: str, store: StoreDep) -> Candidate:
    """CHGNet relaxation, then the same checks on the relaxed geometry (local installs only)."""
    stored = store.get(candidate_id)
    if stored is None:
        raise not_found(candidate_id)
    if not stored[0].editable:  # before the long calculation
        raise NotOwner(candidate_id)
    if not relaxation_available():
        raise HTTPException(
            status_code=501,
            detail="CHGNet relaxation is available only in a local install (uv sync --group relax).",
        )
    candidate, structure = stored
    try:
        outcome = relax(structure)
    except ToolError as exc:
        raise to_http(exc) from exc
    focus = sorted(
        i for sites in candidate.transformation.substituted_sites.values() for i in sites
    )
    relaxation = Relaxation(
        method=outcome.method,
        converged=outcome.converged,
        steps=outcome.steps,
        energy_per_atom=round(outcome.energy_per_atom, 4),
        **displacement_summary(structure, outcome.structure),
        structure=structure_payload(
            outcome.structure, Provenance(source="CHGNet relaxation", reference=candidate_id)
        ),
        assessment=assess(outcome.structure, focus, note=RELAXED_NOTE),
    )
    return store.update(candidate_id, {"relaxation": relaxation})


class ScoreRequest(BaseModel):
    goal: Goal
    candidate_id: str | None = Field(default=None, max_length=20)
    formula: str | None = Field(default=None, max_length=60)


@router.post("/score")
def score(request: ScoreRequest, store: StoreDep) -> GoalScore:
    """Score a candidate (or a known formula) against the research goal, with evidence."""
    try:
        if request.candidate_id:
            stored = store.get(request.candidate_id)
            if stored is None:
                raise not_found(request.candidate_id)
            return score_candidate(stored[0], request.goal)
        if request.formula:
            return score_formula(request.formula, request.goal, get_reference_db())
    except ToolError as exc:
        raise to_http(exc) from exc
    raise HTTPException(status_code=400, detail="Give a candidate_id or a formula.")


_spatial_cache: dict[tuple[str, bool, bool], SpatialAnalysis] = {}


@router.get("/candidates/{candidate_id}/spatial")
def candidate_spatial(candidate_id: str, store: StoreDep, relaxed: bool = False) -> SpatialAnalysis:
    """Symmetry/optical class, polyhedra, connectivity, dopant arrangement, ordering rank."""
    stored = store.get(candidate_id)
    if stored is None:
        raise not_found(candidate_id)
    candidate, structure = stored
    key = (candidate_id, relaxed, candidate.relaxation is not None)
    if key in _spatial_cache:
        return _spatial_cache[key]
    replaced = candidate.transformation.substituted_sites
    parent = before_substitution(structure, candidate.transformation)
    focus = sorted(i for sites in replaced.values() for i in sites)
    if relaxed:
        if candidate.relaxation is None:
            raise HTTPException(status_code=400, detail=f"{candidate_id} has not been relaxed.")
        geometry = parse_cif_structure(
            candidate.relaxation.structure.cif, f"{candidate_id}-relaxed"
        )
        # Compared with the unrelaxed candidate; the ordering rank does not change on relaxing.
        result = analyze(geometry, focus, structure, replaced, rank=False)
    else:
        result = analyze(structure, focus, parent, replaced)
    if len(_spatial_cache) > 256:
        _spatial_cache.clear()
    _spatial_cache[key] = result
    return result


@router.post("/candidates/{candidate_id}/scorecard")
def candidate_scorecard(candidate_id: str, goal: Goal, store: StoreDep) -> Scorecard:
    """A 0-100 ranking score (a range) from the goal, the evidence, and known materials."""
    stored = store.get(candidate_id)
    if stored is None:
        raise not_found(candidate_id)
    candidate, structure = stored
    parent = before_substitution(structure, candidate.transformation)
    return build_scorecard(candidate, structure, parent, goal, get_reference_db())


_novelty_cache: dict[str, Novelty] = {}


@router.get("/candidates/{candidate_id}/novelty")
def candidate_novelty(
    candidate_id: str, mp: OptionalMPDep, cod: CodDep, literature: LiteratureDep, store: StoreDep
) -> Novelty:
    """Exact matches and related work for this composition. Complete answers are kept in memory."""
    stored = store.get(candidate_id)
    if stored is None:
        raise not_found(candidate_id)
    if candidate_id in _novelty_cache:
        return _novelty_cache[candidate_id]
    result = check_novelty(stored[0], mp, cod, literature, get_reference_db())
    if result.complete:
        if len(_novelty_cache) > 256:
            _novelty_cache.clear()
        _novelty_cache[candidate_id] = result
    return result


@router.get("/candidates/{candidate_id}/export.cif", response_class=PlainTextResponse)
def export_cif(candidate_id: str, store: StoreDep, relaxed: bool = False) -> PlainTextResponse:
    """The candidate's P1 cell (or its CHGNet-relaxed cell) with a provenance header."""
    stored = store.get(candidate_id)
    if stored is None:
        raise not_found(candidate_id)
    candidate = stored[0]
    if relaxed and candidate.relaxation is None:
        raise HTTPException(status_code=400, detail=f"{candidate_id} has not been relaxed.")
    name = f"{candidate_id}{'-relaxed' if relaxed else ''}.cif"
    return PlainTextResponse(
        cif_text(candidate, ancestry(store, candidate), relaxed),
        media_type="chemical/x-cif",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.get("/candidates/{candidate_id}/export.json")
def export_record(
    candidate_id: str,
    response: Response,
    store: StoreDep,
    target_n: Annotated[float | None, Query(ge=1, le=5)] = None,
    min_band_gap: Annotated[float | None, Query(ge=0, le=15)] = None,
    forbidden: Annotated[str, Query(max_length=200)] = "",
) -> CandidateRecord:
    """Everything known about a candidate, with the goal score, spatial analysis, and sources.

    Give target_n and min_band_gap (and optionally forbidden=Pb,Cd) to include a goal score.
    """
    stored = store.get(candidate_id)
    if stored is None:
        raise not_found(candidate_id)
    candidate = stored[0]
    goal, goal_score, scorecard = None, None, None
    if target_n is not None and min_band_gap is not None:
        goal = Goal(
            target_n=target_n,
            min_band_gap=min_band_gap,
            forbidden_elements=[e.strip() for e in forbidden.split(",") if e.strip()],
        )
        try:
            goal_score = score_candidate(candidate, goal)
            scorecard = candidate_scorecard(candidate_id, goal, store)
        except ToolError as exc:
            raise to_http(exc) from exc
    spatial = SpatialRecord(
        unrelaxed=candidate_spatial(candidate_id, store),
        relaxed=candidate_spatial(candidate_id, store, relaxed=True)
        if candidate.relaxation
        else None,
    )
    response.headers["Content-Disposition"] = f'attachment; filename="{candidate_id}-record.json"'
    return build_record(
        store, candidate, get_reference_db().meta(), goal, goal_score, spatial, scorecard
    )


class CritiqueRequest(BaseModel):
    goal: Goal
    locale: str = Field(default="en", max_length=10)
    geometry: Literal["unrelaxed", "relaxed"] = "unrelaxed"
    views: list[View] = Field(default_factory=list, max_length=3)
    legend: dict[str, str] = Field(default_factory=dict, max_length=30)  # element -> color
    audience: Audience = "expert"


@router.post("/candidates/{candidate_id}/critique")
def critique_candidate(
    candidate_id: str,
    body: CritiqueRequest,
    request: Request,
    settings: SettingsDep,
    store: StoreDep,
) -> Candidate:
    """Muse Spark reviews the candidate from its evidence and structure views (cites IDs)."""
    stored = store.get(candidate_id)
    if stored is None:
        raise not_found(candidate_id)
    candidate = stored[0]
    if not candidate.editable:  # before the paid request
        raise NotOwner(candidate_id)
    if body.geometry == "relaxed" and candidate.relaxation is None:
        raise HTTPException(status_code=400, detail=f"{candidate_id} has not been relaxed.")
    try:
        client = create_client(settings)
    except ModelAPIKeyMissing as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    # Same Meta credit protection as the research agent.
    if not AGENT_RATE.allow(client_id(request)):
        raise HTTPException(status_code=429, detail="Too many agent requests. Wait a few minutes.")
    try:
        AGENT_CAP.take()
    except UpstreamError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc

    try:
        evidence = evidence_pack(
            candidate,
            score_candidate(candidate, body.goal),
            candidate_spatial(candidate_id, store),
            candidate_spatial(candidate_id, store, relaxed=True) if candidate.relaxation else None,
        )
        critique = run_critique(
            client,
            settings.muse_model,
            candidate,
            body.goal,
            evidence,
            body.views,
            body.legend,
            body.geometry,
            body.locale,
            body.audience,
        )
    except ToolError as exc:
        raise to_http(exc) from exc
    except APIError as exc:
        raise HTTPException(status_code=502, detail=f"Meta Model API error: {exc}") from exc
    updated = store.update(candidate_id, {"critiques": [*candidate.critiques, critique][-5:]})
    if updated is None:
        raise not_found(candidate_id)
    return updated


@router.post("/structures/spatial")
def host_spatial(host: HostRef, mp: OptionalMPDep, store: StoreDep) -> SpatialAnalysis:
    try:
        structure, _, _ = load_host(store, mp, **host.model_dump())
    except ToolError as exc:
        raise to_http(exc) from exc
    return analyze(structure)


@router.post("/structures/assess")
def assess_structure(host: HostRef, mp: OptionalMPDep, store: StoreDep) -> StructuralAssessment:
    try:
        structure, _, _ = load_host(store, mp, **host.model_dump())
        return assess_host(structure, mp)
    except ToolError as exc:
        raise to_http(exc) from exc
