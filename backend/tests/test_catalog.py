import json

import httpx

from app.tools.catalog import build_registry
from app.tools.literature import OpenAlexClient
from app.tools.literature_sources import LiteratureSearch


def offline_literature() -> LiteratureSearch:
    return LiteratureSearch(
        [
            OpenAlexClient(
                transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"results": []}))
            )
        ]
    )


def test_registry_exposes_agent_tools():
    names = [s["name"] for s in build_registry(None, offline_literature()).schemas()]

    assert names == [
        "composition_info",
        "create_candidate",
        "get_candidate",
        "score_against_goal",
        "get_optical_reference",
        "search_materials",
        "search_literature",
    ]


def test_search_materials_without_key_tells_model_to_report_unknown():
    registry = build_registry(None, offline_literature())

    result = registry.execute("search_materials", json.dumps({"formula": "SrTiO3"}))

    assert result["error"] == "tool_error"
    assert "unknown" in result["detail"]


def test_search_literature_tool():
    registry = build_registry(None, offline_literature())

    result = registry.execute("search_literature", json.dumps({"query": "TiO2 waveguide"}))

    assert result == {"count": 0, "results": [], "source_status": {"OpenAlex": "ok"}}
