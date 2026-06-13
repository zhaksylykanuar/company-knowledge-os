from __future__ import annotations

from uuid import uuid4

from sqlalchemy import delete, select

from app.db.agent_models import AgentProposal
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
from app.services.agent_proposals import create_proposal, decide_proposal
from app.services.gardener_apply import apply_gardener_proposal
from app.services.graph_tree import build_graph_tree
from app.services.knowledge_graph import (
    ENTITY_PERSON,
    REL_WORKS_ON,
    upsert_entity,
    upsert_link,
)
from app.services.run_context import set_run_id
from app.services.second_opinion import FINDING_EXECUTION_MISMATCH, upsert_finding


async def _ensure_tables() -> None:
    async with engine.begin() as conn:
        for table in (
            EntityRecord.__table__,
            EntityAliasRecord.__table__,
            EntityLinkRecord.__table__,
            EntitySourceAccount.__table__,
            AgentProposal.__table__,
            SecondOpinionFinding.__table__,
            SourceEvent.__table__,
            NormalizedActivityItemRecord.__table__,
            IngestedEvent.__table__,
            AuditLog.__table__,
        ):
            await conn.run_sync(table.create, checkfirst=True)


async def _cleanup(marker: str) -> None:
    async with AsyncSessionLocal() as session:
        for model, col in (
            (AgentProposal, AgentProposal.proposal_id),
            (SecondOpinionFinding, SecondOpinionFinding.finding_key),
            (SourceEvent, SourceEvent.source_event_id),
            (IngestedEvent, IngestedEvent.event_id),
            (NormalizedActivityItemRecord, NormalizedActivityItemRecord.activity_item_id),
            (AuditLog, AuditLog.correlation_id),
            (EntityLinkRecord, EntityLinkRecord.link_id),
            (EntityRecord, EntityRecord.entity_id),
        ):
            await session.execute(delete(model).where(col.like(f"%{marker}%")))
        await session.commit()
    set_run_id(None)


async def _accept(session, proposal_id: str) -> AgentProposal:
    await decide_proposal(
        session,
        proposal_id=proposal_id,
        decision="accepted",
        reviewer_id="founder",
    )
    return await session.scalar(
        select(AgentProposal).where(AgentProposal.proposal_id == proposal_id)
    )


# --- gardener apply: safe actions, never silent delete ------------------


async def test_apply_orphan_archives_not_deletes_idempotent() -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    entity_id = f"person:orphan-{marker}"
    prop_id = f"gardener:graph_orphan_node:{entity_id}"
    try:
        async with AsyncSessionLocal() as session:
            await upsert_entity(
                session,
                entity_id=entity_id,
                entity_type=ENTITY_PERSON,
                canonical_name=f"Orphan {marker}",
            )
            await create_proposal(
                session,
                proposal_id=prop_id,
                agent="graph_gardener",
                kind="graph_orphan_node",
                title="orphan",
                payload={"entity_id": entity_id},
                confidence=0.5,
            )
            proposal = await _accept(session, prop_id)
            result = await apply_gardener_proposal(session, proposal)
            # Idempotent: applied proposal is a no-op the second time.
            again = await apply_gardener_proposal(session, proposal)
            await session.commit()

            node = await session.scalar(
                select(EntityRecord).where(EntityRecord.entity_id == entity_id)
            )
        assert result["applied"] == "archived"
        assert again["applied"] == "skipped"
        # Node still exists (archived), never deleted.
        assert node is not None
        assert node.attrs.get("archived") is True
        assert proposal.applied_at is not None
    finally:
        await _cleanup(marker)


async def test_apply_edge_without_evidence_removes_with_snapshot() -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    a = f"person:a-{marker}"
    b = f"person:b-{marker}"
    try:
        async with AsyncSessionLocal() as session:
            for eid in (a, b):
                await upsert_entity(
                    session,
                    entity_id=eid,
                    entity_type=ENTITY_PERSON,
                    canonical_name=eid,
                )
            await upsert_link(
                session, from_entity_id=a, relation=REL_WORKS_ON, to_entity_id=b
            )
            link_id = f"{a}->works_on->{b}"
            await create_proposal(
                session,
                proposal_id=f"gardener:graph_edge_without_evidence:{link_id}",
                agent="graph_gardener",
                kind="graph_edge_without_evidence",
                title="edge",
                payload={"link_id": link_id},
                confidence=0.45,
            )
            proposal = await _accept(
                session, f"gardener:graph_edge_without_evidence:{link_id}"
            )
            result = await apply_gardener_proposal(session, proposal)
            await session.commit()

            link = await session.scalar(
                select(EntityLinkRecord).where(EntityLinkRecord.link_id == link_id)
            )
        assert result["applied"] == "edge_removed"
        # Snapshot kept so the edge can be recreated.
        assert result["removed_edge"]["from"] == a
        assert link is None
    finally:
        await _cleanup(marker)


async def test_apply_finding_without_evidence_suppresses() -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    key = f"lost:{marker}"
    try:
        async with AsyncSessionLocal() as session:
            await upsert_finding(
                session,
                finding_key=key,
                entity_id=None,
                finding_type=FINDING_EXECUTION_MISMATCH,
                declared_state="d",
                observed_state="o",
                summary="lost evidence",
                severity="low",
                confidence=0.6,
                evidence_refs=[{"source_id": "x"}],
            )
            await create_proposal(
                session,
                proposal_id=f"gardener:finding_lost_evidence:{key}",
                agent="graph_gardener",
                kind="finding_lost_evidence",
                title="finding lost evidence",
                payload={"finding_key": key},
                confidence=0.6,
            )
            proposal = await _accept(
                session, f"gardener:finding_lost_evidence:{key}"
            )
            result = await apply_gardener_proposal(session, proposal)
            await session.commit()

            finding = await session.scalar(
                select(SecondOpinionFinding).where(
                    SecondOpinionFinding.finding_key == key
                )
            )
        assert result["applied"] == "finding_suppressed"
        assert finding.status == "dismissed"
    finally:
        await _cleanup(marker)


async def test_apply_duplicate_account_files_merge_proposal() -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    a = f"client:acme-{marker}"
    b = f"client:acme2-{marker}"
    try:
        async with AsyncSessionLocal() as session:
            await create_proposal(
                session,
                proposal_id=f"gardener:graph_duplicate_account:{a}+{b}",
                agent="graph_gardener",
                kind="graph_duplicate_account",
                title="dup",
                payload={"candidates": [a, b]},
                confidence=0.5,
            )
            proposal = await _accept(
                session, f"gardener:graph_duplicate_account:{a}+{b}"
            )
            result = await apply_gardener_proposal(session, proposal)
            await session.commit()

            merge = await session.scalar(
                select(AgentProposal).where(
                    AgentProposal.kind == "entity_merge_proposal"
                ).where(AgentProposal.proposal_id.like(f"%{marker}%"))
            )
        # Duplicate accounts are NOT merged directly — an explicit merge
        # proposal is filed for the confirmed merge flow.
        assert result["applied"] == "merge_proposal_filed"
        assert merge is not None
    finally:
        await _cleanup(marker)


async def test_archived_node_hidden_from_graph_tree() -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    entity_id = f"person:arch-{marker}"
    try:
        async with AsyncSessionLocal() as session:
            await upsert_entity(
                session,
                entity_id=entity_id,
                entity_type=ENTITY_PERSON,
                canonical_name="Archived",
                attrs={"archived": True},
            )
            await session.commit()
            tree = await build_graph_tree(session)
        node_ids = {n["entity_id"] for n in tree["nodes"]}
        assert entity_id not in node_ids
    finally:
        await _cleanup(marker)


# --- full run_id lineage surfaced in the trail --------------------------


async def test_trail_surfaces_full_run_lineage() -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    run_a = f"runA-{marker}"
    run_b = f"runB-{marker}"
    project = f"project-zz-{marker}"
    finding_key = f"project:{project}:exec:{marker}"
    try:
        # Source event created by run A.
        set_run_id(run_a)
        async with AsyncSessionLocal() as session:
            session.add(
                IngestedEvent(
                    event_id=f"ie-{marker}",
                    event_type="jira.issue.updated",
                    source_system="jira",
                    source_object_id=f"ZZ-{marker}",
                    idempotency_key=f"idem-{marker}",
                    correlation_id=f"corr-{marker}",
                    trace_id=f"trace-{marker}",
                    raw_object_ref=f"raw://jira/{marker}",
                )
            )
            await session.flush()
            session.add(
                SourceEvent(
                    created_by_run_id=run_a,
                    source_event_id=f"sevt-{marker}",
                    source_event_key=f"sek-{marker}",
                    ingested_event_id=f"ie-{marker}",
                    event_type="jira.issue.updated",
                    source_system="jira",
                    source_object_type="issue",
                    source_object_id=f"ZZ-{marker}",
                    title="t",
                    raw_object_ref=f"raw://jira/{marker}",
                )
            )
            await session.commit()

        # Finding created by run B, referencing the source object id.
        set_run_id(run_b)
        async with AsyncSessionLocal() as session:
            await upsert_finding(
                session,
                finding_key=finding_key,
                entity_id=None,
                finding_type=FINDING_EXECUTION_MISMATCH,
                declared_state="d",
                observed_state="o",
                summary="s",
                severity="low",
                confidence=0.7,
                evidence_refs=[{"source_id": f"ZZ-{marker}"}],
            )
            await session.commit()

        from app.services.evidence_trail import build_finding_trail

        async with AsyncSessionLocal() as session:
            trail = await build_finding_trail(session, finding_key=finding_key)

        # The chain ties the finding (run B) back to its source event (run A).
        assert run_a in trail["lineage_run_ids"]
        assert run_b in trail["lineage_run_ids"]
        chain_event_runs = [
            ev["created_by_run_id"]
            for item in trail["evidence_chain"]
            for ev in item["source_events"]
        ]
        assert run_a in chain_event_runs
    finally:
        await _cleanup(marker)
        set_run_id(None)
