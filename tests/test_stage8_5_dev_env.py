from __future__ import annotations

import json

from httpx import ASGITransport, AsyncClient

from app.api.auth import settings as auth_settings
from app.core.config import Settings, settings
from app.main import app
from app.services.browser_config import (
    ALLOWED_KEYS,
    browser_dev_config_enabled,
    redact_config_for_logs,
    sanitize_browser_config,
    sanitize_for_logs,
)

# External secrets that must NEVER reach the browser dev config. Sentinel
# values (deliberately NOT key-shaped, so the staged-secret scan stays quiet).
_SECRET_FIELDS = {
    "openai_api_key": "LEAKED-OPENAI-VALUE-must-not-surface",
    "jira_api_token": "LEAKED-JIRA-API-TOKEN-value",
    "telegram_bot_token": "LEAKED-TELEGRAM-BOT-value",
    "github_webhook_secret": "LEAKED-GITHUB-SECRET-value",
}
_FORBIDDEN = (
    "leaked-openai",
    "leaked-jira",
    "leaked-telegram",
    "leaked-github",
    "openai_api_key",
    "github_token",
    "jira_api_token",
    "gmail_client_secret",
    "client_secret",
)


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _enable_dev(
    monkeypatch,
    *,
    app_env: str = "local",
    enabled: bool = True,
    dev_key: str | None = "local-dev-key",
) -> None:
    monkeypatch.setattr(settings, "app_env", app_env)
    monkeypatch.setattr(settings, "enable_browser_dev_config", enabled)
    monkeypatch.setattr(settings, "dev_api_key", dev_key)
    monkeypatch.setattr(settings, "founderos_api_base_url", "http://127.0.0.1:8765")


# --- endpoint gating ----------------------------------------------------


async def test_browser_config_local_returns_dev_key(monkeypatch) -> None:
    _enable_dev(monkeypatch)
    async with _client() as client:
        response = await client.get("/api/v1/dev/browser-config")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == set(ALLOWED_KEYS)
    assert body["dev_api_key"] == "local-dev-key"
    assert body["app_env"] == "local"
    assert body["api_base_url"] == "http://127.0.0.1:8765"
    assert body["features"]["share_packs"] is True
    assert body["features"]["role_views"] is True


async def test_browser_config_is_not_cacheable(monkeypatch) -> None:
    _enable_dev(monkeypatch)
    async with _client() as client:
        response = await client.get("/api/v1/dev/browser-config")
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Pragma"] == "no-cache"


async def test_browser_config_disabled_is_not_found(monkeypatch) -> None:
    _enable_dev(monkeypatch, enabled=False)
    async with _client() as client:
        response = await client.get("/api/v1/dev/browser-config")
    assert response.status_code == 404


async def test_browser_config_non_local_is_not_found(monkeypatch) -> None:
    _enable_dev(monkeypatch, app_env="production")
    async with _client() as client:
        response = await client.get("/api/v1/dev/browser-config")
    assert response.status_code == 404


async def test_browser_config_never_leaks_external_secrets(monkeypatch) -> None:
    _enable_dev(monkeypatch)
    for field, value in _SECRET_FIELDS.items():
        monkeypatch.setattr(settings, field, value)
    async with _client() as client:
        response = await client.get("/api/v1/dev/browser-config")
    assert response.status_code == 200
    blob = json.dumps(response.json()).lower()
    for term in _FORBIDDEN:
        assert term not in blob, term


def test_browser_dev_config_enabled_predicate() -> None:
    class Cfg:
        app_env = "local"
        enable_browser_dev_config = True

    assert browser_dev_config_enabled(Cfg()) is True
    Cfg.enable_browser_dev_config = False
    assert browser_dev_config_enabled(Cfg()) is False
    Cfg.enable_browser_dev_config = True
    Cfg.app_env = "production"
    assert browser_dev_config_enabled(Cfg()) is False


def test_sanitize_browser_config_is_allowlist_only() -> None:
    class Cfg:
        app_env = "local"
        founderos_api_base_url = "http://127.0.0.1:8765"
        dev_api_key = "local-dev-key"
        enable_browser_dev_config = True
        # secrets hanging off the same config object must never surface
        openai_api_key = "LEAKED-OPENAI-VALUE"
        jira_api_token = "LEAKED-JIRA-VALUE"
        github_token = "LEAKED-GH-VALUE"
        gmail_client_secret = "LEAKED-GMAIL-VALUE"

    out = sanitize_browser_config(Cfg())
    assert set(out) == set(ALLOWED_KEYS)
    blob = json.dumps(out)
    for bad in ("LEAKED-OPENAI", "LEAKED-JIRA", "LEAKED-GH", "LEAKED-GMAIL"):
        assert bad not in blob


def test_dev_api_key_is_redacted_from_log_safe_config() -> None:
    payload = sanitize_for_logs(
        {
            "dev_api_key": "local-dev-key",
            "nested": {"jira_api_token": "LEAKED-JIRA-VALUE"},
            "app_env": "local",
        }
    )
    blob = json.dumps(payload)
    assert "local-dev-key" not in blob
    assert "LEAKED-JIRA-VALUE" not in blob
    assert "***redacted***" in blob


def test_settings_log_redaction_masks_dev_key() -> None:
    class Cfg:
        app_env = "local"
        dev_api_key = "local-dev-key"
        api_base_url = "http://127.0.0.1:8765"

    safe = redact_config_for_logs(Cfg())
    blob = json.dumps(safe)
    assert safe["dev_api_key"] == "***redacted***"
    assert "local-dev-key" not in blob


# --- settings loader ----------------------------------------------------


def test_settings_dev_fields_default_off() -> None:
    assert Settings.model_fields["enable_browser_dev_config"].default is False
    assert Settings.model_fields["dev_api_key"].default is None
    assert Settings.model_fields["api_keys"].default is None


def test_settings_reads_founderos_aliases(monkeypatch) -> None:
    monkeypatch.setenv("FOUNDEROS_DEV_API_KEY", "env-dev-key")
    monkeypatch.setenv("FOUNDEROS_ENABLE_BROWSER_DEV_CONFIG", "true")
    monkeypatch.setenv("FOUNDEROS_API_KEYS", "k1,k2")
    config = Settings(_env_file=None)
    assert config.dev_api_key == "env-dev-key"
    assert config.enable_browser_dev_config is True
    assert config.api_keys == "k1,k2"


# --- dev key authenticates the local backend ----------------------------


async def test_dev_key_authenticates_protected_endpoint(monkeypatch) -> None:
    _enable_dev(monkeypatch)
    monkeypatch.setattr(auth_settings, "api_auth_enabled", True)
    monkeypatch.setattr(auth_settings, "api_auth_key", None)
    monkeypatch.setattr(auth_settings, "api_keys", None)
    monkeypatch.setattr(auth_settings, "api_auth_header_name", "X-FounderOS-API-Key")
    async with _client() as client:
        ok = await client.get(
            "/api/v1/founder/company-brain/preview",
            headers={"X-FounderOS-API-Key": "local-dev-key"},
        )
        bad = await client.get(
            "/api/v1/founder/company-brain/preview",
            headers={"X-FounderOS-API-Key": "not-the-dev-key"},
        )
    assert ok.status_code == 200
    assert bad.status_code == 401


def test_dev_key_not_accepted_when_not_local(monkeypatch) -> None:
    from app.api.auth import _accepted_keys

    class Cfg:
        api_auth_enabled = True
        api_auth_key = None
        api_auth_header_name = "X-FounderOS-API-Key"
        api_keys = None
        app_env = "production"
        enable_browser_dev_config = True
        dev_api_key = "local-dev-key"

    # Outside local, the dev key is not an accepted backend key.
    assert "local-dev-key" not in _accepted_keys(Cfg())
    Cfg.app_env = "local"
    assert "local-dev-key" in _accepted_keys(Cfg())
