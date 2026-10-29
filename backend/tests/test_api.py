from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app


def test_health_reports_missing_key():
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None)
    try:
        response = TestClient(app).get("/api/health")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["model"] == "muse-spark-1.3"
    assert body["model_api_key_configured"] is False


def test_agent_without_key_returns_503():
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None)
    try:
        response = TestClient(app).post("/api/agent/run", json={"message": "hi"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
