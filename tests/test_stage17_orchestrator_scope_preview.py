from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import func, select

from app.core.config import settings as app_settings
from app.db.base import AsyncSessionLocal
from app.db.event_models import SourceEvent
from app.db.models import AuditLog
from app.db.source_control_models import SourceControlState, SourceRunRequest
from app.services.source_connectors import (
    CONNECTOR_STATUS_SUCCEEDED,
    ConnectorEvent,
    ConnectorReadiness,
    ConnectorRunResult,
    NoopSourceConnector,
)
from app.services.source_run_orchestrator import run_source_request
from tests.test_stage11_connector_ingestion import (
    _cleanup,
    _ensure_tables,
    _restore_state,
    _state_snapshot,
)


class _CountingConnector:
    """Fake SourceConnector that records whether it was invoked."""

    source_type = "jira"

    def __init__(self, marker: str = "fixed") -> None:
        self.marker = marker
        self.test_calls = 0
        self.sync_calls = 0
        self.backfill_calls = 0

    async def readiness(self) -> ConnectorReadiness:
        return ConnectorReadiness(
            source_type="jira",
            configured=True,
            missing_env_vars=[],
            masked_config_status=[{"name": "JIRA_API_TOKEN", "status": "masked"}],
            can_test=True,
            can_sync=True,
            can_backfill=True,
        )

    def _events(self) -> list[ConnectorEvent]:
        return [
            ConnectorEvent(
                source_type="jira",
                external_id=f"ALPHA-{self.marker}",
                object_type="issue",
                event_type="jira.issue.updated",
                occurred_at=datetime(2026, 6, 14, tzinfo=timezone.utc),
                title="Scoped issue",
                url=f"https://example.atlassian.net/browse/ALPHA-{self.marker}",
            )
        ]

    def _result(self, action_type: str, events: list[ConnectorEvent]) -> ConnectorRunResult:
        now = datetime(2026, 6, 14, tzinfo=timezone.utc)
        return ConnectorRunResult(
            status=CONNECTOR_STATUS_SUCCEEDED,
            source_type="jira",
            action_type=action_type,
            started_at=now,
            finished_at=now,
            events=events,
            events_seen=len(events),
            external_side_effect=False,
            sanitized_summary={"mode": "fake"},
        )

    async def test_connection(self) -> ConnectorRunResult:
        self.test_calls += 1
        return self._result("test", [])

    async def sync(self, watermark: str | None = None) -> ConnectorRunResult:
        self.sync_calls += 1
        return self._result("sync", self._events())

    async def backfill(self, *, since=None, until=None, limit=None) -> ConnectorRunResult:
        self.backfill_calls += 1
        return self._result("backfill", self._events())


def _request(action_type: str, marker: str) -> SourceRunRequest:
    return SourceRunRequest(
        request_id=f"src_req_s17_{marker}_{action_type}",
        source_type="jira",
        action_type=action_type,
        status="requested",
        request_key=f"jira-{action_type}-{marker}",
        requested_at=datetime(2026, 6, 14, tzinfo=timezone.utc),
        input_snapshot={"input": {}},
        result_summary={},
        error_summary={},
        external_side_effect=False,
    )


def _configure(monkeypatch, *, scope: bool) -> None:
    monkeypatch.setattr(app_settings, "enable_real_connectors", True)
    monkeypatch.setenv("JIRA_BASE_URL", "https://example.atlassian.net")
    monkeypatch.setenv("JIRA_EMAIL", "ops@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "stage17-secret-shaped-token-value")
    if scope:
        monkeypatch.setenv("FOUNDEROS_JIRA_PROJECT_KEYS", "QS")
    else:
        monkeypatch.delenv("FOUNDEROS_JIRA_PROJECT_KEYS", raising=False)


async def test_test_connection_runs_without_scope(monkeypatch) -> None:
    await _ensure_tables()
    _configure(monkeypatch, scope=False)
    marker = uuid4().hex[:8]
    snapshot = await _state_snapshot("jira")
    fake = _CountingConnector(marker)
    try:
        async with AsyncSessionLocal() as session:
            req = _request("test", marker)
            session.add(req)
            await session.flush()
            result = await run_source_request(
                session, request=req, connectors={"jira": fake}, run_id=f"r_{marker}"
            )
            await session.commit()
        assert result["status"] == "succeeded"
        assert fake.test_calls == 1
    finally:
        await _cleanup(marker)
        await _restore_state("jira", snapshot)


async def test_sync_blocked_without_scope_never_calls_connector(monkeypatch) -> None:
    await _ensure_tables()
    _configure(monkeypatch, scope=False)
    marker = uuid4().hex[:8]
    snapshot = await _state_snapshot("jira")
    fake = _CountingConnector(marker)
    try:
        async with AsyncSessionLocal() as session:
            req = _request("sync", marker)
            session.add(req)
            await session.flush()
            result = await run_source_request(
                session, request=req, connectors={"jira": fake}, run_id=f"r_{marker}"
            )
            row = await session.scalar(
                select(SourceRunRequest).where(
                    SourceRunRequest.request_key == f"jira-sync-{marker}"
                )
            )
            await session.commit()
        assert result["status"] == "blocked_missing_scope"
        assert fake.sync_calls == 0  # connector never invoked
        assert row.result_summary["blocked_reason"] == "missing_scope"
        assert "limits_applied" in row.result_summary
    finally:
        await _cleanup(marker)
        await _restore_state("jira", snapshot)


async def test_sync_proceeds_with_scope_and_includes_meta(monkeypatch) -> None:
    await _ensure_tables()
    _configure(monkeypatch, scope=True)
    marker = uuid4().hex[:8]
    snapshot = await _state_snapshot("jira")
    fake = _CountingConnector(marker)
    try:
        async with AsyncSessionLocal() as session:
            req = _request("sync", marker)
            session.add(req)
            await session.flush()
            result = await run_source_request(
                session, request=req, connectors={"jira": fake}, run_id=f"r_{marker}"
            )
            row = await session.scalar(
                select(SourceRunRequest).where(
                    SourceRunRequest.request_key == f"jira-sync-{marker}"
                )
            )
            await session.commit()
        assert result["status"] == "succeeded"
        assert fake.sync_calls == 1
        assert row.result_summary["scope_configured"] is True
        assert row.result_summary["scope_summary"]["count"] == 1
        assert row.result_summary["limits_applied"]["sync_limit"] >= 1
        assert not contains_secret(row.result_summary)
    finally:
        await _cleanup(marker)
        await _restore_state("jira", snapshot)


async def test_preview_blocked_without_scope(monkeypatch) -> None:
    await _ensure_tables()
    _configure(monkeypatch, scope=False)
    marker = uuid4().hex[:8]
    snapshot = await _state_snapshot("jira")
    fake = _CountingConnector(marker)
    try:
        async with AsyncSessionLocal() as session:
            req = _request("preview_sync", marker)
            session.add(req)
            await session.flush()
            result = await run_source_request(
                session, request=req, connectors={"jira": fake}, run_id=f"r_{marker}"
            )
            await session.commit()
        assert result["status"] == "blocked_missing_scope"
        assert fake.sync_calls == 0
    finally:
        await _cleanup(marker)
        await _restore_state("jira", snapshot)


async def test_preview_writes_no_source_events_and_audits(monkeypatch) -> None:
    await _ensure_tables()
    _configure(monkeypatch, scope=True)
    marker = uuid4().hex[:8]
    snapshot = await _state_snapshot("jira")
    fake = _CountingConnector(marker)
    try:
        async with AsyncSessionLocal() as session:
            req = _request("preview_sync", marker)
            session.add(req)
            await session.flush()
            result = await run_source_request(
                session, request=req, connectors={"jira": fake}, run_id=f"r_{marker}"
            )
            row = await session.scalar(
                select(SourceRunRequest).where(
                    SourceRunRequest.request_key == f"jira-preview_sync-{marker}"
                )
            )
            event_count = await session.scalar(
                select(func.count(SourceEvent.id)).where(
                    SourceEvent.source_object_id == f"ALPHA-{marker}"
                )
            )
            audits = (
                await session.execute(
                    select(AuditLog.event_type).where(
                        AuditLog.correlation_id == req.correlation_id
                    )
                )
            ).scalars().all()
            state = await session.scalar(
                select(SourceControlState).where(
                    SourceControlState.source_type == "jira"
                )
            )
            await session.commit()
        assert result["status"] == "succeeded"
        assert result["preview"] is True
        assert row.result_summary["preview"] is True
        assert row.result_summary["estimated_events"] == 1
        assert event_count == 0  # preview persists no source events
        assert "source_run_finished" in set(audits)
        # preview must not mark the source connected
        assert state is None or state.last_success_at is None
    finally:
        await _cleanup(marker)
        await _restore_state("jira", snapshot)


async def test_real_disabled_skips_before_scope(monkeypatch) -> None:
    await _ensure_tables()
    monkeypatch.setattr(app_settings, "enable_real_connectors", False)
    monkeypatch.setenv("JIRA_BASE_URL", "https://example.atlassian.net")
    monkeypatch.setenv("JIRA_EMAIL", "ops@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "stage17-secret-shaped-token-value")
    monkeypatch.delenv("FOUNDEROS_JIRA_PROJECT_KEYS", raising=False)
    marker = uuid4().hex[:8]
    snapshot = await _state_snapshot("jira")
    try:
        async with AsyncSessionLocal() as session:
            req = _request("sync", marker)
            session.add(req)
            await session.flush()
            # Default registry => jira real_disabled (no client), scope not consulted.
            result = await run_source_request(
                session,
                request=req,
                connectors={"jira": NoopSourceConnector("jira", session=session)},
                run_id=f"r_{marker}",
            )
            await session.commit()
        # Real disabled: scope is not consulted; the Noop skips (no external call).
        assert result["status"] == "skipped"
    finally:
        await _cleanup(marker)
        await _restore_state("jira", snapshot)


def contains_secret(value: object) -> bool:
    from app.services.secret_patterns import contains_secret_value

    return contains_secret_value(json.dumps(value))
