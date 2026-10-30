"""Keeps external API use inside the free tiers: a response cache and a daily request cap.

- OpenAlex: a search costs $0.001 and a free key gets $1 per day (x-ratelimit-* headers).
  The cap stops at 500 requests per day, half of the free budget.
- Materials Project: free, with rate limits. The cap keeps use polite.
"""

import time
from collections import OrderedDict
from datetime import UTC, datetime
from threading import Lock
from typing import Any

from app.tools.registry import UpstreamError

DAY_SECONDS = 24 * 60 * 60


class ResponseCache:
    def __init__(self, ttl_seconds: float = DAY_SECONDS, max_entries: int = 512):
        self._ttl = ttl_seconds
        self._max = max_entries
        self._items: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._lock = Lock()

    def get(self, key: str) -> Any | None:
        with self._lock:
            item = self._items.get(key)
            if item is None or time.monotonic() - item[0] > self._ttl:
                self._items.pop(key, None)
                return None
            self._items.move_to_end(key)
            return item[1]

    def put(self, key: str, value: Any) -> None:
        with self._lock:
            self._items[key] = (time.monotonic(), value)
            self._items.move_to_end(key)
            while len(self._items) > self._max:
                self._items.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()


class DailyCap:
    """Counts requests per UTC day and refuses more than `limit`."""

    def __init__(self, source: str, limit: int):
        self.source = source
        self.limit = limit
        self._day = ""
        self._count = 0
        self._lock = Lock()

    def take(self) -> None:
        with self._lock:
            today = datetime.now(UTC).date().isoformat()
            if today != self._day:
                self._day, self._count = today, 0
            if self._count >= self.limit:
                raise UpstreamError(
                    f"{self.source} daily request cap ({self.limit}) reached. "
                    "It resets at 00:00 UTC; cached results still work."
                )
            self._count += 1

    def reset(self) -> None:
        with self._lock:
            self._day, self._count = "", 0

    def exhaust(self) -> None:
        """Stop all requests for the rest of the UTC day (e.g. the free budget is nearly gone)."""
        with self._lock:
            self._day = datetime.now(UTC).date().isoformat()
            self._count = self.limit


MP_CACHE = ResponseCache()
MP_CAP = DailyCap("Materials Project", limit=1000)
OPENALEX_CACHE = ResponseCache()
OPENALEX_CAP = DailyCap("OpenAlex", limit=500)
# Stop early when the free OpenAlex budget for the day falls below this (USD).
OPENALEX_MIN_REMAINING_USD = 0.05
# Crossref, arXiv, and COD are free and keyless; caps and throttles keep use polite.
CROSSREF_CACHE = ResponseCache()
CROSSREF_CAP = DailyCap("Crossref", limit=1000)
ARXIV_CACHE = ResponseCache()
ARXIV_CAP = DailyCap("arXiv", limit=300)
COD_CACHE = ResponseCache()
COD_CAP = DailyCap("COD", limit=500)


class Throttle:
    """At most one request per `min_interval` seconds (callers wait their turn)."""

    def __init__(self, min_interval: float):
        self.min_interval = min_interval
        self._last = 0.0
        self._lock = Lock()

    def wait(self) -> None:
        with self._lock:
            delay = self._last + self.min_interval - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            self._last = time.monotonic()


CROSSREF_THROTTLE = Throttle(1.0)  # public pool: 1 request per second, 1 at a time
ARXIV_THROTTLE = Throttle(3.0)  # arXiv API terms: no more than 1 request every 3 seconds


class RateLimiter:
    """Sliding-window limit per client (e.g. IP address)."""

    def __init__(self, max_requests: int, window_seconds: float):
        self.max_requests = max_requests
        self.window = window_seconds
        self._hits: dict[str, list[float]] = {}
        self._lock = Lock()

    def allow(self, client: str) -> bool:
        now = time.monotonic()
        with self._lock:
            hits = [t for t in self._hits.get(client, []) if now - t < self.window]
            if len(hits) >= self.max_requests:
                self._hits[client] = hits
                return False
            hits.append(now)
            self._hits[client] = hits
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


# The live demo is public, and Muse Spark calls spend Meta Model API credits.
AGENT_CAP = DailyCap("Muse Spark agent", limit=200)
AGENT_RATE = RateLimiter(max_requests=10, window_seconds=10 * 60)


def cache_key(path: str, params: dict[str, Any]) -> str:
    return path + "?" + "&".join(f"{k}={params[k]}" for k in sorted(params) if k != "api_key")
