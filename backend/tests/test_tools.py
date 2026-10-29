import json

from app.tools.composition import COMPOSITION_TOOL
from app.tools.registry import ToolRegistry

REGISTRY = ToolRegistry([COMPOSITION_TOOL])


def test_composition_info_srtio3():
    result = REGISTRY.execute("composition_info", json.dumps({"formula": "SrTiO3"}))

    assert result["reduced_formula"] == "SrTiO3"
    assert result["elements"] == ["Sr", "Ti", "O"]
    assert result["atomic_fractions"] == {"Sr": 0.2, "Ti": 0.2, "O": 0.6}
    assert result["oxidation_state_guesses"][0] == {"Sr": 2.0, "Ti": 4.0, "O": -2.0}
    assert result["charge_balanced"] is True
    assert result["provenance"]["source"] == "pymatgen"


def test_invalid_formula_is_returned_as_tool_error():
    result = REGISTRY.execute("composition_info", json.dumps({"formula": "Xx2Qq"}))

    assert result["error"] == "tool_error"


def test_invalid_arguments_are_returned_as_data():
    result = REGISTRY.execute("composition_info", json.dumps({"formula": ""}))

    assert result["error"] == "invalid_arguments"


def test_unknown_tool():
    assert REGISTRY.execute("does_not_exist", "{}")["error"] == "unknown_tool"


def test_schema_is_flat_responses_format():
    schema = COMPOSITION_TOOL.schema()

    assert schema["type"] == "function"
    assert schema["name"] == "composition_info"
    assert schema["parameters"]["required"] == ["formula"]
    assert schema["parameters"]["additionalProperties"] is False
