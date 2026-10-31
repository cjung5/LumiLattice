"""Research goal and scoring (spec 3.1, P0 #1): does a host or candidate meet the AR targets?

Each verdict cites the evidence it used, with its tag. A Heuristic range that spans the
target is "uncertain", never "meets".
"""

from typing import Literal

from pydantic import BaseModel, Field
from pymatgen.core import Composition, Element

from app.models.candidates import Candidate, StructuralAssessment
from app.models.evidence import PropertyValue
from app.tools.reference_db import ReferenceDB
from app.tools.registry import ToolError

Verdict = Literal["meets", "uncertain", "fails", "unknown"]


class Goal(BaseModel):
    target_n: float = Field(default=2.2, ge=1, le=5, description="Minimum n near 550 nm.")
    min_band_gap: float = Field(
        default=3.0, ge=0, le=15, description="Minimum band gap in eV (3.1 eV ≈ 400 nm edge)."
    )
    forbidden_elements: list[str] = Field(default_factory=list, max_length=40)


class Criterion(BaseModel):
    id: Literal["n", "band_gap", "elements", "structure"]
    verdict: Verdict
    detail: str
    evidence: PropertyValue | None = None


class GoalScore(BaseModel):
    subject: str  # candidate ID or formula
    goal: Goal
    criteria: list[Criterion]
    meets: int
    total: int


def threshold_verdict(pv: PropertyValue | None, threshold: float) -> Verdict:
    if pv is None or pv.status == "Unknown":
        return "unknown"
    if pv.value is not None:
        return "meets" if pv.value >= threshold else "fails"
    if pv.value_range is not None:
        low, high = pv.value_range
        if low >= threshold:
            return "meets"
        if high < threshold:
            return "fails"
        return "uncertain"
    return "unknown"


def _describe(pv: PropertyValue | None, label: str, threshold: float, unit: str) -> str:
    if pv is None or pv.status == "Unknown":
        return f"No {label} data."
    if pv.value is not None:
        value = f"{pv.value}{unit}"
    elif pv.value_range is not None:
        value = f"{pv.value_range[0]}–{pv.value_range[1]}{unit}"
    else:
        value = "—"
    method = f", {pv.provenance.method}" if pv.provenance and pv.provenance.method else ""
    return f"{label} {value} ({pv.status}{method}) vs target ≥ {threshold}{unit}."


def _criteria(
    formula: str,
    n: PropertyValue | None,
    gap: PropertyValue | None,
    assessment: StructuralAssessment | None,
    goal: Goal,
) -> list[Criterion]:
    elements = {el.symbol for el in Composition(formula).elements}
    banned = sorted(elements & {e.strip().capitalize() for e in goal.forbidden_elements})
    criteria = [
        Criterion(
            id="n",
            verdict=threshold_verdict(n, goal.target_n),
            detail=_describe(n, "n", goal.target_n, ""),
            evidence=n,
        ),
        Criterion(
            id="band_gap",
            verdict=threshold_verdict(gap, goal.min_band_gap),
            detail=_describe(gap, "Band gap", goal.min_band_gap, " eV")
            + (
                " DFT gaps can differ from measured gaps by up to about 1 eV."
                if gap is None or gap.status != "Experimental"
                else ""
            ),
            evidence=gap,
        ),
        Criterion(
            id="elements",
            verdict="fails" if banned else "meets",
            detail=f"Contains forbidden {', '.join(banned)}."
            if banned
            else "No forbidden elements.",
        ),
    ]
    if assessment is not None:
        verdict: Verdict = {
            "Structurally Plausible": "meets",
            "Structural Concerns": "uncertain",
            "Insufficient Evidence": "unknown",
        }[assessment.status]
        criteria.append(Criterion(id="structure", verdict=verdict, detail=assessment.status))
    return criteria


def _score(subject: str, goal: Goal, criteria: list[Criterion]) -> GoalScore:
    return GoalScore(
        subject=subject,
        goal=goal,
        criteria=criteria,
        meets=sum(c.verdict == "meets" for c in criteria),
        total=len(criteria),
    )


def score_candidate(candidate: Candidate, goal: Goal) -> GoalScore:
    optical = candidate.optical_estimate
    criteria = _criteria(
        candidate.formula,
        optical.estimate if optical else None,
        optical.band_gap if optical else None,
        candidate.assessment,
        goal,
    )
    return _score(candidate.candidate_id, goal, criteria)


def score_formula(
    formula: str, goal: Goal, db: ReferenceDB, assessment: StructuralAssessment | None = None
) -> GoalScore:
    for symbol in goal.forbidden_elements:
        if not Element.is_valid_symbol(symbol.strip().capitalize()):
            raise ToolError(f"{symbol!r} is not an element symbol.")
    return _score(
        formula,
        goal,
        _criteria(formula, db.best_n(formula), db.best_gap(formula), assessment, goal),
    )
