from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.evidence import Provenance
from app.models.materials import StructurePayload

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


class StructuralAssessment(BaseModel):
    status: AssessmentStatus
    checks: list[CheckResult]
    oxidation_states: dict[str, float] | None = None
    notes: list[str] = []


class Transformation(BaseModel):
    host: Provenance
    supercell: tuple[int, int, int]
    substitutions: list[Substitution]
    # element_to -> site indices in the candidate structure
    substituted_sites: dict[str, list[int]]
    site_selection: str
    # The original host and every substitution since then (for revisions of revisions).
    root_formula: str
    lineage: list[Substitution]


DecisionKind = Literal["accept", "modify", "reject", "explore"]


class Decision(BaseModel):
    """A researcher's judgment on a candidate (spec section 4, step 5)."""

    decision: DecisionKind
    reason: str = Field(default="", max_length=2000)
    created_at: datetime


class Candidate(BaseModel):
    candidate_id: str
    parent_id: str | None = None
    formula: str
    structure: StructurePayload
    transformation: Transformation
    assessment: StructuralAssessment
    created_at: datetime
    decisions: list[Decision] = []
