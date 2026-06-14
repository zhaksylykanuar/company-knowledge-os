from __future__ import annotations

from pathlib import Path

from app.db.base import AsyncSessionLocal
from app.services.obsidian_vault import (
    _assert_markdown_safe,
    generate_obsidian_vault_plan,
)

ROOT = Path(__file__).resolve().parents[1]


def test_sources_ui_shows_real_execution_state() -> None:
    html = (ROOT / "app" / "static" / "founder_ui.html").read_text(encoding="utf-8")
    for marker in (
        "REAL_CONNECTORS_ENABLED",
        "real_execution_enabled",
        "real exec:",
        "real_connectors_disabled",
        "Real connector execution is",
    ):
        assert marker in html, marker


def test_env_example_documents_real_connector_flags() -> None:
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    for marker in (
        "FOUNDEROS_ENABLE_REAL_CONNECTORS",
        "FOUNDEROS_CONNECTOR_SYNC_LIMIT",
        "FOUNDEROS_CONNECTOR_BACKFILL_LIMIT",
    ):
        assert marker in env_example, marker
    # No real secret values in the template.
    assert "ghp_" not in env_example
    assert "sk-" not in env_example


def test_docs_explain_real_connectors_and_read_only() -> None:
    docs = (ROOT / "docs" / "source-connectors.md").read_text(encoding="utf-8")
    assert "FOUNDEROS_ENABLE_REAL_CONNECTORS=true" in docs
    assert "read-only" in docs.lower()
    assert "run_source_requests.py" in docs
    assert "local-only" in docs.lower()


async def test_obsidian_connector_notes_include_real_execution_and_counts() -> None:
    async with AsyncSessionLocal() as session:
        plan = await generate_obsidian_vault_plan(session)
    connector_notes = [
        note for note in plan.notes if note.node_type == "connector_diagnostics"
    ]
    jira = next(note for note in plan.notes if note.path == "Sources/Jira.md")
    assert "Real execution:" in jira.markdown
    assert "Events ingested:" in jira.markdown
    assert "Normalized events:" in jira.markdown

    blob = "\n".join(note.markdown for note in connector_notes)
    for forbidden in ("ghp_", "sk-", "raw://", "dev_api_key"):
        assert forbidden not in blob
    for note in connector_notes:
        _assert_markdown_safe(note.markdown)
