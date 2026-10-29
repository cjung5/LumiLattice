"""Ionic model helpers: oxidation-state assignment, anions, coordination, Shannon radii."""

import math
from dataclasses import dataclass

from pymatgen.core import Element, PeriodicNeighbor, Structure
from pymatgen.core.bond_valence import BV_PARAMS

ROMAN = {
    "I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7,
    "VIII": 8, "IX": 9, "X": 10, "XI": 11, "XII": 12, "XIV": 14,
}  # fmt: skip
NEIGHBOR_RADIUS = 4.0  # Å; first cation-anion shell in oxides is well inside this
SHELL_TOLERANCE = 0.2  # neighbors within (1 + tol) x shortest cation-anion distance
# Bond valence: s = exp((R0 - d) / b). O'Keeffe & Brese (1991) fitted their universal
# element parameters with b = 0.37 Å (pymatgen's calculate_bv_sum uses 0.31).
BV_B = 0.37


@dataclass(frozen=True)
class IonicModel:
    oxidation_states: dict[str, float]  # average per element
    anions: frozenset[str]
    assumed: bool  # True when no charge-balanced assignment exists

    def is_anion(self, symbol: str) -> bool:
        return symbol in self.anions


def ionic_model(structure: Structure) -> IonicModel | None:
    """Assign average oxidation states, or return None for materials with no anion."""
    comp = structure.composition.reduced_composition
    guesses = comp.oxi_state_guesses()
    if guesses:
        states = {el: float(v) for el, v in guesses[0].items()}
        assumed = False
    else:
        # Fall back to each element's most common oxidation state; the charge check reports it.
        states = {}
        for el in comp.elements:
            common = Element(el.symbol).common_oxidation_states
            states[el.symbol] = float(common[0]) if common else 0.0
        assumed = True
    anions = frozenset(el for el, v in states.items() if v < 0)
    if not anions:
        return None
    return IonicModel(states, anions, assumed)


def anion_shell(structure: Structure, index: int, model: IonicModel) -> list[PeriodicNeighbor]:
    """First coordination shell of a cation: anions within (1 + tol) x the shortest distance."""
    neighbors = [
        n
        for n in structure.get_neighbors(structure[index], NEIGHBOR_RADIUS)
        if model.is_anion(n.specie.symbol)
    ]
    if not neighbors:
        return []
    shortest = min(n.nn_distance for n in neighbors)
    return [n for n in neighbors if n.nn_distance <= shortest * (1 + SHELL_TOLERANCE)]


def universal_r0(cation: Element, anion: Element) -> float:
    """Bond valence R0 from O'Keeffe & Brese (1991) universal element parameters."""
    r1, c1 = BV_PARAMS[cation]["r"], BV_PARAMS[cation]["c"]
    r2, c2 = BV_PARAMS[anion]["r"], BV_PARAMS[anion]["c"]
    return r1 + r2 - r1 * r2 * (math.sqrt(c1) - math.sqrt(c2)) ** 2 / (c1 * r1 + c2 * r2)


def bond_valence_sum(symbol: str, shell: list[PeriodicNeighbor]) -> float | None:
    cation = Element(symbol)
    if cation not in BV_PARAMS:
        return None
    total = 0.0
    for n in shell:
        anion = Element(n.specie.symbol)
        if anion not in BV_PARAMS:
            return None
        total += math.exp((universal_r0(cation, anion) - n.nn_distance) / BV_B)
    return total


def shannon_radius(symbol: str, oxidation: float, cn: int) -> tuple[float, int] | None:
    """Shannon (1976) ionic radius in Å, and the CN actually used (nearest tabulated CN)."""
    by_oxi = Element(symbol).data.get("Shannon radii", {}).get(str(round(oxidation)))
    if not by_oxi:
        return None
    available = {ROMAN[key]: key for key in by_oxi if key in ROMAN}
    if not available:
        return None
    used = cn if cn in available else min(available, key=lambda c: (abs(c - cn), -c))
    by_spin = by_oxi[available[used]]
    spin = "" if "" in by_spin else ("High Spin" if "High Spin" in by_spin else next(iter(by_spin)))
    return float(by_spin[spin]["ionic_radius"]), used
