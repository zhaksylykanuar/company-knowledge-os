from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import delete, func, select

from app.api.auth import settings
from app.core.config import settings as app_settings
from app.db.agent_models import AgentProposal, AgentRunLog, DataAvailability
from app.db.base import AsyncSessionLocal, engine
from app.db.declaration_models import FounderDeclaration
from app.db.event_models import NormalizedActivityItemRecord, SourceEvent
from app.db.graph_models import EntityLinkRecord, EntityRecord, EntitySourceAccount
from app.db.models import AuditLog, IngestedEvent
from app.db.second_opinion_models import SecondOpinionFinding
from app.db.share_pack_models import SharePack
from app.db.source_control_models import SourceControlState, SourceRunRequest
from app.db.source_models import SourceDocument
from app.main import app


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _set_auth(monkeypatch, *, enabled: bool) -> None:
    monkeypatch.setattr(settings, "api_auth_enabled", enabled)
    monkeypatch.setattr(
        settings, "api_auth_key", SecretStr("test-api-key") if enabled else None
    )
    monkeypatch.setattr(settings, "api_auth_header_name", "X-FounderOS-API-Key")


async def _ensure_tables() -> None:
    async with engine.begin() as conn:
        for table in (
            AuditLog.__table__,
            IngestedEvent.__table__,
            SourceEvent.__table__,
            NormalizedActivityItemRecord.__table__,
            AgentRunLog.__table__,
            AgentProposal.__table__,
            DataAvailability.__table__,
            SecondOpinionFinding.__table__,
            EntityRecord.__table__,
            EntityLinkRecord.__table__,
            EntitySourceAccount.__table__,
            FounderDeclaration.__table__,
            SourceDocument.__table__,
            SharePack.__table__,
            SourceControlState.__table__,
            SourceRunRequest.__table__,
        ):
            await conn.run_sync(table.create, checkfirst=True)


async def _cleanup(marker: str) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(SourceRunRequest).where(SourceRunRequest.request_key.like(f"%{marker}%"))
        )
        await session.execute(
            delete(SourceControlState).where(
                SourceControlState.last_request_key.like(f"%{marker}%")
            )
        )
        for model, col in (
            (AuditLog, AuditLog.correlation_id),
            (NormalizedActivityItemRecord, NormalizedActivityItemRecord.activity_item_id),
            (SourceEvent, SourceEvent.source_event_id),
            (IngestedEvent, IngestedEvent.event_id),
            (AgentRunLog, AgentRunLog.run_id),
            (AgentProposal, AgentProposal.proposal_id),
            (DataAvailability, DataAvailability.scope),
            (SecondOpinionFinding, SecondOpinionFinding.finding_key),
            (EntityLinkRecord, EntityLinkRecord.link_id),
            (EntitySourceAccount, EntitySourceAccount.account_id),
            (EntityRecord, EntityRecord.entity_id),
            (FounderDeclaration, FounderDeclaration.declaration_key),
            (SourceDocument, SourceDocument.source_document_id),
            (SharePack, SharePack.pack_id),
        ):
            await session.execute(delete(model).where(col.like(f"%{marker}%")))
        await session.commit()


async def _snapshot_source_state(source_type: str) -> dict | None:
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
            "config_status": row.config_status,
        }


async def _restore_source_state(source_type: str, snapshot: dict | None) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(SourceControlState).where(SourceControlState.source_type == source_type)
        )
        if snapshot is not None:
            session.add(SourceControlState(**snapshot))
        await session.commit()


async def _seed_jira_evidence(marker: str, *, event_status: str = "received") -> None:
    async with AsyncSessionLocal() as session:
        session.add(
            IngestedEvent(
                event_id=f"ie-stage9-{marker}",
                event_type="jira.issue.updated",
                source_system="jira",
                source_object_id=f"ALPHA-{marker}",
                idempotency_key=f"idem-stage9-{marker}",
                correlation_id=f"corr-stage9-{marker}",
                trace_id=f"trace-stage9-{marker}",
                raw_object_ref=f"raw://jira/{marker}",
                payload={"title": "Project Alpha issue"},
                status=event_status,
            )
        )
        await session.flush()
        session.add(
            SourceEvent(
                source_event_id=f"sevt-stage9-{marker}",
                source_event_key=f"sevt-key-stage9-{marker}",
                ingested_event_id=f"ie-stage9-{marker}",
                event_type="jira.issue.updated",
                source_system="jira",
                source_object_type="issue",
                source_object_id=f"ALPHA-{marker}",
                title="Project Alpha task updated",
                summary="Project Alpha sanitized summary",
                source_url="https://example.invalid/browse/ALPHA-101",
                raw_object_ref=f"raw://jira/{marker}",
            )
        )
        await session.flush()
        session.add(
            NormalizedActivityItemRecord(
                activity_item_id=f"nai-stage9-{marker}",
                source_event_id=f"sevt-stage9-{marker}",
                source="jira",
                source_object_id=f"ALPHA-{marker}",
                activity_type="issue_update",
                title="Project Alpha task updated",
                actor="Person A",
                activity_created_at=datetime(2026, 6, 13, tzinfo=timezone.utc),
                project="Project Alpha",
                safe_summary="Project Alpha work moved",
                related_people=["Person A"],
                related_jira_keys=["ALPHA-101"],
                related_prs=[],
                related_files=[],
                evidence_refs=[{"source_id": "ALPHA-101"}],
                run_id=f"run-stage9-{marker}",
            )
        )
        session.add(
            DataAvailability(
                metric_key="jira.open",
                scope=f"project:alpha:{marker}",
                status="ready",
                points_count=5,
                required_points=5,
                last_point_at="2026-06-13",
                message="ready",
            )
        )
        session.add(
            SecondOpinionFinding(
                finding_key=f"finding-stage9-{marker}",
                entity_id=f"project:alpha:{marker}",
                finding_type="execution_mismatch",
                declared_state="Project Alpha is in progress",
                observed_state="Jira and code activity disagree",
                summary="Project Alpha has an evidence-backed conflict",
                severity="medium",
                confidence=0.72,
                evidence_refs=[{"source": "jira", "source_id": "ALPHA-101"}],
                source_refs=[],
            )
        )
        await session.commit()


async def test_source_health_counts_and_masks_connector_setup(monkeypatch) -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    _set_auth(monkeypatch, enabled=False)
    monkeypatch.setenv("GITHUB_TOKEN", "LEAKED-GH-VALUE")
    monkeypatch.setattr(app_settings, "jira_api_token", "LEAKED-JIRA-VALUE")
    try:
        await _seed_jira_evidence(marker)
        async with _client() as client:
            response = await client.get("/v1/founder/sources")
        assert response.status_code == 200
        body = response.json()
        jira = next(item for item in body["sources"] if item["source_type"] == "jira")
        assert jira["events_ingested"] >= 1
        assert jira["normalized_events"] >= 1
        assert jira["findings_generated"] >= 1
        setup_blob = json.dumps(jira["connector_readiness"])
        assert "LEAKED-JIRA-VALUE" not in response.text
        assert "LEAKED-GH-VALUE" not in response.text
        assert "masked" in setup_blob
        assert body["summary"]["total_sources"] >= 8
    finally:
        await _cleanup(marker)


async def test_source_controls_are_audited_idempotent_and_pause_blocks_sync(
    monkeypatch,
) -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    _set_auth(monkeypatch, enabled=False)
    snapshot = await _snapshot_source_state("jira")
    try:
        async with _client() as client:
            first = await client.post(
                "/v1/founder/sources/jira/sync",
                json={"request_key": f"sync-{marker}", "requested_by": "founder"},
            )
            second = await client.post(
                "/v1/founder/sources/jira/sync",
                json={"request_key": f"sync-{marker}", "requested_by": "founder"},
            )
            pause = await client.post(
                "/v1/founder/sources/jira/pause",
                json={"request_key": f"pause-{marker}", "requested_by": "founder"},
            )
            blocked = await client.post(
                "/v1/founder/sources/jira/backfill",
                json={"request_key": f"backfill-{marker}", "requested_by": "founder"},
            )
            resume = await client.post(
                "/v1/founder/sources/jira/resume",
                json={"request_key": f"resume-{marker}", "requested_by": "founder"},
            )
        assert first.status_code == 200
        assert second.status_code == 200
        assert second.json()["idempotent"] is True
        assert pause.json()["status"] == "accepted"
        assert blocked.json()["status"] == "skipped"
        assert blocked.json()["result_summary"]["blocked"] is True
        assert resume.json()["status"] == "accepted"

        async with AsyncSessionLocal() as session:
            requests = await session.scalar(
                select(func.count(SourceRunRequest.id)).where(
                    SourceRunRequest.request_key.like(f"%{marker}%")
                )
            )
            audits = await session.scalar(
                select(func.count(AuditLog.id)).where(
                    AuditLog.correlation_id.like("src_req_%")
                ).where(AuditLog.payload["request_key"].as_string().like(f"%{marker}%"))
            )
        assert requests == 4
        assert audits == 4
    finally:
        await _cleanup(marker)
        await _restore_source_state("jira", snapshot)


async def test_source_controls_are_founder_only(monkeypatch) -> None:
    await _ensure_tables()
    _set_auth(monkeypatch, enabled=False)
    async with _client() as client:
        response = await client.post(
            "/v1/founder/sources/jira/test",
            params={"view": "team"},
            json={"request_key": "team-blocked"},
        )
    assert response.status_code == 403


async def test_source_control_request_input_is_log_safe(monkeypatch) -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    secret_value = "LEAKED-SOURCE-ACTION-INPUT"
    _set_auth(monkeypatch, enabled=False)
    try:
        async with _client() as client:
            response = await client.post(
                "/v1/founder/sources/manual_inputs/test",
                json={
                    "request_key": f"safe-input-{marker}",
                    "input": {"api_token": secret_value, "limit": 10},
                },
            )
        assert response.status_code == 200
        assert secret_value not in response.text
        body = response.json()
        assert body["input_snapshot"]["input"]["api_token"] == "***redacted***"
        assert body["input_snapshot"]["input"]["limit"] == 10

        async with AsyncSessionLocal() as session:
            row = await session.scalar(
                select(SourceRunRequest).where(
                    SourceRunRequest.request_key == f"safe-input-{marker}"
                )
            )
        assert row is not None
        assert secret_value not in json.dumps(row.input_snapshot)
    finally:
        await _cleanup(marker)


async def test_source_controls_reject_unknown_source_and_action_without_rows(
    monkeypatch,
) -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    _set_auth(monkeypatch, enabled=False)
    try:
        async with _client() as client:
            unknown_source = await client.post(
                "/v1/founder/sources/not-a-source/sync",
                json={"request_key": f"invalid-source-{marker}"},
            )
            traversal_like = await client.post(
                "/v1/founder/sources/..jira/sync",
                json={"request_key": f"invalid-traversal-{marker}"},
            )
            unknown_action = await client.post(
                "/v1/founder/sources/jira/not-an-action",
                json={"request_key": f"invalid-action-{marker}"},
            )
        assert unknown_source.status_code == 404
        assert traversal_like.status_code == 404
        assert unknown_action.status_code == 404

        async with AsyncSessionLocal() as session:
            requests = await session.scalar(
                select(func.count(SourceRunRequest.id)).where(
                    SourceRunRequest.request_key.like(f"%{marker}%")
                )
            )
            audits = await session.scalar(
                select(func.count(AuditLog.id)).where(
                    AuditLog.payload["request_key"].as_string().like(f"%{marker}%")
                )
            )
        assert requests == 0
        assert audits == 0
    finally:
        await _cleanup(marker)


async def test_source_events_filters_and_redacts_by_role(monkeypatch) -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    _set_auth(monkeypatch, enabled=False)
    try:
        await _seed_jira_evidence(marker, event_status="failed")
        async with _client() as client:
            founder = await client.get(
                "/v1/source-events",
                params={"source_type": "jira", "status": "failed", "limit": 10},
            )
            team = await client.get(
                "/v1/source-events",
                params={
                    "source_type": "jira",
                    "status": "failed",
                    "limit": 10,
                    "view": "team",
                },
            )
            investor = await client.get(
                "/v1/source-events", params={"view": "investor"}
            )
        assert founder.status_code == 200
        founder_event = next(
            event
            for event in founder.json()["events"]
            if event["source_event_id"] == f"sevt-stage9-{marker}"
        )
        assert founder_event["raw_object_ref"] == f"raw://jira/{marker}"
        assert founder_event["status"] == "failed"
        team_event = next(
            event
            for event in team.json()["events"]
            if event["source_event_id"] == f"sevt-stage9-{marker}"
        )
        assert "raw_object_ref" not in team_event
        assert team_event["redaction"]["raw_object_ref_visible"] is False
        assert investor.status_code == 403
    finally:
        await _cleanup(marker)


async def test_data_quality_center_reports_evidence_based_issues(monkeypatch) -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    _set_auth(monkeypatch, enabled=False)
    try:
        async with AsyncSessionLocal() as session:
            session.add(
                EntityRecord(
                    entity_id=f"project:alpha:orphan:{marker}",
                    entity_type="project",
                    canonical_name="Project Alpha",
                )
            )
            session.add(
                EntityRecord(
                    entity_id=f"person:a:{marker}",
                    entity_type="person",
                    canonical_name="Person A",
                )
            )
            session.add(
                EntityLinkRecord(
                    link_id=f"link-low-{marker}",
                    from_entity_id=f"project:alpha:orphan:{marker}",
                    to_entity_id=f"person:a:{marker}",
                    relation="owned_by",
                    evidence_refs=[{"source_id": "ALPHA-101"}],
                    confidence=0.4,
                )
            )
            session.add(
                SecondOpinionFinding(
                    finding_key=f"finding-empty-{marker}",
                    entity_id=f"project:alpha:orphan:{marker}",
                    finding_type="ownership_gap",
                    declared_state="Project Alpha has an owner",
                    observed_state="No owner found",
                    summary="Project Alpha has no owner",
                    severity="high",
                    confidence=0.8,
                    evidence_refs=[],
                    source_refs=[],
                )
            )
            session.add(
                DataAvailability(
                    metric_key="jira.stale",
                    scope=f"project:alpha:{marker}",
                    status="stale",
                    points_count=2,
                    required_points=5,
                    last_point_at="2026-06-01",
                    message="Data is stale",
                )
            )
            session.add(
                AgentRunLog(
                    run_id=f"run-errors-{marker}",
                    agent="jira_normalizer",
                    agent_version="v1",
                    run_started_at=datetime(2026, 6, 13, tzinfo=timezone.utc),
                    run_finished_at=datetime(2026, 6, 13, tzinfo=timezone.utc),
                    errors=2,
                )
            )
            session.add(
                SourceControlState(
                    source_type=f"manual_inputs:{marker}",
                    status="disabled",
                    paused=True,
                    last_request_key=f"state-{marker}",
                )
            )
            await session.commit()

        async with _client() as client:
            response = await client.get("/v1/founder/data-quality")
        assert response.status_code == 200
        body = response.json()
        categories = {issue["category"] for issue in body["issues"]}
        assert "data_availability_gap" in categories
        assert "low_confidence_edge" in categories
        assert "missing_owner" in categories
        assert "finding_without_evidence" in categories
        assert "failed_normalization" in categories
        assert "source_paused" in categories
        assert "score" not in body
        assert "source_control" in body["links"]
    finally:
        await _cleanup(marker)
