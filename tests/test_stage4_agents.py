from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import delete, select

from app.api.auth import settings
from app.db.agent_models import AgentProposal, AgentRunLog
from app.db.base import AsyncSessionLocal, engine
from app.db.event_models import NormalizedActivityItemRecord, SourceEvent
from app.db.gmail_models import EmailThreadState
from app.db.graph_models import (
    EntityAliasRecord,
    EntityLinkRecord,
    EntityRecord,
    EntitySourceAccount,
)
from app.db.models import IngestedEvent
from app.db.second_opinion_models import SecondOpinionFinding
from app.main import app
from app.services.agent_run_log import latest_runs, record_agent_run
from app.services.evidence_explorer import build_source_event_view
from app.services.graph_gardener import run_graph_gardener
from app.services.knowledge_graph import upsert_entity
from app.services.sales_signal_agent import scan_sales_signals
from app.services.second_opinion import (
    FINDING_EXECUTION_MISMATCH,
    OUTCOME_UPDATED_CLOCK,
    OUTCOME_UPDATED_NEW_EVIDENCE,
    REASON_NEW_EVIDENCE,
    REASON_STALE_WINDOW,
    new_run_counts,
    tally_outcome,
    upsert_finding,
)
from app.services.visibility import SCOPE_FOUNDER, SCOPE_INVESTOR, SCOPE_TEAM


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
            EntityRecord.__table__,
            EntityAliasRecord.__table__,
            EntityLinkRecord.__table__,
            EntitySourceAccount.__table__,
            AgentProposal.__table__,
            AgentRunLog.__table__,
            SecondOpinionFinding.__table__,
            EmailThreadState.__table__,
            SourceEvent.__table__,
            NormalizedActivityItemRecord.__table__,
            IngestedEvent.__table__,
        ):
            await conn.run_sync(table.create, checkfirst=True)


async def _cleanup(marker: str) -> None:
    async with AsyncSessionLocal() as session:
        for model, col in (
            (AgentProposal, AgentProposal.proposal_id),
            (AgentRunLog, AgentRunLog.run_id),
            (SecondOpinionFinding, SecondOpinionFinding.finding_key),
            (EmailThreadState, EmailThreadState.thread_key),
            (SourceEvent, SourceEvent.source_event_id),
            (IngestedEvent, IngestedEvent.event_id),
            (EntityLinkRecord, EntityLinkRecord.link_id),
            (EntitySourceAccount, EntitySourceAccount.account_id),
            (EntityAliasRecord, EntityAliasRecord.entity_id),
            (EntityRecord, EntityRecord.entity_id),
        ):
            await session.execute(delete(model).where(col.like(f"%{marker}%")))
        await session.commit()


# --- hardening: clock vs new evidence -----------------------------------


def test_tally_outcome_buckets() -> None:
    counts = new_run_counts()
    tally_outcome(counts, OUTCOME_UPDATED_NEW_EVIDENCE)
    tally_outcome(counts, OUTCOME_UPDATED_CLOCK)
    tally_outcome(counts, "created")
    tally_outcome(counts, "garbage-outcome")
    assert counts["updated_from_new_evidence"] == 1
    assert counts["updated_from_clock_recalculation"] == 1
    assert counts["created"] == 1
    assert counts["errors"] == 1


async def test_clock_vs_new_evidence_update_reason() -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    key = f"reason:{marker}"
    base = {
        "finding_key": key,
        "entity_id": None,
        "finding_type": FINDING_EXECUTION_MISMATCH,
        "declared_state": "d",
        "observed_state": "age 5d",
        "summary": "s",
        "severity": "medium",
        "confidence": 0.7,
        "evidence_refs": [{"source_id": "X-1"}],
    }
    try:
        async with AsyncSessionLocal() as session:
            await upsert_finding(session, **base)
            # Only the observed age moved -> clock recalculation.
            clock = await upsert_finding(
                session, **{**base, "observed_state": "age 6d"}
            )
            row1 = await session.scalar(
                select(SecondOpinionFinding).where(
                    SecondOpinionFinding.finding_key == key
                )
            )
            reason_clock = row1.last_update_reason
            # Evidence changed -> new evidence.
            fresh = await upsert_finding(
                session,
                **{
                    **base,
                    "observed_state": "age 6d",
                    "evidence_refs": [{"source_id": "X-2"}],
                },
            )
            row2 = await session.scalar(
                select(SecondOpinionFinding).where(
                    SecondOpinionFinding.finding_key == key
                )
            )
            reason_evidence = row2.last_update_reason
            await session.commit()
        assert clock == OUTCOME_UPDATED_CLOCK
        assert reason_clock == REASON_STALE_WINDOW
        assert fresh == OUTCOME_UPDATED_NEW_EVIDENCE
        assert reason_evidence == REASON_NEW_EVIDENCE
    finally:
        await _cleanup(marker)


async def test_agent_run_log_records_and_lists() -> None:
    await _ensure_tables()
    run_id = f"run-{uuid4().hex[:10]}"
    started = datetime(2026, 6, 13, tzinfo=timezone.utc)
    try:
        async with AsyncSessionLocal() as session:
            await record_agent_run(
                session,
                run_id=run_id,
                agent="second_opinion",
                agent_version="testv",
                run_started_at=started,
                run_finished_at=started + timedelta(seconds=2),
                counts={
                    "created": 3,
                    "updated_from_new_evidence": 1,
                    "updated_from_clock_recalculation": 5,
                    "unchanged": 10,
                    "custom_key": 7,
                },
                input_watermark="999",
            )
            await session.commit()
            runs = await latest_runs(session, limit=50)
        mine = next(r for r in runs if r["run_id"] == run_id)
        assert mine["updated_from_clock_recalculation"] == 5
        assert mine["updated_from_new_evidence"] == 1
        assert mine["input_watermark"] == "999"
        # Non-standard keys land in details, not lost.
        assert mine["details"]["custom_key"] == 7
    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(
                delete(AgentRunLog).where(AgentRunLog.run_id == run_id)
            )
            await session.commit()


# --- sales signal agent -------------------------------------------------


async def test_sales_agent_builds_account_contact_deal_graph() -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    domain = f"acme-{marker}.com"
    thread_key = f"sales-{marker}"
    now = datetime(2026, 6, 13, tzinfo=timezone.utc)
    try:
        async with AsyncSessionLocal() as session:
            session.add(
                EmailThreadState(
                    source="gmail",
                    thread_key=thread_key,
                    subject_display="Pilot discussion",
                    participants_json=[f"buyer@{domain}", "me@qtwin.io"],
                    last_message_from=f"buyer@{domain}",
                    last_message_at=now - timedelta(days=20),
                    status="informational",
                    messages_count=4,
                )
            )
            await session.commit()
            counts = await scan_sales_signals(session, now=now)
            # Idempotent second run.
            counts2 = await scan_sales_signals(session, now=now)
            await session.commit()

            client_node = await session.scalar(
                select(EntityRecord).where(
                    EntityRecord.entity_id == f"client:{_slug(domain)}"
                )
            )
            deal_node = await session.scalar(
                select(EntityRecord).where(
                    EntityRecord.entity_id == f"deal:{_slug(domain)}"
                )
            )
        # scan_sales_signals is a global scan; on a fresh database other
        # seeded threads may also turn into accounts, so assert this run
        # created at least this thread's account/signal rather than assuming
        # the database held nothing else. The strong invariants below — this
        # account/deal node existing and the idempotent re-run creating
        # nothing new — still pin the agent's behaviour exactly.
        assert counts["accounts"] >= 1
        assert counts["contacts"] >= 1
        assert counts["signals"] >= 1
        assert counts2["accounts"] == 0  # idempotent: re-scan creates nothing new
        assert client_node is not None
        assert client_node.attrs.get("warmth") in {"cooling", "cold"}
        assert deal_node is not None
        # No money fields anywhere on the deal entity.
        assert "amount" not in (deal_node.attrs or {})
        assert "revenue" not in (deal_node.attrs or {})
    finally:
        await _cleanup(marker)
        await _cleanup(_slug(domain))


def _slug(value: str) -> str:
    from app.services.knowledge_graph import slugify

    return slugify(value)


async def test_sales_agent_skips_free_email_domains() -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    thread_key = f"free-{marker}"
    now = datetime(2026, 6, 13, tzinfo=timezone.utc)
    try:
        async with AsyncSessionLocal() as session:
            session.add(
                EmailThreadState(
                    source="gmail",
                    thread_key=thread_key,
                    subject_display="Personal",
                    participants_json=["someone@gmail.com", "me@qtwin.io"],
                    last_message_from="someone@gmail.com",
                    last_message_at=now - timedelta(days=20),
                    status="informational",
                    messages_count=3,
                )
            )
            await session.commit()
            counts = await scan_sales_signals(session, now=now)
            await session.commit()
        # gmail.com is a mailbox provider, not a company account.
        assert counts["accounts"] == 0
    finally:
        await _cleanup(marker)


# --- graph gardener -----------------------------------------------------


async def test_gardener_files_orphan_proposal_and_is_idempotent() -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    orphan_id = f"person:orphan-{marker}"
    try:
        async with AsyncSessionLocal() as session:
            await upsert_entity(
                session,
                entity_id=orphan_id,
                entity_type="person",
                canonical_name=f"Orphan {marker}",
            )
            await session.commit()
            counts = await run_graph_gardener(session)
            counts2 = await run_graph_gardener(session)
            await session.commit()

            proposal = await session.scalar(
                select(AgentProposal).where(
                    AgentProposal.proposal_id == f"gardener:graph_orphan_node:{orphan_id}"
                )
            )
            orphan_still_there = await session.scalar(
                select(EntityRecord).where(EntityRecord.entity_id == orphan_id)
            )
        assert counts["proposals"] >= 1
        assert counts2["proposals"] == 0  # idempotent: no duplicate proposals
        assert proposal is not None
        assert proposal.kind == "graph_orphan_node"
        # The gardener never deletes — the node is still present.
        assert orphan_still_there is not None
    finally:
        await _cleanup(marker)


# --- evidence explorer + visibility -------------------------------------


async def test_evidence_explorer_visibility() -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    event_id = f"sevt_{marker}"
    try:
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
                    source_event_id=event_id,
                    source_event_key=f"key-{marker}",
                    ingested_event_id=f"ie-{marker}",
                    event_type="jira.issue.updated",
                    source_system="jira",
                    source_object_type="issue",
                    source_object_id=f"ZZ-{marker}",
                    title="Sensitive title",
                    summary="sensitive summary body",
                    source_url="https://jira/issue",
                    raw_object_ref=f"raw://jira/{marker}",
                )
            )
            await session.commit()

            founder_view = await build_source_event_view(
                session, source_event_id=event_id, viewer_scope=SCOPE_FOUNDER
            )
            team_view = await build_source_event_view(
                session, source_event_id=event_id, viewer_scope=SCOPE_TEAM
            )
            investor_view = await build_source_event_view(
                session, source_event_id=event_id, viewer_scope=SCOPE_INVESTOR
            )
        # Founder sees raw_object_ref + summary.
        assert founder_view["event"]["raw_object_ref"] == f"raw://jira/{marker}"
        assert founder_view["event"]["summary"] == "sensitive summary body"
        # Team sees working fields only: no raw ref, no summary.
        assert "raw_object_ref" not in team_view["event"]
        assert "summary" not in team_view["event"]
        # Investor cannot see raw evidence at all.
        assert investor_view is None
    finally:
        await _cleanup(marker)


# --- API guards ---------------------------------------------------------


async def test_command_center_founder_only(monkeypatch) -> None:
    _set_auth(monkeypatch, enabled=False)
    async with _client() as client:
        ok = await client.get("/api/v1/founder/command-center")
        assert ok.status_code == 200
        body = ok.json()
        assert "startup_health" in body
        assert "second_opinion" in body
        assert "team" in body
        assert "data_availability" in body
        # No finance anywhere in the command center contract.
        text = ok.text.lower()
        assert "revenue" not in text
        assert "runway" not in text
        assert "mrr" not in text

        blocked = await client.get(
            "/api/v1/founder/command-center", params={"view": "team"}
        )
        assert blocked.status_code == 403


async def test_source_events_and_agent_runs_guards(monkeypatch) -> None:
    _set_auth(monkeypatch, enabled=False)
    async with _client() as client:
        inv = await client.get("/api/v1/source-events", params={"view": "investor"})
        assert inv.status_code == 403
        runs = await client.get("/api/v1/founder/agent-runs", params={"view": "team"})
        assert runs.status_code == 403
        ok = await client.get("/api/v1/founder/agent-runs")
        assert ok.status_code == 200
        assert "runs" in ok.json()
