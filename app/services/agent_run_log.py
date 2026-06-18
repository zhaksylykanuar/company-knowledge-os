"""Agent run logging: one row per agent per pipeline run.

Records the standardized run buckets (created, updated_from_new_evidence,
updated_from_clock_recalculation, unchanged, auto_resolved, skipped,
errors) plus agent-specific detail, run timestamps, agent_version and the
input watermark — so we always know whether an update came from new
evidence or a clock-based recalculation.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.agent_models import AgentRunLog

_STANDARD_KEYS = (
    "created",
    "updated_from_new_evidence",
    "updated_from_clock_recalculation",
    "unchanged",
    "auto_resolved",
    "skipped",
    "errors",
)


async def record_agent_run(
    session: AsyncSession,
    *,
    run_id: str,
    agent: str,
    agent_version: str,
    run_started_at: datetime,
    run_finished_at: datetime,
    counts: dict[str, Any],
    input_watermark: str | None = None,
) -> None:
    standard = {key: int(counts.get(key, 0) or 0) for key in _STANDARD_KEYS}
    details = {
        key: value for key, value in counts.items() if key not in _STANDARD_KEYS
    }
    session.add(
        AgentRunLog(
            run_id=run_id,
            agent=agent,
            agent_version=agent_version,
            run_started_at=run_started_at,
            run_finished_at=run_finished_at,
            input_watermark=input_watermark,
            details=details,
            **standard,
        )
    )
    await session.flush()


async def latest_runs(
    session: AsyncSession, *, limit: int = 20
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(AgentRunLog)
            .order_by(AgentRunLog.created_at.desc())
            .limit(limit)
        )
    ).scalars()
    return [
        {
            "run_id": row.run_id,
            "agent": row.agent,
            "agent_version": row.agent_version,
            "run_started_at": row.run_started_at.isoformat()
            if row.run_started_at
            else None,
            "run_finished_at": row.run_finished_at.isoformat()
            if row.run_finished_at
            else None,
            "input_watermark": row.input_watermark,
            "created": row.created,
            "updated_from_new_evidence": row.updated_from_new_evidence,
            "updated_from_clock_recalculation": (
                row.updated_from_clock_recalculation
            ),
            "unchanged": row.unchanged,
            "auto_resolved": row.auto_resolved,
            "skipped": row.skipped,
            "errors": row.errors,
            "details": row.details,
        }
        for row in rows
    ]
