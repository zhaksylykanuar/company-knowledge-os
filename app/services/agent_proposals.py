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
) -> bool:
    """File a proposal once; re-runs with the same id are no-ops."""

    existing = await session.scalar(
        select(AgentProposal).where(AgentProposal.proposal_id == proposal_id)
    )
    if existing is not None:
        return False
    session.add(
        AgentProposal(
            proposal_id=proposal_id,
            agent=agent,
            kind=kind,
            title=title,
            payload=dict(payload),
            evidence_refs=list(evidence_refs or []),
            confidence=confidence,
            status=STATUS_PENDING,
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
    return [
        {
            "proposal_id": row.proposal_id,
            "agent": row.agent,
            "kind": row.kind,
            "title": row.title,
            "payload": row.payload,
            "evidence_refs": row.evidence_refs,
            "confidence": row.confidence,
            "status": row.status,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]


async def decide_proposal(
    session: AsyncSession,
    *,
    proposal_id: str,
    decision: str,
    decided_by: str,
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
    row.decided_by = decided_by
    row.decided_at = datetime.now(timezone.utc)
    await session.flush()
    return {"proposal_id": row.proposal_id, "status": row.status}


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
    await session.flush()
