# Backend image for Railway (about 215 MB of memory after candidate work in a local check).
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.28 /uv /bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1

COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev

COPY app ./app
# Reference data (14 MB SQLite, read-only): JARVIS-DFT, refractiveindex.info, measured gaps.
COPY data/reference.sqlite ./data/reference.sqlite
COPY data/validation.json ./data/validation.json

# Railway sets PORT.
CMD ["sh", "-c", "exec .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*' --no-access-log"]
