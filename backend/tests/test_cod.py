import httpx
import pytest
from fastapi.testclient import TestClient
from pymatgen.io.cif import CifWriter

from app.api.deps import get_cod_client
from app.main import app
from app.tools.cod import CodClient
from app.tools.registry import ToolError
from app.tools.usage import DailyCap, ResponseCache

# Shape follows the COD JSON search API; values are fixtures.
ROW = {
    "file": "1512124",
    "formula": "- O3 Sr Ti -",
    "sg": "P m -3 m",
    "sgNumber": "221",
    "a": "3.899",
    "b": "3.899",
    "c": "3.899",
    "year": "2011",
    "authors": "A. Author; B. Author",
    "title": "Example",
    "journal": "Example Journal",
    "doi": "10.1000/x",
}


def cod_client(handler) -> CodClient:
    return CodClient(httpx.MockTransport(handler), cache=ResponseCache(), cap=DailyCap("t", 10))


def test_search_uses_hill_formula():
    seen = {}

    def handler(request):
        seen.update(request.url.params)
        return httpx.Response(200, json=[ROW])

    [entry] = cod_client(handler).search("SrTiO3")

    assert seen["formula"] == "O3 Sr Ti"
    assert entry.cod_id == "1512124"
    assert entry.formula == "O3 Sr Ti"
    assert entry.spacegroup == "Pm-3m"
    assert entry.cell == (3.899, 3.899, 3.899)
    assert entry.url.endswith("/1512124.html")


def test_bad_cod_id():
    with pytest.raises(ToolError):
        cod_client(lambda r: httpx.Response(200)).get_cif("../etc")


def test_structure_endpoint_marks_cod_provenance(srtio3):
    cif = str(CifWriter(srtio3))
    app.dependency_overrides[get_cod_client] = lambda: cod_client(
        lambda r: httpx.Response(200, text=cif)
    )
    try:
        response = TestClient(app).get("/api/cod/1512124/structure")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["formula"] == "SrTiO3"
    assert body["provenance"]["source"] == "Crystallography Open Database"
    assert body["provenance"]["reference"] == "COD 1512124"


def test_a_dropped_connection_is_retried(monkeypatch):
    monkeypatch.setattr("app.tools.cod.RETRY_SECONDS", 0)
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            raise httpx.ConnectError("connection reset")
        return httpx.Response(200, json=[])

    client = CodClient(
        httpx.MockTransport(handler), cache=ResponseCache(), cap=DailyCap("t", limit=9)
    )
    assert client.search("SrTiO3") == []
    assert len(calls) == 2
