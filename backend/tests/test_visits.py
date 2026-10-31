from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app
from app.storage.visits import UNKNOWN, MemoryVisits, SqlVisits, get_visits


@pytest.fixture
def client():
    get_visits.cache_clear()
    get_visits().counts()  # a fresh in-memory counter for this test
    yield TestClient(app)
    app.dependency_overrides.clear()
    get_visits.cache_clear()


@pytest.mark.parametrize("kind", ["memory", "sqlite"])
def test_counts_each_country(kind, tmp_path):
    visits = MemoryVisits() if kind == "memory" else SqlVisits(f"sqlite:///{tmp_path / 'v.db'}")

    visits.add("KR")
    visits.add("KR")
    visits.add("US")
    visits.add(None)

    assert visits.counts() == {"KR": 2, "US": 1, UNKNOWN: 1}


def test_sql_counts_survive_a_restart(tmp_path):
    url = f"sqlite:///{tmp_path / 'v.db'}"
    SqlVisits(url).add("KR")
    assert SqlVisits(url).counts() == {"KR": 1}
    assert SqlVisits(url).persistent and not MemoryVisits().persistent


def test_parallel_visits_are_all_counted(tmp_path):
    visits = SqlVisits(f"sqlite:///{tmp_path / 'v.db'}")
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _: visits.add("KR"), range(40)))
    assert visits.counts() == {"KR": 40}


def test_api_reports_totals_with_the_largest_first(client):
    for country in ("US", "KR", "KR", None):
        body = {"country": country} if country else {}
        assert client.post("/api/visits", json=body).status_code == 204

    stats = client.get("/api/visits").json()

    assert stats["total"] == 4
    assert stats["unknown"] == 1
    assert stats["countries"] == [{"code": "KR", "count": 2}, {"code": "US", "count": 1}]
    assert stats["persistent"] is False


@pytest.mark.parametrize("bad", ["kr", "KOR", "1A", "", UNKNOWN])
def test_api_rejects_anything_but_a_country_code(client, bad):
    assert client.post("/api/visits", json={"country": bad}).status_code == 422
    assert client.get("/api/visits").json()["total"] == 0


def test_api_stores_no_ip_address_or_other_detail(client):
    client.post("/api/visits", json={"country": "KR"}, headers={"X-Forwarded-For": "203.0.113.9"})
    assert "203.0.113.9" not in client.get("/api/visits").text
    assert get_visits().counts() == {"KR": 1}


def test_api_needs_the_secret_once_it_is_set(client):
    app.dependency_overrides[get_settings] = lambda: Settings(visit_secret="right")

    assert client.post("/api/visits", json={"country": "KR"}).status_code == 403
    wrong = client.post("/api/visits", json={"country": "KR"}, headers={"X-Visit-Secret": "no"})
    assert wrong.status_code == 403
    assert client.get("/api/visits").json()["total"] == 0

    good = client.post("/api/visits", json={"country": "KR"}, headers={"X-Visit-Secret": "right"})
    assert good.status_code == 204
    assert client.get("/api/visits").json()["total"] == 1
