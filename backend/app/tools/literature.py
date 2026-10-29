"""OpenAlex literature search (open scholarly metadata, CC0).

https://docs.openalex.org — only metadata is used; full text access depends on each paper.
"""

from typing import Any

import httpx

from app.models.evidence import Provenance
from app.models.materials import PaperEvidence
from app.tools.registry import UpstreamError

OPENALEX_URL = "https://api.openalex.org"
SELECT = (
    "id,doi,display_name,publication_year,authorships,primary_location,open_access,cited_by_count"
)
MAX_AUTHORS = 3


class OpenAlexClient:
    def __init__(self, api_key: str | None = None, transport: httpx.BaseTransport | None = None):
        self._api_key = api_key
        self._http = httpx.Client(base_url=OPENALEX_URL, timeout=20, transport=transport)

    def close(self) -> None:
        self._http.close()

    def search(self, query: str, limit: int = 5) -> list[PaperEvidence]:
        params: dict[str, Any] = {"search": query, "per_page": limit, "select": SELECT}
        if self._api_key:
            params["api_key"] = self._api_key
        try:
            response = self._http.get("/works", params=params)
        except httpx.HTTPError as exc:
            raise UpstreamError(f"OpenAlex request failed: {exc}") from exc
        if response.status_code == 429:
            raise UpstreamError("OpenAlex daily budget is used up. Add OPENALEX_API_KEY.")
        if response.status_code >= 400:
            raise UpstreamError(f"OpenAlex error {response.status_code}: {response.text[:200]}")
        return [to_evidence(work) for work in response.json().get("results", [])]


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
    )
