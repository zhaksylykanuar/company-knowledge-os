from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import delete

from app.core.config import settings as app_settings
from app.db.base import AsyncSessionLocal
from app.db.source_control_models import SourceControlState
from app.services.action_center import build_action_center
from app.services.connector_diagnostics import build_connector_diagnostics
from app.services.data_quality_center import build_data_quality_center
from app.services.obsidian_vault import (
    _assert_markdown_safe,
    generate_obsidian_vault_plan,
)
from app.services.secret_patterns import contains_secret_value

ROOT = Path(__file__).resolve().parents[1]


def test_sources_ui_has_scope_guardrails() -> None:
    html = (ROOT / "app" / "static" / "founder_ui.html").read_text(encoding="utf-8")
    for marker in (
        "scope_required",
        "scope too broad",
        "add scope env (names only)",
        "missing_scope_fields",
        "blocked reason:",
        "limits: sync ",
        "preview_sync",
    ):
        assert marker in html, marker


def test_env_example_documents_scope() -> None:
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    for marker in (
        "FOUNDEROS_REQUIRE_CONNECTOR_SCOPE",
        "FOUNDEROS_JIRA_PROJECT_KEYS",
        "FOUNDEROS_GITHUB_REPOS",
        "FOUNDEROS_CONNECTOR_BACKFILL_MAX_DAYS",
    ):
        assert marker in env_example, marker
    assert "ghp_" not in env_example
    assert "sk-" not in env_example


def test_docs_explain_scoped_setup() -> None:
    docs = (ROOT / "docs" / "source-connectors.md").read_text(encoding="utf-8")
    assert "Safe Live Connector Setup" in docs
    assert "FOUNDEROS_JIRA_PROJECT_KEYS=QS" in docs
    assert "no full-org scan" in docs.lower()
    assert "blocked_missing_scope" in docs


async def test_dq_and_action_center_scope_issues(monkeypatch) -> None:
    monkeypatch.setattr(app_settings, "enable_real_connectors", True)
    monkeypatch.setenv("JIRA_BASE_URL", "https://example.atlassian.net")
    monkeypatch.setenv("JIRA_EMAIL", "ops@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "stage17-secret-shaped-token-value")
    monkeypatch.delenv("FOUNDEROS_JIRA_PROJECT_KEYS", raising=False)
    monkeypatch.setenv("GITHUB_TOKEN", "stage17-secret-shaped-token-value")
    monkeypatch.setenv("FOUNDEROS_GITHUB_REPOS", "owner/*")
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(SourceControlState).where(
                SourceControlState.source_type.in_(["jira", "github"])
            )
        )
        await session.flush()
        dq = await build_data_quality_center(session)
        ac = await build_action_center(session)
        await session.rollback()
    dq_cats = {issue["category"] for issue in dq["issues"]}
    assert "connector_real_enabled_missing_scope" in dq_cats
    assert "connector_scope_too_broad" in dq_cats
    ac_types = {a["action_type"] for a in ac["actions"] if a["source"] == "connector"}
    assert "add_connector_scope" in ac_types
    assert "narrow_connector_scope" in ac_types
    assert not contains_secret_value(json.dumps(dq))
    assert not contains_secret_value(json.dumps(ac))


async def test_obsidian_connector_notes_include_scope(monkeypatch) -> None:
    monkeypatch.setattr(app_settings, "enable_real_connectors", True)
    monkeypatch.setenv("JIRA_BASE_URL", "https://example.atlassian.net")
    monkeypatch.setenv("JIRA_EMAIL", "ops@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "stage17-secret-shaped-token-value")
    monkeypatch.delenv("FOUNDEROS_JIRA_PROJECT_KEYS", raising=False)
    async with AsyncSessionLocal() as session:
        plan = await generate_obsidian_vault_plan(session)
    jira = next(n for n in plan.notes if n.path == "Sources/Jira.md")
    assert "## Область и лимиты" in jira.markdown
    assert "Область обязательна (scope required):" in jira.markdown
    assert "Лимиты: синхронизация" in jira.markdown

    connector_notes = [n for n in plan.notes if n.node_type == "connector_diagnostics"]
    blob = "\n".join(n.markdown for n in connector_notes)
    assert "stage17-secret-shaped-token-value" not in blob
    for forbidden in ("ghp_", "sk-", "raw://"):
        assert forbidden not in blob
    for note in connector_notes:
        _assert_markdown_safe(note.markdown)


async def test_adversarial_secret_env_and_wildcard_scope_no_leak(monkeypatch) -> None:
    secret = "ghp_" + "B" * 32
    monkeypatch.setattr(app_settings, "enable_real_connectors", True)
    monkeypatch.setenv("JIRA_BASE_URL", "https://example.atlassian.net")
    monkeypatch.setenv("JIRA_EMAIL", "ops@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", secret)
    monkeypatch.setenv("GITHUB_TOKEN", secret)
    monkeypatch.setenv("FOUNDEROS_GITHUB_REPOS", "owner/*")
    monkeypatch.setenv("FOUNDEROS_JIRA_PROJECT_KEYS", secret)  # secret-shaped scope
    async with AsyncSessionLocal() as session:
        diagnostics = await build_connector_diagnostics(session)
        plan = await generate_obsidian_vault_plan(session)
    dblob = json.dumps(diagnostics)
    mblob = "\n".join(n.markdown for n in plan.notes)
    assert secret not in dblob
    assert secret not in mblob
    assert not contains_secret_value(dblob)
    # A secret-shaped "scope" value is dropped, not surfaced.
    jira = next(c for c in diagnostics["connectors"] if c["source_type"] == "jira")
    assert secret not in json.dumps(jira["scope_summary"])
