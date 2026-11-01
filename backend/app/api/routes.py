import hashlib
import secrets
from dataclasses import asdict
from typing import Annotated, Any, Literal

import httpx
from fastapi import APIRouter, Header, HTTPException, Request
from openai import APIError
from pydantic import BaseModel, Field, field_validator

from app.agents.loop import BEGINNER_NOTE, AgentStepLimitReached, Audience, run_agent
from app.agents.muse import ModelAPIKeyMissing, create_client
from app.api.deps import LiteratureDep, OptionalMPDep, SettingsDep, client_id
from app.models.candidates import DecisionKind
from app.storage.memory import get_store
from app.storage.visits import UNKNOWN, get_visits
from app.tools.catalog import build_registry
from app.tools.goals import Goal
from app.tools.reference_db import get_reference_db
from app.tools.registry import UpstreamError
from app.tools.relaxation import relaxation_available
from app.tools.usage import AGENT_CAP, AGENT_RATE

router = APIRouter(prefix="/api")


@router.get("/health")
def health(settings: SettingsDep) -> dict[str, Any]:
    return {
        "status": "ok",
        "model": settings.muse_model,
        "model_api_key_configured": settings.model_api_key is not None,
        "materials_project_configured": settings.mp_api_key is not None,
        "openalex_api_key_configured": settings.openalex_api_key is not None,
        "reference_db_available": get_reference_db().available,
        "candidate_store": "postgres" if settings.database_url else "memory",
        "relaxation_available": relaxation_available(),
    }


class VisitRequest(BaseModel):
    country: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")

    @field_validator("country")
    @classmethod
    def not_the_unknown_code(cls, value: str | None) -> str | None:
        # "ZZ" is how the counter stores an unknown country, so a caller cannot send it as one.
        if value == UNKNOWN:
            raise ValueError("Not a country code.")
        return value


@router.post("/visits", status_code=204)
def record_visit(
    body: VisitRequest,
    settings: SettingsDep,
    x_visit_secret: Annotated[str | None, Header()] = None,
) -> None:
    expected = settings.visit_secret
    if expected and not secrets.compare_digest(x_visit_secret or "", expected):
        raise HTTPException(status_code=403, detail="Not allowed.")
    get_visits().add(body.country)


@router.get("/visits")
def visit_stats() -> dict[str, Any]:
    visits = get_visits()
    counts = visits.counts()
    known = [{"code": code, "count": n} for code, n in counts.items() if code != UNKNOWN]
    return {
        "total": sum(counts.values()),
        "unknown": counts.get(UNKNOWN, 0),
        "countries": sorted(known, key=lambda c: (-c["count"], c["code"])),
        "persistent": visits.persistent,
    }


class AgentContext(BaseModel):
    """What the researcher sees in the workspace when they ask the agent."""

    host_material_id: str | None = Field(default=None, max_length=40)
    host_label: str | None = Field(default=None, max_length=200)
    current_candidate_id: str | None = Field(default=None, max_length=20)
    decision: DecisionKind | None = None
    feedback: str | None = Field(default=None, max_length=2000)
    goal: Goal | None = None
    audience: Audience = "expert"


class AgentRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    locale: Literal["en", "ko", "zh-Hans", "ja", "es", "de"] = "en"
    previous_response_id: str | None = Field(default=None, max_length=200)
    context: AgentContext | None = None


def with_context(message: str, context: AgentContext | None) -> str:
    if context is None:
        return message
    lines = []
    if context.host_label or context.host_material_id:
        host = context.host_label or ""
        if context.host_material_id:
            host += f" [Materials Project ID: {context.host_material_id}]"
        else:
            host += " [uploaded CIF: revise candidates made from it by candidate ID]"
        lines.append(f"Host: {host.strip()}")
    if context.goal:
        g = context.goal
        banned = f"; avoid {', '.join(g.forbidden_elements)}" if g.forbidden_elements else ""
        lines.append(
            f"Research goal: n >= {g.target_n} near 550 nm, band gap >= {g.min_band_gap} eV{banned}. "
            "Use score_against_goal to check candidates."
        )
    if context.current_candidate_id:
        stored = get_store().get(context.current_candidate_id)
        if stored:
            candidate = stored[0]
            lines.append(
                f"Current candidate: {candidate.candidate_id} ({candidate.formula}), "
                f"{candidate.assessment.status}"
            )
    if context.decision and context.current_candidate_id:
        reason = f' Reason: "{context.feedback}"' if context.feedback else ""
        lines.append(
            f"Researcher decision on {context.current_candidate_id}: {context.decision}.{reason}"
        )
    if context.audience == "beginner":
        lines.append(BEGINNER_NOTE)
    if not lines:
        return message
    return "[Workspace]\n" + "\n".join(lines) + "\n[/Workspace]\n\n" + message


@router.get("/debug/meta")
def debug_meta(request: Request, settings: SettingsDep) -> dict[str, Any]:
    """TEMPORARY: what Meta tells this server about its models. Remove after the live test."""
    if settings.model_api_key is None:
        raise HTTPException(status_code=503, detail="MODEL_API_KEY is not set.")
    if not AGENT_RATE.allow(client_id(request)):
        raise HTTPException(status_code=429, detail="Too many requests. Wait a few minutes.")
    key = settings.model_api_key.get_secret_value()
    headers = {"Authorization": f"Bearer {key}"}
    with httpx.Client(timeout=30) as http:
        listed = http.get(f"{settings.model_api_base_url}/models", headers=headers)
        location = http.get("https://ipinfo.io/json").json()
        calls = {}
        for model in ("muse-spark-1.3", "muse-spark-1.2", "muse-spark-1.1"):
            response = http.post(
                f"{settings.model_api_base_url}/responses",
                headers=headers,
                json={"model": model, "input": "Reply OK", "max_output_tokens": 16},
            )
            calls[model] = {"status": response.status_code, "text": response.text[:120]}
    return {
        "key_fingerprint": hashlib.sha256(key.encode()).hexdigest()[:12],
        "base_url": settings.model_api_base_url,
        "models_status": listed.status_code,
        "models": [m.get("id") for m in listed.json().get("data", [])]
        if listed.status_code == 200
        else listed.text[:120],
        "server_country": location.get("country"),
        "server_org": location.get("org"),
        "calls": calls,
    }


@router.post("/agent/run")
def agent_run(
    body: AgentRequest,
    request: Request,
    settings: SettingsDep,
    mp: OptionalMPDep,
    literature: LiteratureDep,
) -> dict[str, Any]:
    try:
        client = create_client(settings)
    except ModelAPIKeyMissing as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not AGENT_RATE.allow(client_id(request)):
        raise HTTPException(status_code=429, detail="Too many agent requests. Wait a few minutes.")
    try:
        AGENT_CAP.take()
    except UpstreamError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc

    try:
        result = run_agent(
            client,
            settings.muse_model,
            build_registry(mp, literature, goal=body.context.goal if body.context else None),
            with_context(body.message, body.context),
            locale=body.locale,
            max_steps=settings.agent_max_steps,
            previous_response_id=body.previous_response_id,
        )
    except AgentStepLimitReached as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except APIError as exc:
        raise HTTPException(status_code=502, detail=f"Meta Model API error: {exc}") from exc

    candidate_ids = [
        call.output["candidate_id"]
        for call in result.tool_calls
        if call.name == "create_candidate" and "candidate_id" in call.output
    ]
    return {"model": settings.muse_model, "candidate_ids": candidate_ids, **asdict(result)}
