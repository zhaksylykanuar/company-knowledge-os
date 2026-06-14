from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

import httpx

from app.core.config import settings as app_settings
from app.db.base import AsyncSessionLocal
from app.services.source_connectors import ConnectorEvent, NoopSourceConnector
from scripts.run_local_connector_pilot import run_pilot
from tests.test_stage11_connector_ingestion import _ensure_tables


class _FakeClient:
    async def test_connection(self, source_type: str) -> dict:
        return {"status": "ok", "source_type": source_type}

    async def sync_events(self, source_type, *, watermark=None):
        if source_type == "jira":
            return [
                ConnectorEvent(
                    source_type="jira",
                    external_id="jira-pilot-1",
                    object_type="issue",
                    event_type="jira.issue.updated",
                    occurred_at=datetime(2026, 6, 14, tzinfo=timezone.utc),
                    title="Pilot issue",
                    url="https://example.atlassian.net/browse/PILOT-1",
                )
            ]
        return [
            ConnectorEvent(
                source_type="github",
                external_id="owner/repo#pull/1",
                object_type="pull_request",
                event_type="github.pull_request.synchronized",
                occurred_at=datetime(2026, 6, 14, tzinfo=timezone.utc),
                title="Pilot PR",
                url="https://github.com/owner/repo/pull/1",
            )
        ]

    async def backfill_events(self, source_type, *, since=None, until=None, limit=None):
        return await self.sync_events(source_type)


def _no_network(monkeypatch) -> None:
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("network attempted")),
    )


def _configure_enabled(monkeypatch) -> None:
    monkeypatch.setattr(app_settings, "enable_real_connectors", True)
    for name, value in (
        ("JIRA_BASE_URL", "https://example.atlassian.net"),
        ("JIRA_EMAIL", "ops@example.com"),
        ("JIRA_API_TOKEN", "stage17-secret-shaped-token-value"),
        ("GITHUB_TOKEN", "stage17-secret-shaped-token-value"),
    ):
        monkeypatch.setenv(name, value)


async def test_pilot_missing_scope_prevents_sync(monkeypatch) -> None:
    await _ensure_tables()
    _configure_enabled(monkeypatch)
    monkeypatch.delenv("FOUNDEROS_JIRA_PROJECT_KEYS", raising=False)
    monkeypatch.delenv("FOUNDEROS_GITHUB_REPOS", raising=False)
    monkeypatch.delenv("GITHUB_REPOS", raising=False)
    _no_network(monkeypatch)
    marker = uuid4().hex[:8]
    async with AsyncSessionLocal() as session:
        connectors = {
            "jira": NoopSourceConnector("jira", session=session, client=_FakeClient()),
            "github": NoopSourceConnector(
                "github", session=session, client=_FakeClient()
            ),
        }
        summary = await run_pilot(
            session, run_key=marker, connectors=connectors, evidence_limit=5
        )
        await session.rollback()
    assert summary["test_requests_created"] == 2  # test exempt from scope
    assert summary["sync_requests_created"] == 0  # blocked by missing scope
    assert summary["skipped_missing_scope"] == 2
    assert summary["missing_scope_sources"] == 2
    assert any("missing scope" in w for w in summary["warnings"])
    assert "stage17-secret-shaped-token-value" not in json.dumps(summary)


async def test_pilot_with_scope_creates_sync(monkeypatch) -> None:
    await _ensure_tables()
    _configure_enabled(monkeypatch)
    monkeypatch.setenv("FOUNDEROS_JIRA_PROJECT_KEYS", "QS")
    monkeypatch.setenv("FOUNDEROS_GITHUB_REPOS", "owner/repo")
    _no_network(monkeypatch)
    marker = uuid4().hex[:8]
    async with AsyncSessionLocal() as session:
        connectors = {
            "jira": NoopSourceConnector("jira", session=session, client=_FakeClient()),
            "github": NoopSourceConnector(
                "github", session=session, client=_FakeClient()
            ),
        }
        summary = await run_pilot(
            session, run_key=marker, connectors=connectors, evidence_limit=5
        )
        await session.rollback()
    assert summary["scoped_sources"] == 2
    assert summary["sync_requests_created"] == 2
    assert summary["events_ingested"] >= 2
    assert summary["skipped_missing_scope"] == 0


async def test_pilot_preview_only_creates_no_requests(monkeypatch) -> None:
    await _ensure_tables()
    _configure_enabled(monkeypatch)
    monkeypatch.delenv("FOUNDEROS_JIRA_PROJECT_KEYS", raising=False)
    _no_network(monkeypatch)
    marker = uuid4().hex[:8]
    async with AsyncSessionLocal() as session:
        summary = await run_pilot(
            session, run_key=marker, preview_only=True, evidence_limit=5
        )
        await session.rollback()
    assert summary["preview_only"] is True
    assert summary["test_requests_created"] == 0
    assert summary["sync_requests_created"] == 0
    assert summary["obsidian_notes_updated"] == 0
    assert summary["limits_applied"]["sync_limit"] >= 1
    assert "stage17-secret-shaped-token-value" not in json.dumps(summary)
