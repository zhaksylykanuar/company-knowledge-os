#!/usr/bin/env python
"""Project stored SourceEvents into normalized activity rows locally."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
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

from app.services.normalized_activity import (  # noqa: E402
    SourceEventActivityProjectionError,
    get_normalized_activity_item_for_source_event,
    project_source_event_to_normalized_activity_item,
)
from scripts import prepare_manual_pilot_delivery_draft as prepare_script  # noqa: E402
from scripts import preview_stored_source_event_normalization as preview_script  # noqa: E402

CONFIRM_NORMALIZE_PHRASE = "NORMALIZE STORED SOURCE EVENTS"
DEFAULT_MAX_EVENTS = preview_script.DEFAULT_MAX_EVENTS
MAX_NORMALIZE_EVENTS = preview_script.MAX_NORMALIZATION_PREVIEW_EVENTS


class StoredSourceEventNormalizationInputError(ValueError):
    pass


class StoredSourceEventNormalizationBlockedError(RuntimeError):
    pass


class StoredSourceEventNormalizationRuntimeError(RuntimeError):
    pass


@dataclass(frozen=True)
class StoredSourceEventNormalizationQuery:
    start_at: datetime
    end_at: datetime
    confirm_normalize: str
    max_events: int = DEFAULT_MAX_EVENTS
    include_synthetic: bool = False
    sources: tuple[str, ...] = ()
    output_format: str = "json"


def _parse_datetime(value: str, *, field_name: str) -> datetime:
    try:
        return prepare_script._parse_datetime(value, field_name=field_name)
    except prepare_script.PrepareInputError as exc:
        raise StoredSourceEventNormalizationInputError(str(exc)) from exc


def _clean_max_events(value: int) -> int:
    if not isinstance(value, int):
        raise StoredSourceEventNormalizationInputError("max_events must be an integer")
    if value < 1 or value > MAX_NORMALIZE_EVENTS:
        raise StoredSourceEventNormalizationInputError(
            f"max_events must be between 1 and {MAX_NORMALIZE_EVENTS}"
        )
    return value


def _clean_confirm_normalize(value: str) -> str:
    if not isinstance(value, str) or value != CONFIRM_NORMALIZE_PHRASE:
        raise StoredSourceEventNormalizationInputError(
            "confirm_normalize phrase did not match"
        )
    return value


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--start-at",
        required=True,
        help="Timezone-aware ISO start for the source event normalization window.",
    )
    parser.add_argument(
        "--end-at",
        required=True,
        help="Timezone-aware ISO end for the source event normalization window.",
    )
    parser.add_argument(
        "--confirm-normalize",
        required=True,
        help=f'Exact confirmation phrase: "{CONFIRM_NORMALIZE_PHRASE}".',
    )
    parser.add_argument(
        "--max-events",
        type=int,
        default=DEFAULT_MAX_EVENTS,
        help=(
            "Maximum stored source events to scan, "
            f"1-{MAX_NORMALIZE_EVENTS}; default {DEFAULT_MAX_EVENTS}."
        ),
    )
    parser.add_argument(
        "--include-synthetic",
        action="store_true",
        help="Include clearly synthetic local/dev source events in normalization.",
    )
    parser.add_argument(
        "--source",
        action="append",
        default=[],
        help="Limit normalization to a source_system value; may be provided more than once.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="json",
        help="Output format.",
    )
    return parser.parse_args(argv)


def _query_from_args(args: argparse.Namespace) -> StoredSourceEventNormalizationQuery:
    start_at = _parse_datetime(args.start_at, field_name="start_at")
    end_at = _parse_datetime(args.end_at, field_name="end_at")
    if end_at <= start_at:
        raise StoredSourceEventNormalizationInputError("end_at must be after start_at")
    return StoredSourceEventNormalizationQuery(
        start_at=start_at,
        end_at=end_at,
        confirm_normalize=_clean_confirm_normalize(args.confirm_normalize),
        max_events=_clean_max_events(args.max_events),
        include_synthetic=bool(args.include_synthetic),
        sources=preview_script._clean_sources(args.source),
        output_format=args.format,
    )


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


def _empty_normalization_summary() -> dict[str, Any]:
    return {
        "created_count": 0,
        "already_normalized_count": 0,
        "unsupported_count": 0,
        "invalid_or_unpreviewable_count": 0,
        "synthetic_skipped_count": 0,
        "no_marker_created_count": 0,
        "synthetic_created_count": 0,
        "by_projected_source": {},
        "by_projected_activity_type": {},
    }


async def _source_event_count_for_window(
    session: Any,
    *,
    start_at: datetime,
    end_at: datetime,
    sources: tuple[str, ...] = (),
) -> int:
    from app.db.event_models import SourceEvent

    activity_time = func.coalesce(SourceEvent.source_event_ts, SourceEvent.created_at)
    statement = (
        select(func.count())
        .select_from(SourceEvent)
        .where(activity_time >= start_at, activity_time < end_at)
    )
    if sources:
        statement = statement.where(SourceEvent.source_system.in_(sources))
    return int(
        await session.scalar(statement)
        or 0
    )


def _summarize_source_events(source_events: list[Any]) -> dict[str, Any]:
    by_source_system: dict[str, int] = {}
    by_source_object_type: dict[str, int] = {}
    by_event_type: dict[str, int] = {}
    synthetic_count = 0

    for source_event in source_events:
        if preview_script._is_synthetic_source_event(source_event):
            synthetic_count += 1
        preview_script._bump(by_source_system, source_event.source_system)
        preview_script._bump(by_source_object_type, source_event.source_object_type)
        preview_script._bump(by_event_type, source_event.event_type)

    no_marker_count = max(len(source_events) - synthetic_count, 0)
    return {
        "total": len(source_events),
        "by_source_system": dict(sorted(by_source_system.items())),
        "by_source_object_type": dict(sorted(by_source_object_type.items())),
        "by_event_type": dict(sorted(by_event_type.items())),
        "synthetic_marker_count": synthetic_count,
        "no_marker_count": no_marker_count,
        "synthetic_status": preview_script._synthetic_status(
            synthetic_count=synthetic_count,
            no_marker_count=no_marker_count,
            total=len(source_events),
        ),
    }


def _recommended_next_action(
    *,
    source_event_count: int,
    normalization: Mapping[str, Any],
) -> str:
    created = preview_script._safe_int(normalization.get("created_count"))
    already = preview_script._safe_int(normalization.get("already_normalized_count"))
    unsupported = preview_script._safe_int(normalization.get("unsupported_count"))
    invalid = preview_script._safe_int(
        normalization.get("invalid_or_unpreviewable_count")
    )
    skipped = preview_script._safe_int(normalization.get("synthetic_skipped_count"))

    if source_event_count == 0:
        return "no_source_events_found"
    if created > 0:
        return "run_real_stored_local_data_readiness_report"
    if already > 0 and created == 0:
        return "proceed_to_normalized_activity_triage_readiness"
    if skipped > 0 and unsupported == 0 and invalid == 0:
        return "rerun_with_include_synthetic_for_dev_preview_or_choose_no_marker_window"
    return "no_supported_source_events_for_normalization"


def _safety_metadata(*, created_count: int) -> dict[str, Any]:
    created = created_count > 0
    return {
        "provider_free": True,
        "read_only": False,
        "local_operator_command": True,
        "local_dev_only": True,
        "db_write_scope": "normalized_activity_items_only" if created else "none",
        "source_events_created": False,
        "normalized_activity_created": created,
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
        "normalization_is_source_of_truth": False,
        "telegram_is_source_of_truth": False,
    }


def _limitations(*, include_synthetic: bool) -> list[str]:
    notes = [
        "normalization_reports_counts_only_not_company_facts",
        "normalization_uses_existing_provider_free_source_activity_projection_service",
        "row_identifiers_are_not_returned",
        "row_details_are_omitted_count_only_report",
        "no_synthetic_marker_is_not_proof_of_production_truth",
        "attention_triage_requires_separate_explicit_step",
    ]
    if include_synthetic:
        notes.append("synthetic_local_dev_rows_included_for_dev_normalization")
    else:
        notes.append("synthetic_local_dev_rows_excluded_by_default")
    return notes


def _blocked_result(*, error_code: str, message: str) -> dict[str, Any]:
    return {
        "status": "blocked",
        "error_code": error_code,
        "message": message,
        "safety": _safety_metadata(created_count=0),
    }


async def normalize_stored_source_events(
    query: StoredSourceEventNormalizationQuery,
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
        raise StoredSourceEventNormalizationBlockedError(
            "refusing to normalize stored source events in production-like environment"
        ) from exc

    if query.confirm_normalize != CONFIRM_NORMALIZE_PHRASE:
        raise StoredSourceEventNormalizationInputError(
            "confirm_normalize phrase did not match"
        )

    session_factory = session_factory or AsyncSessionLocal
    source_events_summary = _empty_source_event_summary()
    normalization = _empty_normalization_summary()

    try:
        async with session_factory() as session:
            source_event_count = await _source_event_count_for_window(
                session,
                start_at=query.start_at,
                end_at=query.end_at,
                sources=query.sources,
            )
            if source_event_count > query.max_events:
                raise StoredSourceEventNormalizationInputError(
                    f"range contains {source_event_count} source_events; max_events is {query.max_events}"
                )

            source_events = await preview_script._source_events_for_window(
                session,
                start_at=query.start_at,
                end_at=query.end_at,
                sources=query.sources,
            )
            source_events_summary = _summarize_source_events(source_events)

            for source_event in source_events:
                is_synthetic = preview_script._is_synthetic_source_event(source_event)
                if is_synthetic and not query.include_synthetic:
                    normalization["synthetic_skipped_count"] += 1
                    continue

                existing = await get_normalized_activity_item_for_source_event(
                    session,
                    source_event_id=source_event.source_event_id,
                )
                if existing is not None:
                    normalization["already_normalized_count"] += 1
                    continue

                try:
                    stored = await project_source_event_to_normalized_activity_item(
                        session,
                        source_event=source_event,
                    )
                except SourceEventActivityProjectionError:
                    normalization["unsupported_count"] += 1
                    continue
                except ValueError:
                    normalization["invalid_or_unpreviewable_count"] += 1
                    continue

                normalization["created_count"] += 1
                if is_synthetic:
                    normalization["synthetic_created_count"] += 1
                else:
                    normalization["no_marker_created_count"] += 1
                preview_script._bump(
                    normalization["by_projected_source"],
                    stored.source,
                )
                preview_script._bump(
                    normalization["by_projected_activity_type"],
                    stored.activity_type,
                )

            if normalization["created_count"] > 0:
                await session.commit()
            else:
                await session.rollback()
    except (
        StoredSourceEventNormalizationInputError,
        StoredSourceEventNormalizationBlockedError,
        StoredSourceEventNormalizationRuntimeError,
    ):
        raise
    except ValueError as exc:
        raise StoredSourceEventNormalizationInputError(str(exc)) from exc
    except Exception as exc:
        raise StoredSourceEventNormalizationRuntimeError(
            "stored source event normalization blocked; database, schema, or configuration is unavailable"
        ) from exc

    normalization["by_projected_source"] = dict(
        sorted(normalization["by_projected_source"].items())
    )
    normalization["by_projected_activity_type"] = dict(
        sorted(normalization["by_projected_activity_type"].items())
    )
    created_count = preview_script._safe_int(normalization.get("created_count"))
    return {
        "status": "stored_source_event_normalization",
        "start_at": query.start_at.isoformat(),
        "end_at": query.end_at.isoformat(),
        "max_events": query.max_events,
        "include_synthetic": query.include_synthetic,
        "sources": list(query.sources),
        "scanned_source_event_count": source_events_summary["total"],
        "source_events": source_events_summary,
        "normalization": normalization,
        "recommended_next_action": _recommended_next_action(
            source_event_count=source_events_summary["total"],
            normalization=normalization,
        ),
        "limitations": _limitations(include_synthetic=query.include_synthetic),
        "safety": _safety_metadata(created_count=created_count),
    }


def _print_json(value: Mapping[str, Any]) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def format_text_report(report: Mapping[str, Any]) -> str:
    source_events = (
        report.get("source_events")
        if isinstance(report.get("source_events"), Mapping)
        else {}
    )
    normalization = (
        report.get("normalization")
        if isinstance(report.get("normalization"), Mapping)
        else {}
    )
    safety = report.get("safety") if isinstance(report.get("safety"), Mapping) else {}
    lines = [
        "Stored source event normalization (local/dev write command)",
        f"Window start: {report.get('start_at')}",
        f"Window end: {report.get('end_at')}",
        f"Max events: {report.get('max_events')}",
        f"Include synthetic: {report.get('include_synthetic')}",
        f"Scanned source events: {report.get('scanned_source_event_count')}",
        f"Synthetic status: {source_events.get('synthetic_status')}",
        f"Synthetic marker count: {source_events.get('synthetic_marker_count')}",
        f"No-marker count: {source_events.get('no_marker_count')}",
        f"Created normalized activity rows: {normalization.get('created_count')}",
        f"Already normalized: {normalization.get('already_normalized_count')}",
        f"Unsupported: {normalization.get('unsupported_count')}",
        f"Invalid/unpreviewable: {normalization.get('invalid_or_unpreviewable_count')}",
        f"Synthetic skipped: {normalization.get('synthetic_skipped_count')}",
        f"No-marker created: {normalization.get('no_marker_created_count')}",
        f"Synthetic created: {normalization.get('synthetic_created_count')}",
        f"Projected activity sources: {normalization.get('by_projected_source')}",
        f"Projected activity types: {normalization.get('by_projected_activity_type')}",
        f"Recommended next action: {report.get('recommended_next_action')}",
        "",
        f"Local/dev only: {safety.get('local_dev_only')}",
        f"Provider free: {safety.get('provider_free')}",
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
        report = asyncio.run(normalize_stored_source_events(query))
    except StoredSourceEventNormalizationInputError as exc:
        output_format = getattr(locals().get("args", None), "format", "json")
        if output_format == "json":
            _print_json(_blocked_result(error_code="input_error", message=str(exc)))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 2
    except StoredSourceEventNormalizationBlockedError as exc:
        output_format = getattr(locals().get("args", None), "format", "json")
        if output_format == "json":
            _print_json(_blocked_result(error_code="blocked", message=str(exc)))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 1
    except StoredSourceEventNormalizationRuntimeError as exc:
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
