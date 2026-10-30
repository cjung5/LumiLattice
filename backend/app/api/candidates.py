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
    StructuralAssessment,
    Substitution,
    Visibility,
)
from app.storage.memory import add_decision, get_store
from app.tools.candidates import assess_host, create_candidate, load_host
from app.tools.registry import ToolError

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


@router.post("/structures/assess")
def assess_structure(host: HostRef, mp: OptionalMPDep) -> StructuralAssessment:
    try:
        structure, _, _ = load_host(get_store(), mp, **host.model_dump())
        return assess_host(structure, mp)
    except ToolError as exc:
        raise to_http(exc) from exc
