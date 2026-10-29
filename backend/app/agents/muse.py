from openai import OpenAI

from app.config import Settings


class ModelAPIKeyMissing(RuntimeError):
    pass


def create_client(settings: Settings) -> OpenAI:
    """OpenAI SDK client pointed at the Meta Model API (drop-in compatible)."""
    if settings.model_api_key is None:
        raise ModelAPIKeyMissing("MODEL_API_KEY is not set. Add it to backend/.env.")
    return OpenAI(
        base_url=settings.model_api_base_url,
        api_key=settings.model_api_key.get_secret_value(),
        timeout=120,
        max_retries=2,
    )
