from dataclasses import asdict
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from openai import APIError
from pydantic import BaseModel, Field

from app.agents.loop import AgentStepLimitReached, run_agent
from app.agents.muse import ModelAPIKeyMissing, create_client
from app.api.deps import LiteratureDep, OptionalMPDep, SettingsDep
from app.tools.catalog import build_registry

router = APIRouter(prefix="/api")


@router.get("/health")
def health(settings: SettingsDep) -> dict[str, Any]:
    return {
        "status": "ok",
        "model": settings.muse_model,
        "model_api_key_configured": settings.model_api_key is not None,
        "materials_project_configured": settings.mp_api_key is not None,
        "openalex_api_key_configured": settings.openalex_api_key is not None,
    }


class AgentRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    locale: Literal["en", "ko", "zh-Hans", "ja", "es", "de"] = "en"


@router.post("/agent/run")
def agent_run(
    request: AgentRequest,
    settings: SettingsDep,
    mp: OptionalMPDep,
    literature: LiteratureDep,
) -> dict[str, Any]:
    try:
        client = create_client(settings)
    except ModelAPIKeyMissing as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    try:
        result = run_agent(
            client,
            settings.muse_model,
            build_registry(mp, literature),
            request.message,
            locale=request.locale,
            max_steps=settings.agent_max_steps,
        )
    except AgentStepLimitReached as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except APIError as exc:
        raise HTTPException(status_code=502, detail=f"Meta Model API error: {exc}") from exc
    return {"model": settings.muse_model, **asdict(result)}
