from datetime import datetime
from typing import Literal

from pydantic import BaseModel

CritiqueVerdict = Literal["promising", "mixed", "weak", "insufficient_evidence"]


class EvidenceItem(BaseModel):
    """One computed fact the model may cite, by ID."""

    id: str
    group: Literal["check", "site", "optics", "goal", "spatial", "relaxation", "measurement"]
    text: str


class CritiquePoint(BaseModel):
    kind: Literal["strength", "concern", "open_question"]
    text: str
    evidence: list[str]
    # "image": seen in the rendered views only, so weaker than computed evidence.
    basis: Literal["evidence", "image", "both"]


class CritiqueSuggestion(BaseModel):
    change: str
    rationale: str
    evidence: list[str]


class Critique(BaseModel):
    """Muse Spark's review of a candidate. An opinion that cites evidence; never evidence itself."""

    created_at: datetime
    model: str
    locale: str
    geometry: Literal["unrelaxed", "relaxed"]
    views: int  # rendered structure images sent with the evidence
    verdict: CritiqueVerdict
    summary: str
    points: list[CritiquePoint]
    suggestions: list[CritiqueSuggestion]
    questions: list[str]
    evidence: list[EvidenceItem]  # exactly what the model saw
    warnings: list[str] = []  # citation or number problems left after one retry
