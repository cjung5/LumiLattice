from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr, field_validator
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
    # In production this is the frontend server's /api/meta route (see README, Deploy).
    model_api_base_url: str = "https://api.meta.ai/v1"
    # Standard (non-contributor) variant: researcher data must not be used for training.
    muse_model: str = "muse-spark-1.3"
    agent_max_steps: int = 8

    # Materials Project (free key: https://next-gen.materialsproject.org/api)
    mp_api_key: SecretStr | None = None
    # Semantic Scholar works without a key but is often rate-limited; a free key helps.
    semantic_scholar_api_key: SecretStr | None = None

    # Hosted Postgres for candidates (Railway in production). Unset: kept in memory only.
    database_url: SecretStr | None = None
    # Shared with the frontend server. When set, only that server can add to the visitor counts.
    visit_secret: str | None = None
    # Shared with the frontend server, which signs tokens after a Google sign-in. Unset: nobody can
    # sign in, and only public mode is available.
    auth_secret: str | None = None

    # Built by scripts/build_reference_db.py (JARVIS-DFT + refractiveindex.info subset).
    reference_db_path: Path = BACKEND_DIR / "data" / "reference.sqlite"

    # OpenAlex works without a key but then shares a small daily budget per IP address.
    # A free key (https://openalex.org/settings/api) gives the app its own budget.
    openalex_api_key: SecretStr | None = None

    # JSON list in the environment, e.g. CORS_ORIGINS='["https://lumilattice.vercel.app"]'
    cors_origins: list[str] = ["http://localhost:3000"]
    # Also allow origins that fully match this pattern (e.g. Vercel preview URLs).
    cors_origin_regex: str | None = None

    @field_validator(
        "model_api_key",
        "mp_api_key",
        "semantic_scholar_api_key",
        "openalex_api_key",
        "database_url",
        "auth_secret",
        mode="before",
    )
    @classmethod
    def blank_means_not_set(cls, value: object) -> object:
        """A host can save a variable with no value; it must not count as configured."""
        return None if isinstance(value, str) and not value.strip() else value

    @field_validator("auth_secret")
    @classmethod
    def long_enough(cls, value: str | None) -> str | None:
        """A short secret can be guessed, and then anyone could sign in as anyone."""
        if value is not None and len(value) < 32:
            raise ValueError("AUTH_SECRET needs at least 32 characters (openssl rand -hex 32).")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
