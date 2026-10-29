import httpx
import pytest

from app.tools.materials import MaterialsProjectClient, parse_query
from app.tools.registry import ToolError, UpstreamError

# Fixture values for tests only; they are not real Materials Project data.
SUMMARY_DOC = {
    "material_id": "mp-5229",
    "formula_pretty": "SrTiO3",
    "symmetry": {"crystal_system": "Cubic", "symbol": "Pm-3m", "number": 221},
    "nsites": 5,
    "band_gap": 1.8,
    "energy_above_hull": 0.0,
    "is_stable": True,
    "theoretical": False,
    "n": 2.3,
    "e_electronic": 5.29,
    "database_IDs": {"icsd": ["icsd-1", "icsd-2"]},
}


def mp_client(handler) -> MaterialsProjectClient:
    return MaterialsProjectClient("test-key", transport=httpx.MockTransport(handler))


def test_search_sends_key_and_filters_and_tags_values():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["key"] = request.headers["X-API-KEY"]
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json={"data": [SUMMARY_DOC]})

    [record] = mp_client(handler).search(formula="SrTiO3", band_gap_min=2.5)

    assert seen["key"] == "test-key"
    assert seen["params"]["formula"] == "SrTiO3"
    assert seen["params"]["band_gap_min"] == "2.5"
    assert record.material_id == "mp-5229"
    assert record.spacegroup == "Pm-3m"
    assert record.theoretical is False
    assert record.icsd_ids == ["icsd-1", "icsd-2"]
    assert record.band_gap.status == "DFT-computed"
    assert record.band_gap.units == "eV"
    assert record.refractive_index.status == "DFT-computed"
    assert "not n(550 nm)" in record.refractive_index.conditions
    assert record.url.endswith("/mp-5229")


def test_missing_refractive_index_is_unknown():
    doc = {**SUMMARY_DOC, "n": None, "band_gap": None}
    client = mp_client(lambda r: httpx.Response(200, json={"data": [doc]}))

    [record] = client.search(formula="SrTiO3")

    assert record.refractive_index.status == "Unknown"
    assert record.refractive_index.value is None
    assert record.band_gap.status == "Unknown"


def test_bad_key_is_upstream_error():
    client = mp_client(lambda r: httpx.Response(403, json={"detail": "bad key"}))

    with pytest.raises(UpstreamError):
        client.search(formula="SrTiO3")


def test_search_needs_a_filter():
    with pytest.raises(ToolError):
        mp_client(lambda r: httpx.Response(200, json={"data": []})).search(band_gap_min=3)


def test_get_structure(srtio3):
    client = mp_client(
        lambda r: httpx.Response(
            200, json={"data": [{"material_id": "mp-5229", "structure": srtio3.as_dict()}]}
        )
    )

    structure = client.get_structure("mp-5229")

    assert structure.composition.reduced_formula == "SrTiO3"
    assert len(structure) == 5


def test_get_structure_rejects_bad_id():
    with pytest.raises(ToolError):
        mp_client(lambda r: httpx.Response(200, json={"data": []})).get_structure("../x")


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("mp-5229", {"material_ids": ["mp-5229"]}),
        ("Sr, Ti,O", {"elements": ["Sr", "Ti", "O"]}),
        ("SrTiO3", {"formula": "SrTiO3"}),
        ("*TiO3", {"formula": "*TiO3"}),
    ],
)
def test_parse_query(query, expected):
    assert parse_query(query) == expected
