from __future__ import annotations

from uuid import uuid4

from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import delete, select

from app.api.auth import API_AUTH_FAILURE_DETAIL, settings
from app.db.agent_models import AgentProposal
from app.db.base import AsyncSessionLocal
from app.db.graph_models import (
    EntityAliasRecord,
    EntityLinkRecord,
    EntityRecord,
    EntitySourceAccount,
)
from app.db.second_opinion_models import SecondOpinionFinding
from app.main import app
from app.services.agent_proposals import create_proposal
from app.services.entity_identity import KIND_ENTITY_MERGE
from app.services.knowledge_graph import (
    ENTITY_PERSON,
    REL_WORKS_ON,
    upsert_entity,
    upsert_link,
)
from app.services.second_opinion import FINDING_DELIVERY_RISK, upsert_finding


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _set_auth(monkeypatch, *, enabled: bool) -> None:
    monkeypatch.setattr(settings, "api_auth_enabled", enabled)
    monkeypatch.setattr(
        settings, "api_auth_key", SecretStr("test-api-key") if enabled else None
    )
    monkeypatch.setattr(settings, "api_auth_header_name", "X-FounderOS-API-Key")


async def _cleanup(marker: str) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(AgentProposal).where(AgentProposal.proposal_id.like(f"%{marker}%"))
        )
        await session.execute(
            delete(SecondOpinionFinding).where(
                SecondOpinionFinding.finding_key.like(f"%{marker}%")
            )
        )
        await session.execute(
            delete(EntityLinkRecord).where(
                EntityLinkRecord.link_id.like(f"%{marker}%")
            )
        )
        await session.execute(
            delete(EntitySourceAccount).where(
                EntitySourceAccount.account_id.like(f"%{marker}%")
            )
        )
        await session.execute(
            delete(EntityAliasRecord).where(
                EntityAliasRecord.entity_id.like(f"%{marker}%")
            )
        )
        await session.execute(
            delete(EntityRecord).where(EntityRecord.entity_id.like(f"%{marker}%"))
        )
        await session.commit()


async def test_inbox_requires_auth(monkeypatch) -> None:
    _set_auth(monkeypatch, enabled=True)
    async with _client() as client:
        response = await client.get("/v1/inbox")
    assert response.status_code == 401
    assert response.json() == {"detail": API_AUTH_FAILURE_DETAIL}


async def test_inbox_exposes_product_facing_proposal_fields(monkeypatch) -> None:
    _set_auth(monkeypatch, enabled=False)
    marker = uuid4().hex[:8]
    proposal_id = f"test:{marker}"
    try:
        async with AsyncSessionLocal() as session:
            await create_proposal(
                session,
                proposal_id=proposal_id,
                agent="test_agent",
                kind="entity_merge_proposal",
                title="merge?",
                payload={"keep": "a", "merge": "b"},
                confidence=0.7,
                confidence_factors={"evidence_count": 2},
            )
            await session.commit()

        async with _client() as client:
            response = await client.get("/v1/inbox")
        assert response.status_code == 200
        data = response.json()
        item = next(p for p in data["proposals"] if p["proposal_id"] == proposal_id)
        assert item["proposal_type"] == "entity_merge_proposal"
        assert "reviewer_id" in item
        assert "kind" not in item
        assert "decided_by" not in item
        assert item["confidence_hint"]
        assert item["consequences"]
        assert {"proposals", "findings_open", "disputed_links", "total"} <= set(
            data["counts"]
        )
    finally:
        await _cleanup(marker)


async def test_merge_proposal_accept_applies_canonical(monkeypatch) -> None:
    _set_auth(monkeypatch, enabled=False)
    marker = uuid4().hex[:8]
    keep = f"person:keep-{marker}"
    merge = f"person:merge-{marker}"
    target = f"person:target-{marker}"
    proposal_id = f"merge-test:{marker}"
    try:
        async with AsyncSessionLocal() as session:
            for entity_id in (keep, merge, target):
                await upsert_entity(
                    session,
                    entity_id=entity_id,
                    entity_type=ENTITY_PERSON,
                    canonical_name=entity_id,
                )
            await upsert_link(
                session,
                from_entity_id=merge,
                relation=REL_WORKS_ON,
                to_entity_id=target,
            )
            await create_proposal(
                session,
                proposal_id=proposal_id,
                agent="entity_identity",
                kind=KIND_ENTITY_MERGE,
                title="merge?",
                payload={"keep": keep, "merge": merge},
                confidence=0.7,
            )
            await session.commit()

        async with _client() as client:
            response = await client.post(
                f"/v1/inbox/proposals/{proposal_id}/decision",
                json={"decision": "accepted", "reviewer_id": "founder-test"},
            )
            assert response.status_code == 200
            body = response.json()
            assert body["status"] == "accepted"
            assert body["reviewer_id"] == "founder-test"
            assert body["applied"]["applied"] == 1

            repeat = await client.post(
                f"/v1/inbox/proposals/{proposal_id}/decision",
                json={"decision": "accepted"},
            )
            assert repeat.status_code == 409

        async with AsyncSessionLocal() as session:
            merged = await session.scalar(
                select(EntityRecord).where(EntityRecord.entity_id == merge)
            )
            repointed = await session.scalar(
                select(EntityLinkRecord).where(
                    EntityLinkRecord.link_id == f"{keep}->works_on->{target}"
                )
            )
        assert merged is not None and merged.canonical_entity_id == keep
        assert repointed is not None
    finally:
        await _cleanup(marker)


async def test_second_opinion_feed_and_lifecycle(monkeypatch) -> None:
    _set_auth(monkeypatch, enabled=False)
    marker = uuid4().hex[:8]
    key_a = f"test:{marker}:a"
    key_b = f"test:{marker}:b"
    try:
        async with AsyncSessionLocal() as session:
            for key, severity in ((key_a, "high"), (key_b, "low")):
                await upsert_finding(
                    session,
                    finding_key=key,
                    entity_id=f"project:test-{marker}",
                    finding_type=FINDING_DELIVERY_RISK,
                    declared_state="срок задан",
                    observed_state="срок прошёл",
                    summary=f"finding {key}",
                    severity=severity,
                    confidence=0.8,
                    confidence_factors={"evidence_count": 1},
                )
            await session.commit()

        async with _client() as client:
            feed = await client.get(
                "/v1/founder/second-opinion",
                params={"status": "open", "limit": 200},
            )
            assert feed.status_code == 200
            findings = feed.json()["findings"]
            mine = [f for f in findings if marker in f["finding_key"]]
            assert len(mine) == 2
            index_a = next(
                i for i, f in enumerate(findings) if f["finding_key"] == key_a
            )
            index_b = next(
                i for i, f in enumerate(findings) if f["finding_key"] == key_b
            )
            assert index_a < index_b
            assert mine[0]["suggested_action"]
            assert mine[0]["confidence_hint"]

            dismissed = await client.post(
                f"/v1/founder/second-opinion/{key_a}/status",
                json={"status": "dismissed", "note": "ложная тревога"},
            )
            assert dismissed.status_code == 200

            snoozed = await client.post(
                f"/v1/founder/second-opinion/{key_b}/snooze",
                json={"days": 7},
            )
            assert snoozed.status_code == 200

            after = await client.get(
                "/v1/founder/second-opinion",
                params={"status": "open", "limit": 200},
            )
            assert not [
                f
                for f in after.json()["findings"]
                if marker in f["finding_key"]
            ]

            noted = await client.post(
                f"/v1/founder/second-opinion/{key_b}/note",
                json={"note": "проверить в пятницу"},
            )
            assert noted.status_code == 200
            assert noted.json()["note"] == "проверить в пятницу"

            bad = await client.get(
                "/v1/founder/second-opinion",
                params={"finding_type": "vibes"},
            )
            assert bad.status_code == 400
    finally:
        await _cleanup(marker)


async def test_graph_tree_and_disputed_link_review(monkeypatch) -> None:
    _set_auth(monkeypatch, enabled=False)
    marker = uuid4().hex[:8]
    node_a = f"person:tree-a-{marker}"
    node_b = f"person:tree-b-{marker}"
    try:
        async with AsyncSessionLocal() as session:
            for entity_id in (node_a, node_b):
                await upsert_entity(
                    session,
                    entity_id=entity_id,
                    entity_type=ENTITY_PERSON,
                    canonical_name=entity_id,
                )
            await upsert_link(
                session,
                from_entity_id=node_a,
                relation=REL_WORKS_ON,
                to_entity_id=node_b,
                confidence=0.5,
            )
            await session.commit()

        async with _client() as client:
            tree = await client.get("/v1/graph/tree")
            assert tree.status_code == 200
            data = tree.json()
            node_ids = {n["entity_id"] for n in data["nodes"]}
            assert {node_a, node_b} <= node_ids
            link = next(
                line
                for line in data["links"]
                if line["from"] == node_a and line["to"] == node_b
            )
            assert link["disputed"] is True
            assert "freshness" in data["nodes"][0]

            inbox = (await client.get("/v1/inbox")).json()
            assert any(
                item["link_id"] == link["link_id"]
                for item in inbox["disputed_links"]
            )

            review = await client.post(
                f"/v1/graph/links/{link['link_id']}/review",
                json={"decision": "confirm", "reviewer_id": "founder-test"},
            )
            assert review.status_code == 200
            assert review.json() == {
                "link_id": link["link_id"],
                "decision": "confirmed",
            }

            tree_after = (await client.get("/v1/graph/tree")).json()
            link_after = next(
                line
                for line in tree_after["links"]
                if line["link_id"] == link["link_id"]
            )
            assert link_after["disputed"] is False
            assert link_after["confidence"] == 0.95
    finally:
        await _cleanup(marker)


async def test_data_availability_endpoint(monkeypatch) -> None:
    _set_auth(monkeypatch, enabled=False)
    async with _client() as client:
        response = await client.get("/v1/founder/data-availability")
    assert response.status_code == 200
    rows = response.json()["availability"]
    if rows:
        assert {"metric_key", "scope", "status", "message"} <= set(rows[0])
