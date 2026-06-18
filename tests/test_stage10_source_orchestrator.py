from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.core.config import settings as app_settings
from app.db.base import AsyncSessionLocal, engine
from app.db.event_models import SourceEvent
from app.db.models import AuditLog
from app.db.models import IngestedEvent
from app.db.source_control_models import SourceControlState, SourceRunRequest
from app.main import app
from app.services.source_connectors import (
    CONNECTOR_STATUS_FAILED,
    CONNECTOR_STATUS_SUCCEEDED,
    ConnectorReadiness,
    ConnectorRunResult,
    NoopSourceConnector,
    default_connector_registry,
)
from app.services.source_run_orchestrator import (
    REQUEST_STATUS_FAILED,
    REQUEST_STATUS_REQUESTED,
    REQUEST_STATUS_SUCCEEDED,
    run_source_request,
    run_source_requests,
)


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _ensure_tables() -> None:
    async with engine.begin() as conn:
        for table in (
            AuditLog.__table__,
            IngestedEvent.__table__,
            SourceEvent.__table__,
            SourceControlState.__table__,
            SourceRunRequest.__table__,
        ):
            await conn.run_sync(table.create, checkfirst=True)


async def _state_snapshot(source_type: str) -> dict | None:
    async with AsyncSessionLocal() as session:
        row = await session.scalar(
            select(SourceControlState).where(SourceControlState.source_type == source_type)
        )
        if row is None:
            return None
        return {
            "source_type": row.source_type,
            "status": row.status,
            "paused": row.paused,
            "last_action": row.last_action,
            "last_action_at": row.last_action_at,
            "last_action_by": row.last_action_by,
            "last_request_key": row.last_request_key,
            "last_sync_at": row.last_sync_at,
            "last_success_at": row.last_success_at,
            "last_error_at": row.last_error_at,
            "input_watermark": row.input_watermark,
            "latest_run_id": row.latest_run_id,
            "config_status": row.config_status,
        }


async def _restore_state(source_type: str, snapshot: dict | None) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(SourceControlState).where(SourceControlState.source_type == source_type)
        )
        if snapshot is not None:
            session.add(SourceControlState(**snapshot))
        await session.commit()


async def _cleanup(marker: str) -> None:
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(SourceRunRequest).where(
                    SourceRunRequest.request_key.like(f"%{marker}%")
                )
            )
        ).scalars().all()
        refs = {
            value
            for row in rows
            for value in (row.request_id, row.run_id, row.correlation_id)
            if value
        }
        for ref in refs:
            await session.execute(
                delete(AuditLog).where(
                    (AuditLog.correlation_id == ref)
                    | (AuditLog.trace_id == ref)
                    | (AuditLog.after_ref == f"source_run_request:{ref}")
                )
            )
        await session.execute(
            delete(AuditLog).where(
                AuditLog.payload["request_key"].as_string().like(f"%{marker}%")
            )
        )
        await session.execute(
            delete(SourceEvent).where(SourceEvent.source_event_id.like(f"%{marker}%"))
        )
        await session.execute(
            delete(IngestedEvent).where(IngestedEvent.event_id.like(f"%{marker}%"))
        )
        await session.execute(
            delete(SourceRunRequest).where(SourceRunRequest.request_key.like(f"%{marker}%"))
        )
        await session.commit()


def _request(
    *,
    marker: str,
    source_type: str = "manual_inputs",
    action_type: str = "sync",
    status: str = REQUEST_STATUS_REQUESTED,
) -> SourceRunRequest:
    request_id = f"src_req_stage10_{marker}_{uuid4().hex[:8]}"
    return SourceRunRequest(
        request_id=request_id,
        source_type=source_type,
        action_type=action_type,
        status=status,
        request_key=f"{source_type}-{action_type}-{marker}",
        correlation_id=request_id,
        idempotency_key=f"{source_type}:{action_type}:{marker}",
        requested_by="founder",
        requested_at=datetime(2026, 6, 13, tzinfo=timezone.utc),
        created_at=datetime(2000, 1, 1, tzinfo=timezone.utc),
        input_snapshot={"input": {"limit": 10}},
        result_summary={},
        error_summary={},
        external_side_effect=False,
    )


@dataclass
class FakeConnector:
    source_type: str = "manual_inputs"
    status: str = CONNECTOR_STATUS_SUCCEEDED
    calls: int = 0
    fail: bool = False
    token_value: str = "NEVER-RETURN-THIS-TOKEN"

    async def readiness(self) -> ConnectorReadiness:
        return ConnectorReadiness(
            source_type=self.source_type,
            configured=True,
            missing_env_vars=[],
            masked_config_status=[{"name": "FAKE_TOKEN", "status": "masked"}],
            can_test=True,
            can_sync=True,
            can_backfill=True,
        )

    async def test_connection(self) -> ConnectorRunResult:
        return await self._result("test")

    async def sync(self, watermark: str | None = None) -> ConnectorRunResult:
        return await self._result("sync", watermark=watermark)

    async def backfill(
        self,
        *,
        since: str | None = None,
        until: str | None = None,
        limit: int | None = None,
    ) -> ConnectorRunResult:
        return await self._result("backfill")

    async def _result(
        self,
        action_type: str,
        *,
        watermark: str | None = None,
    ) -> ConnectorRunResult:
        self.calls += 1
        if self.fail:
            raise RuntimeError(self.token_value)
        started = datetime(2026, 6, 13, tzinfo=timezone.utc)
        finished = datetime(2026, 6, 13, 0, 0, 1, tzinfo=timezone.utc)
        return ConnectorRunResult(
            status=self.status,
            source_type=self.source_type,
            action_type=action_type,
            started_at=started,
            finished_at=finished,
            input_watermark=watermark,
            output_watermark="wm-stage10",
            events_seen=1,
            events_ingested=1,
            normalized_events=1,
            graph_updates=0,
            findings_generated=0,
            proposals_generated=0,
            external_side_effect=False,
            sanitized_summary={"mode": "fake", "token": "***redacted***"},
        )


async def test_queued_source_request_executes_and_audits_terminal_status() -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    snapshot = await _state_snapshot("manual_inputs")
    connector = FakeConnector()
    try:
        async with AsyncSessionLocal() as session:
            request = _request(marker=marker)
            session.add(request)
            await session.flush()

            result = await run_source_request(
                session,
                request=request,
                connectors={"manual_inputs": connector},
                run_id=f"src_run_{marker}",
                now=datetime(2026, 6, 13, tzinfo=timezone.utc),
            )
            await session.commit()

        assert result["status"] == REQUEST_STATUS_SUCCEEDED
        assert connector.calls == 1
        async with AsyncSessionLocal() as session:
            saved = await session.scalar(
                select(SourceRunRequest).where(SourceRunRequest.request_key.like(f"%{marker}%"))
            )
            state = await session.scalar(
                select(SourceControlState).where(
                    SourceControlState.source_type == "manual_inputs"
                )
            )
            audits = (
                await session.execute(
                    select(AuditLog).where(
                        AuditLog.correlation_id == saved.correlation_id
                    )
                )
            ).scalars().all()
        assert saved is not None
        assert saved.status == REQUEST_STATUS_SUCCEEDED
        assert saved.run_id == f"src_run_{marker}"
        assert saved.started_at is not None
        assert saved.finished_at is not None
        assert saved.result_summary["external_side_effect"] is False
        assert saved.result_summary["sanitized_summary"]["token"] == "***redacted***"
        assert state is not None
        assert state.last_success_at is not None
        assert state.last_sync_at is not None
        assert state.input_watermark == "wm-stage10"
        assert {audit.event_type for audit in audits} >= {
            "source_run_started",
            "source_run_finished",
        }
    finally:
        await _cleanup(marker)
        await _restore_state("manual_inputs", snapshot)


async def test_completed_request_is_not_executed_again() -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    snapshot = await _state_snapshot("manual_inputs")
    connector = FakeConnector()
    try:
        async with AsyncSessionLocal() as session:
            request = _request(marker=marker, status=REQUEST_STATUS_SUCCEEDED)
            request.result_summary = {"status": "succeeded"}
            session.add(request)
            await session.flush()
            result = await run_source_request(
                session,
                request=request,
                connectors={"manual_inputs": connector},
            )
            await session.commit()
        assert result["status"] == "unchanged"
        assert connector.calls == 0
    finally:
        await _cleanup(marker)
        await _restore_state("manual_inputs", snapshot)


async def test_paused_source_blocks_sync_without_adapter_call() -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    snapshot = await _state_snapshot("manual_inputs")
    connector = FakeConnector()
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(
                delete(SourceControlState).where(
                    SourceControlState.source_type == "manual_inputs"
                )
            )
            session.add(
                SourceControlState(
                    source_type="manual_inputs",
                    status="disabled",
                    paused=True,
                    last_request_key=f"state-{marker}",
                )
            )
            request = _request(marker=marker)
            session.add(request)
            await session.flush()
            result = await run_source_request(
                session,
                request=request,
                connectors={"manual_inputs": connector},
            )
            await session.commit()
        assert result["status"] == "skipped_paused"
        assert connector.calls == 0
        async with AsyncSessionLocal() as session:
            saved = await session.scalar(
                select(SourceRunRequest).where(SourceRunRequest.request_key.like(f"%{marker}%"))
            )
        assert saved is not None
        assert saved.status == "blocked"
        assert saved.result_summary["reason"] == "source_paused"
    finally:
        await _cleanup(marker)
        await _restore_state("manual_inputs", snapshot)


async def test_paused_source_allows_safe_test_connection() -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    snapshot = await _state_snapshot("manual_inputs")
    connector = FakeConnector()
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(
                delete(SourceControlState).where(
                    SourceControlState.source_type == "manual_inputs"
                )
            )
            session.add(
                SourceControlState(
                    source_type="manual_inputs",
                    status="disabled",
                    paused=True,
                    last_request_key=f"state-{marker}",
                )
            )
            request = _request(
                marker=marker,
                source_type="manual_inputs",
                action_type="test",
            )
            session.add(request)
            await session.flush()
            result = await run_source_request(
                session,
                request=request,
                connectors={"manual_inputs": connector},
            )
            await session.commit()
        assert result["status"] == REQUEST_STATUS_SUCCEEDED
        assert connector.calls == 1
    finally:
        await _cleanup(marker)
        await _restore_state("manual_inputs", snapshot)


async def test_invalid_persisted_request_blocks_without_creating_source_state() -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    invalid_source = f"unknown_{marker}"
    try:
        async with AsyncSessionLocal() as session:
            request = _request(marker=marker, source_type=invalid_source)
            session.add(request)
            await session.flush()
            result = await run_source_request(session, request=request)
            await session.commit()
        assert result["status"] == "blocked_invalid"
        async with AsyncSessionLocal() as session:
            state = await session.scalar(
                select(SourceControlState).where(
                    SourceControlState.source_type == invalid_source
                )
            )
            saved = await session.scalar(
                select(SourceRunRequest).where(
                    SourceRunRequest.request_key.like(f"%{marker}%")
                )
            )
        assert state is None
        assert saved is not None
        assert saved.status == "blocked"
        assert saved.result_summary["reason"] == "unknown_source_or_action"
    finally:
        await _cleanup(marker)


async def test_missing_config_result_is_sanitized(monkeypatch) -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    snapshot = await _state_snapshot("jira")
    secret_value = "LEAKED-JIRA-STAGE10-VALUE"
    monkeypatch.delenv("JIRA_BASE_URL", raising=False)
    monkeypatch.delenv("JIRA_EMAIL", raising=False)
    monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
    monkeypatch.setattr(app_settings, "jira_base_url", None)
    monkeypatch.setattr(app_settings, "jira_email", None)
    monkeypatch.setattr(app_settings, "jira_api_token", secret_value)
    # Token alone is not enough; the result may name missing fields but not values.
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(
                delete(SourceControlState).where(SourceControlState.source_type == "jira")
            )
            request = _request(marker=marker, source_type="jira")
            session.add(request)
            await session.flush()
            result = await run_source_request(session, request=request)
            await session.commit()
        assert result["status"] == "skipped"
        async with AsyncSessionLocal() as session:
            saved = await session.scalar(
                select(SourceRunRequest).where(SourceRunRequest.request_key.like(f"%{marker}%"))
            )
        assert saved is not None
        blob = json.dumps(saved.result_summary)
        assert saved.result_summary["status"] == "missing_config"
        assert "JIRA_BASE_URL" in blob
        assert "JIRA_EMAIL" in blob
        assert secret_value not in blob
        assert saved.external_side_effect is False
    finally:
        await _cleanup(marker)
        await _restore_state("jira", snapshot)


async def test_adapter_exception_fails_closed_without_secret_value() -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    snapshot = await _state_snapshot("manual_inputs")
    connector = FakeConnector(fail=True)
    try:
        async with AsyncSessionLocal() as session:
            request = _request(marker=marker)
            session.add(request)
            await session.flush()
            result = await run_source_request(
                session,
                request=request,
                connectors={"manual_inputs": connector},
            )
            await session.commit()
        assert result["status"] == REQUEST_STATUS_FAILED
        async with AsyncSessionLocal() as session:
            saved = await session.scalar(
                select(SourceRunRequest).where(SourceRunRequest.request_key.like(f"%{marker}%"))
            )
        assert saved is not None
        blob = json.dumps({"result": saved.result_summary, "error": saved.error_summary})
        assert saved.status == REQUEST_STATUS_FAILED
        assert "connector adapter failed" in blob
        assert connector.token_value not in blob
    finally:
        await _cleanup(marker)
        await _restore_state("manual_inputs", snapshot)


async def test_run_source_requests_summary_buckets(monkeypatch) -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    manual_snapshot = await _state_snapshot("manual_inputs")
    github_snapshot = await _state_snapshot("github")
    jira_snapshot = await _state_snapshot("jira")
    monkeypatch.delenv("JIRA_BASE_URL", raising=False)
    monkeypatch.delenv("JIRA_EMAIL", raising=False)
    monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
    monkeypatch.setattr(app_settings, "jira_base_url", None)
    monkeypatch.setattr(app_settings, "jira_email", None)
    monkeypatch.setattr(app_settings, "jira_api_token", None)
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(
                delete(SourceControlState).where(
                    SourceControlState.source_type.in_(["manual_inputs", "github", "jira"])
                )
            )
            session.add(
                SourceControlState(
                    source_type="github",
                    status="disabled",
                    paused=True,
                    last_request_key=f"state-{marker}",
                )
            )
            session.add(_request(marker=f"{marker}-ok", source_type="manual_inputs"))
            session.add(_request(marker=f"{marker}-paused", source_type="github"))
            session.add(_request(marker=f"{marker}-missing", source_type="jira"))
            await session.flush()
            connectors = default_connector_registry()
            connectors["manual_inputs"] = FakeConnector()
            summary = await run_source_requests(
                session,
                connectors=connectors,
                limit=10,
                now=datetime(2026, 6, 13, tzinfo=timezone.utc),
            )
            await session.commit()
        assert summary["requested"] >= 3
        assert summary["started"] >= 2
        assert summary["succeeded"] >= 1
        assert summary["skipped_paused"] >= 1
        assert summary["skipped_missing_config"] >= 1
        assert summary["errors"] == 0
        assert summary["run_id"].startswith("src_orch_")
    finally:
        await _cleanup(marker)
        await _restore_state("manual_inputs", manual_snapshot)
        await _restore_state("github", github_snapshot)
        await _restore_state("jira", jira_snapshot)


async def test_connector_readiness_masks_secret_values(monkeypatch) -> None:
    secret_value = "LEAKED-GITHUB-STAGE10-VALUE"
    monkeypatch.setenv("GITHUB_TOKEN", secret_value)
    connector = NoopSourceConnector("github")
    readiness = await connector.readiness()
    result = await connector.sync(watermark="wm-in")
    blob = json.dumps({"readiness": readiness.to_dict(), "result": result.to_dict()})
    assert readiness.configured is True
    assert "GITHUB_TOKEN" in blob
    assert "masked" in blob
    assert secret_value not in blob
    assert result.external_side_effect is False
    assert result.status in {"skipped", CONNECTOR_STATUS_FAILED}


async def test_source_runs_endpoint_is_founder_only_and_redacted(monkeypatch) -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    snapshot = await _state_snapshot("manual_inputs")
    try:
        async with AsyncSessionLocal() as session:
            request = _request(marker=marker)
            request.run_id = f"src_run_{marker}"
            request.started_at = datetime(2026, 6, 13, tzinfo=timezone.utc)
            request.finished_at = datetime(2026, 6, 13, 0, 0, 1, tzinfo=timezone.utc)
            request.status = REQUEST_STATUS_SUCCEEDED
            request.result_summary = {
                "status": "succeeded",
                "external_side_effect": False,
                "sanitized_summary": {"mode": "test"},
            }
            session.add(request)
            await session.commit()

        async with _client() as client:
            founder = await client.get(
                "/v1/founder/source-runs",
                params={"source_type": "manual_inputs", "limit": 10},
            )
            team = await client.get(
                "/v1/founder/source-runs",
                params={"view": "team"},
            )
        assert founder.status_code == 200
        assert team.status_code == 403
        blob = json.dumps(founder.json())
        assert f"src_run_{marker}" in blob
        assert "TOKEN" not in blob
    finally:
        await _cleanup(marker)
        await _restore_state("manual_inputs", snapshot)


async def test_source_events_can_filter_by_run_id() -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    try:
        async with AsyncSessionLocal() as session:
            session.add(
                IngestedEvent(
                    event_id=f"ie-stage10-run-{marker}",
                    event_type="jira.issue.updated",
                    source_system="jira",
                    source_object_id=f"ALPHA-{marker}",
                    idempotency_key=f"idem-stage10-run-{marker}",
                    correlation_id=f"corr-stage10-run-{marker}",
                    trace_id=f"trace-stage10-run-{marker}",
                    raw_object_ref=f"raw://jira/{marker}",
                    payload={"title": "Project Alpha event"},
                    status="received",
                )
            )
            await session.flush()
            session.add(
                SourceEvent(
                    source_event_id=f"sevt-stage10-run-{marker}",
                    source_event_key=f"sevt-key-stage10-run-{marker}",
                    ingested_event_id=f"ie-stage10-run-{marker}",
                    event_type="jira.issue.updated",
                    source_system="jira",
                    source_object_type="issue",
                    source_object_id=f"ALPHA-{marker}",
                    title="Project Alpha event",
                    raw_object_ref=f"raw://jira/{marker}",
                    created_by_run_id=f"src_run_{marker}",
                )
            )
            await session.commit()

        async with _client() as client:
            match = await client.get(
                "/v1/source-events",
                params={"source_type": "jira", "run_id": f"src_run_{marker}"},
            )
            miss = await client.get(
                "/v1/source-events",
                params={"source_type": "jira", "run_id": f"src_run_other_{marker}"},
            )
        assert match.status_code == 200
        assert miss.status_code == 200
        assert [
            event["source_event_id"]
            for event in match.json()["events"]
            if event["source_event_id"] == f"sevt-stage10-run-{marker}"
        ] == [f"sevt-stage10-run-{marker}"]
        assert f"sevt-stage10-run-{marker}" not in json.dumps(miss.json())
    finally:
        await _cleanup(marker)


async def test_data_quality_includes_source_run_lifecycle_issues(monkeypatch) -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    manual_snapshot = await _state_snapshot("manual_inputs")
    github_snapshot = await _state_snapshot("github")
    monkeypatch.delenv("JIRA_BASE_URL", raising=False)
    monkeypatch.delenv("JIRA_EMAIL", raising=False)
    monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
    monkeypatch.setattr(app_settings, "jira_base_url", None)
    monkeypatch.setattr(app_settings, "jira_email", None)
    monkeypatch.setattr(app_settings, "jira_api_token", None)
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(
                delete(SourceControlState).where(
                    SourceControlState.source_type.in_(["manual_inputs", "github"])
                )
            )
            failed = _request(marker=marker, source_type="manual_inputs")
            failed.status = REQUEST_STATUS_FAILED
            failed.run_id = f"src_run_failed_{marker}"
            failed.started_at = datetime(2026, 6, 13, tzinfo=timezone.utc)
            failed.finished_at = datetime(2026, 6, 13, 0, 0, 1, tzinfo=timezone.utc)
            failed.created_at = datetime(2099, 1, 1, tzinfo=timezone.utc)
            failed.result_summary = {
                "status": CONNECTOR_STATUS_FAILED,
                "external_side_effect": False,
                "sanitized_summary": {"mode": "failed"},
            }
            session.add(failed)
            session.add(
                SourceControlState(
                    source_type="github",
                    status="disabled",
                    paused=True,
                    last_request_key=f"state-{marker}",
                )
            )
            session.add(
                IngestedEvent(
                    event_id=f"ie-stage10-{marker}",
                    event_type="stage10.unmapped",
                    source_system=f"stage10_source_{marker}",
                    source_object_id=f"obj-{marker}",
                    idempotency_key=f"idem-stage10-{marker}",
                    correlation_id=f"corr-stage10-{marker}",
                    trace_id=f"trace-stage10-{marker}",
                    raw_object_ref=f"raw://stage10/{marker}",
                    payload={"title": "Project Alpha source event"},
                    status="received",
                )
            )
            await session.flush()
            session.add(
                SourceEvent(
                    source_event_id=f"sevt-stage10-{marker}",
                    source_event_key=f"sevt-key-stage10-{marker}",
                    ingested_event_id=f"ie-stage10-{marker}",
                    event_type="stage10.unmapped",
                    source_system=f"stage10_source_{marker}",
                    source_object_type="item",
                    source_object_id=f"obj-{marker}",
                    title="Project Alpha source event",
                    raw_object_ref=f"raw://stage10/{marker}",
                    created_by_run_id=f"src_run_failed_{marker}",
                )
            )
            await session.commit()

        async with _client() as client:
            response = await client.get("/v1/founder/data-quality")
        assert response.status_code == 200
        body = response.json()
        issues = body["issues"]
        categories = {issue["category"] for issue in issues}
        assert "source_missing_config" in categories
        assert "source_failed_last_run" in categories
        assert "source_paused_with_stale_data" in categories
        assert "source_events_not_normalized" in categories
        failed_issue = next(
            issue
            for issue in issues
            if issue["category"] == "source_failed_last_run"
            and issue["affected_source"] == "manual_inputs"
        )
        assert failed_issue["related_run_id"] == f"src_run_failed_{marker}"
        assert failed_issue["related_request_id"] == failed.request_id
    finally:
        await _cleanup(marker)
        await _restore_state("manual_inputs", manual_snapshot)
        await _restore_state("github", github_snapshot)
