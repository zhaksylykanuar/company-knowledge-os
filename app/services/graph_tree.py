"""Knowledge tree read model: nodes and links for the constellation view.

Nodes glow by freshness (recent updates), links carry confidence;
low-confidence links are flagged ``disputed`` and surface in the inbox.
Merged-away nodes are folded into their canonical survivor.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.graph_models import EntityLinkRecord, EntityRecord, EntitySourceAccount
from app.services.confidence import explain_confidence

DISPUTED_CONFIDENCE_THRESHOLD = 0.7
FRESHNESS_HALF_LIFE_DAYS = 7.0


def _freshness(updated_at: datetime | None, now: datetime) -> float:
    if updated_at is None:
        return 0.1
    age_days = max(0.0, (now - updated_at).total_seconds() / 86400.0)
    return round(1.0 / (1.0 + age_days / FRESHNESS_HALF_LIFE_DAYS), 2)


async def build_graph_tree(
    session: AsyncSession,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    safe_now = now or datetime.now(timezone.utc)

    entities = list((await session.execute(select(EntityRecord))).scalars())
    merged_into: dict[str, str] = {
        row.entity_id: row.canonical_entity_id
        for row in entities
        if row.canonical_entity_id and row.merge_status == "approved"
    }

    accounts_by_entity: dict[str, list[dict[str, str]]] = {}
    accounts = (await session.execute(select(EntitySourceAccount))).scalars()
    for account in accounts:
        target = merged_into.get(account.entity_id, account.entity_id)
        accounts_by_entity.setdefault(target, []).append(
            {"source_system": account.source_system, "account_id": account.account_id}
        )

    nodes = []
    for row in entities:
        if row.entity_id in merged_into:
            continue
        nodes.append(
            {
                "entity_id": row.entity_id,
                "entity_type": row.entity_type,
                "name": row.canonical_name,
                "freshness": _freshness(row.updated_at or row.created_at, safe_now),
                "merge_status": row.merge_status,
                "attrs": row.attrs or {},
                "source_accounts": accounts_by_entity.get(row.entity_id, []),
            }
        )

    links = []
    seen_links: set[tuple[str, str, str]] = set()
    link_rows = (await session.execute(select(EntityLinkRecord))).scalars()
    for link in link_rows:
        source = merged_into.get(link.from_entity_id, link.from_entity_id)
        target = merged_into.get(link.to_entity_id, link.to_entity_id)
        if source == target:
            continue
        dedupe = (source, link.relation, target)
        if dedupe in seen_links:
            continue
        seen_links.add(dedupe)
        disputed = link.confidence < DISPUTED_CONFIDENCE_THRESHOLD
        links.append(
            {
                "link_id": link.link_id,
                "from": source,
                "to": target,
                "relation": link.relation,
                "confidence": link.confidence,
                "confidence_hint": explain_confidence(
                    link.confidence, link.confidence_factors or {}
                ),
                "disputed": disputed,
            }
        )

    node_ids = {node["entity_id"] for node in nodes}
    links = [
        link for link in links if link["from"] in node_ids and link["to"] in node_ids
    ]

    by_type: dict[str, int] = {}
    for node in nodes:
        by_type[node["entity_type"]] = by_type.get(node["entity_type"], 0) + 1

    return {
        "generated_at": safe_now.isoformat(),
        "nodes": nodes,
        "links": links,
        "counts": {
            "nodes": len(nodes),
            "links": len(links),
            "disputed_links": sum(1 for link in links if link["disputed"]),
            "by_type": by_type,
        },
    }


async def list_disputed_links(session: AsyncSession) -> list[dict[str, Any]]:
    """Low-confidence links for the inbox review queue."""

    rows = (
        await session.execute(
            select(EntityLinkRecord)
            .where(EntityLinkRecord.confidence < DISPUTED_CONFIDENCE_THRESHOLD)
            .order_by(EntityLinkRecord.confidence)
        )
    ).scalars()
    return [
        {
            "link_id": row.link_id,
            "from": row.from_entity_id,
            "to": row.to_entity_id,
            "relation": row.relation,
            "confidence": row.confidence,
            "confidence_hint": explain_confidence(
                row.confidence, row.confidence_factors or {}
            ),
            "evidence_refs": row.evidence_refs,
        }
        for row in rows
    ]


async def review_link(
    session: AsyncSession,
    *,
    link_id: str,
    decision: str,
    reviewer_id: str,
) -> dict[str, Any] | None:
    """Founder decision on a disputed link: confirm or remove. Audited."""

    from app.services.inbox_audit import ACTION_LINK_REVIEW, record_inbox_action

    if decision not in {"confirm", "remove"}:
        raise ValueError("decision must be confirm or remove")
    row = await session.scalar(
        select(EntityLinkRecord).where(EntityLinkRecord.link_id == link_id)
    )
    if row is None:
        return None
    previous_state = {
        "status": "disputed",
        "from": row.from_entity_id,
        "relation": row.relation,
        "to": row.to_entity_id,
        "confidence": row.confidence,
        "evidence_refs": list(row.evidence_refs or []),
    }
    if decision == "confirm":
        row.confidence = 0.95
        factors = dict(row.confidence_factors or {})
        factors["confirmed_by"] = reviewer_id
        row.confidence_factors = factors
        await session.flush()
        next_state = {"status": "confirmed", "confidence": 0.95}
        reversible = True
    else:
        await session.delete(row)
        await session.flush()
        # previous_state keeps everything needed to recreate the link.
        next_state = {"status": "removed"}
        reversible = True
    await record_inbox_action(
        session,
        action=ACTION_LINK_REVIEW,
        actor=reviewer_id,
        target_id=link_id,
        previous_state=previous_state,
        next_state=next_state,
        reversible=reversible,
    )
    return {
        "link_id": link_id,
        "decision": "confirmed" if decision == "confirm" else "removed",
    }
