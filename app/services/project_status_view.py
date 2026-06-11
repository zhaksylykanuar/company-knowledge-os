"""Deterministic per-project Jira status view (A5-lite, no LLM).

Builds a founder-readable project answer from synced Jira issue source
events: status breakdown, fresh activity, stale in-progress work, overdue
items and assignee load. Read-only; one phone screen; Russian.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.event_models import SourceEvent

STALE_DAYS = 14
FRESH_DAYS = 7
MAX_LIST_ITEMS = 4
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
    now: datetime | None = None,
) -> str:
    """Founder-readable per-project Jira status, one phone screen."""

    safe_now = now or datetime.now(timezone.utc)
    header = f"📂 {project_name} — статус по Jira ({', '.join(jira_keys)})"
    if not snapshots:
        return (
            f"{header}\n\nЗадачи ещё не синхронизированы.\n"
            "Запустите sync_jira_issues.py и спросите снова.\n"
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

    lines.extend(
        [
            "",
            "Second opinion (Jira↔GitHub) появится после синка GitHub.",
            "[Показать всё] [Скрыть похожее]",
        ]
    )
    return "\n".join(lines) + "\n"
