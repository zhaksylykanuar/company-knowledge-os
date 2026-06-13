"""Command center read model (no finance).

Composes the trust layer into one startup-health document that a future
Command Center UI will render: overall health, second-opinion summary,
top conflicts, focus vs actual activity, risks, stale work, team load,
knowledge freshness, data-availability summary and next actions.

This is a read model, not a final UI. It draws only on real data and
exposes the data-availability state so the UI never paints a number it
cannot back.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.event_models import SourceEvent
from app.db.graph_models import EntityRecord
from app.services.data_availability import get_availability
from app.services.declarations import KEY_FOCUS, get_declaration
from app.services.entity_resolution import ENTITY_TYPE_PROJECT
from app.services.founder_overview import build_founder_overview
from app.services.jira_graph_mapping import jira_keys_for_project
from app.services.project_status_view import load_project_issue_snapshots
from app.services.second_opinion import (
    FINDING_VALIDATION_GAP,
    STATUS_OPEN,
    list_findings,
)

TEAM_OVERLOAD_OPEN_ISSUES = 8


async def _second_opinion_summary(session: AsyncSession) -> dict[str, Any]:
    findings = await list_findings(session, status=STATUS_OPEN, limit=200)
    by_severity = Counter(f["severity"] for f in findings)
    by_type = Counter(f["finding_type"] for f in findings)
    top = sorted(
        findings,
        key=lambda f: {"high": 0, "medium": 1, "low": 2}.get(f["severity"], 3),
    )[:5]
    return {
        "open_total": len(findings),
        "by_severity": dict(by_severity),
        "by_type": dict(by_type),
        "top_conflicts": [
            {
                "finding_key": f["finding_key"],
                "finding_type": f["finding_type"],
                "summary": f["summary"],
                "severity": f["severity"],
                "confidence": f["confidence"],
                "suggested_action": f["suggested_action"],
            }
            for f in top
        ],
        "validation_gaps": sum(
            1 for f in findings if f["finding_type"] == FINDING_VALIDATION_GAP
        ),
    }


_UNASSIGNED_NAMES = {"unassigned", "none", "unknown", ""}


async def _team_load(session: AsyncSession, *, now: datetime) -> dict[str, Any]:
    from datetime import timedelta

    from app.services.founder_overview import _is_overdue
    from app.services.project_status_view import STALE_DAYS

    projects = (
        await session.execute(
            select(EntityRecord).where(
                EntityRecord.entity_type == ENTITY_TYPE_PROJECT
            )
        )
    ).scalars()
    open_by_person: Counter[str] = Counter()
    stale_cutoff = now - timedelta(days=STALE_DAYS)
    # Unassigned work is an operational bucket, NOT a team member.
    unassigned = {"open": 0, "stale": 0, "high_priority": 0}
    for project in projects:
        jira_keys = await jira_keys_for_project(session, project.entity_id)
        for snap in await load_project_issue_snapshots(session, jira_keys):
            if snap.is_done:
                continue
            assignee = (snap.assignee or "").strip()
            if assignee.casefold() in _UNASSIGNED_NAMES:
                unassigned["open"] += 1
                if snap.updated_at is not None and snap.updated_at < stale_cutoff:
                    unassigned["stale"] += 1
                if _is_overdue(snap, now):
                    unassigned["high_priority"] += 1
            else:
                open_by_person[assignee] += 1
    people = [
        {"name": name, "open_issues": count, "overloaded": count >= TEAM_OVERLOAD_OPEN_ISSUES}
        for name, count in open_by_person.most_common(10)
    ]
    return {
        "people": people,
        "overloaded_count": sum(1 for p in people if p["overloaded"]),
        "tracked_people": len(open_by_person),
        "unassigned": {
            "unassigned_work_count": unassigned["open"],
            "stale_unassigned_work": unassigned["stale"],
            "high_priority_unassigned": unassigned["high_priority"],
            "suggested_action": (
                "Назначить ответственных за бесхозную работу"
                if unassigned["open"]
                else None
            ),
        },
    }


async def _knowledge_freshness(session: AsyncSession) -> dict[str, Any]:
    rows = (
        await session.execute(
            select(
                SourceEvent.source_system,
                func.max(SourceEvent.created_at),
                func.count(),
            ).group_by(SourceEvent.source_system)
        )
    ).all()
    return {
        str(system): {
            "last_event_at": last.isoformat() if last else None,
            "events": int(count),
        }
        for system, last, count in rows
    }


async def _focus_vs_activity(
    session: AsyncSession, overview: dict[str, Any]
) -> dict[str, Any]:
    declaration = await get_declaration(session, key=KEY_FOCUS)
    focus = (declaration or {}).get("payload") or {}
    title = str(focus.get("title") or "")
    # A focus_drift finding, if present, is the authoritative signal.
    drift = [
        f
        for f in overview.get("risks", [])
        if f.get("finding_type") == "focus_drift"
    ]
    return {
        "declared_focus": title or None,
        "focus_progress": focus.get("pct"),
        "has_drift_signal": bool(drift),
    }


async def _availability_summary(session: AsyncSession) -> dict[str, Any]:
    rows = await get_availability(session)
    by_status = Counter(r["status"] for r in rows)
    return {
        "by_status": dict(by_status),
        "total_series": len(rows),
        "ready": by_status.get("ready", 0),
        "collecting": by_status.get("collecting", 0),
        "stale": by_status.get("stale", 0),
        "no_data": by_status.get("no_data", 0),
    }


async def build_command_center(
    session: AsyncSession,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    safe_now = now or datetime.now(timezone.utc)
    overview = await build_founder_overview()

    metrics = overview.get("metrics", {})
    second_opinion = await _second_opinion_summary(session)
    team = await _team_load(session, now=safe_now)
    freshness = await _knowledge_freshness(session)
    focus = await _focus_vs_activity(session, overview)
    availability = await _availability_summary(session)

    next_actions = [
        {
            "title": action.get("title"),
            "impact": action.get("impact"),
            "urgent": action.get("urgent"),
            "source_title": action.get("source_title"),
        }
        for action in overview.get("actions", [])[:5]
    ]

    return {
        "generated_at": safe_now.isoformat(),
        "startup_health": {
            "level": overview["status"]["level"],
            "headline": overview["status"]["headline"],
            "projects": [
                {"name": p["name"], "color": p["color"]}
                for p in overview.get("projects", [])
            ],
        },
        "second_opinion": second_opinion,
        "focus": focus,
        "risks": {
            "open": second_opinion["by_type"].get("delivery_risk", 0)
            + len(overview.get("risks", [])),
            "top": overview.get("risks", [])[:3],
        },
        "stale_work": {
            "jira_stale": metrics.get("jira_stale", 0),
            "jira_overdue": metrics.get("jira_overdue", 0),
        },
        "team": team,
        "knowledge_freshness": freshness,
        "data_availability": availability,
        "next_actions": next_actions,
    }
