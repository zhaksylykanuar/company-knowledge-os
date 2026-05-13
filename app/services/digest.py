from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import case, desc, func, select
from sqlalchemy.engine import Row
from sqlalchemy.exc import SQLAlchemyError

from app.db.base import AsyncSessionLocal
from app.db.event_models import SourceEvent
from app.db.gmail_models import EmailThreadState

DEFAULT_DIGEST_ENTRY_LIMIT = 20
MAX_DIGEST_ENTRY_LIMIT = 50
DEFAULT_INFORMATIONAL_EMAIL_THREAD_LIMIT = 3

EMAIL_THREAD_STATUS_NEEDS_MY_REPLY = "needs_my_reply"
EMAIL_THREAD_STATUS_WAITING_FOR_EXTERNAL_REPLY = "waiting_for_external_reply"
EMAIL_THREAD_STATUS_INFORMATIONAL = "informational"
EMAIL_THREAD_GROUPS = (
    EMAIL_THREAD_STATUS_NEEDS_MY_REPLY,
    EMAIL_THREAD_STATUS_WAITING_FOR_EXTERNAL_REPLY,
    EMAIL_THREAD_STATUS_INFORMATIONAL,
)


def _require_aware_datetime(value: datetime, *, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


def _safe_limit(limit: int) -> int:
    try:
        parsed = int(limit)
    except (TypeError, ValueError):
        return DEFAULT_DIGEST_ENTRY_LIMIT

    if parsed < 1:
        return DEFAULT_DIGEST_ENTRY_LIMIT

    return min(parsed, MAX_DIGEST_ENTRY_LIMIT)


def _count_dict(rows: Sequence[tuple[str | None, int]]) -> dict[str, int]:
    return {
        str(key): count
        for key, count in sorted(rows, key=lambda row: str(row[0]))
        if key is not None
    }


def _count_pairs(rows: Sequence[Row[tuple[str, int]]]) -> list[tuple[str, int]]:
    return [(row[0], row[1]) for row in rows]


def _activity_time(source_event: SourceEvent) -> datetime | None:
    return source_event.source_event_ts or source_event.created_at


def _iso_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None

    return value.isoformat()


def _source_event_evidence_refs(source_event: SourceEvent) -> list[dict[str, Any]]:
    evidence_refs: list[dict[str, Any]] = [
        {
            "kind": "source_event",
            "source_event_id": source_event.source_event_id,
            "source_system": source_event.source_system,
            "source_object_type": source_event.source_object_type,
            "source_object_id": source_event.source_object_id,
            "event_type": source_event.event_type,
            "raw_object_ref": source_event.raw_object_ref,
        }
    ]

    if isinstance(source_event.evidence_refs, list):
        evidence_refs.extend(
            dict(evidence_ref)
            for evidence_ref in source_event.evidence_refs
            if isinstance(evidence_ref, dict)
        )

    return evidence_refs


def _json_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _email_thread_evidence_refs(email_thread: EmailThreadState) -> list[dict[str, Any]]:
    evidence_refs = [
        dict(evidence_ref)
        for evidence_ref in _json_list(email_thread.evidence_refs)
        if isinstance(evidence_ref, dict)
    ]
    if evidence_refs:
        return evidence_refs

    return [
        {
            "kind": "email_thread_state",
            "source_system": email_thread.source,
            "source_object_type": "email_thread_state",
            "source_object_id": email_thread.thread_key,
        }
    ]


def _email_thread_digest_item(email_thread: EmailThreadState) -> dict[str, Any]:
    summary = email_thread.thread_summary or email_thread.last_message_summary
    return {
        "status": email_thread.status,
        "last_message_at": _iso_datetime(email_thread.last_message_at),
        "last_message_direction": email_thread.last_message_direction,
        "days_without_reply": email_thread.days_without_reply,
        "messages_count": email_thread.messages_count,
        "summary": summary,
        "evidence_refs": _email_thread_evidence_refs(email_thread),
    }


def _email_thread_sort_key(item: dict[str, Any]) -> tuple[int, str]:
    days_without_reply = item.get("days_without_reply")
    safe_days = days_without_reply if isinstance(days_without_reply, int) else -1
    last_message_at = item.get("last_message_at")
    safe_last_message_at = str(last_message_at) if last_message_at is not None else ""
    return (safe_days, safe_last_message_at)


def _empty_email_thread_intelligence(
    *,
    available: bool,
    data_quality_notes: list[str],
    entry_limit: int,
) -> dict[str, Any]:
    return {
        "section_title": "Email threads requiring attention",
        "available": available,
        "counts": {
            "total": 0,
            "active": 0,
            "by_status": {},
        },
        "groups": {
            EMAIL_THREAD_STATUS_NEEDS_MY_REPLY: [],
            EMAIL_THREAD_STATUS_WAITING_FOR_EXTERNAL_REPLY: [],
            EMAIL_THREAD_STATUS_INFORMATIONAL: [],
        },
        "data_quality_notes": data_quality_notes,
        "metadata": {
            "source_model": "email_thread_states",
            "group_limit": entry_limit,
            "informational_limit": DEFAULT_INFORMATIONAL_EMAIL_THREAD_LIMIT,
            "raw_gmail_entries_suppressed": False,
        },
    }


async def _build_email_thread_intelligence(
    *,
    session,
    start_at: datetime,
    end_at: datetime,
    limit: int,
) -> dict[str, Any]:
    status_priority = case(
        (EmailThreadState.status == EMAIL_THREAD_STATUS_NEEDS_MY_REPLY, 0),
        (EmailThreadState.status == EMAIL_THREAD_STATUS_WAITING_FOR_EXTERNAL_REPLY, 1),
        (EmailThreadState.status == EMAIL_THREAD_STATUS_INFORMATIONAL, 2),
        else_=3,
    )
    selected_rows_limit = max(
        limit * len(EMAIL_THREAD_GROUPS),
        DEFAULT_INFORMATIONAL_EMAIL_THREAD_LIMIT,
    )

    try:
        rows = list(
            (
                await session.execute(
                    select(EmailThreadState)
                    .where(EmailThreadState.source == "gmail")
                    .where(EmailThreadState.last_message_at >= start_at)
                    .where(EmailThreadState.last_message_at < end_at)
                    .where(EmailThreadState.status.in_(EMAIL_THREAD_GROUPS))
                    .order_by(
                        status_priority,
                        desc(EmailThreadState.days_without_reply),
                        desc(EmailThreadState.last_message_at),
                        desc(EmailThreadState.id),
                    )
                    .limit(selected_rows_limit)
                )
            )
            .scalars()
            .all()
        )
    except SQLAlchemyError:
        return _empty_email_thread_intelligence(
            available=False,
            data_quality_notes=[
                "EmailThreadState is unavailable; raw Gmail source events are shown as fallback."
            ],
            entry_limit=limit,
        )

    if not rows:
        return _empty_email_thread_intelligence(
            available=True,
            data_quality_notes=[
                "EmailThreadState has no rows for this digest window; raw Gmail source events are shown as fallback."
            ],
            entry_limit=limit,
        )

    groups = {
        EMAIL_THREAD_STATUS_NEEDS_MY_REPLY: [],
        EMAIL_THREAD_STATUS_WAITING_FOR_EXTERNAL_REPLY: [],
        EMAIL_THREAD_STATUS_INFORMATIONAL: [],
    }
    for row in rows:
        groups[row.status].append(_email_thread_digest_item(row))

    active_count = sum(
        len(groups[status])
        for status in (
            EMAIL_THREAD_STATUS_NEEDS_MY_REPLY,
            EMAIL_THREAD_STATUS_WAITING_FOR_EXTERNAL_REPLY,
        )
    )
    by_status = {
        status: len(items)
        for status, items in groups.items()
        if items
    }
    for status, items in groups.items():
        per_group_limit = (
            DEFAULT_INFORMATIONAL_EMAIL_THREAD_LIMIT
            if status == EMAIL_THREAD_STATUS_INFORMATIONAL
            else limit
        )
        groups[status] = sorted(
            items,
            key=_email_thread_sort_key,
            reverse=True,
        )[:per_group_limit]

    return {
        "section_title": "Email threads requiring attention",
        "available": True,
        "counts": {
            "total": len(rows),
            "active": active_count,
            "by_status": by_status,
        },
        "groups": groups,
        "data_quality_notes": [
            "Raw Gmail source events are summarized in counts because EmailThreadState rows are available."
        ],
        "metadata": {
            "source_model": "email_thread_states",
            "group_limit": limit,
            "informational_limit": DEFAULT_INFORMATIONAL_EMAIL_THREAD_LIMIT,
            "raw_gmail_entries_suppressed": True,
        },
    }


def _digest_entry(source_event: SourceEvent) -> dict[str, Any]:
    return {
        "source_event_id": source_event.source_event_id,
        "source_system": source_event.source_system,
        "source_object_type": source_event.source_object_type,
        "source_object_id": source_event.source_object_id,
        "event_type": source_event.event_type,
        "event_time": _iso_datetime(_activity_time(source_event)),
        "actor_external_id": source_event.actor_external_id,
        "title": source_event.title,
        "source_url": source_event.source_url,
        "evidence_refs": _source_event_evidence_refs(source_event),
    }


def _should_suppress_source_event_entry(
    source_event: SourceEvent,
    *,
    email_thread_intelligence: dict[str, Any],
) -> bool:
    metadata = email_thread_intelligence.get("metadata")
    raw_gmail_entries_suppressed = (
        isinstance(metadata, dict) and metadata.get("raw_gmail_entries_suppressed") is True
    )
    return raw_gmail_entries_suppressed and source_event.source_system == "gmail"


def _visible_source_events(
    source_events: Sequence[SourceEvent],
    *,
    email_thread_intelligence: dict[str, Any],
) -> list[SourceEvent]:
    return [
        source_event
        for source_event in source_events
        if not _should_suppress_source_event_entry(
            source_event,
            email_thread_intelligence=email_thread_intelligence,
        )
    ]


def _has_email_thread_items(email_thread_intelligence: dict[str, Any]) -> bool:
    groups = email_thread_intelligence.get("groups")
    if not isinstance(groups, dict):
        return False

    return any(
        isinstance(groups.get(group_key), list) and bool(groups[group_key])
        for group_key in EMAIL_THREAD_GROUPS
    )


async def build_source_activity_digest(
    *,
    start_at: datetime,
    end_at: datetime,
    limit: int = DEFAULT_DIGEST_ENTRY_LIMIT,
) -> dict[str, Any]:
    """Build a deterministic digest of persisted source activity for a time window.

    This digest reads stored SourceEvent rows only. It does not call LLMs, infer
    tasks/risks/decisions, fetch connector data, or mutate source data.
    """

    _require_aware_datetime(start_at, field_name="start_at")
    _require_aware_datetime(end_at, field_name="end_at")

    if end_at <= start_at:
        raise ValueError("end_at must be after start_at")

    safe_limit = _safe_limit(limit)
    activity_time = func.coalesce(SourceEvent.source_event_ts, SourceEvent.created_at)
    window_filters = (
        activity_time >= start_at,
        activity_time < end_at,
    )

    async with AsyncSessionLocal() as session:
        total_count = (
            await session.execute(
                select(func.count(SourceEvent.id)).where(*window_filters)
            )
        ).scalar_one()

        source_system_counts = (
            await session.execute(
                select(SourceEvent.source_system, func.count(SourceEvent.id))
                .where(*window_filters)
                .group_by(SourceEvent.source_system)
            )
        ).all()
        source_system_count_pairs = _count_pairs(source_system_counts)
        event_type_counts = (
            await session.execute(
                select(SourceEvent.event_type, func.count(SourceEvent.id))
                .where(*window_filters)
                .group_by(SourceEvent.event_type)
            )
        ).all()
        event_type_count_pairs = _count_pairs(event_type_counts)
        source_object_type_counts = (
            await session.execute(
                select(SourceEvent.source_object_type, func.count(SourceEvent.id))
                .where(*window_filters)
                .group_by(SourceEvent.source_object_type)
            )
        ).all()
        source_object_type_count_pairs = _count_pairs(source_object_type_counts)
        has_gmail_source_activity = any(
            source_system == "gmail" and count > 0
            for source_system, count in source_system_count_pairs
        )

        source_events = list(
            (
                await session.execute(
                    select(SourceEvent)
                    .where(*window_filters)
                    .order_by(desc(activity_time), desc(SourceEvent.id))
                    .limit(safe_limit)
                )
            )
            .scalars()
            .all()
        )

        email_thread_intelligence = await _build_email_thread_intelligence(
            session=session,
            start_at=start_at,
            end_at=end_at,
            limit=safe_limit,
        )

    visible_source_events = _visible_source_events(
        source_events,
        email_thread_intelligence=email_thread_intelligence,
    )
    entries = [_digest_entry(source_event) for source_event in visible_source_events]

    digest = {
        "digest_type": "source_activity",
        "window": {
            "start_at": start_at.isoformat(),
            "end_at": end_at.isoformat(),
        },
        "counts": {
            "total": total_count,
            "by_source_system": _count_dict(source_system_count_pairs),
            "by_event_type": _count_dict(event_type_count_pairs),
            "by_source_object_type": _count_dict(source_object_type_count_pairs),
        },
        "entries": entries,
        "metadata": {
            "entry_limit": safe_limit,
            "entry_count": len(entries),
            "truncated": total_count > len(source_events),
            "source_model": "source_events",
            "llm_used": False,
        },
    }

    if has_gmail_source_activity or _has_email_thread_items(email_thread_intelligence):
        digest["email_thread_intelligence"] = email_thread_intelligence

    return digest
