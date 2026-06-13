from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select

from app.core.config import settings as app_settings
from app.db.base import AsyncSessionLocal, engine
from app.db.event_models import NormalizedActivityItemRecord, SourceEvent
from app.db.models import AuditLog, IngestedEvent
from app.db.source_control_models import SourceControlState, SourceRunRequest
from app.main import app
from app.services.source_connectors import (
    CONNECTOR_STATUS_SUCCEEDED,
    ConnectorEvent,
    ConnectorReadiness,
    ConnectorRunResult,
    NoopSourceConnector,
)
from app.services.source_ingestion import ingest_connector_events
from app.services.source_run_orchestrator import run_source_request


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _ensure_tables() -> None:
    async with engine.begin() as conn:
        for table in (
            AuditLog.__table__,
            IngestedEvent.__table__,
            SourceEvent.__table__,
            NormalizedActivityItemRecord.__table__,
            SourceControlState.__table__,
            SourceRunRequest.__table__,
        ):
            await conn.run_sync(table.create, checkfirst=True)


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
            delete(SourceEvent).where(SourceEvent.raw_object_ref.like(f"%{marker}%"))
        )
        await session.execute(
            delete(IngestedEvent).where(IngestedEvent.source_object_id.like(f"%{marker}%"))
        )
        await session.execute(
            delete(IngestedEvent).where(IngestedEvent.raw_object_ref.like(f"%{marker}%"))
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


def _github_event(marker: str, *, title: str = "ALPHA-101 update") -> ConnectorEvent:
    return ConnectorEvent(
        source_type="github",
        external_id=f"example-org/project-alpha/pull/{marker}",
        object_type="pull_request",
        event_type="github.pull_request.synchronized",
        occurred_at=datetime(2026, 6, 14, tzinfo=timezone.utc),
        title=title,
        summary="Project Alpha PR moved forward",
        actor="Person A",
        url=f"https://example.invalid/project-alpha/pull/{marker}",
        raw_object_ref=f"raw://github/stage11/{marker}/pr.json",
        sanitized_payload={
            "source_object_type": "pull_request",
            "repository_full_name": "example-org/project-alpha",
            "pull_request_number": marker,
            "api_token": "LEAKED-STAGE11-TOKEN",
            "raw_body": "PRIVATE RAW BODY",
        },
    )


def _request(marker: str, *, action_type: str = "sync") -> SourceRunRequest:
    request_id = f"src_req_stage11_{marker}_{uuid4().hex[:8]}"
    return SourceRunRequest(
        request_id=request_id,
        source_type="github",
        action_type=action_type,
        status="requested",
        request_key=f"github-{action_type}-{marker}",
        correlation_id=f"corr-stage11-{marker}",
        idempotency_key=f"github:{action_type}:{marker}",
        requested_by="founder",
        requested_at=datetime(2026, 6, 14, tzinfo=timezone.utc),
        input_snapshot={"input": {}},
        result_summary={},
        error_summary={},
        external_side_effect=False,
    )


@dataclass
class FakeEventConnector:
    event: ConnectorEvent
    test_events: bool = False
    calls: int = 0

    source_type: str = "github"

    async def readiness(self) -> ConnectorReadiness:
        return ConnectorReadiness(
            source_type="github",
            configured=True,
            missing_env_vars=[],
            masked_config_status=[{"name": "GITHUB_TOKEN", "status": "masked"}],
            can_test=True,
            can_sync=True,
            can_backfill=True,
        )

    async def test_connection(self) -> ConnectorRunResult:
        self.calls += 1
        now = datetime(2026, 6, 14, tzinfo=timezone.utc)
        return ConnectorRunResult(
            status=CONNECTOR_STATUS_SUCCEEDED,
            source_type="github",
            action_type="test",
            started_at=now,
            finished_at=now,
            events=[self.event] if self.test_events else [],
            external_side_effect=False,
            sanitized_summary={"mode": "fake_test"},
        )

    async def sync(self, watermark: str | None = None) -> ConnectorRunResult:
        self.calls += 1
        now = datetime(2026, 6, 14, tzinfo=timezone.utc)
        return ConnectorRunResult(
            status=CONNECTOR_STATUS_SUCCEEDED,
            source_type="github",
            action_type="sync",
            started_at=now,
            finished_at=now,
            output_watermark=now.isoformat(),
            events=[self.event],
            events_seen=1,
            external_side_effect=False,
            sanitized_summary={"mode": "fake_sync"},
        )

    async def backfill(
        self,
        *,
        since: str | None = None,
        until: str | None = None,
        limit: int | None = None,
    ) -> ConnectorRunResult:
        return await self.sync(watermark=None)


async def test_connector_event_payload_is_deterministic_and_sanitized() -> None:
    marker = uuid4().hex[:8]
    event = _github_event(marker)
    payload = event.to_connector_payload()
    blob = json.dumps(payload, sort_keys=True)
    assert payload["source_system"] == "github"
    assert payload["source_object_type"] == "pull_request"
    assert payload["idempotency_key"].endswith(event.stable_content_hash())
    assert event.stable_content_hash() == _github_event(marker).stable_content_hash()
    assert "LEAKED-STAGE11-TOKEN" not in blob
    assert "PRIVATE RAW BODY" not in blob
    assert payload["payload"]["api_token"] == "***redacted***"
    assert payload["payload"]["raw_body"] == "***redacted***"


async def test_ingestion_upserts_source_events_and_normalizes_idempotently() -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    event = _github_event(marker)
    try:
        async with AsyncSessionLocal() as session:
            first = await ingest_connector_events(
                session,
                events=[event],
                run_id=f"src_run_{marker}",
                correlation_id=f"corr_{marker}",
            )
            second = await ingest_connector_events(
                session,
                events=[event],
                run_id=f"src_run_{marker}",
                correlation_id=f"corr_{marker}",
            )
            changed = await ingest_connector_events(
                session,
                events=[_github_event(marker, title="ALPHA-101 changed title")],
                run_id=f"src_run_{marker}_changed",
                correlation_id=f"corr_{marker}",
            )
            await session.commit()

        assert first["events_ingested"] == 1
        assert first["normalized_events"] == 1
        assert first["payload_redactions"] == 1
        assert second["events_ingested"] == 0
        assert second["duplicates_skipped"] == 1
        assert changed["events_ingested"] == 1

        async with AsyncSessionLocal() as session:
            event_count = await session.scalar(
                select(func.count(SourceEvent.id)).where(
                    SourceEvent.source_object_id == f"example-org/project-alpha/pull/{marker}"
                )
            )
            normalized_count = await session.scalar(
                select(func.count(NormalizedActivityItemRecord.id)).where(
                    NormalizedActivityItemRecord.source_object_id
                    == f"example-org/project-alpha/pull/{marker}"
                )
            )
            source_event = await session.scalar(
                select(SourceEvent).where(SourceEvent.created_by_run_id == f"src_run_{marker}")
            )
            ingested = await session.scalar(
                select(IngestedEvent).where(
                    IngestedEvent.source_object_id
                    == f"example-org/project-alpha/pull/{marker}"
                )
            )
        assert event_count == 2
        assert normalized_count == 2
        assert source_event is not None
        assert source_event.metadata_json["correlation_id"] == f"corr_{marker}"
        assert ingested is not None
        assert "LEAKED-STAGE11-TOKEN" not in json.dumps(ingested.payload)
    finally:
        await _cleanup(marker)


async def test_orchestrator_sync_ingests_and_test_does_not_ingest_events() -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    event = _github_event(marker)
    snapshot = await _state_snapshot("github")
    try:
        async with AsyncSessionLocal() as session:
            sync_request = _request(marker)
            session.add(sync_request)
            await session.flush()
            sync_result = await run_source_request(
                session,
                request=sync_request,
                connectors={"github": FakeEventConnector(event)},
                run_id=f"src_run_{marker}",
            )
            test_request = _request(f"{marker}-test", action_type="test")
            session.add(test_request)
            await session.flush()
            test_result = await run_source_request(
                session,
                request=test_request,
                connectors={"github": FakeEventConnector(event, test_events=True)},
                run_id=f"src_run_{marker}_test",
            )
            await session.commit()

        assert sync_result["status"] == "succeeded"
        assert test_result["status"] == "succeeded"
        ingestion = sync_request.result_summary["sanitized_summary"]["ingestion"]
        assert ingestion["events_ingested"] == 1
        assert ingestion["normalized_events"] == 1

        async with AsyncSessionLocal() as session:
            sync_events = await session.scalar(
                select(func.count(SourceEvent.id)).where(
                    SourceEvent.created_by_run_id == f"src_run_{marker}"
                )
            )
            test_events = await session.scalar(
                select(func.count(SourceEvent.id)).where(
                    SourceEvent.created_by_run_id == f"src_run_{marker}_test"
                )
            )
            state = await session.scalar(
                select(SourceControlState).where(SourceControlState.source_type == "github")
            )
        assert sync_events == 1
        assert test_events == 0
        assert state is not None
        assert state.input_watermark is not None

        async with _client() as client:
            dq = await client.get("/v1/founder/data-quality")
        assert dq.status_code == 200
        dq_blob = json.dumps(dq.json(), sort_keys=True)
        assert "event_payload_redacted" in dq_blob
        assert "LEAKED-STAGE11-TOKEN" not in dq_blob
    finally:
        await _cleanup(marker)
        await _restore_state("github", snapshot)


async def test_normalization_failure_is_recorded_and_visible_in_data_quality() -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    event = ConnectorEvent(
        source_type="telegram",
        external_id=f"telegram-command-{marker}",
        object_type="command",
        event_type="telegram.command.received",
        occurred_at=datetime(2026, 6, 14, tzinfo=timezone.utc),
        title="Unsupported command event",
        sanitized_payload={"text": "/status Project Alpha"},
        raw_object_ref=f"raw://telegram/stage11/{marker}.json",
    )
    try:
        async with AsyncSessionLocal() as session:
            result = await ingest_connector_events(
                session,
                events=[event],
                run_id=f"src_run_norm_fail_{marker}",
                correlation_id=f"corr_{marker}",
            )
            await session.commit()
        assert result["events_ingested"] == 1
        assert result["normalization_errors"] == 1

        async with _client() as client:
            dq = await client.get("/v1/founder/data-quality")
        assert dq.status_code == 200
        categories = {issue["category"] for issue in dq.json()["issues"]}
        assert "normalization_failed" in categories
    finally:
        await _cleanup(marker)


async def test_source_events_filters_and_role_redaction_for_stage11_events() -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    event = _github_event(marker)
    try:
        async with AsyncSessionLocal() as session:
            await ingest_connector_events(
                session,
                events=[event],
                run_id=f"src_run_filter_{marker}",
                correlation_id=f"corr_{marker}",
            )
            await session.commit()
        async with _client() as client:
            founder = await client.get(
                "/v1/source-events",
                params={
                    "source_type": "github",
                    "run_id": f"src_run_filter_{marker}",
                    "object_type": "pull_request",
                    "since": "2026-06-01T00:00:00+00:00",
                },
            )
            team = await client.get(
                "/v1/source-events",
                params={
                    "source_type": "github",
                    "run_id": f"src_run_filter_{marker}",
                    "view": "team",
                },
            )
            investor = await client.get("/v1/source-events", params={"view": "investor"})
        assert founder.status_code == 200
        assert team.status_code == 200
        assert investor.status_code == 403
        founder_event = next(
            item
            for item in founder.json()["events"]
            if item["run_id"] == f"src_run_filter_{marker}"
        )
        assert founder_event["source_object_type"] == "pull_request"
        assert founder_event["normalized_event_count"] == 1
        assert "raw_object_ref" in founder_event
        team_event = next(
            item
            for item in team.json()["events"]
            if item["run_id"] == f"src_run_filter_{marker}"
        )
        assert "raw_object_ref" not in team_event
    finally:
        await _cleanup(marker)


async def test_missing_config_readiness_names_only(monkeypatch) -> None:
    secret_value = "LEAKED-JIRA-STAGE11-VALUE"
    monkeypatch.delenv("JIRA_BASE_URL", raising=False)
    monkeypatch.delenv("JIRA_EMAIL", raising=False)
    monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
    monkeypatch.setattr(app_settings, "jira_base_url", None)
    monkeypatch.setattr(app_settings, "jira_email", None)
    monkeypatch.setattr(app_settings, "jira_api_token", secret_value)
    connector = NoopSourceConnector("jira")
    readiness = await connector.readiness()
    result = await connector.sync(watermark=None)
    blob = json.dumps({"readiness": readiness.to_dict(), "result": result.to_dict()})
    assert "JIRA_BASE_URL" in blob
    assert "JIRA_EMAIL" in blob
    assert secret_value not in blob
    assert result.status == "missing_config"
