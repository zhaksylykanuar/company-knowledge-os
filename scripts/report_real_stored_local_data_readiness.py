#!/usr/bin/env python
"""Report read-only readiness for real stored local data manual pilots."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import re
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import func, select

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import prepare_manual_pilot_delivery_draft as prepare_script  # noqa: E402

DEFAULT_WINDOW_SIZE_HOURS = 24
MAX_WINDOW_SIZE_HOURS = 24 * 31
DEFAULT_MAX_WINDOWS = 31
MAX_READINESS_WINDOWS = 90
SYNTHETIC_SOURCE_OBJECT_PREFIX = "local.synthetic.persisted_attention_seed:"
SAFE_COUNT_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{1,120}$")
UNSAFE_COUNT_KEY_MARKERS = (
    "://",
    "api_key",
    "bot_token",
    "chat_id",
    "credential",
    "secret",
    "token",
    "webhook",
)


class RealStoredReadinessInputError(ValueError):
    pass


class RealStoredReadinessBlockedError(RuntimeError):
    pass


class RealStoredReadinessRuntimeError(RuntimeError):
    pass


@dataclass(frozen=True)
class RealStoredReadinessQuery:
    start_at: datetime
    end_at: datetime
    window_size_hours: int = DEFAULT_WINDOW_SIZE_HOURS
    max_windows: int = DEFAULT_MAX_WINDOWS
    include_empty: bool = False
    output_format: str = "json"


def _parse_datetime(value: str, *, field_name: str) -> datetime:
    try:
        return prepare_script._parse_datetime(value, field_name=field_name)
    except prepare_script.PrepareInputError as exc:
        raise RealStoredReadinessInputError(str(exc)) from exc


def _clean_window_size_hours(value: int) -> int:
    if not isinstance(value, int):
        raise RealStoredReadinessInputError("window_size_hours must be an integer")
    if value < 1 or value > MAX_WINDOW_SIZE_HOURS:
        raise RealStoredReadinessInputError(
            f"window_size_hours must be between 1 and {MAX_WINDOW_SIZE_HOURS}"
        )
    return value


def _clean_max_windows(value: int) -> int:
    if not isinstance(value, int):
        raise RealStoredReadinessInputError("max_windows must be an integer")
    if value < 1 or value > MAX_READINESS_WINDOWS:
        raise RealStoredReadinessInputError(
            f"max_windows must be between 1 and {MAX_READINESS_WINDOWS}"
        )
    return value


def _planned_window_count(
    *,
    start_at: datetime,
    end_at: datetime,
    window_size_hours: int,
) -> int:
    total_seconds = (end_at - start_at).total_seconds()
    window_seconds = window_size_hours * 60 * 60
    return int(math.ceil(total_seconds / window_seconds))


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--start-at",
        required=True,
        help="Timezone-aware ISO start for the readiness discovery range.",
    )
    parser.add_argument(
        "--end-at",
        required=True,
        help="Timezone-aware ISO end for the readiness discovery range.",
    )
    parser.add_argument(
        "--window-size-hours",
        type=int,
        default=DEFAULT_WINDOW_SIZE_HOURS,
        help=(
            "Candidate window size in hours, "
            f"1-{MAX_WINDOW_SIZE_HOURS}; default {DEFAULT_WINDOW_SIZE_HOURS}."
        ),
    )
    parser.add_argument(
        "--max-windows",
        type=int,
        default=DEFAULT_MAX_WINDOWS,
        help=(
            "Maximum candidate windows to scan, "
            f"1-{MAX_READINESS_WINDOWS}; default {DEFAULT_MAX_WINDOWS}."
        ),
    )
    parser.add_argument(
        "--include-empty",
        action="store_true",
        help="Include windows with no source, normalized activity, or attention rows.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="json",
        help="Output format.",
    )
    return parser.parse_args(argv)


def _query_from_args(args: argparse.Namespace) -> RealStoredReadinessQuery:
    start_at = _parse_datetime(args.start_at, field_name="start_at")
    end_at = _parse_datetime(args.end_at, field_name="end_at")
    if end_at <= start_at:
        raise RealStoredReadinessInputError("end_at must be after start_at")
    window_size_hours = _clean_window_size_hours(args.window_size_hours)
    max_windows = _clean_max_windows(args.max_windows)
    planned_count = _planned_window_count(
        start_at=start_at,
        end_at=end_at,
        window_size_hours=window_size_hours,
    )
    if planned_count > max_windows:
        raise RealStoredReadinessInputError(
            f"range would scan {planned_count} windows; max_windows is {max_windows}"
        )
    return RealStoredReadinessQuery(
        start_at=start_at,
        end_at=end_at,
        window_size_hours=window_size_hours,
        max_windows=max_windows,
        include_empty=bool(args.include_empty),
        output_format=args.format,
    )


def _candidate_windows(
    query: RealStoredReadinessQuery,
) -> list[tuple[datetime, datetime]]:
    step = timedelta(hours=query.window_size_hours)
    windows: list[tuple[datetime, datetime]] = []
    cursor = query.start_at
    while cursor < query.end_at:
        window_end = min(cursor + step, query.end_at)
        windows.append((cursor, window_end))
        if len(windows) > query.max_windows:
            raise RealStoredReadinessInputError(
                f"range would scan more than {query.max_windows} windows"
            )
        cursor = window_end
    return windows


def _safe_int(value: Any) -> int:
    return int(value) if isinstance(value, int) and not isinstance(value, bool) else 0


def _safe_count_key(value: Any) -> str:
    if not isinstance(value, str):
        return "unknown"
    cleaned = value.strip()
    if not cleaned:
        return "unknown"
    folded = cleaned.casefold()
    if any(marker in folded for marker in UNSAFE_COUNT_KEY_MARKERS):
        return "unsafe_or_unknown"
    if not SAFE_COUNT_KEY_PATTERN.fullmatch(cleaned):
        return "unsafe_or_unknown"
    return cleaned


async def _count_by(
    session: Any,
    *,
    column: Any,
    filters: tuple[Any, ...],
) -> dict[str, int]:
    rows = (
        await session.execute(
            select(column, func.count()).where(*filters).group_by(column)
        )
    ).all()
    counts: dict[str, int] = {}
    for raw_key, raw_count in rows:
        key = _safe_count_key(raw_key)
        counts[key] = counts.get(key, 0) + int(raw_count or 0)
    return dict(sorted(counts.items()))


async def _count_total(
    session: Any,
    *,
    model: Any,
    filters: tuple[Any, ...],
) -> int:
    return int(
        await session.scalar(select(func.count()).select_from(model).where(*filters))
        or 0
    )


async def _source_event_ids(
    session: Any,
    *,
    filters: tuple[Any, ...],
) -> set[str]:
    from app.db.event_models import SourceEvent

    values = (
        await session.scalars(select(SourceEvent.source_event_id).where(*filters))
    ).all()
    return {value for value in values if isinstance(value, str) and value}


async def _normalized_activity_ids(
    session: Any,
    *,
    filters: tuple[Any, ...],
) -> set[str]:
    from app.db.event_models import NormalizedActivityItemRecord

    values = (
        await session.scalars(
            select(NormalizedActivityItemRecord.activity_item_id).where(*filters)
        )
    ).all()
    return {value for value in values if isinstance(value, str) and value}


async def _linked_normalized_source_event_ids(
    session: Any,
    *,
    source_event_ids: set[str],
) -> set[str]:
    from app.db.event_models import NormalizedActivityItemRecord

    if not source_event_ids:
        return set()
    values = (
        await session.scalars(
            select(NormalizedActivityItemRecord.source_event_id)
            .where(NormalizedActivityItemRecord.source_event_id.in_(source_event_ids))
            .where(NormalizedActivityItemRecord.source_event_id.is_not(None))
        )
    ).all()
    return {value for value in values if isinstance(value, str) and value}


async def _linked_attention_activity_item_ids(
    session: Any,
    *,
    activity_item_ids: set[str],
) -> set[str]:
    from app.db.attention_models import AttentionTriageResultRecord

    if not activity_item_ids:
        return set()
    values = (
        await session.scalars(
            select(AttentionTriageResultRecord.activity_item_id)
            .where(AttentionTriageResultRecord.activity_item_id.in_(activity_item_ids))
            .where(AttentionTriageResultRecord.activity_item_id.is_not(None))
        )
    ).all()
    return {value for value in values if isinstance(value, str) and value}


def _marker_status(*, synthetic_count: int, no_marker_count: int, total: int) -> str:
    if total < 1:
        return "unknown"
    if synthetic_count > 0 and no_marker_count > 0:
        return "mixed"
    if synthetic_count > 0:
        return "synthetic_local_dev_detected"
    return "no_synthetic_marker_detected"


async def _source_event_summary(
    session: Any,
    *,
    start_at: datetime,
    end_at: datetime,
) -> tuple[dict[str, Any], set[str]]:
    from app.db.event_models import SourceEvent

    activity_time = func.coalesce(SourceEvent.source_event_ts, SourceEvent.created_at)
    filters = (
        activity_time >= start_at,
        activity_time < end_at,
    )
    total = await _count_total(session, model=SourceEvent, filters=filters)
    synthetic_count = await _count_total(
        session,
        model=SourceEvent,
        filters=(
            *filters,
            SourceEvent.source_system == "internal",
            SourceEvent.source_object_id.like(f"{SYNTHETIC_SOURCE_OBJECT_PREFIX}%"),
        ),
    )
    return (
        {
            "total": total,
            "by_source_system": await _count_by(
                session,
                column=SourceEvent.source_system,
                filters=filters,
            ),
            "by_source_object_type": await _count_by(
                session,
                column=SourceEvent.source_object_type,
                filters=filters,
            ),
            "by_event_type": await _count_by(
                session,
                column=SourceEvent.event_type,
                filters=filters,
            ),
            "synthetic_marker_count": synthetic_count,
            "no_marker_count": max(total - synthetic_count, 0),
        },
        await _source_event_ids(session, filters=filters),
    )


async def _normalized_activity_summary(
    session: Any,
    *,
    start_at: datetime,
    end_at: datetime,
) -> tuple[dict[str, Any], set[str]]:
    from app.db.event_models import NormalizedActivityItemRecord

    activity_time = func.coalesce(
        NormalizedActivityItemRecord.activity_created_at,
        NormalizedActivityItemRecord.created_at,
    )
    filters = (
        activity_time >= start_at,
        activity_time < end_at,
    )
    total = await _count_total(
        session,
        model=NormalizedActivityItemRecord,
        filters=filters,
    )
    synthetic_count = await _count_total(
        session,
        model=NormalizedActivityItemRecord,
        filters=(
            *filters,
            NormalizedActivityItemRecord.source == "internal",
            NormalizedActivityItemRecord.source_object_id.like(
                f"{SYNTHETIC_SOURCE_OBJECT_PREFIX}%"
            ),
        ),
    )
    return (
        {
            "total": total,
            "by_source": await _count_by(
                session,
                column=NormalizedActivityItemRecord.source,
                filters=filters,
            ),
            "by_activity_type": await _count_by(
                session,
                column=NormalizedActivityItemRecord.activity_type,
                filters=filters,
            ),
            "synthetic_marker_count": synthetic_count,
            "no_marker_count": max(total - synthetic_count, 0),
        },
        await _normalized_activity_ids(session, filters=filters),
    )


async def _attention_result_summary(
    session: Any,
    *,
    start_at: datetime,
    end_at: datetime,
) -> dict[str, Any]:
    from app.db.attention_models import AttentionTriageResultRecord

    filters = (
        AttentionTriageResultRecord.created_at >= start_at,
        AttentionTriageResultRecord.created_at < end_at,
    )
    visible_filter = (*filters, AttentionTriageResultRecord.show_in_digest.is_(True))
    total = await _count_total(
        session,
        model=AttentionTriageResultRecord,
        filters=filters,
    )
    visible_count = await _count_total(
        session,
        model=AttentionTriageResultRecord,
        filters=visible_filter,
    )
    synthetic_count = await _count_total(
        session,
        model=AttentionTriageResultRecord,
        filters=(
            *filters,
            AttentionTriageResultRecord.source == "internal",
            AttentionTriageResultRecord.source_object_id.like(
                f"{SYNTHETIC_SOURCE_OBJECT_PREFIX}%"
            ),
        ),
    )
    visible_synthetic_count = await _count_total(
        session,
        model=AttentionTriageResultRecord,
        filters=(
            *visible_filter,
            AttentionTriageResultRecord.source == "internal",
            AttentionTriageResultRecord.source_object_id.like(
                f"{SYNTHETIC_SOURCE_OBJECT_PREFIX}%"
            ),
        ),
    )
    return {
        "total": total,
        "visible_persisted_attention_candidate_count": visible_count,
        "hidden_count": max(total - visible_count, 0),
        "by_attention_class": await _count_by(
            session,
            column=AttentionTriageResultRecord.attention_class,
            filters=filters,
        ),
        "by_priority": await _count_by(
            session,
            column=AttentionTriageResultRecord.priority,
            filters=filters,
        ),
        "by_source": await _count_by(
            session,
            column=AttentionTriageResultRecord.source,
            filters=filters,
        ),
        "synthetic_marker_count": synthetic_count,
        "no_marker_count": max(total - synthetic_count, 0),
        "visible_synthetic_marker_count": visible_synthetic_count,
        "visible_no_marker_count": max(visible_count - visible_synthetic_count, 0),
    }


def _pipeline_coverage(
    *,
    source_events: Mapping[str, Any],
    normalized_activity: Mapping[str, Any],
    attention_results: Mapping[str, Any],
    source_event_ids: set[str],
    linked_normalized_source_event_ids: set[str],
    normalized_activity_ids: set[str],
    linked_attention_activity_item_ids: set[str],
) -> dict[str, Any]:
    visible_no_marker_count = _safe_int(attention_results.get("visible_no_marker_count"))
    visible_count = _safe_int(
        attention_results.get("visible_persisted_attention_candidate_count")
    )
    return {
        "has_source_events": _safe_int(source_events.get("total")) > 0,
        "has_normalized_activity_items": _safe_int(normalized_activity.get("total")) > 0,
        "has_attention_results": _safe_int(attention_results.get("total")) > 0,
        "has_visible_persisted_attention_candidates": visible_count > 0,
        "source_only_count": len(source_event_ids - linked_normalized_source_event_ids),
        "source_with_normalized_count": len(linked_normalized_source_event_ids),
        "normalized_with_attention_count": len(linked_attention_activity_item_ids),
        "pipeline_ready_for_manual_digest_pilot": visible_no_marker_count > 0,
    }


def _synthetic_status_for_window(
    *,
    source_events: Mapping[str, Any],
    normalized_activity: Mapping[str, Any],
    attention_results: Mapping[str, Any],
) -> str:
    synthetic_count = (
        _safe_int(source_events.get("synthetic_marker_count"))
        + _safe_int(normalized_activity.get("synthetic_marker_count"))
        + _safe_int(attention_results.get("synthetic_marker_count"))
    )
    no_marker_count = (
        _safe_int(source_events.get("no_marker_count"))
        + _safe_int(normalized_activity.get("no_marker_count"))
        + _safe_int(attention_results.get("no_marker_count"))
    )
    return _marker_status(
        synthetic_count=synthetic_count,
        no_marker_count=no_marker_count,
        total=synthetic_count + no_marker_count,
    )


def _recommended_next_action(
    *,
    source_events: Mapping[str, Any],
    normalized_activity: Mapping[str, Any],
    attention_results: Mapping[str, Any],
    synthetic_status: str,
) -> str:
    source_total = _safe_int(source_events.get("total"))
    normalized_total = _safe_int(normalized_activity.get("total"))
    attention_total = _safe_int(attention_results.get("total"))
    visible_count = _safe_int(
        attention_results.get("visible_persisted_attention_candidate_count")
    )
    visible_synthetic_count = _safe_int(
        attention_results.get("visible_synthetic_marker_count")
    )
    visible_no_marker_count = _safe_int(attention_results.get("visible_no_marker_count"))

    if source_total == 0 and normalized_total == 0 and attention_total == 0:
        return "no_real_stored_candidates_found"
    if source_total > 0 and normalized_total == 0 and attention_total == 0:
        return "project_source_events_before_real_pilot"
    if normalized_total > 0 and attention_total == 0:
        return "triage_normalized_activity_before_real_pilot"
    if attention_total > 0 and visible_count == 0:
        return "review_attention_results_visibility_before_real_pilot"
    if visible_count > 0 and visible_no_marker_count > 0:
        return "review_no_marker_window_before_manual_pilot"
    if visible_count > 0 and visible_synthetic_count > 0 and synthetic_status != "mixed":
        return "continue_synthetic_manual_pilot_or_find_non_synthetic_window"
    if visible_count > 0:
        return "candidate_window_ready_for_manual_status_report"
    return "no_real_stored_candidates_found"


def _window_limitations(*, synthetic_status: str) -> list[str]:
    notes = [
        "readiness_summarizes_counts_only_not_company_facts",
        "pipeline_coverage_uses_stored_row_linkage_only",
        "delivery_lifecycle_not_evaluated_use_persisted_attention_window_discovery",
        "row_details_are_omitted_count_only_report",
    ]
    if synthetic_status == "synthetic_local_dev_detected":
        notes.append("synthetic_status_detected_from_safe_local_seed_marker")
    elif synthetic_status == "mixed":
        notes.append("mixed_marker_window_requires_human_review_before_manual_pilot")
    elif synthetic_status == "no_synthetic_marker_detected":
        notes.append("no_synthetic_marker_is_not_proof_of_production_truth")
    else:
        notes.append("no_rows_available_to_determine_synthetic_marker_status")
    return notes


def _aggregate_summary(windows: list[dict[str, Any]]) -> dict[str, int]:
    def action_count(action: str) -> int:
        return sum(
            1 for window in windows if window.get("recommended_next_action") == action
        )

    return {
        "window_count": len(windows),
        "non_empty_source_window_count": sum(
            1 for window in windows if _safe_int(window["source_events"].get("total")) > 0
        ),
        "non_empty_normalized_window_count": sum(
            1
            for window in windows
            if _safe_int(window["normalized_activity"].get("total")) > 0
        ),
        "non_empty_attention_window_count": sum(
            1
            for window in windows
            if _safe_int(window["attention_results"].get("total")) > 0
        ),
        "visible_attention_candidate_window_count": sum(
            1
            for window in windows
            if _safe_int(
                window["attention_results"].get(
                    "visible_persisted_attention_candidate_count"
                )
            )
            > 0
        ),
        "synthetic_local_dev_window_count": sum(
            1
            for window in windows
            if window.get("synthetic_status") == "synthetic_local_dev_detected"
        ),
        "no_synthetic_marker_window_count": sum(
            1
            for window in windows
            if window.get("synthetic_status") == "no_synthetic_marker_detected"
        ),
        "mixed_marker_window_count": sum(
            1 for window in windows if window.get("synthetic_status") == "mixed"
        ),
        "ready_for_manual_digest_pilot_window_count": sum(
            1
            for window in windows
            if window["pipeline_coverage"].get("pipeline_ready_for_manual_digest_pilot")
            is True
        ),
        "source_only_window_count": sum(
            1
            for window in windows
            if _safe_int(window["pipeline_coverage"].get("source_only_count")) > 0
        ),
        "needs_normalization_window_count": action_count(
            "project_source_events_before_real_pilot"
        ),
        "needs_attention_triage_window_count": action_count(
            "triage_normalized_activity_before_real_pilot"
        ),
    }


def _safety_metadata() -> dict[str, Any]:
    return {
        "provider_free": True,
        "read_only": True,
        "local_operator_command": True,
        "db_write_scope": "none",
        "source_events_created": False,
        "normalized_activity_created": False,
        "attention_results_created": False,
        "approval_created": False,
        "rejection_created": False,
        "delivery_draft_created": False,
        "delivery_intention_created": False,
        "telegram_plan_created": False,
        "preflight_created": False,
        "execution_gate_created": False,
        "delivery_result_created": False,
        "delivery_invoked": False,
        "delivery_adapter_invoked": False,
        "approval_execution_invoked": False,
        "scheduler_invoked": False,
        "outbox_record_created": False,
        "delivery_worker_invoked": False,
        "api_clients_invoked": False,
        "connectors_invoked": False,
        "live_api_calls": False,
        "openai_invoked": False,
        "telegram_invoked": False,
        "slack_invoked": False,
        "credential_values_exposed": False,
        "stored_digest_text_included": False,
        "chunk_text_included": False,
        "raw_content_exposed": False,
        "item_details_included": False,
        "evidence_refs_included": False,
        "raw_storage_touched": False,
        "obsidian_touched": False,
        "production_mode": False,
        "report_is_source_of_truth": False,
        "telegram_is_source_of_truth": False,
    }


async def _window_summary(
    session: Any,
    *,
    start_at: datetime,
    end_at: datetime,
) -> dict[str, Any]:
    source_events, source_event_ids = await _source_event_summary(
        session,
        start_at=start_at,
        end_at=end_at,
    )
    normalized_activity, normalized_activity_ids = await _normalized_activity_summary(
        session,
        start_at=start_at,
        end_at=end_at,
    )
    attention_results = await _attention_result_summary(
        session,
        start_at=start_at,
        end_at=end_at,
    )
    linked_normalized_source_event_ids = await _linked_normalized_source_event_ids(
        session,
        source_event_ids=source_event_ids,
    )
    linked_attention_activity_item_ids = await _linked_attention_activity_item_ids(
        session,
        activity_item_ids=normalized_activity_ids,
    )
    pipeline_coverage = _pipeline_coverage(
        source_events=source_events,
        normalized_activity=normalized_activity,
        attention_results=attention_results,
        source_event_ids=source_event_ids,
        linked_normalized_source_event_ids=linked_normalized_source_event_ids,
        normalized_activity_ids=normalized_activity_ids,
        linked_attention_activity_item_ids=linked_attention_activity_item_ids,
    )
    synthetic_status = _synthetic_status_for_window(
        source_events=source_events,
        normalized_activity=normalized_activity,
        attention_results=attention_results,
    )
    return {
        "start_at": start_at.isoformat(),
        "end_at": end_at.isoformat(),
        "source_events": source_events,
        "normalized_activity": normalized_activity,
        "attention_results": attention_results,
        "pipeline_coverage": pipeline_coverage,
        "synthetic_status": synthetic_status,
        "recommended_next_action": _recommended_next_action(
            source_events=source_events,
            normalized_activity=normalized_activity,
            attention_results=attention_results,
            synthetic_status=synthetic_status,
        ),
        "limitations": _window_limitations(synthetic_status=synthetic_status),
    }


def _has_any_rows(window: Mapping[str, Any]) -> bool:
    return (
        _safe_int(window["source_events"].get("total"))
        + _safe_int(window["normalized_activity"].get("total"))
        + _safe_int(window["attention_results"].get("total"))
    ) > 0


async def build_real_stored_local_data_readiness_report(
    query: RealStoredReadinessQuery,
    *,
    session_factory: Callable[[], Any] | None = None,
    settings_override: Any | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    from app.core.config import settings
    from app.db.base import AsyncSessionLocal

    try:
        prepare_script._assert_local_environment(
            settings=settings_override or settings,
            environ=environ if environ is not None else os.environ,
        )
    except prepare_script.PrepareBlockedError as exc:
        raise RealStoredReadinessBlockedError(str(exc)) from exc

    candidate_windows = _candidate_windows(query)
    session_factory = session_factory or AsyncSessionLocal
    scanned_windows: list[dict[str, Any]] = []

    try:
        async with session_factory() as session:
            for start_at, end_at in candidate_windows:
                scanned_windows.append(
                    await _window_summary(
                        session,
                        start_at=start_at,
                        end_at=end_at,
                    )
                )
    except (
        RealStoredReadinessInputError,
        RealStoredReadinessBlockedError,
        RealStoredReadinessRuntimeError,
    ):
        raise
    except ValueError as exc:
        raise RealStoredReadinessInputError(str(exc)) from exc
    except Exception as exc:
        raise RealStoredReadinessRuntimeError(
            "real stored local data readiness report blocked; database, schema, or configuration is unavailable"
        ) from exc

    returned_windows = [
        window for window in scanned_windows if query.include_empty or _has_any_rows(window)
    ]
    return {
        "status": "real_stored_local_data_readiness",
        "start_at": query.start_at.isoformat(),
        "end_at": query.end_at.isoformat(),
        "window_size_hours": query.window_size_hours,
        "max_windows": query.max_windows,
        "include_empty": query.include_empty,
        "scanned_window_count": len(scanned_windows),
        "returned_window_count": len(returned_windows),
        "windows": returned_windows,
        "aggregate_summary": _aggregate_summary(scanned_windows),
        "safety": _safety_metadata(),
        "limitations": [
            "readiness_discovery_reports_counts_only_not_company_facts",
            "absence_of_synthetic_marker_is_not_proof_of_production_truth",
            "delivery_lifecycle_not_evaluated_use_persisted_attention_window_discovery",
        ],
    }


def _blocked_result(*, error_code: str, message: str) -> dict[str, Any]:
    return {
        "status": "blocked",
        "error_code": error_code,
        "message": message,
        "safety": _safety_metadata(),
    }


def _print_json(value: Mapping[str, Any]) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def format_text_report(report: Mapping[str, Any]) -> str:
    aggregate = (
        report.get("aggregate_summary")
        if isinstance(report.get("aggregate_summary"), Mapping)
        else {}
    )
    safety = report.get("safety") if isinstance(report.get("safety"), Mapping) else {}
    lines = [
        "Real stored local data readiness (read-only; no send)",
        f"Range start: {report.get('start_at')}",
        f"Range end: {report.get('end_at')}",
        f"Window size hours: {report.get('window_size_hours')}",
        f"Scanned windows: {report.get('scanned_window_count')}",
        f"Returned windows: {report.get('returned_window_count')}",
        f"Source windows: {aggregate.get('non_empty_source_window_count')}",
        f"Normalized windows: {aggregate.get('non_empty_normalized_window_count')}",
        f"Attention windows: {aggregate.get('non_empty_attention_window_count')}",
        "Visible attention candidate windows: "
        f"{aggregate.get('visible_attention_candidate_window_count')}",
        "Ready for manual digest pilot windows: "
        f"{aggregate.get('ready_for_manual_digest_pilot_window_count')}",
        "Synthetic local/dev windows: "
        f"{aggregate.get('synthetic_local_dev_window_count')}",
        "No synthetic marker windows: "
        f"{aggregate.get('no_synthetic_marker_window_count')}",
        f"Mixed marker windows: {aggregate.get('mixed_marker_window_count')}",
        "",
        "Candidate windows:",
    ]
    windows = report.get("windows") if isinstance(report.get("windows"), list) else []
    if not windows:
        lines.append("- none returned")
    for window in windows:
        if not isinstance(window, Mapping):
            continue
        source_events = (
            window.get("source_events")
            if isinstance(window.get("source_events"), Mapping)
            else {}
        )
        normalized = (
            window.get("normalized_activity")
            if isinstance(window.get("normalized_activity"), Mapping)
            else {}
        )
        attention = (
            window.get("attention_results")
            if isinstance(window.get("attention_results"), Mapping)
            else {}
        )
        coverage = (
            window.get("pipeline_coverage")
            if isinstance(window.get("pipeline_coverage"), Mapping)
            else {}
        )
        lines.extend(
            [
                f"- Window: {window.get('start_at')} -> {window.get('end_at')}",
                f"  Source events: {source_events.get('total')}",
                f"  Normalized activity: {normalized.get('total')}",
                f"  Attention results: {attention.get('total')}",
                "  Visible persisted attention candidates: "
                f"{attention.get('visible_persisted_attention_candidate_count')}",
                f"  Synthetic status: {window.get('synthetic_status')}",
                "  Pipeline ready for manual digest pilot: "
                f"{coverage.get('pipeline_ready_for_manual_digest_pilot')}",
                f"  Recommended next action: {window.get('recommended_next_action')}",
            ]
        )
    lines.extend(
        [
            "",
            f"Read-only: {safety.get('read_only')}",
            f"DB write scope: {safety.get('db_write_scope')}",
            f"Source events created: {safety.get('source_events_created')}",
            "Normalized activity created: "
            f"{safety.get('normalized_activity_created')}",
            f"Attention results created: {safety.get('attention_results_created')}",
            f"Delivery draft created: {safety.get('delivery_draft_created')}",
            f"Delivery intention created: {safety.get('delivery_intention_created')}",
            f"Delivery result created: {safety.get('delivery_result_created')}",
            f"Delivery invoked: {safety.get('delivery_invoked')}",
            f"Telegram invoked: {safety.get('telegram_invoked')}",
            f"Scheduler invoked: {safety.get('scheduler_invoked')}",
        ]
    )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parse_args(argv)
        query = _query_from_args(args)
        report = asyncio.run(build_real_stored_local_data_readiness_report(query))
    except RealStoredReadinessInputError as exc:
        output_format = getattr(locals().get("args", None), "format", "json")
        if output_format == "json":
            _print_json(_blocked_result(error_code="input_error", message=str(exc)))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 2
    except RealStoredReadinessBlockedError as exc:
        output_format = getattr(locals().get("args", None), "format", "json")
        if output_format == "json":
            _print_json(_blocked_result(error_code="blocked", message=str(exc)))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 1
    except RealStoredReadinessRuntimeError as exc:
        output_format = getattr(locals().get("args", None), "format", "json")
        if output_format == "json":
            _print_json(_blocked_result(error_code="runtime_error", message=str(exc)))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 1

    if query.output_format == "json":
        _print_json(report)
    else:
        print(format_text_report(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
