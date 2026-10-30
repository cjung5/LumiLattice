"""OpenAlex literature search (open scholarly metadata, CC0).

https://docs.openalex.org — only metadata is used; full text access depends on each paper.
"""

from typing import Any

import httpx

from app.models.evidence import Provenance
from app.models.materials import PaperEvidence
from app.tools.registry import UpstreamError
from app.tools.usage import (
    OPENALEX_CACHE,
    OPENALEX_CAP,
    OPENALEX_MIN_REMAINING_USD,
    DailyCap,
    ResponseCache,
    cache_key,
)

OPENALEX_URL = "https://api.openalex.org"
SELECT = (
    "id,doi,display_name,publication_year,authorships,primary_location,open_access,cited_by_count"
)
MAX_AUTHORS = 3


class OpenAlexClient:
    name = "OpenAlex"

    def __init__(
        self,
        api_key: str | None = None,
        transport: httpx.BaseTransport | None = None,
        cache: ResponseCache = OPENALEX_CACHE,
        cap: DailyCap = OPENALEX_CAP,
    ):
        self._api_key = api_key
        self._http = httpx.Client(base_url=OPENALEX_URL, timeout=20, transport=transport)
        self._cache = cache
        self._cap = cap

    def close(self) -> None:
        self._http.close()

    def search(self, query: str, limit: int = 5) -> list[PaperEvidence]:
        params: dict[str, Any] = {"search": query, "per_page": limit, "select": SELECT}
        key = cache_key("/works", params)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        if self._api_key:
            params["api_key"] = self._api_key
        self._cap.take()
        try:
            response = self._http.get("/works", params=params)
        except httpx.HTTPError as exc:
            raise UpstreamError(f"OpenAlex request failed: {exc}") from exc
        self._check_free_budget(response)
        if response.status_code == 429:
            raise UpstreamError("OpenAlex free daily budget is used up. It resets at 00:00 UTC.")
        if response.status_code >= 400:
            raise UpstreamError(f"OpenAlex error {response.status_code}: {response.text[:200]}")
        papers = [to_evidence(work) for work in response.json().get("results", [])]
        self._cache.put(key, papers)
        return papers

    def _check_free_budget(self, response: httpx.Response) -> None:
        """Stop for the day before the free budget runs out (header: x-ratelimit-remaining-usd)."""
        remaining = response.headers.get("x-ratelimit-remaining-usd")
        try:
            if remaining is not None and float(remaining) < OPENALEX_MIN_REMAINING_USD:
                self._cap.exhaust()
        except ValueError:
            pass


def to_evidence(work: dict[str, Any]) -> PaperEvidence:
    authors = [
        a["author"]["display_name"]
        for a in (work.get("authorships") or [])[:MAX_AUTHORS]
        if a.get("author", {}).get("display_name")
    ]
    location = work.get("primary_location") or {}
    open_access = work.get("open_access") or {}
    doi = work.get("doi")
    return PaperEvidence(
        title=work.get("display_name") or "(untitled)",
        authors=authors,
        year=work.get("publication_year"),
        venue=(location.get("source") or {}).get("display_name"),
        doi=doi.removeprefix("https://doi.org/") if doi else None,
        url=doi or location.get("landing_page_url"),
        cited_by_count=work.get("cited_by_count"),
        open_access=bool(open_access.get("is_oa")),
        open_access_url=open_access.get("oa_url"),
        provenance=Provenance(source="OpenAlex", reference=work.get("id")),
        sources=["OpenAlex"],
    )
