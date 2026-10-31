import numpy as np
import pytest
from fastapi.testclient import TestClient
from pymatgen.core import Lattice, Structure
from pymatgen.io.cif import CifWriter

from app.main import app
from app.tools.cloud import SIZE_FROM_RADIUS, cloud_model


def covariance(site) -> np.ndarray:
    xx, yy, zz, xy, xz, yz = site.covariance
    return np.array([[xx, xy, xz], [xy, yy, yz], [xz, yz, zz]])


def test_a_site_on_a_cubic_site_has_a_round_cloud(srtio3):
    model = cloud_model(srtio3)
    titanium = next(s for s in model.sites if s.element == "Ti")

    assert model.kind == "ionic"
    assert titanium.stretch == pytest.approx(0, abs=1e-3)
    values = np.linalg.eigvalsh(covariance(titanium))
    assert values[-1] == pytest.approx(values[0], abs=1e-3)


def test_oxygen_stretches_along_its_short_titanium_bonds(srtio3):
    model = cloud_model(srtio3)
    oxygens = [s for s in model.sites if s.element == "O"]
    lattice = np.array(model.lattice)
    assert len(oxygens) == 3
    assert [o.stretch for o in oxygens] == pytest.approx([oxygens[0].stretch] * 3)

    for oxygen in oxygens:
        assert oxygen.stretch > 0.3
        titanium = next(s for s in model.sites if s.element == "Ti")
        # The nearest Ti, through the periodic boundary if needed.
        delta = np.array(titanium.frac) - np.array(oxygen.frac)
        delta -= np.round(delta)
        bond = delta @ lattice
        along = abs(np.dot(bond / np.linalg.norm(bond), oxygen.direction))
        assert along == pytest.approx(1, abs=1e-3)


def test_anions_have_larger_clouds_than_small_cations(srtio3):
    sites = {s.element: s for s in cloud_model(srtio3).sites}
    assert sites["O"].radius > sites["Ti"].radius
    trace = np.trace(covariance(sites["Ti"]))
    assert trace == pytest.approx(3 * (SIZE_FROM_RADIUS * sites["Ti"].radius) ** 2, abs=1e-3)


def test_the_cloud_order_matches_the_site_order(srtio3):
    model = cloud_model(srtio3)
    assert [s.index for s in model.sites] == list(range(len(srtio3)))
    assert [s.element for s in model.sites] == [s.specie.symbol for s in srtio3]


def test_a_material_with_no_anion_has_round_clouds():
    copper = Structure.from_spacegroup("Fm-3m", Lattice.cubic(3.61), ["Cu"], [[0, 0, 0]])
    model = cloud_model(copper)

    assert model.kind == "neutral"
    assert all(s.stretch == 0 for s in model.sites)


def test_cloud_api(srtio3):
    client = TestClient(app)
    response = client.post("/api/structures/cloud", json={"cif": str(CifWriter(srtio3))})

    assert response.status_code == 200
    assert len(response.json()["sites"]) == 5
    assert client.post("/api/structures/cloud", json={"cif": "not a cif"}).status_code >= 400
