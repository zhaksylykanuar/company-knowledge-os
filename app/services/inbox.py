"""Inbox read model: everything that waits for the founder's decision.

A decision center, not a list: each item carries why the AI thinks so
(confidence factors + hint), what it saw (source_snapshot, evidence)
and what happens on accept (consequences).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.graph_models import EntityLinkRecord
from app.db.second_opinion_models import SecondOpinionFinding
from app.services.agent_proposals import (
    STATUS_ACCEPTED,
    STATUS_PENDING,
    STATUS_REJECTED,
    decide_proposal,
    list_proposals,
)
from app.services.confidence import explain_confidence
from app.services.entity_identity import KIND_ENTITY_MERGE, apply_decided_merges
from app.services.graph_tree import list_disputed_links
from app.services.second_opinion import STATUS_OPEN as FINDING_OPEN
from app.services.second_opinion import list_findings

_CONSEQUENCES = {
    KIND_ENTITY_MERGE: (
        "Ноды будут объединены: связи и алиасы дубликата перейдут к "
        "основной ноде, активность сольётся в один профиль. Обратимо."
    ),
}


async def _merge_consequences(
    session: AsyncSession, payload: dict[str, Any]
) -> str:
    merge_id = str(payload.get("merge") or "")
    if not merge_id:
        return _CONSEQUENCES[KIND_ENTITY_MERGE]
    links = (
        await session.execute(
            select(func.count())
            .select_from(EntityLinkRecord)
            .where(
                (EntityLinkRecord.from_entity_id == merge_id)
                | (EntityLinkRecord.to_entity_id == merge_id)
            )
        )
    ).scalar() or 0
    return (
        f"Связей будет перевешено: {links}. " + _CONSEQUENCES[KIND_ENTITY_MERGE]
    )


async def build_inbox(session: AsyncSession) -> dict[str, Any]:
    proposals = await list_proposals(session, status=STATUS_PENDING, limit=50)
    for proposal in proposals:
        proposal["confidence_hint"] = explain_confidence(
            proposal["confidence"], proposal.get("confidence_factors") or {}
        )
        if proposal["proposal_type"] == KIND_ENTITY_MERGE:
            proposal["consequences"] = await _merge_consequences(
                session, proposal.get("payload") or {}
            )
        else:
            proposal["consequences"] = _CONSEQUENCES.get(
                proposal["proposal_type"], "Изменение графа знаний."
            )

    findings = await list_findings(session, status=FINDING_OPEN, limit=50)
    disputed = await list_disputed_links(session)

    open_findings_total = (
        await session.execute(
            select(func.count())
            .select_from(SecondOpinionFinding)
            .where(SecondOpinionFinding.status == FINDING_OPEN)
        )
    ).scalar() or 0

    return {
        "proposals": proposals,
        "findings": findings,
        "disputed_links": disputed,
        "counts": {
            "proposals": len(proposals),
            "findings_open": int(open_findings_total),
            "disputed_links": len(disputed),
            "total": len(proposals) + int(open_findings_total) + len(disputed),
        },
    }


async def decide_inbox_proposal(
    session: AsyncSession,
    *,
    proposal_id: str,
    decision: str,
    reviewer_id: str,
    decision_reason: str | None = None,
) -> dict[str, Any] | None:
    """Decide and immediately apply (merges repoint links right away)."""

    if decision not in {STATUS_ACCEPTED, STATUS_REJECTED}:
        raise ValueError("decision must be accepted or rejected")
    decided = await decide_proposal(
        session,
        proposal_id=proposal_id,
        decision=decision,
        reviewer_id=reviewer_id,
        decision_reason=decision_reason,
    )
    if decided is None:
        return None
    applied = await apply_decided_merges(session)
    return {**decided, "applied": applied}
