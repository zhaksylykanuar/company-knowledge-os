from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import delete

from app.db.agent_models import AgentProposal, MetricSnapshot
from app.db.base import AsyncSessionLocal, engine
from app.db.graph_models import EntityAliasRecord, EntityLinkRecord, EntityRecord
from app.services.agent_proposals import (
    STATUS_ACCEPTED,
    STATUS_PENDING,
    create_proposal,
    decide_proposal,
    list_proposals,
)
from app.services.graph_lift import _name_tokens, _propose_person_merges
from app.services.knowledge_graph import (
    ENTITY_PERSON,
    REL_WORKS_ON,
    link_id,
    person_entity_id,
    slugify,
    upsert_entity,
    upsert_link,
)
from app.services.metric_collector import _record, metric_series


async def _ensure_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(EntityRecord.__table__.create, checkfirst=True)
        await conn.run_sync(EntityAliasRecord.__table__.create, checkfirst=True)
        await conn.run_sync(EntityLinkRecord.__table__.create, checkfirst=True)
        await conn.run_sync(AgentProposal.__table__.create, checkfirst=True)
        await conn.run_sync(MetricSnapshot.__table__.create, checkfirst=True)


async def _cleanup_entities(prefix: str) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(EntityLinkRecord).where(
                EntityLinkRecord.link_id.like(f"%{prefix}%")
            )
        )
        await session.execute(
            delete(EntityAliasRecord).where(
                EntityAliasRecord.entity_id.like(f"%{prefix}%")
            )
        )
        await session.execute(
            delete(EntityRecord).where(EntityRecord.entity_id.like(f"%{prefix}%"))
        )
        await session.commit()


def test_slugify_and_ids() -> None:
    assert slugify("Amir B") == "amir-b"
    assert slugify("alizhan kazscanservice") == "alizhan-kazscanservice"
    assert slugify("Амир Бикчентаев") == "амир-бикчентаев"
    assert slugify("!!!") == "unknown"
    assert person_entity_id("Jane Doe") == "person:jane-doe"
    assert link_id("a", "works_on", "b") == "a->works_on->b"


def test_name_tokens_overlap() -> None:
    assert _name_tokens("person:amir-bikchentaev") == {"amir", "bikchentaev"}
    assert _name_tokens("person:ab") == set()


async def test_upsert_entity_and_link_idempotent() -> None:
    await _ensure_tables()
    suffix = uuid4().hex[:8]
    person = f"person:test-{suffix}"
    project = f"person:test-target-{suffix}"
    try:
        async with AsyncSessionLocal() as session:
            first = await upsert_entity(
                session,
                entity_id=person,
                entity_type=ENTITY_PERSON,
                canonical_name="Test Person",
                attrs={"seen_in_jira": True},
            )
            second = await upsert_entity(
                session,
                entity_id=person,
                entity_type=ENTITY_PERSON,
                canonical_name="Test Person",
                attrs={"seen_in_github": True},
            )
            await upsert_entity(
                session,
                entity_id=project,
                entity_type=ENTITY_PERSON,
                canonical_name="Target",
            )
            link_first = await upsert_link(
                session,
                from_entity_id=person,
                relation=REL_WORKS_ON,
                to_entity_id=project,
                evidence_refs=[{"kind": "test"}],
                confidence=0.9,
            )
            link_second = await upsert_link(
                session,
                from_entity_id=person,
                relation=REL_WORKS_ON,
                to_entity_id=project,
            )
            await session.commit()

        assert first is True and second is False
        assert link_first is True and link_second is False
    finally:
        await _cleanup_entities(suffix)


async def test_upsert_rejects_unknown_vocabulary() -> None:
    await _ensure_tables()
    async with AsyncSessionLocal() as session:
        with pytest.raises(ValueError):
            await upsert_entity(
                session,
                entity_id="thing:1",
                entity_type="thing",
                canonical_name="x",
            )
        with pytest.raises(ValueError):
            await upsert_link(
                session,
                from_entity_id="a",
                relation="likes",
                to_entity_id="b",
            )


async def test_proposals_lifecycle() -> None:
    await _ensure_tables()
    proposal_id = f"test:prop-{uuid4().hex[:8]}"
    try:
        async with AsyncSessionLocal() as session:
            created = await create_proposal(
                session,
                proposal_id=proposal_id,
                agent="test_agent",
                kind="merge_person",
                title="merge?",
                payload={"keep": "a", "merge": "b"},
                confidence=0.6,
            )
            duplicate = await create_proposal(
                session,
                proposal_id=proposal_id,
                agent="test_agent",
                kind="merge_person",
                title="merge?",
                payload={},
                confidence=0.6,
            )
            pending = await list_proposals(session, status=STATUS_PENDING, limit=100)
            decided = await decide_proposal(
                session,
                proposal_id=proposal_id,
                decision=STATUS_ACCEPTED,
                decided_by="test",
            )
            await session.commit()

        assert created is True and duplicate is False
        assert any(item["proposal_id"] == proposal_id for item in pending)
        assert decided == {"proposal_id": proposal_id, "status": STATUS_ACCEPTED}

        async with AsyncSessionLocal() as session:
            with pytest.raises(ValueError):
                await decide_proposal(
                    session,
                    proposal_id=proposal_id,
                    decision=STATUS_ACCEPTED,
                    decided_by="test",
                )
    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(
                delete(AgentProposal).where(
                    AgentProposal.proposal_id == proposal_id
                )
            )
            await session.commit()


async def test_merge_proposals_only_for_overlapping_names() -> None:
    await _ensure_tables()
    # Distinct suffixes per name: a shared suffix would itself count as a
    # shared token and create false merge pairs.
    sfx = [uuid4().hex[:8] for _ in range(3)]
    try:
        async with AsyncSessionLocal() as session:
            count = await _propose_person_merges(
                session,
                jira_people={f"person:j{sfx[0]}-amir-bikchentaev"},
                github_people={
                    f"person:g{sfx[1]}-amir",
                    f"person:g{sfx[2]}-unrelated-zzz",
                },
            )
            await session.commit()
        assert count == 1
    finally:
        async with AsyncSessionLocal() as session:
            for marker in sfx:
                await session.execute(
                    delete(AgentProposal).where(
                        AgentProposal.proposal_id.like(f"%{marker}%")
                    )
                )
            await session.commit()


async def test_metric_record_upsert_and_series() -> None:
    await _ensure_tables()
    metric_key = f"test.metric.{uuid4().hex[:8]}"
    try:
        async with AsyncSessionLocal() as session:
            first = await _record(
                session,
                metric_key=metric_key,
                scope="global",
                captured_on="2026-06-12",
                value=10,
            )
            unchanged = await _record(
                session,
                metric_key=metric_key,
                scope="global",
                captured_on="2026-06-12",
                value=10,
            )
            updated = await _record(
                session,
                metric_key=metric_key,
                scope="global",
                captured_on="2026-06-12",
                value=12,
            )
            await _record(
                session,
                metric_key=metric_key,
                scope="global",
                captured_on="2026-06-11",
                value=8,
            )
            series = await metric_series(
                session, metric_key=metric_key, scope="global", days=10
            )
            await session.commit()

        assert (first, unchanged, updated) == ("created", "unchanged", "updated")
        assert [point["value"] for point in series] == [8.0, 12.0]
    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(
                delete(MetricSnapshot).where(
                    MetricSnapshot.metric_key == metric_key
                )
            )
            await session.commit()
