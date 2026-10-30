import pytest
from fastapi.testclient import TestClient

from app.api import candidates as candidates_api
from app.main import app
from app.models.candidates import Substitution
from app.models.evidence import Provenance
from app.storage.memory import get_store
from app.tools.candidates import create_candidate
from app.tools.relaxation import RelaxOutcome, displacement_summary, relaxation_available


def seed(srtio3):
    return create_candidate(
        get_store(),
        srtio3,
        Provenance(source="test"),
        [Substitution(element_from="Sr", element_to="Ba", fraction=0.5)],
    )


def test_displacement_summary(srtio3):
    after = srtio3.copy()
    after.scale_lattice(srtio3.volume * 1.03)

    summary = displacement_summary(srtio3, after)

    assert summary["volume_change"] == pytest.approx(0.03, abs=1e-4)
    assert all(c == pytest.approx(1.03 ** (1 / 3) - 1, abs=1e-3) for c in summary["lattice_change"])


def test_relax_endpoint_without_chgnet_returns_501(monkeypatch, srtio3):
    monkeypatch.setattr(candidates_api, "relaxation_available", lambda: False)
    candidate = seed(srtio3)

    response = TestClient(app).post(f"/api/candidates/{candidate.candidate_id}/relax")

    assert response.status_code == 501
    assert "local install" in response.json()["detail"]


def test_relax_endpoint_stores_relaxed_checks(monkeypatch, srtio3):
    candidate = seed(srtio3)
    _, structure = get_store().get(candidate.candidate_id)
    expanded = structure.copy()
    expanded.scale_lattice(structure.volume * 1.06)  # a fake relaxer: the Ba site expands

    monkeypatch.setattr(candidates_api, "relaxation_available", lambda: True)
    monkeypatch.setattr(
        candidates_api,
        "relax",
        lambda s: RelaxOutcome(
            expanded, steps=7, converged=True, energy_per_atom=-8.4, method="fake"
        ),
    )
    body = TestClient(app).post(f"/api/candidates/{candidate.candidate_id}/relax").json()

    relaxation = body["relaxation"]
    assert relaxation["volume_change"] == pytest.approx(0.06, abs=1e-3)
    assert relaxation["steps"] == 7
    assert "CHGNet" in relaxation["assessment"]["notes"][0]
    assert relaxation["structure"]["provenance"]["source"] == "CHGNet relaxation"


@pytest.mark.skipif(
    not relaxation_available(), reason="CHGNet is not installed (uv sync --group relax)"
)
def test_real_chgnet_expands_cell_for_larger_ion(srtio3):
    from app.tools.relaxation import relax

    candidate = seed(srtio3)
    _, structure = get_store().get(candidate.candidate_id)
    outcome = relax(structure)

    assert outcome.structure.volume > structure.volume  # Ba2+ is larger than Sr2+
    assert outcome.steps >= 1
