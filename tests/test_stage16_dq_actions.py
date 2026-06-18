from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import delete, select

from app.core.config import settings as app_settings
from app.db.base import AsyncSessionLocal
from app.db.source_control_models import SourceControlState, SourceRunRequest
from app.services.action_center import build_action_center
from app.services.data_quality_center import build_data_quality_center
from app.services.secret_patterns import contains_secret_value
from app.services.source_connectors import ConnectorEvent
from app.services.source_control import request_source_action
from app.services.source_run_orchestrator import run_source_request
from tests.test_stage11_connector_ingestion import _ensure_tables


def _sync_request(marker: str, *, events: int) -> SourceRunRequest:
    return SourceRunRequest(
        request_id=f"src_req_dq_{marker}",
        source_type="jira",
        action_type="sync",
        status="succeeded",
        request_key=f"jira-sync-{marker}",
        requested_at=datetime(2026, 6, 14, tzinfo=timezone.utc),
        finished_at=datetime(2026, 6, 14, tzinfo=timezone.utc),
        input_snapshot={"input": {}},
        result_summary={
            "status": "succeeded",
            "sanitized_summary": {"ingestion": {"events_ingested": events}},
        },
        error_summary={},
        external_side_effect=False,
    )


def _test_request(marker: str) -> SourceRunRequest:
    return SourceRunRequest(
        request_id=f"src_req_dq_test_{marker}",
        source_type="jira",
        action_type="test",
        status="succeeded",
        request_key=f"jira-test-{marker}",
        requested_at=datetime(2026, 6, 14, tzinfo=timezone.utc),
        finished_at=datetime(2026, 6, 14, tzinfo=timezone.utc),
        input_snapshot={"input": {}},
        result_summary={"status": "succeeded", "sanitized_summary": {"mode": "fake"}},
        error_summary={},
        external_side_effect=False,
    )


def _configure_jira(monkeypatch) -> None:
    monkeypatch.setenv("JIRA_BASE_URL", "https://example.atlassian.net")
    monkeypatch.setenv("JIRA_EMAIL", "ops@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "stage16-dq-fake-token-value")


async def test_dq_real_enabled_never_tested(monkeypatch) -> None:
    await _ensure_tables()
    monkeypatch.setattr(app_settings, "enable_real_connectors", True)
    _configure_jira(monkeypatch)
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(SourceControlState).where(SourceControlState.source_type == "jira")
        )
        await session.flush()
        center = await build_data_quality_center(session)
        await session.rollback()
    cats = {i["category"] for i in center["issues"]}
    assert "connector_real_enabled_never_tested" in cats


async def test_dq_tested_not_synced(monkeypatch) -> None:
    await _ensure_tables()
    monkeypatch.setattr(app_settings, "enable_real_connectors", False)
    _configure_jira(monkeypatch)
    marker = uuid4().hex[:8]
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(SourceControlState).where(SourceControlState.source_type == "jira")
        )
        session.add(
            SourceControlState(
                source_type="jira",
                status="connected",
                last_success_at=datetime(2026, 6, 14, tzinfo=timezone.utc),
            )
        )
        session.add(_test_request(marker))
        await session.flush()
        center = await build_data_quality_center(session)
        await session.rollback()
    cats = {i["category"] for i in center["issues"]}
    assert "connector_tested_not_synced" in cats


async def test_dq_synced_without_events(monkeypatch) -> None:
    await _ensure_tables()
    monkeypatch.setattr(app_settings, "enable_real_connectors", False)
    _configure_jira(monkeypatch)
    marker = uuid4().hex[:8]
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(SourceControlState).where(SourceControlState.source_type == "jira")
        )
        session.add(
            SourceControlState(
                source_type="jira",
                status="connected",
                last_success_at=datetime(2026, 6, 14, tzinfo=timezone.utc),
                last_sync_at=datetime(2026, 6, 14, tzinfo=timezone.utc),
            )
        )
        session.add(_sync_request(marker, events=0))
        await session.flush()
        center = await build_data_quality_center(session)
        await session.rollback()
    cats = {i["category"] for i in center["issues"]}
    assert "connector_synced_without_events" in cats


async def test_action_center_includes_connector_actions(monkeypatch) -> None:
    await _ensure_tables()
    monkeypatch.setattr(app_settings, "enable_real_connectors", False)
    async with AsyncSessionLocal() as session:
        center = await build_action_center(session)
    connector_actions = [a for a in center["actions"] if a["source"] == "connector"]
    assert connector_actions
    for action in connector_actions:
        assert action["group"]
        assert action["group_reason"]
        assert action["action_ref"]["kind"] in {"connector", "obsidian"}
    assert not contains_secret_value(json.dumps(center))


async def test_queued_request_is_not_succeeded_and_terminal_not_rerun(
    monkeypatch,
) -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    async with AsyncSessionLocal() as session:
        # A freshly requested action is queued, never "succeeded".
        requested = await request_source_action(
            session,
            source_type="declarations",
            action_type="test",
            request_key=f"dq-{marker}",
            requested_by="founder",
        )
        assert requested["status"] in {"requested", "accepted"}

        row = await session.scalar(
            select(SourceRunRequest).where(
                SourceRunRequest.request_id == requested["request_id"]
            )
        )

        class _Fake:
            source_type = "declarations"

            async def readiness(self):  # pragma: no cover - not used here
                raise NotImplementedError

            async def test_connection(self):
                from app.services.source_connectors import ConnectorRunResult

                now = datetime(2026, 6, 14, tzinfo=timezone.utc)
                return ConnectorRunResult(
                    status="succeeded",
                    source_type="declarations",
                    action_type="test",
                    started_at=now,
                    finished_at=now,
                    events=[],
                    external_side_effect=False,
                    sanitized_summary={"mode": "fake"},
                )

            async def sync(self, watermark=None):
                return await self.test_connection()

            async def backfill(self, *, since=None, until=None, limit=None):
                return await self.test_connection()

        first = await run_source_request(
            session, request=row, connectors={"declarations": _Fake()}, run_id=f"r_{marker}"
        )
        assert first["status"] == "succeeded"
        # A terminal request is never re-run.
        again = await run_source_request(
            session, request=row, connectors={"declarations": _Fake()}, run_id=f"r_{marker}"
        )
        assert again["status"] == "unchanged"
        await session.rollback()


def test_connector_event_has_no_raw_body() -> None:
    event = ConnectorEvent(
        source_type="jira",
        external_id="ALPHA-1",
        object_type="issue",
        event_type="jira.issue.updated",
    )
    payload = event.safe_payload()
    assert "body" not in json.dumps(payload).lower()
