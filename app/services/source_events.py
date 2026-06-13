from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.event_models import SourceEvent
from app.db.models import IngestedEvent
from app.integrations.source_registry import validate_source_event_contract


class SourceEventContractValidationError(ValueError):
    pass


@dataclass(frozen=True)
class SourceEventReadModel:
    source_event_id: str
    source_system: str
    source_object_type: str
    source_object_id: str
    event_type: str
    event_time: datetime | None
    title: str | None
    summary: str | None
    source_url: str | None
    raw_object_ref: str
    trace_id: str | None
    correlation_id: str | None
    evidence_refs: list[dict[str, Any]]
    payload_subset: dict[str, str]


KNOWN_SOURCE_SYSTEMS = {
    "drive",
    "gmail",
    "jira",
    "github",
    "gitlab",
    "bitbucket",
    "telegram",
    "internal",
}

READ_MODEL_PAYLOAD_FIELDS = (
    "title",
    "subject",
    "name",
    "summary",
    "description",
    "text",
    "source_url",
    "actor_external_id",
)


def _clean_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None

    cleaned = value.strip()
    return cleaned or None


def _bounded(value: str, max_length: int) -> str:
    if len(value) <= max_length:
        return value

    digest = sha256(value.encode("utf-8")).hexdigest()
    return f"{value[: max_length - 72]}:sha256:{digest}"


def _infer_source_object_type(
    *,
    source_system: str,
    event_type: str,
    payload: dict[str, Any],
) -> str:
    explicit_type = _clean_string(payload.get("source_object_type"))
    if explicit_type:
        return _bounded(explicit_type, 120)

    parts = [part for part in event_type.split(".") if part]

    if len(parts) >= 2 and parts[0] == source_system:
        return _bounded(parts[1], 120)

    if len(parts) >= 2 and parts[0] in KNOWN_SOURCE_SYSTEMS:
        return _bounded(parts[1], 120)

    if parts:
        return _bounded(parts[0], 120)

    return "event"


def _build_source_event_key(
    *,
    source_system: str,
    source_object_type: str,
    source_object_id: str,
    event_type: str,
    idempotency_key: str,
) -> str:
    readable_key = ":".join(
        [
            source_system,
            source_object_type,
            source_object_id,
            event_type,
            idempotency_key,
        ]
    )
    return _bounded(readable_key, 500)


def _build_source_event_id(source_event_key: str) -> str:
    digest = sha256(source_event_key.encode("utf-8")).hexdigest()
    return f"sevt_{digest[:32]}"


def _extract_title(payload: dict[str, Any]) -> str | None:
    for key in ("title", "subject", "name"):
        value = _clean_string(payload.get(key))
        if value:
            return _bounded(value, 500)

    return None


def _extract_summary(payload: dict[str, Any]) -> str | None:
    for key in ("summary", "description", "text"):
        value = _clean_string(payload.get(key))
        if value:
            return value

    return None


def _copy_evidence_refs(evidence_refs: Any) -> list[dict[str, Any]]:
    if not isinstance(evidence_refs, list):
        return []

    return [dict(ref) for ref in evidence_refs if isinstance(ref, dict)]


def _build_payload_subset(payload: dict[str, Any] | None) -> dict[str, str]:
    if payload is None:
        return {}

    subset: dict[str, str] = {}
    for field in READ_MODEL_PAYLOAD_FIELDS:
        value = _clean_string(payload.get(field))
        if value:
            subset[field] = value
    return subset


def project_source_event_read_model(
    source_event: SourceEvent,
    *,
    ingested_payload: dict[str, Any] | None = None,
) -> SourceEventReadModel:
    """Project an existing SourceEvent into a deterministic service read model."""

    metadata = source_event.metadata_json if isinstance(source_event.metadata_json, dict) else {}

    return SourceEventReadModel(
        source_event_id=source_event.source_event_id,
        source_system=source_event.source_system,
        source_object_type=source_event.source_object_type,
        source_object_id=source_event.source_object_id,
        event_type=source_event.event_type,
        event_time=source_event.source_event_ts or source_event.created_at,
        title=source_event.title,
        summary=source_event.summary,
        source_url=source_event.source_url,
        raw_object_ref=source_event.raw_object_ref,
        trace_id=_clean_string(metadata.get("trace_id")),
        correlation_id=_clean_string(metadata.get("correlation_id")),
        evidence_refs=_copy_evidence_refs(source_event.evidence_refs),
        payload_subset=_build_payload_subset(ingested_payload),
    )


async def normalize_ingested_event_to_source_event(
    session: AsyncSession,
    ingested_event: IngestedEvent,
) -> SourceEvent:
    """Create an evidence-backed normalized SourceEvent from a raw IngestedEvent.

    This function is deterministic and does not call external APIs.
    The caller controls commit/rollback.
    """

    payload = ingested_event.payload or {}

    source_object_type = _infer_source_object_type(
        source_system=ingested_event.source_system,
        event_type=ingested_event.event_type,
        payload=payload,
    )

    contract_errors = validate_source_event_contract(
        source_system=ingested_event.source_system,
        source_object_type=source_object_type,
        event_type=ingested_event.event_type,
        payload=payload,
    )
    if contract_errors:
        raise SourceEventContractValidationError("; ".join(contract_errors))

    source_event_key = _build_source_event_key(
        source_system=ingested_event.source_system,
        source_object_type=source_object_type,
        source_object_id=ingested_event.source_object_id,
        event_type=ingested_event.event_type,
        idempotency_key=ingested_event.idempotency_key,
    )

    existing = await session.scalar(
        select(SourceEvent).where(SourceEvent.source_event_key == source_event_key)
    )
    if existing:
        return existing

    from app.services.run_context import get_run_id

    source_event = SourceEvent(
        created_by_run_id=get_run_id(),
        source_event_id=_build_source_event_id(source_event_key),
        source_event_key=source_event_key,
        ingested_event_id=ingested_event.event_id,
        event_type=ingested_event.event_type,
        source_system=ingested_event.source_system,
        source_object_type=source_object_type,
        source_object_id=ingested_event.source_object_id,
        source_event_ts=None,
        actor_external_id=_clean_string(payload.get("actor_external_id")),
        title=_extract_title(payload),
        summary=_extract_summary(payload),
        source_url=_clean_string(payload.get("source_url")),
        raw_object_ref=ingested_event.raw_object_ref,
        evidence_refs=[
            {
                "kind": "ingested_event",
                "event_id": ingested_event.event_id,
                "source_system": ingested_event.source_system,
                "source_object_id": ingested_event.source_object_id,
                "raw_object_ref": ingested_event.raw_object_ref,
            }
        ],
        metadata_json={
            "correlation_id": ingested_event.correlation_id,
            "trace_id": ingested_event.trace_id,
            "ingested_event_status": ingested_event.status,
        },
        schema_version="1.0",
    )

    session.add(source_event)
    await session.flush()

    return source_event
