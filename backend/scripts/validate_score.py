"""Test the score's parts against data, and write data/validation.json.

Six tests:
1. Band-gap ranges against measured solid solutions (Zhuo et al. compositions with fractions).
2. Band-gap and n ranges against computed mixes (JARVIS TBmBJ), the only large test for n.
3. The optical score on known materials: waveguide materials against opaque and low-n controls.
4. The structural checks on real, unmodified crystals: every alarm here is a false alarm.
5. The atom-fit metric on swaps to real compounds and on implausible swaps. The charge-only cap
   was chosen on the first set, so the held-out set is the fair test.
6. Band-gap and n ranges on oxide solid solutions from text-mined databases, with the end-member
   values the app really uses. data/oxide_gap_review.json holds the hand-checked subset.

Tests 4 and 5 use about 200 Materials Project requests. Run from backend/:
    uv run python -m scripts.validate_score
"""

import ast
import csv
import io
import itertools
import json
import math
import random
import re
import statistics
import sys
import zipfile
from collections import defaultdict
from functools import cache
from pathlib import Path
from types import SimpleNamespace

from pymatgen.core import Composition

from app.config import BACKEND_DIR, get_settings
from app.models.candidates import Substitution
from app.models.evidence import Provenance
from app.storage.memory import MemoryStore
from app.tools.candidates import create_candidate
from app.tools.goals import Goal
from app.tools.materials import MaterialsProjectClient
from app.tools.reference_db import (
    GAP_MARGIN_EV,
    MAX_MINED_SPREAD_EV,
    N_MARGIN,
    get_reference_db,
)
from app.tools.registry import ToolError
from app.tools.scorecard import CHARGE_FAIL_CAP, CHECK_POINTS, fit_score, optical_score
from app.tools.validation import assess
from scripts.build_reference_db import MINED_CSV_NAME, mined_reports
from scripts.download_data import DATASETS

OUT = BACKEND_DIR / "data" / "validation.json"
GAP_CSV = DATASETS[2]["path"]
TOLERANCES = (0, 0.1, 0.2, 0.3, 0.5)
COMPUTED_SAMPLE = 2000
SEED = 0

# Named for AR waveguides: Huawei patent US11899241 (the oxides and Si3N4) and Coherent's 2024 note
# on high-index materials (LiNbO3, SiC). A sanity check, not proof: n and the gap build the score.
WAVEGUIDE = ("TiO2", "Si3N4", "LiNbO3", "SiC", "Nb2O5", "Ta2O5", "ZrO2", "HfO2")
OPAQUE = ("GaAs", "InP", "PbS", "Fe2O3", "GaSb", "InAs", "CdTe", "PbTe")  # absorb visible light
LOW_N = ("MgF2", "CaF2", "LiF", "SiO2", "BaF2", "NaF")  # clear, but they bend light too little

# (host ID, element to replace, new elements). 100% swaps, so the exact formula can be looked up.
SWAPS = (
    ("mp-5229", "Sr", ("Ca", "Ba", "Pb", "Mg", "Cd", "Mn", "Zn", "Be")),
    ("mp-5229", "Ti", ("Zr", "Hf", "Sn", "Ge", "Si", "Ce", "Mn", "Pb")),
    ("mp-390", "Ti", ("Zr", "Hf", "Sn", "Ge", "Si", "Ce")),
    ("mp-10695", "Zn", ("Cd", "Hg", "Be", "Mg", "Mn", "Ca", "Sr", "Ba")),
    ("mp-22862", "Na", ("Li", "K", "Rb", "Cs", "Ag", "Cu")),
    ("mp-1265", "Mg", ("Ca", "Sr", "Ba", "Mn", "Ni", "Co", "Cd", "Zn")),
    ("mp-1143", "Al", ("Ga", "In", "Cr", "Fe", "Sc", "Y", "La", "V")),
    ("mp-2741", "Ca", ("Sr", "Ba", "Cd", "Pb", "Mg", "Hg")),
    ("mp-804", "Ga", ("Al", "In", "B", "Sc", "Y")),
)
# Wrong charge, or far too large or too small for the site: the checks should object.
IMPLAUSIBLE = (
    ("mp-5229", "Sr", "Cs"),
    ("mp-5229", "Ti", "Na"),
    ("mp-5229", "Ti", "Cs"),
    ("mp-5229", "O", "Cl"),
    ("mp-1265", "Mg", "K"),
    ("mp-1143", "Al", "Cs"),
    ("mp-22862", "Na", "La"),
    ("mp-2741", "Ca", "Cs"),
    ("mp-804", "Ga", "Cs"),
    ("mp-10695", "Zn", "Cs"),
)


# The same kinds of test on hosts and swaps that played no part in choosing the charge-only cap.
HELD_OUT_SWAPS = (
    ("mp-2133", "Zn", ("Cd", "Mg", "Be", "Hg", "Ca", "Mn")),
    ("mp-1138", "Li", ("Na", "K", "Rb", "Cs")),
    ("mp-2998", "Ti", ("Zr", "Hf", "Sn", "Ce")),
    ("mp-2998", "Ba", ("Sr", "Ca", "Pb")),
    ("mp-1249", "Mg", ("Zn", "Mn", "Fe", "Co", "Ni")),
)
HELD_OUT_IMPLAUSIBLE = (
    ("mp-2133", "Zn", "Cs"),
    ("mp-2133", "Zn", "La"),
    ("mp-1138", "Li", "Ba"),
    ("mp-1138", "Li", "La"),
    ("mp-2998", "Ba", "Cs"),
    ("mp-2998", "Ti", "K"),
    ("mp-1249", "Mg", "Rb"),
    ("mp-1249", "Mg", "La"),
)
REAL_CRYSTALS = 40


MIN_SHARE = 0.1  # below this, a dopant more than a solid solution
REVIEW_FILE = BACKEND_DIR / "data" / "oxide_gap_review.json"
MINED_ZIP, INDEX_CSV = DATASETS[3]["path"], DATASETS[4]["path"]


def _spaced(formula: str) -> str:
    return " ".join(re.findall(r"[A-Z][a-z]?[\d.]*", formula))


def _visible(wavelength: str) -> bool:
    """True when no wavelength is stated, or the stated one is in the visible range."""
    match = re.match(r"\s*([\d.]+)\s*(nm|μm|µm|um)", wavelength or "")
    if not wavelength.strip():
        return True
    if not match:
        return False
    nm = float(match.group(1)) * (1 if match.group(2) == "nm" else 1000)
    return 400 <= nm <= 700


def rank_correlation(a: list[float], b: list[float]) -> float | None:
    """Spearman's rho with average ranks; None when a list is constant."""

    def ranks(values: list[float]) -> list[float]:
        order = sorted(range(len(values)), key=values.__getitem__)
        out = [0.0] * len(values)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
                j += 1
            for k in range(i, j + 1):
                out[order[k]] = (i + j) / 2
            i = j + 1
        return out

    ra, rb = ranks(a), ranks(b)
    if len(set(ra)) < 2 or len(set(rb)) < 2:
        return None
    return round(statistics.correlation(ra, rb), 3)


def area_under_curve(positives: list[float], negatives: list[float]) -> float | None:
    """The chance that a random positive scores above a random negative (ties count half)."""
    if not positives or not negatives:
        return None
    wins = sum(1.0 if p > n else 0.5 if p == n else 0.0 for p in positives for n in negatives)
    return round(wins / (len(positives) * len(negatives)), 3)


def site_groups(comp: Composition) -> list[tuple[str, ...]] | None:
    """Group the fractional elements into sites: Ga0.5 In0.5 As0.4 P0.6 -> (Ga, In), (As, P)."""
    amounts = {el.symbol: amount for el, amount in comp.items()}
    fractional = [e for e, a in amounts.items() if abs(a - round(a)) > 1e-3]
    if not 2 <= len(fractional) <= 6:
        return None

    def partition(items: list[str]) -> list[tuple[str, ...]] | None:
        if not items:
            return []
        first, others = items[0], items[1:]
        for size in range(1, len(others) + 1):
            for rest in itertools.combinations(others, size):
                total = amounts[first] + sum(amounts[e] for e in rest)
                if abs(total - round(total)) < 1e-3:
                    tail = partition([e for e in others if e not in rest])
                    if tail is not None:
                        return [(first, *rest), *tail]
        return None

    return partition(fractional)


def end_members(comp: Composition, groups: list[tuple[str, ...]]) -> list[tuple[str, float]]:
    """Each end member's reduced formula and its share in the mix."""
    amounts = {el.symbol: amount for el, amount in comp.items()}
    fixed = {e: a for e, a in amounts.items() if not any(e in g for g in groups)}
    ends = []
    for pick in itertools.product(*groups):
        composition = dict(fixed)
        share = 1.0
        for group, element in zip(groups, pick, strict=True):
            total = sum(amounts[e] for e in group)
            composition[element] = composition.get(element, 0) + total
            share *= amounts[element] / total
        ends.append((Composition(composition).reduced_formula, share))
    return ends


def measured_cases() -> list[dict]:
    reports: dict[str, list[float]] = defaultdict(list)
    with GAP_CSV.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            text, gap = row["composition"], float(row["Eg (eV)"])
            if "." not in text or "," in text or gap <= 0:
                continue
            try:
                reports[Composition(text).formula].append(gap)
            except (ValueError, KeyError):
                continue
    db = get_reference_db()
    cases = []
    for formula, gaps in reports.items():
        comp = Composition(formula)
        groups = site_groups(comp)
        if not groups:
            continue
        ends = end_members(comp, groups)
        values = [db.measured_gaps(end) for end, _ in ends]
        if not all(values):
            continue  # the app would mix in computed values; this test is measured against measured
        medians = [statistics.median(v) for v in values]
        cases.append(
            {
                "formula": formula.replace(" ", ""),
                "measured": statistics.median(gaps),
                "low": min(medians),
                "high": max(medians),
                "linear": sum(m * share for m, (_, share) in zip(medians, ends, strict=True)),
                "oxide": "O" in {el.symbol for el in comp.elements},
            }
        )
    return cases


def range_summary(cases: list[dict]) -> dict | None:
    if not cases:
        return None
    measured = [c["measured"] for c in cases]
    middle = [(c["low"] + c["high"]) / 2 for c in cases]
    below = sum(c["measured"] < c["low"] for c in cases)
    above = sum(c["measured"] > c["high"] for c in cases)
    return {
        "cases": len(cases),
        "inside": {
            f"{t}": round(
                sum(c["low"] - t <= c["measured"] <= c["high"] + t for c in cases) / len(cases), 3
            )
            for t in TOLERANCES
        },
        "below_range": below,
        "above_range": above,
        "error_of_midpoint": round(
            statistics.fmean(abs(m - c["measured"]) for m, c in zip(middle, cases, strict=True)), 3
        ),
        "error_of_linear_mix": round(
            statistics.fmean(abs(c["linear"] - c["measured"]) for c in cases), 3
        ),
        "rank_correlation_midpoint": rank_correlation(middle, measured),
        "rank_correlation_linear": rank_correlation([c["linear"] for c in cases], measured),
    }


def margin_holdout(cases: list[dict], margins=(0, 0.1, 0.2, 0.3, 0.5)) -> dict:
    """Pick the smallest margin that reaches 90% on one half, then test it on the other half."""
    shuffled = cases[:]
    random.Random(SEED).shuffle(shuffled)
    half = len(shuffled) // 2
    tune, test = shuffled[:half], shuffled[half:]

    def inside(rows: list[dict], margin: float) -> float:
        return sum(c["low"] - margin <= c["measured"] <= c["high"] + margin for c in rows) / len(
            rows
        )

    chosen = next((m for m in margins if inside(tune, m) >= 0.9), margins[-1])
    return {
        "chosen_margin_ev": chosen,
        "tune_cases": len(tune),
        "test_cases": len(test),
        "inside_on_tune": round(inside(tune, chosen), 3),
        "inside_on_test": round(inside(test, chosen), 3),
    }


@cache
def _oxidation_guess(formula: str) -> dict[str, float] | None:
    guesses = Composition(formula).oxi_state_guesses(max_sites=-1)
    return dict(guesses[0]) if guesses else None


def computed_cases() -> list[dict]:
    """Ordered JARVIS compounds that mix two compounds with one element swapped at the same charge.

    Example: BaSr3Ti4O12 between BaTiO3 and SrTiO3. CuInSe2 is not a mix of CuSe and InSe, because
    Cu and In have different charges, so it is left out. Median over polymorphs, as in the app.
    """
    db = get_reference_db()
    rows = db._db.execute(
        "SELECT formula, mbj_gap, eps_mbj FROM jarvis WHERE mbj_gap IS NOT NULL AND eps_mbj >= 1"
    ).fetchall()
    gaps: dict[str, list[float]] = defaultdict(list)
    index: dict[str, list[float]] = defaultdict(list)
    for formula, gap, eps in rows:
        gaps[formula].append(gap)
        index[formula].append(math.sqrt(eps))
    known = {f: (statistics.median(gaps[f]), statistics.median(index[f])) for f in gaps}
    candidates = sorted(f for f in known if len(Composition(f).elements) >= 3)
    random.Random(SEED).shuffle(candidates)
    cases = []
    for formula in candidates:
        if len(cases) >= COMPUTED_SAMPLE:
            break
        comp = Composition(formula)
        amounts = {el.symbol: a for el, a in comp.items()}
        for a, b in itertools.combinations(amounts, 2):
            total = amounts[a] + amounts[b]
            base = {e: v for e, v in amounts.items() if e not in (a, b)}
            end_a = Composition({**base, a: total}).reduced_formula
            end_b = Composition({**base, b: total}).reduced_formula
            if end_a not in known or end_b not in known:
                continue
            guess_a, guess_b = _oxidation_guess(end_a), _oxidation_guess(end_b)
            if not guess_a or not guess_b or guess_a.get(a) != guess_b.get(b):
                continue
            cases.append(
                {
                    "formula": formula,
                    "gap": known[formula][0],
                    "n": known[formula][1],
                    "gap_ends": (known[end_a][0], known[end_b][0]),
                    "n_ends": (known[end_a][1], known[end_b][1]),
                    "share": amounts[a] / total,
                    "oxide": "O" in amounts,
                }
            )
            break
    return cases


def computed_summary(cases: list[dict], key: str, ends: str) -> dict | None:
    rows = [
        {
            "measured": c[key],
            "low": min(c[ends]),
            "high": max(c[ends]),
            "linear": c["share"] * c[ends][0] + (1 - c["share"]) * c[ends][1],
        }
        for c in cases
    ]
    return range_summary(rows)


def _charge_balanced(formula: str) -> bool:
    return bool(_oxidation_guess(formula))


def _oxide_case(comp: Composition, value, best, label: str = "") -> dict | None:
    """Ends are the charge-balanced corners, and each must have a value in the app's own data."""
    groups = site_groups(comp)
    if not groups:
        return None
    ends = [(e, share) for e, share in end_members(comp, groups) if _charge_balanced(e)]
    if len(ends) < 2 or min(share for _, share in ends) < MIN_SHARE:
        return None
    values = [best(e).value for e, _ in ends]
    if any(v is None for v in values):
        return None
    total = sum(share for _, share in ends)
    return {
        "formula": label or comp.formula.replace(" ", ""),
        "measured": value,
        "low": min(values),
        "high": max(values),
        "linear": sum(v * s for v, (_, s) in zip(values, ends, strict=True)) / total,
        "system": "–".join(sorted(e for e, _ in ends)),
    }


def by_system(cases: list[dict], margin: float) -> dict:
    """Each chemical system gets one vote, so MgO-ZnO cannot outvote everything else."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for case in cases:
        groups[case["system"]].append(case)
    shares = [
        sum(c["low"] - margin <= c["measured"] <= c["high"] + margin for c in rows) / len(rows)
        for rows in groups.values()
    ]
    largest = max(groups, key=lambda k: len(groups[k]))
    return {
        "systems": len(groups),
        "mean_share_inside": round(statistics.fmean(shares), 3),
        "largest_system": largest,
        "largest_system_cases": len(groups[largest]),
    }


def mined_against_computed() -> dict:
    """Compiled measured gaps (Zhuo et al.) as the reference for text-mined medians and TBmBJ."""
    db = get_reference_db()
    rows = []
    for formula, median, q1, q3, _ in db._db.execute(
        "SELECT formula, median, q1, q3, reports FROM mined_gaps"
    ):
        compiled = db.measured_gaps(formula)
        computed = [c.band_gap_mbj for c in db.computed(formula) if c.band_gap_mbj is not None]
        if compiled and computed:
            reference = statistics.median(compiled)
            rows.append(
                {
                    "spread": q3 - q1,
                    "mined": abs(median - reference),
                    "tbmbj": abs(statistics.median(computed) - reference),
                    "oxide": "O" in {el.symbol for el in Composition(formula).elements},
                }
            )

    def summary(selected: list[dict]) -> dict:
        return {
            "formulas": len(selected),
            "mean_error_mined": round(statistics.fmean(r["mined"] for r in selected), 3),
            "mean_error_tbmbj": round(statistics.fmean(r["tbmbj"] for r in selected), 3),
        }

    tight = [r for r in rows if r["spread"] <= MAX_MINED_SPREAD_EV]
    wide = [r for r in rows if r["spread"] > MAX_MINED_SPREAD_EV]
    return {
        "spread_within_limit": summary(tight),
        "spread_within_limit_oxides": summary([r for r in tight if r["oxide"]]),
        "spread_over_limit": summary(wide),
        "spread_over_limit_oxides": summary([r for r in wide if r["oxide"]]),
        "note": (
            "The limit was chosen on this comparison. Some reports can appear in both sources, so "
            "the text-mined error can be too low."
        ),
    }


def oxide_tests() -> dict:
    db = get_reference_db()
    with zipfile.ZipFile(MINED_ZIP) as z, z.open(MINED_CSV_NAME) as f:
        reports: dict[str, list[float]] = defaultdict(list)
        for comp, gap, _ in mined_reports(io.TextIOWrapper(f, encoding="utf-8", errors="replace")):
            fractional = any(abs(a - round(a)) > 1e-6 for a in comp.values())
            if fractional and "O" in {el.symbol for el in comp.elements}:
                reports[comp.formula].append(gap)
    mined = [
        case
        for formula, gaps in reports.items()
        if (case := _oxide_case(Composition(formula), statistics.median(gaps), db.best_gap))
    ]

    review = json.loads(REVIEW_FILE.read_text())["cases"]
    reviewed = [
        case
        for row in review
        if row["value_ev"] is not None
        and (
            case := _oxide_case(
                Composition(_spaced(row["formula"])), row["value_ev"], db.best_gap, row["formula"]
            )
        )
    ]
    clear = [c for c in reviewed if c["measured"] >= 2.5]
    no_mgzn = [c for c in clear if c["system"] != "MgO–ZnO"]

    index_reports: dict[str, list[float]] = defaultdict(list)
    whole_index: dict[str, list[float]] = defaultdict(list)
    with INDEX_CSV.open(encoding="utf-8", errors="replace", newline="") as f:
        csv.field_size_limit(10**8)
        for row in csv.DictReader(f):
            name = row["normalised_name"]
            if row["property_type"] != "Refractive Index" or not name.startswith("["):
                continue
            if not _visible(row["measurement_wavelength"]):
                continue
            try:
                comp = Composition(
                    {element: float(amount) for element, amount in ast.literal_eval(name)}
                )
                value = float(row["extracted_value"])
            except (ValueError, SyntaxError, TypeError, KeyError, IndexError):
                continue
            if (
                not comp.valid
                or not 1 < value < 5
                or "O" not in {el.symbol for el in comp.elements}
            ):
                continue
            if any(abs(a - round(a)) > 1e-6 for a in comp.values()):
                index_reports[comp.formula].append(value)
            else:
                whole_index[comp.reduced_formula].append(value)

    def index_of(formula: str) -> SimpleNamespace:
        """Measured n when the app has it. Computed n is left out: for metals it is far too high."""
        best = db.best_n(formula)
        if best.status == "Experimental":
            return SimpleNamespace(value=best.value)
        reports = whole_index.get(formula, [])
        return SimpleNamespace(value=statistics.median(reports) if len(reports) >= 3 else None)

    index_cases = [
        case
        for formula, values in index_reports.items()
        if (case := _oxide_case(Composition(formula), statistics.median(values), index_of))
    ]
    return {
        "gap_mined_unreviewed": range_summary(mined),
        "gap_reviewed": range_summary(reviewed),
        "gap_reviewed_clear": range_summary(clear),
        "gap_reviewed_clear_by_system": by_system(clear, GAP_MARGIN_EV),
        "gap_reviewed_clear_without_mgzno": range_summary(no_mgzn),
        "review_counts": {
            verdict: sum(r["verdict"] == verdict for r in review)
            for verdict in ("ok", "corrected", "excluded")
        },
        "n_mined_unreviewed": range_summary(index_cases),
        "n_by_system": by_system(index_cases, N_MARGIN) if index_cases else None,
        "note": (
            "Gap end members use the app's own values. Minority share at least 10%. The gap review "
            "read up to two source sentences per composition and chose compositions with a "
            "text-mined gap of at least 2.5 eV. n was not reviewed (most rows have no source "
            "sentence): end members use measured n, or a median of at least 3 text-mined values, "
            "and several of the n cases are films, which can have lower n than bulk crystals."
        ),
    }


def control_scores(goal: Goal) -> dict:
    db = get_reference_db()

    def scored(formulas: tuple[str, ...]) -> dict[str, float]:
        out = {}
        for formula in formulas:
            n, gap = db.best_n(formula), db.best_gap(formula)
            if n.value is not None and gap.value is not None:
                out[formula] = round(optical_score(n.value, gap.value, goal), 1)
        return out

    waveguide, opaque, low_n = scored(WAVEGUIDE), scored(OPAQUE), scored(LOW_N)
    return {
        "lowest_waveguide": min(waveguide.values()),
        "highest_opaque": max(opaque.values()),
        "highest_low_n": max(low_n.values()),
        "waveguide": waveguide,
        "opaque": opaque,
        "low_n": low_n,
        "beats_opaque": area_under_curve(list(waveguide.values()), list(opaque.values())),
        "lowest_waveguide_note": "SiC: the text-mined 2.4 eV is mainly cubic 3C-SiC; AR waveguides use hexagonal SiC.",
        "beats_low_n": area_under_curve(list(waveguide.values()), list(low_n.values())),
        "note": "A sanity check, not proof: n and the band gap also build the score.",
    }


def _check_rates(assessments: list) -> dict:
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for assessment in assessments:
        for check in assessment.checks:
            if check.status in CHECK_POINTS:
                counts[check.id][check.status] += 1
    rate = lambda c, status: round(c[status] / max(1, sum(c.values())), 3)
    return {
        "pass_rate": {k: rate(c, "pass") for k, c in counts.items()},
        "warn_rate": {k: rate(c, "warn") for k, c in counts.items()},
        "fail_rate": {k: rate(c, "fail") for k, c in counts.items()},
    }


def real_crystal_test(mp: MaterialsProjectClient) -> dict:
    """Observed, stable crystals with no swap, in their own positions, so no alarm is deserved."""
    formulas = sorted({p.formula for p in get_reference_db().landscape().measured})
    random.Random(SEED).shuffle(formulas)
    assessments, names = [], []
    for formula in formulas:
        if len(assessments) >= REAL_CRYSTALS:
            break
        try:
            records = [
                r for r in mp.search(formula=formula, limit=5) if not r.theoretical and r.is_stable
            ]
            if not records:
                continue
            assessment = assess(mp.get_structure(records[0].material_id))
        except ToolError as exc:
            print(f"skip {formula}: {exc}", file=sys.stderr)
            continue
        if assessment.status == "Insufficient Evidence":
            continue
        assessments.append(assessment)
        names.append((formula, assessment.status))
    return {
        "crystals": len(assessments),
        "no_alarm": sum(status == "Structurally Plausible" for _, status in names),
        **_check_rates(assessments),
        "with_alarm": [f for f, status in names if status != "Structurally Plausible"],
        "note": "Real crystals at their own geometry, so every warning and failure here is a false alarm.",
    }


def fit_test(mp: MaterialsProjectClient, swaps, implausible_swaps) -> dict:
    """Swaps to real compounds against implausible ones, at the host's positions (no relaxation)."""
    store = MemoryStore()
    hosts = {}

    def make(material_id: str, old: str, new: str):
        if material_id not in hosts:
            hosts[material_id] = mp.get_structure(material_id)
        # No analog lookup: the check that asks Materials Project would leak the label.
        return create_candidate(
            store,
            hosts[material_id],
            Provenance(source="validation", reference=material_id),
            [Substitution(element_from=old, element_to=new, fraction=1)],
        )

    cases: list[dict] = []
    assessments = []
    for material_id, old, news in swaps:
        for new in news:
            try:
                candidate = make(material_id, old, new)
                records = mp.search(formula=candidate.formula, limit=5)
            except ToolError as exc:
                print(f"skip {material_id} {old}->{new}: {exc}", file=sys.stderr)
                continue
            score = fit_score(candidate.assessment)
            if score is None:
                continue
            assessments.append(candidate.assessment)
            cases.append(
                {
                    "formula": candidate.formula,
                    "fit": round(score, 1),
                    "observed": any(not r.theoretical for r in records),
                }
            )
    real = [c["fit"] for c in cases if c["observed"]]
    implausible, bad_assessments = [], []
    for material_id, old, new in implausible_swaps:
        try:
            candidate = make(material_id, old, new)
        except ToolError as exc:
            print(f"skip {material_id} {old}->{new}: {exc}", file=sys.stderr)
            continue
        bad_assessments.append(candidate.assessment)
        implausible.append(
            {
                "swap": f"{old}->{new} in {material_id}",
                "formula": candidate.formula,
                "fit": round(fit_score(candidate.assessment) or 0, 1),
            }
        )
    bad = [c["fit"] for c in implausible]
    return {
        "swaps": len(real),
        "not_observed_left_out": len(cases) - len(real),
        "kept_above_cap": sum(f > CHARGE_FAIL_CAP for f in real),
        "implausible_total": len(bad),
        "implausible_capped": sum(f <= CHARGE_FAIL_CAP for f in bad),
        "mean_fit_real": round(statistics.fmean(real), 1) if real else None,
        "mean_fit_implausible": round(statistics.fmean(bad), 1) if bad else None,
        "auc_real_vs_implausible": area_under_curve(real, bad),
        "real_compound_checks": _check_rates(assessments),
        "implausible_checks": _check_rates(bad_assessments),
        "implausible": implausible,
        "cases": cases,
    }


def main(path: Path = OUT) -> int:
    settings = get_settings()
    measured = measured_cases()
    wide = [c for c in measured if c["measured"] >= 2]
    oxides = [c for c in measured if c["oxide"]]
    computed = computed_cases()
    computed_wide = [c for c in computed if c["gap"] >= 2 and c["oxide"]]
    report = {
        "applied_margins": {"gap_ev": GAP_MARGIN_EV, "n": N_MARGIN},
        "measured_gap_ranges": {
            "all": range_summary(measured),
            "gap_at_least_2_ev": range_summary(wide),
            "oxides": range_summary(oxides),
            "margin_holdout": margin_holdout(measured),
            "note": (
                "Solid solutions with fractional compositions in the Zhuo et al. compilation, with "
                "measured values for every end member. Most are III-V and chalcogenide semiconductors."
            ),
        },
        "computed_ranges": {
            "gap_all": computed_summary(computed, "gap", "gap_ends"),
            "n_all": computed_summary(computed, "n", "n_ends"),
            "gap_oxides_wide": computed_summary(computed_wide, "gap", "gap_ends"),
            "n_oxides_wide": computed_summary(computed_wide, "n", "n_ends"),
            "note": (
                "Ordered JARVIS compounds between two compounds with one element swapped at the "
                "same charge, all TBmBJ. n = sqrt(eps) is a long-wavelength value. Median over "
                "polymorphs, so the phases can differ."
            ),
        },
        "optical_score_controls": control_scores(Goal()),
        "oxides": oxide_tests(),
        "mined_gaps_against_computed": mined_against_computed(),
    }
    if settings.mp_api_key is None:
        print("MP_API_KEY is not set: skipping the atom-fit test.", file=sys.stderr)
    else:
        mp = MaterialsProjectClient(settings.mp_api_key.get_secret_value())
        try:
            report["real_crystals"] = real_crystal_test(mp)
            report["atom_fit_tuning"] = fit_test(mp, SWAPS, IMPLAUSIBLE)
            report["atom_fit_holdout"] = fit_test(mp, HELD_OUT_SWAPS, HELD_OUT_IMPLAUSIBLE)
        finally:
            mp.close()
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
