import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.agents.critique import (
    View,
    evidence_pack,
    known_numbers,
    run_critique,
    unsupported_numbers,
)
from app.api import candidates as candidates_api
from app.main import app
from app.models.candidates import Substitution
from app.models.evidence import Provenance
from app.storage.memory import get_store
from app.tools.candidates import create_candidate
from app.tools.goals import Goal, score_candidate
from app.tools.spatial import analyze

GOAL = Goal(target_n=2.2, min_band_gap=3.0)
PIXEL = "data:image/png;base64,iVBORw0KGgo="


class FakeClient:
    """Stands in for the Meta Model API: returns the queued JSON replies in order."""

    def __init__(self, *replies: dict):
        self.replies = [json.dumps(r) for r in replies]
        self.requests: list[dict] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.requests.append(kwargs)
        content = self.replies.pop(0)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def reply(points, suggestions=(), summary="Mixed evidence.", questions=()):
    return {
        "verdict": "mixed",
        "summary": summary,
        "points": list(points),
        "suggestions": list(suggestions),
        "questions": list(questions),
    }


@pytest.fixture
def candidate(srtio3):
    return create_candidate(
        get_store(),
        srtio3,
        Provenance(source="test"),
        [
            Substitution(element_from="Sr", element_to="La", fraction=0.5),
            Substitution(element_from="Ti", element_to="Al", fraction=0.5),
        ],
    )


def pack(candidate):
    _, structure = get_store().get(candidate.candidate_id)
    return evidence_pack(candidate, score_candidate(candidate, GOAL), analyze(structure), None)


def test_evidence_pack_covers_checks_sites_goal_and_space(candidate):
    ids = {e.id for e in pack(candidate)}

    assert {"check.charge", "goal.n", "goal.band_gap", "spatial.symmetry", "spatial.links"} <= ids
    assert any(i.startswith("site.La") for i in ids)
    assert any(i.startswith("spatial.poly.") for i in ids)


def test_numbers_must_match_evidence_at_the_precision_written():
    known = known_numbers(["n 2.432 (Experimental); distortion index 0.0183"])

    assert unsupported_numbers("n is about 2.43 and the index 0.018", known) == []
    assert unsupported_numbers("n near 2.44", known) == ["2.44"]
    assert unsupported_numbers("SrTiO3 and LL-0003 have 12 sites", known) == []  # integers pass


def test_critique_retries_once_then_returns_clean_result(candidate):
    evidence = pack(candidate)
    bad = reply(
        [{"kind": "concern", "text": "n is 2.91.", "evidence": ["made.up"], "basis": "evidence"}]
    )
    good = reply(
        [
            {
                "kind": "concern",
                "text": "Charge is balanced.",
                "evidence": ["check.charge"],
                "basis": "evidence",
            }
        ],
        suggestions=[
            {
                "change": "Relax with CHGNet.",
                "rationale": "Positions are unrelaxed.",
                "evidence": ["check.charge"],
            }
        ],
    )
    client = FakeClient(bad, good)
    views = [View(label="down the c axis", image=PIXEL)]

    critique = run_critique(
        client, "muse-test", candidate, GOAL, evidence, views, {"La": "#70d4ff"}, "unrelaxed"
    )

    assert len(client.requests) == 2
    first = client.requests[0]["messages"][1]["content"]
    assert any(part["type"] == "image_url" for part in first)
    assert "La #70d4ff" in first[0]["text"]
    retry = client.requests[1]["messages"][-1]["content"]
    assert "made.up" in retry and "2.91" in retry
    assert critique.warnings == [] and critique.views == 1
    assert critique.points[0].evidence == ["check.charge"]
    assert critique.evidence == evidence  # what the model saw is kept with the critique


def test_problems_left_after_retry_become_warnings(candidate):
    evidence = pack(candidate)
    bad = reply(
        [
            {
                "kind": "strength",
                "text": "Gap 4.73 eV.",
                "evidence": ["check.charge", "nope"],
                "basis": "both",
            }
        ]
    )
    client = FakeClient(bad, bad)

    critique = run_critique(client, "muse-test", candidate, GOAL, evidence, [], {}, "unrelaxed")

    assert any("4.73" in w for w in critique.warnings)
    assert any("nope" in w for w in critique.warnings)
    assert critique.points[0].evidence == ["check.charge"]  # unknown IDs are dropped


def test_critique_endpoint_stores_the_critique(candidate, monkeypatch):
    good = reply(
        [
            {
                "kind": "strength",
                "text": "Charge balanced.",
                "evidence": ["check.charge"],
                "basis": "evidence",
            }
        ]
    )
    monkeypatch.setattr(candidates_api, "create_client", lambda settings: FakeClient(good))
    client = TestClient(app)
    url = f"/api/candidates/{candidate.candidate_id}/critique"

    body = {
        "goal": GOAL.model_dump(),
        "locale": "ko",
        "views": [{"label": "down c", "image": PIXEL}],
    }
    response = client.post(url, json=body)

    assert response.status_code == 200
    stored = response.json()["critiques"]
    assert len(stored) == 1 and stored[0]["locale"] == "ko" and stored[0]["verdict"] == "mixed"
    assert client.post(url, json={**body, "geometry": "relaxed"}).status_code == 400
    bad_image = {**body, "views": [{"label": "x", "image": "https://example.com/a.png"}]}
    assert client.post(url, json=bad_image).status_code == 422
