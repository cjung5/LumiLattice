import json
from types import SimpleNamespace

import pytest

from app.agents.loop import AgentStepLimitReached, run_agent
from app.tools.composition import COMPOSITION_TOOL
from app.tools.registry import ToolRegistry

REGISTRY = ToolRegistry([COMPOSITION_TOOL])


def function_call(call_id: str, formula: str) -> SimpleNamespace:
    return SimpleNamespace(
        type="function_call",
        name="composition_info",
        arguments=json.dumps({"formula": formula}),
        call_id=call_id,
    )


class FakeResponses:
    """Plays back scripted Responses API outputs and records each request."""

    def __init__(self, outputs: list[list[SimpleNamespace]], final_text: str = "done"):
        self.outputs = outputs
        self.final_text = final_text
        self.requests: list[dict] = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        step = len(self.requests)
        output = self.outputs[step - 1] if step <= len(self.outputs) else []
        return SimpleNamespace(
            id=f"resp_{step}",
            output=output,
            output_text="" if output else self.final_text,
        )


def test_loop_runs_tool_and_returns_final_text():
    fake = FakeResponses([[function_call("call_1", "SrTiO3")]], final_text="Sr2+ Ti4+ O2-")
    client = SimpleNamespace(responses=fake)

    result = run_agent(client, "muse-spark-1.3", REGISTRY, "Oxidation states of SrTiO3?", "ko")

    assert result.output_text == "Sr2+ Ti4+ O2-"
    assert result.response_id == "resp_2"
    assert [r.name for r in result.tool_calls] == ["composition_info"]
    assert result.tool_calls[0].output["reduced_formula"] == "SrTiO3"

    first, second = fake.requests
    assert "Korean" in first["input"][0]["content"]
    assert second["previous_response_id"] == "resp_1"
    assert second["tools"] == first["tools"]  # tools do not carry over; resent each turn
    sent = second["input"][0]
    assert sent["type"] == "function_call_output" and sent["call_id"] == "call_1"


def test_parallel_tool_calls_are_all_answered():
    fake = FakeResponses([[function_call("a", "SrTiO3"), function_call("b", "TiO2")]])
    client = SimpleNamespace(responses=fake)

    result = run_agent(client, "muse-spark-1.3", REGISTRY, "Compare SrTiO3 and TiO2")

    assert len(result.tool_calls) == 2
    assert [o["call_id"] for o in fake.requests[1]["input"]] == ["a", "b"]


def test_step_limit():
    looping = [[function_call(f"c{i}", "SrTiO3")] for i in range(10)]
    client = SimpleNamespace(responses=FakeResponses(looping))

    with pytest.raises(AgentStepLimitReached):
        run_agent(client, "muse-spark-1.3", REGISTRY, "loop", max_steps=3)
