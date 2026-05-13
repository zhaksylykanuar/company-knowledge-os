from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

SAFE_EVIDENCE_REF_KEYS = (
    "kind",
    "source_event_id",
    "event_id",
    "source_system",
    "source_object_type",
    "source_object_id",
    "event_type",
    "raw_object_ref",
    "source_document_id",
    "chunk_id",
    "message_id",
)

EMAIL_THREAD_GROUP_LABELS = (
    ("needs_my_reply", "Needs my reply"),
    ("waiting_for_external_reply", "Waiting for external reply"),
    ("informational", "Informational"),
)

EMAIL_THREAD_STATUS_LABELS = {
    "needs_my_reply": "Needs my reply",
    "waiting_for_external_reply": "Waiting for external reply",
    "informational": "Informational",
    "resolved": "Resolved",
}


def _string_value(value: Any, *, fallback: str = "unknown") -> str:
    if value is None:
        return fallback

    text = str(value).strip()
    return text or fallback


def _mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value

    return {}


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, str):
        return value

    return []


def _count_items(value: Any) -> list[tuple[str, Any]]:
    counts = _mapping(value)
    return sorted(
        ((str(key), count) for key, count in counts.items()),
        key=lambda item: item[0],
    )


def _append_count_section(lines: list[str], title: str, value: Any) -> None:
    items = _count_items(value)
    if not items:
        return

    lines.append(f"{title}:")
    for key, count in items:
        lines.append(f"- {key}: {count}")


def _format_evidence_ref(value: Any) -> str | None:
    evidence_ref = _mapping(value)
    if not evidence_ref:
        return None

    parts = [
        f"{key}={evidence_ref[key]}"
        for key in SAFE_EVIDENCE_REF_KEYS
        if evidence_ref.get(key) is not None
    ]
    if not parts:
        return None

    return "; ".join(parts)


def _format_evidence_refs(value: Any) -> str:
    refs = [
        rendered
        for rendered in (_format_evidence_ref(ref) for ref in _sequence(value))
        if rendered is not None
    ]
    if not refs:
        return "none"

    return " | ".join(refs)


def _format_evidence_summary(value: Any, *, fallback: str = "Evidence unavailable") -> str:
    text = _string_value(value, fallback="")
    return text if text else fallback


def _format_seen_count(value: Any) -> str | None:
    try:
        seen_count = int(value)
    except (TypeError, ValueError):
        return None

    if seen_count <= 1:
        return None

    return f"Seen {seen_count} times"


def _format_entry(value: Any, index: int, *, debug_evidence: bool) -> list[str]:
    entry = _mapping(value)
    event_time = _string_value(entry.get("event_time"))
    source_system = _string_value(entry.get("source_system"))
    source_object_type = _string_value(entry.get("source_object_type"))
    event_type = _string_value(entry.get("event_type"))
    title = _string_value(entry.get("title"), fallback="untitled")

    lines = [
        f"{index}. {event_time} | {source_system}/{source_object_type} | {event_type}",
        f"   Title: {title}",
        f"   Evidence: {_format_evidence_summary(entry.get('evidence'))}",
    ]
    seen_note = _format_seen_count(entry.get("seen_count"))
    if seen_note:
        lines.append(f"   {seen_note}")

    if debug_evidence:
        source_event_id = _string_value(entry.get("source_event_id"))
        source_object_id = _string_value(entry.get("source_object_id"))
        source_url = _string_value(entry.get("source_url"), fallback="")
        lines.append(f"   Source event: {source_event_id}")
        lines.append(f"   Source object: {source_object_id}")
        if source_url:
            lines.append(f"   Source URL: {source_url}")
        lines.append(
            f"   Debug evidence refs: {_format_evidence_refs(entry.get('evidence_refs'))}"
        )

    return lines


def _email_thread_groups(value: Any) -> Mapping[str, Any]:
    email_thread_intelligence = _mapping(value)
    return _mapping(email_thread_intelligence.get("groups"))


def _has_email_thread_items(value: Any) -> bool:
    groups = _email_thread_groups(value)
    return any(_sequence(groups.get(group_key)) for group_key, _label in EMAIL_THREAD_GROUP_LABELS)


def _format_status(value: Any) -> str:
    status = _string_value(value, fallback="informational")
    return EMAIL_THREAD_STATUS_LABELS.get(status, status.replace("_", " ").title())


def _format_days(value: Any) -> str:
    try:
        days = int(value)
    except (TypeError, ValueError):
        return "unknown"

    if days == 1:
        return "1 day"
    return f"{days} days"


def _format_email_thread_item(
    value: Any,
    index: int,
    *,
    debug_evidence: bool,
) -> list[str]:
    item = _mapping(value)
    subject = _string_value(item.get("subject"), fallback="Subject unavailable")
    last_message_at = _string_value(item.get("last_message_at"))
    status = _format_status(item.get("status"))
    status_key = _string_value(item.get("status"), fallback="informational")
    last_message_from = _string_value(item.get("last_message_from"), fallback="unknown sender")
    last_message_to = _string_value(item.get("last_message_to"), fallback="unknown recipient")
    participants = _string_value(item.get("participants"), fallback="unknown participant")
    summary = _string_value(item.get("summary"), fallback="Summary unavailable")
    last_message_summary = _string_value(
        item.get("last_message_summary"),
        fallback="Summary unavailable",
    )
    days_without_reply = _format_days(item.get("days_without_reply"))

    wait_label = "Waiting for external reply"
    if status_key == "needs_my_reply":
        wait_label = "Not answered for"

    lines = [
        f"{index}. Subject: {subject}",
        f"   Status: {status}",
        f"   Last message: {last_message_at} from {last_message_from}",
        f"   Last message to: {last_message_to}",
        f"   Participants: {participants}",
        f"   {wait_label}: {days_without_reply}",
        f"   Summary: {summary}",
        f"   Last message summary: {last_message_summary}",
        f"   Evidence: {_format_evidence_summary(item.get('evidence'))}",
    ]
    if debug_evidence:
        lines.append(
            f"   Debug evidence refs: {_format_evidence_refs(item.get('evidence_refs'))}"
        )

    return lines


def _append_email_thread_section(
    lines: list[str],
    value: Any,
    *,
    debug_evidence: bool,
) -> None:
    email_thread_intelligence = _mapping(value)
    groups = _email_thread_groups(email_thread_intelligence)
    if not _has_email_thread_items(email_thread_intelligence):
        for note in _sequence(email_thread_intelligence.get("data_quality_notes")):
            lines.append(f"Email thread data quality note: {_string_value(note)}")
        return

    lines.append(
        _string_value(
            email_thread_intelligence.get("section_title"),
            fallback="Email threads requiring attention",
        )
    )
    for group_key, label in EMAIL_THREAD_GROUP_LABELS:
        items = _sequence(groups.get(group_key))
        if not items:
            continue
        lines.append(f"{label}:")
        for index, item in enumerate(items, start=1):
            lines.extend(
                _format_email_thread_item(
                    item,
                    index,
                    debug_evidence=debug_evidence,
                )
            )

    for note in _sequence(email_thread_intelligence.get("data_quality_notes")):
        lines.append(f"Email thread data quality note: {_string_value(note)}")


def _append_source_event_data_quality_section(lines: list[str], value: Any) -> None:
    source_event_data_quality = _mapping(value)
    for note in _sequence(source_event_data_quality.get("notes")):
        lines.append(f"Source event data quality note: {_string_value(note)}")


def render_source_activity_digest_text(
    digest: Mapping[str, Any],
    *,
    debug_evidence: bool = False,
) -> str:
    """Render a source activity digest as deterministic plain text.

    The renderer formats an existing digest dict only. It does not call the
    database, API layer, LLMs, connectors, or infer source meaning.
    """

    window = _mapping(digest.get("window"))
    counts = _mapping(digest.get("counts"))
    email_thread_intelligence = _mapping(digest.get("email_thread_intelligence"))
    entries = _sequence(digest.get("entries"))
    metadata = _mapping(digest.get("metadata"))
    source_event_data_quality = _mapping(digest.get("source_event_data_quality"))
    effective_debug_evidence = debug_evidence or metadata.get("debug_evidence") is True

    lines = [
        "Source activity digest",
        f"Generated at: {_string_value(metadata.get('generated_at'))}",
        f"Window: {_string_value(window.get('start_at'))} to {_string_value(window.get('end_at'))}",
        f"Total events: {_string_value(counts.get('total'), fallback='0')}",
    ]

    _append_count_section(lines, "Source systems", counts.get("by_source_system"))
    _append_count_section(lines, "Event types", counts.get("by_event_type"))
    _append_count_section(lines, "Source object types", counts.get("by_source_object_type"))
    _append_source_event_data_quality_section(lines, source_event_data_quality)
    _append_email_thread_section(
        lines,
        email_thread_intelligence,
        debug_evidence=effective_debug_evidence,
    )

    entry_count = _string_value(metadata.get("entry_count"), fallback=str(len(entries)))
    entry_limit = _string_value(metadata.get("entry_limit"), fallback="unknown")
    truncated = metadata.get("truncated") is True

    if entries:
        lines.append(f"Entries: {entry_count} shown, limit {entry_limit}")
        if truncated:
            lines.append("Entries are truncated by the digest limit.")
        for index, entry in enumerate(entries, start=1):
            lines.extend(
                _format_entry(
                    entry,
                    index,
                    debug_evidence=effective_debug_evidence,
                )
            )
    else:
        lines.append("Entries: none")
        lines.append("No source activity found for this window.")

    lines.append(
        "This digest is source activity only; it does not infer decisions, tasks, or risks."
    )

    return "\n".join(lines)
