"""Deterministic tools the agent can call.

The model never produces scientific numbers itself: it asks for a tool, the arguments
are validated here, and the tool result (with provenance) goes back to the model.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError


class ToolError(Exception):
    """An expected failure the model should see and can recover from (e.g. bad formula)."""


class UpstreamError(ToolError):
    """An external data source (Materials Project, OpenAlex) failed or refused the request."""


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    args_model: type[BaseModel]
    handler: Callable[[BaseModel], dict[str, Any]]

    def schema(self) -> dict[str, Any]:
        """Function tool definition in Responses API format (flat, not nested)."""
        parameters = self.args_model.model_json_schema()
        parameters.pop("title", None)
        parameters["additionalProperties"] = False
        return {
            "type": "function",
            "name": self.name,
            "description": self.description,
            "parameters": parameters,
        }


class ToolRegistry:
    def __init__(self, tools: list[Tool]):
        self._tools = {tool.name: tool for tool in tools}

    def schemas(self) -> list[dict[str, Any]]:
        return [tool.schema() for tool in self._tools.values()]

    def execute(self, name: str, arguments: str) -> dict[str, Any]:
        """Run one tool call. Errors are returned as data so the model can correct itself."""
        tool = self._tools.get(name)
        if tool is None:
            return {"error": "unknown_tool", "detail": f"No tool named {name!r}."}
        try:
            args = tool.args_model.model_validate_json(arguments or "{}")
        except ValidationError as exc:
            return {
                "error": "invalid_arguments",
                "detail": json.loads(exc.json(include_url=False)),
            }
        try:
            return tool.handler(args)
        except ToolError as exc:
            return {"error": "tool_error", "detail": str(exc)}
