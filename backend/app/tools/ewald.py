"""Point-charge (Ewald) energies of dopant arrangements on one parent cell.

E = q^T M q / N, where M is the Ewald energy matrix of unit charges on the parent's sites, so
one Ewald sum serves every arrangement. Charges are formal (average) oxidation states and
there is no screening or relaxation: use the energies to rank arrangements, nothing more.
"""

import itertools
import math
import random
from collections.abc import Iterator, Sequence

import numpy as np
from pymatgen.analysis.ewald import EwaldSummation
from pymatgen.core import Structure

# (element replaced, new element, number of sites)
Group = tuple[str, str, int]
Choice = list[list[int]]  # site indices per group

EXACT_LIMIT = 50_000  # enumerate every arrangement up to this many
SEARCH_SAMPLE = 2_000  # otherwise: seeded random sample, then greedy swaps
_BATCH = 4_096


class Arrangements:
    def __init__(self, parent: Structure, groups: list[Group], charges: dict[str, float]):
        self.groups = groups
        self.charges = charges
        self.size = len(parent)
        self.pools = [
            [i for i, s in enumerate(parent) if s.specie.symbol == old] for old, _, _ in groups
        ]
        self.total = math.prod(
            math.comb(len(pool), k) for pool, (_, _, k) in zip(self.pools, groups, strict=True)
        )
        unit = parent.copy()
        unit.add_oxidation_state_by_site([1.0] * len(unit))
        self.matrix = EwaldSummation(unit).total_energy_matrix
        self.base = np.array([charges.get(s.specie.symbol, 0.0) for s in parent])

    def energies(self, choices: Sequence[Choice]) -> np.ndarray:
        """eV/atom for each choice; inf where two substitutions take the same site."""
        out = np.empty(len(choices))
        for start in range(0, len(choices), _BATCH):
            chunk = choices[start : start + _BATCH]
            q = np.tile(self.base, (len(chunk), 1))
            clash = np.zeros(len(chunk), dtype=bool)
            for row, choice in enumerate(chunk):
                used: set[int] = set()
                for (_, new, _), sites in zip(self.groups, choice, strict=True):
                    clash[row] |= bool(used & set(sites))
                    used |= set(sites)
                    q[row, sites] = self.charges[new]
            energy = np.einsum("ij,ij->i", q @ self.matrix, q) / self.size
            energy[clash] = math.inf
            out[start : start + len(chunk)] = energy
        return out

    def energy(self, choice: Choice) -> float:
        return float(self.energies([choice])[0])

    def every(self) -> Iterator[Choice]:
        yield from (
            list(map(list, c))
            for c in itertools.product(
                *(
                    itertools.combinations(pool, k)
                    for pool, (_, _, k) in zip(self.pools, self.groups, strict=True)
                )
            )
        )

    def sample(self, n: int, seed: int = 0) -> list[Choice]:
        """An even, reproducible random sample (not the first n in enumeration order)."""
        rng = random.Random(seed)
        return [
            [
                sorted(rng.sample(pool, k))
                for pool, (_, _, k) in zip(self.pools, self.groups, strict=True)
            ]
            for _ in range(n)
        ]

    def _descend(self, choice: Choice) -> tuple[Choice, float]:
        """Greedy: move one dopant to a free site of its pool while that lowers the energy."""
        current, best = choice, self.energy(choice)
        while True:
            occupied = {i for sites in current for i in sites}
            moves = [
                [
                    sorted([*(x for x in sites if x != a), b]) if g == h else list(other)
                    for h, other in enumerate(current)
                ]
                for g, sites in enumerate(current)
                for a in sites
                for b in self.pools[g]
                if b not in occupied
            ]
            if not moves:
                return current, best
            energies = self.energies(moves)
            i = int(np.argmin(energies))
            if energies[i] >= best - 1e-12:
                return current, best
            current, best = moves[i], float(energies[i])

    def lowest(self) -> tuple[Choice, float, bool]:
        """The lowest-energy arrangement, its energy, and whether the search was exhaustive.

        Exhaustive up to EXACT_LIMIT arrangements (ties: the first in enumeration order).
        Larger spaces: the best of a seeded random sample, improved by greedy swaps.
        """
        if self.total <= EXACT_LIMIT:
            choices = list(self.every())
            energies = self.energies(choices)
            i = int(np.argmin(energies))
            return choices[i], float(energies[i]), True
        choices = self.sample(SEARCH_SAMPLE)
        energies = self.energies(choices)
        starts = [choices[i] for i in np.argsort(energies)[:5]]
        found = min((self._descend(s) for s in starts), key=lambda r: r[1])
        return found[0], found[1], False
