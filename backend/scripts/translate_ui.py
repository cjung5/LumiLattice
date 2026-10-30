"""Translate the UI strings (frontend/messages/en.json) with Muse Spark.

Korean is written by hand; these languages are machine-translated and the UI says so.
The model must return the same keys (strict JSON schema), and every {placeholder}
must survive, or the language is rejected. Run from backend/:
    uv run python -m scripts.translate_ui            # all languages
    uv run python -m scripts.translate_ui ja de      # some languages
"""

import json
import re
import sys
from pathlib import Path
from typing import Any

from app.agents.muse import create_client
from app.config import get_settings

MESSAGES = Path(__file__).resolve().parents[2] / "frontend" / "messages"
LANGUAGES = {
    "zh-Hans": "Simplified Chinese",
    "ja": "Japanese",
    "es": "Spanish",
    "de": "German",
}
KEEP = (
    "LumiLattice, Muse Spark, Meta, Materials Project, COD, Crystallography Open Database, "
    "OpenAlex, Crossref, arXiv, JARVIS-DFT, refractiveindex.info, DFT, TBmBJ, OptB88vdW, CIF, "
    "ORCID, ICSD, Postgres, DATABASE_URL, MODEL_API_KEY, MP_API_KEY, chemical formulas such as "
    "SrTiO3, IDs such as mp-5229, units (eV, Å, nm), and symbols such as n, k, E above hull"
)
PROMPT = """Translate the user-interface strings of a materials-science research app from \
English to {language}.
Rules:
- Keep every key. Translate only the values.
- Keep every placeholder in braces exactly, e.g. {{count}}, {{id}}, {{host}}.
- Do not translate: {keep}.
- Use the short, neutral style of scientific software. Keep leading numbers like "1." and \
symbols like "+", "…", "→".
Return only the JSON object."""


def schema_for(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return {
            "type": "object",
            "properties": {k: schema_for(v) for k, v in value.items()},
            "required": list(value),
            "additionalProperties": False,
        }
    return {"type": "string"}


def flatten(value: Any, prefix: str = "") -> dict[str, str]:
    if isinstance(value, dict):
        out: dict[str, str] = {}
        for k, v in value.items():
            out.update(flatten(v, f"{prefix}{k}."))
        return out
    return {prefix.rstrip("."): value}


def problems(source: dict[str, Any], translated: dict[str, Any]) -> list[str]:
    src, out = flatten(source), flatten(translated)
    issues = [f"missing key {k}" for k in src if k not in out]
    issues += [f"extra key {k}" for k in out if k not in src]
    for key, text in src.items():
        if key in out and set(re.findall(r"\{\w+\}", text)) != set(
            re.findall(r"\{\w+\}", out[key])
        ):
            issues.append(f"placeholders changed in {key}")
    return issues


def translate(client: Any, model: str, source: dict[str, Any], language: str) -> dict[str, Any]:
    messages = [
        {"role": "system", "content": PROMPT.format(language=language, keep=KEEP)},
        {"role": "user", "content": json.dumps(source, ensure_ascii=False)},
    ]
    for _ in range(2):
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "ui_messages",
                    "schema": schema_for(source),
                    "strict": True,
                },
            },
            max_completion_tokens=20000,
        )
        content = response.choices[0].message.content or ""
        translated = json.loads(content)
        issues = problems(source, translated)
        if not issues:
            return translated
        messages += [
            {"role": "assistant", "content": content},
            {
                "role": "user",
                "content": "Fix these problems and return the full JSON: " + "; ".join(issues[:20]),
            },
        ]
    raise RuntimeError(f"{language}: {'; '.join(issues[:5])}")


def main(codes: list[str]) -> int:
    settings = get_settings()
    client = create_client(settings)
    source = json.loads((MESSAGES / "en.json").read_text())
    for code in codes or list(LANGUAGES):
        translated = translate(client, settings.muse_model, source, LANGUAGES[code])
        path = MESSAGES / f"{code}.json"
        path.write_text(json.dumps(translated, ensure_ascii=False, indent=2) + "\n")
        print(f"ok  {path.name}  ({len(flatten(translated))} strings, {settings.muse_model})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
