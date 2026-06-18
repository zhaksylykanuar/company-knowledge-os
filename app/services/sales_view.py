"""Sales signals read model (no finance).

Reads the sales graph the sales_signal_agent built — accounts
(``client``), contacts (``person`` employed_by), opportunities
(``deal`` signal entities with warmth) — plus the relationship findings
(``communication_silence``) tied to those accounts. Never any money:
no amounts, no revenue, no pipeline value.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.graph_models import EntityLinkRecord, EntityRecord
from app.db.second_opinion_models import SecondOpinionFinding
from app.services.knowledge_graph import (
    ENTITY_CLIENT,
    ENTITY_DEAL,
    REL_BELONGS_TO,
    REL_EMPLOYED_BY,
)
from app.services.second_opinion import STATUS_OPEN, _finding_read_model

_WARMTH_ORDER = {"warm": 0, "cooling": 1, "cold": 2, "unknown": 3}


async def build_sales_signals(session: AsyncSession) -> dict[str, Any]:
    clients = list(
        (
            await session.execute(
                select(EntityRecord).where(
                    EntityRecord.entity_type == ENTITY_CLIENT
                )
            )
        ).scalars()
    )
    deals = list(
        (
            await session.execute(
                select(EntityRecord).where(EntityRecord.entity_type == ENTITY_DEAL)
            )
        ).scalars()
    )
    links = list(
        (
            await session.execute(
                select(EntityLinkRecord).where(
                    EntityLinkRecord.relation.in_(
                        [REL_EMPLOYED_BY, REL_BELONGS_TO]
                    )
                )
            )
        ).scalars()
    )

    contacts_by_client: dict[str, list[str]] = {}
    deal_by_client: dict[str, str] = {}
    for link in links:
        if link.relation == REL_EMPLOYED_BY:
            contacts_by_client.setdefault(link.to_entity_id, []).append(
                link.from_entity_id
            )
        elif link.relation == REL_BELONGS_TO and link.from_entity_id.startswith(
            "deal:"
        ):
            deal_by_client[link.to_entity_id] = link.from_entity_id

    contact_names: dict[str, str] = {}
    if contacts_by_client:
        contact_ids = {cid for ids in contacts_by_client.values() for cid in ids}
        rows = (
            await session.execute(
                select(EntityRecord).where(
                    EntityRecord.entity_id.in_(contact_ids)
                )
            )
        ).scalars()
        contact_names = {r.entity_id: r.canonical_name for r in rows}

    # Relationship findings keyed to deal entities.
    finding_rows = (
        await session.execute(
            select(SecondOpinionFinding)
            .where(SecondOpinionFinding.status == STATUS_OPEN)
            .where(SecondOpinionFinding.entity_id.like("deal:%"))
        )
    ).scalars()
    findings_by_deal: dict[str, list[dict[str, Any]]] = {}
    for row in finding_rows:
        findings_by_deal.setdefault(row.entity_id, []).append(
            _finding_read_model(row)
        )

    accounts: list[dict[str, Any]] = []
    for client in clients:
        deal_id = deal_by_client.get(client.entity_id)
        accounts.append(
            {
                "client_id": client.entity_id,
                "name": client.canonical_name,
                "domain": (client.attrs or {}).get("domain"),
                "warmth": (client.attrs or {}).get("warmth", "unknown"),
                "messages_seen": (client.attrs or {}).get("messages_seen", 0),
                "last_message_at": (client.attrs or {}).get("last_message_at"),
                "contacts": [
                    {"contact_id": cid, "name": contact_names.get(cid, cid)}
                    for cid in contacts_by_client.get(client.entity_id, [])
                ],
                "deal_id": deal_id,
                "signals": findings_by_deal.get(deal_id, []) if deal_id else [],
            }
        )

    accounts.sort(key=lambda a: _WARMTH_ORDER.get(a["warmth"], 3))

    warmth_counts: dict[str, int] = {}
    for account in accounts:
        warmth_counts[account["warmth"]] = warmth_counts.get(account["warmth"], 0) + 1

    return {
        "accounts": accounts,
        "counts": {
            "accounts": len(accounts),
            "contacts": sum(len(a["contacts"]) for a in accounts),
            "deals": len(deals),
            "by_warmth": warmth_counts,
            "relationship_risks": sum(len(a["signals"]) for a in accounts),
        },
    }
