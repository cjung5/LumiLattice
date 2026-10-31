"""Scorecard: a 0-100 score that ranks a candidate against the goal and against known materials.

The score is a low-high range: it is computed for the worst and the best end of the evidence, so
weak evidence gives a wide range instead of a false precise number. It ranks ideas. It is not a
probability that the material can be made or will work, and the weights are a design choice.

The benchmark scores the materials with a measured n the same way, on the three optical metrics
only, because they have no candidate structure to check.
"""

import itertools
import json
import math
from functools import lru_cache
from typing import Literal

from pydantic import BaseModel
from pymatgen.analysis.hhi import HHIModel
from pymatgen.core import Composition, Structure

from app.config import BACKEND_DIR
from app.models.candidates import Candidate, StructuralAssessment
from app.models.evidence import EvidenceStatus, PropertyValue
from app.tools.goals import Goal
from app.tools.reference_db import MOSS_CONSTANT_EV, ReferenceDB
from app.tools.spatial import symmetry_of

MetricId = Literal["n", "band_gap", "trade_off", "isotropy", "fit", "supply"]
WEIGHTS: dict[MetricId, int] = {
    "n": 30,
    "band_gap": 30,
    "trade_off": 10,
    "isotropy": 10,
    "fit": 15,
    "supply": 5,
}
OPTICAL: tuple[MetricId, ...] = ("n", "band_gap", "trade_off")
# Well-known optical materials to compare with. Not a top list: one outlier report can lead that.
LANDMARKS = ("TiO2", "ZrO2", "ZnS", "SrTiO3", "LiNbO3", "BaTiO3", "Ta2O5", "Nb2O5", "SiO2", "Al2O3")
# "Model": computed here from the candidate's structure or composition, not looked up.
MetricEvidence = EvidenceStatus | Literal["Model"]
ISOTROPY_POINTS = {"isotropic": 100.0, "uniaxial": 60.0, "biaxial": 30.0}
CHECK_POINTS = {"pass": 100.0, "warn": 50.0, "fail": 0.0}
# Only charge caps the metric: real compounds pass it and impossible swaps fail it. The geometry
# checks fail for many real compounds, because the atoms stay in the host's positions.
CHARGE_FAIL_CAP = 30.0
EVIDENCE_ORDER: tuple[EvidenceStatus, ...] = (
    "Unknown",
    "Heuristic",
    "DFT-computed",
    "Experimental",
)
METHOD = (
    "Weights: n and band gap 60 together, n-gap trade-off 10, optical isotropy 10, atom fit 15, "
    "element supply 5. n and the band gap are combined as a geometric mean, because AR glasses "
    "need both and one cannot make up for the other. The goal value earns 70 points on each. A "
    "range is the worst and best end of the evidence, and a metric with no data counts as 0 to "
    "100. This score ranks ideas; it is not a probability that the material can be made or will "
    "work."
)
VALIDATION_FILE = BACKEND_DIR / "data" / "validation.json"


class Metric(BaseModel):
    id: MetricId
    weight: int
    low: float
    high: float
    value: str | None  # the number behind the points, e.g. "2.067–2.432"
    evidence: MetricEvidence
    detail: str


class BenchmarkEntry(BaseModel):
    formula: str
    score: float
    n: float
    band_gap: float


class Benchmark(BaseModel):
    """Where the candidate's optical score falls among materials with a measured n."""

    size: int
    beats_low: int
    beats_high: int
    host: BenchmarkEntry | None
    landmarks: list[BenchmarkEntry]  # highest score first
    note: str


class Validation(BaseModel):
    """How the score's parts did in scripts/validate_score.py; percentages."""

    gap_cases: int
    gap_inside: int
    oxide_cases: int
    oxide_inside: int
    oxide_systems: int
    oxide_other_cases: int
    oxide_other_inside: int
    oxide_other_rank: float
    n_cases: int
    n_inside: int
    swaps: int
    swaps_kept: int
    implausible: int
    implausible_caught: int


class Scorecard(BaseModel):
    subject: str
    goal: Goal
    low: float
    high: float
    optical_low: float
    optical_high: float
    metrics: list[Metric]
    evidence_mix: dict[str, int]  # share of the score's weight, percent
    biggest_gain: MetricId  # the metric with the most points still open
    disqualified: list[str]  # forbidden elements in the candidate
    benchmark: Benchmark
    method: str
    validation: Validation | None = None


def ramp(x: float, anchors: list[tuple[float, float]]) -> float:
    """Piecewise-linear points, flat outside the first and last anchors."""
    if x <= anchors[0][0]:
        return anchors[0][1]
    for (x0, y0), (x1, y1) in itertools.pairwise(anchors):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return anchors[-1][1]


def n_points(n: float, goal: Goal) -> float:
    return ramp(
        n, [(min(1.3, goal.target_n - 0.1), 0), (goal.target_n, 70), (goal.target_n + 0.4, 100)]
    )


def gap_points(gap: float, goal: Goal) -> float:
    """0 points below 1.6 eV: the material absorbs nearly all visible light."""
    floor = min(1.6, goal.min_band_gap - 0.1)
    return ramp(gap, [(floor, 0), (goal.min_band_gap, 70), (goal.min_band_gap + 1.5, 100)])


def moss_ratio(n: float, gap: float) -> float:
    """Above 1: the material beats the usual trade-off between n and band gap."""
    return n**4 * gap / MOSS_CONSTANT_EV


def moss_points(ratio: float) -> float:
    return ramp(ratio, [(0.5, 0), (1, 50), (2, 100)])


def _span(pv: PropertyValue | None) -> tuple[float, float] | None:
    if pv is None or pv.status == "Unknown":
        return None
    if pv.value is not None:
        return (pv.value, pv.value)
    return pv.value_range


def _text(span: tuple[float, float] | None) -> str | None:
    if span is None:
        return None
    return f"{span[0]:.3g}" if span[0] == span[1] else f"{span[0]:.3g}–{span[1]:.3g}"


def _weakest(*values: PropertyValue | None) -> EvidenceStatus:
    statuses = [v.status if v else "Unknown" for v in values]
    return min(statuses, key=EVIDENCE_ORDER.index)


def _property_metric(
    metric: MetricId, pv: PropertyValue | None, points, goal_value: float, unit: str
) -> Metric:
    span = _span(pv)
    label = "n" if metric == "n" else "Band gap"
    if span is None:
        return Metric(
            id=metric,
            weight=WEIGHTS[metric],
            low=0,
            high=100,
            value=None,
            evidence="Unknown",
            detail=f"{label} is unknown, so this metric counts as 0 to 100.",
        )
    return Metric(
        id=metric,
        weight=WEIGHTS[metric],
        low=points(span[0]),
        high=points(span[1]),
        value=_text(span),
        evidence=pv.status,
        detail=f"{label} {_text(span)}{unit} against a goal of {goal_value}{unit} ({pv.status}).",
    )


def _trade_off_metric(candidate: Candidate) -> Metric:
    optical = candidate.optical_estimate
    n, gap = (optical.estimate, optical.band_gap) if optical else (None, None)
    # The end members are real pairs of n and gap; pairing the range's corners would invent some.
    both_exact = n and n.value is not None and gap and gap.value is not None
    ratios = (
        [
            moss_ratio(m.n.value, m.band_gap.value)
            for m in optical.end_members
            if m.n.value is not None and m.band_gap and m.band_gap.value is not None
        ]
        if optical and not both_exact
        else []
    )
    if len(ratios) < 2:
        n_span, gap_span = _span(n), _span(gap)
        if n_span is None or gap_span is None:
            return Metric(
                id="trade_off",
                weight=WEIGHTS["trade_off"],
                low=0,
                high=100,
                value=None,
                evidence="Unknown",
                detail="n or the band gap is unknown, so this metric counts as 0 to 100.",
            )
        ratios = [moss_ratio(n_span[0], gap_span[0]), moss_ratio(n_span[1], gap_span[1])]
    span = (round(min(ratios), 2), round(max(ratios), 2))
    return Metric(
        id="trade_off",
        weight=WEIGHTS["trade_off"],
        low=moss_points(span[0]),
        high=moss_points(span[1]),
        value=_text(span),
        evidence=_weakest(n, gap),
        detail=f"n^4 x gap / {MOSS_CONSTANT_EV:.0f} eV = {_text(span)}. Above 1 beats the usual trend.",
    )


def _isotropy_metric(structure: Structure, parent: Structure) -> Metric:
    """The ordered model can have lower symmetry than the real disordered crystal, which keeps
    the average symmetry of its host, so the two give the worst and the best case."""
    model, host = symmetry_of(structure), symmetry_of(parent)
    classes = [s.optical_class for s in (model, host) if s.optical_class]
    if not classes:
        return Metric(
            id="isotropy",
            weight=WEIGHTS["isotropy"],
            low=0,
            high=100,
            value=None,
            evidence="Unknown",
            detail="The symmetry could not be determined.",
        )
    points = [ISOTROPY_POINTS[c] for c in classes]
    names = list(dict.fromkeys(classes))
    return Metric(
        id="isotropy",
        weight=WEIGHTS["isotropy"],
        low=min(points),
        high=max(points),
        value=" – ".join(names),
        evidence="Model",
        detail=(
            f"Ordered model: {model.optical_class}. Host: {host.optical_class}. An isotropic "
            "crystal has one n in all directions, so light does not split."
        ),
    )


def fit_score(assessment: StructuralAssessment) -> float | None:
    points = [CHECK_POINTS[c.status] for c in assessment.checks if c.status in CHECK_POINTS]
    if not points:
        return None
    score = sum(points) / len(points)
    charge_failed = any(c.id == "charge" and c.status == "fail" for c in assessment.checks)
    return min(score, CHARGE_FAIL_CAP) if charge_failed else score


def _fit_metric(candidate: Candidate) -> Metric:
    score = fit_score(candidate.assessment)
    if score is None:
        return Metric(
            id="fit",
            weight=WEIGHTS["fit"],
            low=0,
            high=100,
            value=None,
            evidence="Unknown",
            detail="No structural check could run.",
        )
    statuses = [c.status for c in candidate.assessment.checks if c.status in CHECK_POINTS]
    passed = statuses.count("pass")
    return Metric(
        id="fit",
        weight=WEIGHTS["fit"],
        low=score,
        high=score,
        value=f"{passed}/{len(statuses)}",
        evidence="Model",
        detail=f"{passed} of {len(statuses)} structural checks passed ({candidate.assessment.status}).",
    )


@lru_cache(maxsize=1)
def _hhi_model() -> HHIModel:
    return HHIModel()


def _supply_metric(formula: str) -> Metric:
    """Herfindahl-Hirschman index of element production (Gaultois et al., Chem. Mater. 2013)."""
    try:
        hhi = _hhi_model().get_hhi_production(Composition(formula))
    except (KeyError, TypeError, ValueError):
        hhi = None
    if hhi is None:
        return Metric(
            id="supply",
            weight=WEIGHTS["supply"],
            low=0,
            high=100,
            value=None,
            evidence="Unknown",
            detail="No supply data for at least one element.",
        )
    score = ramp(hhi, [(1000, 100), (2500, 50), (6000, 0)])
    return Metric(
        id="supply",
        weight=WEIGHTS["supply"],
        low=score,
        high=score,
        value=f"{hhi:.0f}",
        evidence="Model",
        detail=f"Element production concentration (HHI) {hhi:.0f}. Lower means more producers.",
    )


def _weighted(scores: dict[MetricId, float], ids: tuple[MetricId, ...]) -> float:
    """n and the gap combine as a geometric mean: an opaque material gets 0 on that part, however
    strongly it bends light."""
    rest = [i for i in ids if i not in ("n", "band_gap")]
    core = WEIGHTS["n"] + WEIGHTS["band_gap"]
    both = math.sqrt(scores["n"] * scores["band_gap"])
    total = core * both + sum(WEIGHTS[i] * scores[i] for i in rest)
    return total / (core + sum(WEIGHTS[i] for i in rest))


def optical_score(n: float, gap: float, goal: Goal) -> float:
    scores: dict[MetricId, float] = {
        "n": n_points(n, goal),
        "band_gap": gap_points(gap, goal),
        "trade_off": moss_points(moss_ratio(n, gap)),
    }
    return _weighted(scores, OPTICAL)


def reference_scores(db: ReferenceDB, goal: Goal) -> list[BenchmarkEntry]:
    entries = [
        BenchmarkEntry(
            formula=p.formula,
            score=round(optical_score(p.n, p.band_gap, goal), 1),
            n=p.n,
            band_gap=p.band_gap,
        )
        for p in db.landscape().measured
    ]
    return sorted(entries, key=lambda e: -e.score)


def _benchmark(
    candidate: Candidate, goal: Goal, db: ReferenceDB, low: float, high: float
) -> Benchmark:
    references = reference_scores(db, goal)
    root = candidate.transformation.root_formula
    n, gap = db.best_n(root), db.best_gap(root)
    host = (
        BenchmarkEntry(
            formula=root,
            score=round(optical_score(n.value, gap.value, goal), 1),
            n=n.value,
            band_gap=gap.value,
        )
        if n.value is not None and gap.value is not None
        else None
    )
    return Benchmark(
        size=len(references),
        beats_low=sum(e.score < low for e in references),
        beats_high=sum(e.score < high for e in references),
        host=host,
        landmarks=[e for e in references if e.formula in LANDMARKS],
        note=(
            "Materials with a measured n at 550 nm in refractiveindex.info, scored on the three "
            "optical metrics. This set favors materials already used in optics, not all of them "
            "have a measured band gap, and some reports are doubtful (BP is listed at 4.2 eV)."
        ),
    )


@lru_cache(maxsize=1)
def load_validation() -> Validation | None:
    """Numbers from the committed report; the panel works without them."""
    try:
        report = json.loads(VALIDATION_FILE.read_text())
        gaps = report["measured_gap_ranges"]["all"]
        oxides = report["oxides"]
        clear = oxides["gap_reviewed_clear"]
        other = oxides["gap_reviewed_clear_without_mgzno"]
        n = oxides["n_mined_unreviewed"]
        fit = report["atom_fit_holdout"]
        gap_margin = str(report["applied_margins"]["gap_ev"])
        n_margin = str(report["applied_margins"]["n"])
        return Validation(
            gap_cases=gaps["cases"],
            gap_inside=round(100 * gaps["inside"][gap_margin]),
            oxide_cases=clear["cases"],
            oxide_inside=round(100 * clear["inside"][gap_margin]),
            oxide_systems=oxides["gap_reviewed_clear_by_system"]["systems"],
            oxide_other_cases=other["cases"],
            oxide_other_inside=round(100 * other["inside"][gap_margin]),
            oxide_other_rank=other["rank_correlation_midpoint"],
            n_cases=n["cases"],
            n_inside=round(100 * n["inside"][n_margin]),
            swaps=fit["swaps"],
            swaps_kept=fit["kept_above_cap"],
            implausible=fit["implausible_total"],
            implausible_caught=fit["implausible_capped"],
        )
    except (OSError, KeyError, TypeError, ValueError):
        return None


def build_scorecard(
    candidate: Candidate, structure: Structure, parent: Structure, goal: Goal, db: ReferenceDB
) -> Scorecard:
    optical = candidate.optical_estimate
    metrics = [
        _property_metric(
            "n",
            optical.estimate if optical else None,
            lambda x: n_points(x, goal),
            goal.target_n,
            "",
        ),
        _property_metric(
            "band_gap",
            optical.band_gap if optical else None,
            lambda x: gap_points(x, goal),
            goal.min_band_gap,
            " eV",
        ),
        _trade_off_metric(candidate),
        _isotropy_metric(structure, parent),
        _fit_metric(candidate),
        _supply_metric(candidate.formula),
    ]
    for metric in metrics:
        metric.low, metric.high = round(metric.low, 1), round(metric.high, 1)
    lows = {m.id: m.low for m in metrics}
    highs = {m.id: m.high for m in metrics}
    total = sum(WEIGHTS.values())
    optical_low, optical_high = _weighted(lows, OPTICAL), _weighted(highs, OPTICAL)
    mix: dict[str, int] = {}
    for metric in metrics:
        mix[metric.evidence] = mix.get(metric.evidence, 0) + metric.weight
    elements = {el.symbol for el in Composition(candidate.formula).elements}
    banned = sorted(elements & {e.strip().capitalize() for e in goal.forbidden_elements})
    return Scorecard(
        subject=candidate.candidate_id,
        goal=goal,
        low=round(_weighted(lows, tuple(WEIGHTS)), 1),
        high=round(_weighted(highs, tuple(WEIGHTS)), 1),
        optical_low=round(optical_low, 1),
        optical_high=round(optical_high, 1),
        metrics=metrics,
        evidence_mix={k: round(100 * v / total) for k, v in mix.items()},
        biggest_gain=max(metrics, key=lambda m: m.weight * (100 - (m.low + m.high) / 2)).id,
        disqualified=banned,
        benchmark=_benchmark(candidate, goal, db, optical_low, optical_high),
        method=METHOD,
        validation=load_validation(),
    )
