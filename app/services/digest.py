from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.engine import Row

from app.db.base import AsyncSessionLocal
from app.db.event_models import SourceEvent

DEFAULT_DIGEST_ENTRY_LIMIT = 20
MAX_DIGEST_ENTRY_LIMIT = 50


def _require_aware_datetime(value: datetime, *, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


def _safe_limit(limit: int) -> int:
    try:
        parsed = int(limit)
    except (TypeError, ValueError):
        return DEFAULT_DIGEST_ENTRY_LIMIT

    if parsed < 1:
        return DEFAULT_DIGEST_ENTRY_LIMIT

    return min(parsed, MAX_DIGEST_ENTRY_LIMIT)


def _count_dict(rows: Sequence[tuple[str | None, int]]) -> dict[str, int]:
    return {
        str(key): count
        for key, count in sorted(rows, key=lambda row: str(row[0]))
        if key is not None
    }


def _count_pairs(rows: Sequence[Row[tuple[str, int]]]) -> list[tuple[str, int]]:
    return [(row[0], row[1]) for row in rows]


def _activity_time(source_event: SourceEvent) -> datetime | None:
    return source_event.source_event_ts or source_event.created_at


def _iso_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None

    return value.isoformat()


def _source_event_evidence_refs(source_event: SourceEvent) -> list[dict[str, Any]]:
    evidence_refs: list[dict[str, Any]] = [
        {
            "kind": "source_event",
            "source_event_id": source_event.source_event_id,
            "source_system": source_event.source_system,
            "source_object_type": source_event.source_object_type,
            "source_object_id": source_event.source_object_id,
            "event_type": source_event.event_type,
            "raw_object_ref": source_event.raw_object_ref,
        }
    ]

    if isinstance(source_event.evidence_refs, list):
        evidence_refs.extend(
            dict(evidence_ref)
            for evidence_ref in source_event.evidence_refs
            if isinstance(evidence_ref, dict)
        )

    return evidence_refs


def _digest_entry(source_event: SourceEvent) -> dict[str, Any]:
    return {
        "source_event_id": source_event.source_event_id,
        "source_system": source_event.source_system,
        "source_object_type": source_event.source_object_type,
        "source_object_id": source_event.source_object_id,
        "event_type": source_event.event_type,
        "event_time": _iso_datetime(_activity_time(source_event)),
        "actor_external_id": source_event.actor_external_id,
        "title": source_event.title,
        "source_url": source_event.source_url,
        "evidence_refs": _source_event_evidence_refs(source_event),
    }


async def build_source_activity_digest(
    *,
    start_at: datetime,
    end_at: datetime,
    limit: int = DEFAULT_DIGEST_ENTRY_LIMIT,
) -> dict[str, Any]:
    """Build a deterministic digest of persisted source activity for a time window.

    This digest reads stored SourceEvent rows only. It does not call LLMs, infer
    tasks/risks/decisions, fetch connector data, or mutate source data.
    """

    _require_aware_datetime(start_at, field_name="start_at")
    _require_aware_datetime(end_at, field_name="end_at")

    if end_at <= start_at:
        raise ValueError("end_at must be after start_at")

    safe_limit = _safe_limit(limit)
    activity_time = func.coalesce(SourceEvent.source_event_ts, SourceEvent.created_at)
    window_filters = (
        activity_time >= start_at,
        activity_time < end_at,
    )

    async with AsyncSessionLocal() as session:
        total_count = (
            await session.execute(
                select(func.count(SourceEvent.id)).where(*window_filters)
            )
        ).scalar_one()

        source_system_counts = (
            await session.execute(
                select(SourceEvent.source_system, func.count(SourceEvent.id))
                .where(*window_filters)
                .group_by(SourceEvent.source_system)
            )
        ).all()
        source_system_count_pairs = _count_pairs(source_system_counts)
        event_type_counts = (
            await session.execute(
                select(SourceEvent.event_type, func.count(SourceEvent.id))
                .where(*window_filters)
                .group_by(SourceEvent.event_type)
            )
        ).all()
        event_type_count_pairs = _count_pairs(event_type_counts)
        source_object_type_counts = (
            await session.execute(
                select(SourceEvent.source_object_type, func.count(SourceEvent.id))
                .where(*window_filters)
                .group_by(SourceEvent.source_object_type)
            )
        ).all()
        source_object_type_count_pairs = _count_pairs(source_object_type_counts)

        source_events = list(
            (
                await session.execute(
                    select(SourceEvent)
                    .where(*window_filters)
                    .order_by(desc(activity_time), desc(SourceEvent.id))
                    .limit(safe_limit)
                )
            )
            .scalars()
            .all()
        )

    entries = [_digest_entry(source_event) for source_event in source_events]

    return {
        "digest_type": "source_activity",
        "window": {
            "start_at": start_at.isoformat(),
            "end_at": end_at.isoformat(),
        },
        "counts": {
            "total": total_count,
            "by_source_system": _count_dict(source_system_count_pairs),
            "by_event_type": _count_dict(event_type_count_pairs),
            "by_source_object_type": _count_dict(source_object_type_count_pairs),
        },
        "entries": entries,
        "metadata": {
            "entry_limit": safe_limit,
            "entry_count": len(entries),
            "truncated": total_count > len(entries),
            "source_model": "source_events",
            "llm_used": False,
        },
    }
