"""Composed founder overview read model for the local UI.

Aggregates existing read models into one JSON document per request: project
status, attention items split into actions and risks, recent extracted
decisions, normalized activity counts, and operational metrics. UI/founder GET
views are read-only by default; status snapshot persistence is an explicit
operator/bot behavior, not an implicit side effect of reading the overview.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select

from app.db.base import AsyncSessionLocal
from app.db.event_models import NormalizedActivityItemRecord
from app.db.graph_models import EntityRecord
from app.db.source_models import SourceDocument
from app.db.task_models import ExtractedDecision, ExtractedRisk, ExtractedTask
from app.services.github_graph_mapping import repos_for_project
from app.services.jira_graph_mapping import jira_keys_for_project
from app.services.knowledge_attention import get_attention_dashboard
from app.services.project_status_view import (
    FRESH_DAYS,
    STALE_DAYS,
    JiraIssueSnapshot,
    RepoActivity,
    load_project_issue_snapshots,
    load_repo_activity,
)
from app.services.status_engine import (
    DEFAULT_ORGANIZATION_ID,
    build_project_status_snapshot,
)
from app.services.entity_resolution import ENTITY_TYPE_PROJECT
from app.services.status_snapshot_repository import (
    get_latest_status_snapshot,
    save_status_snapshot,
)

DEFAULT_ATTENTION_LIMIT = 20
DECISIONS_LIMIT = 8
ACTIVITY_DAYS = 14

HIGH_IMPACT_THRESHOLD = 0.7
HIGH_URGENCY_THRESHOLD = 0.5


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat()


def _is_overdue(snapshot: JiraIssueSnapshot, now: datetime) -> bool:
    if snapshot.is_done or not snapshot.duedate:
        return False
    try:
        due = datetime.fromisoformat(str(snapshot.duedate))
    except ValueError:
        return False
    if due.tzinfo is None:
        due = due.replace(tzinfo=timezone.utc)
    return due < now


def _jira_stats(snapshots: list[JiraIssueSnapshot], now: datetime) -> dict[str, Any]:
    open_items = [item for item in snapshots if not item.is_done]
    stale_cutoff = now - timedelta(days=STALE_DAYS)
    stale = [
        item
        for item in open_items
        if item.updated_at is not None and item.updated_at < stale_cutoff
    ]
    overdue = [item for item in open_items if _is_overdue(item, now)]
    by_status: dict[str, int] = {}
    for item in open_items:
        by_status[item.status] = by_status.get(item.status, 0) + 1
    top_statuses = sorted(by_status.items(), key=lambda pair: -pair[1])[:3]
    return {
        "total": len(snapshots),
        "open": len(open_items),
        "done": len(snapshots) - len(open_items),
        "stale": len(stale),
        "overdue": len(overdue),
        "top_statuses": [
            {"status": status, "count": count} for status, count in top_statuses
        ],
    }


def _repo_activity_provenance(
    repo_activity: RepoActivity,
    *,
    now: datetime,
) -> dict[str, Any]:
    return {
        "computed": True,
        "source": "github_source_events",
        "source_system": "github",
        "metric_family": "code",
        "window_days": repo_activity.window_days or FRESH_DAYS,
        "window_start": _iso(repo_activity.window_start),
        "window_end": _iso(repo_activity.window_end or now),
        "source_event_count": repo_activity.source_event_count,
        "last_source_event_at": _iso(repo_activity.last_source_event_at),
        "source_run_ids": list(repo_activity.source_run_ids[:5]),
        "computed_at": _iso(now),
        "scope": "mapped_repositories_only",
    }


async def _project_blocks(
    session: Any,
    *,
    now: datetime,
    organization_id: str,
    persist_status_snapshots: bool,
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(EntityRecord)
            .where(EntityRecord.entity_type == ENTITY_TYPE_PROJECT)
            .order_by(EntityRecord.canonical_name)
        )
    ).scalars()

    projects: list[dict[str, Any]] = []
    for entity in rows:
        jira_keys = await jira_keys_for_project(session, entity.entity_id)
        snapshots = await load_project_issue_snapshots(session, jira_keys)
        repos = await repos_for_project(session, entity.entity_id)
        repo_activity = await load_repo_activity(session, repos, now=now)
        previous = await get_latest_status_snapshot(
            session,
            organization_id=organization_id,
            entity_type=ENTITY_TYPE_PROJECT,
            entity_id=entity.entity_id,
        )
        snapshot = build_project_status_snapshot(
            project_entity_id=entity.entity_id,
            project_name=entity.canonical_name,
            jira_keys=jira_keys,
            snapshots=snapshots,
            repo_activity=repo_activity,
            previous_snapshot=previous,
            organization_id=organization_id,
            now=now,
        )
        if persist_status_snapshots:
            await save_status_snapshot(session, snapshot)

        code: dict[str, Any] | None = None
        if repo_activity is not None:
            code = {
                "repos": list(repo_activity.repo_names),
                "commits_7d": repo_activity.commit_count_7d,
                "open_prs": len(repo_activity.open_prs),
                "merged_prs": len(repo_activity.merged_prs),
                "provenance": _repo_activity_provenance(repo_activity, now=now),
            }

        top_signal: str | None = None
        for collection in (snapshot.blockers, snapshot.conflicts, snapshot.risks):
            if collection:
                first = collection[0]
                top_signal = str(
                    first.get("summary")
                    or first.get("message")
                    or first.get("issue_key")
                    or ""
                ) or None
                break

        projects.append(
            {
                "entity_id": entity.entity_id,
                "name": entity.canonical_name,
                "color": snapshot.status_color,
                "confidence": snapshot.confidence,
                "summary": snapshot.summary,
                "jira_keys": jira_keys,
                "jira": _jira_stats(snapshots, now),
                "code": code,
                "blockers": [dict(item) for item in snapshot.blockers[:3]],
                "risks_count": len(snapshot.risks),
                "conflicts_count": len(snapshot.conflicts),
                "recommendations": [
                    dict(item) for item in snapshot.recommendations[:3]
                ],
                "top_signal": top_signal,
                "last_update_at": _iso(snapshot.last_meaningful_update_at),
            }
        )
    return projects


def _split_attention_items(
    items: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    actions: list[dict[str, Any]] = []
    risks: list[dict[str, Any]] = []
    for item in items:
        importance = float(item.get("importance_score") or 0.0)
        urgency = float(item.get("urgency_score") or 0.0)
        impact = (
            "high"
            if importance >= HIGH_IMPACT_THRESHOLD
            else "medium"
            if importance >= 0.4
            else "low"
        )
        compact = {
            "title": item.get("title"),
            "item_type": item.get("item_type"),
            "attention_score": item.get("attention_score"),
            "impact": impact,
            "urgent": urgency >= HIGH_URGENCY_THRESHOLD,
            "source_title": item.get("source_title"),
            "source_document_id": item.get("source_document_id"),
            "reasons": [
                str(reason.get("message"))
                for reason in item.get("reasons", [])
                if isinstance(reason, dict) and reason.get("message")
            ][:2],
        }
        if item.get("item_type") == "risk":
            risks.append(compact)
        else:
            actions.append(compact)
    return actions, risks


async def _recent_decisions(session: Any) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(ExtractedDecision)
            .order_by(ExtractedDecision.created_at.desc())
            .limit(DECISIONS_LIMIT)
        )
    ).scalars()
    return [
        {
            "title": row.title,
            "decision": row.decision,
            "owner": row.owner,
            "created_at": _iso(row.created_at),
            "source_document_id": row.source_document_id,
        }
        for row in rows
    ]


async def _activity_block(session: Any, *, now: datetime) -> dict[str, Any]:
    window_start = now - timedelta(days=ACTIVITY_DAYS)
    occurred = func.coalesce(
        NormalizedActivityItemRecord.activity_created_at,
        NormalizedActivityItemRecord.created_at,
    )
    by_source_rows = (
        await session.execute(
            select(NormalizedActivityItemRecord.source, func.count())
            .where(occurred >= window_start)
            .group_by(NormalizedActivityItemRecord.source)
        )
    ).all()
    by_day_rows = (
        await session.execute(
            select(func.date(occurred), func.count())
            .where(occurred >= window_start)
            .group_by(func.date(occurred))
            .order_by(func.date(occurred))
        )
    ).all()
    return {
        "window_days": ACTIVITY_DAYS,
        "by_source": {str(source): int(count) for source, count in by_source_rows},
        "by_day": [
            {"date": str(day), "count": int(count)} for day, count in by_day_rows
        ],
    }


async def _counts_block(session: Any) -> dict[str, int]:
    async def _count(model: Any) -> int:
        return int(
            (await session.execute(select(func.count()).select_from(model))).scalar()
            or 0
        )

    return {
        "documents": await _count(SourceDocument),
        "tasks": await _count(ExtractedTask),
        "risks": await _count(ExtractedRisk),
        "decisions": await _count(ExtractedDecision),
    }


def _overall_status(
    projects: list[dict[str, Any]],
    risks: list[dict[str, Any]],
) -> dict[str, str]:
    colors = {project["color"] for project in projects}
    blockers = sum(len(project["blockers"]) for project in projects)
    if "red" in colors:
        return {
            "level": "red",
            "headline": "Есть красный проект — нужно вмешательство",
        }
    if blockers:
        return {
            "level": "red",
            "headline": f"Блокеров: {blockers} — разобрать сегодня",
        }
    if "yellow" in colors or risks:
        return {
            "level": "yellow",
            "headline": "Есть риски — стоит посмотреть сегодня",
        }
    if projects:
        return {"level": "green", "headline": "Спокойно: можно строить, не тушить"}
    return {"level": "unknown", "headline": "Пока нет данных по проектам"}


async def build_founder_overview(
    *,
    now: datetime | None = None,
    attention_limit: int = DEFAULT_ATTENTION_LIMIT,
    organization_id: str = DEFAULT_ORGANIZATION_ID,
    persist_status_snapshots: bool = False,
) -> dict[str, Any]:
    safe_now = now or datetime.now(timezone.utc)

    async with AsyncSessionLocal() as session:
        projects = await _project_blocks(
            session,
            now=safe_now,
            organization_id=organization_id,
            persist_status_snapshots=persist_status_snapshots,
        )
        decisions = await _recent_decisions(session)
        activity = await _activity_block(session, now=safe_now)
        counts = await _counts_block(session)
        if persist_status_snapshots:
            await session.commit()

    dashboard = await get_attention_dashboard(limit=attention_limit)
    actions, risks = _split_attention_items(dashboard.get("top_items", []))

    jira_open = sum(project["jira"]["open"] for project in projects)
    jira_stale = sum(project["jira"]["stale"] for project in projects)
    jira_overdue = sum(project["jira"]["overdue"] for project in projects)
    prs_merged = sum(
        (project["code"] or {}).get("merged_prs", 0) for project in projects
    )
    commits_7d = sum(
        (project["code"] or {}).get("commits_7d", 0) for project in projects
    )

    return {
        "schema_version": "founder_overview.v2",
        "generated_at": _iso(safe_now),
        "provenance": {
            "source": "server_read_model",
            "computed": True,
            "cache_policy": {
                "browser_cache_key": "fos_overview_cache",
                "cache_is_client_side_only": True,
                "stale_on_read": True,
            },
        },
        "status": _overall_status(projects, risks),
        "projects": projects,
        "actions": actions,
        "risks": risks,
        "decisions": decisions,
        "activity": activity,
        "metrics": {
            "jira_open": jira_open,
            "jira_stale": jira_stale,
            "jira_overdue": jira_overdue,
            "prs_merged": prs_merged,
            "commits_7d": commits_7d,
            "attention_items": len(actions) + len(risks),
            **counts,
        },
    }
