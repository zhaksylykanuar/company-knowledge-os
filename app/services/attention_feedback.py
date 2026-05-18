from __future__ import annotations

from datetime import datetime, timezone
from typing import get_args
from uuid import uuid4

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.attention_models import AttentionTriageFeedbackRecord
from app.services.attention_triage import AttentionTriageFeedback, FeedbackAction

DEFAULT_ATTENTION_FEEDBACK_LIMIT = 20
DEFAULT_ATTENTION_CONTEXT_FEEDBACK_LIMIT = 5
MAX_ATTENTION_FEEDBACK_LIMIT = 100
ATTENTION_FEEDBACK_ACTIONS = set(get_args(FeedbackAction))


class AttentionFeedbackValidationError(ValueError):
    pass


def _clean_required_string(value: str, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise AttentionFeedbackValidationError(f"{field_name} must be a non-empty string")

    cleaned = value.strip()
    if not cleaned:
        raise AttentionFeedbackValidationError(f"{field_name} must be a non-empty string")
    return cleaned


def _clean_optional_string(value: str | None, *, field_name: str) -> str | None:
    if value is None:
        return None
    return _clean_required_string(value, field_name=field_name)


def _validate_user_action(value: FeedbackAction | str) -> FeedbackAction:
    if value not in ATTENTION_FEEDBACK_ACTIONS:
        raise AttentionFeedbackValidationError("user_action is not a supported feedback action")
    return value  # type: ignore[return-value]


def _created_at(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None or value.utcoffset() is None:
        raise AttentionFeedbackValidationError("created_at must be timezone-aware")
    return value


def _bounded_limit(value: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise AttentionFeedbackValidationError("limit must be an integer") from exc
    if parsed < 1:
        raise AttentionFeedbackValidationError("limit must be at least 1")
    return min(parsed, MAX_ATTENTION_FEEDBACK_LIMIT)


def _record_to_feedback(record: AttentionTriageFeedbackRecord) -> AttentionTriageFeedback:
    return AttentionTriageFeedback(
        feedback_id=record.feedback_id,
        source_object_id=record.source_object_id,
        triage_result_id=record.triage_result_id,
        user_action=record.user_action,
        created_at=record.created_at,
    )


async def record_attention_triage_feedback(
    session: AsyncSession,
    *,
    source_object_id: str,
    user_action: FeedbackAction | str,
    source: str | None = None,
    triage_result_id: str | None = None,
    feedback_id: str | None = None,
    created_at: datetime | None = None,
) -> AttentionTriageFeedback:
    """Persist user feedback for future attention triage context.

    The caller controls commit/rollback. This service stores only feedback
    metadata and does not call providers, mutate triage results, or inspect raw
    source bodies.
    """

    record = AttentionTriageFeedbackRecord(
        feedback_id=_clean_optional_string(feedback_id, field_name="feedback_id")
        or f"atfb_{uuid4().hex}",
        source=_clean_optional_string(source, field_name="source"),
        source_object_id=_clean_required_string(
            source_object_id,
            field_name="source_object_id",
        ),
        triage_result_id=_clean_optional_string(
            triage_result_id,
            field_name="triage_result_id",
        ),
        user_action=_validate_user_action(user_action),
        created_at=_created_at(created_at),
    )

    session.add(record)
    await session.flush()

    return _record_to_feedback(record)


async def get_recent_attention_triage_feedback(
    session: AsyncSession,
    *,
    source_object_id: str,
    source: str | None = None,
    user_action: FeedbackAction | str | None = None,
    limit: int = DEFAULT_ATTENTION_FEEDBACK_LIMIT,
) -> list[AttentionTriageFeedback]:
    """Return newest feedback rows suitable for AttentionContext.recent_feedback."""

    filters = [
        AttentionTriageFeedbackRecord.source_object_id
        == _clean_required_string(source_object_id, field_name="source_object_id")
    ]
    cleaned_source = _clean_optional_string(source, field_name="source")
    if cleaned_source is not None:
        filters.append(AttentionTriageFeedbackRecord.source == cleaned_source)
    if user_action is not None:
        filters.append(
            AttentionTriageFeedbackRecord.user_action == _validate_user_action(user_action)
        )

    rows = list(
        (
            await session.scalars(
                select(AttentionTriageFeedbackRecord)
                .where(*filters)
                .order_by(
                    desc(AttentionTriageFeedbackRecord.created_at),
                    desc(AttentionTriageFeedbackRecord.id),
                )
                .limit(_bounded_limit(limit))
            )
        ).all()
    )

    return [_record_to_feedback(row) for row in rows]


async def get_recent_feedback_for_source_object(
    session: AsyncSession,
    *,
    source_object_id: str,
    source: str | None = None,
    limit: int = DEFAULT_ATTENTION_CONTEXT_FEEDBACK_LIMIT,
) -> list[AttentionTriageFeedback]:
    """Return bounded feedback rows for AttentionContext.recent_feedback.

    Source filtering is service-level collision protection. The public
    AttentionTriageFeedback DTO intentionally remains playbook-compatible and
    does not expose the source field.
    """

    return await get_recent_attention_triage_feedback(
        session,
        source_object_id=source_object_id,
        source=source,
        limit=limit,
    )
