from __future__ import annotations

import json

from app.core.config import settings as app_settings
from app.db.base import AsyncSessionLocal
from app.services import connector_scope
from app.services.connector_diagnostics import build_connector_diagnostics
from app.services.secret_patterns import contains_secret_value


def test_require_connector_scope_defaults_true() -> None:
    assert app_settings.require_connector_scope is True


def _configure_jira(monkeypatch) -> None:
    monkeypatch.setenv("JIRA_BASE_URL", "https://example.atlassian.net")
    monkeypatch.setenv("JIRA_EMAIL", "ops@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "stage17-secret-shaped-token-value")


def test_scope_block_only_when_enabled_configured_and_unscoped(monkeypatch) -> None:
    _configure_jira(monkeypatch)
    monkeypatch.delenv("FOUNDEROS_JIRA_PROJECT_KEYS", raising=False)
    # Real disabled -> handled elsewhere, no scope block.
    monkeypatch.setattr(app_settings, "enable_real_connectors", False)
    assert connector_scope.sync_scope_block("jira") is None
    # Real enabled + configured + no scope -> blocked.
    monkeypatch.setattr(app_settings, "enable_real_connectors", True)
    assert connector_scope.sync_scope_block("jira") == "missing_scope"
    # Scope present -> not blocked.
    monkeypatch.setenv("FOUNDEROS_JIRA_PROJECT_KEYS", "QS,ABC")
    assert connector_scope.sync_scope_block("jira") is None


def test_scope_too_broad_detection(monkeypatch) -> None:
    monkeypatch.setenv("FOUNDEROS_GITHUB_REPOS", "owner/*")
    assert connector_scope.scope_too_broad("github") is True
    monkeypatch.setenv("FOUNDEROS_GITHUB_REPOS", "owner/repo")
    assert connector_scope.scope_too_broad("github") is False


def test_scope_values_drop_secret_shaped(monkeypatch) -> None:
    monkeypatch.setenv("FOUNDEROS_GITHUB_REPOS", "owner/repo,ghp_" + "a" * 30)
    values = connector_scope.scope_values("github")
    assert "owner/repo" in values
    assert all(not contains_secret_value(v) for v in values)


async def test_diagnostics_missing_scope_when_enabled_unscoped(monkeypatch) -> None:
    monkeypatch.setattr(app_settings, "enable_real_connectors", True)
    _configure_jira(monkeypatch)
    monkeypatch.delenv("FOUNDEROS_JIRA_PROJECT_KEYS", raising=False)
    async with AsyncSessionLocal() as session:
        diagnostics = await build_connector_diagnostics(session)
    jira = next(c for c in diagnostics["connectors"] if c["source_type"] == "jira")
    if jira["connector_state"] == "connected":
        return  # a prior successful run; covered by the connected invariant test
    assert jira["scope_required"] is True
    assert jira["scope_configured"] is False
    assert jira["pipeline_state"] == "missing_scope"
    assert jira["blocked_reason"] == "missing_scope"
    assert jira["can_test"] is True  # test is exempt
    assert jira["can_sync"] is False  # sync blocked without scope
    assert "FOUNDEROS_JIRA_PROJECT_KEYS" in jira["missing_scope_fields"]
    # The secret token never appears.
    assert not contains_secret_value(json.dumps(diagnostics))


async def test_diagnostics_scope_summary_and_not_connected(monkeypatch) -> None:
    monkeypatch.setattr(app_settings, "enable_real_connectors", True)
    _configure_jira(monkeypatch)
    monkeypatch.setenv("FOUNDEROS_JIRA_PROJECT_KEYS", "QS,ABC")
    async with AsyncSessionLocal() as session:
        diagnostics = await build_connector_diagnostics(session)
    jira = next(c for c in diagnostics["connectors"] if c["source_type"] == "jira")
    assert jira["scope_configured"] is True
    assert jira["scope_summary"]["count"] == 2
    assert jira["scope_summary"].get("project_keys") == ["QS", "ABC"]
    # configured + scoped is NOT connected without a successful run.
    if jira["connector_state"] == "connected":
        assert jira["last_success_at"] is not None
    else:
        assert jira["pipeline_state"] in {"never_tested", "test_succeeded"}
    assert jira["limits"]["sync_limit"] >= 1


async def test_connected_requires_success_invariant() -> None:
    async with AsyncSessionLocal() as session:
        diagnostics = await build_connector_diagnostics(session)
    for connector in diagnostics["connectors"]:
        if connector["connector_state"] == "connected":
            assert connector["last_success_at"] is not None
