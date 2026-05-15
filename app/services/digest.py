from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import case, desc, func, select
from sqlalchemy.engine import Row
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.db.base import AsyncSessionLocal
from app.db.event_models import SourceEvent
from app.db.gmail_models import EmailThreadState
from app.services.attention_triage import AttentionTriageResult
from app.services.email_attention import email_thread_state_to_attention_result_for_digest

DEFAULT_DIGEST_ENTRY_LIMIT = 20
MAX_DIGEST_ENTRY_LIMIT = 50
DEFAULT_INFORMATIONAL_EMAIL_THREAD_LIMIT = 3
SOURCE_EVENT_DEDUPE_SCAN_MULTIPLIER = 10

EMAIL_THREAD_STATUS_NEEDS_MY_REPLY = "needs_my_reply"
EMAIL_THREAD_STATUS_WAITING_FOR_EXTERNAL_REPLY = "waiting_for_external_reply"
EMAIL_THREAD_STATUS_MANUAL_ACTION_REQUIRED = "manual_action_required"
EMAIL_THREAD_STATUS_INFORMATIONAL = "informational"
EMAIL_THREAD_STATUS_RESOLVED = "resolved"
EMAIL_THREAD_STATUS_HIDDEN = "hidden"

EMAIL_TRIAGE_ACTION_REPLY_REQUIRED = "reply_required"
EMAIL_TRIAGE_ACTION_MANUAL_ACTION_REQUIRED = "manual_action_required"
EMAIL_TRIAGE_ACTION_WAITING_EXTERNAL_REPLY = "waiting_external_reply"
EMAIL_TRIAGE_ACTION_NO_ACTION_REQUIRED = "no_action_required"
EMAIL_TRIAGE_ACTION_REVIEW_OPTIONAL = "review_optional"

EMAIL_TRIAGE_PRIORITY_HIGH = "high"
EMAIL_TRIAGE_PRIORITY_MEDIUM = "medium"
EMAIL_TRIAGE_PRIORITY_LOW = "low"
EMAIL_TRIAGE_PRIORITY_HIDDEN = "hidden"

EMAIL_TRIAGE_CATEGORY_WORK_ACTION = "work_action"
EMAIL_TRIAGE_CATEGORY_WORK_WAITING = "work_waiting"
EMAIL_TRIAGE_CATEGORY_WORK_INFO = "work_info"
EMAIL_TRIAGE_CATEGORY_MANUAL_ACTION = "manual_action"
EMAIL_TRIAGE_CATEGORY_CALENDAR_UPDATE = "calendar_update"
EMAIL_TRIAGE_CATEGORY_SECURITY_ALERT = "security_alert"
EMAIL_TRIAGE_CATEGORY_MARKETING = "marketing"
EMAIL_TRIAGE_CATEGORY_NEWSLETTER = "newsletter"
EMAIL_TRIAGE_CATEGORY_SOCIAL_NETWORK = "social_network"
EMAIL_TRIAGE_CATEGORY_AUTOMATED_NOTIFICATION = "automated_notification"
EMAIL_TRIAGE_CATEGORY_NOISE = "noise"
EMAIL_TRIAGE_CATEGORY_UNKNOWN = "unknown"

EMAIL_THREAD_GROUP_WORK_ACTIONS = "work_actions"
EMAIL_THREAD_GROUP_MANUAL_ACTIONS = "manual_actions"
EMAIL_THREAD_GROUP_WAITING_EXTERNAL_REPLY = "waiting_external_reply"
EMAIL_THREAD_GROUP_WORK_INFO = "work_info"
EMAIL_THREAD_GROUP_REVIEW_OPTIONAL = "review_optional"

EMAIL_THREAD_GROUPS = (
    EMAIL_THREAD_GROUP_WORK_ACTIONS,
    EMAIL_THREAD_GROUP_MANUAL_ACTIONS,
    EMAIL_THREAD_GROUP_WAITING_EXTERNAL_REPLY,
    EMAIL_THREAD_GROUP_WORK_INFO,
    EMAIL_THREAD_GROUP_REVIEW_OPTIONAL,
)

MARKETING_TRIAGE_CATEGORIES = {
    EMAIL_TRIAGE_CATEGORY_MARKETING,
    EMAIL_TRIAGE_CATEGORY_NEWSLETTER,
    EMAIL_TRIAGE_CATEGORY_SOCIAL_NETWORK,
}
AUTOMATED_TRIAGE_CATEGORIES = {
    EMAIL_TRIAGE_CATEGORY_AUTOMATED_NOTIFICATION,
    EMAIL_TRIAGE_CATEGORY_CALENDAR_UPDATE,
}
HIDDEN_EMAIL_CATEGORY_LABELS = {
    EMAIL_TRIAGE_CATEGORY_MARKETING: "marketing/event promotion emails",
    EMAIL_TRIAGE_CATEGORY_NEWSLETTER: "newsletter emails",
    EMAIL_TRIAGE_CATEGORY_SOCIAL_NETWORK: "social network notifications",
    EMAIL_TRIAGE_CATEGORY_CALENDAR_UPDATE: "calendar auto-updates",
    EMAIL_TRIAGE_CATEGORY_AUTOMATED_NOTIFICATION: "automated notifications",
    EMAIL_TRIAGE_CATEGORY_SECURITY_ALERT: "no-action security alerts",
    EMAIL_TRIAGE_CATEGORY_NOISE: "noise emails",
    EMAIL_TRIAGE_CATEGORY_UNKNOWN: "unknown low-priority emails",
}


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


def _plural(count: int, singular: str, plural: str | None = None) -> str:
    if count == 1:
        return f"1 {singular}"
    return f"{count} {plural or singular + 's'}"


def _days_without_reply(last_message_at: datetime | None, generated_at: datetime) -> int | None:
    if last_message_at is None:
        return None

    safe_last = last_message_at
    if safe_last.tzinfo is None or safe_last.utcoffset() is None:
        safe_last = safe_last.replace(tzinfo=timezone.utc)
    else:
        safe_last = safe_last.astimezone(timezone.utc)

    safe_generated_at = generated_at.astimezone(timezone.utc)
    seconds = (safe_generated_at - safe_last).total_seconds()
    if seconds < 0:
        return 0
    return int(seconds // 86_400)


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


def _source_event_evidence_summary(seen_count: int) -> str:
    return _plural(seen_count, "event")


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


def _email_thread_evidence_summary(email_thread: EmailThreadState) -> str:
    messages_count = email_thread.messages_count or 0
    if messages_count > 0:
        return f"1 thread, {_plural(messages_count, 'message')}"

    evidence_refs = _email_thread_evidence_refs(email_thread)
    if evidence_refs:
        return _plural(len(evidence_refs), "ref")

    return "1 thread"


def _email_thread_triage_category(email_thread: EmailThreadState) -> str:
    return email_thread.triage_category or EMAIL_TRIAGE_CATEGORY_UNKNOWN


def _email_thread_action_type(email_thread: EmailThreadState) -> str:
    return email_thread.triage_action_type or EMAIL_TRIAGE_ACTION_REVIEW_OPTIONAL


def _email_thread_priority(email_thread: EmailThreadState) -> str:
    return email_thread.triage_priority or EMAIL_TRIAGE_PRIORITY_LOW


def _email_thread_visible_by_config(email_thread: EmailThreadState) -> bool:
    category = _email_thread_triage_category(email_thread)
    priority = _email_thread_priority(email_thread)
    show_in_digest = email_thread.show_in_digest is True

    if category in MARKETING_TRIAGE_CATEGORIES:
        return settings.email_digest_show_marketing is True
    if category in AUTOMATED_TRIAGE_CATEGORIES:
        return settings.email_digest_show_automated is True
    if not show_in_digest or priority == EMAIL_TRIAGE_PRIORITY_HIDDEN:
        return settings.email_digest_show_low_priority is True
    return True


def _email_thread_group_key_from_attention_result(
    result: AttentionTriageResult,
) -> str | None:
    if not result.show_in_digest:
        return None
    if result.attention_class == "requires_my_attention":
        return EMAIL_THREAD_GROUP_WORK_ACTIONS
    if result.attention_class == "manual_action":
        return EMAIL_THREAD_GROUP_MANUAL_ACTIONS
    if result.attention_class == "waiting_on_external":
        return EMAIL_THREAD_GROUP_WAITING_EXTERNAL_REPLY
    if result.attention_class == "important_info":
        return EMAIL_THREAD_GROUP_WORK_INFO
    if result.attention_class == "review_optional":
        return EMAIL_THREAD_GROUP_REVIEW_OPTIONAL
    if result.attention_class == "no_action_required":
        return EMAIL_THREAD_GROUP_REVIEW_OPTIONAL
    return None


def _email_thread_action_type_from_attention_result(result: AttentionTriageResult) -> str:
    return {
        "requires_my_attention": EMAIL_TRIAGE_ACTION_REPLY_REQUIRED,
        "manual_action": EMAIL_TRIAGE_ACTION_MANUAL_ACTION_REQUIRED,
        "waiting_on_external": EMAIL_TRIAGE_ACTION_WAITING_EXTERNAL_REPLY,
        "important_info": EMAIL_TRIAGE_ACTION_REVIEW_OPTIONAL,
        "review_optional": EMAIL_TRIAGE_ACTION_REVIEW_OPTIONAL,
        "no_action_required": EMAIL_TRIAGE_ACTION_NO_ACTION_REQUIRED,
    }[result.attention_class]


def _hidden_email_category_label(email_thread: EmailThreadState) -> str:
    category = _email_thread_triage_category(email_thread)
    return HIDDEN_EMAIL_CATEGORY_LABELS.get(
        category,
        f"{category.replace('_', ' ')} emails",
    )


def _safe_metadata_text(value: Any, *, fallback: str) -> str:
    if not isinstance(value, str):
        return fallback

    cleaned = " ".join(value.strip().split())
    return cleaned or fallback


def _safe_metadata_list_text(value: Any, *, fallback: str) -> str:
    if isinstance(value, list):
        cleaned = [
            " ".join(str(item).strip().split())
            for item in value
            if str(item).strip()
        ]
        if cleaned:
            return ", ".join(dict.fromkeys(cleaned))

    return fallback


def _participants_display(email_thread: EmailThreadState) -> str:
    metadata = email_thread.metadata_json if isinstance(email_thread.metadata_json, dict) else {}
    metadata_display = _safe_metadata_text(
        metadata.get("participants_display"),
        fallback="",
    )
    if metadata_display:
        return metadata_display

    participants = email_thread.participants_json if isinstance(email_thread.participants_json, list) else []
    if not participants:
        return "unknown participant"

    includes_me = any(
        isinstance(participant, dict) and participant.get("is_me") is True
        for participant in participants
    )
    external_count = sum(
        1
        for participant in participants
        if isinstance(participant, dict) and participant.get("is_me") is not True
    )
    parts = []
    if includes_me:
        parts.append("me")
    if external_count == 1:
        parts.append("1 external participant")
    elif external_count > 1:
        parts.append(f"{external_count} external participants")

    return ", ".join(parts) if parts else "unknown participant"


def _last_message_from_display(email_thread: EmailThreadState) -> str:
    metadata = email_thread.metadata_json if isinstance(email_thread.metadata_json, dict) else {}
    metadata_display = _safe_metadata_text(
        metadata.get("last_message_from_display"),
        fallback="",
    )
    if metadata_display:
        return metadata_display

    if email_thread.last_message_direction == "from_me":
        return "me"
    if email_thread.last_message_direction == "from_external":
        return "external sender"
    return "unknown sender"


def _last_message_to_display(email_thread: EmailThreadState) -> str:
    metadata = email_thread.metadata_json if isinstance(email_thread.metadata_json, dict) else {}
    return _safe_metadata_list_text(
        metadata.get("last_message_to_display"),
        fallback="unknown recipient",
    )


def _email_thread_digest_item(
    email_thread: EmailThreadState,
    *,
    attention_result: AttentionTriageResult,
    generated_at: datetime,
    debug_evidence: bool,
    debug_triage: bool,
) -> dict[str, Any]:
    item = {
        "subject": email_thread.subject_display
        or email_thread.subject_normalized
        or "Subject unavailable",
        "status": email_thread.status,
        "attention_class": attention_result.attention_class,
        "category": _email_thread_triage_category(email_thread),
        "action_type": _email_thread_action_type_from_attention_result(attention_result),
        "priority": attention_result.priority,
        "show_in_digest": attention_result.show_in_digest,
        "recommended_action": attention_result.recommended_action,
        "last_message_at": _iso_datetime(email_thread.last_message_at),
        "last_message_from": _last_message_from_display(email_thread),
        "last_message_to": _last_message_to_display(email_thread),
        "last_message_direction": email_thread.last_message_direction,
        "participants": _participants_display(email_thread),
        "days_without_reply": _days_without_reply(email_thread.last_message_at, generated_at),
        "messages_count": email_thread.messages_count,
        "summary": email_thread.thread_summary
        or email_thread.last_message_summary
        or "Summary unavailable",
        "last_message_summary": email_thread.last_message_summary or "Summary unavailable",
        "evidence": _email_thread_evidence_summary(email_thread),
    }
    if debug_evidence:
        item["evidence_refs"] = _email_thread_evidence_refs(email_thread)
    if debug_triage:
        item["triage"] = {
            "category": _email_thread_triage_category(email_thread),
            "action_type": _email_thread_action_type(email_thread),
            "priority": _email_thread_priority(email_thread),
            "show_in_digest": email_thread.show_in_digest is True,
            "reason": email_thread.triage_reason,
            "confidence": email_thread.triage_confidence,
            "attention_class": attention_result.attention_class,
            "attention_priority": attention_result.priority,
            "attention_show_in_digest": attention_result.show_in_digest,
            "attention_reason": attention_result.reason,
            "attention_confidence": attention_result.confidence,
            "recommended_action": attention_result.recommended_action,
        }

    return item


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
            "by_category": {},
            "by_action_type": {},
            "by_priority": {},
            "by_show_in_digest": {},
        },
        "groups": {
            EMAIL_THREAD_GROUP_WORK_ACTIONS: [],
            EMAIL_THREAD_GROUP_MANUAL_ACTIONS: [],
            EMAIL_THREAD_GROUP_WAITING_EXTERNAL_REPLY: [],
            EMAIL_THREAD_GROUP_WORK_INFO: [],
            EMAIL_THREAD_GROUP_REVIEW_OPTIONAL: [],
        },
        "hidden_low_priority_summary": {
            "total": 0,
            "counts": {},
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
    generated_at: datetime,
    debug_evidence: bool,
    debug_triage: bool,
) -> dict[str, Any]:
    action_priority = case(
        (EmailThreadState.triage_action_type == EMAIL_TRIAGE_ACTION_REPLY_REQUIRED, 0),
        (
            EmailThreadState.triage_action_type
            == EMAIL_TRIAGE_ACTION_MANUAL_ACTION_REQUIRED,
            1,
        ),
        (
            EmailThreadState.triage_action_type
            == EMAIL_TRIAGE_ACTION_WAITING_EXTERNAL_REPLY,
            2,
        ),
        (EmailThreadState.triage_category == EMAIL_TRIAGE_CATEGORY_WORK_INFO, 3),
        (EmailThreadState.triage_action_type == EMAIL_TRIAGE_ACTION_REVIEW_OPTIONAL, 4),
        else_=5,
    )
    priority_rank = case(
        (EmailThreadState.triage_priority == EMAIL_TRIAGE_PRIORITY_HIGH, 0),
        (EmailThreadState.triage_priority == EMAIL_TRIAGE_PRIORITY_MEDIUM, 1),
        (EmailThreadState.triage_priority == EMAIL_TRIAGE_PRIORITY_LOW, 2),
        else_=3,
    )

    try:
        rows = list(
            (
                await session.execute(
                    select(EmailThreadState)
                    .where(EmailThreadState.source == "gmail")
                    .where(EmailThreadState.last_message_at >= start_at)
                    .where(EmailThreadState.last_message_at < end_at)
                    .order_by(
                        action_priority,
                        priority_rank,
                        desc(EmailThreadState.days_without_reply),
                        desc(EmailThreadState.last_message_at),
                        desc(EmailThreadState.id),
                    )
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

    groups: dict[str, list[dict[str, Any]]] = {group_key: [] for group_key in EMAIL_THREAD_GROUPS}
    hidden_counts: Counter[str] = Counter()
    for row in rows:
        attention_result = email_thread_state_to_attention_result_for_digest(
            row,
            settings=settings,
        )
        group_key = _email_thread_group_key_from_attention_result(attention_result)
        if group_key is None:
            hidden_counts[_hidden_email_category_label(row)] += 1
            continue

        groups[group_key].append(
            _email_thread_digest_item(
                row,
                attention_result=attention_result,
                generated_at=generated_at,
                debug_evidence=debug_evidence,
                debug_triage=debug_triage,
            )
        )

    active_count = sum(
        len(groups[group_key])
        for group_key in (
            EMAIL_THREAD_GROUP_WORK_ACTIONS,
            EMAIL_THREAD_GROUP_MANUAL_ACTIONS,
            EMAIL_THREAD_GROUP_WAITING_EXTERNAL_REPLY,
        )
    )
    by_status = dict(Counter(row.status for row in rows if row.status))
    by_category = dict(Counter(_email_thread_triage_category(row) for row in rows))
    by_action_type = dict(Counter(_email_thread_action_type(row) for row in rows))
    by_priority = dict(Counter(_email_thread_priority(row) for row in rows))
    by_show_in_digest = dict(
        Counter(str(row.show_in_digest is True).lower() for row in rows)
    )

    for group_key, items in groups.items():
        per_group_limit = (
            DEFAULT_INFORMATIONAL_EMAIL_THREAD_LIMIT
            if group_key
            in (
                EMAIL_THREAD_GROUP_WORK_INFO,
                EMAIL_THREAD_GROUP_REVIEW_OPTIONAL,
            )
            else limit
        )
        groups[group_key] = sorted(
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
            "by_category": by_category,
            "by_action_type": by_action_type,
            "by_priority": by_priority,
            "by_show_in_digest": by_show_in_digest,
        },
        "groups": groups,
        "hidden_low_priority_summary": {
            "total": sum(hidden_counts.values()),
            "counts": dict(sorted(hidden_counts.items())),
        },
        "data_quality_notes": [
            "Raw Gmail source events are summarized in counts because EmailThreadState rows are available."
        ],
        "metadata": {
            "source_model": "email_thread_states",
            "group_limit": limit,
            "informational_limit": DEFAULT_INFORMATIONAL_EMAIL_THREAD_LIMIT,
            "raw_gmail_entries_suppressed": True,
            "debug_triage": debug_triage,
        },
    }


def _digest_entry(
    source_event: SourceEvent,
    *,
    seen_count: int,
    debug_evidence: bool,
) -> dict[str, Any]:
    entry = {
        "source_event_id": source_event.source_event_id,
        "source_system": source_event.source_system,
        "source_object_type": source_event.source_object_type,
        "source_object_id": source_event.source_object_id,
        "event_type": source_event.event_type,
        "event_time": _iso_datetime(_activity_time(source_event)),
        "actor_external_id": source_event.actor_external_id,
        "title": source_event.title,
        "source_url": source_event.source_url,
        "evidence": _source_event_evidence_summary(seen_count),
        "seen_count": seen_count,
    }
    if seen_count > 1:
        entry["repeated_count"] = seen_count
    if debug_evidence:
        entry["evidence_refs"] = _source_event_evidence_refs(source_event)

    return entry


def _stable_source_event_object_key(source_event: SourceEvent) -> str:
    for value in (
        source_event.source_object_id,
        source_event.raw_object_ref,
        source_event.source_event_key,
        source_event.source_event_id,
    ):
        if value:
            return str(value)

    return "unknown"


def _source_event_dedupe_key(source_event: SourceEvent) -> tuple[str, str, str, str]:
    return (
        str(source_event.source_system),
        str(source_event.source_object_type),
        _stable_source_event_object_key(source_event),
        str(source_event.event_type),
    )


def _contains_mock_marker(value: Any) -> bool:
    if not isinstance(value, str):
        return False

    lowered = value.casefold()
    return (
        "example.invalid" in lowered
        or "mock" in lowered
        or "fixture" in lowered
        or "sample" in lowered
    )


def _is_mock_or_example_source_event(source_event: SourceEvent) -> bool:
    metadata = source_event.metadata_json if isinstance(source_event.metadata_json, dict) else {}
    if metadata.get("mock") is True or metadata.get("fixture") is True:
        return True

    return any(
        _contains_mock_marker(value)
        for value in (
            source_event.source_system,
            source_event.event_type,
            source_event.source_event_key,
            source_event.title,
            source_event.source_url,
            source_event.raw_object_ref,
        )
    )


def _dedupe_source_event_groups(
    source_events: Sequence[SourceEvent],
) -> tuple[list[tuple[SourceEvent, int]], int]:
    grouped: dict[tuple[str, str, str, str], tuple[SourceEvent, int]] = {}
    hidden_mock_example_count = 0

    for source_event in source_events:
        if _is_mock_or_example_source_event(source_event):
            hidden_mock_example_count += 1
            continue

        key = _source_event_dedupe_key(source_event)
        if key not in grouped:
            grouped[key] = (source_event, 1)
            continue

        first_event, count = grouped[key]
        grouped[key] = (first_event, count + 1)

    return list(grouped.values()), hidden_mock_example_count


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


def _has_email_thread_rows(email_thread_intelligence: dict[str, Any]) -> bool:
    counts = email_thread_intelligence.get("counts")
    if not isinstance(counts, dict):
        return False
    try:
        return int(counts.get("total", 0)) > 0
    except (TypeError, ValueError):
        return False


async def build_source_activity_digest(
    *,
    start_at: datetime,
    end_at: datetime,
    limit: int = DEFAULT_DIGEST_ENTRY_LIMIT,
    generated_at: datetime | None = None,
    debug_evidence: bool | None = None,
    debug_triage: bool | None = None,
) -> dict[str, Any]:
    """Build a deterministic digest of persisted source activity for a time window.

    This digest reads stored SourceEvent rows only. It does not call LLMs, infer
    tasks/risks/decisions, fetch connector data, or mutate source data.
    """

    _require_aware_datetime(start_at, field_name="start_at")
    _require_aware_datetime(end_at, field_name="end_at")
    safe_generated_at = generated_at or datetime.now(timezone.utc)
    _require_aware_datetime(safe_generated_at, field_name="generated_at")
    effective_debug_evidence = bool(debug_evidence) or settings.email_digest_debug_evidence
    effective_debug_triage = bool(debug_triage) or settings.email_digest_debug_triage

    if end_at <= start_at:
        raise ValueError("end_at must be after start_at")

    safe_limit = _safe_limit(limit)
    source_event_scan_limit = safe_limit * SOURCE_EVENT_DEDUPE_SCAN_MULTIPLIER
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
                    .limit(source_event_scan_limit)
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
            generated_at=safe_generated_at,
            debug_evidence=effective_debug_evidence,
            debug_triage=effective_debug_triage,
        )

    visible_source_events = _visible_source_events(
        source_events,
        email_thread_intelligence=email_thread_intelligence,
    )
    source_event_groups, hidden_mock_example_count = _dedupe_source_event_groups(
        visible_source_events
    )
    limited_source_event_groups = source_event_groups[:safe_limit]
    entries = [
        _digest_entry(
            source_event,
            seen_count=seen_count,
            debug_evidence=effective_debug_evidence,
        )
        for source_event, seen_count in limited_source_event_groups
    ]
    duplicate_source_events_collapsed = any(
        seen_count > 1 for _source_event, seen_count in source_event_groups
    )
    source_event_data_quality_notes = []
    if hidden_mock_example_count:
        source_event_data_quality_notes.append(
            f"Hidden {hidden_mock_example_count} mock/example source events from production activity."
        )

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
            "generated_at": safe_generated_at.isoformat(),
            "entry_limit": safe_limit,
            "entry_count": len(entries),
            "truncated": total_count > len(source_events)
            or len(source_event_groups) > len(limited_source_event_groups),
            "source_model": "source_events",
            "debug_evidence": effective_debug_evidence,
            "debug_triage": effective_debug_triage,
            "llm_used": False,
            "source_event_scan_limit": source_event_scan_limit,
            "source_event_scan_count": len(source_events),
            "duplicate_source_events_collapsed": duplicate_source_events_collapsed,
        },
        "source_event_data_quality": {
            "hidden_mock_example_event_count": hidden_mock_example_count,
            "notes": source_event_data_quality_notes,
        },
    }

    if (
        has_gmail_source_activity
        or _has_email_thread_items(email_thread_intelligence)
        or _has_email_thread_rows(email_thread_intelligence)
    ):
        digest["email_thread_intelligence"] = email_thread_intelligence

    return digest
