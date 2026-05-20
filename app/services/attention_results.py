from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import asc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.attention_models import AttentionTriageResultRecord
from app.services.attention_feedback import get_recent_feedback_for_source_object
from app.services.attention_triage import (
    AttentionContext,
    AttentionTriageAgent,
    AttentionTriageProvider,
    AttentionTriageResult,
    ConservativeFallbackAttentionTriageProvider,
    apply_attention_confidence_policy,
    parse_attention_triage_result,
)
from app.services.normalized_activity import (
    StoredNormalizedActivityItem,
    get_normalized_activity_item,
)


class AttentionResultValidationError(ValueError):
    pass


@dataclass(frozen=True)
class StoredAttentionTriageResult:
    triage_result_id: str
    source: str
    source_object_id: str
    activity_item_id: str | None
    attention_class: str
    priority: str
    show_in_digest: bool
    confidence: float
    reason: str
    recommended_action: str
    owner: str | None
    deadline: str | None
    evidence_refs: list[dict[str, Any]]
    created_at: datetime

    def to_attention_triage_result(self) -> AttentionTriageResult:
        return AttentionTriageResult(
            attention_class=self.attention_class,
            priority=self.priority,
            show_in_digest=self.show_in_digest,
            confidence=self.confidence,
            reason=self.reason,
            recommended_action=self.recommended_action,
            owner=self.owner,
            deadline=self.deadline,
            evidence=[dict(ref) for ref in self.evidence_refs],
        )


AttentionResultInput = AttentionTriageResult | Mapping[str, Any] | str | bytes
ActivityAttentionAgent = AttentionTriageAgent | AttentionTriageProvider


def _clean_required_string(value: str, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise AttentionResultValidationError(f"{field_name} must be a non-empty string")

    cleaned = value.strip()
    if not cleaned:
        raise AttentionResultValidationError(f"{field_name} must be a non-empty string")
    return cleaned


def _clean_optional_string(value: str | None, *, field_name: str) -> str | None:
    if value is None:
        return None
    return _clean_required_string(value, field_name=field_name)


def _created_at(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None or value.utcoffset() is None:
        raise AttentionResultValidationError("created_at must be timezone-aware")
    return value


def _coerce_result(value: AttentionResultInput) -> AttentionTriageResult:
    if isinstance(value, AttentionTriageResult):
        return value
    if not isinstance(value, str | bytes | Mapping):
        raise AttentionResultValidationError("attention triage result is invalid")
    try:
        return parse_attention_triage_result(value)
    except (TypeError, ValueError, ValidationError) as exc:
        raise AttentionResultValidationError("attention triage result is invalid") from exc


def _dedupe_strings(values: list[str | None]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        cleaned = value.strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        result.append(cleaned)
    return result


def _jira_project_keys(jira_keys: list[str]) -> list[str]:
    projects: list[str | None] = []
    for jira_key in jira_keys:
        if not isinstance(jira_key, str) or "-" not in jira_key:
            continue
        projects.append(jira_key.split("-", 1)[0])
    return _dedupe_strings(projects)


def _activity_triage_result_id(activity_item_id: str) -> str:
    digest = sha256(activity_item_id.encode("utf-8")).hexdigest()
    return f"atri_{digest[:32]}"


def _build_activity_attention_context(
    activity: StoredNormalizedActivityItem,
    *,
    recent_feedback: list[Any],
    generated_at: datetime | None = None,
) -> AttentionContext:
    generated_at = _created_at(generated_at)
    return AttentionContext(
        important_projects=_dedupe_strings([activity.project]),
        known_people=_dedupe_strings(activity.related_people),
        active_jira_projects=_jira_project_keys(activity.related_jira_keys),
        recent_drive_topics=_dedupe_strings(
            [activity.project] if activity.source in {"drive", "google_drive"} else []
        ),
        recent_feedback=list(recent_feedback),
        instructions=(
            "Prioritize work-relevant normalized activity. If uncertain, do not hide. "
            "Treat recent feedback as advisory context only. "
            f"Generated at {generated_at.isoformat()}."
        ),
    )


def _context_with_recent_feedback(
    context: AttentionContext,
    recent_feedback: list[Any],
) -> AttentionContext:
    return context.model_copy(update={"recent_feedback": list(recent_feedback)})


def _activity_agent(
    *,
    provider: AttentionTriageProvider | None,
) -> AttentionTriageAgent:
    return AttentionTriageAgent(
        provider or ConservativeFallbackAttentionTriageProvider(),
        fallback_provider=ConservativeFallbackAttentionTriageProvider(),
        fallback_on_provider_error=provider is None,
    )


async def _stored_activity(
    session: AsyncSession,
    *,
    activity_item_id: str | None,
    activity: StoredNormalizedActivityItem | None,
) -> StoredNormalizedActivityItem:
    if activity is not None:
        cleaned_activity_item_id = _clean_required_string(
            activity.activity_item_id,
            field_name="activity_item_id",
        )
        if activity_item_id is not None:
            requested_activity_item_id = _clean_required_string(
                activity_item_id,
                field_name="activity_item_id",
            )
            if requested_activity_item_id != cleaned_activity_item_id:
                raise AttentionResultValidationError(
                    "activity_item_id does not match normalized activity item"
                )
        return activity

    requested_activity_item_id = _clean_required_string(
        activity_item_id,
        field_name="activity_item_id",
    )
    stored = await get_normalized_activity_item(
        session,
        activity_item_id=requested_activity_item_id,
    )
    if stored is None:
        raise AttentionResultValidationError("normalized activity item was not found")
    return stored


def _record_to_read_model(record: AttentionTriageResultRecord) -> StoredAttentionTriageResult:
    return StoredAttentionTriageResult(
        triage_result_id=record.triage_result_id,
        source=record.source,
        source_object_id=record.source_object_id,
        activity_item_id=record.activity_item_id,
        attention_class=record.attention_class,
        priority=record.priority,
        show_in_digest=record.show_in_digest,
        confidence=record.confidence,
        reason=record.reason,
        recommended_action=record.recommended_action,
        owner=record.owner,
        deadline=record.deadline,
        evidence_refs=[
            dict(evidence_ref)
            for evidence_ref in record.evidence_refs
            if isinstance(evidence_ref, dict)
        ],
        created_at=record.created_at,
    )


async def record_attention_triage_result(
    session: AsyncSession,
    *,
    source: str,
    source_object_id: str,
    result: AttentionResultInput,
    activity_item_id: str | None = None,
    triage_result_id: str | None = None,
    created_at: datetime | None = None,
) -> StoredAttentionTriageResult:
    """Persist a validated attention triage result without provider side effects.

    The caller controls commit/rollback. This stores only the strict
    AttentionTriageResult fields and source identifiers, not prompts, source
    bodies, provider payloads, or raw activity text.
    """

    parsed_result = _coerce_result(result)

    record = AttentionTriageResultRecord(
        triage_result_id=_clean_optional_string(
            triage_result_id,
            field_name="triage_result_id",
        )
        or f"atri_{uuid4().hex}",
        source=_clean_required_string(source, field_name="source"),
        source_object_id=_clean_required_string(
            source_object_id,
            field_name="source_object_id",
        ),
        activity_item_id=_clean_optional_string(
            activity_item_id,
            field_name="activity_item_id",
        ),
        attention_class=parsed_result.attention_class,
        priority=parsed_result.priority,
        show_in_digest=parsed_result.show_in_digest,
        confidence=parsed_result.confidence,
        reason=parsed_result.reason,
        recommended_action=parsed_result.recommended_action,
        owner=parsed_result.owner,
        deadline=parsed_result.deadline,
        evidence_refs=[dict(evidence_ref) for evidence_ref in parsed_result.evidence],
        created_at=_created_at(created_at),
    )

    session.add(record)
    await session.flush()

    return _record_to_read_model(record)


async def get_attention_triage_result(
    session: AsyncSession,
    *,
    triage_result_id: str,
) -> StoredAttentionTriageResult | None:
    record = await session.scalar(
        select(AttentionTriageResultRecord).where(
            AttentionTriageResultRecord.triage_result_id
            == _clean_required_string(
                triage_result_id,
                field_name="triage_result_id",
            )
        )
    )
    if record is None:
        return None
    return _record_to_read_model(record)


async def get_attention_triage_result_for_activity_item(
    session: AsyncSession,
    *,
    activity_item_id: str,
) -> StoredAttentionTriageResult | None:
    record = await session.scalar(
        select(AttentionTriageResultRecord)
        .where(
            AttentionTriageResultRecord.activity_item_id
            == _clean_required_string(
                activity_item_id,
                field_name="activity_item_id",
            )
        )
        .order_by(asc(AttentionTriageResultRecord.id))
    )
    if record is None:
        return None
    return _record_to_read_model(record)


async def triage_normalized_activity_item(
    session: AsyncSession,
    *,
    activity_item_id: str | None = None,
    activity: StoredNormalizedActivityItem | None = None,
    provider: AttentionTriageProvider | None = None,
    agent: ActivityAttentionAgent | None = None,
    context: AttentionContext | None = None,
    generated_at: datetime | None = None,
) -> StoredAttentionTriageResult:
    """Classify one stored normalized activity item and persist the result.

    This bridge is provider-free by default and idempotent by activity_item_id.
    It stores only the validated AttentionTriageResult fields through the
    existing persistence service. Feedback is loaded into AttentionContext as
    advisory context only; it does not deterministically override provider or
    fallback classification.
    """

    stored_activity = await _stored_activity(
        session,
        activity_item_id=activity_item_id,
        activity=activity,
    )

    existing = await get_attention_triage_result_for_activity_item(
        session,
        activity_item_id=stored_activity.activity_item_id,
    )
    if existing is not None:
        return existing

    recent_feedback = await get_recent_feedback_for_source_object(
        session,
        source=stored_activity.source,
        source_object_id=stored_activity.source_object_id,
    )
    safe_context = (
        _context_with_recent_feedback(context, recent_feedback)
        if context is not None
        else _build_activity_attention_context(
            stored_activity,
            recent_feedback=recent_feedback,
            generated_at=generated_at,
        )
    )
    activity_contract = stored_activity.to_normalized_activity_item()
    selected_agent = agent or _activity_agent(provider=provider)

    try:
        raw_result = selected_agent.classify_activity(activity_contract, safe_context)
        result = apply_attention_confidence_policy(_coerce_result(raw_result))
    except Exception as exc:
        raise AttentionResultValidationError("attention triage result is invalid") from exc

    return await record_attention_triage_result(
        session,
        triage_result_id=_activity_triage_result_id(stored_activity.activity_item_id),
        source=stored_activity.source,
        source_object_id=stored_activity.source_object_id,
        activity_item_id=stored_activity.activity_item_id,
        result=result,
    )
