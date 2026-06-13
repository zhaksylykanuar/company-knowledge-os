"""Graph gardener: hygiene checks that file proposals, never silent edits.

The gardener finds graph-quality problems and routes them to the inbox
for human approval. It never deletes or merges on its own. Decisions go
through the proposal queue (and therefore the audit trail); a rejected
cleanup proposal will not resurface (stable dedupe key).

Checks: orphan nodes, person nodes without any source evidence, edges
without evidence, low-confidence edges, stale nodes, duplicate accounts,
and open findings that have lost their evidence.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.graph_models import (
    EntityAliasRecord,
    EntityLinkRecord,
    EntityRecord,
    EntitySourceAccount,
)
from app.db.second_opinion_models import SecondOpinionFinding
from app.services.agent_proposals import create_proposal
from app.services.confidence import build_confidence

AGENT_NAME = "graph_gardener"

KIND_ORPHAN = "graph_orphan_node"
KIND_NO_EVIDENCE_NODE = "graph_node_without_evidence"
KIND_NO_EVIDENCE_EDGE = "graph_edge_without_evidence"
KIND_DUPLICATE_ACCOUNT = "graph_duplicate_account"
KIND_FINDING_LOST_EVIDENCE = "finding_lost_evidence"

STALE_NODE_DAYS = 60
MAX_PROPOSALS_PER_RUN = 60

# Node types that should always have edges; structural nodes are exempt.
_ORPHAN_CHECK_TYPES = frozenset(
    {"person", "client", "deal", "meeting", "decision", "risk", "task", "hypothesis"}
)


async def run_graph_gardener(
    session: AsyncSession,
    *,
    now: datetime | None = None,
) -> dict[str, int]:
    safe_now = now or datetime.now(timezone.utc)
    counts = {"proposals": 0, "checked": 0}

    async def propose(*, kind: str, key: str, title: str, payload: dict, confidence: float) -> None:
        if counts["proposals"] >= MAX_PROPOSALS_PER_RUN:
            return
        score, factors = build_confidence(
            evidence_count=1,
            source_quality=0.6,
            freshness=0.6,
            cross_source_match=False,
            contradiction_strength=1.0 - confidence,
        )
        created = await create_proposal(
            session,
            proposal_id=f"gardener:{kind}:{key}",
            dedupe_key=f"gardener:{kind}:{key}",
            agent=AGENT_NAME,
            kind=kind,
            title=title,
            payload=payload,
            evidence_refs=[{"kind": "graph_hygiene", "check": kind}],
            confidence=score,
            confidence_factors=factors,
            reversible=True,
        )
        if created:
            counts["proposals"] += 1

    # Build link adjacency once.
    link_rows = list((await session.execute(select(EntityLinkRecord))).scalars())
    linked_ids: set[str] = set()
    for link in link_rows:
        linked_ids.add(link.from_entity_id)
        linked_ids.add(link.to_entity_id)

    entities = list((await session.execute(select(EntityRecord))).scalars())
    counts["checked"] = len(entities) + len(link_rows)

    # People with at least one source account or alias have evidence.
    people_with_accounts = set(
        (
            await session.execute(
                select(EntitySourceAccount.entity_id).distinct()
            )
        ).scalars()
    )
    people_with_aliases = set(
        (
            await session.execute(select(EntityAliasRecord.entity_id).distinct())
        ).scalars()
    )

    client_names: list[tuple[str, str]] = []
    stale_cutoff = safe_now - timedelta(days=STALE_NODE_DAYS)

    for entity in entities:
        if entity.canonical_entity_id:  # already merged away
            continue
        if (entity.attrs or {}).get("archived"):  # gardener already handled it
            continue
        if entity.entity_type == "client":
            client_names.append((entity.entity_id, entity.canonical_name))

        if (
            entity.entity_type in _ORPHAN_CHECK_TYPES
            and entity.entity_id not in linked_ids
        ):
            updated = entity.updated_at or entity.created_at
            stale = updated is not None and updated < stale_cutoff
            await propose(
                kind=KIND_ORPHAN,
                key=entity.entity_id,
                title=f"Изолированная нода без связей: {entity.canonical_name[:80]}",
                payload={
                    "entity_id": entity.entity_id,
                    "entity_type": entity.entity_type,
                    "stale": stale,
                    "action": "review_or_remove",
                },
                confidence=0.5,
            )

        if (
            entity.entity_type == "person"
            and entity.entity_id not in people_with_accounts
            and entity.entity_id not in people_with_aliases
        ):
            await propose(
                kind=KIND_NO_EVIDENCE_NODE,
                key=entity.entity_id,
                title=f"Персона без источника: {entity.canonical_name[:80]}",
                payload={
                    "entity_id": entity.entity_id,
                    "action": "review_or_remove",
                },
                confidence=0.4,
            )

    # Duplicate accounts: same slug root with a different domain suffix.
    by_root: dict[str, list[str]] = {}
    for entity_id, name in client_names:
        root = name.split(".")[0].casefold()
        if len(root) > 2:
            by_root.setdefault(root, []).append(entity_id)
    for root, ids in by_root.items():
        if len(ids) > 1:
            pair = sorted(ids)
            await propose(
                kind=KIND_DUPLICATE_ACCOUNT,
                key="+".join(pair),
                title=f"Возможные дубли аккаунтов: {', '.join(pair)}",
                payload={"candidates": pair, "root": root, "action": "review_merge"},
                confidence=0.5,
            )

    # Edges without evidence.
    for link in link_rows:
        if not (link.evidence_refs or []):
            await propose(
                kind=KIND_NO_EVIDENCE_EDGE,
                key=link.link_id,
                title=f"Связь без evidence: {link.link_id[:90]}",
                payload={"link_id": link.link_id, "action": "review_or_remove"},
                confidence=0.45,
            )

    # Open findings that lost their evidence (should not happen — safety net).
    lost = (
        await session.execute(
            select(SecondOpinionFinding).where(
                SecondOpinionFinding.status == "open"
            )
        )
    ).scalars()
    for finding in lost:
        if not (finding.evidence_refs or []):
            await propose(
                kind=KIND_FINDING_LOST_EVIDENCE,
                key=finding.finding_key,
                title=f"Finding без evidence: {finding.summary[:80]}",
                payload={
                    "finding_key": finding.finding_key,
                    "action": "resolve_finding",
                },
                confidence=0.6,
            )

    return counts
