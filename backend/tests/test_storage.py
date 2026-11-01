from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.candidates import Decision, Substitution
from app.models.evidence import Provenance
from app.storage.memory import MemoryStore, SqlStore, add_decision, get_store, sqlalchemy_url
from app.tools.candidates import create_candidate


def make(store, srtio3, parent_id=None, host=None):
    return create_candidate(
        store,
        host or srtio3,
        Provenance(source="test"),
        [Substitution(element_from="Sr", element_to="La", fraction=0.5)],
        parent_id,
    )


@pytest.mark.parametrize("kind", ["memory", "sqlite"])
def test_store_round_trip(kind, tmp_path, srtio3):
    store = MemoryStore() if kind == "memory" else SqlStore(f"sqlite:///{tmp_path / 'c.db'}")

    first = make(store, srtio3)
    second = make(store, srtio3)
    assert (first.candidate_id, second.candidate_id) == ("LL-0001", "LL-0002")

    candidate, structure = store.get(first.candidate_id)
    assert candidate == first
    assert structure.composition.reduced_formula == "SrLaTi2O6"

    decision = Decision(decision="reject", reason="test", created_at=datetime.now(UTC))
    updated = add_decision(store, first.candidate_id, decision)
    assert updated.decisions[0].reason == "test"
    assert store.get(first.candidate_id)[0].decisions[0].decision == "reject"
    assert [c.candidate_id for c in store.all()] == ["LL-0001", "LL-0002"]
    assert store.get("LL-9999") is None


def test_sql_store_survives_restart(tmp_path, srtio3):
    url = f"sqlite:///{tmp_path / 'c.db'}"
    first = make(SqlStore(url), srtio3)

    reopened = SqlStore(url)  # e.g. after the server restarts

    assert reopened.get(first.candidate_id)[0].formula == first.formula
    assert make(reopened, srtio3).candidate_id == "LL-0002"


def test_postgres_url_uses_psycopg3():
    assert sqlalchemy_url("postgres://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert sqlalchemy_url("postgresql://u:p@h/db?sslmode=require").startswith(
        "postgresql+psycopg://"
    )
    assert sqlalchemy_url("sqlite:///x.db") == "sqlite:///x.db"


def test_publish_needs_consent_and_can_be_undone(srtio3):
    candidate = make(get_store(), srtio3)
    api = TestClient(app)
    url = f"/api/candidates/{candidate.candidate_id}/visibility"

    assert candidate.visibility == "private"  # private by default
    assert api.post(url, json={"visibility": "published"}).status_code == 400
    assert (
        api.post(
            url, json={"visibility": "published", "credit_display": "name", "consent": True}
        ).status_code
        == 400
    )

    published = api.post(
        url,
        json={
            "visibility": "published",
            "credit_display": "name",
            "display_name": "A. Researcher",
            "consent": True,
        },
    ).json()
    assert published["visibility"] == "published"
    assert published["credit"]["name"] == "A. Researcher"

    private = api.post(url, json={"visibility": "private"}).json()
    assert private["visibility"] == "private"
    assert private["credit"] is None


def test_experiment_upload(srtio3):
    candidate = make(get_store(), srtio3)
    api = TestClient(app)
    url = f"/api/candidates/{candidate.candidate_id}/experiments"

    missing_wavelength = api.post(url, json={"property": "refractive_index", "value": 2.3})
    assert missing_wavelength.status_code == 400

    body = api.post(
        url,
        json={
            "property": "refractive_index",
            "value": 2.31,
            "wavelength_nm": 550,
            "sample": "thin film",
            "method": "ellipsometry",
        },
    ).json()
    [record] = body["experiments"]
    assert record["value"] == 2.31
    assert record["sample"] == "thin film"
    assert (
        api.post(
            "/api/candidates/LL-9999/experiments", json={"property": "band_gap", "value": 3}
        ).status_code
        == 404
    )
