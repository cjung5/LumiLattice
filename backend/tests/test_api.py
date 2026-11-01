from fastapi.testclient import TestClient

from app.agents.muse import create_client
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


def test_cors_regex_allows_vercel_previews():
    import re

    pattern = re.compile(r"https://lumilattice[a-z0-9-]*\.vercel\.app")
    assert pattern.fullmatch("https://lumilattice.vercel.app")
    assert pattern.fullmatch("https://lumilattice-git-main-cjung5.vercel.app")
    assert not pattern.fullmatch("https://evil.example.com")
    assert not pattern.fullmatch("https://lumilattice.vercel.app.evil.com")


def test_blank_secret_counts_as_not_configured():
    settings = Settings(_env_file=None, model_api_key="", mp_api_key="  ", openalex_api_key="k")

    assert settings.model_api_key is None
    assert settings.mp_api_key is None
    assert settings.openalex_api_key is not None


def test_proxy_secret_goes_only_to_the_proxy():
    direct = create_client(Settings(_env_file=None, model_api_key="k", visit_secret="s"))
    proxied = create_client(
        Settings(
            _env_file=None,
            model_api_key="k",
            visit_secret="s",
            model_api_base_url="https://site.vercel.app/api/meta",
        )
    )

    assert "X-Proxy-Secret" not in direct.default_headers
    assert proxied.default_headers["X-Proxy-Secret"] == "s"
