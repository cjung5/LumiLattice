from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import OptionalMPDep
from app.api.materials import to_http
from app.models.candidates import (
    Candidate,
    Credit,
    Decision,
    DecisionKind,
    ExperimentRecord,
    Relaxation,
    StructuralAssessment,
    Substitution,
    Visibility,
)
from app.models.evidence import Provenance
from app.storage.memory import add_decision, get_store
from app.tools.candidates import assess_host, create_candidate, load_host
from app.tools.goals import Goal, GoalScore, score_candidate, score_formula
from app.tools.reference_db import get_reference_db
from app.tools.registry import ToolError
from app.tools.relaxation import displacement_summary, relax, relaxation_available
from app.tools.spatial import SpatialAnalysis, analyze
from app.tools.structures import parse_cif_structure, structure_payload
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


def not_found(candidate_id: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"No candidate {candidate_id}.")


@router.post("/candidates")
def new_candidate(request: CandidateRequest, mp: OptionalMPDep) -> Candidate:
    store = get_store()
    try:
        host, host_ref, parent_id = load_host(store, mp, **request.host.model_dump())
        return create_candidate(store, host, host_ref, request.substitutions, parent_id, mp)
    except ToolError as exc:
        raise to_http(exc) from exc


@router.get("/candidates")
def list_candidates() -> list[Candidate]:
    return get_store().all()


@router.get("/candidates/{candidate_id}")
def get_candidate(candidate_id: str) -> Candidate:
    stored = get_store().get(candidate_id)
    if stored is None:
        raise not_found(candidate_id)
    return stored[0]


class DecisionRequest(BaseModel):
    decision: DecisionKind
    reason: str = Field(default="", max_length=2000)


@router.post("/candidates/{candidate_id}/decisions")
def record_decision(candidate_id: str, request: DecisionRequest) -> Candidate:
    decision = Decision(
        decision=request.decision, reason=request.reason.strip(), created_at=datetime.now(UTC)
    )
    updated = add_decision(get_store(), candidate_id, decision)
    if updated is None:
        raise not_found(candidate_id)
    return updated


class VisibilityRequest(BaseModel):
    visibility: Visibility
    credit_display: Literal["name", "anonymous"] = "anonymous"
    display_name: str | None = Field(default=None, max_length=200)
    consent: bool = False


@router.post("/candidates/{candidate_id}/visibility")
def set_visibility(candidate_id: str, request: VisibilityRequest) -> Candidate:
    """Private by default; publishing needs explicit consent and a credit choice."""
    if request.visibility == "private":
        changes = {"visibility": "private", "credit": None}
    else:
        if not request.consent:
            raise HTTPException(status_code=400, detail="Publishing needs explicit consent.")
        name = (request.display_name or "").strip()
        if request.credit_display == "name" and not name:
            raise HTTPException(status_code=400, detail="Give a name, or choose anonymous credit.")
        changes = {
            "visibility": "published",
            "credit": Credit(
                display=request.credit_display,
                name=name if request.credit_display == "name" else None,
                published_at=datetime.now(UTC),
            ),
        }
    updated = get_store().update(candidate_id, changes)
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
def add_experiment(candidate_id: str, request: ExperimentRequest) -> Candidate:
    """Attach a researcher's measurement, so prediction and experiment can be compared."""
    if request.property == "refractive_index" and request.wavelength_nm is None:
        raise HTTPException(status_code=400, detail="Give the wavelength for a refractive index.")
    store = get_store()
    stored = store.get(candidate_id)
    if stored is None:
        raise not_found(candidate_id)
    record = ExperimentRecord(**request.model_dump(), created_at=datetime.now(UTC))
    return store.update(candidate_id, {"experiments": [*stored[0].experiments, record]})


@router.post("/candidates/{candidate_id}/relax")
def relax_candidate(candidate_id: str) -> Candidate:
    """CHGNet relaxation, then the same checks on the relaxed geometry (local installs only)."""
    store = get_store()
    stored = store.get(candidate_id)
    if stored is None:
        raise not_found(candidate_id)
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
def score(request: ScoreRequest) -> GoalScore:
    """Score a candidate (or a known formula) against the research goal, with evidence."""
    try:
        if request.candidate_id:
            stored = get_store().get(request.candidate_id)
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
def candidate_spatial(candidate_id: str, relaxed: bool = False) -> SpatialAnalysis:
    """Symmetry/optical class, polyhedra, connectivity, dopant arrangement, ordering rank."""
    stored = get_store().get(candidate_id)
    if stored is None:
        raise not_found(candidate_id)
    candidate, structure = stored
    key = (candidate_id, relaxed, candidate.relaxation is not None)
    if key in _spatial_cache:
        return _spatial_cache[key]
    replaced = candidate.transformation.substituted_sites
    origin = {s.element_to: s.element_from for s in candidate.transformation.substitutions}
    parent = structure.copy()  # the same supercell before this step's substitutions
    for element, sites in replaced.items():
        for i in sites:
            parent.replace(i, origin[element])
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


@router.post("/structures/spatial")
def host_spatial(host: HostRef, mp: OptionalMPDep) -> SpatialAnalysis:
    try:
        structure, _, _ = load_host(get_store(), mp, **host.model_dump())
    except ToolError as exc:
        raise to_http(exc) from exc
    return analyze(structure)


@router.post("/structures/assess")
def assess_structure(host: HostRef, mp: OptionalMPDep) -> StructuralAssessment:
    try:
        structure, _, _ = load_host(get_store(), mp, **host.model_dump())
        return assess_host(structure, mp)
    except ToolError as exc:
        raise to_http(exc) from exc
