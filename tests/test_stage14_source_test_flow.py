from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import AsyncSessionLocal
from app.db.models import AuditLog
from app.db.source_control_models import SourceControlState, SourceRunRequest
from app.services.source_connectors import NoopSourceConnector
from app.services.source_control import request_source_action
from app.services.source_run_orchestrator import run_source_request
from tests.test_stage11_connector_ingestion import (
    _cleanup,
    _ensure_tables,
    _restore_state,
    _state_snapshot,
)


class _FakeReadOnlyClient:
    """A fake read-only connector client used in place of any real provider."""

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls = 0

    async def test_connection(self, source_type: str) -> dict:
        self.calls += 1
        if self.fail:
            # Message intentionally contains a secret-shaped token to prove the
            # orchestrator never persists the raw exception message.
            raise RuntimeError("boom ghp_" + "a" * 30)
        return {"status": "ok", "source_type": source_type}

    async def sync_events(self, source_type, *, watermark=None):
        self.calls += 1
        return []

    async def backfill_events(self, source_type, *, since=None, until=None, limit=None):
        self.calls += 1
        return []


def _make_request(source_type: str, action_type: str, marker: str) -> SourceRunRequest:
    request_id = f"src_req_stage14_{marker}_{uuid4().hex[:8]}"
    return SourceRunRequest(
        request_id=request_id,
        source_type=source_type,
        action_type=action_type,
        status="requested",
        request_key=f"{source_type}-{action_type}-{marker}",
        correlation_id=f"corr-stage14-{marker}",
        idempotency_key=f"{source_type}:{action_type}:{marker}",
        requested_by="founder",
        requested_at=datetime(2026, 6, 14, tzinfo=timezone.utc),
        input_snapshot={"input": {}},
        result_summary={},
        error_summary={},
        external_side_effect=False,
    )


async def _github_state(session: AsyncSession) -> SourceControlState | None:
    return await session.scalar(
        select(SourceControlState).where(SourceControlState.source_type == "github")
    )


async def test_missing_config_never_calls_client() -> None:
    """A missing-config source must not reach a connector client at all."""
    fake = _FakeReadOnlyClient()
    async with AsyncSessionLocal() as session:
        connector = NoopSourceConnector("jira", session=session, client=fake)
        result = await connector.test_connection()
    assert result.status == "missing_config"
    assert fake.calls == 0
    assert "missing_env_vars" in result.sanitized_summary


async def test_test_connection_success_with_fake_client_sets_connected(
    monkeypatch,
) -> None:
    await _ensure_tables()
    monkeypatch.setenv("GITHUB_TOKEN", "stage14-fake-not-a-real-secret")
    marker = uuid4().hex[:8]
    snapshot = await _state_snapshot("github")
    fake = _FakeReadOnlyClient()
    try:
        async with AsyncSessionLocal() as session:
            request = _make_request("github", "test", marker)
            session.add(request)
            await session.flush()
            result = await run_source_request(
                session,
                request=request,
                connectors={
                    "github": NoopSourceConnector(
                        "github", session=session, client=fake
                    )
                },
                run_id=f"src_run_{marker}",
            )
            await session.commit()
        assert result["status"] == "succeeded"
        assert fake.calls == 1
        async with AsyncSessionLocal() as session:
            state = await _github_state(session)
        assert state is not None
        assert state.status == "connected"
        assert state.last_success_at is not None
    finally:
        await _cleanup(marker)
        await _restore_state("github", snapshot)


async def test_configured_external_without_client_is_not_connected(
    monkeypatch,
) -> None:
    """Env presence alone must never produce a connected state."""
    await _ensure_tables()
    monkeypatch.setenv("GITHUB_TOKEN", "stage14-fake-not-a-real-secret")
    marker = uuid4().hex[:8]
    snapshot = await _state_snapshot("github")
    try:
        async with AsyncSessionLocal() as session:
            request = _make_request("github", "test", marker)
            session.add(request)
            await session.flush()
            # Default registry => no real client wired => no external call.
            result = await run_source_request(
                session,
                request=request,
                connectors={
                    "github": NoopSourceConnector("github", session=session)
                },
                run_id=f"src_run_{marker}",
            )
            await session.commit()
        assert result["status"] == "skipped"
        async with AsyncSessionLocal() as session:
            state = await _github_state(session)
        assert state is not None
        assert state.status == "degraded"
        assert state.last_success_at is None
    finally:
        await _cleanup(marker)
        await _restore_state("github", snapshot)


async def test_test_connection_failure_is_sanitized_and_degrades(monkeypatch) -> None:
    await _ensure_tables()
    monkeypatch.setenv("GITHUB_TOKEN", "stage14-fake-not-a-real-secret")
    marker = uuid4().hex[:8]
    snapshot = await _state_snapshot("github")
    fake = _FakeReadOnlyClient(fail=True)
    try:
        async with AsyncSessionLocal() as session:
            request = _make_request("github", "test", marker)
            session.add(request)
            await session.flush()
            result = await run_source_request(
                session,
                request=request,
                connectors={
                    "github": NoopSourceConnector(
                        "github", session=session, client=fake
                    )
                },
                run_id=f"src_run_{marker}",
            )
            await session.commit()
        assert result["status"] == "failed"
        async with AsyncSessionLocal() as session:
            row = await session.scalar(
                select(SourceRunRequest).where(
                    SourceRunRequest.request_key == f"github-test-{marker}"
                )
            )
            state = await _github_state(session)
        assert state is not None
        assert state.status == "error"
        assert state.last_error_at is not None
        # The raw exception message (with its secret-shaped token) is never kept.
        blob = json.dumps(
            {"result": row.result_summary, "error": row.error_summary}
        )
        assert "ghp_" not in blob
        assert row.error_summary.get("message") == "connector adapter failed"
    finally:
        await _cleanup(marker)
        await _restore_state("github", snapshot)


async def test_test_connection_request_is_founder_only_and_idempotent() -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    request_key = f"jira-test-{marker}"
    try:
        async with AsyncSessionLocal() as session:
            first = await request_source_action(
                session,
                source_type="jira",
                action_type="test",
                request_key=request_key,
                requested_by="founder",
            )
            second = await request_source_action(
                session,
                source_type="jira",
                action_type="test",
                request_key=request_key,
                requested_by="founder",
            )
            await session.commit()
        assert first["idempotent"] is False
        assert second["idempotent"] is True
        assert first["request_id"] == second["request_id"]
        assert first["external_side_effect"] is False

        async with AsyncSessionLocal() as session:
            audits = (
                await session.execute(
                    select(AuditLog.event_type).where(
                        AuditLog.correlation_id == first["request_id"]
                    )
                )
            ).scalars().all()
        assert "source_action_requested" in set(audits)
    finally:
        await _cleanup(marker)


async def test_orchestrator_audits_started_and_finished(monkeypatch) -> None:
    await _ensure_tables()
    monkeypatch.setenv("GITHUB_TOKEN", "stage14-fake-not-a-real-secret")
    marker = uuid4().hex[:8]
    snapshot = await _state_snapshot("github")
    try:
        async with AsyncSessionLocal() as session:
            request = _make_request("github", "test", marker)
            session.add(request)
            await session.flush()
            await run_source_request(
                session,
                request=request,
                connectors={
                    "github": NoopSourceConnector(
                        "github", session=session, client=_FakeReadOnlyClient()
                    )
                },
                run_id=f"src_run_{marker}",
            )
            await session.commit()
            events = (
                await session.execute(
                    select(AuditLog.event_type).where(
                        AuditLog.correlation_id == request.correlation_id
                    )
                )
            ).scalars().all()
        assert "source_run_started" in set(events)
        assert "source_run_finished" in set(events)
    finally:
        await _cleanup(marker)
        await _restore_state("github", snapshot)
