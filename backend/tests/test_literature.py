import httpx
import pytest

from app.tools.literature import OpenAlexClient
from app.tools.registry import UpstreamError

# Shape follows the OpenAlex works API; values are test fixtures.
WORK = {
    "id": "https://openalex.org/W123",
    "doi": "https://doi.org/10.1000/example",
    "display_name": "Optical constants of a perovskite oxide",
    "publication_year": 2020,
    "authorships": [{"author": {"display_name": f"Author {i}"}} for i in range(5)],
    "primary_location": {"source": {"display_name": "Example Journal"}},
    "open_access": {"is_oa": True, "oa_url": "https://example.org/paper.pdf"},
    "cited_by_count": 42,
}


def test_search_maps_metadata_and_sends_key():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(request.url.params)
        return httpx.Response(200, json={"results": [WORK]})

    client = OpenAlexClient("oa-key", transport=httpx.MockTransport(handler))
    [paper] = client.search("SrTiO3 refractive index", limit=3)

    assert seen["search"] == "SrTiO3 refractive index"
    assert seen["per_page"] == "3"
    assert seen["api_key"] == "oa-key"
    assert paper.authors == ["Author 0", "Author 1", "Author 2"]
    assert paper.doi == "10.1000/example"
    assert paper.url == "https://doi.org/10.1000/example"
    assert paper.venue == "Example Journal"
    assert paper.open_access is True
    assert paper.provenance.source == "OpenAlex"


def test_no_key_is_not_sent():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(request.url.params)
        return httpx.Response(200, json={"results": []})

    OpenAlexClient(None, transport=httpx.MockTransport(handler)).search("TiO2")

    assert "api_key" not in seen


def test_budget_exhausted():
    client = OpenAlexClient(transport=httpx.MockTransport(lambda r: httpx.Response(429)))

    with pytest.raises(UpstreamError, match="OPENALEX_API_KEY"):
        client.search("TiO2")
