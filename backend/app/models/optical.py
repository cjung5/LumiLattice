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
    best_gap: PropertyValue
    measured_gaps: list[float] = []  # every reported value in eV, lowest first
    measured: list[MeasuredIndex]
    computed: list[ComputedOptics]
    note: str


class EndMemberIndex(BaseModel):
    formula: str
    n: PropertyValue
    band_gap: PropertyValue | None = None


class OpticalEstimate(BaseModel):
    """Heuristic n and band-gap ranges for a candidate, spanned by its end members (spec D3)."""

    estimate: PropertyValue
    end_members: list[EndMemberIndex]
    band_gap: PropertyValue | None = None


class DispersionCurve(BaseModel):
    title: str
    category: str
    direction: str | None
    n: list[float | None]  # one value per wavelength in DispersionData.wavelengths_nm


class DispersionData(BaseModel):
    formula: str
    wavelengths_nm: list[int]
    curves: list[DispersionCurve]
    # Median of the bulk/crystal curves at each wavelength (what charts and ranges use).
    bulk_median: list[float | None] | None


class LandscapePoint(BaseModel):
    formula: str
    n: float
    band_gap: float
    gap_measured: bool = False  # False: JARVIS TBmBJ


class Landscape(BaseModel):
    """n vs band gap: the trade-off every high-index transparent material faces."""

    measured: list[LandscapePoint]  # measured bulk n(550 nm), measured or TBmBJ gap
    computed: list[tuple[float, float]]  # sample of JARVIS (TBmBJ gap, TBmBJ n = sqrt(eps))
    computed_total: int
    moss: list[tuple[float, float]]  # empirical Moss relation n^4 * Eg = 95 eV
    notes: list[str]
