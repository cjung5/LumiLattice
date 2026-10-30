from pydantic import BaseModel

from app.models.evidence import PropertyValue, Provenance


class MaterialRecord(BaseModel):
    material_id: str
    formula: str
    crystal_system: str | None = None
    spacegroup: str | None = None
    spacegroup_number: int | None = None
    nsites: int | None = None
    is_stable: bool = False
    # False when the material matches an experimentally observed (ICSD) structure.
    theoretical: bool = True
    icsd_ids: list[str] = []
    band_gap: PropertyValue
    energy_above_hull: PropertyValue
    refractive_index: PropertyValue
    url: str


class Lattice(BaseModel):
    a: float
    b: float
    c: float
    alpha: float
    beta: float
    gamma: float
    volume: float


class Site(BaseModel):
    index: int
    species: str
    frac_coords: tuple[float, float, float]


class StructurePayload(BaseModel):
    formula: str
    spacegroup: str | None
    spacegroup_number: int | None
    lattice: Lattice
    sites: list[Site]
    # P1 CIF: every site is written out, so viewer atom order == site index.
    cif: str
    provenance: Provenance
    warnings: list[str] = []


class PaperEvidence(BaseModel):
    title: str
    authors: list[str]
    year: int | None
    venue: str | None
    doi: str | None
    url: str | None
    cited_by_count: int | None
    open_access: bool | None  # None: the source does not say
    open_access_url: str | None
    provenance: Provenance
    # Every source that returned this paper (results with the same DOI are merged).
    sources: list[str] = []


class LiteratureResult(BaseModel):
    papers: list[PaperEvidence]
    # Per source: "ok", or why it returned nothing (e.g. rate limit).
    source_status: dict[str, str]
