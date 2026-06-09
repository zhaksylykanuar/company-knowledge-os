from __future__ import annotations

import html
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import getaddresses, parsedate_to_datetime
from hashlib import sha256
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.base import AsyncSessionLocal
from app.db.gmail_models import EmailThreadState, GmailMessage
from app.db.source_models import SourceDocument

EMAIL_SOURCE_GMAIL = "gmail"

THREAD_STATUS_NEEDS_MY_REPLY = "needs_my_reply"
THREAD_STATUS_WAITING_FOR_EXTERNAL_REPLY = "waiting_for_external_reply"
THREAD_STATUS_MANUAL_ACTION_REQUIRED = "manual_action_required"
THREAD_STATUS_RESOLVED = "resolved"
THREAD_STATUS_INFORMATIONAL = "informational"
THREAD_STATUS_HIDDEN = "hidden"

TRIAGE_CATEGORY_WORK_ACTION = "work_action"
TRIAGE_CATEGORY_WORK_WAITING = "work_waiting"
TRIAGE_CATEGORY_WORK_INFO = "work_info"
TRIAGE_CATEGORY_MANUAL_ACTION = "manual_action"
TRIAGE_CATEGORY_CALENDAR_UPDATE = "calendar_update"
TRIAGE_CATEGORY_SECURITY_ALERT = "security_alert"
TRIAGE_CATEGORY_MARKETING = "marketing"
TRIAGE_CATEGORY_NEWSLETTER = "newsletter"
TRIAGE_CATEGORY_SOCIAL_NETWORK = "social_network"
TRIAGE_CATEGORY_AUTOMATED_NOTIFICATION = "automated_notification"
TRIAGE_CATEGORY_NOISE = "noise"
TRIAGE_CATEGORY_UNKNOWN = "unknown"

TRIAGE_ACTION_REPLY_REQUIRED = "reply_required"
TRIAGE_ACTION_MANUAL_ACTION_REQUIRED = "manual_action_required"
TRIAGE_ACTION_WAITING_EXTERNAL_REPLY = "waiting_external_reply"
TRIAGE_ACTION_NO_ACTION_REQUIRED = "no_action_required"
TRIAGE_ACTION_REVIEW_OPTIONAL = "review_optional"

TRIAGE_PRIORITY_HIGH = "high"
TRIAGE_PRIORITY_MEDIUM = "medium"
TRIAGE_PRIORITY_LOW = "low"
TRIAGE_PRIORITY_HIDDEN = "hidden"

TRIAGE_CATEGORIES = {
    TRIAGE_CATEGORY_WORK_ACTION,
    TRIAGE_CATEGORY_WORK_WAITING,
    TRIAGE_CATEGORY_WORK_INFO,
    TRIAGE_CATEGORY_MANUAL_ACTION,
    TRIAGE_CATEGORY_CALENDAR_UPDATE,
    TRIAGE_CATEGORY_SECURITY_ALERT,
    TRIAGE_CATEGORY_MARKETING,
    TRIAGE_CATEGORY_NEWSLETTER,
    TRIAGE_CATEGORY_SOCIAL_NETWORK,
    TRIAGE_CATEGORY_AUTOMATED_NOTIFICATION,
    TRIAGE_CATEGORY_NOISE,
    TRIAGE_CATEGORY_UNKNOWN,
}
TRIAGE_ACTION_TYPES = {
    TRIAGE_ACTION_REPLY_REQUIRED,
    TRIAGE_ACTION_MANUAL_ACTION_REQUIRED,
    TRIAGE_ACTION_WAITING_EXTERNAL_REPLY,
    TRIAGE_ACTION_NO_ACTION_REQUIRED,
    TRIAGE_ACTION_REVIEW_OPTIONAL,
}
TRIAGE_PRIORITIES = {
    TRIAGE_PRIORITY_HIGH,
    TRIAGE_PRIORITY_MEDIUM,
    TRIAGE_PRIORITY_LOW,
    TRIAGE_PRIORITY_HIDDEN,
}

MESSAGE_DIRECTION_FROM_ME = "from_me"
MESSAGE_DIRECTION_FROM_EXTERNAL = "from_external"
MESSAGE_DIRECTION_UNKNOWN = "unknown"

SUMMARY_UNAVAILABLE = "Summary unavailable from stored metadata."
SUMMARY_PREVIEW_MAX_CHARS = 180

_SUBJECT_PREFIX_RE = re.compile(r"^\s*(?:(?:re|fw|fwd)(?:\[\d+\])?\s*:\s*)+", re.IGNORECASE)
_MESSAGE_ID_RE = re.compile(r"<([^>]+)>")
_ZERO_WIDTH_RE = re.compile(r"[\u200b-\u200d\ufeff]")
_SYSTEM_LOCAL_PARTS = {
    "no-reply",
    "noreply",
    "do-not-reply",
    "donotreply",
    "notification",
    "notifications",
}
_AUTOMATED_SENDER_TOKENS = (
    "noreply",
    "no-reply",
    "notification",
    "notifications",
    "automated",
    "calendar",
)
_SOCIAL_TOKENS = (
    "linkedin",
    "facebook",
    "instagram",
    "twitter",
    "x.com",
    "social",
)
_MARKETING_PHRASES = (
    "your post is ready",
    "build your digital twin",
    "activate it",
    "let your network know",
    "recommendations",
)
_MANUAL_ACTION_PHRASES = (
    "badge is ready",
    "your badge is ready",
    "ticket is ready",
    "your ticket is ready",
    "access is ready",
    "access ready",
    "registration is ready",
    "your registration is ready",
    "ready for pickup",
    "ready to access",
)
_SECURITY_TOKENS = (
    "security alert",
    "security notice",
    "new sign-in",
    "new signin",
    "new login",
    "suspicious",
    "password",
    "two-factor",
    "2fa",
)
_SECURITY_NO_ACTION_PHRASES = (
    "if this was you, no action is required",
    "if this was you no action is required",
    "if this was you, no action needed",
    "if this was you no action needed",
    "если это вы, ничего делать не нужно",
)
_DIRECT_WORK_REQUEST_PHRASES = (
    "can you",
    "could you",
    "please",
    "need your",
    "needs your",
    "needs a reply",
    "needs an operator reply",
    "do you",
    "what do you think",
    "let me know",
    "confirm",
    "approve",
    "review",
    "send over",
    "share",
    "next steps",
    "question",
    "request",
)
_WORK_INFO_TOKENS = (
    "project",
    "proposal",
    "customer",
    "client",
    "roadmap",
    "launch",
    "integration",
    "contract",
)
_URGENT_TOKENS = (
    "urgent",
    "asap",
    "today",
    "tomorrow",
    "deadline",
    "blocked",
)


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
    headers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class EmailTriageResult:
    category: str
    action_type: str
    priority: str
    show_in_digest: bool
    reason: str
    confidence: float


SEMANTIC_TRIAGE_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "category",
        "action_type",
        "priority",
        "show_in_digest",
        "reason",
        "confidence",
    ],
    "properties": {
        "category": {"type": "string", "enum": sorted(TRIAGE_CATEGORIES)},
        "action_type": {"type": "string", "enum": sorted(TRIAGE_ACTION_TYPES)},
        "priority": {"type": "string", "enum": sorted(TRIAGE_PRIORITIES)},
        "show_in_digest": {"type": "boolean"},
        "reason": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
}


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
    triage_category: str
    triage_action_type: str
    triage_priority: str
    show_in_digest: bool
    triage_reason: str
    triage_confidence: float
    evidence_refs: list[dict[str, Any]]
    metadata_json: dict[str, Any]
    computed_at: datetime


@dataclass(frozen=True)
class EmailThreadRebuildResult:
    thread_states_built: int
    messages_considered: int
    status_counts: dict[str, int]
    triage_category_counts: dict[str, int]
    action_type_counts: dict[str, int]
    priority_counts: dict[str, int]
    show_in_digest_counts: dict[str, int]


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
    cleaned = html.unescape(value)
    cleaned = _ZERO_WIDTH_RE.sub("", cleaned)
    cleaned = " ".join(cleaned.strip().split())
    return cleaned or None


def _short_preview(value: Any, *, max_chars: int = SUMMARY_PREVIEW_MAX_CHARS) -> str | None:
    cleaned = _clean_string(value)
    if cleaned is None:
        return None

    if len(cleaned) <= max_chars:
        return cleaned

    limit = max(1, max_chars - 3)
    truncated = cleaned[:limit].rstrip()
    word_boundary = truncated.rfind(" ")
    if word_boundary >= max(40, limit // 2):
        truncated = truncated[:word_boundary].rstrip()
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


def _parse_config_values(value: str | None) -> set[str]:
    if not value:
        return set()

    return {
        cleaned.casefold()
        for item in re.split(r"[,;\n]+", value)
        if (cleaned := " ".join(item.strip().split()))
    }


def _sender_domain(address: str | None) -> str | None:
    if not address or "@" not in address:
        return None
    domain = address.rsplit("@", 1)[1].strip().casefold()
    return domain or None


def _sender_local_part(address: str | None) -> str:
    if not address or "@" not in address:
        return ""
    return address.split("@", 1)[0].casefold()


def _domain_matches(domain: str | None, configured_domains: set[str]) -> bool:
    if not domain:
        return False

    return any(
        domain == configured or domain.endswith(f".{configured}")
        for configured in configured_domains
    )


def _address_matches(address: str | None, configured_addresses: set[str]) -> bool:
    return bool(address and address.casefold() in configured_addresses)


def _message_headers(message: EmailMessageSnapshot) -> dict[str, str]:
    return {
        str(key).casefold(): _clean_string(value) or ""
        for key, value in message.headers.items()
    }


def _header_value(message: EmailMessageSnapshot, name: str) -> str:
    return _message_headers(message).get(name.casefold(), "")


def _combined_message_text(message: EmailMessageSnapshot) -> str:
    parts = (
        message.subject,
        message.snippet,
        message.body_preview,
        _header_value(message, "content-type"),
    )
    return " ".join(part.casefold() for part in (_clean_string(part) for part in parts) if part)


def _contains_any(text: str, phrases: Iterable[str]) -> bool:
    return any(phrase.casefold() in text for phrase in phrases)


def _has_newsletter_headers(message: EmailMessageSnapshot) -> bool:
    headers = _message_headers(message)
    precedence = headers.get("precedence", "").casefold()
    return bool(headers.get("list-unsubscribe")) or precedence == "bulk"


def _is_automation_sender(address: str | None) -> bool:
    local_part = _sender_local_part(address)
    full_address = (address or "").casefold()
    return any(token in local_part or token in full_address for token in _AUTOMATED_SENDER_TOKENS)


def _is_calendar_update(message: EmailMessageSnapshot) -> bool:
    sender = (message.from_address or "").casefold()
    text = _combined_message_text(message)
    subject = (_clean_string(message.subject) or "").casefold()
    return (
        "calendar.google.com" in sender
        or "google calendar" in text
        or "text/calendar" in text
        or subject.startswith("invitation:")
        or subject.startswith("updated invitation:")
        or subject.startswith("canceled invitation:")
        or "calendar" in _sender_local_part(message.from_address)
    )


def _is_social_notification(message: EmailMessageSnapshot) -> bool:
    sender = (message.from_address or "").casefold()
    text = _combined_message_text(message)
    return _contains_any(sender, _SOCIAL_TOKENS) or _contains_any(text, _SOCIAL_TOKENS)


def _is_security_alert(message: EmailMessageSnapshot) -> bool:
    sender = (message.from_address or "").casefold()
    text = _combined_message_text(message)
    return (
        "security" in _sender_local_part(message.from_address)
        or "security" in sender
        or _contains_any(text, _SECURITY_TOKENS)
    )


def _is_security_no_action(message: EmailMessageSnapshot) -> bool:
    return _contains_any(_combined_message_text(message), _SECURITY_NO_ACTION_PHRASES)


def _is_manual_action_ready(message: EmailMessageSnapshot) -> bool:
    return _contains_any(_combined_message_text(message), _MANUAL_ACTION_PHRASES)


def _is_marketing_promotion(message: EmailMessageSnapshot) -> bool:
    return _contains_any(_combined_message_text(message), _MARKETING_PHRASES)


def _looks_direct_work_request(
    message: EmailMessageSnapshot,
    *,
    important_keywords: set[str],
) -> bool:
    text = _combined_message_text(message)
    if "?" in text:
        return True
    if _contains_any(text, _DIRECT_WORK_REQUEST_PHRASES):
        return True
    return any(keyword in text for keyword in important_keywords)


def _looks_work_info(
    message: EmailMessageSnapshot,
    *,
    important_keywords: set[str],
) -> bool:
    text = _combined_message_text(message)
    return _contains_any(text, _WORK_INFO_TOKENS) or any(
        keyword in text for keyword in important_keywords
    )


def _priority_for_work_request(
    message: EmailMessageSnapshot,
    *,
    important_sender: bool,
) -> str:
    text = _combined_message_text(message)
    if important_sender or _contains_any(text, _URGENT_TOKENS):
        return TRIAGE_PRIORITY_HIGH
    return TRIAGE_PRIORITY_MEDIUM


def _triage_result(
    *,
    category: str,
    action_type: str,
    priority: str,
    show_in_digest: bool,
    reason: str,
    confidence: float,
) -> EmailTriageResult:
    safe_category = category if category in TRIAGE_CATEGORIES else TRIAGE_CATEGORY_UNKNOWN
    safe_action_type = (
        action_type if action_type in TRIAGE_ACTION_TYPES else TRIAGE_ACTION_REVIEW_OPTIONAL
    )
    safe_priority = priority if priority in TRIAGE_PRIORITIES else TRIAGE_PRIORITY_LOW
    safe_confidence = min(1.0, max(0.0, float(confidence)))
    if safe_confidence < 0.65 and not show_in_digest:
        show_in_digest = True
        safe_priority = TRIAGE_PRIORITY_LOW

    return EmailTriageResult(
        category=safe_category,
        action_type=safe_action_type,
        priority=safe_priority,
        show_in_digest=show_in_digest,
        reason=reason,
        confidence=safe_confidence,
    )


def classify_email_thread_triage(
    messages: list[EmailMessageSnapshot],
    *,
    last_message_direction: str,
) -> EmailTriageResult:
    if not messages:
        return _triage_result(
            category=TRIAGE_CATEGORY_UNKNOWN,
            action_type=TRIAGE_ACTION_REVIEW_OPTIONAL,
            priority=TRIAGE_PRIORITY_LOW,
            show_in_digest=True,
            reason="empty_thread",
            confidence=0.0,
        )

    last_message = messages[-1]
    sender = last_message.from_address
    sender_domain = _sender_domain(sender)
    important_senders = _parse_config_values(settings.email_important_senders)
    important_domains = _parse_config_values(settings.email_important_domains)
    marketing_blocklist = _parse_config_values(settings.email_marketing_sender_blocklist)
    important_keywords = _parse_config_values(settings.email_important_project_keywords)
    important_sender = _address_matches(sender, important_senders) or _domain_matches(
        sender_domain,
        important_domains,
    )

    if _address_matches(sender, marketing_blocklist) or _domain_matches(
        sender_domain,
        marketing_blocklist,
    ):
        return _triage_result(
            category=TRIAGE_CATEGORY_MARKETING,
            action_type=TRIAGE_ACTION_REVIEW_OPTIONAL,
            priority=TRIAGE_PRIORITY_HIDDEN,
            show_in_digest=False,
            reason="marketing_sender_blocklist",
            confidence=0.95,
        )

    if _is_calendar_update(last_message):
        return _triage_result(
            category=TRIAGE_CATEGORY_CALENDAR_UPDATE,
            action_type=TRIAGE_ACTION_NO_ACTION_REQUIRED,
            priority=TRIAGE_PRIORITY_HIDDEN,
            show_in_digest=False,
            reason="calendar_update",
            confidence=0.9,
        )

    if _is_social_notification(last_message):
        return _triage_result(
            category=TRIAGE_CATEGORY_SOCIAL_NETWORK,
            action_type=TRIAGE_ACTION_REVIEW_OPTIONAL,
            priority=TRIAGE_PRIORITY_HIDDEN,
            show_in_digest=False,
            reason="social_notification",
            confidence=0.9,
        )

    if _is_security_alert(last_message):
        if _is_security_no_action(last_message):
            return _triage_result(
                category=TRIAGE_CATEGORY_SECURITY_ALERT,
                action_type=TRIAGE_ACTION_NO_ACTION_REQUIRED,
                priority=TRIAGE_PRIORITY_HIDDEN,
                show_in_digest=False,
                reason="security_alert_no_action_required",
                confidence=0.9,
            )
        return _triage_result(
            category=TRIAGE_CATEGORY_SECURITY_ALERT,
            action_type=TRIAGE_ACTION_MANUAL_ACTION_REQUIRED,
            priority=TRIAGE_PRIORITY_HIGH,
            show_in_digest=True,
            reason="security_alert_requires_review",
            confidence=0.9,
        )

    if _is_manual_action_ready(last_message):
        return _triage_result(
            category=TRIAGE_CATEGORY_MANUAL_ACTION,
            action_type=TRIAGE_ACTION_MANUAL_ACTION_REQUIRED,
            priority=TRIAGE_PRIORITY_MEDIUM,
            show_in_digest=True,
            reason="manual_action_ready",
            confidence=0.86,
        )

    if _has_newsletter_headers(last_message):
        return _triage_result(
            category=TRIAGE_CATEGORY_NEWSLETTER,
            action_type=TRIAGE_ACTION_REVIEW_OPTIONAL,
            priority=TRIAGE_PRIORITY_HIDDEN,
            show_in_digest=False,
            reason="newsletter_headers",
            confidence=0.95,
        )

    if _is_marketing_promotion(last_message):
        return _triage_result(
            category=TRIAGE_CATEGORY_MARKETING,
            action_type=TRIAGE_ACTION_REVIEW_OPTIONAL,
            priority=TRIAGE_PRIORITY_HIDDEN,
            show_in_digest=False,
            reason="marketing_promotion_phrase",
            confidence=0.85,
        )

    if _is_automation_sender(sender):
        return _triage_result(
            category=TRIAGE_CATEGORY_AUTOMATED_NOTIFICATION,
            action_type=TRIAGE_ACTION_NO_ACTION_REQUIRED,
            priority=TRIAGE_PRIORITY_HIDDEN,
            show_in_digest=False,
            reason="automated_sender",
            confidence=0.8,
        )

    if last_message_direction == MESSAGE_DIRECTION_FROM_ME:
        return _triage_result(
            category=TRIAGE_CATEGORY_WORK_WAITING,
            action_type=TRIAGE_ACTION_WAITING_EXTERNAL_REPLY,
            priority=TRIAGE_PRIORITY_MEDIUM,
            show_in_digest=True,
            reason="last_message_from_me",
            confidence=0.78,
        )

    if last_message_direction == MESSAGE_DIRECTION_FROM_EXTERNAL:
        if _looks_direct_work_request(
            last_message,
            important_keywords=important_keywords,
        ):
            return _triage_result(
                category=TRIAGE_CATEGORY_WORK_ACTION,
                action_type=TRIAGE_ACTION_REPLY_REQUIRED,
                priority=_priority_for_work_request(
                    last_message,
                    important_sender=important_sender,
                ),
                show_in_digest=True,
                reason="external_work_request",
                confidence=0.78,
            )
        if _looks_work_info(last_message, important_keywords=important_keywords):
            return _triage_result(
                category=TRIAGE_CATEGORY_WORK_INFO,
                action_type=TRIAGE_ACTION_REVIEW_OPTIONAL,
                priority=TRIAGE_PRIORITY_LOW,
                show_in_digest=True,
                reason="work_like_information",
                confidence=0.6,
            )
        return _triage_result(
            category=TRIAGE_CATEGORY_UNKNOWN,
            action_type=TRIAGE_ACTION_REVIEW_OPTIONAL,
            priority=TRIAGE_PRIORITY_LOW,
            show_in_digest=True,
            reason="uncertain_external_message",
            confidence=0.55,
        )

    return _triage_result(
        category=TRIAGE_CATEGORY_UNKNOWN,
        action_type=TRIAGE_ACTION_REVIEW_OPTIONAL,
        priority=TRIAGE_PRIORITY_LOW,
        show_in_digest=True,
        reason="unknown_message_direction",
        confidence=0.5,
    )


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


def classify_thread_status(
    last_message_direction: str,
    *,
    informational: bool = False,
    triage_action_type: str | None = None,
    show_in_digest: bool = True,
    triage_priority: str | None = None,
) -> str:
    if triage_action_type == TRIAGE_ACTION_REPLY_REQUIRED:
        return THREAD_STATUS_NEEDS_MY_REPLY
    if triage_action_type == TRIAGE_ACTION_WAITING_EXTERNAL_REPLY:
        return THREAD_STATUS_WAITING_FOR_EXTERNAL_REPLY
    if triage_action_type == TRIAGE_ACTION_MANUAL_ACTION_REQUIRED:
        return THREAD_STATUS_MANUAL_ACTION_REQUIRED
    if triage_action_type == TRIAGE_ACTION_NO_ACTION_REQUIRED:
        if not show_in_digest or triage_priority == TRIAGE_PRIORITY_HIDDEN:
            return THREAD_STATUS_HIDDEN
        return THREAD_STATUS_INFORMATIONAL
    if triage_action_type == TRIAGE_ACTION_REVIEW_OPTIONAL:
        if not show_in_digest or triage_priority == TRIAGE_PRIORITY_HIDDEN:
            return THREAD_STATUS_HIDDEN
        return THREAD_STATUS_INFORMATIONAL

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
    triage = classify_email_thread_triage(messages, last_message_direction=last_direction)
    informational = _looks_informational(last_message)
    status = classify_thread_status(
        last_direction,
        informational=informational,
        triage_action_type=triage.action_type,
        show_in_digest=triage.show_in_digest,
        triage_priority=triage.priority,
    )
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
        triage_category=triage.category,
        triage_action_type=triage.action_type,
        triage_priority=triage.priority,
        show_in_digest=triage.show_in_digest,
        triage_reason=triage.reason,
        triage_confidence=triage.confidence,
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
            "triage_classifier": "deterministic_v1",
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


def _headers_from_value(value: Any) -> dict[str, str]:
    if isinstance(value, dict):
        return {
            str(key).casefold(): cleaned
            for key, raw_value in value.items()
            if (cleaned := _clean_string(raw_value))
        }

    if isinstance(value, list):
        headers: dict[str, str] = {}
        for item in value:
            if not isinstance(item, dict):
                continue
            name = _clean_string(item.get("name"))
            header_value = _clean_string(item.get("value"))
            if name and header_value:
                headers[name.casefold()] = header_value
        return headers

    return {}


def _headers_from_sources(metadata: dict[str, Any], payload: dict[str, Any]) -> dict[str, str]:
    headers: dict[str, str] = {}
    for value in (
        metadata.get("headers"),
        payload.get("headers"),
        _value_from_sources(metadata, payload, "payload_headers"),
    ):
        headers.update(_headers_from_value(value))

    nested_payload = payload.get("payload")
    if isinstance(nested_payload, dict):
        headers.update(_headers_from_value(nested_payload.get("headers")))

    return headers


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
        headers=_headers_from_sources(metadata, payload),
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
        "triage_category": candidate.triage_category,
        "triage_action_type": candidate.triage_action_type,
        "triage_priority": candidate.triage_priority,
        "show_in_digest": candidate.show_in_digest,
        "triage_reason": candidate.triage_reason,
        "triage_confidence": candidate.triage_confidence,
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
        triage_category_counts=dict(Counter(candidate.triage_category for candidate in candidates)),
        action_type_counts=dict(Counter(candidate.triage_action_type for candidate in candidates)),
        priority_counts=dict(Counter(candidate.triage_priority for candidate in candidates)),
        show_in_digest_counts=dict(
            Counter(str(candidate.show_in_digest).lower() for candidate in candidates)
        ),
    )
