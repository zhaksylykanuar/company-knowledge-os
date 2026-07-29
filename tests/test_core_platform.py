from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.exc import SQLAlchemyError

from app.api import health as health_routes
from app.core.config import settings
from app.main import app


def test_public_health_is_minimal_and_leaks_no_flags():
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    # Public liveness only — no env / write / llm posture.
    assert body == {"status": "ok"}
    assert "env" not in body
    assert "write_actions_enabled" not in body
    assert "llm_enabled" not in body
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert len(response.headers["x-request-id"]) == 32


def test_public_readiness_checks_postgres_and_remains_minimal():
    with TestClient(app) as client:
        response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_readiness_fails_closed_when_postgres_is_unavailable(monkeypatch):
    class FailingSession:
        async def __aenter__(self):
            raise SQLAlchemyError("database unavailable")

        async def __aexit__(self, *_args):
            return None

    monkeypatch.setattr(health_routes, "AsyncSessionLocal", FailingSession)

    with TestClient(app) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}


def test_health_detail_requires_operator_auth(monkeypatch):
    monkeypatch.setattr(settings, "api_auth_enabled", True)
    monkeypatch.setattr(settings, "api_auth_key", SecretStr("test-api-key"))
    monkeypatch.setattr(settings, "api_auth_header_name", "X-FounderOS-API-Key")

    with TestClient(app) as client:
        unauthenticated = client.get("/health/detail")
        authenticated = client.get(
            "/health/detail", headers={"X-FounderOS-API-Key": "test-api-key"}
        )
        metrics = client.get(
            "/health/metrics", headers={"X-FounderOS-API-Key": "test-api-key"}
        )

    assert unauthenticated.status_code == 401
    assert authenticated.status_code == 200
    body = authenticated.json()
    assert body["status"] == "ok"
    assert body["env"] == settings.app_env
    assert body["write_actions_enabled"] is False
    assert body["llm_enabled"] is False

    assert metrics.status_code == 200
    payload = metrics.json()
    assert payload["scope"] == "process"
    assert payload["metrics"]["requests_total"] >= 1
    assert "paths" not in payload["metrics"]


def test_non_local_api_docs_are_hidden_and_browser_mutations_require_origin(
    monkeypatch,
):
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "api_auth_enabled", True)
    monkeypatch.setattr(settings, "api_auth_key", SecretStr("test-api-key"))
    monkeypatch.setattr(
        settings,
        "cors_allowed_origins",
        "https://founderos.example.test",
    )

    with TestClient(app) as client:
        docs = client.get("/openapi.json")
        missing_origin = client.post(
            "/api/v1/auth/login",
            json={},
        )
        wrong_origin = client.post(
            "/api/v1/auth/login",
            headers={"Origin": "https://attacker.example.test"},
            json={},
        )
        accepted_origin = client.post(
            "/api/v1/auth/login",
            headers={"Origin": "https://founderos.example.test"},
            json={},
        )

    assert docs.status_code == 404
    assert "strict-transport-security" in docs.headers
    assert "content-security-policy" in docs.headers
    assert missing_origin.status_code == 403
    assert wrong_origin.status_code == 403
    assert accepted_origin.status_code == 422
