from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.critique import Critique
from app.models.evidence import Provenance
from app.models.materials import StructurePayload
from app.models.optical import OpticalEstimate

CheckStatus = Literal["pass", "warn", "fail", "info", "not_applicable"]
AssessmentStatus = Literal["Structurally Plausible", "Structural Concerns", "Insufficient Evidence"]


class Substitution(BaseModel):
    element_from: str = Field(
        min_length=1, max_length=3, description="Element to replace, e.g. 'Ti'."
    )
    element_to: str = Field(min_length=1, max_length=3, description="New element, e.g. 'Zr'.")
    fraction: float = Field(gt=0, le=1, description="Fraction of element_from sites to replace.")


class CheckResult(BaseModel):
    id: str
    name: str
    status: CheckStatus
    message: str
    # Site indices in the assessed structure (same order as the viewer's atoms).
    atom_indices: list[int] = []
    values: dict[str, float | str] = {}
    method: str | None = None


class SiteMetric(BaseModel):
    """The numbers behind the per-site checks for one cation site."""

    index: int
    element: str
    oxidation_state: float
    coordination: int
    bond_lengths: list[float]  # Å, first anion shell
    mean_bond: float  # Å
    expected_bond: float | None = None  # Å, Shannon radii sum
    size_mismatch: float | None = None  # (expected - mean) / mean
    bvs: float | None = None
    bvs_bond_change: float | None = None  # bond change that would fix the BVS, / mean


class StructuralAssessment(BaseModel):
    status: AssessmentStatus
    checks: list[CheckResult]
    oxidation_states: dict[str, float] | None = None
    notes: list[str] = []
    site_metrics: list[SiteMetric] = []
    thresholds: dict[str, float] = {}


class Transformation(BaseModel):
    host: Provenance
    supercell: tuple[int, int, int]
    substitutions: list[Substitution]
    # element_to -> site indices in the candidate structure
    substituted_sites: dict[str, list[int]]
    site_selection: str
    # "spread": dopants as far apart as possible; "lowest_ewald": lowest point-charge energy.
    arrangement: Literal["spread", "lowest_ewald"] = "spread"
    # The original host and every substitution since then (for revisions of revisions).
    root_formula: str
    lineage: list[Substitution]


DecisionKind = Literal["accept", "modify", "reject", "explore"]


class Decision(BaseModel):
    """A researcher's judgment on a candidate (spec section 4, step 5)."""

    decision: DecisionKind
    reason: str = Field(default="", max_length=2000)
    created_at: datetime


class Relaxation(BaseModel):
    """CHGNet relaxation of a candidate (local installs only; spec D5)."""

    method: str
    converged: bool
    steps: int
    # Machine-learned potential energy. Never compare with DFT energies.
    energy_per_atom: float
    lattice_change: tuple[float, float, float]  # fractions for a, b, c
    volume_change: float  # fraction
    max_displacement: float  # Å
    structure: StructurePayload
    assessment: StructuralAssessment


class ExperimentRecord(BaseModel):
    """A measurement the researcher adds to a candidate (spec 3.5). LumiLattice does not verify it."""

    property: Literal["refractive_index", "band_gap"]
    value: float
    wavelength_nm: float | None = Field(default=None, gt=0, le=20000)
    sample: Literal["bulk", "thin film", "powder", "other"] = "bulk"
    method: str = Field(default="", max_length=200)  # e.g. "ellipsometry"
    reference: str | None = Field(default=None, max_length=300)  # DOI or URL
    notes: str = Field(default="", max_length=1000)
    created_at: datetime


Visibility = Literal["private", "published"]


class Credit(BaseModel):
    """How the researcher wants to be credited when a candidate is published (spec section 7)."""

    display: Literal["name", "anonymous"]
    name: str | None = Field(default=None, max_length=200)
    published_at: datetime


class Candidate(BaseModel):
    candidate_id: str
    parent_id: str | None = None
    formula: str
    structure: StructurePayload
    transformation: Transformation
    assessment: StructuralAssessment
    optical_estimate: OpticalEstimate | None = None
    created_at: datetime
    decisions: list[Decision] = []
    # "private" means only "not marked as published": there are no accounts, so anyone can read it.
    # Stage 1 records the choice only; nothing is shared outside the app.
    visibility: Visibility = "private"
    credit: Credit | None = None
    relaxation: Relaxation | None = None
    experiments: list[ExperimentRecord] = []
    critiques: list[Critique] = []  # Muse Spark reviews, newest last
