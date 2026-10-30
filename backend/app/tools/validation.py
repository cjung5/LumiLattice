"""Structural feasibility checks (spec 3.4).

These checks test basic chemical and geometric plausibility. They do not predict whether
a material can be synthesized. All thresholds are heuristic and are reported with each check.
Atom positions are not relaxed, so the checks describe the host geometry with new elements.
"""

import math
from collections.abc import Callable

from pymatgen.core import Structure

from app.models.candidates import CheckResult, StructuralAssessment
from app.tools.ionic import (
    BV_B,
    IonicModel,
    anion_shell,
    bond_valence_sum,
    ionic_model,
    shannon_radius,
)

OVERLAP_DISTANCE = 1.2  # Å: closer than this, two atoms effectively overlap
SHORT_BOND_RATIO = 0.8  # cation-anion distance below 0.8 x (r_cation + r_anion)
BOND_MISMATCH_WARN, BOND_MISMATCH_FAIL = 0.10, 0.20
# BVS deviation is graded by the bond-length change it implies: b * ln(BVS / V) / mean d.
# BVS is exponential in distance, so raw BVS percentages would overstate small misfits.
BVS_WARN, BVS_FAIL = 0.04, 0.10
TOLERANCE_PASS = (0.85, 1.06)
TOLERANCE_WARN = (0.80, 1.10)
NO_RELAXATION_NOTE = (
    "No relaxation: atoms stay at the host positions, so the checks show how well the new "
    "elements fit the host geometry. A real material would adjust its lattice."
)
RELAXED_NOTE = (
    "Relaxed with CHGNet (machine-learned potential): atoms and cell moved to lower energy, "
    "so the checks describe the relaxed geometry. Still not a synthesis prediction."
)
RADII_METHOD = "Shannon (1976) ionic radii"
BVS_METHOD = f"Bond valence sum, O'Keeffe & Brese (1991) universal parameters, b = {BV_B} Å"

AnalogLookup = Callable[[str], list[str]]


def _graded(deviation: float, warn: float, fail: float) -> str:
    return "fail" if abs(deviation) > fail else "warn" if abs(deviation) > warn else "pass"


def _cation_sites(structure: Structure, model: IonicModel, focus: list[int] | None) -> list[int]:
    sites = focus if focus is not None else range(len(structure))
    return [i for i in sites if not model.is_anion(structure[i].specie.symbol)]


def check_charge(structure: Structure, model: IonicModel, focus: list[int]) -> CheckResult:
    formula = structure.composition.reduced_formula
    if model.assumed:
        return CheckResult(
            id="charge",
            name="Oxidation states and charge neutrality",
            status="fail",
            message=f"No charge-balanced assignment with common oxidation states for {formula}.",
            atom_indices=focus,
            method="pymatgen Composition.oxi_state_guesses",
        )
    mixed = {el: v for el, v in model.oxidation_states.items() if abs(v - round(v)) > 1e-3}
    states = ", ".join(f"{el} {v:+g}" for el, v in model.oxidation_states.items())
    if mixed:
        mixed_text = ", ".join(f"{el} (average {v:+.2f})" for el, v in mixed.items())
        indices = [i for i, s in enumerate(structure) if s.specie.symbol in mixed]
        return CheckResult(
            id="charge",
            name="Oxidation states and charge neutrality",
            status="warn",
            message=f"Charge balance needs mixed valence: {mixed_text}. Consider a charge-compensating co-substitution.",
            atom_indices=indices,
            values={"assignment": states},
            method="pymatgen Composition.oxi_state_guesses",
        )
    return CheckResult(
        id="charge",
        name="Oxidation states and charge neutrality",
        status="pass",
        message=f"Charge-balanced with common oxidation states: {states}.",
        values={"assignment": states},
        method="pymatgen Composition.oxi_state_guesses",
    )


def check_distances(structure: Structure, model: IonicModel) -> CheckResult:
    flagged: list[int] = []
    shortest = math.inf
    worst = ""
    for i, site in enumerate(structure):
        for n in structure.get_neighbors(site, 3.0):
            if n.index < i:  # each pair once
                continue
            d = n.nn_distance
            if d < shortest:
                shortest, worst = d, f"{site.specie.symbol}{i}-{n.specie.symbol}{n.index}"
            too_close = d < OVERLAP_DISTANCE
            if not too_close and model.is_anion(n.specie.symbol) != model.is_anion(
                site.specie.symbol
            ):
                cation, anion = (site, n) if model.is_anion(n.specie.symbol) else (n, site)
                rc = shannon_radius(
                    cation.specie.symbol, model.oxidation_states[cation.specie.symbol], 6
                )
                ra = shannon_radius(
                    anion.specie.symbol, model.oxidation_states[anion.specie.symbol], 6
                )
                too_close = bool(rc and ra and d < SHORT_BOND_RATIO * (rc[0] + ra[0]))
            if too_close:
                flagged.extend([i, n.index])
    values = {"shortest_distance_A": round(shortest, 3), "shortest_pair": worst}
    if flagged:
        return CheckResult(
            id="distances",
            name="Interatomic distances",
            status="fail",
            message=f"Some atoms are too close (shortest {shortest:.2f} Å, {worst}).",
            atom_indices=sorted(set(flagged)),
            values=values,
            method=f"Overlap below {OVERLAP_DISTANCE} Å or cation-anion below {SHORT_BOND_RATIO} x radius sum",
        )
    return CheckResult(
        id="distances",
        name="Interatomic distances",
        status="pass",
        message=f"No overlapping atoms. Shortest distance {shortest:.2f} Å ({worst}).",
        values=values,
        method=f"Overlap below {OVERLAP_DISTANCE} Å or cation-anion below {SHORT_BOND_RATIO} x radius sum",
    )


def check_sites(
    structure: Structure, model: IonicModel, sites: list[int]
) -> tuple[CheckResult, CheckResult, CheckResult]:
    """Bond-length fit, coordination, and bond valence sum for each focus cation site."""
    fit_status, fit_msgs, fit_atoms = "pass", [], []
    cn_status, cn_msgs, cn_atoms = "pass", [], []
    bvs_status, bvs_msgs, bvs_atoms = "pass", [], []
    order = {"pass": 0, "info": 0, "warn": 1, "fail": 2}

    def worse(current: str, new: str) -> str:
        return new if order[new] > order[current] else current

    for i in sites:
        symbol = structure[i].specie.symbol
        oxi = model.oxidation_states[symbol]
        shell = anion_shell(structure, i, model)
        if not shell:
            continue
        cn = len(shell)
        mean_d = sum(n.nn_distance for n in shell) / cn
        anion = shell[0].specie.symbol
        shell_atoms = [i] + [n.index for n in shell]

        rc = shannon_radius(symbol, oxi, cn)
        ra = shannon_radius(anion, model.oxidation_states[anion], 6)
        if rc and ra:
            expected = rc[0] + ra[0]
            dev = (expected - mean_d) / mean_d
            status = _graded(dev, BOND_MISMATCH_WARN, BOND_MISMATCH_FAIL)
            if status != "pass":
                size = "too large" if dev > 0 else "too small"
                fit_msgs.append(
                    f"{symbol}{i}: ion is {size} for this site "
                    f"(expected {expected:.2f} Å, site gives {mean_d:.2f} Å, {dev:+.0%})."
                )
                fit_atoms += shell_atoms
            fit_status = worse(fit_status, status)
            if rc[1] != cn:
                cn_status = worse(cn_status, "warn")
                cn_msgs.append(
                    f"{symbol}{oxi:+g} has no tabulated radius at CN {cn} "
                    f"(nearest tabulated CN {rc[1]}): uncommon coordination."
                )
                cn_atoms += shell_atoms

        bvs = bond_valence_sum(symbol, shell)
        if bvs is None or bvs <= 0 or oxi <= 0:
            continue
        # Bond-length change that would bring the BVS to the oxidation state.
        delta_d = BV_B * math.log(bvs / oxi)
        dev = delta_d / mean_d
        status = _graded(dev, BVS_WARN, BVS_FAIL)
        if status != "pass":
            kind = "overbonded: site too small" if dev > 0 else "underbonded: site too large"
            bvs_msgs.append(
                f"{symbol}{i}: BVS {bvs:.2f} vs {oxi:+g} ({kind}; bonds would need to change "
                f"by {delta_d:+.2f} Å, {dev:+.0%})."
            )
            bvs_atoms += shell_atoms
        bvs_status = worse(bvs_status, status)

    ok = "All checked sites are within the heuristic limits."
    return (
        CheckResult(
            id="bond_fit",
            name="Ionic size fit",
            status=fit_status,
            message=" ".join(fit_msgs) or ok,
            atom_indices=sorted(set(fit_atoms)),
            method=f"{RADII_METHOD}; warn >{BOND_MISMATCH_WARN:.0%}, fail >{BOND_MISMATCH_FAIL:.0%}",
        ),
        CheckResult(
            id="coordination",
            name="Coordination environment",
            status=cn_status,
            message=" ".join(cn_msgs) or "Each ion is tabulated at its coordination number.",
            atom_indices=sorted(set(cn_atoms)),
            method=f"First anion shell within {1 + 0.2:.1f} x shortest distance; {RADII_METHOD}",
        ),
        CheckResult(
            id="bond_valence",
            name="Bond valence sum",
            status=bvs_status,
            message=" ".join(bvs_msgs) or ok,
            atom_indices=sorted(set(bvs_atoms)),
            method=f"{BVS_METHOD}; implied bond change warn >{BVS_WARN:.0%}, fail >{BVS_FAIL:.0%}",
        ),
    )


def check_tolerance_factor(structure: Structure, model: IonicModel) -> CheckResult:
    """Goldschmidt tolerance factor, only for ABX3 perovskite-like structures."""
    a_sites, b_sites = [], []
    for i in _cation_sites(structure, model, None):
        cn = len(anion_shell(structure, i, model))
        (a_sites if cn >= 8 else b_sites if cn == 6 else []).append(i)
    n_anion = sum(1 for s in structure if model.is_anion(s.specie.symbol))
    is_perovskite = (
        a_sites
        and b_sites
        and len(a_sites) == len(b_sites)
        and n_anion == 3 * len(a_sites)
        and len(a_sites) + len(b_sites) + n_anion == len(structure)
    )
    if not is_perovskite:
        return CheckResult(
            id="tolerance_factor",
            name="Goldschmidt tolerance factor",
            status="not_applicable",
            message="Applies only to ABX3 perovskite-like structures.",
        )

    def mean_radius(sites: list[int], cn: int) -> float | None:
        radii = []
        for i in sites:
            symbol = structure[i].specie.symbol
            r = shannon_radius(symbol, model.oxidation_states[symbol], cn)
            if r is None:
                return None
            radii.append(r[0])
        return sum(radii) / len(radii)

    anion = next(s.specie.symbol for s in structure if model.is_anion(s.specie.symbol))
    ra, rb = mean_radius(a_sites, 12), mean_radius(b_sites, 6)
    rx = shannon_radius(anion, model.oxidation_states[anion], 6)
    if ra is None or rb is None or rx is None:
        return CheckResult(
            id="tolerance_factor",
            name="Goldschmidt tolerance factor",
            status="info",
            message="Missing tabulated radii; cannot compute.",
        )
    t = (ra + rx[0]) / (math.sqrt(2) * (rb + rx[0]))
    if TOLERANCE_PASS[0] <= t <= TOLERANCE_PASS[1]:
        status = "pass"
    elif TOLERANCE_WARN[0] <= t <= TOLERANCE_WARN[1]:
        status = "warn"
    else:
        status = "fail"
    return CheckResult(
        id="tolerance_factor",
        name="Goldschmidt tolerance factor",
        status=status,
        message=f"t = {t:.3f} (perovskites usually form for about {TOLERANCE_PASS[0]}–{TOLERANCE_PASS[1]}).",
        atom_indices=[] if status == "pass" else a_sites + b_sites,
        values={"t": round(t, 3), "r_A": round(ra, 3), "r_B": round(rb, 3), "r_X": rx[0]},
        method=f"t = (r_A + r_X) / (sqrt(2) (r_B + r_X)); {RADII_METHOD}, A at CN 12, B at CN 6",
    )


def check_analogs(formulas: list[str], lookup: AnalogLookup | None) -> CheckResult:
    if lookup is None or not formulas:
        return CheckResult(
            id="analogs",
            name="Reference analogs",
            status="not_applicable",
            message="No materials database available for analog search.",
        )
    found = {f: lookup(f) for f in formulas}
    known = {f: ids for f, ids in found.items() if ids}
    text = "; ".join(f"{f}: {', '.join(ids[:3])}" for f, ids in known.items())
    missing = [f for f in formulas if f not in known]
    message = f"Known end-member compounds: {text}." if known else ""
    if missing:
        message += f" No database entry for {', '.join(missing)}."
    return CheckResult(
        id="analogs",
        name="Reference analogs",
        status="pass" if known else "info",
        message=message.strip(),
        method="Materials Project formula search (end members of each substitution)",
    )


def assess(
    structure: Structure,
    focus_sites: list[int] | None = None,
    analog_formulas: list[str] | None = None,
    analog_lookup: AnalogLookup | None = None,
    note: str = NO_RELAXATION_NOTE,
) -> StructuralAssessment:
    """Run all checks. focus_sites: substituted sites (None = check every cation site)."""
    model = ionic_model(structure)
    if model is None:
        return StructuralAssessment(
            status="Insufficient Evidence",
            checks=[
                CheckResult(
                    id="ionic_model",
                    name="Ionic model",
                    status="not_applicable",
                    message="No anion: the checks need an ionic material (oxide, nitride, fluoride).",
                )
            ],
            notes=[note],
        )

    sites = _cation_sites(structure, model, focus_sites)
    fit, coordination, bvs = check_sites(structure, model, sites)
    checks = [
        check_charge(structure, model, sites),
        check_distances(structure, model),
        fit,
        coordination,
        bvs,
        check_tolerance_factor(structure, model),
        check_analogs(analog_formulas or [], analog_lookup),
    ]
    if any(c.status in ("warn", "fail") for c in checks):
        status = "Structural Concerns"
    else:
        status = "Structurally Plausible"
    return StructuralAssessment(
        status=status,
        checks=checks,
        oxidation_states=model.oxidation_states,
        notes=[note],
    )
