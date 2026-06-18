from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.db.base import AsyncSessionLocal
from app.db.event_models import NormalizedActivityItemRecord, SourceEvent
from app.db.models import AuditLog, IngestedEvent
from app.db.source_control_models import SourceControlState, SourceRunRequest
from app.main import app
from app.services.action_center import build_action_center
from app.services.data_quality_center import build_data_quality_center
from app.services.obsidian_vault import generate_obsidian_vault_plan
from app.services.source_connectors import (
    CONNECTOR_STATUS_PARTIAL_SUCCEEDED,
    CONNECTOR_STATUS_SUCCEEDED,
    ConnectorEvent,
    ConnectorReadiness,
    ConnectorRunResult,
)
from app.services.source_control import request_source_action
from app.services.source_run_orchestrator import run_source_request
from tests.test_stage11_connector_ingestion import _ensure_tables


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _cleanup(marker: str) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(NormalizedActivityItemRecord).where(
                NormalizedActivityItemRecord.activity_item_id.like(f"%{marker}%")
            )
        )
        await session.execute(
            delete(NormalizedActivityItemRecord).where(
                NormalizedActivityItemRecord.source_object_id.like(f"%{marker}%")
            )
        )
        await session.execute(
            delete(SourceEvent).where(SourceEvent.source_object_id.like(f"%{marker}%"))
        )
        await session.execute(
            delete(IngestedEvent).where(IngestedEvent.source_object_id.like(f"%{marker}%"))
        )
        await session.execute(
            delete(SourceRunRequest).where(SourceRunRequest.request_key.like(f"%{marker}%"))
        )
        await session.execute(
            delete(AuditLog).where(
                AuditLog.payload["request_key"].as_string().like(f"%{marker}%")
            )
        )
        await session.execute(
            delete(SourceControlState).where(
                SourceControlState.last_request_key.like(f"%{marker}%")
            )
        )
        await session.commit()


def _event(marker: str) -> ConnectorEvent:
    return ConnectorEvent(
        source_type="github",
        external_id=f"example-org/project-alpha/pull/{marker}",
        object_type="pull_request",
        event_type="github.pull_request.synchronized",
        occurred_at=datetime(2026, 6, 14, tzinfo=timezone.utc),
        title="ALPHA-101 status changed",
        summary="Project Alpha moved forward",
        actor="Person A",
        url=f"https://github.com/example-org/project-alpha/pull/{marker}",
        sanitized_payload={
            "source_object_type": "pull_request",
            "repository_full_name": "example-org/project-alpha",
            "pull_request_number": marker,
        },
    )


@dataclass
class ReceiptFakeConnector:
    marker: str = "default"
    status: str = CONNECTOR_STATUS_SUCCEEDED
    stopped_reason: str = "no_more_results"
    fail: bool = False
    include_event: bool = True
    output_watermark: str | None = "2026-06-14T00:00:00+00:00"
    token_value: str = "stage18-secret-shaped-token-value"

    source_type: str = "github"

    async def readiness(self) -> ConnectorReadiness:
        return ConnectorReadiness(
            source_type=self.source_type,
            configured=True,
            missing_env_vars=[],
            masked_config_status=[],
            can_test=True,
            can_sync=True,
            can_backfill=True,
        )

    async def test_connection(self) -> ConnectorRunResult:
        return await self._result("test", events=[])

    async def sync(self, watermark: str | None = None) -> ConnectorRunResult:
        if self.fail:
            raise RuntimeError(self.token_value)
        return await self._result("sync", watermark=watermark)

    async def backfill(
        self,
        *,
        since: str | None = None,
        until: str | None = None,
        limit: int | None = None,
    ) -> ConnectorRunResult:
        return await self._result("backfill", watermark=None)

    async def _result(
        self,
        action_type: str,
        *,
        watermark: str | None = None,
        events: list[ConnectorEvent] | None = None,
    ) -> ConnectorRunResult:
        now = datetime(2026, 6, 14, tzinfo=timezone.utc)
        run_events = events if events is not None else ([_event(self.marker)] if self.include_event else [])
        return ConnectorRunResult(
            status=self.status,
            source_type=self.source_type,
            action_type=action_type,
            started_at=now,
            finished_at=now,
            input_watermark=watermark,
            output_watermark=self.output_watermark,
            events_seen=len(run_events),
            pages_read=2,
            page_size=1,
            limit_applied=2,
            stopped_reason=self.stopped_reason,
            retry_after_seconds=60 if self.stopped_reason == "rate_limited" else None,
            rate_limit_remaining=0 if self.stopped_reason == "rate_limited" else 10,
            warnings=["rate_limited"] if self.stopped_reason == "rate_limited" else [],
            external_side_effect=False,
            sanitized_summary={"mode": "fake_stage18"},
            events=run_events,
        )


async def _run(
    marker: str,
    *,
    action_type: str = "sync",
    connector: ReceiptFakeConnector | None = None,
) -> SourceRunRequest:
    async with AsyncSessionLocal() as session:
        request = await request_source_action(
            session,
            source_type="github",
            action_type=action_type,
            request_key=f"stage18-{action_type}-{marker}",
            requested_by="founder",
        )
        row = await session.scalar(
            select(SourceRunRequest).where(
                SourceRunRequest.request_id == request["request_id"]
            )
        )
        active_connector = connector or ReceiptFakeConnector(marker=marker)
        if active_connector.marker == "default":
            active_connector.marker = marker
        await run_source_request(
            session,
            request=row,
            connectors={"github": active_connector},
            run_id=f"src_run_stage18_{marker}",
        )
        await session.commit()
        refreshed = await session.scalar(
            select(SourceRunRequest).where(
                SourceRunRequest.request_id == request["request_id"]
            )
        )
        return refreshed


async def test_sync_run_creates_receipt_endpoint_and_updates_watermark() -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    try:
        row = await _run(marker)
        receipt = row.result_summary["receipt"]
        assert receipt["watermark_updated"] is True
        assert receipt["watermark_update_reason"] == "sync_success"
        assert receipt["events_ingested"] == 1
        assert receipt["normalized_events"] >= 1
        assert receipt["pages_read"] == 2
        assert receipt["limit_applied"] == 2
        assert receipt["external_side_effect"] is False
        async with _client() as client:
            ok = await client.get(f"/v1/founder/source-runs/{row.request_id}/receipt")
            blocked = await client.get(
                f"/v1/founder/source-runs/{row.request_id}/receipt",
                params={"view": "team"},
            )
        assert ok.status_code == 200
        assert ok.json()["receipt"]["receipt_id"] == receipt["receipt_id"]
        assert blocked.status_code == 403
        assert "stage18-secret-shaped-token-value" not in json.dumps(ok.json())
    finally:
        await _cleanup(marker)


async def test_preview_writes_no_events_and_does_not_update_watermark() -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    try:
        row = await _run(marker, action_type="preview_sync")
        receipt = row.result_summary["receipt"]
        assert row.status == "succeeded"
        assert receipt["watermark_updated"] is False
        assert receipt["watermark_update_reason"] == "preview_no_write"
        async with AsyncSessionLocal() as session:
            count = await session.scalar(
                select(SourceEvent).where(
                    SourceEvent.created_by_run_id == f"src_run_stage18_{marker}"
                )
            )
        assert count is None
    finally:
        await _cleanup(marker)


async def test_backfill_does_not_overwrite_normal_sync_watermark() -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    try:
        row = await _run(marker, action_type="backfill")
        receipt = row.result_summary["receipt"]
        assert receipt["watermark_updated"] is False
        assert (
            receipt["watermark_update_reason"]
            == "backfill_does_not_advance_sync_watermark"
        )
    finally:
        await _cleanup(marker)


async def test_failed_run_receipt_is_sanitized_and_retry_is_safe() -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    try:
        row = await _run(marker, connector=ReceiptFakeConnector(fail=True))
        receipt = row.result_summary["receipt"]
        assert row.status == "failed"
        assert receipt["watermark_updated"] is False
        assert receipt["watermark_update_reason"] == "adapter_exception"
        blob = json.dumps({"row": row.result_summary, "error": row.error_summary})
        assert "stage18-secret-shaped-token-value" not in blob
        async with _client() as client:
            retry = await client.post(
                f"/v1/founder/sources/github/retry/{row.request_id}",
                json={
                    "request_key": f"stage18-retry-{marker}",
                    "requested_by": "founder",
                },
            )
        assert retry.status_code == 200
        assert retry.json()["status"] == "requested"
        assert retry.json()["retry_count"] == 1
    finally:
        await _cleanup(marker)


async def test_partial_rate_limit_receipt_drives_dq_action_and_obsidian() -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    try:
        row = await _run(
            marker,
            connector=ReceiptFakeConnector(
                status=CONNECTOR_STATUS_PARTIAL_SUCCEEDED,
                stopped_reason="rate_limited",
            ),
        )
        receipt = row.result_summary["receipt"]
        assert row.status == "partial_succeeded"
        assert receipt["stopped_reason"] == "rate_limited"
        assert receipt["retry_after_seconds"] == 60
        async with AsyncSessionLocal() as session:
            dq = await build_data_quality_center(session)
            actions = await build_action_center(session, limit=200)
            plan = await generate_obsidian_vault_plan(session, limit=20)
        categories = {issue["category"] for issue in dq["issues"]}
        assert "receipt_rate_limited" in categories
        assert "receipt_partial_success" in categories
        assert any(
            action["action_type"] in {"retry_failed_run", "lower_sync_limit"}
            for action in actions["actions"]
        )
        paths = {note.path for note in plan.notes}
        assert "_System/Connector Run Receipts.md" in paths
        receipt_note = next(
            note for note in plan.notes if note.path == "_System/Connector Run Receipts.md"
        )
        assert "rate_limited" in receipt_note.markdown
        assert "stage18-secret-shaped-token-value" not in receipt_note.markdown
    finally:
        await _cleanup(marker)


async def test_completed_request_does_not_rerun_or_retry() -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    try:
        row = await _run(marker)
        first_hash = row.result_summary["receipt"]["content_hash"]
        async with AsyncSessionLocal() as session:
            row = await session.scalar(
                select(SourceRunRequest).where(SourceRunRequest.request_key.like(f"%{marker}%"))
            )
            result = await run_source_request(
                session,
                request=row,
                connectors={"github": ReceiptFakeConnector(output_watermark="changed")},
                run_id=f"src_run_stage18_{marker}_again",
            )
            await session.commit()
        assert result["status"] == "unchanged"
        async with _client() as client:
            retry = await client.post(
                f"/v1/founder/sources/github/retry/{row.request_id}",
                json={
                    "request_key": f"stage18-complete-retry-{marker}",
                    "requested_by": "founder",
                },
            )
        assert retry.status_code == 400
        async with AsyncSessionLocal() as session:
            saved = await session.scalar(
                select(SourceRunRequest).where(SourceRunRequest.request_id == row.request_id)
            )
        assert saved.result_summary["receipt"]["content_hash"] == first_hash
    finally:
        await _cleanup(marker)
