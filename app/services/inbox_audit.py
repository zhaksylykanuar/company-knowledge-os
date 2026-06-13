"""Audit trail for human decisions in the inbox.

Every accept/reject/confirm/remove/resolve/snooze/note writes an
``audit_logs`` row with previous_state / next_state and reversibility,
so the trust layer can always answer: who decided, when, what changed.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog

INBOX_AUDIT_PREFIX = "inbox."

ACTION_PROPOSAL_DECISION = "proposal_decision"
ACTION_LINK_REVIEW = "link_review"
ACTION_FINDING_STATUS = "finding_status"
ACTION_FINDING_SNOOZE = "finding_snooze"
ACTION_FINDING_NOTE = "finding_note"


async def record_inbox_action(
    session: AsyncSession,
    *,
    action: str,
    actor: str,
    target_id: str,
    previous_state: dict[str, Any] | None,
    next_state: dict[str, Any] | None,
    reversible: bool,
    details: dict[str, Any] | None = None,
    run_id: str | None = None,
) -> None:
    # agent_run_id links the human decision back to the agent run that
    # produced the finding/proposal being decided on.
    session.add(
        AuditLog(
            event_type=f"{INBOX_AUDIT_PREFIX}{action}",
            actor=actor,
            correlation_id=target_id[:120],
            trace_id=f"inbox-{uuid4().hex[:16]}",
            agent_run_id=run_id,
            before_ref=str((previous_state or {}).get("status") or "")[:500] or None,
            after_ref=str((next_state or {}).get("status") or "")[:500] or None,
            payload={
                "target_id": target_id,
                "previous_state": previous_state or {},
                "next_state": next_state or {},
                "reversible": reversible,
                "details": details or {},
            },
        )
    )
    await session.flush()


async def list_inbox_actions(
    session: AsyncSession,
    *,
    target_id: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(AuditLog)
            .where(AuditLog.event_type.like(f"{INBOX_AUDIT_PREFIX}%"))
            .where(AuditLog.correlation_id == target_id[:120])
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        )
    ).scalars()
    return [
        {
            "action": row.event_type.removeprefix(INBOX_AUDIT_PREFIX),
            "actor": row.actor,
            "previous_state": (row.payload or {}).get("previous_state"),
            "next_state": (row.payload or {}).get("next_state"),
            "reversible": (row.payload or {}).get("reversible"),
            "details": (row.payload or {}).get("details"),
            "run_id": row.agent_run_id,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]
