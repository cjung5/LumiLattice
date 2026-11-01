"""End members follow the whole line of substitutions, including swaps of atoms put in earlier."""

import pytest

from app.models.candidates import Substitution
from app.models.evidence import Provenance
from app.storage.memory import MemoryStore
from app.tools.candidates import create_candidate, end_member_formulas, solid_solution_ends
from app.tools.goals import Goal, score_candidate
from app.tools.reference_db import (
    MAX_CREDIBLE_MOSS_RATIO,
    MAX_CREDIBLE_N,
    MOSS_CONSTANT_EV,
    NOT_CREDIBLE,
    get_reference_db,
)

GOAL = Goal(target_n=2.2, min_band_gap=3.0)


def line(*steps: tuple[str, str, float]) -> list[Substitution]:
    return [Substitution(element_from=a, element_to=b, fraction=f) for a, b, f in steps]


@pytest.mark.parametrize(
    "steps,ends",
    [
        # One step or several from the host: as before.
        ([("Sr", "La", 0.25)], ["SrTiO3", "LaTiO3"]),
        ([("Sr", "La", 0.25), ("Ti", "Al", 0.25)], ["SrTiO3", "LaAlO3"]),
        ([("Ti", "Zr", 0.5), ("Ti", "Hf", 0.5)], ["SrTiO3", "SrZrO3", "SrHfO3"]),
        ([("Sr", "La", 1), ("Ti", "Al", 1)], ["SrTiO3", "LaAlO3"]),
        # A later step removes all of an element: it is no longer an end member.
        ([("Sr", "La", 0.25), ("Ti", "Al", 0.25), ("Al", "Ti", 1)], ["SrTiO3", "LaTiO3"]),
        # A later step removes part of it: it stays.
        ([("Sr", "La", 0.25), ("Ti", "Al", 0.25), ("Al", "Ti", 0.5)], ["SrTiO3", "LaAlO3"]),
        # A later step replaces the new element with another one.
        ([("Sr", "La", 0.25), ("La", "Ce", 1)], ["SrTiO3", "CeTiO3"]),
        ([("Sr", "La", 0.5), ("La", "Ba", 0.5)], ["SrTiO3", "LaTiO3", "BaTiO3"]),
        # No Ti is left, so SrTiO3 is not an end member.
        ([("Ti", "Zr", 1), ("Zr", "Hf", 0.5)], ["SrZrO3", "SrHfO3"]),
        # Everything goes back: only the host remains.
        ([("Sr", "La", 1), ("La", "Sr", 1)], ["SrTiO3"]),
    ],
)
def test_solid_solution_ends(steps, ends):
    assert solid_solution_ends("SrTiO3", line(*steps)) == ends


def test_analogs_of_a_chain_leave_out_removed_elements():
    steps = line(("Sr", "La", 0.25), ("Ti", "Al", 0.25), ("Al", "Ti", 1))
    assert end_member_formulas("SrTiO3", steps) == ["LaTiO3"]


def test_two_varied_site_families_after_a_chain():
    steps = line(("Sr", "La", 0.5), ("La", "Ba", 0.5), ("Ti", "Zr", 0.5))
    assert solid_solution_ends("SrTiO3", steps) == ["SrTiO3", "LaZrO3", "BaZrO3"]


def test_a_revision_that_removes_aluminium_has_no_aluminium_end_member(srtio3):
    store = MemoryStore()
    source = Provenance(source="test")
    first = create_candidate(store, srtio3, source, line(("Sr", "La", 0.25), ("Ti", "Al", 0.25)))
    assert [m.formula for m in first.optical_estimate.end_members] == ["SrTiO3", "LaAlO3"]
    revised = create_candidate(
        store, store.get(first.candidate_id)[1], source, line(("Al", "Ti", 1)), first.candidate_id
    )
    assert "Al" not in revised.formula
    assert [m.formula for m in revised.optical_estimate.end_members] == ["SrTiO3", "LaTiO3"]
    assert "LaAlO3" not in (revised.optical_estimate.estimate.conditions or "")


def test_a_revision_is_a_linear_mix_of_its_new_end_members(srtio3):
    if not get_reference_db().available:
        pytest.skip("reference.sqlite is not built")
    store = MemoryStore()
    source = Provenance(source="test")
    first = create_candidate(store, srtio3, source, line(("Sr", "La", 0.25), ("Ti", "Al", 0.25)))
    revised = create_candidate(
        store, store.get(first.candidate_id)[1], source, line(("Al", "Ti", 1)), first.candidate_id
    )
    mix = revised.optical_estimate.linear_mix
    if mix is not None:
        assert mix.shares == {"SrTiO3": 0.75, "LaTiO3": 0.25}


def needs_reference_data():
    if not get_reference_db().available:
        pytest.skip("reference.sqlite is not built")


def test_a_metallic_calculation_is_left_out_of_a_range(srtio3):
    """LaTiO3's computed n is 7.48 with a 3.5 eV gap: it must not make a candidate "meet" a goal."""
    needs_reference_data()
    db = get_reference_db()
    assert db.best_n("LaTiO3").value > MAX_CREDIBLE_N  # still listed as reference data
    n, gap = db.usable_optics("LaTiO3")
    assert (n.status, gap.status) == ("Unknown", "Unknown")
    assert n.conditions == NOT_CREDIBLE

    store = MemoryStore()
    made = create_candidate(store, srtio3, Provenance(source="t"), line(("Sr", "La", 0.25)))
    assert made.optical_estimate.estimate.status == "Unknown"
    verdicts = {c.id: c.verdict for c in score_candidate(made, GOAL).criteria}
    assert verdicts["n"] == "unknown"
    assert verdicts["band_gap"] == "unknown"


def test_a_measured_gap_stays_when_only_the_computed_n_is_left_out():
    needs_reference_data()
    n, gap = get_reference_db().usable_optics("MnO")
    assert n.status == "Unknown"
    assert gap.status == "Experimental"


@pytest.mark.parametrize("formula", ["SrTiO3", "LaAlO3", "TiO2", "BaTiO3", "ZrO2", "SiO2", "MoS2"])
def test_credible_values_are_not_changed(formula):
    needs_reference_data()
    db = get_reference_db()
    assert db.usable_optics(formula) == (db.best_n(formula), db.best_gap(formula))


def test_measured_materials_are_inside_the_limits():
    """The limits are for computed values, and they must not be tighter than real materials."""
    needs_reference_data()
    db = get_reference_db()
    for point in db.landscape().measured:
        assert point.n <= MAX_CREDIBLE_N
        if point.band_gap:
            assert point.n**4 * point.band_gap / MOSS_CONSTANT_EV <= MAX_CREDIBLE_MOSS_RATIO, point
