from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from app.db.agent_models import AgentProposal, DataAvailability, MetricSnapshot
from app.db.base import AsyncSessionLocal, engine
from app.db.graph_models import (
    EntityAliasRecord,
    EntityLinkRecord,
    EntityRecord,
    EntitySourceAccount,
)
from app.db.second_opinion_models import SecondOpinionFinding
from app.services.agent_proposals import STATUS_ACCEPTED, decide_proposal
from app.services.confidence import build_confidence, explain_confidence
from app.services.data_availability import (
    STATUS_COLLECTING,
    STATUS_NO_DATA,
    STATUS_READY,
    STATUS_STALE,
    _upsert_availability,
)
from app.services.entity_identity import (
    MERGE_STATUS_APPROVED,
    apply_decided_merges,
    register_source_account,
    resolve_canonical,
    suggest_person_merges,
)
from app.services.knowledge_graph import (
    ENTITY_PERSON,
    REL_WORKS_ON,
    upsert_entity,
    upsert_link,
)
from app.services.second_opinion import (
    FINDING_EXECUTION_MISMATCH,
    STATUS_DISMISSED,
    set_finding_status,
    upsert_finding,
)
from app.services.visibility import SCOPE_FOUNDER, SCOPE_INVESTOR, SCOPE_TEAM, can_view


async def _ensure_tables() -> None:
    async with engine.begin() as conn:
        for table in (
            EntityRecord.__table__,
            EntityAliasRecord.__table__,
            EntityLinkRecord.__table__,
            EntitySourceAccount.__table__,
            AgentProposal.__table__,
            MetricSnapshot.__table__,
            DataAvailability.__table__,
            SecondOpinionFinding.__table__,
        ):
            await conn.run_sync(table.create, checkfirst=True)


def test_confidence_is_explainable() -> None:
    score, factors = build_confidence(
        evidence_count=4,
        source_quality=0.9,
        freshness=0.9,
        cross_source_match=True,
    )
    assert score >= 0.7
    assert factors["cross_source_match"] is True
    hint = explain_confidence(score, factors)
    assert hint.startswith("High confidence")
    assert "несколько" in hint or "нескольких" in hint

    low_score, low_factors = build_confidence(
        evidence_count=1,
        source_quality=0.4,
        freshness=0.2,
        cross_source_match=False,
        contradiction_strength=0.5,
    )
    assert low_score < 0.4
    low_hint = explain_confidence(low_score, low_factors)
    assert low_hint.startswith("Low confidence")
    assert "одном источнике" in low_hint


def test_visibility_hierarchy() -> None:
    assert can_view(SCOPE_FOUNDER, SCOPE_FOUNDER)
    assert can_view(SCOPE_FOUNDER, SCOPE_INVESTOR)
    assert can_view(SCOPE_TEAM, SCOPE_INVESTOR)
    assert not can_view(SCOPE_TEAM, SCOPE_FOUNDER)
    assert not can_view(SCOPE_INVESTOR, SCOPE_TEAM)
    assert not can_view("stranger", SCOPE_INVESTOR)


async def test_finding_lifecycle_and_dedupe() -> None:
    await _ensure_tables()
    key = f"test:finding-{uuid4().hex[:8]}"
    try:
        async with AsyncSessionLocal() as session:
            created = await upsert_finding(
                session,
                finding_key=key,
                entity_id="project:test",
                finding_type=FINDING_EXECUTION_MISMATCH,
                declared_state="Jira: In Progress",
                observed_state="Нет кода",
                summary="QS-1 без кода",
                severity="medium",
                confidence=0.7,
            )
            unchanged = await upsert_finding(
                session,
                finding_key=key,
                entity_id="project:test",
                finding_type=FINDING_EXECUTION_MISMATCH,
                declared_state="Jira: In Progress",
                observed_state="Нет кода",
                summary="QS-1 без кода",
                severity="medium",
                confidence=0.7,
            )
            updated = await upsert_finding(
                session,
                finding_key=key,
                entity_id="project:test",
                finding_type=FINDING_EXECUTION_MISMATCH,
                declared_state="Jira: In Progress",
                observed_state="Нет кода 10 дней",
                summary="QS-1 без кода",
                severity="medium",
                confidence=0.7,
            )
            dismissed = await set_finding_status(
                session, finding_key=key, status=STATUS_DISMISSED
            )
            skipped = await upsert_finding(
                session,
                finding_key=key,
                entity_id="project:test",
                finding_type=FINDING_EXECUTION_MISMATCH,
                declared_state="Jira: In Progress",
                observed_state="Нет кода 12 дней",
                summary="QS-1 без кода",
                severity="medium",
                confidence=0.7,
            )
            await session.commit()

        assert (created, unchanged, updated) == ("created", "unchanged", "updated")
        assert dismissed == {"finding_key": key, "status": STATUS_DISMISSED}
        assert skipped == "skipped"
    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(
                delete(SecondOpinionFinding).where(
                    SecondOpinionFinding.finding_key == key
                )
            )
            await session.commit()


async def test_finding_rejects_unknown_taxonomy() -> None:
    await _ensure_tables()
    async with AsyncSessionLocal() as session:
        with pytest.raises(ValueError):
            await upsert_finding(
                session,
                finding_key="x",
                entity_id=None,
                finding_type="vibes_mismatch",
                declared_state="a",
                observed_state="b",
                summary="c",
                severity="medium",
                confidence=0.5,
            )
        with pytest.raises(ValueError):
            await upsert_finding(
                session,
                finding_key="x",
                entity_id=None,
                finding_type=FINDING_EXECUTION_MISMATCH,
                declared_state="a",
                observed_state="b",
                summary="c",
                severity="catastrophic",
                confidence=0.5,
            )


async def test_data_availability_statuses() -> None:
    await _ensure_tables()
    metric_key = f"test.avail.{uuid4().hex[:8]}"
    now = datetime(2026, 6, 12, tzinfo=timezone.utc)
    try:
        async with AsyncSessionLocal() as session:
            await _upsert_availability(
                session,
                metric_key=metric_key,
                scope="s1",
                points=0,
                last_point=None,
                now=now,
            )
            await _upsert_availability(
                session,
                metric_key=metric_key,
                scope="s2",
                points=2,
                last_point="2026-06-12",
                now=now,
            )
            await _upsert_availability(
                session,
                metric_key=metric_key,
                scope="s3",
                points=7,
                last_point="2026-06-12",
                now=now,
            )
            await _upsert_availability(
                session,
                metric_key=metric_key,
                scope="s4",
                points=7,
                last_point="2026-06-01",
                now=now,
            )
            await session.commit()

            rows = (
                await session.execute(
                    select(DataAvailability).where(
                        DataAvailability.metric_key == metric_key
                    )
                )
            ).scalars()
            by_scope = {row.scope: row for row in rows}

        assert by_scope["s1"].status == STATUS_NO_DATA
        assert by_scope["s2"].status == STATUS_COLLECTING
        assert "точка 2 из 5" in by_scope["s2"].message
        assert by_scope["s3"].status == STATUS_READY
        assert by_scope["s4"].status == STATUS_STALE
        assert "устарели" in by_scope["s4"].message
    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(
                delete(DataAvailability).where(
                    DataAvailability.metric_key == metric_key
                )
            )
            await session.commit()


async def test_merge_cycle_applies_canonical_and_repoints_links() -> None:
    await _ensure_tables()
    sfx = uuid4().hex[:8]
    jira_person = f"person:тест-инженер-{sfx}"
    github_person = f"person:testinzhener{sfx}"
    target = f"person:target-{sfx}"
    try:
        async with AsyncSessionLocal() as session:
            for entity_id, name in (
                (jira_person, f"Тест Инженер {sfx}"),
                (github_person, f"testinzhener{sfx}"),
                (target, "Target"),
            ):
                await upsert_entity(
                    session,
                    entity_id=entity_id,
                    entity_type=ENTITY_PERSON,
                    canonical_name=name,
                )
            await register_source_account(
                session,
                entity_id=jira_person,
                source_system="jira",
                account_id=f"Тест Инженер {sfx}",
            )
            await register_source_account(
                session,
                entity_id=github_person,
                source_system="github",
                account_id=f"testinzhener{sfx}",
            )
            await upsert_link(
                session,
                from_entity_id=github_person,
                relation=REL_WORKS_ON,
                to_entity_id=target,
            )
            suggestions = await suggest_person_merges(session)
            await session.commit()

        assert suggestions == 1

        async with AsyncSessionLocal() as session:
            proposal = await session.scalar(
                select(AgentProposal).where(
                    AgentProposal.dedupe_key.like(f"%{sfx}%")
                )
            )
            assert proposal is not None
            keep = proposal.payload["keep"]
            merge = proposal.payload["merge"]
            assert {keep, merge} == {jira_person, github_person}
            await decide_proposal(
                session,
                proposal_id=proposal.proposal_id,
                decision=STATUS_ACCEPTED,
                decided_by="test",
                decision_reason="один человек",
            )
            counts = await apply_decided_merges(session)
            await session.commit()

        assert counts["applied"] == 1

        async with AsyncSessionLocal() as session:
            merged_row = await session.scalar(
                select(EntityRecord).where(EntityRecord.entity_id == merge)
            )
            assert merged_row is not None
            assert merged_row.canonical_entity_id == keep
            assert merged_row.merge_status == MERGE_STATUS_APPROVED
            assert await resolve_canonical(session, merge) == keep
            if merge == github_person:
                repointed = await session.scalar(
                    select(EntityLinkRecord).where(
                        EntityLinkRecord.link_id
                        == f"{keep}->works_on->{target}"
                    )
                )
                assert repointed is not None
    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(
                delete(AgentProposal).where(
                    AgentProposal.dedupe_key.like(f"%{sfx}%")
                )
            )
            await session.execute(
                delete(EntitySourceAccount).where(
                    EntitySourceAccount.account_id.like(f"%{sfx}%")
                )
            )
            await session.execute(
                delete(EntityLinkRecord).where(
                    EntityLinkRecord.link_id.like(f"%{sfx}%")
                )
            )
            await session.execute(
                delete(EntityAliasRecord).where(
                    EntityAliasRecord.entity_id.like(f"%{sfx}%")
                )
            )
            await session.execute(
                delete(EntityRecord).where(EntityRecord.entity_id.like(f"%{sfx}%"))
            )
            await session.commit()
