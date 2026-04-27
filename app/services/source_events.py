from __future__ import annotations

from hashlib import sha256
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.event_models import SourceEvent
from app.db.models import IngestedEvent
from app.integrations.source_registry import validate_source_event_contract


class SourceEventContractValidationError(ValueError):
    pass


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

    source_event = SourceEvent(
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
