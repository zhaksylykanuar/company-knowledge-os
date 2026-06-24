from __future__ import annotations

import json

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.config import settings as app_settings
from app.db.base import AsyncSessionLocal
from app.db.source_control_models import SourceControlState
from app.main import app
from app.services.connector_diagnostics import build_connector_diagnostics
from app.services.secret_patterns import contains_secret_value

_REQUIRED_KEYS = {
    "source_type",
    "label",
    "readiness",
    "configured",
    "connector_state",
    "missing_env_vars",
    "can_test",
    "can_sync",
    "can_backfill",
    "last_test_result",
    "last_sync_result",
    "last_error_sanitized",
    "docs_link",
    "setup_steps",
    "restart_required_hint",
    "security_policy",
    "adapter_type",
}


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_connector_diagnostics_endpoint_is_founder_only() -> None:
    async with _client() as client:
        founder = await client.get("/api/v1/founder/connectors/diagnostics")
        team = await client.get(
            "/api/v1/founder/connectors/diagnostics", params={"view": "team"}
        )
        investor = await client.get(
            "/api/v1/founder/connectors/diagnostics", params={"view": "investor"}
        )
    assert founder.status_code == 200
    assert team.status_code == 403
    assert investor.status_code == 403


async def test_connector_diagnostics_shape_and_security_policy() -> None:
    async with _client() as client:
        response = await client.get("/api/v1/founder/connectors/diagnostics")
    assert response.status_code == 200
    payload = response.json()
    assert payload["security_policy"] == {
        "read_only": True,
        "secrets_exposed_to_browser": False,
        "external_writes_allowed": False,
    }
    types = {c["source_type"] for c in payload["connectors"]}
    assert {"jira", "github", "gmail", "meetings", "declarations"} <= types
    for connector in payload["connectors"]:
        assert _REQUIRED_KEYS <= set(connector.keys()), connector["source_type"]
        assert connector["security_policy"]["read_only"] is True
        assert connector["security_policy"]["secrets_exposed_to_browser"] is False
        assert connector["security_policy"]["external_writes_allowed"] is False
        assert isinstance(connector["setup_steps"], list)
        assert connector["setup_steps"], connector["source_type"]
        assert isinstance(connector["missing_env_vars"], list)


async def test_connector_diagnostics_reports_missing_names_never_values(
    monkeypatch,
) -> None:
    secret = "SECRET-JIRA-STAGE14-TOKEN-VALUE"
    monkeypatch.delenv("JIRA_BASE_URL", raising=False)
    monkeypatch.delenv("JIRA_EMAIL", raising=False)
    monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
    monkeypatch.setattr(app_settings, "jira_base_url", None)
    monkeypatch.setattr(app_settings, "jira_email", None)
    monkeypatch.setattr(app_settings, "jira_api_token", secret)

    async with AsyncSessionLocal() as session:
        diagnostics = await build_connector_diagnostics(session)
    blob = json.dumps(diagnostics)

    # Secret value (or a token-length prefix of it) never appears.
    assert secret not in blob
    assert secret[:8] not in blob
    assert not contains_secret_value(blob)

    jira = next(c for c in diagnostics["connectors"] if c["source_type"] == "jira")
    assert "JIRA_BASE_URL" in jira["missing_env_vars"]
    assert "JIRA_EMAIL" in jira["missing_env_vars"]
    # The masked token is reported by name/status only, not by value.
    statuses = {item["name"]: item["status"] for item in jira["masked_config_status"]}
    assert statuses.get("JIRA_API_TOKEN") in {"masked", "configured"}


async def test_connector_diagnostics_no_fake_connected_state() -> None:
    """A connector is only ``connected`` if a run actually succeeded."""

    async with AsyncSessionLocal() as session:
        diagnostics = await build_connector_diagnostics(session)
    for connector in diagnostics["connectors"]:
        if connector["connector_state"] == "connected":
            assert connector["last_success_at"] is not None, connector["source_type"]


async def test_connector_diagnostics_missing_config_when_not_configured(
    monkeypatch,
) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("FOS_GITHUB_READONLY_TOKEN", raising=False)
    async with AsyncSessionLocal() as session:
        snapshot = await session.scalar(
            select(SourceControlState).where(
                SourceControlState.source_type == "github"
            )
        )
        had_success = bool(snapshot and snapshot.last_success_at)
        diagnostics = await build_connector_diagnostics(session)
    github = next(c for c in diagnostics["connectors"] if c["source_type"] == "github")
    if had_success:
        # A prior successful run legitimately makes it connected; the missing
        # config assertions below only apply to the clean-slate case.
        return
    # No env, no successful run -> not configured and not connected.
    assert github["configured"] is False
    assert github["connector_state"] in {"missing_config"}
    assert github["can_test"] is False
    assert "GITHUB_TOKEN" in github["missing_env_vars"]
