"""Public and private modes: who can read and change a candidate, on every path."""

import json
import time
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from pymatgen.io.cif import CifWriter

from app.api.deps import get_cod_client, get_literature_client, get_optional_mp_client
from app.auth import InvalidToken, Viewer, sign_token, verify_token
from app.config import Settings, get_settings
from app.main import app
from app.models.candidates import Substitution
from app.storage.memory import MemoryStore, SqlStore, get_store
from app.storage.scoped import NotOwner, ScopedStore
from app.tools.candidates import create_candidate
from app.tools.catalog import build_registry
from app.tools.goals import Goal
from app.tools.literature_sources import LiteratureResult

SECRET = "test-secret-with-at-least-32-characters"
ALICE = "github:1"
BOB = "github:2"
GOAL = {"target_n": 2.2, "min_band_gap": 3.0}


def token(sub: str, login: str = "alice", *, exp: float | None = None, aud: str = "api") -> str:
    return sign_token(
        {"sub": sub, "login": login, "aud": aud, "exp": exp or time.time() + 600}, SECRET
    )


def auth(sub: str, login: str = "alice") -> dict[str, str]:
    return {"Authorization": f"Bearer {token(sub, login)}"}


class NoLiterature:
    def search(self, query: str, limit: int = 5) -> LiteratureResult:
        return LiteratureResult(papers=[], source_status={})


class NoCod:
    def search(self, formula: str, limit: int = 20) -> list:
        return []

    def close(self) -> None:
        pass


@pytest.fixture
def api() -> Iterator[TestClient]:
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, auth_secret=SECRET)
    app.dependency_overrides[get_optional_mp_client] = lambda: None
    app.dependency_overrides[get_literature_client] = lambda: NoLiterature()
    app.dependency_overrides[get_cod_client] = lambda: NoCod()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def create(api: TestClient, srtio3, headers: dict[str, str] | None = None) -> str:
    response = api.post(
        "/api/candidates",
        headers=headers or {},
        json={
            "host": {"cif": str(CifWriter(srtio3)), "filename": "sto.cif"},
            "substitutions": [{"element_from": "Sr", "element_to": "Ba", "fraction": 0.5}],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["candidate_id"]


def publish(api: TestClient, candidate_id: str, credit: str = "name", sub: str = ALICE) -> dict:
    response = api.post(
        f"/api/candidates/{candidate_id}/visibility",
        headers=auth(sub),
        json={"visibility": "published", "credit_display": credit, "consent": True},
    )
    assert response.status_code == 200, response.text
    return response.json()


# Every path with a candidate in it. A new path fails test_every_candidate_path_is_listed until it
# is added here, so a new way to read a candidate cannot skip these tests by accident.
READS = {
    ("GET", "/api/candidates/{candidate_id}"): {},
    ("GET", "/api/candidates/{candidate_id}/spatial"): {},
    ("POST", "/api/candidates/{candidate_id}/scorecard"): {"json": GOAL},
    ("GET", "/api/candidates/{candidate_id}/novelty"): {},
    ("GET", "/api/candidates/{candidate_id}/export.cif"): {},
    ("GET", "/api/candidates/{candidate_id}/export.json"): {},
}
WRITES = {
    ("POST", "/api/candidates/{candidate_id}/decisions"): {
        "json": {"decision": "accept", "reason": "x"}
    },
    ("POST", "/api/candidates/{candidate_id}/visibility"): {
        "json": {"visibility": "published", "consent": True}
    },
    ("POST", "/api/candidates/{candidate_id}/experiments"): {
        "json": {"property": "band_gap", "value": 3.0}
    },
    ("POST", "/api/candidates/{candidate_id}/relax"): {},
    ("POST", "/api/candidates/{candidate_id}/critique"): {"json": {"goal": GOAL}},
}


def call(api: TestClient, route: tuple[str, str], kwargs: dict, candidate_id: str, headers: dict):
    method, path = route
    return api.request(
        method, path.replace("{candidate_id}", candidate_id), headers=headers, **kwargs
    )


def test_every_candidate_path_is_listed():
    found = {
        (method.upper(), path)
        for path, methods in app.openapi()["paths"].items()
        if "{candidate_id}" in path
        for method in methods
    }
    assert found == set(READS) | set(WRITES)


@pytest.mark.parametrize("route,kwargs", [*READS.items(), *WRITES.items()])
def test_private_candidate_is_hidden_on_every_path(api, srtio3, route, kwargs):
    candidate_id = create(api, srtio3, auth(ALICE))
    for headers in ({}, auth(BOB, "bob")):
        response = call(api, route, kwargs, candidate_id, headers)
        # 404, not 403: a stranger cannot tell a private candidate from one that does not exist.
        assert response.status_code == 404, (route, response.text)
        assert candidate_id in response.json()["detail"]
        assert "github:" not in response.text


@pytest.mark.parametrize("route,kwargs", READS.items())
def test_owner_can_read_on_every_path(api, srtio3, route, kwargs):
    candidate_id = create(api, srtio3, auth(ALICE))
    assert call(api, route, kwargs, candidate_id, auth(ALICE)).status_code == 200


@pytest.mark.parametrize("route,kwargs", READS.items())
def test_published_candidate_can_be_read_by_anyone(api, srtio3, route, kwargs):
    candidate_id = create(api, srtio3, auth(ALICE))
    publish(api, candidate_id)
    for headers in ({}, auth(BOB, "bob")):
        response = call(api, route, kwargs, candidate_id, headers)
        assert response.status_code == 200
        assert "github:" not in response.text


@pytest.mark.parametrize("route,kwargs", WRITES.items())
def test_only_the_owner_can_change_a_published_candidate(api, srtio3, route, kwargs):
    candidate_id = create(api, srtio3, auth(ALICE))
    before = publish(api, candidate_id)
    for headers in ({}, auth(BOB, "bob")):
        response = call(api, route, kwargs, candidate_id, headers)
        assert response.status_code == 403, (route, response.text)
    assert api.get(f"/api/candidates/{candidate_id}").json() == before | {
        "mine": False,
        "editable": False,
        "publications": [],
    }


def test_decision_and_measurement_by_the_owner(api, srtio3):
    candidate_id = create(api, srtio3, auth(ALICE))
    response = api.post(
        f"/api/candidates/{candidate_id}/decisions",
        headers=auth(ALICE),
        json={"decision": "accept", "reason": "unpublished idea"},
    )
    assert response.json()["decisions"][0]["reason"] == "unpublished idea"
    response = api.post(
        f"/api/candidates/{candidate_id}/experiments",
        headers=auth(ALICE),
        json={"property": "band_gap", "value": 3.1},
    )
    assert response.json()["experiments"][0]["value"] == 3.1


def test_lists_show_each_viewer_the_right_candidates(api, srtio3):
    open_id = create(api, srtio3)
    alice_private = create(api, srtio3, auth(ALICE))
    alice_published = create(api, srtio3, auth(ALICE))
    publish(api, alice_published)
    bob_private = create(api, srtio3, auth(BOB, "bob"))

    def ids(headers: dict) -> set[str]:
        response = api.get("/api/candidates", headers=headers)
        assert "github:" not in response.text
        return {c["candidate_id"] for c in response.json()}

    mine = {open_id, alice_private, alice_published, bob_private}
    assert ids({}) & mine == {open_id, alice_published}
    assert ids(auth(ALICE)) & mine == {open_id, alice_private, alice_published}
    assert ids(auth(BOB, "bob")) & mine == {open_id, alice_published, bob_private}


def test_public_mode_is_open_to_everyone(api, srtio3):
    candidate_id = create(api, srtio3)
    for headers in ({}, auth(BOB, "bob")):
        body = api.get(f"/api/candidates/{candidate_id}", headers=headers).json()
        assert (body["mine"], body["editable"]) == (False, True)
        response = api.post(
            f"/api/candidates/{candidate_id}/decisions",
            headers=headers,
            json={"decision": "accept"},
        )
        assert response.status_code == 200


@pytest.mark.parametrize("headers", [{}, {"sub": ALICE}])
def test_nobody_can_claim_a_public_mode_candidate(api, srtio3, headers):
    candidate_id = create(api, srtio3)
    response = api.post(
        f"/api/candidates/{candidate_id}/visibility",
        headers=auth(headers["sub"]) if headers else {},
        json={"visibility": "published", "consent": True, "display_name": "x"},
    )
    assert response.status_code == 403


def test_a_published_name_is_the_account_not_typed_text(api, srtio3):
    candidate_id = create(api, srtio3, auth(ALICE, "alice"))
    response = api.post(
        f"/api/candidates/{candidate_id}/visibility",
        headers=auth(ALICE, "alice"),
        json={
            "visibility": "published",
            "credit_display": "name",
            "display_name": "Marie Curie",
            "consent": True,
        },
    )
    credit = response.json()["credit"]
    assert (credit["name"], credit["verified"], credit["license"]) == ("alice", True, "CC BY 4.0")
    assert len(credit["content_sha256"]) == 64


def test_anonymous_credit_does_not_show_the_account(api, srtio3):
    login = "anonymous-test-login"
    candidate_id = create(api, srtio3, auth(ALICE, login))
    publish(api, candidate_id, "anonymous")
    for url in (
        f"/api/candidates/{candidate_id}",
        f"/api/candidates/{candidate_id}/export.json",
        "/api/candidates",
    ):
        text = api.get(url).text
        assert "github:" not in text
        assert login not in text


def test_an_earlier_named_publication_stays_with_the_owner(api, srtio3):
    """Publish with a name, undo, publish as anonymous: others must not see the earlier name."""
    login = "renamed-test-login"
    candidate_id = create(api, srtio3, auth(ALICE, login))
    url = f"/api/candidates/{candidate_id}/visibility"
    body = {"visibility": "published", "consent": True}
    api.post(url, headers=auth(ALICE, login), json=body | {"credit_display": "name"})
    api.post(url, headers=auth(ALICE, login), json={"visibility": "private"})
    api.post(url, headers=auth(ALICE, login), json=body | {"credit_display": "anonymous"})
    assert login not in api.get(f"/api/candidates/{candidate_id}").text
    assert login not in api.get(f"/api/candidates/{candidate_id}/export.json").text
    own = api.get(f"/api/candidates/{candidate_id}", headers=auth(ALICE, login)).json()
    assert [p["action"] for p in own["publications"]] == ["published", "unpublished", "published"]
    assert own["publications"][0]["credit"]["name"] == login


def test_publishing_needs_consent(api, srtio3):
    candidate_id = create(api, srtio3, auth(ALICE))
    response = api.post(
        f"/api/candidates/{candidate_id}/visibility",
        headers=auth(ALICE),
        json={"visibility": "published"},
    )
    assert response.status_code == 400
    assert api.get(f"/api/candidates/{candidate_id}").status_code == 404


def test_undo_hides_it_again_and_keeps_the_record(api, srtio3):
    candidate_id = create(api, srtio3, auth(ALICE))
    publish(api, candidate_id)
    response = api.post(
        f"/api/candidates/{candidate_id}/visibility",
        headers=auth(ALICE),
        json={"visibility": "private"},
    )
    assert response.status_code == 200
    assert response.json()["credit"] is None
    assert [p["action"] for p in response.json()["publications"]] == ["published", "unpublished"]
    assert api.get(f"/api/candidates/{candidate_id}").status_code == 404


def test_a_revision_of_published_work_is_yours_and_keeps_the_credit(api, srtio3):
    original = create(api, srtio3, auth(ALICE, "alice"))
    publish(api, original)
    body = {
        "host": {"candidate_id": original},
        "substitutions": [{"element_from": "Ti", "element_to": "Zr", "fraction": 0.25}],
    }
    child = api.post("/api/candidates", headers=auth(BOB, "bob"), json=body).json()
    assert (child["parent_id"], child["mine"], child["visibility"]) == (original, True, "private")
    assert child["based_on_credit"]["name"] == "alice"
    assert api.get(f"/api/candidates/{child['candidate_id']}").status_code == 404
    assert (
        api.get(f"/api/candidates/{original}", headers=auth(BOB, "bob")).json()["editable"] is False
    )

    # A revision of that revision keeps the original author's credit.
    body["host"] = {"candidate_id": child["candidate_id"]}
    body["substitutions"] = [{"element_from": "Ti", "element_to": "Hf", "fraction": 0.25}]
    grandchild = api.post("/api/candidates", headers=auth(BOB, "bob"), json=body).json()
    assert grandchild["based_on_credit"]["name"] == "alice"


def test_your_own_revision_has_no_outside_credit(api, srtio3):
    original = create(api, srtio3, auth(ALICE))
    publish(api, original)
    child = api.post(
        "/api/candidates",
        headers=auth(ALICE),
        json={
            "host": {"candidate_id": original},
            "substitutions": [{"element_from": "Ti", "element_to": "Zr", "fraction": 0.25}],
        },
    ).json()
    assert child["based_on_credit"] is None


@pytest.mark.parametrize(
    "path", ["/api/candidates", "/api/structures/spatial", "/api/structures/assess"]
)
def test_a_private_candidate_cannot_be_used_as_a_host(api, srtio3, path):
    candidate_id = create(api, srtio3, auth(ALICE))
    host = {"candidate_id": candidate_id}
    body = (
        {
            "host": host,
            "substitutions": [{"element_from": "Ti", "element_to": "Zr", "fraction": 0.25}],
        }
        if path == "/api/candidates"
        else host
    )
    for headers in ({}, auth(BOB, "bob")):
        response = api.post(path, headers=headers, json=body)
        assert response.status_code >= 400
        assert response.status_code < 500


def test_score_hides_a_private_candidate(api, srtio3):
    candidate_id = create(api, srtio3, auth(ALICE))
    body = {"goal": GOAL, "candidate_id": candidate_id}
    assert api.post("/api/score", json=body).status_code == 404
    assert api.post("/api/score", headers=auth(BOB, "bob"), json=body).status_code == 404
    assert api.post("/api/score", headers=auth(ALICE), json=body).status_code == 200


def test_export_of_a_published_child_does_not_show_a_private_parent(api, srtio3):
    parent = create(api, srtio3, auth(ALICE))
    api.post(
        f"/api/candidates/{parent}/decisions",
        headers=auth(ALICE),
        json={"decision": "modify", "reason": "secret plan"},
    )
    child = api.post(
        "/api/candidates",
        headers=auth(ALICE),
        json={
            "host": {"candidate_id": parent},
            "substitutions": [{"element_from": "Ti", "element_to": "Zr", "fraction": 0.25}],
        },
    ).json()["candidate_id"]
    publish(api, child)
    assert api.get(f"/api/candidates/{parent}").status_code == 404
    record = api.get(f"/api/candidates/{child}/export.json")
    assert record.status_code == 200
    assert "secret plan" not in record.text
    assert record.json()["ancestry"] == []
    # The owner still sees the whole line.
    own = api.get(f"/api/candidates/{child}/export.json", headers=auth(ALICE))
    assert [a["candidate_id"] for a in own.json()["ancestry"]] == [parent]


@pytest.mark.parametrize(
    "header",
    [
        "Bearer not-a-token",
        "Bearer a.b",
        "Basic abc",
        f"Bearer {token(ALICE, exp=time.time() - 1)}",
        f"Bearer {token(ALICE, aud='session')}",
        f"Bearer {sign_token({'sub': ALICE, 'login': 'a', 'aud': 'api', 'exp': time.time() + 600}, 'x' * 32)}",
    ],
)
def test_a_bad_token_is_an_error_and_never_public_mode(api, srtio3, header):
    """Otherwise an expired sign-in would save private work where anyone can read it."""
    response = api.post(
        "/api/candidates",
        headers={"Authorization": header},
        json={
            "host": {"cif": str(CifWriter(srtio3)), "filename": "sto.cif"},
            "substitutions": [{"element_from": "Sr", "element_to": "Ba", "fraction": 0.5}],
        },
    )
    assert response.status_code == 401
    assert api.get("/api/candidates", headers={"Authorization": header}).status_code == 401


def test_any_token_is_refused_when_sign_in_is_off(srtio3):
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, auth_secret=None)
    try:
        response = TestClient(app).get("/api/candidates", headers=auth(ALICE))
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 401


def test_a_private_candidate_stays_hidden_when_sign_in_is_off(api, srtio3):
    candidate_id = create(api, srtio3, auth(ALICE))
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, auth_secret=None)
    assert api.get(f"/api/candidates/{candidate_id}").status_code == 404
    assert candidate_id not in {c["candidate_id"] for c in api.get("/api/candidates").json()}


def test_publishing_works_as_before_when_sign_in_is_off(srtio3):
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, auth_secret=None)
    app.dependency_overrides[get_optional_mp_client] = lambda: None
    try:
        api = TestClient(app)
        candidate_id = create(api, srtio3)
        response = api.post(
            f"/api/candidates/{candidate_id}/visibility",
            json={
                "visibility": "published",
                "credit_display": "name",
                "display_name": "A. Researcher",
                "consent": True,
            },
        )
    finally:
        app.dependency_overrides.clear()
    assert response.json()["credit"]["name"] == "A. Researcher"
    assert response.json()["credit"]["verified"] is False


def test_short_secret_is_refused():
    with pytest.raises(ValueError, match="32 characters"):
        Settings(_env_file=None, auth_secret="short")


def test_token_round_trip_and_tampering():
    good = token(ALICE, "alice")
    assert verify_token(good, SECRET) == Viewer(id=ALICE, login="alice")
    body, signature = good.split(".")
    other = sign_token({"sub": BOB, "login": "bob", "aud": "api", "exp": time.time() + 9}, SECRET)
    for bad in (f"{other.split('.')[0]}.{signature}", f"{body}.", good + "x"):
        with pytest.raises(InvalidToken):
            verify_token(bad, SECRET)


def test_store_keeps_the_owner_and_hides_it_from_the_view(tmp_path, srtio3):
    for store in (MemoryStore(), SqlStore(f"sqlite:///{tmp_path / 'c.db'}")):
        alice = ScopedStore(store, Viewer(id=ALICE, login="alice"))
        bob = ScopedStore(store, Viewer(id=BOB, login="bob"))
        made = create_candidate(
            alice, srtio3, _host(), [Substitution(element_from="Sr", element_to="Ba", fraction=0.5)]
        )
        assert (made.owner_id, made.mine) == (None, True)
        assert store.get(made.candidate_id)[0].owner_id == ALICE
        assert bob.get(made.candidate_id) is None
        assert bob.update(made.candidate_id, {"visibility": "published"}) is None
        alice.update(made.candidate_id, {"visibility": "published"})
        assert store.get(made.candidate_id)[0].owner_id == ALICE  # an update keeps the owner
        with pytest.raises(NotOwner):
            bob.update(made.candidate_id, {"decisions": []})


def test_old_records_with_no_owner_stay_open(tmp_path, srtio3):
    """Candidates saved before accounts existed have no owner fields in their JSON."""
    store = SqlStore(f"sqlite:///{tmp_path / 'old.db'}")
    made = create_candidate(
        store, srtio3, _host(), [Substitution(element_from="Sr", element_to="Ba", fraction=0.5)]
    )
    from sqlalchemy import update

    from app.storage.memory import candidates_table

    old = json.loads(made.model_dump_json())
    for key in ("owner_id", "mine", "editable", "based_on_credit", "publications"):
        old.pop(key)
    with store._engine.begin() as conn:
        conn.execute(update(candidates_table).values(data=json.dumps(old)))
    seen = ScopedStore(store, None).get(made.candidate_id)[0]
    assert (seen.owner_id, seen.mine, seen.editable) == (None, False, True)


def test_agent_tools_see_only_what_the_viewer_can(srtio3):
    store = MemoryStore()
    alice = ScopedStore(store, Viewer(id=ALICE, login="alice"))
    secret = create_candidate(
        alice, srtio3, _host(), [Substitution(element_from="Sr", element_to="Ba", fraction=0.5)]
    ).candidate_id
    goal = Goal(target_n=2.2, min_band_gap=3.0)
    for viewer in (None, Viewer(id=BOB, login="bob")):
        registry = build_registry(None, NoLiterature(), store=ScopedStore(store, viewer), goal=goal)
        for tool in ("get_candidate", "score_against_goal", "get_scorecard", "check_novelty"):
            assert "error" in _run(registry, tool, {"candidate_id": secret}), tool
        made = _run(
            registry,
            "create_candidate",
            {
                "host_candidate_id": secret,
                "substitutions": [{"element_from": "Ti", "element_to": "Zr", "fraction": 0.25}],
            },
        )
        assert "error" in made
    own = build_registry(None, NoLiterature(), store=alice, goal=goal)
    assert _run(own, "get_candidate", {"candidate_id": secret})["candidate_id"] == secret
    made = _run(
        own,
        "create_candidate",
        {
            "host_candidate_id": secret,
            "substitutions": [{"element_from": "Ti", "element_to": "Zr", "fraction": 0.25}],
        },
    )
    assert store.get(made["candidate_id"])[0].owner_id == ALICE  # the agent saves as the viewer


def test_agent_context_does_not_name_a_private_candidate(api, srtio3):
    from app.api.routes import AgentContext, with_context

    candidate_id = create(api, srtio3, auth(ALICE))
    context = AgentContext(current_candidate_id=candidate_id)
    formula = get_store().get(candidate_id)[0].formula
    assert formula not in with_context("hi", context, ScopedStore(get_store(), None))
    own = ScopedStore(get_store(), Viewer(id=ALICE, login="alice"))
    assert formula in with_context("hi", context, own)


def test_browser_can_send_the_token(api):
    response = api.options(
        "/api/candidates",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert response.status_code == 200
    assert "authorization" in response.headers["access-control-allow-headers"].lower()


def _host():
    from app.models.evidence import Provenance

    return Provenance(source="test")


def _run(registry, name: str, arguments: dict) -> dict:
    return registry.execute(name, json.dumps(arguments))
