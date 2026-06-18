"""Graph gardener apply flow: safe Accept actions, never silent deletes.

Each gardener proposal type maps to a *safe* action on Accept:

- orphan node / node without evidence -> mark archived (hidden from
  read models), never deleted without a separate dangerous approval;
- edge without evidence -> remove the edge (the Accept IS the approval;
  the removed edge is recorded in the audit payload so it can be
  recreated);
- duplicate account -> file an explicit ``entity_merge_proposal`` rather
  than merging directly (merge only via the confirmed merge flow);
- finding without evidence -> suppress the finding (status dismissed),
  audited, never silently closed.

Reject is handled by the proposal status + stable dedupe key: a rejected
cleanup will not resurface without new evidence.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.agent_models import AgentProposal
from app.db.graph_models import EntityLinkRecord, EntityRecord
from app.db.second_opinion_models import SecondOpinionFinding
from app.services.agent_proposals import STATUS_ACCEPTED, mark_applied

ARCHIVE_KINDS = {"graph_orphan_node", "graph_node_without_evidence"}
MERGE_CONFIDENCE_FOR_DUPLICATE = 0.8


async def _archive_node(session: AsyncSession, entity_id: str) -> dict[str, Any]:
    row = await session.scalar(
        select(EntityRecord).where(EntityRecord.entity_id == entity_id)
    )
    if row is None:
        return {"applied": "node_missing"}
    attrs = dict(row.attrs or {})
    attrs["archived"] = True
    row.attrs = attrs
    await session.flush()
    return {"applied": "archived", "entity_id": entity_id}


async def _remove_edge(session: AsyncSession, link_id: str) -> dict[str, Any]:
    row = await session.scalar(
        select(EntityLinkRecord).where(EntityLinkRecord.link_id == link_id)
    )
    if row is None:
        return {"applied": "edge_missing"}
    snapshot = {
        "link_id": row.link_id,
        "from": row.from_entity_id,
        "relation": row.relation,
        "to": row.to_entity_id,
        "confidence": row.confidence,
        "evidence_refs": list(row.evidence_refs or []),
    }
    await session.delete(row)
    await session.flush()
    return {"applied": "edge_removed", "removed_edge": snapshot}


async def _suppress_finding(session: AsyncSession, finding_key: str) -> dict[str, Any]:
    from app.services.second_opinion import STATUS_DISMISSED

    row = await session.scalar(
        select(SecondOpinionFinding).where(
            SecondOpinionFinding.finding_key == finding_key
        )
    )
    if row is None:
        return {"applied": "finding_missing"}
    row.status = STATUS_DISMISSED
    row.note = "gardener: подавлено — finding без evidence"
    await session.flush()
    return {"applied": "finding_suppressed", "finding_key": finding_key}


async def _file_duplicate_merge(
    session: AsyncSession, proposal: AgentProposal
) -> dict[str, Any]:
    from app.services.agent_proposals import create_proposal
    from app.services.entity_identity import KIND_ENTITY_MERGE

    candidates = (proposal.payload or {}).get("candidates") or []
    if len(candidates) < 2:
        return {"applied": "no_candidates"}
    pair = sorted(candidates)[:2]
    created = await create_proposal(
        session,
        proposal_id=f"merge:{pair[0]}+{pair[1]}",
        dedupe_key=f"merge:{pair[0]}+{pair[1]}",
        agent="gardener_apply",
        kind=KIND_ENTITY_MERGE,
        title=f"Объединить дубли аккаунтов? {pair[0]} и {pair[1]}",
        payload={"keep": pair[0], "merge": pair[1]},
        evidence_refs=list(proposal.evidence_refs or []),
        confidence=MERGE_CONFIDENCE_FOR_DUPLICATE,
    )
    return {
        "applied": "merge_proposal_filed" if created else "merge_proposal_exists",
        "keep": pair[0],
        "merge": pair[1],
    }


async def apply_gardener_proposal(
    session: AsyncSession, proposal: AgentProposal
) -> dict[str, Any]:
    """Apply one accepted gardener proposal's safe action and mark it
    applied. Idempotent: a non-accepted/applied proposal is a no-op."""

    if proposal.status != STATUS_ACCEPTED or proposal.applied_at is not None:
        return {"applied": "skipped"}

    payload = proposal.payload or {}
    if proposal.kind in ARCHIVE_KINDS:
        result = await _archive_node(session, str(payload.get("entity_id") or ""))
    elif proposal.kind == "graph_edge_without_evidence":
        result = await _remove_edge(session, str(payload.get("link_id") or ""))
    elif proposal.kind == "finding_lost_evidence":
        result = await _suppress_finding(
            session, str(payload.get("finding_key") or "")
        )
    elif proposal.kind == "graph_duplicate_account":
        result = await _file_duplicate_merge(session, proposal)
    else:
        result = {"applied": "no_handler"}

    await mark_applied(session, proposal)
    return result


async def apply_accepted_gardener_proposals(
    session: AsyncSession,
) -> dict[str, int]:
    """Batch apply for the pipeline: process all accepted-but-unapplied
    gardener proposals."""

    from app.services.graph_gardener import (
        KIND_DUPLICATE_ACCOUNT,
        KIND_FINDING_LOST_EVIDENCE,
        KIND_NO_EVIDENCE_EDGE,
        KIND_NO_EVIDENCE_NODE,
        KIND_ORPHAN,
    )

    kinds = [
        KIND_ORPHAN,
        KIND_NO_EVIDENCE_NODE,
        KIND_NO_EVIDENCE_EDGE,
        KIND_DUPLICATE_ACCOUNT,
        KIND_FINDING_LOST_EVIDENCE,
    ]
    rows = (
        await session.execute(
            select(AgentProposal)
            .where(AgentProposal.kind.in_(kinds))
            .where(AgentProposal.status == STATUS_ACCEPTED)
            .where(AgentProposal.applied_at.is_(None))
        )
    ).scalars()
    counts = {"applied": 0}
    for proposal in rows:
        await apply_gardener_proposal(session, proposal)
        counts["applied"] += 1
    return counts
