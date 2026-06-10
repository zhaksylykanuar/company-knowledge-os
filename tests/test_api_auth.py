from dataclasses import dataclass

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
import pytest
from pydantic import SecretStr

from app.api.auth import API_AUTH_FAILURE_DETAIL, build_require_api_key
from app.core.config import Settings
from app.main import app as production_app


@dataclass
class AuthConfig:
    api_auth_enabled: bool = False
    api_auth_key: SecretStr | str | None = None
    api_auth_header_name: str = "X-FounderOS-API-Key"


def _build_test_app(config: AuthConfig) -> FastAPI:
    app = FastAPI()

    @app.get("/protected", dependencies=[Depends(build_require_api_key(config))])
    async def protected() -> dict[str, bool]:
        return {"ok": True}

    return app


def test_api_auth_config_defaults_are_non_breaking() -> None:
    assert Settings.model_fields["api_auth_enabled"].default is False
    assert Settings.model_fields["api_auth_key"].default is None
    assert Settings.model_fields["api_auth_header_name"].default == "X-FounderOS-API-Key"
    assert Settings.model_fields["openai_api_key"].default is None


def test_settings_accepts_fos_openai_api_key_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("FOS_OPENAI_API_KEY", "test-fos-openai-key")

    config = Settings(_env_file=None)

    assert config.openai_api_key == "test-fos-openai-key"


def test_settings_prefers_standard_openai_api_key_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("FOS_OPENAI_API_KEY", "test-fos-openai-key")

    config = Settings(_env_file=None)

    assert config.openai_api_key == "test-openai-key"


def test_dependency_allows_when_auth_disabled() -> None:
    config = AuthConfig(api_auth_enabled=False, api_auth_key=None)

    with TestClient(_build_test_app(config)) as client:
        response = client.get("/protected")

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_dependency_rejects_missing_request_key_when_auth_enabled() -> None:
    config = AuthConfig(api_auth_enabled=True, api_auth_key=SecretStr("test-api-key"))

    with TestClient(_build_test_app(config)) as client:
        response = client.get("/protected")

    assert response.status_code == 401
    assert response.json() == {"detail": API_AUTH_FAILURE_DETAIL}
    assert "test-api-key" not in response.text


def test_dependency_rejects_wrong_request_key_without_exposing_keys() -> None:
    config = AuthConfig(api_auth_enabled=True, api_auth_key=SecretStr("test-api-key"))

    with TestClient(_build_test_app(config)) as client:
        response = client.get(
            "/protected",
            headers={"X-FounderOS-API-Key": "wrong-test-key"},
        )

    assert response.status_code == 401
    assert response.json() == {"detail": API_AUTH_FAILURE_DETAIL}
    assert "test-api-key" not in response.text
    assert "wrong-test-key" not in response.text


def test_dependency_accepts_valid_request_key() -> None:
    config = AuthConfig(api_auth_enabled=True, api_auth_key=SecretStr("test-api-key"))

    with TestClient(_build_test_app(config)) as client:
        response = client.get(
            "/protected",
            headers={"X-FounderOS-API-Key": "test-api-key"},
        )

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_dependency_fails_closed_when_auth_enabled_without_configured_key() -> None:
    config = AuthConfig(api_auth_enabled=True, api_auth_key=None)

    with TestClient(_build_test_app(config)) as client:
        response = client.get(
            "/protected",
            headers={"X-FounderOS-API-Key": "test-api-key"},
        )

    assert response.status_code == 401
    assert response.json() == {"detail": API_AUTH_FAILURE_DETAIL}
    assert "test-api-key" not in response.text


def test_dependency_uses_configured_header_name() -> None:
    config = AuthConfig(
        api_auth_enabled=True,
        api_auth_key=SecretStr("test-api-key"),
        api_auth_header_name="X-Custom-Test-Key",
    )

    with TestClient(_build_test_app(config)) as client:
        response = client.get(
            "/protected",
            headers={"X-Custom-Test-Key": "test-api-key"},
        )

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_health_remains_public_until_route_wiring_ticket() -> None:
    with TestClient(production_app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
