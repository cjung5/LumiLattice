from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.deps import CodDep, LiteratureDep, MPDep
from app.models.evidence import Provenance
from app.models.materials import LiteratureResult, MaterialRecord, StructurePayload
from app.models.optical import DispersionData, Landscape, OpticalReference
from app.tools.cloud import CloudModel, cloud_model
from app.tools.cod import CodEntry
from app.tools.materials import parse_query
from app.tools.reference_db import get_landscape, get_reference_db
from app.tools.registry import ToolError, UpstreamError
from app.tools.structures import (
    CELL_METHOD,
    MAX_SITES,
    parse_cif,
    parse_cif_structure,
    structure_payload,
)

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
            Provenance(source="Materials Project", method=CELL_METHOD, reference=material_id),
        )
    except ToolError as exc:
        raise to_http(exc) from exc


@router.get("/landscape")
def landscape() -> Landscape:
    """n vs band gap for every material with a measured n, plus a sample of JARVIS DFT."""
    return get_landscape()


@router.get("/dispersion")
def dispersion(formulas: str = Query(min_length=1, max_length=200)) -> list[DispersionData]:
    """n(λ) curves (380–780 nm) for up to 6 comma-separated formulas."""
    names = [f.strip() for f in formulas.split(",") if f.strip()][:6]
    try:
        return [get_reference_db().dispersion(f) for f in names]
    except ToolError as exc:
        raise to_http(exc) from exc


@router.get("/cod/search")
def search_cod(cod: CodDep, formula: str = Query(min_length=1, max_length=60)) -> list[CodEntry]:
    """Experimental structures from the Crystallography Open Database (CC0)."""
    try:
        return cod.search(formula)
    except ToolError as exc:
        raise to_http(exc) from exc


@router.get("/cod/{cod_id}/structure")
def cod_structure(cod_id: str, cod: CodDep) -> StructurePayload:
    try:
        payload = parse_cif(cod.get_cif(cod_id), f"COD-{cod_id}.cif")
    except ToolError as exc:
        raise to_http(exc) from exc
    payload.provenance = Provenance(
        source="Crystallography Open Database",
        reference=f"COD {cod_id}",
        method="experimental structure (CC0)",
    )
    return payload


class CifUpload(BaseModel):
    filename: str = Field(min_length=1, max_length=200)
    cif: str = Field(min_length=1, max_length=2_000_000)


@router.post("/structures/cif")
def upload_cif(upload: CifUpload) -> StructurePayload:
    try:
        return parse_cif(upload.cif, upload.filename)
    except ToolError as exc:
        raise to_http(exc) from exc


class CloudRequest(BaseModel):
    cif: str = Field(min_length=1, max_length=2_000_000)


@router.post("/structures/cloud")
def structure_cloud(request: CloudRequest) -> CloudModel:
    """The model behind the 3D cloud view: a size and a stretch for each atom's cloud."""
    try:
        structure = parse_cif_structure(request.cif, "structure.cif")
        if len(structure) > MAX_SITES:
            raise ToolError(f"Structure has {len(structure)} sites; the limit is {MAX_SITES}.")
        return cloud_model(structure)
    except ToolError as exc:
        raise to_http(exc) from exc


@router.get("/literature/search")
def search_literature(
    literature: LiteratureDep,
    q: str = Query(min_length=2, max_length=200),
    limit: int = Query(default=5, ge=1, le=10),
) -> LiteratureResult:
    """OpenAlex, Crossref, and arXiv in parallel; the same paper is merged by DOI or title."""
    try:
        return literature.search(q, limit=limit)
    except ToolError as exc:
        raise to_http(exc) from exc
