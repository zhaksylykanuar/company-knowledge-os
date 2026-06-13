from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from httpx import ASGITransport, AsyncClient
from sqlalchemy import Text, cast, delete, func, select

from app.db.agent_models import AgentProposal, AgentRunLog
from app.db.base import AsyncSessionLocal, engine
from app.db.event_models import NormalizedActivityItemRecord, SourceEvent
from app.db.graph_models import (
    EntityAliasRecord,
    EntityLinkRecord,
    EntityRecord,
    EntitySourceAccount,
)
from app.db.models import AuditLog, IngestedEvent
from app.db.second_opinion_models import SecondOpinionFinding
from app.db.source_control_models import SourceRunRequest
from app.main import app
from app.services.data_quality_center import build_data_quality_center
from app.services.evidence_graph_lift import (
    lift_normalized_activity_item,
    run_evidence_pipeline,
)
from app.services.evidence_trail import build_finding_trail
from app.services.graph_tree import build_graph_tree
from app.services.source_control import build_source_health


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _ensure_tables() -> None:
    async with engine.begin() as conn:
        for table in (
            AuditLog.__table__,
            IngestedEvent.__table__,
            SourceEvent.__table__,
            NormalizedActivityItemRecord.__table__,
            EntityRecord.__table__,
            EntityAliasRecord.__table__,
            EntitySourceAccount.__table__,
            EntityLinkRecord.__table__,
            AgentProposal.__table__,
            AgentRunLog.__table__,
            SecondOpinionFinding.__table__,
            SourceRunRequest.__table__,
        ):
            await conn.run_sync(table.create, checkfirst=True)


async def _cleanup(marker: str) -> None:
    async with AsyncSessionLocal() as session:
        entity_ids = (
            await session.execute(
                select(EntityRecord.entity_id).where(
                    cast(EntityRecord.attrs, Text).like(f"%{marker}%")
                )
            )
        ).scalars().all()
        if entity_ids:
            await session.execute(
                delete(EntityLinkRecord).where(
                    EntityLinkRecord.from_entity_id.in_(entity_ids)
                    | EntityLinkRecord.to_entity_id.in_(entity_ids)
                )
            )
            await session.execute(
                delete(EntitySourceAccount).where(
                    EntitySourceAccount.entity_id.in_(entity_ids)
                )
            )
            await session.execute(
                delete(EntityAliasRecord).where(EntityAliasRecord.entity_id.in_(entity_ids))
            )
            await session.execute(
                delete(EntityRecord).where(EntityRecord.entity_id.in_(entity_ids))
            )
        await session.execute(
            delete(EntityLinkRecord).where(
                cast(EntityLinkRecord.evidence_refs, Text).like(f"%{marker}%")
            )
        )
        await session.execute(
            delete(AgentProposal).where(
                cast(AgentProposal.evidence_refs, Text).like(f"%{marker}%")
                | cast(AgentProposal.payload, Text).like(f"%{marker}%")
                | AgentProposal.proposal_id.like(f"%{marker}%")
            )
        )
        await session.execute(
            delete(SecondOpinionFinding).where(
                SecondOpinionFinding.finding_key.like(f"%{marker}%")
                | cast(SecondOpinionFinding.evidence_refs, Text).like(f"%{marker}%")
            )
        )
        await session.execute(
            delete(AuditLog).where(
                AuditLog.correlation_id.like(f"%{marker}%")
                | AuditLog.trace_id.like(f"%{marker}%")
                | cast(AuditLog.payload, Text).like(f"%{marker}%")
            )
        )
        await session.execute(
            delete(AgentRunLog).where(
                AgentRunLog.run_id.like(f"%{marker}%")
                | cast(AgentRunLog.details, Text).like(f"%{marker}%")
            )
        )
        await session.execute(
            delete(NormalizedActivityItemRecord).where(
                NormalizedActivityItemRecord.activity_item_id.like(f"%{marker}%")
                | NormalizedActivityItemRecord.source_object_id.like(f"%{marker}%")
            )
        )
        await session.execute(
            delete(SourceEvent).where(
                SourceEvent.source_event_id.like(f"%{marker}%")
                | SourceEvent.source_object_id.like(f"%{marker}%")
                | SourceEvent.raw_object_ref.like(f"%{marker}%")
            )
        )
        await session.execute(
            delete(IngestedEvent).where(
                IngestedEvent.event_id.like(f"%{marker}%")
                | IngestedEvent.source_object_id.like(f"%{marker}%")
                | IngestedEvent.raw_object_ref.like(f"%{marker}%")
            )
        )
        await session.execute(
            delete(SourceRunRequest).where(
                SourceRunRequest.request_key.like(f"%{marker}%")
                | SourceRunRequest.request_id.like(f"%{marker}%")
                | SourceRunRequest.run_id.like(f"%{marker}%")
            )
        )
        await session.commit()


def _source_run_request(marker: str, *, source_type: str = "github") -> SourceRunRequest:
    return SourceRunRequest(
        request_id=f"src_req_stage12_{marker}",
        source_type=source_type,
        action_type="sync",
        status="succeeded",
        request_key=f"{source_type}-sync-stage12-{marker}",
        run_id=f"src_run_stage12_{marker}",
        correlation_id=f"corr_stage12_{marker}",
        idempotency_key=f"{source_type}:sync:stage12:{marker}",
        requested_by="founder",
        requested_at=datetime(2026, 6, 14, tzinfo=timezone.utc),
        started_at=datetime(2026, 6, 14, tzinfo=timezone.utc),
        finished_at=datetime(2026, 6, 14, tzinfo=timezone.utc),
        input_snapshot={"input": {"limit": 1}},
        result_summary={
            "status": "succeeded",
            "sanitized_summary": {
                "ingestion": {"events_ingested": 1, "normalized_events": 1}
            },
            "external_side_effect": False,
        },
        error_summary={},
        external_side_effect=False,
    )


async def _insert_normalized(
    marker: str,
    *,
    source: str = "github",
    object_type: str = "pull_request",
    activity_type: str = "github.pull_request.synchronized",
    title: str | None = None,
    actor: str | None = "Person A",
    project: str | None = "Project Alpha",
    related_jira_keys: list[str] | None = None,
    source_object_id: str | None = None,
) -> tuple[str, str]:
    source_event_id = f"src_evt_stage12_{marker}"
    activity_item_id = f"act_stage12_{marker}"
    object_id = source_object_id or f"example-org/project-alpha/pull/{marker}"
    async with AsyncSessionLocal() as session:
        session.add(_source_run_request(marker, source_type=source))
        session.add(
            IngestedEvent(
                event_id=f"ing_stage12_{marker}",
                event_type=activity_type,
                source_system=source,
                source_object_id=object_id,
                idempotency_key=f"stage12:{source}:{object_id}:{marker}",
                correlation_id=f"corr_stage12_{marker}",
                trace_id=f"src_run_stage12_{marker}",
                raw_object_ref=f"raw://{source}/stage12/{marker}.json",
                payload={
                    "title": title or "ALPHA-101 Project Alpha update",
                    "source_object_type": object_type,
                    "source_type": source,
                },
                status="normalized",
            )
        )
        await session.flush()
        session.add(
            SourceEvent(
                source_event_id=source_event_id,
                source_event_key=f"stage12:{source}:{object_id}:{marker}",
                ingested_event_id=f"ing_stage12_{marker}",
                event_type=activity_type,
                source_system=source,
                source_object_type=object_type,
                source_object_id=object_id,
                source_event_ts=datetime(2026, 6, 14, tzinfo=timezone.utc),
                actor_external_id=actor,
                title=title or "ALPHA-101 Project Alpha update",
                summary="Project Alpha evidence was observed.",
                source_url=f"https://example.invalid/stage12/{marker}",
                raw_object_ref=f"raw://{source}/stage12/{marker}.json",
                evidence_refs=[{"kind": "connector_event", "marker": marker}],
                metadata_json={"correlation_id": f"corr_stage12_{marker}"},
                created_by_run_id=f"src_run_stage12_{marker}",
            )
        )
        await session.flush()
        session.add(
            NormalizedActivityItemRecord(
                activity_item_id=activity_item_id,
                source_event_id=source_event_id,
                source=source,
                source_object_id=object_id,
                activity_type=activity_type,
                title=title or "ALPHA-101 Project Alpha update",
                actor=actor,
                activity_created_at=datetime(2026, 6, 14, tzinfo=timezone.utc),
                project=project,
                safe_summary="Project Alpha evidence was observed.",
                related_people=[actor] if actor else [],
                related_jira_keys=related_jira_keys if related_jira_keys is not None else ["ALPHA-101"],
                related_prs=[object_id] if source == "github" else [],
                related_files=[],
                evidence_refs=[{"kind": "source_event", "source_event_id": source_event_id}],
                run_id=f"norm_stage12_{marker}",
            )
        )
        await session.commit()
    return activity_item_id, source_event_id


async def test_evidence_pipeline_lifts_event_to_graph_and_is_idempotent() -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    try:
        activity_item_id, source_event_id = await _insert_normalized(marker)
        async with AsyncSessionLocal() as session:
            first = await run_evidence_pipeline(
                session,
                activity_item_ids=[activity_item_id],
                run_id=f"evidence_pipeline_{marker}",
            )
            second = await run_evidence_pipeline(
                session,
                activity_item_ids=[activity_item_id],
                run_id=f"evidence_pipeline_{marker}_again",
            )
            await session.commit()
            nodes = await session.scalar(
                select(func.count(EntityRecord.id)).where(
                    cast(EntityRecord.attrs, Text).like(f"%{activity_item_id}%")
                )
            )
            links = await session.scalar(
                select(func.count(EntityLinkRecord.id)).where(
                    cast(EntityLinkRecord.evidence_refs, Text).like(f"%{source_event_id}%")
                )
            )
            request = await session.scalar(
                select(SourceRunRequest).where(
                    SourceRunRequest.request_key == f"github-sync-stage12-{marker}"
                )
            )
        assert first["graph_nodes_created"] >= 3
        assert first["graph_edges_created"] >= 2
        assert second["graph_nodes_created"] == 0
        assert second["graph_edges_created"] == 0
        assert nodes and nodes >= 3
        assert links and links >= 2
        assert request is not None
        pipeline = request.result_summary["evidence_pipeline"]
        assert pipeline["graph_nodes_created"] >= 3
        assert pipeline["graph_edges_created"] >= 2

        async with AsyncSessionLocal() as session:
            health = await build_source_health(session)
        github = next(s for s in health["sources"] if s["source_type"] == "github")
        assert github["graph_updates"] >= 1
    finally:
        await _cleanup(marker)


async def test_low_confidence_project_hint_creates_proposal_not_graph_edge() -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    try:
        activity_item_id, source_event_id = await _insert_normalized(
            marker,
            title=f"Project Alpha ambiguous note {marker}",
            project=None,
            related_jira_keys=[],
        )
        async with AsyncSessionLocal() as session:
            summary = await run_evidence_pipeline(
                session,
                activity_item_ids=[activity_item_id],
                run_id=f"evidence_pipeline_{marker}",
            )
            await session.commit()
            proposal = await session.scalar(
                select(AgentProposal).where(
                    AgentProposal.kind == "low_confidence_relation",
                    cast(AgentProposal.evidence_refs, Text).like(f"%{source_event_id}%"),
                )
            )
            weak_edge = await session.scalar(
                select(EntityLinkRecord).where(
                    EntityLinkRecord.confidence < 0.65,
                    cast(EntityLinkRecord.evidence_refs, Text).like(f"%{source_event_id}%"),
                )
            )
        assert summary["link_proposals_created"] >= 1
        assert proposal is not None
        assert proposal.status == "pending"
        assert weak_edge is None
    finally:
        await _cleanup(marker)


async def test_findings_have_lineage_and_no_evidence_skips_finding() -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    orphan_marker = f"{marker}_orphan"
    try:
        activity_item_id, source_event_id = await _insert_normalized(
            marker,
            related_jira_keys=[],
        )
        async with AsyncSessionLocal() as session:
            session.add(
                NormalizedActivityItemRecord(
                    activity_item_id=f"act_stage12_{orphan_marker}",
                    source_event_id=None,
                    source="github",
                    source_object_id=f"example-org/project-alpha/pull/{orphan_marker}",
                    activity_type="github.pull_request.synchronized",
                    title="Project Alpha orphan evidence",
                    actor="Person A",
                    project="Project Alpha",
                    safe_summary="No source event backs this row.",
                    related_people=["Person A"],
                    related_jira_keys=[],
                    related_prs=[],
                    related_files=[],
                    evidence_refs=[],
                    run_id=f"norm_stage12_{orphan_marker}",
                )
            )
            orphan = await session.scalar(
                select(NormalizedActivityItemRecord).where(
                    NormalizedActivityItemRecord.activity_item_id
                    == f"act_stage12_{orphan_marker}"
                )
            )
            no_evidence = await lift_normalized_activity_item(session, orphan)
            summary = await run_evidence_pipeline(
                session,
                activity_item_ids=[activity_item_id, f"act_stage12_{orphan_marker}"],
                run_id=f"evidence_pipeline_{marker}",
            )
            await session.commit()

            finding = await session.scalar(
                select(SecondOpinionFinding).where(
                    SecondOpinionFinding.finding_key.like(f"%{marker}%")
                )
            )
            trail = await build_finding_trail(
                session, finding_key=finding.finding_key if finding else ""
            )
        assert no_evidence["skipped_no_evidence"] == 1
        assert summary["findings_created"] >= 1
        assert finding is not None
        assert finding.evidence_refs[0]["source_event_id"] == source_event_id
        assert finding.evidence_refs[0]["normalized_event_id"] == activity_item_id
        assert finding.last_run_id == f"evidence_pipeline_{marker}"
        assert trail is not None
        assert trail["graph_lineage"]["nodes"]
        assert trail["evidence_chain"][0]["source_events"][0]["source_event_id"] == source_event_id
        assert trail["evidence_chain"][0]["source_runs"][0]["run_id"] == f"src_run_stage12_{marker}"
    finally:
        await _cleanup(marker)
        await _cleanup(orphan_marker)


async def test_data_quality_action_center_and_tree_surface_pipeline_lineage() -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    low_marker = f"{marker}_low"
    try:
        activity_item_id, _ = await _insert_normalized(marker, related_jira_keys=[])
        low_activity_item_id, _ = await _insert_normalized(
            low_marker,
            title=f"Project Alpha ambiguous note {low_marker}",
            project=None,
            related_jira_keys=[],
        )
        async with AsyncSessionLocal() as session:
            session.add(
                NormalizedActivityItemRecord(
                    activity_item_id=f"act_stage12_unlinked_{marker}",
                    source_event_id=None,
                    source="github",
                    source_object_id=f"example-org/project-alpha/unlinked/{marker}",
                    activity_type="github.activity.observed",
                    title="Project Alpha unlinked activity",
                    actor="Person A",
                    project="Project Alpha",
                    safe_summary="No backing source event.",
                    related_people=["Person A"],
                    related_jira_keys=[],
                    related_prs=[],
                    related_files=[],
                    evidence_refs=[],
                    run_id=f"norm_stage12_unlinked_{marker}",
                )
            )
            await run_evidence_pipeline(
                session,
                activity_item_ids=[
                    activity_item_id,
                    low_activity_item_id,
                    f"act_stage12_unlinked_{marker}",
                ],
                run_id=f"evidence_pipeline_{marker}",
            )
            quality = await build_data_quality_center(session)
            tree = await build_graph_tree(session)
            await session.commit()

        categories = {issue["category"] for issue in quality["issues"]}
        assert "normalized_event_not_lifted_to_graph" in categories
        assert any(
            node["created_by_run_id"] == f"evidence_pipeline_{marker}"
            and activity_item_id in json.dumps(node["attrs"], sort_keys=True)
            for node in tree["nodes"]
        )

        async with _client() as client:
            action_center = await client.get("/v1/founder/action-center")
        assert action_center.status_code == 200
        action_blob = json.dumps(action_center.json(), sort_keys=True)
        assert "evidence_pipeline" in action_blob
    finally:
        await _cleanup(marker)
        await _cleanup(low_marker)


async def test_run_script_requires_confirmation() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/run_evidence_pipeline.py", "--confirm-run", "WRONG"],
        cwd=Path(__file__).resolve().parents[1],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["status"] == "blocked"
    assert payload["external_side_effect"] is False


async def test_stage12_ui_static_markers_present() -> None:
    html = Path("app/static/founder_ui.html").read_text(encoding="utf-8")
    assert "graph updates" in html
    assert "graph nodes" in html
    assert "graph lineage" in html
    assert "created run" in html
