import httpx
import pytest

from app.tools.literature import OpenAlexClient
from app.tools.materials import MaterialsProjectClient
from app.tools.registry import UpstreamError
from app.tools.usage import DailyCap, RateLimiter, ResponseCache, cache_key


def test_daily_cap_blocks_after_limit():
    cap = DailyCap("Test", limit=2)
    cap.take()
    cap.take()

    with pytest.raises(UpstreamError, match="cap"):
        cap.take()


def test_rate_limiter_stores_no_client_address_and_removes_old_entries(monkeypatch):
    now = [100.0]
    monkeypatch.setattr("app.tools.usage.time.monotonic", lambda: now[0])
    limiter = RateLimiter(max_requests=1, window_seconds=60)

    assert limiter.allow("203.0.113.9")
    assert not limiter.allow("203.0.113.9")
    assert b"203.0.113.9" not in b"".join(limiter._hits)

    now[0] += 61
    assert limiter.allow("198.51.100.1")
    assert len(limiter._hits) == 1
    assert limiter.allow("203.0.113.9")


def test_cache_key_ignores_api_key():
    assert cache_key("/w", {"q": "a", "api_key": "secret"}) == cache_key("/w", {"q": "a"})


def test_openalex_cache_avoids_second_request():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"results": []})

    client = OpenAlexClient(
        "key", httpx.MockTransport(handler), cache=ResponseCache(), cap=DailyCap("OA", 10)
    )
    client.search("TiO2")
    client.search("TiO2")

    assert len(calls) == 1


def test_openalex_stops_when_free_budget_is_low():
    cap = DailyCap("OA", 10)
    headers = {"x-ratelimit-remaining-usd": "0.01"}
    client = OpenAlexClient(
        "key",
        httpx.MockTransport(lambda r: httpx.Response(200, json={"results": []}, headers=headers)),
        cache=ResponseCache(),
        cap=cap,
    )
    client.search("TiO2")

    with pytest.raises(UpstreamError):
        client.search("ZrO2")


def test_mp_requests_legacy_ids_and_uses_cache():
    calls = []

    def handler(request):
        calls.append(dict(request.url.params))
        return httpx.Response(200, json={"data": []})

    client = MaterialsProjectClient(
        "key", httpx.MockTransport(handler), cache=ResponseCache(), cap=DailyCap("MP", 10)
    )
    client.search(formula="SrTiO3")
    client.search(formula="SrTiO3")

    assert len(calls) == 1
    assert calls[0]["id_format"] == "legacy"
