"""Controlled element substitution on a known host structure (spec 3.3).

No generative model: the host lattice and atom positions are kept, and a fraction of one
element's sites is replaced. Partial fractions use the smallest supercell that makes the
number of replaced sites an integer.
"""

from collections import defaultdict

from pymatgen.core import Element, Structure

from app.models.candidates import Substitution
from app.tools.registry import ToolError

# Number of host cells -> supercell scaling along a, b, c.
SUPERCELLS: dict[int, tuple[int, int, int]] = {
    1: (1, 1, 1),
    2: (2, 1, 1),
    3: (3, 1, 1),
    4: (2, 2, 1),
    6: (3, 2, 1),
    8: (2, 2, 2),
}
MAX_CANDIDATE_SITES = 200
SITE_SELECTION = (
    "farthest-point: replaced sites are spread as far apart as possible "
    "(deterministic; one of many possible orderings, not energy-ranked)"
)


def _check_input(host: Structure, subs: list[Substitution]) -> None:
    if not host.is_ordered:
        raise ToolError("The host has partial occupancies. Use an ordered structure.")
    if not subs:
        raise ToolError("Give at least one substitution.")
    present = {site.specie.symbol for site in host}
    totals: dict[str, float] = defaultdict(float)
    for sub in subs:
        if sub.element_from not in present:
            raise ToolError(
                f"{sub.element_from} is not in the host ({', '.join(sorted(present))})."
            )
        if not Element.is_valid_symbol(sub.element_to):
            raise ToolError(f"{sub.element_to!r} is not an element symbol.")
        if sub.element_to == sub.element_from:
            raise ToolError(f"Substituting {sub.element_from} with itself does nothing.")
        totals[sub.element_from] += sub.fraction
    for element, total in totals.items():
        if total > 1 + 1e-9:
            raise ToolError(f"Fractions for {element} add up to {total:.2f}, more than 1.")


def _cells_needed(host: Structure, subs: list[Substitution]) -> int:
    counts = host.composition.as_dict()
    for cells in SUPERCELLS:
        replaced = [counts[s.element_from] * cells * s.fraction for s in subs]
        if all(abs(r - round(r)) < 1e-6 and round(r) >= 1 for r in replaced):
            if len(host) * cells > MAX_CANDIDATE_SITES:
                break
            return cells
    raise ToolError(
        "These fractions need a supercell that is too large. "
        "Use fractions such as 1, 1/2, 1/3, 1/4, 1/6, or 1/8 of the sites."
    )


def _farthest_point(structure: Structure, candidates: list[int], k: int) -> list[int]:
    chosen = [candidates[0]]
    while len(chosen) < k:
        remaining = [i for i in candidates if i not in chosen]
        best = max(
            remaining,
            key=lambda i: (min(structure.get_distance(i, j) for j in chosen), -i),
        )
        chosen.append(best)
    return sorted(chosen)


def substitute(
    host: Structure, subs: list[Substitution]
) -> tuple[Structure, tuple[int, int, int], dict[str, list[int]]]:
    """Return the candidate structure, the supercell scaling, and the replaced site indices."""
    _check_input(host, subs)
    scaling = SUPERCELLS[_cells_needed(host, subs)]
    candidate = host.copy()
    candidate.make_supercell(scaling)

    replaced: dict[str, list[int]] = defaultdict(list)
    taken: set[int] = set()
    for sub in subs:
        sites = [
            i
            for i, site in enumerate(candidate)
            if site.specie.symbol == sub.element_from and i not in taken
        ]
        original_count = host.composition[sub.element_from] * len(candidate) / len(host)
        k = round(original_count * sub.fraction)
        for i in _farthest_point(candidate, sites, k):
            candidate.replace(i, sub.element_to)
            replaced[sub.element_to].append(i)
            taken.add(i)
    return candidate, scaling, {el: sorted(idx) for el, idx in replaced.items()}
