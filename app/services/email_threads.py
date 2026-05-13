from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import getaddresses, parsedate_to_datetime
from hashlib import sha256
from typing import Any, Iterable

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.base import AsyncSessionLocal
from app.db.gmail_models import EmailThreadState, GmailMessage
from app.db.source_models import SourceDocument

EMAIL_SOURCE_GMAIL = "gmail"

THREAD_STATUS_NEEDS_MY_REPLY = "needs_my_reply"
THREAD_STATUS_WAITING_FOR_EXTERNAL_REPLY = "waiting_for_external_reply"
THREAD_STATUS_RESOLVED = "resolved"
THREAD_STATUS_INFORMATIONAL = "informational"

MESSAGE_DIRECTION_FROM_ME = "from_me"
MESSAGE_DIRECTION_FROM_EXTERNAL = "from_external"
MESSAGE_DIRECTION_UNKNOWN = "unknown"

SUMMARY_UNAVAILABLE = "Summary unavailable from stored metadata."
SUMMARY_PREVIEW_MAX_CHARS = 180

_SUBJECT_PREFIX_RE = re.compile(r"^\s*(?:(?:re|fw|fwd)(?:\[\d+\])?\s*:\s*)+", re.IGNORECASE)
_MESSAGE_ID_RE = re.compile(r"<([^>]+)>")
_SYSTEM_LOCAL_PARTS = {
    "no-reply",
    "noreply",
    "do-not-reply",
    "donotreply",
    "notification",
    "notifications",
}


@dataclass(frozen=True)
class EmailMessageSnapshot:
    message_id: str
    provider_thread_id: str | None
    subject: str | None
    from_address: str | None
    to_addresses: tuple[str, ...]
    cc_addresses: tuple[str, ...]
    message_at: datetime | None
    raw_object_ref: str | None
    source_document_id: str | None
    message_id_header: str | None
    in_reply_to: tuple[str, ...]
    references: tuple[str, ...]
    label_ids: tuple[str, ...]
    snippet: str | None = None
    body_preview: str | None = None


@dataclass(frozen=True)
class EmailThreadStateCandidate:
    source: str
    thread_key: str
    provider_thread_id: str | None
    subject_normalized: str | None
    subject_display: str | None
    participants_json: list[dict[str, Any]]
    first_message_at: datetime | None
    last_message_at: datetime | None
    last_message_from: str | None
    last_message_direction: str
    last_message_summary: str
    thread_summary: str
    status: str
    days_without_reply: int | None
    messages_count: int
    evidence_refs: list[dict[str, Any]]
    metadata_json: dict[str, Any]
    computed_at: datetime


@dataclass(frozen=True)
class EmailThreadRebuildResult:
    thread_states_built: int
    messages_considered: int
    status_counts: dict[str, int]


@dataclass
class _ThreadGroup:
    key: str
    provider_thread_id: str | None
    grouping_strategy: str
    messages: list[EmailMessageSnapshot]


class _UnionFind:
    def __init__(self, values: Iterable[str]) -> None:
        self.parent = {value: value for value in values}

    def find(self, value: str) -> str:
        parent = self.parent[value]
        if parent != value:
            self.parent[value] = self.find(parent)
        return self.parent[value]

    def union(self, left: str, right: str) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root != right_root:
            self.parent[right_root] = left_root


def _clean_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.strip().split())
    return cleaned or None


def _short_preview(value: Any, *, max_chars: int = SUMMARY_PREVIEW_MAX_CHARS) -> str | None:
    cleaned = _clean_string(value)
    if cleaned is None:
        return None

    if len(cleaned) <= max_chars:
        return cleaned

    truncated = cleaned[: max_chars - 3].rstrip()
    return f"{truncated}..."


def _hash_value(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()[:32]


def normalize_email_subject(subject: str | None) -> str:
    cleaned = _clean_string(subject)
    if cleaned is None:
        return ""

    previous = None
    current = cleaned
    while previous != current:
        previous = current
        current = _SUBJECT_PREFIX_RE.sub("", current).strip()

    return " ".join(current.casefold().split())


def normalize_email_address(value: str | None) -> str | None:
    cleaned = _clean_string(value)
    if cleaned is None:
        return None

    parsed = getaddresses([cleaned])
    if parsed:
        address = parsed[0][1] or parsed[0][0]
    else:
        address = cleaned

    address = address.strip().strip("<>").casefold()
    return address or None


def parse_email_addresses(value: Any) -> tuple[str, ...]:
    if isinstance(value, list):
        raw = ",".join(str(item) for item in value)
    elif isinstance(value, str):
        raw = value
    else:
        return ()

    addresses = []
    for _display, address in getaddresses([raw.replace(";", ",")]):
        normalized = normalize_email_address(address)
        if normalized:
            addresses.append(normalized)

    return tuple(dict.fromkeys(addresses))


def parse_email_me_addresses(value: str | None = None) -> set[str]:
    configured = settings.email_me_addresses if value is None else value
    return set(parse_email_addresses(configured))


def _participant_key(address: str) -> str:
    return f"addr_{_hash_value(address)[:16]}"


def _participant_domain(address: str) -> str | None:
    if "@" not in address:
        return None
    domain = address.rsplit("@", 1)[1].strip().casefold()
    return domain or None


def _participant_addresses(message: EmailMessageSnapshot) -> set[str]:
    values = [message.from_address, *message.to_addresses, *message.cc_addresses]
    return {address for address in values if address}


def _participants_json(
    messages: list[EmailMessageSnapshot],
    *,
    me_addresses: set[str],
) -> list[dict[str, Any]]:
    participants = sorted(
        {
            address
            for message in messages
            for address in _participant_addresses(message)
        }
    )
    return [
        {
            "participant_key": _participant_key(address),
            "domain": _participant_domain(address),
            "is_me": address in me_addresses,
        }
        for address in participants
    ]


def _parse_message_id_refs(value: Any) -> tuple[str, ...]:
    if isinstance(value, list):
        raw = " ".join(str(item) for item in value)
    elif isinstance(value, str):
        raw = value
    else:
        return ()

    found = [match.casefold() for match in _MESSAGE_ID_RE.findall(raw)]
    if not found:
        found = [part.strip("<>,").casefold() for part in raw.split()]

    return tuple(dict.fromkeys(part for part in found if part))


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, (int, float)):
        timestamp = float(value)
        if timestamp > 10_000_000_000:
            timestamp = timestamp / 1000
        parsed = datetime.fromtimestamp(timestamp, timezone.utc)
    elif isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return None
        if cleaned.isdigit():
            return _parse_datetime(int(cleaned))
        try:
            parsed = datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
        except ValueError:
            try:
                parsed = parsedate_to_datetime(cleaned)
            except (TypeError, ValueError, IndexError, OverflowError):
                return None
    else:
        return None

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _message_sort_key(message: EmailMessageSnapshot) -> tuple[str, str]:
    message_at = message.message_at.isoformat() if message.message_at else ""
    return (message_at, message.message_id)


def compute_thread_key(message: EmailMessageSnapshot) -> str:
    if message.provider_thread_id:
        return f"gmail:thread:{_hash_value(message.provider_thread_id)}"

    if message.message_id_header:
        return f"gmail:message-header:{_hash_value(message.message_id_header)}"

    subject = normalize_email_subject(message.subject)
    participants = ",".join(sorted(_participant_addresses(message)))
    fallback_key = f"{subject}:{participants}:{message.message_id}"
    return f"gmail:subject-participants:{_hash_value(fallback_key)}"


def classify_thread_status(
    last_message_direction: str,
    *,
    informational: bool = False,
) -> str:
    if informational or last_message_direction == MESSAGE_DIRECTION_UNKNOWN:
        return THREAD_STATUS_INFORMATIONAL
    if last_message_direction == MESSAGE_DIRECTION_FROM_EXTERNAL:
        return THREAD_STATUS_NEEDS_MY_REPLY
    if last_message_direction == MESSAGE_DIRECTION_FROM_ME:
        return THREAD_STATUS_WAITING_FOR_EXTERNAL_REPLY
    return THREAD_STATUS_INFORMATIONAL


def compute_days_without_reply(last_message_at: datetime | None, now: datetime) -> int | None:
    if last_message_at is None:
        return None

    safe_now = _parse_datetime(now) or datetime.now(timezone.utc)
    safe_last = _parse_datetime(last_message_at)
    if safe_last is None:
        return None

    seconds = (safe_now - safe_last).total_seconds()
    if seconds < 0:
        return 0
    return int(seconds // 86_400)


def _last_message_direction(
    message: EmailMessageSnapshot,
    *,
    me_addresses: set[str],
) -> str:
    if not me_addresses or not message.from_address:
        return MESSAGE_DIRECTION_UNKNOWN
    if message.from_address in me_addresses:
        return MESSAGE_DIRECTION_FROM_ME
    return MESSAGE_DIRECTION_FROM_EXTERNAL


def _looks_informational(message: EmailMessageSnapshot) -> bool:
    from_address = message.from_address or ""
    local_part = from_address.split("@", 1)[0].casefold()
    return local_part in _SYSTEM_LOCAL_PARTS


def _subject_display(messages: list[EmailMessageSnapshot]) -> str | None:
    for message in sorted(messages, key=_message_sort_key):
        subject = _clean_string(message.subject)
        if subject:
            return subject
    return None


def _thread_evidence_refs(messages: list[EmailMessageSnapshot]) -> list[dict[str, Any]]:
    evidence_refs: list[dict[str, Any]] = []

    for message in sorted(messages, key=_message_sort_key):
        ref: dict[str, Any] = {
            "kind": "gmail_message",
            "source_system": EMAIL_SOURCE_GMAIL,
            "message_id": message.message_id,
        }
        if message.raw_object_ref:
            ref["raw_object_ref"] = message.raw_object_ref
        if message.source_document_id:
            ref["source_document_id"] = message.source_document_id
        evidence_refs.append(ref)

    return evidence_refs


def _sender_display(direction: str) -> str:
    if direction == MESSAGE_DIRECTION_FROM_ME:
        return "me"
    if direction == MESSAGE_DIRECTION_FROM_EXTERNAL:
        return "external sender"
    return "unknown sender"


def _recipient_display_labels(
    message: EmailMessageSnapshot,
    *,
    me_addresses: set[str],
) -> list[str]:
    labels: list[str] = []
    for address in (*message.to_addresses, *message.cc_addresses):
        if address in me_addresses:
            labels.append("me")
        else:
            labels.append("external participant")

    return list(dict.fromkeys(labels))


def _participants_display(
    messages: list[EmailMessageSnapshot],
    *,
    me_addresses: set[str],
) -> str:
    participants = {
        address
        for message in messages
        for address in _participant_addresses(message)
    }
    if not participants:
        return "unknown participant"

    includes_me = any(address in me_addresses for address in participants)
    external_count = sum(1 for address in participants if address not in me_addresses)
    parts = []
    if includes_me:
        parts.append("me")
    if external_count == 1:
        parts.append("1 external participant")
    elif external_count > 1:
        parts.append(f"{external_count} external participants")

    return ", ".join(parts) if parts else "unknown participant"


def _message_summary(
    message: EmailMessageSnapshot,
    *,
    direction: str,
    subject_display: str | None,
) -> str:
    preview = _short_preview(message.snippet) or _short_preview(message.body_preview)
    if preview:
        return preview

    subject = _short_preview(subject_display, max_chars=120)
    sender = _sender_display(direction)
    if subject:
        return f"Latest message from {sender} about {subject}."

    return f"Latest message from {sender}."


def _thread_summary(
    messages: list[EmailMessageSnapshot],
    *,
    last_message_summary: str,
) -> str:
    messages_count = len(messages)
    if messages_count <= 1:
        return last_message_summary

    return _short_preview(
        f"{messages_count}-message thread. Latest: {last_message_summary}",
        max_chars=SUMMARY_PREVIEW_MAX_CHARS,
    ) or SUMMARY_UNAVAILABLE


def _build_thread_state_candidate(
    group: _ThreadGroup,
    *,
    me_addresses: set[str],
    now: datetime,
) -> EmailThreadStateCandidate:
    messages = sorted(group.messages, key=_message_sort_key)
    first_message = messages[0]
    last_message = messages[-1]
    last_direction = _last_message_direction(last_message, me_addresses=me_addresses)
    informational = _looks_informational(last_message)
    status = classify_thread_status(last_direction, informational=informational)
    subject_display = _subject_display(messages)
    subject_normalized = normalize_email_subject(subject_display)
    last_message_summary = _message_summary(
        last_message,
        direction=last_direction,
        subject_display=subject_display,
    )

    return EmailThreadStateCandidate(
        source=EMAIL_SOURCE_GMAIL,
        thread_key=group.key,
        provider_thread_id=group.provider_thread_id,
        subject_normalized=subject_normalized or None,
        subject_display=subject_display,
        participants_json=_participants_json(messages, me_addresses=me_addresses),
        first_message_at=first_message.message_at,
        last_message_at=last_message.message_at,
        last_message_from=(
            _participant_key(last_message.from_address) if last_message.from_address else None
        ),
        last_message_direction=last_direction,
        last_message_summary=last_message_summary,
        thread_summary=_thread_summary(messages, last_message_summary=last_message_summary),
        status=status,
        days_without_reply=compute_days_without_reply(last_message.message_at, now),
        messages_count=len(messages),
        evidence_refs=_thread_evidence_refs(messages),
        metadata_json={
            "grouping_strategy": group.grouping_strategy,
            "summary_uses_private_content": False,
            "summary_source": (
                "stored_preview"
                if last_message.snippet or last_message.body_preview
                else "subject_direction_fallback"
            ),
            "last_message_from_display": _sender_display(last_direction),
            "last_message_to_display": _recipient_display_labels(
                last_message,
                me_addresses=me_addresses,
            ),
            "participants_display": _participants_display(
                messages,
                me_addresses=me_addresses,
            ),
            "resolved_status_supported": True,
        },
        computed_at=now,
    )


def _group_by_provider_thread(
    messages: list[EmailMessageSnapshot],
) -> tuple[list[_ThreadGroup], list[EmailMessageSnapshot]]:
    grouped: dict[str, list[EmailMessageSnapshot]] = {}
    remaining: list[EmailMessageSnapshot] = []

    for message in messages:
        if message.provider_thread_id:
            grouped.setdefault(message.provider_thread_id, []).append(message)
        else:
            remaining.append(message)

    groups = [
        _ThreadGroup(
            key=f"gmail:thread:{_hash_value(provider_thread_id)}",
            provider_thread_id=provider_thread_id,
            grouping_strategy="gmail_thread_id",
            messages=group_messages,
        )
        for provider_thread_id, group_messages in sorted(grouped.items())
    ]

    return groups, remaining


def _group_by_message_headers(
    messages: list[EmailMessageSnapshot],
) -> tuple[list[_ThreadGroup], list[EmailMessageSnapshot]]:
    if not messages:
        return [], []

    ids = [message.message_id for message in messages]
    union_find = _UnionFind(ids)
    by_header_id = {
        message.message_id_header: message.message_id
        for message in messages
        if message.message_id_header
    }

    for message in messages:
        for ref in (*message.in_reply_to, *message.references):
            linked_message_id = by_header_id.get(ref)
            if linked_message_id:
                union_find.union(message.message_id, linked_message_id)

    by_root: dict[str, list[EmailMessageSnapshot]] = {}
    for message in messages:
        by_root.setdefault(union_find.find(message.message_id), []).append(message)

    groups: list[_ThreadGroup] = []
    remaining: list[EmailMessageSnapshot] = []
    for group_messages in by_root.values():
        if len(group_messages) < 2:
            remaining.extend(group_messages)
            continue

        header_ids = sorted(
            {
                message.message_id_header
                for message in group_messages
                if message.message_id_header
            }
        )
        if not header_ids:
            remaining.extend(group_messages)
            continue

        anchor = header_ids[0]
        groups.append(
            _ThreadGroup(
                key=f"gmail:message-headers:{_hash_value(anchor)}",
                provider_thread_id=None,
                grouping_strategy="message_headers",
                messages=group_messages,
            )
        )

    return sorted(groups, key=lambda group: group.key), remaining


def _subject_participant_group_key(
    subject_normalized: str,
    participants: set[str],
    messages: list[EmailMessageSnapshot],
) -> str:
    participant_part = ",".join(sorted(participants))
    message_anchor = sorted(message.message_id for message in messages)[0]
    digest = _hash_value(f"{subject_normalized}:{participant_part}:{message_anchor}")
    return f"gmail:subject-participants:{digest}"


def _group_by_subject_participants(
    messages: list[EmailMessageSnapshot],
) -> list[_ThreadGroup]:
    buckets: list[tuple[str, set[str], list[EmailMessageSnapshot]]] = []

    for message in sorted(messages, key=_message_sort_key):
        subject = normalize_email_subject(message.subject)
        participants = _participant_addresses(message)
        selected_index: int | None = None

        for index, (bucket_subject, bucket_participants, _bucket_messages) in enumerate(buckets):
            if bucket_subject != subject:
                continue
            if participants and bucket_participants and participants & bucket_participants:
                selected_index = index
                break

        if selected_index is None:
            buckets.append((subject, set(participants), [message]))
            continue

        bucket_subject, bucket_participants, bucket_messages = buckets[selected_index]
        bucket_participants.update(participants)
        bucket_messages.append(message)
        buckets[selected_index] = (bucket_subject, bucket_participants, bucket_messages)

    groups = []
    for subject, participants, bucket_messages in buckets:
        groups.append(
            _ThreadGroup(
                key=_subject_participant_group_key(subject, participants, bucket_messages),
                provider_thread_id=None,
                grouping_strategy="subject_participants",
                messages=bucket_messages,
            )
        )

    return groups


def group_gmail_messages_into_thread_candidates(
    messages: list[EmailMessageSnapshot],
) -> list[_ThreadGroup]:
    provider_groups, remaining = _group_by_provider_thread(messages)
    header_groups, remaining = _group_by_message_headers(remaining)
    fallback_groups = _group_by_subject_participants(remaining)
    return [*provider_groups, *header_groups, *fallback_groups]


def build_email_thread_state_candidates(
    messages: list[EmailMessageSnapshot],
    *,
    me_addresses: set[str] | None = None,
    now: datetime | None = None,
) -> list[EmailThreadStateCandidate]:
    safe_now = _parse_datetime(now) if now is not None else datetime.now(timezone.utc)
    if safe_now is None:
        safe_now = datetime.now(timezone.utc)

    me_address_set = me_addresses if me_addresses is not None else parse_email_me_addresses()
    groups = group_gmail_messages_into_thread_candidates(messages)
    return [
        _build_thread_state_candidate(group, me_addresses=me_address_set, now=safe_now)
        for group in sorted(groups, key=lambda item: item.key)
        if group.messages
    ]


def _metadata_for_message(
    message: GmailMessage,
    documents_by_message_id: dict[str, SourceDocument],
) -> dict[str, Any]:
    document = documents_by_message_id.get(message.message_id)
    if document is None or not isinstance(document.metadata_json, dict):
        return {}
    return document.metadata_json


def _payload_for_message(message: GmailMessage) -> dict[str, Any]:
    return message.payload if isinstance(message.payload, dict) else {}


def _value_from_sources(
    metadata: dict[str, Any],
    payload: dict[str, Any],
    *keys: str,
) -> Any:
    for key in keys:
        value = metadata.get(key)
        if value is not None:
            return value
        value = payload.get(key)
        if value is not None:
            return value
    return None


def _snapshot_from_gmail_message(
    message: GmailMessage,
    documents_by_message_id: dict[str, SourceDocument],
) -> EmailMessageSnapshot:
    metadata = _metadata_for_message(message, documents_by_message_id)
    payload = _payload_for_message(message)
    document = documents_by_message_id.get(message.message_id)
    label_ids = message.label_ids if isinstance(message.label_ids, list) else []
    message_at = _parse_datetime(
        _value_from_sources(metadata, payload, "date", "internalDate", "internal_date")
    ) or _parse_datetime(message.created_at)

    return EmailMessageSnapshot(
        message_id=message.message_id,
        provider_thread_id=message.thread_id or _clean_string(payload.get("threadId")),
        subject=_clean_string(_value_from_sources(metadata, payload, "subject", "title")),
        from_address=normalize_email_address(_value_from_sources(metadata, payload, "from")),
        to_addresses=parse_email_addresses(_value_from_sources(metadata, payload, "to")),
        cc_addresses=parse_email_addresses(_value_from_sources(metadata, payload, "cc")),
        message_at=message_at,
        raw_object_ref=message.raw_object_ref,
        source_document_id=document.source_document_id if document else None,
        message_id_header=(
            _parse_message_id_refs(_value_from_sources(metadata, payload, "message-id")) or (None,)
        )[0],
        in_reply_to=_parse_message_id_refs(
            _value_from_sources(metadata, payload, "in-reply-to", "in_reply_to")
        ),
        references=_parse_message_id_refs(_value_from_sources(metadata, payload, "references")),
        label_ids=tuple(str(item) for item in label_ids),
        snippet=_short_preview(
            message.snippet or _value_from_sources(metadata, payload, "snippet")
        ),
        body_preview=_short_preview(
            _value_from_sources(
                metadata,
                payload,
                "body_preview",
                "text_preview",
                "preview",
            )
        ),
    )


async def load_stored_gmail_message_snapshots(session: AsyncSession) -> list[EmailMessageSnapshot]:
    message_rows = list(
        (
            await session.execute(select(GmailMessage).order_by(GmailMessage.id))
        )
        .scalars()
        .all()
    )

    document_rows = list(
        (
            await session.execute(
                select(SourceDocument)
                .where(SourceDocument.source_system == EMAIL_SOURCE_GMAIL)
                .order_by(SourceDocument.created_at, SourceDocument.id)
            )
        )
        .scalars()
        .all()
    )
    documents_by_message_id = {
        document.source_object_id: document for document in document_rows
    }

    return [
        _snapshot_from_gmail_message(message, documents_by_message_id)
        for message in message_rows
    ]


def _thread_state_values(candidate: EmailThreadStateCandidate) -> dict[str, Any]:
    return {
        "source": candidate.source,
        "thread_key": candidate.thread_key,
        "provider_thread_id": candidate.provider_thread_id,
        "subject_normalized": candidate.subject_normalized,
        "subject_display": candidate.subject_display,
        "participants_json": candidate.participants_json,
        "first_message_at": candidate.first_message_at,
        "last_message_at": candidate.last_message_at,
        "last_message_from": candidate.last_message_from,
        "last_message_direction": candidate.last_message_direction,
        "last_message_summary": candidate.last_message_summary,
        "thread_summary": candidate.thread_summary,
        "status": candidate.status,
        "days_without_reply": candidate.days_without_reply,
        "messages_count": candidate.messages_count,
        "evidence_refs": candidate.evidence_refs,
        "metadata_json": candidate.metadata_json,
        "computed_at": candidate.computed_at,
    }


async def upsert_email_thread_states(
    session: AsyncSession,
    candidates: list[EmailThreadStateCandidate],
) -> int:
    upserted = 0

    for candidate in candidates:
        existing = await session.scalar(
            select(EmailThreadState).where(EmailThreadState.thread_key == candidate.thread_key)
        )
        values = _thread_state_values(candidate)

        if existing is None:
            session.add(EmailThreadState(**values))
        else:
            for key, value in values.items():
                setattr(existing, key, value)
        upserted += 1

    await session.flush()
    return upserted


async def rebuild_email_thread_states_from_stored_gmail(
    *,
    me_addresses: set[str] | None = None,
    now: datetime | None = None,
) -> EmailThreadRebuildResult:
    async with AsyncSessionLocal() as session:
        messages = await load_stored_gmail_message_snapshots(session)
        candidates = build_email_thread_state_candidates(
            messages,
            me_addresses=me_addresses,
            now=now,
        )
        upserted = await upsert_email_thread_states(session, candidates)
        await session.commit()

    return EmailThreadRebuildResult(
        thread_states_built=upserted,
        messages_considered=len(messages),
        status_counts=dict(Counter(candidate.status for candidate in candidates)),
    )


async def get_active_email_thread_states(
    *,
    limit: int = 20,
    statuses: tuple[str, ...] = (
        THREAD_STATUS_NEEDS_MY_REPLY,
        THREAD_STATUS_WAITING_FOR_EXTERNAL_REPLY,
        THREAD_STATUS_INFORMATIONAL,
    ),
) -> list[EmailThreadState]:
    safe_limit = max(1, min(int(limit), 50))

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(EmailThreadState)
            .where(EmailThreadState.source == EMAIL_SOURCE_GMAIL)
            .where(EmailThreadState.status.in_(statuses))
            .order_by(desc(EmailThreadState.last_message_at), desc(EmailThreadState.id))
            .limit(safe_limit)
        )
        return list(result.scalars().all())
