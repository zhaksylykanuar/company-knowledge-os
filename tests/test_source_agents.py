from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import delete, select

from app.db.base import AsyncSessionLocal, engine
from app.db.declaration_models import FounderDeclaration
from app.db.event_models import NormalizedActivityItemRecord
from app.db.gmail_models import EmailThreadState
from app.db.graph_models import EntityLinkRecord, EntityRecord
from app.db.second_opinion_models import SecondOpinionFinding
from app.db.source_models import DocumentChunk, SourceDocument
from app.db.task_models import ExtractedRisk
from app.services.agent_proposals import AgentProposal
from app.services.declaration_agents import scan_focus_drift, scan_hypotheses
from app.services.declarations import KEY_FOCUS, KEY_HYPOTHESES, set_declaration
from app.services.email_thread_agent import scan_email_silence
from app.services.meeting_agent import scan_meetings
from app.services.second_opinion import (
    FINDING_COMMUNICATION_SILENCE,
    FINDING_VALIDATION_GAP,
    LOW_CONFIDENCE_THRESHOLD,
    emit_finding_or_proposal,
    list_findings,
    set_finding_status,
    upsert_finding,
)


async def _ensure_tables() -> None:
    async with engine.begin() as conn:
        for table in (
            SourceDocument.__table__,
            DocumentChunk.__table__,
            EntityRecord.__table__,
            EntityLinkRecord.__table__,
            SecondOpinionFinding.__table__,
            AgentProposal.__table__,
            FounderDeclaration.__table__,
            EmailThreadState.__table__,
            NormalizedActivityItemRecord.__table__,
            ExtractedRisk.__table__,
        ):
            await conn.run_sync(table.create, checkfirst=True)


async def _cleanup(marker: str) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(DocumentChunk).where(
                DocumentChunk.source_document_id.like(f"%{marker}%")
            )
        )
        await session.execute(
            delete(SourceDocument).where(
                SourceDocument.source_document_id.like(f"%{marker}%")
            )
        )
        await session.execute(
            delete(EntityLinkRecord).where(
                EntityLinkRecord.link_id.like(f"%{marker}%")
            )
        )
        await session.execute(
            delete(EntityRecord).where(EntityRecord.entity_id.like(f"%{marker}%"))
        )
        await session.execute(
            delete(SecondOpinionFinding).where(
                SecondOpinionFinding.finding_key.like(f"%{marker}%")
            )
        )
        await session.execute(
            delete(AgentProposal).where(
                AgentProposal.proposal_id.like(f"%{marker}%")
            )
        )
        await session.execute(
            delete(EmailThreadState).where(
                EmailThreadState.thread_key.like(f"%{marker}%")
            )
        )
        await session.commit()


# --- emit_finding_or_proposal: the trust rules --------------------------


async def test_no_evidence_means_no_finding() -> None:
    await _ensure_tables()
    async with AsyncSessionLocal() as session:
        outcome = await emit_finding_or_proposal(
            session,
            agent="test",
            finding_kwargs={
                "finding_key": "x",
                "entity_id": None,
                "finding_type": FINDING_VALIDATION_GAP,
                "declared_state": "d",
                "observed_state": "o",
                "summary": "s",
                "severity": "low",
                "confidence": 0.9,
                "evidence_refs": [],
            },
        )
    assert outcome == "no_evidence"


async def test_low_confidence_goes_to_proposal_not_finding() -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    key = f"weak:{marker}"
    try:
        async with AsyncSessionLocal() as session:
            outcome = await emit_finding_or_proposal(
                session,
                agent="test",
                finding_kwargs={
                    "finding_key": key,
                    "entity_id": None,
                    "finding_type": FINDING_VALIDATION_GAP,
                    "declared_state": "d",
                    "observed_state": "o",
                    "summary": "weak signal",
                    "severity": "low",
                    "confidence": LOW_CONFIDENCE_THRESHOLD - 0.1,
                    "evidence_refs": [{"source_id": "x"}],
                },
            )
            await session.commit()
            proposal = await session.scalar(
                select(AgentProposal).where(
                    AgentProposal.proposal_id == f"finding:{key}"
                )
            )
            finding = await session.scalar(
                select(SecondOpinionFinding).where(
                    SecondOpinionFinding.finding_key == key
                )
            )
        assert outcome == "proposed"
        assert proposal is not None
        assert finding is None
    finally:
        await _cleanup(marker)


async def test_resolved_finding_only_reopens_with_new_evidence() -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    key = f"reopen:{marker}"
    base = {
        "finding_key": key,
        "entity_id": None,
        "finding_type": FINDING_VALIDATION_GAP,
        "declared_state": "d",
        "observed_state": "o-original",
        "summary": "s",
        "severity": "medium",
        "confidence": 0.7,
        "evidence_refs": [{"source_id": "e1"}],
    }
    try:
        async with AsyncSessionLocal() as session:
            await upsert_finding(session, **base)
            await set_finding_status(
                session, finding_key=key, status="resolved"
            )
            # Same evidence + observed: stays resolved.
            same = await upsert_finding(session, **base)
            # New observed state + new evidence: reopens.
            changed = await upsert_finding(
                session,
                **{
                    **base,
                    "observed_state": "o-new",
                    "evidence_refs": [{"source_id": "e2"}],
                },
            )
            await session.commit()
            row = await session.scalar(
                select(SecondOpinionFinding).where(
                    SecondOpinionFinding.finding_key == key
                )
            )
        assert same == "skipped"
        assert changed == "reopened"
        assert row.status == "open"
    finally:
        await _cleanup(marker)


# --- meeting agent ------------------------------------------------------


async def test_meeting_agent_lifts_decisions_actions_risks() -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    doc_id = f"drive:meeting-{marker}"
    transcript = (
        "Summary: weekly sync\n"
        "Decision: ship the SSAP bot fix this week\n"
        "Action: prepare release notes owner=Paul due=2026-06-20\n"
        "Risk: SCADA access may be delayed severity=high\n"
        "Question: who signs off?\n"
    )
    try:
        async with AsyncSessionLocal() as session:
            session.add(
                SourceDocument(
                    source_document_id=doc_id,
                    source_system="drive",
                    source_object_id=f"obj-{marker}",
                    title="Weekly sync",
                    raw_object_ref=f"raw://drive/{marker}",
                    content_hash=f"hash-{marker}",
                )
            )
            session.add(
                DocumentChunk(
                    source_document_id=doc_id,
                    chunk_id="chunk_0",
                    source_system="drive",
                    source_object_id=f"obj-{marker}",
                    raw_object_ref=f"raw://drive/{marker}",
                    text=transcript,
                    start_char=0,
                    end_char=len(transcript),
                    content_hash=f"chash-{marker}",
                )
            )
            await session.commit()

            counts = await scan_meetings(session)
            # Idempotent second run creates nothing new.
            counts2 = await scan_meetings(session)
            await session.commit()

            meetings = list(
                (
                    await session.execute(
                        select(EntityRecord).where(
                            EntityRecord.entity_type == "meeting"
                        )
                    )
                ).scalars()
            )
            mine = [
                m
                for m in meetings
                if (m.attrs or {}).get("source_document_id") == doc_id
            ]
        assert counts["meetings"] >= 1
        assert counts["decisions"] >= 1
        assert counts["action_items"] >= 1
        assert counts["risks"] >= 1
        assert counts2["meetings"] == 0
        assert len(mine) == 1
        assert mine[0].attrs.get("summary")
    finally:
        await _cleanup(marker)


# --- email thread agent -------------------------------------------------


async def test_email_agent_emits_communication_silence() -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    thread_key = f"thread-{marker}"
    now = datetime(2026, 6, 12, tzinfo=timezone.utc)
    try:
        async with AsyncSessionLocal() as session:
            session.add(
                EmailThreadState(
                    source="gmail",
                    thread_key=thread_key,
                    subject_display="Контракт ABC",
                    status="needs_my_reply",
                    last_message_at=now - timedelta(days=5),
                    last_message_from="client@abc.kz",
                    last_message_direction="inbound",
                    days_without_reply=5,
                )
            )
            await session.commit()

            counts = await scan_email_silence(session, now=now)
            await session.commit()
            findings = await list_findings(
                session, status="open", finding_type=FINDING_COMMUNICATION_SILENCE
            )
        mine = [f for f in findings if thread_key in f["finding_key"]]
        assert counts["created"] == 1
        assert len(mine) == 1
        assert mine[0]["visibility_scope"] == "founder"
        assert "5 дн" in mine[0]["observed_state"]
    finally:
        await _cleanup(marker)


async def test_email_agent_skips_threads_under_threshold() -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    thread_key = f"thread-fresh-{marker}"
    now = datetime(2026, 6, 12, tzinfo=timezone.utc)
    try:
        async with AsyncSessionLocal() as session:
            session.add(
                EmailThreadState(
                    source="gmail",
                    thread_key=thread_key,
                    subject_display="Fresh",
                    status="needs_my_reply",
                    last_message_at=now - timedelta(days=1),
                    days_without_reply=1,
                )
            )
            await session.commit()
            counts = await scan_email_silence(session, now=now)
            await session.commit()
        assert counts["created"] == 0
    finally:
        await _cleanup(marker)


# --- hypothesis / focus declaration agents ------------------------------


async def test_hypothesis_agent_validation_gap() -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    try:
        async with AsyncSessionLocal() as session:
            await set_declaration(
                session,
                key=KEY_HYPOTHESES,
                payload={
                    "items": [
                        {
                            "text": f"Клиенты платят за предиктивный мониторинг {marker}",
                            "status": "validated",
                        }
                    ]
                },
            )
            await session.commit()
            counts = await scan_hypotheses(session)
            await session.commit()
            findings = await list_findings(
                session, status="open", finding_type=FINDING_VALIDATION_GAP
            )
        # No supporting evidence for a validated hypothesis -> a gap.
        assert counts["hypotheses"] == 1
        mine = [f for f in findings if marker in f["finding_key"]]
        assert len(mine) == 1
        assert "validated" in mine[0]["declared_state"]
    finally:
        await _cleanup(marker)
        async with AsyncSessionLocal() as session:
            await session.execute(
                delete(FounderDeclaration).where(
                    FounderDeclaration.declaration_key == KEY_HYPOTHESES
                )
            )
            await session.commit()


async def test_focus_drift_requires_declaration() -> None:
    await _ensure_tables()
    # With no focus declaration, the generator emits nothing (skipped).
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(FounderDeclaration).where(
                FounderDeclaration.declaration_key == KEY_FOCUS
            )
        )
        await session.commit()
        counts = await scan_focus_drift(session)
    assert counts["findings"] == 0
    assert counts["skipped"] == 1
