from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.deps import LiteratureDep, MPDep
from app.models.evidence import Provenance
from app.models.materials import MaterialRecord, PaperEvidence, StructurePayload
from app.models.optical import OpticalReference
from app.tools.materials import parse_query
from app.tools.reference_db import get_reference_db
from app.tools.registry import ToolError, UpstreamError
from app.tools.structures import parse_cif, structure_payload

router = APIRouter(prefix="/api")


def to_http(exc: ToolError) -> HTTPException:
    return HTTPException(
        status_code=502 if isinstance(exc, UpstreamError) else 400, detail=str(exc)
    )


@router.get("/reference/{formula}")
def optical_reference(formula: str) -> OpticalReference:
    """Measured n (refractiveindex.info) and DFT gaps and n (JARVIS-DFT) for a formula."""
    try:
        return get_reference_db().reference(formula)
    except ToolError as exc:
        raise to_http(exc) from exc


@router.get("/materials/search")
def search_materials(
    mp: MPDep,
    q: str = Query(min_length=1, max_length=100),
    band_gap_min: float | None = Query(default=None, ge=0, le=20),
    limit: int = Query(default=10, ge=1, le=50),
) -> list[MaterialRecord]:
    try:
        return mp.search(**parse_query(q), band_gap_min=band_gap_min, limit=limit)
    except ToolError as exc:
        raise to_http(exc) from exc


@router.get("/materials/{material_id}/structure")
def material_structure(material_id: str, mp: MPDep) -> StructurePayload:
    try:
        structure = mp.get_structure(material_id)
        return structure_payload(
            structure,
            Provenance(source="Materials Project", reference=material_id),
        )
    except ToolError as exc:
        raise to_http(exc) from exc


class CifUpload(BaseModel):
    filename: str = Field(min_length=1, max_length=200)
    cif: str = Field(min_length=1, max_length=2_000_000)


@router.post("/structures/cif")
def upload_cif(upload: CifUpload) -> StructurePayload:
    try:
        return parse_cif(upload.cif, upload.filename)
    except ToolError as exc:
        raise to_http(exc) from exc


@router.get("/literature/search")
def search_literature(
    literature: LiteratureDep,
    q: str = Query(min_length=2, max_length=200),
    limit: int = Query(default=5, ge=1, le=10),
) -> list[PaperEvidence]:
    try:
        return literature.search(q, limit=limit)
    except ToolError as exc:
        raise to_http(exc) from exc
