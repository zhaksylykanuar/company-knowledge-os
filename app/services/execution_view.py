"""Execution OS read model: tasks as an honest quest log.

Quests are real Jira issues (not invented). Buckets:

- main_quest: the declared weekly focus (a declaration, not a guess);
- side_quests: important open issues with an owner and movement;
- blocked_quests: issues flagged blocked by the status engine;
- stale_quests: open with no movement past the stale window;
- ownerless_quests: open without an assignee;
- overdue_quests: past their due date;
- project_health: done/total rings per project (only when total > 0).

Each quest carries impact/urgency derived from real signals (never a
fake productivity score) and the findings attached to its issue key.
A task detail view assembles source refs, related nodes, related
findings, evidence timeline, owner, status history and next action.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.event_models import SourceEvent
from app.db.graph_models import EntityRecord
from app.db.second_opinion_models import SecondOpinionFinding
from app.services.entity_resolution import ENTITY_TYPE_PROJECT, resolve_entities_in_text
from app.services.founder_overview import _is_overdue
from app.services.jira_graph_mapping import jira_keys_for_project
from app.services.project_status_view import (
    STALE_DAYS,
    JiraIssueSnapshot,
    load_project_issue_snapshots,
)
from app.services.second_opinion import _finding_read_model

_UNASSIGNED = {"unassigned", "none", "unknown", ""}


def _is_unassigned(assignee: str | None) -> bool:
    return (assignee or "").strip().casefold() in _UNASSIGNED


def _impact_urgency(
    snap: JiraIssueSnapshot, *, overdue: bool, stale: bool, blocked: bool, now: datetime
) -> tuple[str, str]:
    impact = "high" if blocked else "medium"
    if overdue:
        urgency = "high"
    elif stale:
        urgency = "medium"
    else:
        urgency = "low"
    return impact, urgency


async def _findings_by_issue(session: AsyncSession) -> dict[str, list[dict[str, Any]]]:
    rows = (
        await session.execute(
            select(SecondOpinionFinding).where(
                SecondOpinionFinding.status == "open"
            )
        )
    ).scalars()
    by_issue: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        model = _finding_read_model(row)
        # Attach the finding to every distinct issue key in its evidence,
        # not just the first — a finding may span multiple issues.
        keys: set[str] = set()
        for ref in row.evidence_refs or []:
            if isinstance(ref, dict):
                sid = ref.get("source_id") or ref.get("issue_key")
                if isinstance(sid, str) and sid:
                    keys.add(sid)
        for key in keys:
            by_issue.setdefault(key, []).append(model)
    return by_issue


def _quest(snap: JiraIssueSnapshot, *, project: str, impact: str, urgency: str,
           flags: list[str], findings: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "issue_key": snap.issue_key,
        "title": snap.title,
        "status": snap.status,
        "owner": None if _is_unassigned(snap.assignee) else snap.assignee,
        "due_date": snap.duedate,
        "project": project,
        "impact": impact,
        "urgency": urgency,
        "flags": flags,
        "findings": findings,
        "evidence_count": len(findings),
    }


async def build_execution_view(
    session: AsyncSession,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    from app.services.declarations import KEY_FOCUS, get_declaration

    safe_now = now or datetime.now(timezone.utc)
    stale_cutoff = safe_now - timedelta(days=STALE_DAYS)
    findings_by_issue = await _findings_by_issue(session)

    focus_decl = await get_declaration(session, key=KEY_FOCUS)
    focus_title = ((focus_decl or {}).get("payload") or {}).get("title") or None
    focus_project_id: str | None = None
    if focus_title:
        try:
            recognized = await resolve_entities_in_text(
                session, focus_title, entity_type=ENTITY_TYPE_PROJECT
            )
            if recognized:
                focus_project_id = recognized[0].entity_id
        except Exception:
            focus_project_id = None

    projects = (
        await session.execute(
            select(EntityRecord)
            .where(EntityRecord.entity_type == ENTITY_TYPE_PROJECT)
            .order_by(EntityRecord.canonical_name)
        )
    ).scalars()

    side: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    stale: list[dict[str, Any]] = []
    ownerless: list[dict[str, Any]] = []
    overdue: list[dict[str, Any]] = []
    project_health: list[dict[str, Any]] = []
    main_quest_project: dict[str, Any] | None = None

    for project in projects:
        jira_keys = await jira_keys_for_project(session, project.entity_id)
        snaps = await load_project_issue_snapshots(session, jira_keys)
        open_snaps = [s for s in snaps if not s.is_done]
        total = len(snaps)
        done = total - len(open_snaps)
        if total > 0:
            health = {
                "project": project.canonical_name,
                "entity_id": project.entity_id,
                "done": done,
                "total": total,
                "open": len(open_snaps),
                "is_focus": project.entity_id == focus_project_id,
            }
            project_health.append(health)
            if project.entity_id == focus_project_id:
                main_quest_project = health

        for snap in open_snaps:
            is_overdue = _is_overdue(snap, safe_now)
            is_stale = snap.updated_at is not None and snap.updated_at < stale_cutoff
            issue_findings = findings_by_issue.get(snap.issue_key, [])
            is_blocked = any(
                f["finding_type"] in {"delivery_risk", "execution_mismatch"}
                for f in issue_findings
            )
            flags: list[str] = []
            if is_overdue:
                flags.append("overdue")
            if is_stale:
                flags.append("stale")
            if is_blocked:
                flags.append("blocked")
            if _is_unassigned(snap.assignee):
                flags.append("ownerless")
            impact, urgency = _impact_urgency(
                snap, overdue=is_overdue, stale=is_stale, blocked=is_blocked, now=safe_now
            )
            quest = _quest(
                snap,
                project=project.canonical_name,
                impact=impact,
                urgency=urgency,
                flags=flags,
                findings=issue_findings,
            )
            if is_overdue:
                overdue.append(quest)
            if is_blocked:
                blocked.append(quest)
            if is_stale:
                stale.append(quest)
            if _is_unassigned(snap.assignee):
                ownerless.append(quest)
            if (
                not (is_overdue or is_stale or is_blocked)
                and not _is_unassigned(snap.assignee)
                and issue_findings
            ):
                # Side quests: important, owned, moving — never ownerless.
                side.append(quest)

    def _trim(items: list[dict[str, Any]], n: int = 12) -> list[dict[str, Any]]:
        return items[:n]

    return {
        "generated_at": safe_now.isoformat(),
        "main_quest": {
            "focus": focus_title,
            "project": main_quest_project,
        },
        "side_quests": _trim(side),
        "blocked_quests": _trim(blocked),
        "stale_quests": _trim(stale),
        "ownerless_quests": _trim(ownerless),
        "overdue_quests": _trim(overdue),
        "project_health": project_health,
        "counts": {
            "side": len(side),
            "blocked": len(blocked),
            "stale": len(stale),
            "ownerless": len(ownerless),
            "overdue": len(overdue),
        },
    }


async def build_task_detail(
    session: AsyncSession,
    *,
    issue_key: str,
) -> dict[str, Any] | None:
    """Detail drawer: source refs, related nodes, related findings,
    evidence timeline, owner, status history, next action."""

    # Exact match: a substring LIKE over-matches QS-1 against QS-10/QS-100.
    events = list(
        (
            await session.execute(
                select(SourceEvent)
                .where(SourceEvent.source_object_id == issue_key)
                .order_by(SourceEvent.id)
            )
        ).scalars()
    )

    status_history = [
        {
            "source_event_id": e.source_event_id,
            "title": e.title,
            "received_at": e.created_at.isoformat() if e.created_at else None,
            "source_system": e.source_system,
            "created_by_run_id": e.created_by_run_id,
        }
        for e in events
    ]

    findings = await _findings_by_issue(session)
    related_findings = findings.get(issue_key, [])

    # Related graph nodes: the jira project prefix node.
    related_nodes: list[dict[str, Any]] = []
    prefix = issue_key.split("-")[0] if "-" in issue_key else issue_key
    node_rows = (
        await session.execute(
            select(EntityRecord).where(EntityRecord.entity_id == f"jira:{prefix}")
        )
    ).scalars()
    for node in node_rows:
        related_nodes.append(
            {
                "entity_id": node.entity_id,
                "entity_type": node.entity_type,
                "name": node.canonical_name,
            }
        )

    # The assignee lives in actor_external_id, not metadata_json.
    owner = events[-1].actor_external_id if events else None
    next_action = None
    if related_findings:
        next_action = related_findings[0].get("suggested_action")

    return {
        "issue_key": issue_key,
        "owner": owner,
        "source_refs": [
            {"source_event_id": e.source_event_id, "raw_object_ref": e.raw_object_ref}
            for e in events
        ],
        "related_nodes": related_nodes,
        "related_findings": related_findings,
        "evidence_timeline": status_history,
        "status_history": status_history,
        "suggested_next_action": next_action,
    }
