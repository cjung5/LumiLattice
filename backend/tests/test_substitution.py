import pytest

from app.models.candidates import Substitution
from app.tools.registry import ToolError
from app.tools.substitution import _farthest_point, substitute


def sub(a: str, b: str, f: float) -> Substitution:
    return Substitution(element_from=a, element_to=b, fraction=f)


def test_full_substitution_keeps_the_cell(srtio3):
    candidate, scaling, replaced = substitute(srtio3, [sub("Sr", "Ba", 1)])

    assert scaling == (1, 1, 1)
    assert candidate.composition.reduced_formula == "BaTiO3"
    assert replaced == {"Ba": [0]}
    assert candidate.lattice.abc == srtio3.lattice.abc  # no relaxation


@pytest.mark.parametrize(("fraction", "cells"), [(0.5, 2), (0.25, 4), (1 / 3, 3), (0.125, 8)])
def test_partial_substitution_uses_smallest_supercell(srtio3, fraction, cells):
    candidate, _, replaced = substitute(srtio3, [sub("Ti", "Zr", fraction)])

    assert len(candidate) == 5 * cells
    assert len(replaced["Zr"]) == round(cells * fraction)


def test_farthest_point_spreads_replaced_sites(srtio3):
    supercell = srtio3.copy()
    supercell.make_supercell((2, 2, 1))
    ti_sites = [i for i, site in enumerate(supercell) if site.specie.symbol == "Ti"]

    i, j = _farthest_point(supercell, ti_sites, 2)

    # In a 2x2x1 cell the farthest Ti pair is across the ab face diagonal: a * sqrt(2).
    assert supercell.get_distance(i, j) == pytest.approx(3.905 * 2**0.5, rel=1e-3)


def test_co_substitution(srtio3):
    candidate, scaling, replaced = substitute(srtio3, [sub("Sr", "La", 0.5), sub("Ti", "Ga", 0.5)])

    assert scaling == (2, 1, 1)
    assert candidate.composition.reduced_formula == "SrLaTiGaO6"
    assert set(replaced) == {"La", "Ga"}


@pytest.mark.parametrize(
    "subs",
    [
        [sub("Ba", "Sr", 1)],  # not in host
        [sub("Ti", "Xx", 1)],  # not an element
        [sub("Ti", "Ti", 1)],  # no change
        [sub("Ti", "Zr", 0.6), sub("Ti", "Hf", 0.6)],  # more than 100 %
        [sub("Ti", "Zr", 0.37)],  # needs a huge supercell
    ],
)
def test_rejects_bad_input(srtio3, subs):
    with pytest.raises(ToolError):
        substitute(srtio3, subs)
