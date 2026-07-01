from dataclasses import dataclass

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
import pytest
from pydantic import SecretStr

from app.api.auth import (
    API_AUTH_FAILURE_DETAIL,
    FailClosedAuthError,
    build_require_api_key,
    enforce_fail_closed_auth,
)
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
    assert Settings.model_fields["github_app_id"].default is None
    assert Settings.model_fields["github_app_private_key"].default is None
    assert Settings.model_fields["github_app_webhook_secret"].default is None


def test_settings_accepts_github_app_env_aliases(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FOUNDEROS_GITHUB_APP_ID", "12345")
    monkeypatch.setenv("FOUNDEROS_GITHUB_APP_SLUG", "founderos-test")
    monkeypatch.setenv("FOUNDEROS_GITHUB_APP_PRIVATE_KEY_PATH", "/tmp/github-app.pem")
    monkeypatch.setenv("FOUNDEROS_GITHUB_APP_WEBHOOK_SECRET", "test-webhook-secret")
    monkeypatch.setenv(
        "FOUNDEROS_GITHUB_APP_SETUP_URL",
        "https://github.com/apps/founderos-test/installations/new",
    )

    config = Settings(_env_file=None)

    assert config.github_app_id == "12345"
    assert config.github_app_slug == "founderos-test"
    assert config.github_app_private_key_path == "/tmp/github-app.pem"
    assert isinstance(config.github_app_webhook_secret, SecretStr)
    assert (
        config.github_app_webhook_secret.get_secret_value()
        == "test-webhook-secret"
    )
    assert (
        config.github_app_setup_url
        == "https://github.com/apps/founderos-test/installations/new"
    )


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


def test_settings_accepts_fos_telegram_aliases(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.setenv("FOS_TELEGRAM_BOT_TOKEN", "test-fos-telegram-token")
    monkeypatch.setenv("FOS_TELEGRAM_CHAT_ID", "test-fos-telegram-chat")

    config = Settings(_env_file=None)

    assert config.telegram_bot_token == "test-fos-telegram-token"
    assert config.telegram_chat_id == "test-fos-telegram-chat"


def test_settings_prefers_standard_telegram_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-telegram-token")
    monkeypatch.setenv("FOS_TELEGRAM_BOT_TOKEN", "test-fos-telegram-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "test-telegram-chat")
    monkeypatch.setenv("FOS_TELEGRAM_CHAT_ID", "test-fos-telegram-chat")

    config = Settings(_env_file=None)

    assert config.telegram_bot_token == "test-telegram-token"
    assert config.telegram_chat_id == "test-telegram-chat"


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


# --- Fail-closed auth posture for non-local deployments --------------------


def test_fail_closed_allows_local_with_auth_disabled() -> None:
    config = Settings(app_env="local", api_auth_enabled=False, _env_file=None)

    # Local developer convenience: disabled auth must remain a valid startup.
    enforce_fail_closed_auth(config)


def test_fail_closed_allows_dev_with_auth_disabled() -> None:
    config = Settings(app_env="dev", api_auth_enabled=False, _env_file=None)

    enforce_fail_closed_auth(config)


def test_fail_closed_rejects_non_local_with_auth_disabled() -> None:
    config = Settings(app_env="production", api_auth_enabled=False, _env_file=None)

    with pytest.raises(FailClosedAuthError):
        enforce_fail_closed_auth(config)


def test_fail_closed_rejects_non_local_when_enabled_without_key() -> None:
    config = Settings(
        app_env="production",
        api_auth_enabled=True,
        api_auth_key=None,
        api_keys=None,
        _env_file=None,
    )

    with pytest.raises(FailClosedAuthError):
        enforce_fail_closed_auth(config)


def test_fail_closed_allows_non_local_when_enabled_with_primary_key() -> None:
    config = Settings(
        app_env="production",
        api_auth_enabled=True,
        api_auth_key=SecretStr("configured-operator-key"),
        _env_file=None,
    )

    enforce_fail_closed_auth(config)


def test_fail_closed_allows_non_local_when_enabled_with_api_keys_list() -> None:
    config = Settings(
        app_env="production",
        api_auth_enabled=True,
        api_auth_key=None,
        api_keys="configured-operator-key",
        _env_file=None,
    )

    enforce_fail_closed_auth(config)


def test_fail_closed_error_names_env_vars_and_hides_values() -> None:
    config = Settings(app_env="production", api_auth_enabled=False, _env_file=None)

    with pytest.raises(FailClosedAuthError) as exc_info:
        enforce_fail_closed_auth(config)

    message = str(exc_info.value)
    assert "API_AUTH_ENABLED" in message
    assert "API_AUTH_KEY" in message
    # The error must reference variable names only, never any key material.
    assert "configured-operator-key" not in message
