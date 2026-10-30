"""Crossref and arXiv clients, and the merged literature search (OpenAlex + Crossref + arXiv).

All three are public and free. Only metadata is used. Results with the same DOI (or the
same title) are merged, and each paper lists every source that returned it.
"""

import html
import re
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Protocol

import httpx

from app.models.evidence import Provenance
from app.models.materials import LiteratureResult, PaperEvidence
from app.tools.registry import ToolError, UpstreamError
from app.tools.usage import (
    ARXIV_CACHE,
    ARXIV_CAP,
    ARXIV_THROTTLE,
    CROSSREF_CACHE,
    CROSSREF_CAP,
    CROSSREF_THROTTLE,
    DailyCap,
    ResponseCache,
    Throttle,
    cache_key,
)

USER_AGENT = "LumiLattice/0.1 (https://github.com/cjung5/LumiLattice)"
MAX_AUTHORS = 3
ATOM = "{http://www.w3.org/2005/Atom}"
ARXIV_NS = "{http://arxiv.org/schemas/atom}"


class LiteratureSource(Protocol):
    name: str

    def search(self, query: str, limit: int = 5) -> list[PaperEvidence]: ...

    def close(self) -> None: ...


def _plain(text: str | None) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", text or ""))).strip()


BACKOFF_SECONDS = 600
# Source name -> monotonic time until which it is skipped (shared by all requests).
_paused_until: dict[str, float] = {}


class _PoliteClient:
    name = ""

    def __init__(
        self,
        base_url: str,
        transport: httpx.BaseTransport | None,
        cache: ResponseCache,
        cap: DailyCap,
        throttle: Throttle,
        timeout: float,
    ):
        self._http = httpx.Client(
            base_url=base_url,
            headers={"User-Agent": USER_AGENT},
            timeout=timeout,
            transport=transport,
            follow_redirects=True,
        )
        self._cache, self._cap, self._throttle = cache, cap, throttle

    def close(self) -> None:
        self._http.close()

    def _get(self, path: str, params: dict[str, Any]) -> httpx.Response | Any:
        key = cache_key(path, params)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        wait = _paused_until.get(self.name, 0) - time.monotonic()
        if wait > 0:
            # After a rate limit or timeout, skip this source for a while instead of making
            # every search wait for it.
            raise UpstreamError(
                f"{self.name} paused after a rate limit or timeout ({wait / 60:.0f} min left)."
            )
        self._cap.take()
        self._throttle.wait()
        try:
            response = self._http.get(path, params=params)
        except httpx.TimeoutException as exc:
            _paused_until[self.name] = time.monotonic() + BACKOFF_SECONDS
            raise UpstreamError(f"{self.name} did not answer in time.") from exc
        except httpx.HTTPError as exc:
            raise UpstreamError(f"{self.name} request failed: {exc}") from exc
        if response.status_code == 429:
            _paused_until[self.name] = time.monotonic() + BACKOFF_SECONDS
            raise UpstreamError(f"{self.name} rate limit reached; try again later.")
        if response.status_code >= 400:
            raise UpstreamError(f"{self.name} error {response.status_code}")
        return key, response


class CrossrefClient(_PoliteClient):
    name = "Crossref"
    SELECT = "DOI,title,author,issued,container-title,is-referenced-by-count,URL"

    def __init__(
        self,
        transport: httpx.BaseTransport | None = None,
        cache: ResponseCache = CROSSREF_CACHE,
        cap: DailyCap = CROSSREF_CAP,
        throttle: Throttle = CROSSREF_THROTTLE,
    ):
        super().__init__("https://api.crossref.org", transport, cache, cap, throttle, 20)

    def search(self, query: str, limit: int = 5) -> list[PaperEvidence]:
        result = self._get("/works", {"query": query, "rows": limit, "select": self.SELECT})
        if isinstance(result, list):
            return result
        key, response = result
        papers = [crossref_to_evidence(item) for item in response.json()["message"]["items"]]
        self._cache.put(key, papers)
        return papers


def crossref_to_evidence(item: dict[str, Any]) -> PaperEvidence:
    authors = [
        " ".join(p for p in (a.get("given"), a.get("family")) if p)
        for a in (item.get("author") or [])[:MAX_AUTHORS]
    ]
    issued = (item.get("issued") or {}).get("date-parts") or [[None]]
    doi = item.get("DOI")
    return PaperEvidence(
        title=_plain((item.get("title") or ["(untitled)"])[0]),
        authors=[a for a in authors if a],
        year=issued[0][0] if issued and issued[0] else None,
        venue=_plain((item.get("container-title") or [None])[0]) or None,
        doi=doi.lower() if doi else None,
        url=item.get("URL") or (f"https://doi.org/{doi}" if doi else None),
        cited_by_count=item.get("is-referenced-by-count"),
        open_access=None,
        open_access_url=None,
        provenance=Provenance(source="Crossref", reference=doi),
        sources=["Crossref"],
    )


class ArxivClient(_PoliteClient):
    name = "arXiv"

    def __init__(
        self,
        transport: httpx.BaseTransport | None = None,
        cache: ResponseCache = ARXIV_CACHE,
        cap: DailyCap = ARXIV_CAP,
        throttle: Throttle = ARXIV_THROTTLE,
    ):
        super().__init__("https://export.arxiv.org", transport, cache, cap, throttle, 8)

    def search(self, query: str, limit: int = 5) -> list[PaperEvidence]:
        words = re.findall(r"[A-Za-z0-9]+", query)[:6]
        if not words:
            return []
        params = {
            "search_query": " AND ".join(f"all:{w}" for w in words),
            "max_results": limit,
            "sortBy": "relevance",
        }
        result = self._get("/api/query", params)
        if isinstance(result, list):
            return result
        key, response = result
        try:
            papers = parse_arxiv(response.text)
        except ET.ParseError as exc:
            raise UpstreamError(f"arXiv returned unreadable data: {exc}") from exc
        self._cache.put(key, papers)
        return papers


def parse_arxiv(feed: str) -> list[PaperEvidence]:
    papers = []
    for entry in ET.fromstring(feed).iter(f"{ATOM}entry"):
        abs_url = (entry.findtext(f"{ATOM}id") or "").strip()
        arxiv_id = abs_url.rsplit("/abs/", 1)[-1] if "/abs/" in abs_url else None
        doi = entry.findtext(f"{ARXIV_NS}doi")
        published = entry.findtext(f"{ATOM}published") or ""
        pdf = next(
            (link.get("href") for link in entry.iter(f"{ATOM}link") if link.get("title") == "pdf"),
            None,
        )
        authors = [
            _plain(a.findtext(f"{ATOM}name")) for a in entry.findall(f"{ATOM}author")[:MAX_AUTHORS]
        ]
        papers.append(
            PaperEvidence(
                title=_plain(entry.findtext(f"{ATOM}title")) or "(untitled)",
                authors=[a for a in authors if a],
                year=int(published[:4]) if published[:4].isdigit() else None,
                venue=_plain(entry.findtext(f"{ARXIV_NS}journal_ref")) or "arXiv preprint",
                doi=doi.strip().lower() if doi else None,
                url=abs_url or None,
                cited_by_count=None,
                open_access=True,
                open_access_url=pdf,
                provenance=Provenance(source="arXiv", reference=arxiv_id),
                sources=["arXiv"],
            )
        )
    return papers


def _title_key(title: str) -> str:
    return re.sub(r"[^a-z0-9]", "", title.lower())[:120]


def merge_papers(groups: list[list[PaperEvidence]]) -> list[PaperEvidence]:
    """Merge results by DOI, then by title; keep the first source's order."""
    merged: list[PaperEvidence] = []
    index: dict[str, int] = {}
    for papers in groups:
        for paper in papers:
            keys = [
                k
                for k in (paper.doi and f"doi:{paper.doi.lower()}", f"t:{_title_key(paper.title)}")
                if k
            ]
            hit = next((index[k] for k in keys if k in index), None)
            source = paper.provenance.source
            if hit is None:
                merged.append(paper.model_copy(update={"sources": [source]}))
                hit = len(merged) - 1
            else:
                old = merged[hit]
                merged[hit] = old.model_copy(
                    update={
                        "sources": [*old.sources, source]
                        if source not in old.sources
                        else old.sources,
                        "doi": old.doi or paper.doi,
                        "url": old.url or paper.url,
                        "venue": old.venue or paper.venue,
                        "year": old.year or paper.year,
                        "authors": old.authors or paper.authors,
                        "cited_by_count": max(
                            (
                                c
                                for c in (old.cited_by_count, paper.cited_by_count)
                                if c is not None
                            ),
                            default=None,
                        ),
                        "open_access": old.open_access or paper.open_access,
                        "open_access_url": old.open_access_url or paper.open_access_url,
                    }
                )
            for k in keys:
                index.setdefault(k, hit)
    return merged


class LiteratureSearch:
    """Searches every source in parallel; a failing source does not block the others."""

    def __init__(self, sources: list[LiteratureSource]):
        self.sources = sources

    def close(self) -> None:
        for source in self.sources:
            source.close()

    def search(self, query: str, limit: int = 5) -> LiteratureResult:
        query = query.strip()
        if len(query) < 2:
            raise ToolError("Give at least 2 characters to search.")

        def run(source: LiteratureSource) -> tuple[list[PaperEvidence], str]:
            try:
                return source.search(query, limit), "ok"
            except ToolError as exc:
                return [], str(exc)

        with ThreadPoolExecutor(max_workers=len(self.sources)) as pool:
            results = list(pool.map(run, self.sources))
        return LiteratureResult(
            papers=merge_papers([papers for papers, _ in results]),
            source_status={
                s.name: status for s, (_, status) in zip(self.sources, results, strict=True)
            },
        )
