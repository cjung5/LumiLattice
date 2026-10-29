import json

import httpx
from fastapi.testclient import TestClient
from pymatgen.io.cif import CifWriter

from app.config import Settings, get_settings
from app.main import app
from app.storage.memory import CandidateStore
from app.tools.catalog import build_registry
from app.tools.literature import OpenAlexClient


def client() -> TestClient:
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None)
    return TestClient(app)


def test_candidate_from_cif_then_revision(srtio3):
    api = client()
    try:
        first = api.post(
            "/api/candidates",
            json={
                "host": {"cif": str(CifWriter(srtio3)), "filename": "sto.cif"},
                "substitutions": [{"element_from": "Sr", "element_to": "La", "fraction": 0.5}],
            },
        )
        assert first.status_code == 200, first.text
        body = first.json()
        assert body["candidate_id"].startswith("LL-")
        assert body["assessment"]["status"] == "Structural Concerns"
        assert body["transformation"]["host"]["source"] == "CIF upload"

        # Researcher feedback: compensate the charge with Ga on the Ti site.
        revised = api.post(
            "/api/candidates",
            json={
                "host": {"candidate_id": body["candidate_id"]},
                "substitutions": [{"element_from": "Ti", "element_to": "Ga", "fraction": 0.5}],
            },
        )
        assert revised.status_code == 200, revised.text
        assert revised.json()["parent_id"] == body["candidate_id"]
        assert revised.json()["assessment"]["status"] == "Structurally Plausible"
        assert api.get(f"/api/candidates/{body['candidate_id']}").status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_candidate_needs_exactly_one_host(srtio3):
    api = client()
    try:
        response = api.post(
            "/api/candidates",
            json={
                "host": {"material_id": "mp-5229", "candidate_id": "LL-0001"},
                "substitutions": [{"element_from": "Ti", "element_to": "Zr", "fraction": 1}],
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400


def test_assess_host(srtio3):
    api = client()
    try:
        response = api.post("/api/structures/assess", json={"cif": str(CifWriter(srtio3))})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["status"] == "Structurally Plausible"


def test_agent_tool_revises_a_candidate(srtio3):
    store = CandidateStore()
    literature = OpenAlexClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"results": []}))
    )
    registry = build_registry(None, literature, store)

    # Seed a candidate the way the API would, then let the tool revise it.
    from app.models.candidates import Substitution
    from app.models.evidence import Provenance
    from app.tools.candidates import create_candidate

    seed = create_candidate(
        store,
        srtio3,
        Provenance(source="test"),
        [Substitution(element_from="Sr", element_to="La", fraction=0.5)],
    )
    result = registry.execute(
        "create_candidate",
        json.dumps(
            {
                "host_candidate_id": seed.candidate_id,
                "substitutions": [{"element_from": "Ti", "element_to": "Ga", "fraction": 0.5}],
            }
        ),
    )

    assert result["parent_id"] == seed.candidate_id
    assert result["assessment_status"] == "Structurally Plausible"
