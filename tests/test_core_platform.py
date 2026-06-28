from fastapi.testclient import TestClient
from pydantic import SecretStr

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


def test_health_detail_requires_operator_auth(monkeypatch):
    monkeypatch.setattr(settings, "api_auth_enabled", True)
    monkeypatch.setattr(settings, "api_auth_key", SecretStr("test-api-key"))
    monkeypatch.setattr(settings, "api_auth_header_name", "X-FounderOS-API-Key")

    with TestClient(app) as client:
        unauthenticated = client.get("/health/detail")
        authenticated = client.get(
            "/health/detail", headers={"X-FounderOS-API-Key": "test-api-key"}
        )

    assert unauthenticated.status_code == 401
    assert authenticated.status_code == 200
    body = authenticated.json()
    assert body["status"] == "ok"
    assert body["env"] == settings.app_env
    assert body["write_actions_enabled"] is False
    assert body["llm_enabled"] is False
