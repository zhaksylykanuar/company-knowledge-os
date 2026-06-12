"""Agent proposal queue: low-confidence graph changes await a human.

Agents never silently write uncertain facts. They file a proposal here;
the founder accepts or rejects it in the UI inbox. Accepting only flips
the status — the proposing agent applies accepted proposals on its next
run, keeping apply-logic next to the agent that owns it.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.agent_models import AgentProposal

STATUS_PENDING = "pending"
STATUS_ACCEPTED = "accepted"
STATUS_REJECTED = "rejected"
STATUS_APPLIED = "applied"

DECIDABLE_STATUSES = {STATUS_ACCEPTED, STATUS_REJECTED}


async def create_proposal(
    session: AsyncSession,
    *,
    proposal_id: str,
    agent: str,
    kind: str,
    title: str,
    payload: dict[str, Any],
    evidence_refs: list[dict[str, Any]] | None = None,
    confidence: float,
    confidence_factors: dict[str, Any] | None = None,
    dedupe_key: str | None = None,
    source_snapshot: dict[str, Any] | None = None,
    expires_at: datetime | None = None,
    reversible: bool = True,
) -> bool:
    """File a proposal once; re-runs with the same id/dedupe_key are no-ops."""

    existing = await session.scalar(
        select(AgentProposal).where(AgentProposal.proposal_id == proposal_id)
    )
    if existing is None and dedupe_key:
        existing = await session.scalar(
            select(AgentProposal).where(AgentProposal.dedupe_key == dedupe_key)
        )
    if existing is not None:
        return False
    session.add(
        AgentProposal(
            proposal_id=proposal_id,
            dedupe_key=dedupe_key or proposal_id,
            agent=agent,
            kind=kind,
            title=title,
            payload=dict(payload),
            source_snapshot=dict(source_snapshot) if source_snapshot else None,
            evidence_refs=list(evidence_refs or []),
            confidence=confidence,
            confidence_factors=dict(confidence_factors)
            if confidence_factors
            else None,
            status=STATUS_PENDING,
            expires_at=expires_at,
            reversible=reversible,
        )
    )
    await session.flush()
    return True


async def list_proposals(
    session: AsyncSession,
    *,
    status: str = STATUS_PENDING,
    limit: int = 50,
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(AgentProposal)
            .where(AgentProposal.status == status)
            .order_by(AgentProposal.created_at.desc())
            .limit(limit)
        )
    ).scalars()
    return [_proposal_read_model(row) for row in rows]


def _proposal_read_model(row: AgentProposal) -> dict[str, Any]:
    """Product-facing shape: proposal_type / reviewer_id, not the legacy
    column names (kind / decided_by stay internal for compatibility)."""

    return {
        "proposal_id": row.proposal_id,
        "dedupe_key": row.dedupe_key,
        "agent": row.agent,
        "proposal_type": row.kind,
        "title": row.title,
        "payload": row.payload,
        "source_snapshot": row.source_snapshot,
        "evidence_refs": row.evidence_refs,
        "confidence": row.confidence,
        "confidence_factors": row.confidence_factors,
        "status": row.status,
        "reviewer_id": row.decided_by,
        "decision_reason": row.decision_reason,
        "reversible": row.reversible,
        "applied_at": row.applied_at.isoformat() if row.applied_at else None,
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


async def decide_proposal(
    session: AsyncSession,
    *,
    proposal_id: str,
    decision: str,
    reviewer_id: str,
    decision_reason: str | None = None,
) -> dict[str, Any] | None:
    """Accept or reject a pending proposal. Returns None when not found."""

    if decision not in DECIDABLE_STATUSES:
        raise ValueError(f"decision must be one of {sorted(DECIDABLE_STATUSES)}")

    row = await session.scalar(
        select(AgentProposal).where(AgentProposal.proposal_id == proposal_id)
    )
    if row is None:
        return None
    if row.status != STATUS_PENDING:
        raise ValueError(f"proposal already {row.status}")

    row.status = decision
    row.decided_by = reviewer_id
    row.decision_reason = decision_reason
    row.decided_at = datetime.now(timezone.utc)
    await session.flush()
    return {
        "proposal_id": row.proposal_id,
        "status": row.status,
        "reviewer_id": row.decided_by,
    }


async def accepted_proposals(
    session: AsyncSession,
    *,
    agent: str,
    kind: str | None = None,
) -> list[AgentProposal]:
    """Accepted-but-unapplied proposals for the owning agent to apply."""

    query = (
        select(AgentProposal)
        .where(AgentProposal.agent == agent)
        .where(AgentProposal.status == STATUS_ACCEPTED)
    )
    if kind is not None:
        query = query.where(AgentProposal.kind == kind)
    return list((await session.execute(query)).scalars())


async def mark_applied(session: AsyncSession, proposal: AgentProposal) -> None:
    proposal.status = STATUS_APPLIED
    proposal.applied_at = datetime.now(timezone.utc)
    await session.flush()
