from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings as app_settings
from app.db.gmail_models import EmailThreadState
from app.services.attention_triage import (
    AttentionContext,
    AttentionTriageAgent,
    AttentionTriageProvider,
    AttentionTriageResult,
    ConservativeFallbackAttentionTriageProvider,
    NormalizedActivityItem,
)
from app.services.email_threads import parse_email_addresses

DEFAULT_EMAIL_ATTENTION_PREVIEW_LIMIT = 20
MAX_EMAIL_ATTENTION_PREVIEW_LIMIT = 50


@dataclass(frozen=True)
class EmailAttentionBatchResult:
    threads_considered: int
    attention_class_counts: dict[str, int]
    action_type_counts: dict[str, int]
    priority_counts: dict[str, int]
    show_in_digest_counts: dict[str, int]
    low_confidence_visible_count: int
    private_content_printed: bool = False

    def to_safe_dict(self) -> dict[str, Any]:
        return {
            "threads_considered": self.threads_considered,
            "attention_class_counts": self.attention_class_counts,
            "action_type_counts": self.action_type_counts,
            "priority_counts": self.priority_counts,
            "show_in_digest_counts": self.show_in_digest_counts,
            "low_confidence_visible_count": self.low_confidence_visible_count,
            "private_content_printed": self.private_content_printed,
        }


def _setting(settings: Any | None, name: str, fallback: Any) -> Any:
    if settings is None:
        settings = app_settings
    return getattr(settings, name, fallback)


def _safe_limit(limit: int | None) -> int:
    if limit is None:
        return DEFAULT_EMAIL_ATTENTION_PREVIEW_LIMIT
    try:
        parsed = int(limit)
    except (TypeError, ValueError):
        return DEFAULT_EMAIL_ATTENTION_PREVIEW_LIMIT
    if parsed < 1:
        return DEFAULT_EMAIL_ATTENTION_PREVIEW_LIMIT
    return min(parsed, MAX_EMAIL_ATTENTION_PREVIEW_LIMIT)


def _truncate(value: str | None, max_chars: int) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.strip().split())
    if not cleaned:
        return None
    if max_chars <= 0:
        return ""
    return cleaned[:max_chars]


def _datetime_attr(value: Any) -> datetime | None:
    return value if isinstance(value, datetime) else None


def _list_attr(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _dict_attr(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string_attr(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _participant_labels(thread_state: Any) -> list[str]:
    labels: list[str] = []
    for participant in _list_attr(getattr(thread_state, "participants_json", None)):
        if isinstance(participant, dict):
            participant_key = _string_attr(participant.get("participant_key"))
            if participant_key:
                labels.append(participant_key)
                continue
            if participant.get("is_me") is True:
                labels.append("me")
                continue
        elif isinstance(participant, str) and participant.strip():
            labels.append(participant.strip())
    return list(dict.fromkeys(labels))


def _last_actor_label(thread_state: Any) -> str | None:
    metadata = _dict_attr(getattr(thread_state, "metadata_json", None))
    display = _string_attr(metadata.get("last_message_from_display"))
    if display:
        return display

    direction = _string_attr(getattr(thread_state, "last_message_direction", None))
    if direction == "from_me":
        return "me"
    if direction == "from_external":
        return "external sender"
    if direction == "system":
        return "system"
    return None


def _recipient_labels(thread_state: Any) -> list[str]:
    metadata = _dict_attr(getattr(thread_state, "metadata_json", None))
    value = metadata.get("last_message_to_display")
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _activity_direction(thread_state: Any) -> str:
    direction = _string_attr(getattr(thread_state, "last_message_direction", None))
    if direction in {"from_me", "from_external", "system", "unknown"}:
        return direction
    return "unknown"


def _activity_source(thread_state: Any) -> str:
    source = _string_attr(getattr(thread_state, "source", None))
    return source if source in {"gmail", "github", "jira", "google_drive", "calendar"} else "gmail"


def _source_metadata(thread_state: Any) -> dict[str, Any]:
    participants = _list_attr(getattr(thread_state, "participants_json", None))
    evidence_refs = _list_attr(getattr(thread_state, "evidence_refs", None))
    return {
        "source_model": "email_thread_states",
        "status": _string_attr(getattr(thread_state, "status", None)),
        "deterministic_triage_category": _string_attr(
            getattr(thread_state, "triage_category", None)
        ),
        "deterministic_action_type": _string_attr(
            getattr(thread_state, "triage_action_type", None)
        ),
        "deterministic_priority": _string_attr(getattr(thread_state, "triage_priority", None)),
        "deterministic_show_in_digest": getattr(thread_state, "show_in_digest", None),
        "deterministic_triage_confidence": getattr(thread_state, "triage_confidence", None),
        "deterministic_triage_reason": _string_attr(
            getattr(thread_state, "triage_reason", None)
        ),
        "days_without_reply": getattr(thread_state, "days_without_reply", None),
        "participants_count": len(participants),
        "evidence_refs": evidence_refs,
        "evidence_ref_count": len(evidence_refs),
    }


def email_thread_state_to_activity_item(
    thread_state: Any,
    *,
    max_text_chars: int | None = None,
) -> NormalizedActivityItem:
    max_chars = 6000 if max_text_chars is None else max(0, int(max_text_chars))
    thread_key = _string_attr(getattr(thread_state, "thread_key", None)) or "unknown-email-thread"
    subject = _string_attr(getattr(thread_state, "subject_display", None)) or _string_attr(
        getattr(thread_state, "subject_normalized", None)
    )

    return NormalizedActivityItem(
        source=_activity_source(thread_state),
        object_type="email_thread",
        object_id=thread_key,
        title=subject,
        created_at=_datetime_attr(getattr(thread_state, "created_at", None)),
        updated_at=_datetime_attr(getattr(thread_state, "updated_at", None)),
        last_activity_at=_datetime_attr(getattr(thread_state, "last_message_at", None)),
        last_actor=_last_actor_label(thread_state),
        last_activity_direction=_activity_direction(thread_state),
        participants=_participant_labels(thread_state),
        sender=_last_actor_label(thread_state),
        recipients=_recipient_labels(thread_state),
        thread_message_count=max(0, int(getattr(thread_state, "messages_count", 0) or 0)),
        clean_text_preview=_truncate(
            getattr(thread_state, "last_message_summary", None),
            max_chars,
        ),
        thread_summary=_truncate(getattr(thread_state, "thread_summary", None), max_chars),
        source_metadata=_source_metadata(thread_state),
        links=[],
    )


def build_email_attention_context(
    *,
    settings: Any | None = None,
    generated_at: datetime | None = None,
) -> AttentionContext:
    generated_at = generated_at or datetime.now(timezone.utc)
    user_email_addresses = list(parse_email_addresses(_setting(settings, "email_me_addresses", None)))
    return AttentionContext(
        user_email_addresses=user_email_addresses,
        instructions=(
            "Prioritize work-relevant email threads. If uncertain, do not hide. "
            f"Generated at {generated_at.isoformat()}."
        ),
    )


def _agent_for(
    *,
    provider: AttentionTriageProvider | None,
    settings: Any | None,
) -> AttentionTriageAgent:
    selected_provider = provider or ConservativeFallbackAttentionTriageProvider()
    return AttentionTriageAgent(
        selected_provider,
        fallback_provider=ConservativeFallbackAttentionTriageProvider(),
        min_confidence_to_hide=float(
            _setting(settings, "attention_triage_min_confidence_to_hide", 0.80)
        ),
        review_threshold=float(_setting(settings, "attention_triage_review_threshold", 0.55)),
    )


def classify_email_thread_attention(
    thread_state: Any,
    *,
    provider: AttentionTriageProvider | None = None,
    context: AttentionContext | None = None,
    settings: Any | None = None,
) -> AttentionTriageResult:
    max_chars = int(_setting(settings, "attention_triage_max_text_chars", 6000))
    activity = email_thread_state_to_activity_item(thread_state, max_text_chars=max_chars)
    safe_context = context or build_email_attention_context(settings=settings)
    return _agent_for(provider=provider, settings=settings).classify_activity(
        activity,
        safe_context,
    )


def _aggregate_results(
    results: Sequence[AttentionTriageResult],
    *,
    review_threshold: float,
) -> EmailAttentionBatchResult:
    return EmailAttentionBatchResult(
        threads_considered=len(results),
        attention_class_counts=dict(Counter(result.attention_class for result in results)),
        action_type_counts=dict(Counter(result.action_type for result in results)),
        priority_counts=dict(Counter(result.priority for result in results)),
        show_in_digest_counts=dict(
            Counter(str(result.show_in_digest).lower() for result in results)
        ),
        low_confidence_visible_count=sum(
            1
            for result in results
            if result.confidence < review_threshold and result.show_in_digest is True
        ),
    )


def classify_email_thread_state_items(
    thread_states: Sequence[Any],
    *,
    provider: AttentionTriageProvider | None = None,
    context: AttentionContext | None = None,
    settings: Any | None = None,
) -> EmailAttentionBatchResult:
    safe_context = context or build_email_attention_context(settings=settings)
    results = [
        classify_email_thread_attention(
            thread_state,
            provider=provider,
            context=safe_context,
            settings=settings,
        )
        for thread_state in thread_states
    ]
    return _aggregate_results(
        results,
        review_threshold=float(_setting(settings, "attention_triage_review_threshold", 0.55)),
    )


async def classify_email_thread_states(
    session: AsyncSession,
    *,
    provider: AttentionTriageProvider | None = None,
    context: AttentionContext | None = None,
    settings: Any | None = None,
    limit: int | None = None,
) -> EmailAttentionBatchResult:
    result = await session.execute(
        select(EmailThreadState)
        .where(EmailThreadState.source == "gmail")
        .order_by(desc(EmailThreadState.last_message_at), desc(EmailThreadState.id))
        .limit(_safe_limit(limit))
    )
    thread_states = list(result.scalars().all())
    return classify_email_thread_state_items(
        thread_states,
        provider=provider,
        context=context,
        settings=settings,
    )
