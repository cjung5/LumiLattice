from urllib.parse import urlsplit

from openai import OpenAI

from app.config import Settings


class ModelAPIKeyMissing(RuntimeError):
    pass


def create_client(settings: Settings) -> OpenAI:
    """OpenAI SDK client pointed at the Meta Model API (drop-in compatible)."""
    if settings.model_api_key is None:
        raise ModelAPIKeyMissing("MODEL_API_KEY is not set. Add it to backend/.env.")
    # Through the frontend server's route, the secret proves that this backend is the caller.
    # It is never sent to Meta itself.
    through_proxy = urlsplit(settings.model_api_base_url).hostname != "api.meta.ai"
    return OpenAI(
        base_url=settings.model_api_base_url,
        api_key=settings.model_api_key.get_secret_value(),
        timeout=120,
        max_retries=2,
        default_headers={"X-Proxy-Secret": settings.visit_secret}
        if through_proxy and settings.visit_secret
        else None,
    )
