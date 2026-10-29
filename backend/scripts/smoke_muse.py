"""Live check: Muse Spark calls a real scientific tool and answers from its result.

Run from backend/ after you put MODEL_API_KEY in backend/.env:
    uv run python -m scripts.smoke_muse
"""

import json
import sys

from app.agents.loop import run_agent
from app.agents.muse import ModelAPIKeyMissing, create_client
from app.config import get_settings
from app.tools.composition import COMPOSITION_TOOL
from app.tools.registry import ToolRegistry


def main() -> int:
    settings = get_settings()
    try:
        client = create_client(settings)
    except ModelAPIKeyMissing as exc:
        print(exc)
        return 1

    result = run_agent(
        client,
        settings.muse_model,
        ToolRegistry([COMPOSITION_TOOL]),
        "What are the likely oxidation states in SrTiO3, and is it charge balanced?",
    )
    for call in result.tool_calls:
        print(f"tool call: {call.name}({call.arguments})")
        print(json.dumps(call.output, indent=2))
    print("\nanswer:", result.output_text)

    if not result.tool_calls:
        print("FAIL: the model answered without calling the tool.")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
