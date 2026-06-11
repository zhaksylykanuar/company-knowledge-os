"""Deterministic project status snapshots built from project_status_view data."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.project_status_view import (
    FRESH_DAYS,
    PR_REVIEW_STALE_DAYS,
    STALE_DAYS,
    JiraIssueSnapshot,
    RepoActivity,
    load_project_issue_snapshots,
    load_repo_activity,
)

DEFAULT_ORGANIZATION_ID = "default"
ENTITY_TYPE_PROJECT = "project"
STATUS_GREEN = "green"
STATUS_YELLOW = "yellow"
STATUS_RED = "red"
STATUS_UNKNOWN = "unknown"

_MISSING_OWNER_VALUES = {"", "none", "null", "unknown", "unassigned"}
_RED_MARKERS = (
    "blocked",
    "blocker",
    "critical",
    "escalation",
    "missed deadline",
    "release blocked",
    "security",
    "заблок",
    "критич",
    "безопас",
)


@dataclass(frozen=True)
class StatusSnapshot:
    organization_id: str
    entity_type: str
    entity_id: str
    status_color: str
    summary: str
    what_changed: tuple[dict[str, Any], ...]
    current_work: tuple[dict[str, Any], ...]
    blockers: tuple[dict[str, Any], ...]
    risks: tuple[dict[str, Any], ...]
    conflicts: tuple[dict[str, Any], ...]
    recommendations: tuple[dict[str, Any], ...]
    confidence: float
    confidence_reason: str
    last_meaningful_update_at: datetime | None
    evidence_source_ids: tuple[str, ...]


def build_project_status_snapshot(
    *,
    project_entity_id: str,
    project_name: str,
    jira_keys: list[str],
    snapshots: list[JiraIssueSnapshot],
    repo_activity: RepoActivity | None = None,
    previous_snapshot: Any | None = None,
    organization_id: str = DEFAULT_ORGANIZATION_ID,
    now: datetime | None = None,
) -> StatusSnapshot:
    safe_now = now or datetime.now(timezone.utc)
    open_items = [item for item in snapshots if not item.is_done]
    done_count = len(snapshots) - len(open_items)
    current_work = tuple(_current_work_item(item) for item in sorted(open_items, key=lambda i: i.issue_key))
    blockers = tuple(_blockers(open_items, safe_now))
    risks = tuple(_risks(open_items, repo_activity, safe_now))
    conflicts = tuple(_conflicts(open_items, snapshots, repo_activity, safe_now))
    recommendations = tuple(_recommendations(blockers, risks, conflicts, snapshots))
    evidence_source_ids = tuple(_evidence_source_ids(snapshots, repo_activity))
    last_meaningful_update_at = _last_meaningful_update_at(snapshots, repo_activity)
    status_color = _status_color(
        snapshots=snapshots,
        blockers=blockers,
        risks=risks,
        conflicts=conflicts,
        last_meaningful_update_at=last_meaningful_update_at,
    )
    confidence, confidence_reason = _confidence(
        snapshots=snapshots,
        repo_activity=repo_activity,
        conflicts=conflicts,
        risks=risks,
        last_meaningful_update_at=last_meaningful_update_at,
        now=safe_now,
    )
    summary = _summary(
        project_name=project_name,
        jira_keys=jira_keys,
        snapshots=snapshots,
        open_count=len(open_items),
        done_count=done_count,
        blockers=blockers,
        risks=risks,
        conflicts=conflicts,
        status_color=status_color,
    )
    what_changed = tuple(
        _what_changed(
            previous_snapshot=previous_snapshot,
            status_color=status_color,
            summary=summary,
            confidence=confidence,
            current_work=current_work,
            blockers=blockers,
            risks=risks,
            conflicts=conflicts,
        )
    )
    return StatusSnapshot(
        organization_id=organization_id,
        entity_type=ENTITY_TYPE_PROJECT,
        entity_id=project_entity_id,
        status_color=status_color,
        summary=summary,
        what_changed=what_changed,
        current_work=current_work,
        blockers=blockers,
        risks=risks,
        conflicts=conflicts,
        recommendations=recommendations,
        confidence=confidence,
        confidence_reason=confidence_reason,
        last_meaningful_update_at=last_meaningful_update_at,
        evidence_source_ids=evidence_source_ids,
    )


async def create_project_status_snapshot(
    session: AsyncSession,
    *,
    project_entity_id: str,
    project_name: str,
    jira_keys: list[str],
    repos: list[dict[str, str]] | None = None,
    organization_id: str = DEFAULT_ORGANIZATION_ID,
    now: datetime | None = None,
) -> Any:
    from app.services.status_snapshot_repository import (
        get_latest_status_snapshot,
        save_status_snapshot,
    )

    safe_now = now or datetime.now(timezone.utc)
    issue_snapshots = await load_project_issue_snapshots(session, jira_keys)
    repo_activity = await load_repo_activity(session, repos or [], now=safe_now)
    previous = await get_latest_status_snapshot(
        session,
        organization_id=organization_id,
        entity_type=ENTITY_TYPE_PROJECT,
        entity_id=project_entity_id,
    )
    snapshot = build_project_status_snapshot(
        project_entity_id=project_entity_id,
        project_name=project_name,
        jira_keys=jira_keys,
        snapshots=issue_snapshots,
        repo_activity=repo_activity,
        previous_snapshot=previous,
        organization_id=organization_id,
        now=safe_now,
    )
    return await save_status_snapshot(session, snapshot)


def _current_work_item(item: JiraIssueSnapshot) -> dict[str, Any]:
    return {
        "id": item.issue_key,
        "title": item.title,
        "status": item.status,
        "assignee": item.assignee,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
        "due_date": item.duedate,
    }


def _blockers(items: Iterable[JiraIssueSnapshot], now: datetime) -> list[dict[str, Any]]:
    today = now.date().isoformat()
    blockers: list[dict[str, Any]] = []
    for item in items:
        if item.duedate and item.duedate < today:
            blockers.append(
                {
                    "id": f"overdue:{item.issue_key}",
                    "type": "overdue",
                    "source_id": item.issue_key,
                    "title": item.title,
                    "due_date": item.duedate,
                    "severity": "critical",
                }
            )
        marker_text = f"{item.status} {item.title}".casefold()
        if any(marker in marker_text for marker in _RED_MARKERS):
            blockers.append(
                {
                    "id": f"critical_marker:{item.issue_key}",
                    "type": "critical_marker",
                    "source_id": item.issue_key,
                    "title": item.title,
                    "severity": "critical",
                }
            )
    return blockers


def _risks(
    items: Iterable[JiraIssueSnapshot],
    repo_activity: RepoActivity | None,
    now: datetime,
) -> list[dict[str, Any]]:
    risks: list[dict[str, Any]] = []
    for item in items:
        age = _age_days(item.updated_at, now)
        if age is not None and age > STALE_DAYS:
            risks.append(
                {
                    "id": f"stale_issue:{item.issue_key}",
                    "type": "stale_issue",
                    "source_id": item.issue_key,
                    "title": item.title,
                    "age_days": age,
                    "severity": "medium",
                }
            )
        if _is_missing_owner(item.assignee):
            risks.append(
                {
                    "id": f"missing_owner:{item.issue_key}",
                    "type": "missing_owner",
                    "source_id": item.issue_key,
                    "title": item.title,
                    "severity": "medium",
                }
            )
    if repo_activity is not None:
        for pr in repo_activity.open_prs:
            age = _age_days(pr.updated_at, now)
            if age is not None and age >= PR_REVIEW_STALE_DAYS:
                risks.append(
                    {
                        "id": f"stale_review_pr:{pr.pr_id}",
                        "type": "stale_review_pr",
                        "source_id": pr.pr_id,
                        "title": pr.title,
                        "age_days": age,
                        "severity": "medium",
                    }
                )
    return risks


def _conflicts(
    open_items: list[JiraIssueSnapshot],
    snapshots: list[JiraIssueSnapshot],
    repo_activity: RepoActivity | None,
    now: datetime,
) -> list[dict[str, Any]]:
    if repo_activity is None:
        return []

    active_keys = set(repo_activity.commit_jira_keys_7d)
    for pr in repo_activity.open_prs + repo_activity.merged_prs:
        age = _age_days(pr.updated_at, now)
        if age is not None and age <= FRESH_DAYS:
            active_keys.update(pr.jira_keys)

    conflicts: list[dict[str, Any]] = []
    in_progress = [item for item in open_items if "progress" in item.status.casefold()]
    for item in in_progress:
        if item.issue_key not in active_keys:
            conflicts.append(
                {
                    "id": f"jira_in_progress_without_code:{item.issue_key}",
                    "type": "jira_in_progress_without_code",
                    "source_id": item.issue_key,
                    "title": item.title,
                    "severity": "medium",
                }
            )

    for pr in repo_activity.open_prs:
        if not pr.jira_keys:
            conflicts.append(
                {
                    "id": f"github_pr_without_jira:{pr.pr_id}",
                    "type": "github_pr_without_jira",
                    "source_id": pr.pr_id,
                    "title": pr.title,
                    "severity": "medium",
                }
            )

    open_issue_keys = {item.issue_key for item in open_items}
    known_issue_keys = {item.issue_key for item in snapshots}
    for pr in repo_activity.merged_prs:
        for key in pr.jira_keys:
            if key in open_issue_keys and key in known_issue_keys:
                conflicts.append(
                    {
                        "id": f"merged_pr_open_jira:{key}",
                        "type": "merged_pr_open_jira",
                        "source_id": key,
                        "pr_id": pr.pr_id,
                        "title": pr.title,
                        "severity": "medium",
                    }
                )
    return conflicts


def _recommendations(
    blockers: tuple[dict[str, Any], ...],
    risks: tuple[dict[str, Any], ...],
    conflicts: tuple[dict[str, Any], ...],
    snapshots: list[JiraIssueSnapshot],
) -> list[dict[str, str]]:
    recommendations: list[dict[str, str]] = []
    risk_types = {str(item.get("type")) for item in risks}
    if not snapshots:
        recommendations.append(
            {
                "id": "sync_jira",
                "text": "Sync Jira issues before relying on this project status.",
            }
        )
    if blockers:
        recommendations.append(
            {
                "id": "resolve_blockers",
                "text": "Resolve critical blockers before the next status update.",
            }
        )
    if "stale_issue" in risk_types:
        recommendations.append(
            {
                "id": "refresh_stale_issues",
                "text": "Refresh stale open Jira issues or close them.",
            }
        )
    if "missing_owner" in risk_types:
        recommendations.append(
            {
                "id": "assign_owners",
                "text": "Assign owners to unowned open issues.",
            }
        )
    if conflicts:
        recommendations.append(
            {
                "id": "reconcile_sources",
                "text": "Reconcile Jira and GitHub status mismatches.",
            }
        )
    return recommendations


def _status_color(
    *,
    snapshots: list[JiraIssueSnapshot],
    blockers: tuple[dict[str, Any], ...],
    risks: tuple[dict[str, Any], ...],
    conflicts: tuple[dict[str, Any], ...],
    last_meaningful_update_at: datetime | None,
) -> str:
    if not snapshots or last_meaningful_update_at is None:
        return STATUS_UNKNOWN
    if blockers:
        return STATUS_RED
    if risks or conflicts:
        return STATUS_YELLOW
    return STATUS_GREEN


def _confidence(
    *,
    snapshots: list[JiraIssueSnapshot],
    repo_activity: RepoActivity | None,
    conflicts: tuple[dict[str, Any], ...],
    risks: tuple[dict[str, Any], ...],
    last_meaningful_update_at: datetime | None,
    now: datetime,
) -> tuple[float, str]:
    if not snapshots:
        return 0.2, "No synced Jira issue snapshots; source freshness is insufficient."

    score = 0.50
    reasons: list[str] = []
    latest_age = _age_days(last_meaningful_update_at, now)
    if latest_age is None:
        score -= 0.20
        reasons.append("latest evidence timestamp is missing")
    elif latest_age <= FRESH_DAYS:
        score += 0.20
        reasons.append("fresh source evidence")
    elif latest_age <= STALE_DAYS:
        score += 0.10
        reasons.append("recent source evidence")
    else:
        score -= 0.15
        reasons.append("latest source evidence is stale")

    if repo_activity is not None:
        score += 0.15
        reasons.append("Jira and GitHub are independent sources")
    else:
        score += 0.05
        reasons.append("Jira is the only available source")

    score += 0.10
    reasons.append("Jira issue status is structured source data")

    if all(item.updated_at and item.issue_key and item.status for item in snapshots):
        score += 0.05
        reasons.append("raw issue evidence is complete")
    else:
        score -= 0.05
        reasons.append("some raw issue evidence is incomplete")

    if conflicts:
        score -= min(0.35, 0.15 * len(conflicts))
        reasons.append("source conflicts reduce confidence")

    risk_types = {str(item.get("type")) for item in risks}
    if "stale_issue" in risk_types:
        score -= 0.10
        reasons.append("stale open Jira issues reduce confidence")
    if "missing_owner" in risk_types:
        score -= 0.10
        reasons.append("missing owners reduce confidence")

    return round(_clamp(score), 2), "; ".join(reasons)


def _summary(
    *,
    project_name: str,
    jira_keys: list[str],
    snapshots: list[JiraIssueSnapshot],
    open_count: int,
    done_count: int,
    blockers: tuple[dict[str, Any], ...],
    risks: tuple[dict[str, Any], ...],
    conflicts: tuple[dict[str, Any], ...],
    status_color: str,
) -> str:
    key_text = ", ".join(jira_keys) if jira_keys else "no Jira keys"
    return (
        f"{project_name}: {status_color}; Jira {key_text}; "
        f"{len(snapshots)} issues, {open_count} open, {done_count} done; "
        f"{len(blockers)} blockers, {len(risks)} risks, {len(conflicts)} conflicts."
    )


def _what_changed(
    *,
    previous_snapshot: Any | None,
    status_color: str,
    summary: str,
    confidence: float,
    current_work: tuple[dict[str, Any], ...],
    blockers: tuple[dict[str, Any], ...],
    risks: tuple[dict[str, Any], ...],
    conflicts: tuple[dict[str, Any], ...],
) -> list[dict[str, Any]]:
    if previous_snapshot is None:
        return [{"field": "snapshot", "change": "created"}]

    changes: list[dict[str, Any]] = []
    previous_color = getattr(previous_snapshot, "status_color", None)
    if previous_color != status_color:
        changes.append(
            {
                "field": "status_color",
                "change": "changed",
                "from": previous_color,
                "to": status_color,
            }
        )

    previous_summary = getattr(previous_snapshot, "summary", None)
    if previous_summary != summary:
        changes.append({"field": "summary", "change": "changed"})

    previous_confidence = getattr(previous_snapshot, "confidence", None)
    if previous_confidence is None or abs(float(previous_confidence) - confidence) >= 0.01:
        changes.append(
            {
                "field": "confidence",
                "change": "changed",
                "from": previous_confidence,
                "to": confidence,
            }
        )

    changes.extend(_collection_changes("current_work", _list_field(previous_snapshot, "current_work"), current_work))
    changes.extend(_collection_changes("blockers", _list_field(previous_snapshot, "blockers"), blockers))
    changes.extend(_collection_changes("risks", _list_field(previous_snapshot, "risks"), risks))
    changes.extend(_collection_changes("conflicts", _list_field(previous_snapshot, "conflicts"), conflicts))
    return changes


def _collection_changes(
    field: str,
    previous_items: Iterable[dict[str, Any]],
    current_items: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    previous_ids = {_item_id(item) for item in previous_items}
    current_ids = {_item_id(item) for item in current_items}
    previous_ids.discard("")
    current_ids.discard("")
    changes: list[dict[str, Any]] = []
    added = sorted(current_ids - previous_ids)
    removed = sorted(previous_ids - current_ids)
    if added:
        changes.append({"field": field, "change": "added", "ids": added})
    if removed:
        changes.append({"field": field, "change": "removed", "ids": removed})
    return changes


def _list_field(snapshot: Any, field: str) -> list[dict[str, Any]]:
    value = getattr(snapshot, field, None)
    if value is None:
        value = getattr(snapshot, f"{field}_json", None)
    if value is None:
        return []
    return [item for item in value if isinstance(item, dict)]


def _item_id(item: dict[str, Any]) -> str:
    return str(item.get("id") or item.get("source_id") or "")


def _evidence_source_ids(
    snapshots: list[JiraIssueSnapshot],
    repo_activity: RepoActivity | None,
) -> list[str]:
    evidence = [f"jira:issue:{item.issue_key}" for item in snapshots]
    if repo_activity is not None:
        evidence.extend(f"github:pull_request:{pr.pr_id}" for pr in repo_activity.open_prs)
        evidence.extend(f"github:pull_request:{pr.pr_id}" for pr in repo_activity.merged_prs)
        if repo_activity.commit_count_7d:
            evidence.append("github:commits:7d")
    return sorted(set(evidence))


def _last_meaningful_update_at(
    snapshots: list[JiraIssueSnapshot],
    repo_activity: RepoActivity | None,
) -> datetime | None:
    values = [item.updated_at for item in snapshots if item.updated_at is not None]
    if repo_activity is not None:
        values.extend(pr.updated_at for pr in repo_activity.open_prs if pr.updated_at is not None)
        values.extend(pr.updated_at for pr in repo_activity.merged_prs if pr.updated_at is not None)
    return max(values) if values else None


def _is_missing_owner(value: str | None) -> bool:
    return (value or "").strip().casefold() in _MISSING_OWNER_VALUES


def _age_days(value: datetime | None, now: datetime) -> int | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return max(0, int((now - value.astimezone(timezone.utc)).total_seconds() // 86_400))


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
