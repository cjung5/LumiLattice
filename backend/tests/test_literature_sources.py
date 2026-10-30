import httpx

from app.models.evidence import Provenance
from app.models.materials import PaperEvidence
from app.tools.literature_sources import (
    ArxivClient,
    CrossrefClient,
    LiteratureSearch,
    merge_papers,
    parse_arxiv,
)
from app.tools.registry import UpstreamError
from app.tools.usage import DailyCap, ResponseCache, Throttle

# Shapes follow the Crossref works API and the arXiv Atom feed; values are fixtures.
CROSSREF_ITEM = {
    "DOI": "10.1000/ABC",
    "title": ["Refractive index of <i>SrTiO<sub>3</sub></i>"],
    "author": [{"given": "A.", "family": "Author"}, {"family": "Second"}],
    "issued": {"date-parts": [[1977, 1]]},
    "container-title": ["Example Journal"],
    "is-referenced-by-count": 12,
    "URL": "https://doi.org/10.1000/abc",
}

ARXIV_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2101.00001v1</id>
    <published>2021-01-01T00:00:00Z</published>
    <title>  Optical constants of
      perovskite oxides </title>
    <author><name>First Author</name></author>
    <author><name>Second Author</name></author>
    <arxiv:doi>10.1000/ABC</arxiv:doi>
    <link title="pdf" href="http://arxiv.org/pdf/2101.00001v1" rel="related"/>
  </entry>
</feed>"""


def fast(cls, handler):
    return cls(
        transport=httpx.MockTransport(handler),
        cache=ResponseCache(),
        cap=DailyCap("t", 10),
        throttle=Throttle(0),
    )


def test_crossref_parsing_and_polite_user_agent():
    seen = {}

    def handler(request):
        seen["ua"] = request.headers["user-agent"]
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json={"message": {"items": [CROSSREF_ITEM]}})

    [paper] = fast(CrossrefClient, handler).search("SrTiO3 refractive index", 3)

    assert "LumiLattice" in seen["ua"] and "mailto" not in seen["ua"]  # no personal email sent
    assert seen["params"]["rows"] == "3"
    assert paper.title == "Refractive index of SrTiO3"  # HTML tags removed
    assert paper.doi == "10.1000/abc"
    assert paper.authors == ["A. Author", "Second"]
    assert paper.open_access is None  # Crossref does not say
    assert paper.sources == ["Crossref"]


def test_arxiv_parsing():
    [paper] = parse_arxiv(ARXIV_FEED)

    assert paper.title == "Optical constants of perovskite oxides"
    assert paper.year == 2021
    assert paper.provenance.reference == "2101.00001v1"
    assert paper.open_access is True
    assert paper.open_access_url.endswith("2101.00001v1")
    assert paper.venue == "arXiv preprint"


def test_arxiv_query_uses_words_only():
    seen = {}

    def handler(request):
        seen.update(request.url.params)
        return httpx.Response(200, text=ARXIV_FEED)

    fast(ArxivClient, handler).search("SrTiO3 (refractive) index!")

    assert seen["search_query"] == "all:SrTiO3 AND all:refractive AND all:index"


def paper(source: str, title: str, doi: str | None, cited: int | None = None) -> PaperEvidence:
    return PaperEvidence(
        title=title,
        authors=[],
        year=None,
        venue=None,
        doi=doi,
        url=None,
        cited_by_count=cited,
        open_access=None,
        open_access_url=None,
        provenance=Provenance(source=source),
        sources=[source],
    )


def test_merge_by_doi_then_title():
    merged = merge_papers(
        [
            [paper("OpenAlex", "Paper A", "10.1/a", 5), paper("OpenAlex", "Paper B", None)],
            [paper("Crossref", "paper a", "10.1/A", 9), paper("Crossref", "Paper C", "10.1/c")],
            [paper("arXiv", "Paper   B", None)],
        ]
    )

    assert [m.title for m in merged] == ["Paper A", "Paper B", "Paper C"]
    assert merged[0].sources == ["OpenAlex", "Crossref"]
    assert merged[0].cited_by_count == 9
    assert merged[1].sources == ["OpenAlex", "arXiv"]


class Failing:
    name = "arXiv"

    def search(self, query, limit=5):
        raise UpstreamError("arXiv rate limit reached; try again later.")

    def close(self):
        pass


class Working:
    name = "Crossref"

    def search(self, query, limit=5):
        return [paper("Crossref", "Paper C", "10.1/c")]

    def close(self):
        pass


def test_one_failing_source_does_not_block_others():
    result = LiteratureSearch([Working(), Failing()]).search("SrTiO3")

    assert [p.title for p in result.papers] == ["Paper C"]
    assert result.source_status["Crossref"] == "ok"
    assert "rate limit" in result.source_status["arXiv"]


def test_rate_limited_source_is_paused(monkeypatch):
    from app.tools import literature_sources

    monkeypatch.setattr(literature_sources, "_paused_until", {})
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(429)

    client = fast(ArxivClient, handler)
    for _ in range(3):
        try:
            client.search(f"query {len(calls)}")
        except UpstreamError:
            pass

    assert len(calls) == 1  # later searches skip arXiv instead of waiting for it
