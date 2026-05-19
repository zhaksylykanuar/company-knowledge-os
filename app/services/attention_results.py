from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.attention_models import AttentionTriageResultRecord
from app.services.attention_triage import AttentionTriageResult, parse_attention_triage_result


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
