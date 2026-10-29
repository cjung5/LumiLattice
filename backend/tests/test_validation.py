from pymatgen.core import Lattice, Structure

from app.models.candidates import Substitution
from app.tools.substitution import substitute
from app.tools.validation import assess


def checks(assessment) -> dict[str, str]:
    return {c.id: c.status for c in assessment.checks}


def candidate(host, *subs):
    structure, _, replaced = substitute(
        host, [Substitution(element_from=a, element_to=b, fraction=f) for a, b, f in subs]
    )
    return structure, sorted(i for sites in replaced.values() for i in sites)


def test_host_srtio3_is_plausible(srtio3):
    result = assess(srtio3)

    assert result.status == "Structurally Plausible"
    assert checks(result)["tolerance_factor"] == "pass"
    tf = next(c for c in result.checks if c.id == "tolerance_factor")
    assert abs(tf.values["t"] - 1.0) < 0.01


def test_host_rutile_is_plausible_and_not_a_perovskite():
    rutile = Structure.from_spacegroup(
        "P4_2/mnm", Lattice.tetragonal(4.594, 2.959), ["Ti", "O"], [[0, 0, 0], [0.3053, 0.3053, 0]]
    )
    result = assess(rutile)

    assert result.status == "Structurally Plausible"
    assert checks(result)["tolerance_factor"] == "not_applicable"


def test_aliovalent_substitution_needs_mixed_valence(srtio3):
    structure, focus = candidate(srtio3, ("Sr", "La", 0.5))
    result = assess(structure, focus)

    assert result.status == "Structural Concerns"
    charge = next(c for c in result.checks if c.id == "charge")
    assert charge.status == "warn"
    assert "Ti" in charge.message
    assert charge.atom_indices  # mapped to the Ti sites in the viewer


def test_charge_compensated_co_substitution_is_plausible(srtio3):
    structure, focus = candidate(srtio3, ("Sr", "La", 0.5), ("Ti", "Ga", 0.5))

    assert assess(structure, focus).status == "Structurally Plausible"


def test_oversized_ion_fails_and_points_at_its_site(srtio3):
    structure, focus = candidate(srtio3, ("Ti", "K", 0.25))
    result = assess(structure, focus)
    status = checks(result)

    assert status["charge"] == "fail"
    assert status["bond_fit"] == "fail"
    assert status["bond_valence"] == "fail"
    fit = next(c for c in result.checks if c.id == "bond_fit")
    assert focus[0] in fit.atom_indices


def test_unrelaxed_larger_ion_is_flagged_as_overbonded(srtio3):
    structure, focus = candidate(srtio3, ("Ti", "Zr", 0.5))
    bvs = next(c for c in assess(structure, focus).checks if c.id == "bond_valence")

    assert bvs.status == "warn"
    assert "overbonded" in bvs.message


def test_metal_without_anion_is_insufficient_evidence():
    copper = Structure(
        Lattice.cubic(3.61), ["Cu"] * 4, [[0, 0, 0], [0.5, 0.5, 0], [0.5, 0, 0.5], [0, 0.5, 0.5]]
    )

    assert assess(copper).status == "Insufficient Evidence"


def test_analog_lookup_is_used(srtio3):
    structure, focus = candidate(srtio3, ("Ti", "Zr", 0.5))
    result = assess(structure, focus, ["SrZrO3"], lambda f: ["mp-4387"] if f == "SrZrO3" else [])

    analogs = next(c for c in result.checks if c.id == "analogs")
    assert analogs.status == "pass"
    assert "mp-4387" in analogs.message
