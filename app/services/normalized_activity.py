from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import Any
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.event_models import NormalizedActivityItemRecord, SourceEvent
from app.services.attention_triage import NormalizedActivityItem
from app.services.source_activity import SourceActivityMappingError, source_event_to_activity_item


class NormalizedActivityValidationError(ValueError):
    pass


class SourceEventActivityProjectionError(ValueError):
    pass


@dataclass(frozen=True)
class StoredNormalizedActivityItem:
    activity_item_id: str
    source_event_id: str | None
    source: str
    source_object_id: str
    activity_type: str
    title: str | None
    actor: str | None
    activity_created_at: datetime | None
    project: str | None
    safe_summary: str | None
    related_people: list[str]
    related_jira_keys: list[str]
    related_prs: list[str]
    related_files: list[str]
    evidence_refs: list[dict[str, Any]]
    created_at: datetime

    def to_normalized_activity_item(self) -> NormalizedActivityItem:
        return NormalizedActivityItem(
            source=self.source,
            source_object_id=self.source_object_id,
            activity_type=self.activity_type,
            title=self.title,
            actor=self.actor,
            created_at=self.activity_created_at,
            project=self.project,
            safe_summary=self.safe_summary,
            related_people=list(self.related_people),
            related_jira_keys=list(self.related_jira_keys),
            related_prs=list(self.related_prs),
            related_files=list(self.related_files),
            evidence_refs=[dict(ref) for ref in self.evidence_refs],
        )


NormalizedActivityInput = NormalizedActivityItem | Mapping[str, Any] | str | bytes


def _clean_required_string(value: str, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise NormalizedActivityValidationError(f"{field_name} must be a non-empty string")

    cleaned = value.strip()
    if not cleaned:
        raise NormalizedActivityValidationError(f"{field_name} must be a non-empty string")
    return cleaned


def _clean_optional_string(value: str | None, *, field_name: str) -> str | None:
    if value is None:
        return None
    return _clean_required_string(value, field_name=field_name)


def _coerce_activity(value: NormalizedActivityInput) -> NormalizedActivityItem:
    if isinstance(value, NormalizedActivityItem):
        return value
    if not isinstance(value, str | bytes | Mapping):
        raise NormalizedActivityValidationError("normalized activity item is invalid")
    try:
        parsed = json.loads(value) if isinstance(value, str | bytes) else dict(value)
        return NormalizedActivityItem.model_validate(parsed)
    except (TypeError, ValueError, ValidationError) as exc:
        raise NormalizedActivityValidationError("normalized activity item is invalid") from exc


def _copy_string_list(value: list[str]) -> list[str]:
    return [item for item in value if isinstance(item, str)]


def _copy_evidence_refs(value: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [dict(ref) for ref in value if isinstance(ref, dict)]


def _source_event_projection_id(source_event_id: str) -> str:
    digest = sha256(source_event_id.encode("utf-8")).hexdigest()
    return f"nact_{digest[:32]}"


def _record_to_read_model(record: NormalizedActivityItemRecord) -> StoredNormalizedActivityItem:
    return StoredNormalizedActivityItem(
        activity_item_id=record.activity_item_id,
        source_event_id=record.source_event_id,
        source=record.source,
        source_object_id=record.source_object_id,
        activity_type=record.activity_type,
        title=record.title,
        actor=record.actor,
        activity_created_at=record.activity_created_at,
        project=record.project,
        safe_summary=record.safe_summary,
        related_people=_copy_string_list(record.related_people),
        related_jira_keys=_copy_string_list(record.related_jira_keys),
        related_prs=_copy_string_list(record.related_prs),
        related_files=_copy_string_list(record.related_files),
        evidence_refs=_copy_evidence_refs(record.evidence_refs),
        created_at=record.created_at,
    )


async def record_normalized_activity_item(
    session: AsyncSession,
    *,
    activity: NormalizedActivityInput,
    source_event_id: str | None = None,
    activity_item_id: str | None = None,
) -> StoredNormalizedActivityItem:
    """Persist a validated NormalizedActivityItem without provider side effects.

    The caller controls commit/rollback. This stores only the strict activity
    contract fields, evidence refs, and optional SourceEvent linkage, not raw
    payloads, prompts, provider payloads, or unvalidated JSON blobs.
    """

    parsed_activity = _coerce_activity(activity)

    from app.services.run_context import get_run_id

    record = NormalizedActivityItemRecord(
        run_id=get_run_id(),
        activity_item_id=_clean_optional_string(
            activity_item_id,
            field_name="activity_item_id",
        )
        or f"nact_{uuid4().hex}",
        source_event_id=_clean_optional_string(
            source_event_id,
            field_name="source_event_id",
        ),
        source=_clean_required_string(parsed_activity.source, field_name="source"),
        source_object_id=_clean_required_string(
            parsed_activity.source_object_id,
            field_name="source_object_id",
        ),
        activity_type=_clean_required_string(
            parsed_activity.activity_type,
            field_name="activity_type",
        ),
        title=parsed_activity.title,
        actor=parsed_activity.actor,
        activity_created_at=parsed_activity.created_at,
        project=parsed_activity.project,
        safe_summary=parsed_activity.safe_summary,
        related_people=list(parsed_activity.related_people),
        related_jira_keys=list(parsed_activity.related_jira_keys),
        related_prs=list(parsed_activity.related_prs),
        related_files=list(parsed_activity.related_files),
        evidence_refs=[dict(ref) for ref in parsed_activity.evidence_refs],
    )

    session.add(record)
    await session.flush()

    return _record_to_read_model(record)


async def get_normalized_activity_item(
    session: AsyncSession,
    *,
    activity_item_id: str,
) -> StoredNormalizedActivityItem | None:
    record = await session.scalar(
        select(NormalizedActivityItemRecord).where(
            NormalizedActivityItemRecord.activity_item_id
            == _clean_required_string(
                activity_item_id,
                field_name="activity_item_id",
            )
        )
    )
    if record is None:
        return None
    return _record_to_read_model(record)


async def get_normalized_activity_item_for_source_event(
    session: AsyncSession,
    *,
    source_event_id: str,
) -> StoredNormalizedActivityItem | None:
    record = await session.scalar(
        select(NormalizedActivityItemRecord)
        .where(
            NormalizedActivityItemRecord.source_event_id
            == _clean_required_string(
                source_event_id,
                field_name="source_event_id",
            )
        )
        .order_by(NormalizedActivityItemRecord.id)
    )
    if record is None:
        return None
    return _record_to_read_model(record)


def _source_event_payload(source_event: SourceEvent) -> dict[str, Any]:
    return {
        "source": source_event.source_system,
        "source_system": source_event.source_system,
        "source_event_id": source_event.source_event_id,
        "source_object_type": source_event.source_object_type,
        "source_object_id": source_event.source_object_id,
        "event_type": source_event.event_type,
        "event_time": source_event.source_event_ts or source_event.created_at,
        "title": source_event.title,
        "summary": source_event.summary,
        "source_url": source_event.source_url,
        "actor_external_id": source_event.actor_external_id,
        "raw_object_ref": source_event.raw_object_ref,
    }


def _merged_source_event_evidence_refs(
    *,
    activity: NormalizedActivityItem,
    source_event: SourceEvent,
) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = [
        dict(ref)
        for ref in activity.evidence_refs
        if isinstance(ref, dict)
    ]
    if isinstance(source_event.evidence_refs, list):
        refs.extend(
            dict(ref)
            for ref in source_event.evidence_refs
            if isinstance(ref, dict)
        )

    seen: set[tuple[tuple[str, str], ...]] = set()
    unique_refs: list[dict[str, Any]] = []
    for ref in refs:
        marker = tuple(sorted((str(key), str(value)) for key, value in ref.items()))
        if marker in seen:
            continue
        seen.add(marker)
        unique_refs.append(ref)
    return unique_refs


def _source_event_to_validated_activity(source_event: SourceEvent) -> NormalizedActivityItem:
    try:
        activity = source_event_to_activity_item(_source_event_payload(source_event))
    except SourceActivityMappingError as exc:
        raise SourceEventActivityProjectionError(
            "source event cannot be projected to normalized activity"
        ) from exc

    return NormalizedActivityItem.model_validate(
        {
            **activity.model_dump(),
            "evidence_refs": _merged_source_event_evidence_refs(
                activity=activity,
                source_event=source_event,
            ),
        }
    )


async def project_source_event_to_normalized_activity_item(
    session: AsyncSession,
    *,
    source_event_id: str | None = None,
    source_event: SourceEvent | None = None,
) -> StoredNormalizedActivityItem:
    """Project one stored SourceEvent into one persisted NormalizedActivityItem.

    This bridge is provider-free and idempotent by source_event_id. It reuses the
    existing source activity mapper and the normalized activity persistence
    service, so invalid or unsupported source event shapes fail before any new
    normalized_activity_items row is inserted.
    """

    if source_event is None:
        cleaned_source_event_id = _clean_required_string(
            source_event_id,
            field_name="source_event_id",
        )
        source_event = await session.scalar(
            select(SourceEvent).where(SourceEvent.source_event_id == cleaned_source_event_id)
        )
        if source_event is None:
            raise SourceEventActivityProjectionError("source event was not found")
    elif source_event_id is not None and source_event.source_event_id != source_event_id:
        raise SourceEventActivityProjectionError("source_event_id does not match source_event")

    existing = await get_normalized_activity_item_for_source_event(
        session,
        source_event_id=source_event.source_event_id,
    )
    if existing is not None:
        return existing

    activity = _source_event_to_validated_activity(source_event)
    return await record_normalized_activity_item(
        session,
        activity=activity,
        source_event_id=source_event.source_event_id,
        activity_item_id=_source_event_projection_id(source_event.source_event_id),
    )
