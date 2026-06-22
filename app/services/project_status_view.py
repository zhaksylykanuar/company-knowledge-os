"""Deterministic per-project Jira status view (A5-lite, no LLM).

Builds a founder-readable project answer from synced Jira issue source
events: status breakdown, fresh activity, stale in-progress work, overdue
items and assignee load. Read-only; one phone screen; Russian.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.event_models import SourceEvent

STALE_DAYS = 14
FRESH_DAYS = 7
MAX_LIST_ITEMS = 4
PR_REVIEW_STALE_DAYS = 2
_DONE_STATUSES = {
    "done",
    "готово",
    "closed",
    "resolved",
    "отменено",
    "cancelled",
    "canceled",
}


@dataclass(frozen=True)
class JiraIssueSnapshot:
    issue_key: str
    title: str
    status: str
    assignee: str
    updated_at: datetime | None
    duedate: str | None

    @property
    def is_done(self) -> bool:
        return self.status.casefold() in _DONE_STATUSES


@dataclass(frozen=True)
class PullRequestSnapshot:
    pr_id: str
    title: str
    state: str
    merged: bool
    author: str
    updated_at: datetime | None
    jira_keys: tuple[str, ...]
    review_requested: bool


@dataclass(frozen=True)
class RepoActivity:
    repo_names: tuple[str, ...]
    open_prs: tuple[PullRequestSnapshot, ...]
    merged_prs: tuple[PullRequestSnapshot, ...]
    commit_count_7d: int
    commit_jira_keys_7d: frozenset[str]
    pr_jira_keys: frozenset[str]
    source_event_count: int = 0
    last_source_event_at: datetime | None = None
    source_run_ids: tuple[str, ...] = ()
    window_start: datetime | None = None
    window_end: datetime | None = None
    window_days: int = FRESH_DAYS


def _parse_jira_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def snapshot_from_payload(source_object_id: str, payload: Any) -> JiraIssueSnapshot:
    data = payload if isinstance(payload, dict) else {}
    title = data.get("title")
    if isinstance(title, str) and title.startswith(f"[{source_object_id}] "):
        title = title[len(source_object_id) + 3 :]
    return JiraIssueSnapshot(
        issue_key=source_object_id,
        title=title if isinstance(title, str) and title else source_object_id,
        status=str(data.get("status") or "Unknown"),
        assignee=str(data.get("actor_external_id") or "unassigned"),
        updated_at=_parse_jira_datetime(data.get("updated")),
        duedate=data.get("duedate") if isinstance(data.get("duedate"), str) else None,
    )


async def load_project_issue_snapshots(
    session: AsyncSession,
    jira_keys: list[str],
) -> list[JiraIssueSnapshot]:
    """Latest synced snapshot per issue for the given Jira project keys."""

    if not jira_keys:
        return []
    from app.db.models import IngestedEvent

    rows = (
        await session.execute(
            select(SourceEvent.source_object_id, IngestedEvent.payload)
            .join(
                IngestedEvent,
                IngestedEvent.event_id == SourceEvent.ingested_event_id,
            )
            .where(SourceEvent.source_system == "jira")
            .where(SourceEvent.source_object_type == "issue")
            .where(
                or_(
                    *[
                        SourceEvent.source_object_id.like(f"{key}-%")
                        for key in jira_keys
                    ]
                )
            )
            .order_by(SourceEvent.id)
        )
    ).all()

    latest: dict[str, JiraIssueSnapshot] = {}
    for source_object_id, payload in rows:
        snapshot = snapshot_from_payload(str(source_object_id), payload)
        current = latest.get(snapshot.issue_key)
        if (
            current is None
            or (snapshot.updated_at or datetime.min.replace(tzinfo=timezone.utc))
            >= (current.updated_at or datetime.min.replace(tzinfo=timezone.utc))
        ):
            latest[snapshot.issue_key] = snapshot
    return list(latest.values())


async def load_repo_activity(
    session: AsyncSession,
    repos: list[dict[str, str]],
    *,
    now: datetime | None = None,
) -> RepoActivity | None:
    """Latest PR snapshots + recent commit signal for mapped repos."""

    if not repos:
        return None
    from app.db.models import IngestedEvent

    safe_now = _as_utc(now) or datetime.now(timezone.utc)
    window_start = safe_now - timedelta(days=FRESH_DAYS)
    prefixes = [f"{r['org']}/{r['repo']}" for r in repos]
    rows = (
        await session.execute(
            select(
                SourceEvent.source_object_id,
                SourceEvent.source_object_type,
                SourceEvent.source_event_ts,
                SourceEvent.created_at,
                SourceEvent.created_by_run_id,
                IngestedEvent.payload,
            )
            .join(
                IngestedEvent,
                IngestedEvent.event_id == SourceEvent.ingested_event_id,
            )
            .where(SourceEvent.source_system == "github")
            .where(
                or_(
                    *[
                        SourceEvent.source_object_id.like(f"{prefix}%")
                        for prefix in prefixes
                    ]
                )
            )
            .order_by(SourceEvent.id)
        )
    ).all()

    latest_prs: dict[str, PullRequestSnapshot] = {}
    commit_count_7d = 0
    commit_keys_7d: set[str] = set()
    source_event_count = 0
    last_source_event_at: datetime | None = None
    source_run_ids: set[str] = set()
    for (
        object_id,
        object_type,
        source_event_ts,
        created_at,
        created_by_run_id,
        payload,
    ) in rows:
        source_event_count += 1
        observed_at = _as_utc(source_event_ts) or _as_utc(created_at)
        if observed_at is not None and (
            last_source_event_at is None or observed_at > last_source_event_at
        ):
            last_source_event_at = observed_at
        if isinstance(created_by_run_id, str) and created_by_run_id:
            source_run_ids.add(created_by_run_id)

        data = payload if isinstance(payload, dict) else {}
        if object_type == "commit":
            authored = _parse_jira_datetime(data.get("authored_at"))
            if authored and (safe_now - authored).days <= FRESH_DAYS:
                commit_count_7d += 1
                for key in data.get("jira_keys") or []:
                    if isinstance(key, str):
                        commit_keys_7d.add(key)
            continue
        if object_type != "pull_request":
            continue
        snap = PullRequestSnapshot(
            pr_id=str(object_id),
            title=str(data.get("title") or object_id),
            state=str(data.get("state") or "open"),
            merged=data.get("merged") is True,
            author=str(data.get("actor_external_id") or "unknown"),
            updated_at=_parse_jira_datetime(data.get("updated")),
            jira_keys=tuple(
                key for key in (data.get("jira_keys") or []) if isinstance(key, str)
            ),
            review_requested=data.get("review_requested") is True,
        )
        current = latest_prs.get(snap.pr_id)
        if current is None or (
            (snap.updated_at or datetime.min.replace(tzinfo=timezone.utc))
            >= (current.updated_at or datetime.min.replace(tzinfo=timezone.utc))
        ):
            latest_prs[snap.pr_id] = snap

    open_prs = tuple(
        sorted(
            (p for p in latest_prs.values() if p.state == "open"),
            key=lambda p: p.updated_at or datetime.min.replace(tzinfo=timezone.utc),
        )
    )
    merged_prs = tuple(p for p in latest_prs.values() if p.merged)
    pr_keys = frozenset(
        key for p in latest_prs.values() for key in p.jira_keys
    )
    return RepoActivity(
        repo_names=tuple(sorted(r["repo"] for r in repos)),
        open_prs=open_prs,
        merged_prs=merged_prs,
        commit_count_7d=commit_count_7d,
        commit_jira_keys_7d=frozenset(commit_keys_7d),
        pr_jira_keys=pr_keys,
        source_event_count=source_event_count,
        last_source_event_at=last_source_event_at,
        source_run_ids=tuple(sorted(source_run_ids)),
        window_start=window_start,
        window_end=safe_now,
        window_days=FRESH_DAYS,
    )


def _age_days(snapshot: JiraIssueSnapshot, now: datetime) -> int | None:
    if snapshot.updated_at is None:
        return None
    return max(0, int((now - snapshot.updated_at).total_seconds() // 86_400))


def _short(text: str, limit: int = 60) -> str:
    cleaned = " ".join(text.split())
    return cleaned if len(cleaned) <= limit else cleaned[: limit - 1].rstrip() + "…"


def render_project_status_text(
    *,
    project_name: str,
    jira_keys: list[str],
    snapshots: list[JiraIssueSnapshot],
    repo_activity: RepoActivity | None = None,
    now: datetime | None = None,
) -> str:
    """Founder-readable per-project Jira status, one phone screen."""

    safe_now = now or datetime.now(timezone.utc)
    header = f"📂 {project_name} — статус по Jira ({', '.join(jira_keys)})"
    if not snapshots:
        return (
            f"{header}\n\nЗадачи ещё не синхронизированы.\n"
            "Запустите Source Control request через операторский run_source_requests.py "
            "и спросите снова.\n"
        )

    open_items = [s for s in snapshots if not s.is_done]
    done_count = len(snapshots) - len(open_items)
    by_status = Counter(s.status for s in open_items)
    fresh = [
        s
        for s in open_items
        if (_age_days(s, safe_now) is not None and _age_days(s, safe_now) <= FRESH_DAYS)
    ]
    stale = sorted(
        (
            s
            for s in open_items
            if (_age_days(s, safe_now) or 0) > STALE_DAYS
        ),
        key=lambda s: -(_age_days(s, safe_now) or 0),
    )
    today = safe_now.date().isoformat()
    overdue = [s for s in open_items if s.duedate and s.duedate < today]

    lines = [header, ""]
    status_line = " · ".join(
        f"{status}: {count}" for status, count in by_status.most_common(4)
    )
    lines.append(
        f"Всего: {len(snapshots)} задач "
        f"(открытых {len(open_items)}, закрытых {done_count})"
    )
    if status_line:
        lines.append(status_line)
    lines.append(
        f"Обновлялись за {FRESH_DAYS} дн: {len(fresh)} · "
        f"без движения >{STALE_DAYS} дн: {len(stale)} · просрочено: {len(overdue)}"
    )

    fresh_sorted = sorted(
        fresh, key=lambda s: (_age_days(s, safe_now) if _age_days(s, safe_now) is not None else 999)
    )
    if fresh_sorted:
        lines.extend(["", "🔧 Свежая активность"])
        for s in fresh_sorted[:MAX_LIST_ITEMS]:
            age = _age_days(s, safe_now)
            lines.append(
                f"• [{s.issue_key}] {_short(s.title)} — {s.assignee}"
                + (f" ({age} дн назад)" if age is not None else "")
            )

    if stale:
        lines.extend(["", f"🧊 Без движения >{STALE_DAYS} дней"])
        for s in stale[:MAX_LIST_ITEMS]:
            lines.append(
                f"• [{s.issue_key}] {_short(s.title)} — {s.assignee}"
                f" ({_age_days(s, safe_now)} дн)"
            )
        if len(stale) > MAX_LIST_ITEMS:
            lines.append(f"…и ещё {len(stale) - MAX_LIST_ITEMS}")

    if overdue:
        lines.extend(["", "⏰ Просрочено"])
        for s in overdue[:MAX_LIST_ITEMS]:
            lines.append(
                f"• [{s.issue_key}] {_short(s.title)} — {s.assignee} (до {s.duedate})"
            )

    load = Counter(s.assignee for s in open_items)
    if load:
        lines.extend(["", "👥 Открытые задачи по людям"])
        lines.append(
            " · ".join(f"{name}: {count}" for name, count in load.most_common(5))
        )

    if repo_activity is not None:
        lines.extend(["", f"⚙️ Код ({', '.join(repo_activity.repo_names)})"])
        lines.append(
            f"Коммитов за {FRESH_DAYS} дн: {repo_activity.commit_count_7d} · "
            f"открытых PR: {len(repo_activity.open_prs)} · "
            f"merged: {len(repo_activity.merged_prs)}"
        )
        waiting_prs = [
            p
            for p in repo_activity.open_prs
            if (
                p.updated_at is not None
                and (safe_now - p.updated_at).days >= PR_REVIEW_STALE_DAYS
            )
        ]
        for p in waiting_prs[:3]:
            age = (safe_now - p.updated_at).days if p.updated_at else 0
            lines.append(f"• {_short(p.title)} — {p.author}, без движения {age} дн")

        active_keys = set(repo_activity.commit_jira_keys_7d)
        for p in repo_activity.open_prs + repo_activity.merged_prs:
            if p.updated_at and (safe_now - p.updated_at).days <= FRESH_DAYS:
                active_keys.update(p.jira_keys)

        findings: list[str] = []
        in_progress = [
            s for s in open_items if "progress" in s.status.casefold()
        ]
        if in_progress:
            covered = [s for s in in_progress if s.issue_key in active_keys]
            line = (
                f"• Jira In Progress: {len(in_progress)} задач, "
                f"код за {FRESH_DAYS} дн виден по {len(covered)}"
            )
            silent = [s.issue_key for s in in_progress if s.issue_key not in active_keys]
            if silent:
                line += f" (молчат: {', '.join(silent[:3])}"
                line += f" и ещё {len(silent) - 3})" if len(silent) > 3 else ")"
            findings.append(line)
        prs_without_jira = [p for p in repo_activity.open_prs if not p.jira_keys]
        if prs_without_jira:
            findings.append(
                f"• Открытых PR без Jira-задачи: {len(prs_without_jira)}"
            )
        done_keys = {s.issue_key for s in snapshots if s.is_done}
        merged_not_done = sorted(
            {
                key
                for p in repo_activity.merged_prs
                for key in p.jira_keys
                if key in {s.issue_key for s in open_items}
            }
        )
        del done_keys
        if merged_not_done:
            findings.append(
                "• PR merged, но задача не закрыта: "
                + ", ".join(merged_not_done[:3])
            )

        lines.extend(["", "🔍 Second opinion"])
        if findings:
            lines.extend(findings)
        else:
            lines.append("Расхождений Jira↔GitHub не найдено.")

    lines.extend(["", "[Показать всё] [Скрыть похожее]"])
    return "\n".join(lines) + "\n"
