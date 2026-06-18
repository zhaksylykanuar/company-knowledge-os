"""ConnectorEvent ingestion and normalization pipeline.

This stage stays inside FounderOS storage: connector events are already
sanitized DTOs, then they are persisted as IngestedEvent -> SourceEvent and
projected into normalized_activity_items. The service never calls providers.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.event_models import NormalizedActivityItemRecord, SourceEvent
from app.db.models import IngestedEvent
from app.integrations.payload_mapper import map_connector_payload_to_ingested_event
from app.services.browser_config import sanitize_for_logs
from app.services.normalized_activity import (
    SourceEventActivityProjectionError,
    project_source_event_to_normalized_activity_item,
)
from app.services.run_context import get_run_id, set_run_id
from app.services.source_connectors import ConnectorEvent
from app.services.source_events import normalize_ingested_event_to_source_event


@dataclass
class SourceIngestionSummary:
    events_seen: int = 0
    events_ingested: int = 0
    duplicates_skipped: int = 0
    failed_events: int = 0
    normalized_events: int = 0
    normalization_errors: int = 0
    payload_redactions: int = 0
    source_event_ids: list[str] = field(default_factory=list)
    normalized_activity_item_ids: list[str] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "events_seen": self.events_seen,
            "events_ingested": self.events_ingested,
            "duplicates_skipped": self.duplicates_skipped,
            "failed_events": self.failed_events,
            "normalized_events": self.normalized_events,
            "normalization_errors": self.normalization_errors,
            "payload_redactions": self.payload_redactions,
            "source_event_ids": list(self.source_event_ids),
            "normalized_activity_item_ids": list(self.normalized_activity_item_ids),
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


def _json_blob(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _was_redacted(original: dict[str, Any], sanitized: dict[str, Any]) -> bool:
    return _json_blob(original) != _json_blob(sanitized)


def _safe_error(exc: Exception) -> dict[str, str]:
    return {
        "error_type": type(exc).__name__,
        "message": "source event ingestion failed",
    }


async def _existing_normalized(
    session: AsyncSession,
    *,
    source_event_id: str,
) -> NormalizedActivityItemRecord | None:
    return await session.scalar(
        select(NormalizedActivityItemRecord)
        .where(NormalizedActivityItemRecord.source_event_id == source_event_id)
        .order_by(NormalizedActivityItemRecord.id)
    )


async def ingest_connector_events(
    session: AsyncSession,
    *,
    events: list[ConnectorEvent],
    run_id: str | None,
    correlation_id: str | None,
    normalize: bool = True,
) -> dict[str, Any]:
    summary = SourceIngestionSummary(events_seen=len(events))
    previous_run_id = get_run_id()
    set_run_id(run_id)
    try:
        for event in events:
            event_payload = event.to_connector_payload()
            payload = event_payload.get("payload") if isinstance(event_payload, dict) else {}
            sanitized_payload = sanitize_for_logs(payload if isinstance(payload, dict) else {})
            event_payload_was_redacted = event.payload_was_redacted()
            if event_payload_was_redacted:
                summary.payload_redactions += 1
            if isinstance(payload, dict) and isinstance(sanitized_payload, dict):
                if _was_redacted(payload, sanitized_payload) and not event_payload_was_redacted:
                    summary.payload_redactions += 1
                event_payload["payload"] = sanitized_payload
            if correlation_id and not event_payload.get("correlation_id"):
                event_payload["correlation_id"] = correlation_id
            if run_id and not event_payload.get("trace_id"):
                event_payload["trace_id"] = run_id

            try:
                mapped = map_connector_payload_to_ingested_event(event_payload)
                ingested_event = await session.scalar(
                    select(IngestedEvent).where(IngestedEvent.event_id == mapped.event_id)
                )
                if ingested_event is None:
                    ingested_event = IngestedEvent(**mapped.to_ingested_event_kwargs())
                    session.add(ingested_event)
                    await session.flush()

                existing_source_event = await session.scalar(
                    select(SourceEvent).where(
                        SourceEvent.ingested_event_id == ingested_event.event_id
                    )
                )
                source_event = await normalize_ingested_event_to_source_event(
                    session,
                    ingested_event,
                )
                if existing_source_event is None or not source_event.created_by_run_id:
                    source_event.created_by_run_id = run_id
                source_event.source_event_ts = event.occurred_at
                metadata = (
                    dict(source_event.metadata_json)
                    if isinstance(source_event.metadata_json, dict)
                    else {}
                )
                metadata.update(
                    {
                        "run_id": run_id,
                        "correlation_id": correlation_id,
                        "last_seen_run_id": run_id,
                        "content_hash": event.stable_content_hash(),
                        "visibility_scope": event.visibility_scope,
                        "source_metadata": sanitize_for_logs(event.source_metadata),
                    }
                )
                source_event.metadata_json = metadata
                summary.source_event_ids.append(source_event.source_event_id)
                if existing_source_event is None:
                    summary.events_ingested += 1
                else:
                    summary.duplicates_skipped += 1

                if not normalize:
                    continue

                normalized_before = await _existing_normalized(
                    session,
                    source_event_id=source_event.source_event_id,
                )
                try:
                    normalized = await project_source_event_to_normalized_activity_item(
                        session,
                        source_event=source_event,
                    )
                    if normalized_before is None:
                        summary.normalized_events += 1
                    summary.normalized_activity_item_ids.append(
                        normalized.activity_item_id
                    )
                    ingested_event.status = "normalized"
                except SourceEventActivityProjectionError as exc:
                    summary.normalization_errors += 1
                    ingested_event.status = "normalization_failed"
                    metadata = (
                        dict(source_event.metadata_json)
                        if isinstance(source_event.metadata_json, dict)
                        else {}
                    )
                    metadata["normalization_error"] = {
                        "error_type": type(exc).__name__,
                        "message": "source event cannot be projected",
                    }
                    source_event.metadata_json = metadata
                    summary.errors.append(
                        {
                            "source_event_id": source_event.source_event_id,
                            "error_type": type(exc).__name__,
                            "message": "source event cannot be projected",
                        }
                    )
            except Exception as exc:  # noqa: BLE001 - isolate bad connector event.
                summary.failed_events += 1
                summary.errors.append(_safe_error(exc))
        await session.flush()
        return summary.to_dict()
    finally:
        set_run_id(previous_run_id)
