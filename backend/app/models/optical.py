from pydantic import BaseModel

from app.models.evidence import PropertyValue


class MeasuredIndex(BaseModel):
    """One refractiveindex.info page (measured n, k)."""

    title: str
    category: str  # e.g. "Bulk", "Crystal", "Thin film"; "" when the source gives none
    direction: str | None  # e.g. "o", "e"
    n_450: float | None
    n_550: float | None
    n_650: float | None
    k_550: float | None
    wavelength_range_um: tuple[float, float]
    reference: str
    doi: str | None
    url: str


class ComputedOptics(BaseModel):
    """One JARVIS-DFT entry with gaps and n = sqrt(eps) from DFT linear optics."""

    jid: str
    mp_id: str | None
    spacegroup: str | None
    has_icsd: bool
    band_gap_optb88vdw: float | None
    band_gap_mbj: float | None
    n_optb88vdw: float | None
    n_mbj: float | None
    url: str


class OpticalReference(BaseModel):
    formula: str
    best_n: PropertyValue
    measured: list[MeasuredIndex]
    computed: list[ComputedOptics]
    note: str


class EndMemberIndex(BaseModel):
    formula: str
    n: PropertyValue


class OpticalEstimate(BaseModel):
    """Heuristic n range for a candidate, spanned by its end-member compounds (spec D3)."""

    estimate: PropertyValue
    end_members: list[EndMemberIndex]
