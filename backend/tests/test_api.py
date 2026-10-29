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


def test_materials_search_without_mp_key_returns_503():
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None)
    try:
        response = TestClient(app).get("/api/materials/search", params={"q": "SrTiO3"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert "MP_API_KEY" in response.json()["detail"]


def test_cif_upload(srtio3):
    from pymatgen.io.cif import CifWriter

    response = TestClient(app).post(
        "/api/structures/cif", json={"filename": "a.cif", "cif": str(CifWriter(srtio3))}
    )

    assert response.status_code == 200
    assert response.json()["formula"] == "SrTiO3"


def test_bad_cif_upload_returns_400():
    response = TestClient(app).post("/api/structures/cif", json={"filename": "a.cif", "cif": "x"})

    assert response.status_code == 400


def test_agent_without_key_returns_503():
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None)
    try:
        response = TestClient(app).post("/api/agent/run", json={"message": "hi"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
