from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        extra="ignore",
        protected_namespaces=(),
    )

    # Meta Model API (https://dev.meta.ai/docs/quickstart). The OpenAI SDK does not
    # read MODEL_API_KEY on its own, so it is passed to the client explicitly.
    model_api_key: SecretStr | None = None
    model_api_base_url: str = "https://api.meta.ai/v1"
    # Standard (non-contributor) variant: researcher data must not be used for training.
    muse_model: str = "muse-spark-1.3"
    agent_max_steps: int = 8

    # Materials Project (free key: https://next-gen.materialsproject.org/api)
    mp_api_key: SecretStr | None = None
    # OpenAlex works without a key but then shares a small daily budget per IP address.
    # A free key (https://openalex.org/settings/api) gives the app its own budget.
    openalex_api_key: SecretStr | None = None

    # JSON list in the environment, e.g. CORS_ORIGINS='["https://lumilattice.vercel.app"]'
    cors_origins: list[str] = ["http://localhost:3000"]
    # Also allow origins that fully match this pattern (e.g. Vercel preview URLs).
    cors_origin_regex: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
