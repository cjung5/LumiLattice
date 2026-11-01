from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.api import routes
from app.config import Settings, get_settings
from app.main import app
from app.models.candidates import Substitution
from app.models.evidence import Provenance
from app.storage.memory import get_store
from app.tools.candidates import create_candidate
from app.tools.usage import AGENT_RATE


class OneShotResponses:
    """Fake Responses API: answers immediately and records the request."""

    def __init__(self):
        self.requests = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        return SimpleNamespace(id="resp_1", output=[], output_text="done")


@pytest.fixture
def fake_agent(monkeypatch):
    fake = OneShotResponses()
    monkeypatch.setattr(routes, "create_client", lambda settings: SimpleNamespace(responses=fake))
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, model_api_key=SecretStr("test")
    )
    yield fake
    app.dependency_overrides.clear()


def test_context_and_decision_reach_the_model(fake_agent, srtio3):
    seed = create_candidate(
        get_store(),
        srtio3,
        Provenance(source="test"),
        [Substitution(element_from="Sr", element_to="La", fraction=0.5)],
    )
    response = TestClient(app).post(
        "/api/agent/run",
        json={
            "message": "Please revise it.",
            "previous_response_id": "resp_0",
            "context": {
                "host_material_id": "mp-5229",
                "host_label": "SrTiO3",
                "current_candidate_id": seed.candidate_id,
                "decision": "modify",
                "feedback": "Keep Ti4+ only.",
            },
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["candidate_ids"] == []
    sent = fake_agent.requests[0]
    assert sent["previous_response_id"] == "resp_0"
    text = sent["input"][0]["content"]
    assert "mp-5229" in text
    assert f"{seed.candidate_id} ({seed.formula}), Structural Concerns" in text
    assert 'modify. Reason: "Keep Ti4+ only."' in text


def test_agent_rate_limit(fake_agent):
    api = TestClient(app)
    for _ in range(AGENT_RATE.max_requests):
        assert api.post("/api/agent/run", json={"message": "hi"}).status_code == 200

    assert api.post("/api/agent/run", json={"message": "hi"}).status_code == 429


def test_changing_x_forwarded_for_does_not_avoid_the_rate_limit(fake_agent):
    api = TestClient(app)
    for n in range(AGENT_RATE.max_requests):
        response = api.post(
            "/api/agent/run", json={"message": "hi"}, headers={"X-Forwarded-For": f"203.0.113.{n}"}
        )
        assert response.status_code == 200

    response = api.post(
        "/api/agent/run", json={"message": "hi"}, headers={"X-Forwarded-For": "198.51.100.1"}
    )
    assert response.status_code == 429


def test_rate_limit_is_per_real_ip(fake_agent):
    api = TestClient(app)
    first = {"X-Real-IP": "203.0.113.1"}
    for _ in range(AGENT_RATE.max_requests):
        assert api.post("/api/agent/run", json={"message": "hi"}, headers=first).status_code == 200
    assert api.post("/api/agent/run", json={"message": "hi"}, headers=first).status_code == 429

    other = {"X-Real-IP": "203.0.113.2"}
    assert api.post("/api/agent/run", json={"message": "hi"}, headers=other).status_code == 200


def test_last_real_ip_is_used_when_a_proxy_adds_to_the_client_value(fake_agent):
    api = TestClient(app)
    for n in range(AGENT_RATE.max_requests):
        headers = [("X-Real-IP", f"203.0.113.{n}"), ("X-Real-IP", "198.51.100.1")]
        assert (
            api.post("/api/agent/run", json={"message": "hi"}, headers=headers).status_code == 200
        )

    headers = [("X-Real-IP", "203.0.113.200"), ("X-Real-IP", "198.51.100.1")]
    assert api.post("/api/agent/run", json={"message": "hi"}, headers=headers).status_code == 429


def test_decision_is_recorded(srtio3):
    seed = create_candidate(
        get_store(),
        srtio3,
        Provenance(source="test"),
        [Substitution(element_from="Ti", element_to="Zr", fraction=0.5)],
    )
    api = TestClient(app)

    response = api.post(
        f"/api/candidates/{seed.candidate_id}/decisions",
        json={"decision": "reject", "reason": "Zr site is overbonded."},
    )

    assert response.status_code == 200
    [decision] = response.json()["decisions"]
    assert decision["decision"] == "reject"
    assert (
        api.post("/api/candidates/LL-9999/decisions", json={"decision": "accept"}).status_code
        == 404
    )
