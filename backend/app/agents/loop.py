"""Tool-calling loop on the Meta Model API Responses endpoint.

Responses is the endpoint Meta recommends for agents: with previous_response_id the
server keeps the model's reasoning between turns. `tools` does not carry over across
previous_response_id, so it is sent again on every request.
https://dev.meta.ai/docs/tool-calling
"""

import json
import time
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from openai import BadRequestError

from app.tools.registry import ToolRegistry

CHAIN_RETRY_SECONDS = (2.0, 4.0)

LANGUAGES = {
    "en": "English",
    "ko": "Korean",
    "zh-Hans": "Simplified Chinese",
    "ja": "Japanese",
    "es": "Spanish",
    "de": "German",
}

# Guided mode: the reader may be new to the field, so the words change. The rules on numbers do not.
Audience = Literal["beginner", "expert"]
BEGINNER_NOTE = (
    "The reader is new to materials science. Use short, everyday sentences. Explain each "
    "technical term the first time you use it, and say what each number means for AR glasses "
    "(does it bend light enough, does it stay clear). Keep the answer under about 150 words. "
    "Do not leave out uncertainty."
)

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


def create_chained(client: ResponsesClient, **request: Any) -> Any:
    """Meta can need a few seconds to save a response, and until then a request that refers to it
    gets a 400. Meta's advice is to retry once or twice with a short wait.
    https://dev.meta.ai/docs/protocols/responses (Persistence guarantees)
    """
    for delay in CHAIN_RETRY_SECONDS:
        try:
            return client.responses.create(**request)
        except BadRequestError as exc:
            if "referenced response" not in str(exc):
                raise
            time.sleep(delay)
    return client.responses.create(**request)


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
        response = create_chained(
            client,
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
        response = create_chained(
            client,
            model=model,
            input=outputs,
            previous_response_id=response.id,
            tools=tools,
        )

    raise AgentStepLimitReached(f"Agent did not finish within {max_steps} tool steps.")
