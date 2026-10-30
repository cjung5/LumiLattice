"""Tool-calling loop on the Meta Model API Responses endpoint.

Responses is the endpoint Meta recommends for agents: with previous_response_id the
server keeps the model's reasoning between turns. `tools` does not carry over across
previous_response_id, so it is sent again on every request.
https://dev.meta.ai/docs/tool-calling
"""

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.tools.registry import ToolRegistry

LANGUAGES = {
    "en": "English",
    "ko": "Korean",
    "zh-Hans": "Simplified Chinese",
    "ja": "Japanese",
    "es": "Spanish",
    "de": "German",
}

SYSTEM_PROMPT = """You are LumiLattice, a research agent that helps researchers explore \
optoelectronic materials for AR waveguides.
- Use the tools for every number and every chemical fact. Never invent numerical values.
- If no tool can answer, say that the value is unknown.
- The researcher steers the work. When they give feedback on a candidate, revise that \
candidate with create_candidate and host_candidate_id, then explain which checks changed and why.
- Create at most 3 candidates per request. Prefer fractions 1, 1/2, 1/3, or 1/4.
- Structural checks are not synthesis predictions; atoms are not relaxed. Say so when it matters.
- Respond in {language}. Keep chemical formulas, units, paper titles, and data values unchanged."""


class ResponsesClient(Protocol):
    """The part of the OpenAI SDK client the loop uses (lets tests pass a fake)."""

    @property
    def responses(self) -> Any: ...


@dataclass
class ToolCallRecord:
    name: str
    arguments: str
    output: dict[str, Any]


@dataclass
class AgentResult:
    output_text: str
    response_id: str
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    completed: bool = True


class AgentStepLimitReached(RuntimeError):
    pass


def run_agent(
    client: ResponsesClient,
    model: str,
    registry: ToolRegistry,
    user_message: str,
    locale: str = "en",
    max_steps: int = 8,
    previous_response_id: str | None = None,
) -> AgentResult:
    """Run one researcher turn. With previous_response_id the server keeps the conversation."""
    tools = registry.schemas()
    records: list[ToolCallRecord] = []

    if previous_response_id is None:
        system = SYSTEM_PROMPT.format(language=LANGUAGES.get(locale, "English"))
        response = client.responses.create(
            model=model,
            input=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_message},
            ],
            tools=tools,
        )
    else:
        response = client.responses.create(
            model=model,
            input=[{"role": "user", "content": user_message}],
            previous_response_id=previous_response_id,
            tools=tools,
        )
    for _ in range(max_steps):
        calls = [item for item in response.output if item.type == "function_call"]
        if not calls:
            return AgentResult(response.output_text, response.id, records)

        outputs = []
        for call in calls:
            result = registry.execute(call.name, call.arguments)
            records.append(ToolCallRecord(call.name, call.arguments, result))
            outputs.append(
                {
                    "type": "function_call_output",
                    "call_id": call.call_id,
                    "output": json.dumps(result),
                }
            )
        response = client.responses.create(
            model=model,
            input=outputs,
            previous_response_id=response.id,
            tools=tools,
        )

    raise AgentStepLimitReached(f"Agent did not finish within {max_steps} tool steps.")
