from __future__ import annotations

import json
import os
from pathlib import Path

from app.db.base import AsyncSessionLocal
from app.services.obsidian_vault import (
    _assert_markdown_safe,
    generate_obsidian_vault_plan,
)
from app.services.secret_patterns import contains_secret_value

ROOT = Path(__file__).resolve().parents[1]


def test_sources_ui_has_guided_flow_and_run_detail_chain() -> None:
    html = (ROOT / "app" / "static" / "founder_ui.html").read_text(encoding="utf-8")
    for marker in (
        "PILOT_INFO",
        "Connector E2E runbook",
        "Stage:",  # per-connector guided next step
        "FOUNDEROS_ENABLE_REAL_CONNECTORS=true",  # banner step 2 (static)
        "adapter: ",  # run detail chain
        "real exec: ",
        "stage: ",
        "audit refs:",
        "next_command",
    ):
        assert marker in html, marker


def test_run_detail_request_model_includes_state_before_after() -> None:
    # The read-model exposes connector state before/after for the E2E chain.
    from app.services import source_control

    src = Path(source_control.__file__).read_text(encoding="utf-8")
    assert '"source_state_before": row.source_state_before' in src
    assert '"source_state_after": row.source_state_after' in src


def test_pilot_script_documents_safety() -> None:
    docs = (ROOT / "docs" / "source-connectors.md").read_text(encoding="utf-8")
    assert "Local Connector Pilot" in docs
    assert "run_local_connector_pilot.py" in docs
    assert "No writes to Jira, GitHub, or Gmail" in docs
    bridge = (ROOT / "docs" / "obsidian-bridge.md").read_text(encoding="utf-8")
    assert "Local Pilot.md" in bridge


async def test_obsidian_local_pilot_note_generated_and_safe() -> None:
    async with AsyncSessionLocal() as session:
        plan = await generate_obsidian_vault_plan(session)
    paths = {note.path for note in plan.notes}
    assert "_System/Local Pilot.md" in paths

    pilot = next(n for n in plan.notes if n.path == "_System/Local Pilot.md")
    assert "## Этапы конвейера" in pilot.markdown
    assert "## Следующие шаги" in pilot.markdown
    assert "Реальные коннекторы включены (real connectors enabled):" in pilot.markdown

    jira = next(n for n in plan.notes if n.path == "Sources/Jira.md")
    assert "Этап конвейера (pipeline stage):" in jira.markdown
    assert "Следующее действие (next action):" in jira.markdown

    connector_notes = [n for n in plan.notes if n.node_type == "connector_diagnostics"]
    blob = "\n".join(n.markdown for n in connector_notes)
    for forbidden in ("ghp_", "sk-", "raw://", "dev_api_key"):
        assert forbidden not in blob
    for note in connector_notes:
        _assert_markdown_safe(note.markdown)


async def test_adversarial_secret_shaped_env_does_not_leak(monkeypatch) -> None:
    secret = "ghp_STAGE16ADVERSARIAL1234567890abcd"
    monkeypatch.setenv("JIRA_BASE_URL", "https://example.atlassian.net")
    monkeypatch.setenv("JIRA_EMAIL", "ops@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", secret)
    monkeypatch.setenv("GITHUB_TOKEN", secret)
    os.environ.setdefault("GITHUB_REPOS", "owner/repo")
    from app.services.connector_diagnostics import build_connector_diagnostics

    async with AsyncSessionLocal() as session:
        diagnostics = await build_connector_diagnostics(session)
        plan = await generate_obsidian_vault_plan(session)
    dblob = json.dumps(diagnostics)
    mblob = "\n".join(n.markdown for n in plan.notes)
    assert secret not in dblob
    assert secret not in mblob
    assert not contains_secret_value(dblob)
