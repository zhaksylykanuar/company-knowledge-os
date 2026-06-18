from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import httpx

from app.core.config import settings as app_settings
from app.db.base import AsyncSessionLocal
from app.services.source_connectors import ConnectorEvent, NoopSourceConnector
from scripts.run_local_connector_pilot import run_pilot
from tests.test_stage11_connector_ingestion import _ensure_tables
from tests.test_stage12_obsidian_bridge import _enable_bridge

ROOT = Path(__file__).resolve().parents[1]


class _FakeClient:
    def __init__(self, marker: str) -> None:
        self.marker = marker
        self.calls = 0

    async def test_connection(self, source_type: str) -> dict:
        self.calls += 1
        return {"status": "ok", "source_type": source_type}

    async def sync_events(self, source_type, *, watermark=None):
        self.calls += 1
        if source_type == "jira":
            return [
                ConnectorEvent(
                    source_type="jira",
                    external_id=f"jira-{self.marker}",
                    object_type="issue",
                    event_type="jira.issue.updated",
                    occurred_at=datetime(2026, 6, 14, tzinfo=timezone.utc),
                    title="Pilot issue",
                    summary="pilot",
                    url=f"https://example.atlassian.net/browse/PILOT-{self.marker}",
                )
            ]
        return [
            ConnectorEvent(
                source_type="github",
                external_id=f"owner/repo#pull/{self.marker}",
                object_type="pull_request",
                event_type="github.pull_request.synchronized",
                occurred_at=datetime(2026, 6, 14, tzinfo=timezone.utc),
                title="Pilot PR",
                summary="pilot",
                url=f"https://github.com/owner/repo/pull/{self.marker}",
            )
        ]

    async def backfill_events(self, source_type, *, since=None, until=None, limit=None):
        return await self.sync_events(source_type)


def test_pilot_requires_confirm_run() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/run_local_connector_pilot.py", "--confirm-run", "WRONG"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["status"] == "blocked"
    assert payload["external_side_effect"] is False


async def test_pilot_disabled_makes_no_external_calls(monkeypatch) -> None:
    await _ensure_tables()
    monkeypatch.setattr(app_settings, "enable_real_connectors", False)
    monkeypatch.setenv("JIRA_BASE_URL", "https://example.atlassian.net")
    monkeypatch.setenv("JIRA_EMAIL", "ops@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "stage16-fake-token-value")
    # Any network attempt fails the test.
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("network attempted")),
    )
    async with AsyncSessionLocal() as session:
        summary = await run_pilot(
            session, run_key=uuid4().hex[:8], evidence_limit=5
        )
        await session.rollback()
    assert summary["real_execution_enabled"] is False
    assert summary["test_requests_created"] == 0
    assert summary["sync_requests_created"] == 0
    assert summary["obsidian_notes_updated"] == 0
    assert summary["next_steps"]
    # Warnings name the source, never a secret value.
    blob = json.dumps(summary)
    assert "stage16-fake-token-value" not in blob


async def test_pilot_enabled_fake_clients_create_requests(monkeypatch) -> None:
    await _ensure_tables()
    monkeypatch.setattr(app_settings, "enable_real_connectors", True)
    for name, value in (
        ("JIRA_BASE_URL", "https://example.atlassian.net"),
        ("JIRA_EMAIL", "ops@example.com"),
        ("JIRA_API_TOKEN", "stage16-fake-token-value"),
        ("GITHUB_TOKEN", "stage16-fake-token-value"),
        ("FOUNDEROS_JIRA_PROJECT_KEYS", "QS"),  # explicit scopes for sync
        ("FOUNDEROS_GITHUB_REPOS", "owner/repo"),
    ):
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("network attempted")),
    )
    marker = uuid4().hex[:8]
    async with AsyncSessionLocal() as session:
        connectors = {
            "jira": NoopSourceConnector(
                "jira", session=session, client=_FakeClient(marker)
            ),
            "github": NoopSourceConnector(
                "github", session=session, client=_FakeClient(marker)
            ),
        }
        summary = await run_pilot(
            session,
            run_key=marker,
            connectors=connectors,
            evidence_limit=5,
        )
        await session.rollback()
    assert summary["test_requests_created"] == 2
    assert summary["source_runs_succeeded"] >= 2
    assert summary["sync_requests_created"] >= 2
    assert summary["events_ingested"] >= 2
    assert summary["source_runs_skipped_real_disabled"] == 0
    assert "stage16-fake-token-value" not in json.dumps(summary)


async def test_pilot_obsidian_write_only_with_flag(monkeypatch, tmp_path) -> None:
    await _ensure_tables()
    monkeypatch.setattr(app_settings, "enable_real_connectors", False)
    _enable_bridge(monkeypatch, tmp_path)
    async with AsyncSessionLocal() as session:
        no_write = await run_pilot(
            session, run_key=uuid4().hex[:8], sync_obsidian=False, evidence_limit=5
        )
        await session.rollback()
    assert no_write["obsidian_notes_would_update"] >= 1
    assert no_write["obsidian_notes_updated"] == 0
    assert not (tmp_path / "00 Index.md").exists()

    async with AsyncSessionLocal() as session:
        with_write = await run_pilot(
            session, run_key=uuid4().hex[:8], sync_obsidian=True, evidence_limit=5
        )
        await session.rollback()
    assert with_write["obsidian_notes_updated"] >= 1
    assert (tmp_path / "00 Index.md").exists()
