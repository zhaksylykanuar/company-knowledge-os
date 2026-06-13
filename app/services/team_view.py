"""Team operational load map (no performance ranking).

Shows operational risk per person — open / stale / blocked / overdue
issues and ownership context — never a productivity score and never a
"better/worse" comparison. Overload produces a suggested operational
action (redistribute / clarify priority / assign owner), not a judgment.
Unassigned work is a separate bucket, not a person.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.graph_models import EntityRecord
from app.db.second_opinion_models import SecondOpinionFinding
from app.services.entity_resolution import ENTITY_TYPE_PROJECT
from app.services.founder_overview import _is_overdue
from app.services.jira_graph_mapping import jira_keys_for_project
from app.services.project_status_view import STALE_DAYS, load_project_issue_snapshots
from app.services.second_opinion import _finding_read_model

_UNASSIGNED = {"unassigned", "none", "unknown", ""}
OVERLOAD_OPEN = 8


def _is_unassigned(assignee: str | None) -> bool:
    return (assignee or "").strip().casefold() in _UNASSIGNED


def _overload_action(load: dict[str, int]) -> str | None:
    if load["open"] >= OVERLOAD_OPEN:
        return "Перераспределить нагрузку или прояснить приоритеты"
    if load["overdue"]:
        return "Снять блокеры по просроченным задачам"
    return None


async def _ownership_gap_findings(session: AsyncSession) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(SecondOpinionFinding)
            .where(SecondOpinionFinding.status == "open")
            .where(SecondOpinionFinding.finding_type == "ownership_gap")
            .limit(20)
        )
    ).scalars()
    return [_finding_read_model(r) for r in rows]


async def build_team_view(
    session: AsyncSession,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    safe_now = now or datetime.now(timezone.utc)
    stale_cutoff = safe_now - timedelta(days=STALE_DAYS)

    projects = (
        await session.execute(
            select(EntityRecord).where(
                EntityRecord.entity_type == ENTITY_TYPE_PROJECT
            )
        )
    ).scalars()

    # Key by a normalized form so "Alice"/"alice " are one person; keep
    # the first-seen display name for the row.
    load: dict[str, dict[str, Any]] = {}
    unassigned = {"open": 0, "stale": 0, "overdue": 0}

    for project in projects:
        jira_keys = await jira_keys_for_project(session, project.entity_id)
        for snap in await load_project_issue_snapshots(session, jira_keys):
            if snap.is_done:
                continue
            stale = snap.updated_at is not None and snap.updated_at < stale_cutoff
            overdue = _is_overdue(snap, safe_now)
            if _is_unassigned(snap.assignee):
                target = unassigned
            else:
                key = snap.assignee.strip().casefold()
                target = load.setdefault(
                    key,
                    {
                        "name": snap.assignee.strip(),
                        "open": 0,
                        "stale": 0,
                        "overdue": 0,
                    },
                )
            target["open"] += 1
            if stale:
                target["stale"] += 1
            if overdue:
                target["overdue"] += 1

    people = []
    for stats in sorted(load.values(), key=lambda s: s["open"], reverse=True):
        people.append(
            {
                "name": stats["name"],
                "open": stats["open"],
                "stale": stats["stale"],
                "overdue": stats["overdue"],
                "overloaded": stats["open"] >= OVERLOAD_OPEN,
                "suggested_action": _overload_action(stats),
            }
        )

    gaps = await _ownership_gap_findings(session)

    return {
        "generated_at": safe_now.isoformat(),
        "people": people,
        "unassigned": {
            "unassigned_work_count": unassigned["open"],
            "stale_unassigned_work": unassigned["stale"],
            "overdue_unassigned": unassigned["overdue"],
            "suggested_action": (
                "Назначить ответственных за бесхозную работу"
                if unassigned["open"]
                else None
            ),
        },
        "ownership_gaps": gaps,
        "counts": {
            "tracked_people": len(people),
            "overloaded": sum(1 for p in people if p["overloaded"]),
            "ownership_gaps": len(gaps),
        },
    }
