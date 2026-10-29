from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import OptionalMPDep
from app.api.materials import to_http
from app.models.candidates import Candidate, StructuralAssessment, Substitution
from app.storage.memory import STORE
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


@router.post("/candidates")
def new_candidate(request: CandidateRequest, mp: OptionalMPDep) -> Candidate:
    try:
        host, host_ref, parent_id = load_host(STORE, mp, **request.host.model_dump())
        return create_candidate(STORE, host, host_ref, request.substitutions, parent_id, mp)
    except ToolError as exc:
        raise to_http(exc) from exc


@router.get("/candidates")
def list_candidates() -> list[Candidate]:
    return STORE.all()


@router.get("/candidates/{candidate_id}")
def get_candidate(candidate_id: str) -> Candidate:
    stored = STORE.get(candidate_id)
    if stored is None:
        raise HTTPException(status_code=404, detail=f"No candidate {candidate_id}.")
    return stored[0]


@router.post("/structures/assess")
def assess_structure(host: HostRef, mp: OptionalMPDep) -> StructuralAssessment:
    try:
        structure, _, _ = load_host(STORE, mp, **host.model_dump())
        return assess_host(structure, mp)
    except ToolError as exc:
        raise to_http(exc) from exc
