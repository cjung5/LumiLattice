import pytest
from fastapi.testclient import TestClient
from pymatgen.core import Lattice, Structure
from pymatgen.io.cif import CifWriter

from app.main import app
from app.models.candidates import Substitution
from app.models.evidence import Provenance
from app.storage.memory import get_store
from app.tools.candidates import create_candidate
from app.tools.spatial import analyze


@pytest.fixture
def rutile() -> Structure:
    return Structure.from_spacegroup(
        "P4_2/mnm", Lattice.tetragonal(4.594, 2.959), ["Ti", "O"], [[0, 0, 0], [0.3053, 0.3053, 0]]
    )


def test_perovskite_host_is_isotropic_with_straight_links(srtio3):
    result = analyze(srtio3)

    assert result.symmetry.optical_class == "isotropic"
    ti = next(p for p in result.polyhedra if p.element == "Ti")
    assert ti.shape == "octahedron" and ti.shape_score == pytest.approx(1.0)
    assert ti.distortion_index == pytest.approx(0) and ti.bond_angle_variance == pytest.approx(0)
    assert result.linkages.edge == 0 and result.linkages.corner > 0
    assert set(result.linkages.bxb_angles) == {180.0}
    assert result.linkages.mean_tilt == pytest.approx(0)


def test_rutile_is_uniaxial_with_edge_and_corner_sharing(rutile):
    result = analyze(rutile)

    assert result.symmetry.optical_class == "uniaxial"  # rutile is birefringent
    assert result.linkages.edge > 0 and result.linkages.corner > 0
    assert result.linkages.mean_tilt is None  # not a perovskite-type corner-only framework
    assert min(result.linkages.bxb_angles) == pytest.approx(130.5, abs=0.5)  # corner-shared Ti-O-Ti
    ti = result.polyhedra[0]
    assert ti.shape == "octahedron" and ti.distortion_index > 0


def test_candidate_spatial_endpoint(srtio3):
    candidate = create_candidate(
        get_store(),
        srtio3,
        Provenance(source="test"),
        [
            Substitution(element_from="Sr", element_to="La", fraction=0.5),
            Substitution(element_from="Ti", element_to="Al", fraction=0.5),
        ],
    )
    body = TestClient(app).get(f"/api/candidates/{candidate.candidate_id}/spatial").json()

    assert body["parent_symmetry"]["optical_class"] == "isotropic"
    assert body["symmetry"]["optical_class"] != "isotropic"  # ordered layers lower the symmetry
    assert any("Symmetry" in f for f in body["findings"])
    ordering = body["ordering"]
    assert ordering["distinct"] >= 2  # a repeated cell holds competing arrangements
    assert ordering["chosen_rank"] >= 1 and len(ordering["energies"]) == ordering["total"]
    assert {d["element"] for d in body["dopants"]} == {"La", "Al"}


def test_host_spatial_endpoint(srtio3):
    body = (
        TestClient(app).post("/api/structures/spatial", json={"cif": str(CifWriter(srtio3))}).json()
    )
    assert body["symmetry"]["spacegroup"] == "Pm-3m"


def test_relaxed_geometry_is_compared_with_the_candidate(srtio3):
    candidate = create_candidate(
        get_store(),
        srtio3,
        Provenance(source="test"),
        [Substitution(element_from="Ti", element_to="Zr", fraction=0.5)],
    )
    _, structure = get_store().get(candidate.candidate_id)
    replaced = candidate.transformation.substituted_sites
    focus = sorted(i for sites in replaced.values() for i in sites)

    result = analyze(structure.copy(), focus, structure, replaced, rank=False)

    assert result.parent_symmetry == result.symmetry
    assert any(f.startswith("Symmetry kept") for f in result.findings)
    assert result.ordering is None and result.dopants == []  # the arrangement does not change
