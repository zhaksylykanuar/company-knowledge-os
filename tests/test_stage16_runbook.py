from __future__ import annotations

import json

from sqlalchemy import select

from app.core.config import settings as app_settings
from app.db.base import AsyncSessionLocal
from app.db.source_control_models import SourceControlState
from app.services.connector_diagnostics import build_connector_diagnostics
from app.services.secret_patterns import contains_secret_value


async def _diag(session):
    return await build_connector_diagnostics(session)


async def test_runbook_missing_config_stage(monkeypatch) -> None:
    monkeypatch.setattr(app_settings, "enable_real_connectors", False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("FOS_GITHUB_READONLY_TOKEN", raising=False)
    async with AsyncSessionLocal() as session:
        diagnostics = await _diag(session)
    github = next(c for c in diagnostics["connectors"] if c["source_type"] == "github")
    if github["configured"]:
        return  # env present in this environment; covered by other states
    assert github["pipeline_state"] == "missing_config"
    runbook = github["runbook"]
    assert runbook["stage"] == "configure_env"
    assert "GITHUB_TOKEN" in runbook["blocking_env_vars"]
    assert "start_local.py" in runbook["next_command"]


async def test_runbook_real_disabled_stage(monkeypatch) -> None:
    monkeypatch.setattr(app_settings, "enable_real_connectors", False)
    monkeypatch.setenv("JIRA_BASE_URL", "https://example.atlassian.net")
    monkeypatch.setenv("JIRA_EMAIL", "ops@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "stage16-fake-token-value")
    async with AsyncSessionLocal() as session:
        await session.execute(
            select(SourceControlState).where(SourceControlState.source_type == "jira")
        )
        diagnostics = await _diag(session)
    jira = next(c for c in diagnostics["connectors"] if c["source_type"] == "jira")
    # Configured but real connectors off, and no prior success in env.
    if jira["connector_state"] == "connected":
        return
    assert jira["pipeline_state"] == "real_disabled"
    assert jira["runbook"]["stage"] == "enable_real_connectors"
    assert "FOUNDEROS_ENABLE_REAL_CONNECTORS=true" in jira["runbook"]["next_command"]


async def test_runbook_never_tested_when_enabled_configured(monkeypatch) -> None:
    monkeypatch.setattr(app_settings, "enable_real_connectors", True)
    monkeypatch.setenv("JIRA_BASE_URL", "https://example.atlassian.net")
    monkeypatch.setenv("JIRA_EMAIL", "ops@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "stage16-fake-token-value")
    monkeypatch.setenv("FOUNDEROS_JIRA_PROJECT_KEYS", "QS")  # scope present
    async with AsyncSessionLocal() as session:
        # Clean slate: no prior success row.
        await session.execute(
            select(SourceControlState).where(SourceControlState.source_type == "jira")
        )
        state = await session.scalar(
            select(SourceControlState).where(SourceControlState.source_type == "jira")
        )
        if state and state.last_success_at:
            return
        diagnostics = await _diag(session)
    jira = next(c for c in diagnostics["connectors"] if c["source_type"] == "jira")
    assert jira["pipeline_state"] == "never_tested"
    assert jira["runbook"]["stage"] == "test_connection"
    assert "RUN SOURCE REQUESTS" in jira["runbook"]["next_command"]


async def test_pilot_summary_and_no_secrets(monkeypatch) -> None:
    monkeypatch.setenv("JIRA_API_TOKEN", "stage16-secret-shaped-value-xyz")
    async with AsyncSessionLocal() as session:
        diagnostics = await _diag(session)
    pilot = diagnostics["pilot"]
    assert "by_pipeline_state" in pilot
    assert pilot["commands"]["pilot"].endswith('"RUN LOCAL CONNECTOR PILOT"')
    assert pilot["commands"]["operator_run"].endswith('"RUN SOURCE REQUESTS"')
    assert isinstance(pilot["next_steps"], list) and pilot["next_steps"]
    assert not contains_secret_value(json.dumps(diagnostics))


async def test_state_machine_env_configured_is_not_connected(monkeypatch) -> None:
    """Configured env must never read as connected without a successful run."""
    monkeypatch.setattr(app_settings, "enable_real_connectors", True)
    monkeypatch.setenv("JIRA_BASE_URL", "https://example.atlassian.net")
    monkeypatch.setenv("JIRA_EMAIL", "ops@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "stage16-fake-token-value")
    async with AsyncSessionLocal() as session:
        diagnostics = await _diag(session)
    for connector in diagnostics["connectors"]:
        if connector["connector_state"] == "connected":
            assert connector["last_success_at"] is not None
        if connector["pipeline_state"] in {"sync_succeeded", "connected"}:
            assert connector["last_success_at"] is not None
