#!/usr/bin/env python
"""Preview stored SourceEvent normalization eligibility without writing rows."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.services.source_activity import (  # noqa: E402
    SourceActivityMappingError,
    source_event_to_activity_item,
)
from scripts import prepare_manual_pilot_delivery_draft as prepare_script  # noqa: E402

DEFAULT_MAX_EVENTS = 100
MAX_NORMALIZATION_PREVIEW_EVENTS = 500
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


class NormalizationPreviewInputError(ValueError):
    pass


class NormalizationPreviewBlockedError(RuntimeError):
    pass


class NormalizationPreviewRuntimeError(RuntimeError):
    pass


@dataclass(frozen=True)
class NormalizationPreviewQuery:
    start_at: datetime
    end_at: datetime
    max_events: int = DEFAULT_MAX_EVENTS
    include_synthetic: bool = False
    output_format: str = "json"


def _parse_datetime(value: str, *, field_name: str) -> datetime:
    try:
        return prepare_script._parse_datetime(value, field_name=field_name)
    except prepare_script.PrepareInputError as exc:
        raise NormalizationPreviewInputError(str(exc)) from exc


def _clean_max_events(value: int) -> int:
    if not isinstance(value, int):
        raise NormalizationPreviewInputError("max_events must be an integer")
    if value < 1 or value > MAX_NORMALIZATION_PREVIEW_EVENTS:
        raise NormalizationPreviewInputError(
            f"max_events must be between 1 and {MAX_NORMALIZATION_PREVIEW_EVENTS}"
        )
    return value


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--start-at",
        required=True,
        help="Timezone-aware ISO start for the source event preview window.",
    )
    parser.add_argument(
        "--end-at",
        required=True,
        help="Timezone-aware ISO end for the source event preview window.",
    )
    parser.add_argument(
        "--max-events",
        type=int,
        default=DEFAULT_MAX_EVENTS,
        help=(
            "Maximum stored source events to scan, "
            f"1-{MAX_NORMALIZATION_PREVIEW_EVENTS}; default {DEFAULT_MAX_EVENTS}."
        ),
    )
    parser.add_argument(
        "--include-synthetic",
        action="store_true",
        help="Include clearly synthetic local/dev source events in the preview.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="json",
        help="Output format.",
    )
    return parser.parse_args(argv)


def _query_from_args(args: argparse.Namespace) -> NormalizationPreviewQuery:
    start_at = _parse_datetime(args.start_at, field_name="start_at")
    end_at = _parse_datetime(args.end_at, field_name="end_at")
    if end_at <= start_at:
        raise NormalizationPreviewInputError("end_at must be after start_at")
    return NormalizationPreviewQuery(
        start_at=start_at,
        end_at=end_at,
        max_events=_clean_max_events(args.max_events),
        include_synthetic=bool(args.include_synthetic),
        output_format=args.format,
    )


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


def _bump(counts: dict[str, int], raw_key: Any, *, amount: int = 1) -> None:
    key = _safe_count_key(raw_key)
    counts[key] = counts.get(key, 0) + amount


def _synthetic_status(*, synthetic_count: int, no_marker_count: int, total: int) -> str:
    if total < 1:
        return "unknown"
    if synthetic_count > 0 and no_marker_count > 0:
        return "mixed"
    if synthetic_count > 0:
        return "synthetic_local_dev_detected"
    return "no_synthetic_marker_detected"


def _is_synthetic_source_event(source_event: Any) -> bool:
    return (
        getattr(source_event, "source_system", None) == "internal"
        and isinstance(getattr(source_event, "source_object_id", None), str)
        and source_event.source_object_id.startswith(SYNTHETIC_SOURCE_OBJECT_PREFIX)
    )


def _source_event_payload(source_event: Any) -> dict[str, Any]:
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


async def _source_events_for_window(
    session: Any,
    *,
    start_at: datetime,
    end_at: datetime,
) -> list[Any]:
    from app.db.event_models import SourceEvent

    activity_time = func.coalesce(SourceEvent.source_event_ts, SourceEvent.created_at)
    return (
        await session.scalars(
            select(SourceEvent)
            .where(activity_time >= start_at, activity_time < end_at)
            .order_by(SourceEvent.id)
        )
    ).all()


async def _normalized_source_event_ids(
    session: Any,
    *,
    source_event_ids: set[str],
) -> set[str]:
    from app.db.event_models import NormalizedActivityItemRecord

    if not source_event_ids:
        return set()
    rows = (
        await session.scalars(
            select(NormalizedActivityItemRecord.source_event_id)
            .where(NormalizedActivityItemRecord.source_event_id.in_(source_event_ids))
            .where(NormalizedActivityItemRecord.source_event_id.is_not(None))
        )
    ).all()
    return {value for value in rows if isinstance(value, str) and value}


async def _existing_normalized_summary(
    session: Any,
    *,
    source_event_ids: set[str],
) -> dict[str, Any]:
    from app.db.event_models import NormalizedActivityItemRecord

    if not source_event_ids:
        return {
            "total_linked_to_source_events": 0,
            "by_source": {},
            "by_activity_type": {},
        }

    rows = (
        await session.execute(
            select(
                NormalizedActivityItemRecord.source,
                NormalizedActivityItemRecord.activity_type,
            )
            .where(NormalizedActivityItemRecord.source_event_id.in_(source_event_ids))
            .where(NormalizedActivityItemRecord.source_event_id.is_not(None))
        )
    ).all()
    by_source: dict[str, int] = {}
    by_activity_type: dict[str, int] = {}
    for source, activity_type in rows:
        _bump(by_source, source)
        _bump(by_activity_type, activity_type)
    return {
        "total_linked_to_source_events": len(rows),
        "by_source": dict(sorted(by_source.items())),
        "by_activity_type": dict(sorted(by_activity_type.items())),
    }


def _empty_source_event_summary() -> dict[str, Any]:
    return {
        "total": 0,
        "by_source_system": {},
        "by_source_object_type": {},
        "by_event_type": {},
        "synthetic_marker_count": 0,
        "no_marker_count": 0,
        "synthetic_status": "unknown",
    }


def _empty_normalization_preview() -> dict[str, Any]:
    return {
        "already_normalized_count": 0,
        "eligible_for_projection_count": 0,
        "unsupported_for_projection_count": 0,
        "invalid_or_unpreviewable_count": 0,
        "synthetic_skipped_count": 0,
        "no_marker_eligible_count": 0,
        "synthetic_eligible_count": 0,
        "projected_activity": {
            "by_source": {},
            "by_activity_type": {},
        },
    }


def _recommended_next_action(
    *,
    source_event_count: int,
    include_synthetic: bool,
    normalization_preview: Mapping[str, Any],
) -> str:
    already_normalized = _safe_int(
        normalization_preview.get("already_normalized_count")
    )
    eligible = _safe_int(normalization_preview.get("eligible_for_projection_count"))
    no_marker_eligible = _safe_int(
        normalization_preview.get("no_marker_eligible_count")
    )
    synthetic_eligible = _safe_int(
        normalization_preview.get("synthetic_eligible_count")
    )
    unsupported = _safe_int(
        normalization_preview.get("unsupported_for_projection_count")
    )
    invalid = _safe_int(normalization_preview.get("invalid_or_unpreviewable_count"))
    synthetic_skipped = _safe_int(normalization_preview.get("synthetic_skipped_count"))

    if source_event_count == 0:
        return "no_source_events_found"
    if no_marker_eligible > 0 and already_normalized > 0:
        return "review_projection_preview_and_existing_normalized_counts"
    if no_marker_eligible > 0:
        return "review_projection_preview_before_local_normalization"
    if (
        synthetic_skipped > 0
        and not include_synthetic
        and eligible == 0
        and already_normalized == 0
    ):
        return "rerun_with_include_synthetic_for_dev_preview_or_choose_no_marker_window"
    if synthetic_eligible > 0 and no_marker_eligible == 0 and already_normalized > 0:
        return "review_projection_preview_and_existing_normalized_counts"
    if synthetic_eligible > 0 and no_marker_eligible == 0:
        return "review_projection_preview_before_local_normalization"
    if already_normalized > 0 and eligible == 0:
        return "proceed_to_normalized_activity_triage_readiness"
    if eligible == 0 and already_normalized == 0 and (unsupported > 0 or invalid > 0):
        return "no_supported_source_events_for_normalization"
    return "no_supported_source_events_for_normalization"


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
        "telegram_invoked": False,
        "slack_invoked": False,
        "scheduler_invoked": False,
        "delivery_worker_invoked": False,
        "outbox_record_created": False,
        "api_clients_invoked": False,
        "connectors_invoked": False,
        "live_api_calls": False,
        "openai_invoked": False,
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


def _limitations(*, include_synthetic: bool) -> list[str]:
    notes = [
        "normalization_preview_reports_counts_only_not_company_facts",
        "preview_uses_provider_free_source_activity_mapper_only",
        "row_identifiers_are_not_returned",
        "row_details_are_omitted_count_only_report",
        "no_synthetic_marker_is_not_proof_of_production_truth",
        "future_projection_requires_separate_explicit_local_write_command",
    ]
    if include_synthetic:
        notes.append("synthetic_local_dev_rows_included_for_dev_preview")
    else:
        notes.append("synthetic_local_dev_rows_excluded_by_default")
    return notes


def _blocked_result(*, error_code: str, message: str) -> dict[str, Any]:
    return {
        "status": "blocked",
        "error_code": error_code,
        "message": message,
        "safety": _safety_metadata(),
    }


async def build_stored_source_event_normalization_preview(
    query: NormalizationPreviewQuery,
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
        raise NormalizationPreviewBlockedError(str(exc)) from exc

    session_factory = session_factory or AsyncSessionLocal
    source_events_summary = _empty_source_event_summary()
    normalization_preview = _empty_normalization_preview()

    try:
        async with session_factory() as session:
            source_events = await _source_events_for_window(
                session,
                start_at=query.start_at,
                end_at=query.end_at,
            )
            if len(source_events) > query.max_events:
                raise NormalizationPreviewInputError(
                    f"range contains {len(source_events)} source_events; max_events is {query.max_events}"
                )

            source_event_ids = {
                event.source_event_id
                for event in source_events
                if isinstance(event.source_event_id, str) and event.source_event_id
            }
            normalized_source_event_ids = await _normalized_source_event_ids(
                session,
                source_event_ids=source_event_ids,
            )
            existing_normalized = await _existing_normalized_summary(
                session,
                source_event_ids=source_event_ids,
            )

            synthetic_count = 0
            by_source_system: dict[str, int] = {}
            by_source_object_type: dict[str, int] = {}
            by_event_type: dict[str, int] = {}

            for source_event in source_events:
                is_synthetic = _is_synthetic_source_event(source_event)
                if is_synthetic:
                    synthetic_count += 1
                _bump(by_source_system, source_event.source_system)
                _bump(by_source_object_type, source_event.source_object_type)
                _bump(by_event_type, source_event.event_type)

                if is_synthetic and not query.include_synthetic:
                    normalization_preview["synthetic_skipped_count"] += 1
                    continue

                if source_event.source_event_id in normalized_source_event_ids:
                    normalization_preview["already_normalized_count"] += 1
                    continue

                try:
                    activity = source_event_to_activity_item(
                        _source_event_payload(source_event)
                    )
                except SourceActivityMappingError:
                    normalization_preview["unsupported_for_projection_count"] += 1
                    continue
                except Exception:
                    normalization_preview["invalid_or_unpreviewable_count"] += 1
                    continue

                normalization_preview["eligible_for_projection_count"] += 1
                if is_synthetic:
                    normalization_preview["synthetic_eligible_count"] += 1
                else:
                    normalization_preview["no_marker_eligible_count"] += 1
                _bump(
                    normalization_preview["projected_activity"]["by_source"],
                    activity.source,
                )
                _bump(
                    normalization_preview["projected_activity"]["by_activity_type"],
                    activity.activity_type,
                )

            source_events_summary = {
                "total": len(source_events),
                "by_source_system": dict(sorted(by_source_system.items())),
                "by_source_object_type": dict(sorted(by_source_object_type.items())),
                "by_event_type": dict(sorted(by_event_type.items())),
                "synthetic_marker_count": synthetic_count,
                "no_marker_count": max(len(source_events) - synthetic_count, 0),
                "synthetic_status": _synthetic_status(
                    synthetic_count=synthetic_count,
                    no_marker_count=max(len(source_events) - synthetic_count, 0),
                    total=len(source_events),
                ),
            }
    except (
        NormalizationPreviewInputError,
        NormalizationPreviewBlockedError,
        NormalizationPreviewRuntimeError,
    ):
        raise
    except ValueError as exc:
        raise NormalizationPreviewInputError(str(exc)) from exc
    except Exception as exc:
        raise NormalizationPreviewRuntimeError(
            "stored source event normalization preview blocked; database, schema, or configuration is unavailable"
        ) from exc

    normalization_preview["projected_activity"]["by_source"] = dict(
        sorted(normalization_preview["projected_activity"]["by_source"].items())
    )
    normalization_preview["projected_activity"]["by_activity_type"] = dict(
        sorted(normalization_preview["projected_activity"]["by_activity_type"].items())
    )
    returned_preview_count = (
        _safe_int(normalization_preview.get("already_normalized_count"))
        + _safe_int(normalization_preview.get("eligible_for_projection_count"))
        + _safe_int(normalization_preview.get("unsupported_for_projection_count"))
        + _safe_int(normalization_preview.get("invalid_or_unpreviewable_count"))
    )
    return {
        "status": "stored_source_event_normalization_preview",
        "start_at": query.start_at.isoformat(),
        "end_at": query.end_at.isoformat(),
        "max_events": query.max_events,
        "include_synthetic": query.include_synthetic,
        "scanned_source_event_count": source_events_summary["total"],
        "returned_preview_count": returned_preview_count,
        "source_events": source_events_summary,
        "normalization_preview": normalization_preview,
        "existing_normalized_activity": existing_normalized,
        "recommended_next_action": _recommended_next_action(
            source_event_count=source_events_summary["total"],
            include_synthetic=query.include_synthetic,
            normalization_preview=normalization_preview,
        ),
        "limitations": _limitations(include_synthetic=query.include_synthetic),
        "safety": _safety_metadata(),
    }


def _print_json(value: Mapping[str, Any]) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def format_text_report(report: Mapping[str, Any]) -> str:
    source_events = (
        report.get("source_events")
        if isinstance(report.get("source_events"), Mapping)
        else {}
    )
    preview = (
        report.get("normalization_preview")
        if isinstance(report.get("normalization_preview"), Mapping)
        else {}
    )
    projected = (
        preview.get("projected_activity")
        if isinstance(preview.get("projected_activity"), Mapping)
        else {}
    )
    existing = (
        report.get("existing_normalized_activity")
        if isinstance(report.get("existing_normalized_activity"), Mapping)
        else {}
    )
    safety = report.get("safety") if isinstance(report.get("safety"), Mapping) else {}
    lines = [
        "Stored source event normalization preview (read-only; no writes)",
        f"Window start: {report.get('start_at')}",
        f"Window end: {report.get('end_at')}",
        f"Max events: {report.get('max_events')}",
        f"Include synthetic: {report.get('include_synthetic')}",
        f"Scanned source events: {report.get('scanned_source_event_count')}",
        f"Synthetic status: {source_events.get('synthetic_status')}",
        f"Synthetic marker count: {source_events.get('synthetic_marker_count')}",
        f"No-marker count: {source_events.get('no_marker_count')}",
        f"Already normalized: {preview.get('already_normalized_count')}",
        f"Eligible for projection: {preview.get('eligible_for_projection_count')}",
        f"No-marker eligible: {preview.get('no_marker_eligible_count')}",
        f"Synthetic eligible: {preview.get('synthetic_eligible_count')}",
        f"Unsupported: {preview.get('unsupported_for_projection_count')}",
        f"Invalid/unpreviewable: {preview.get('invalid_or_unpreviewable_count')}",
        f"Synthetic skipped: {preview.get('synthetic_skipped_count')}",
        "Existing normalized linked to source events: "
        f"{existing.get('total_linked_to_source_events')}",
        f"Projected activity sources: {projected.get('by_source')}",
        f"Projected activity types: {projected.get('by_activity_type')}",
        f"Recommended next action: {report.get('recommended_next_action')}",
        "",
        f"Read-only: {safety.get('read_only')}",
        f"DB write scope: {safety.get('db_write_scope')}",
        f"Source events created: {safety.get('source_events_created')}",
        f"Normalized activity created: {safety.get('normalized_activity_created')}",
        f"Attention results created: {safety.get('attention_results_created')}",
        f"Delivery draft created: {safety.get('delivery_draft_created')}",
        f"Delivery intention created: {safety.get('delivery_intention_created')}",
        f"Delivery result created: {safety.get('delivery_result_created')}",
        f"Delivery invoked: {safety.get('delivery_invoked')}",
        f"Telegram invoked: {safety.get('telegram_invoked')}",
        f"Scheduler invoked: {safety.get('scheduler_invoked')}",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parse_args(argv)
        query = _query_from_args(args)
        report = asyncio.run(build_stored_source_event_normalization_preview(query))
    except NormalizationPreviewInputError as exc:
        output_format = getattr(locals().get("args", None), "format", "json")
        if output_format == "json":
            _print_json(_blocked_result(error_code="input_error", message=str(exc)))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 2
    except NormalizationPreviewBlockedError as exc:
        output_format = getattr(locals().get("args", None), "format", "json")
        if output_format == "json":
            _print_json(_blocked_result(error_code="blocked", message=str(exc)))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 1
    except NormalizationPreviewRuntimeError as exc:
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
