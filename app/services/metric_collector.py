"""Metric collector agent: one daily point per series, all from real data.

Captured series (scope = project entity id or "global"):

- ``jira.open`` / ``jira.stale`` / ``jira.overdue`` / ``jira.done`` per project
- ``code.merged_prs`` / ``code.commits_7d`` per project with mapped repos
- ``knowledge.tasks`` / ``knowledge.risks`` / ``knowledge.decisions`` global
- ``activity.events`` global (normalized activity that day)

Re-running on the same day updates the day's value instead of duplicating.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.agent_models import MetricSnapshot
from app.db.event_models import NormalizedActivityItemRecord
from app.db.graph_models import EntityRecord
from app.db.task_models import ExtractedDecision, ExtractedRisk, ExtractedTask
from app.services.entity_resolution import ENTITY_TYPE_PROJECT
from app.services.founder_overview import _is_overdue
from app.services.github_graph_mapping import repos_for_project
from app.services.jira_graph_mapping import jira_keys_for_project
from app.services.project_status_view import (
    STALE_DAYS,
    load_project_issue_snapshots,
    load_repo_activity,
)

GLOBAL_SCOPE = "global"


async def _record(
    session: AsyncSession,
    *,
    metric_key: str,
    scope: str,
    captured_on: str,
    value: float,
    details: dict | None = None,
) -> str:
    existing = await session.scalar(
        select(MetricSnapshot)
        .where(MetricSnapshot.metric_key == metric_key)
        .where(MetricSnapshot.scope == scope)
        .where(MetricSnapshot.captured_on == captured_on)
    )
    if existing is not None:
        if existing.value != value:
            existing.value = value
            existing.details = dict(details or {})
            await session.flush()
            return "updated"
        return "unchanged"
    session.add(
        MetricSnapshot(
            metric_key=metric_key,
            scope=scope,
            captured_on=captured_on,
            value=float(value),
            details=dict(details or {}),
        )
    )
    await session.flush()
    return "created"


async def collect_metrics(
    session: AsyncSession,
    *,
    now: datetime | None = None,
) -> dict[str, int]:
    safe_now = now or datetime.now(timezone.utc)
    day = safe_now.date().isoformat()
    counts = {"created": 0, "updated": 0, "unchanged": 0}

    async def record(metric_key: str, scope: str, value: float, **details) -> None:
        outcome = await _record(
            session,
            metric_key=metric_key,
            scope=scope,
            captured_on=day,
            value=value,
            details=details or None,
        )
        counts[outcome] += 1

    projects = (
        await session.execute(
            select(EntityRecord).where(
                EntityRecord.entity_type == ENTITY_TYPE_PROJECT
            )
        )
    ).scalars()
    stale_cutoff = safe_now - timedelta(days=STALE_DAYS)
    for project in projects:
        jira_keys = await jira_keys_for_project(session, project.entity_id)
        snapshots = await load_project_issue_snapshots(session, jira_keys)
        open_items = [item for item in snapshots if not item.is_done]
        await record("jira.open", project.entity_id, len(open_items))
        await record(
            "jira.done", project.entity_id, len(snapshots) - len(open_items)
        )
        await record(
            "jira.stale",
            project.entity_id,
            sum(
                1
                for item in open_items
                if item.updated_at is not None and item.updated_at < stale_cutoff
            ),
        )
        await record(
            "jira.overdue",
            project.entity_id,
            sum(1 for item in open_items if _is_overdue(item, safe_now)),
        )

        repos = await repos_for_project(session, project.entity_id)
        activity = await load_repo_activity(session, repos, now=safe_now)
        if activity is not None:
            await record(
                "code.merged_prs", project.entity_id, len(activity.merged_prs)
            )
            await record(
                "code.commits_7d", project.entity_id, activity.commit_count_7d
            )

    for metric_key, model in (
        ("knowledge.tasks", ExtractedTask),
        ("knowledge.risks", ExtractedRisk),
        ("knowledge.decisions", ExtractedDecision),
    ):
        total = (
            await session.execute(select(func.count()).select_from(model))
        ).scalar() or 0
        await record(metric_key, GLOBAL_SCOPE, int(total))

    occurred = func.coalesce(
        NormalizedActivityItemRecord.activity_created_at,
        NormalizedActivityItemRecord.created_at,
    )
    day_start = datetime(
        safe_now.year, safe_now.month, safe_now.day, tzinfo=timezone.utc
    )
    events_today = (
        await session.execute(
            select(func.count())
            .select_from(NormalizedActivityItemRecord)
            .where(occurred >= day_start)
        )
    ).scalar() or 0
    await record("activity.events", GLOBAL_SCOPE, int(events_today))

    return counts


async def metric_series(
    session: AsyncSession,
    *,
    metric_key: str,
    scope: str = GLOBAL_SCOPE,
    days: int = 30,
) -> list[dict]:
    rows = (
        await session.execute(
            select(MetricSnapshot)
            .where(MetricSnapshot.metric_key == metric_key)
            .where(MetricSnapshot.scope == scope)
            .order_by(MetricSnapshot.captured_on.desc())
            .limit(days)
        )
    ).scalars()
    points = [
        {"date": row.captured_on, "value": row.value} for row in rows
    ]
    return list(reversed(points))
