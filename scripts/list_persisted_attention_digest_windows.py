#!/usr/bin/env python
"""Discover persisted attention digest windows for manual pilots."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
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

from app.services.digest import (  # noqa: E402
    DEFAULT_DIGEST_ENTRY_LIMIT,
    MAX_DIGEST_ENTRY_LIMIT,
)
from scripts import prepare_manual_pilot_delivery_draft as prepare_script  # noqa: E402
from scripts import report_manual_pilot_status as pilot_status_script  # noqa: E402

DEFAULT_WINDOW_SIZE_HOURS = 24
MAX_WINDOW_SIZE_HOURS = 24 * 31
DEFAULT_MAX_WINDOWS = 31
MAX_DISCOVERY_WINDOWS = 90
SYNTHETIC_SOURCE_OBJECT_PREFIX = "local.synthetic.persisted_attention_seed:"


class WindowDiscoveryInputError(ValueError):
    pass


class WindowDiscoveryBlockedError(RuntimeError):
    pass


class WindowDiscoveryRuntimeError(RuntimeError):
    pass


@dataclass(frozen=True)
class WindowDiscoveryQuery:
    start_at: datetime
    end_at: datetime
    window_size_hours: int = DEFAULT_WINDOW_SIZE_HOURS
    max_windows: int = DEFAULT_MAX_WINDOWS
    limit: int = DEFAULT_DIGEST_ENTRY_LIMIT
    debug_evidence: bool = False
    include_empty: bool = False
    output_format: str = "json"


def _parse_datetime(value: str, *, field_name: str) -> datetime:
    try:
        return prepare_script._parse_datetime(value, field_name=field_name)
    except prepare_script.PrepareInputError as exc:
        raise WindowDiscoveryInputError(str(exc)) from exc


def _clean_limit(value: int) -> int:
    if not isinstance(value, int):
        raise WindowDiscoveryInputError("limit must be an integer")
    if value < 1 or value > MAX_DIGEST_ENTRY_LIMIT:
        raise WindowDiscoveryInputError(
            f"limit must be between 1 and {MAX_DIGEST_ENTRY_LIMIT}"
        )
    return value


def _clean_window_size_hours(value: int) -> int:
    if not isinstance(value, int):
        raise WindowDiscoveryInputError("window_size_hours must be an integer")
    if value < 1 or value > MAX_WINDOW_SIZE_HOURS:
        raise WindowDiscoveryInputError(
            f"window_size_hours must be between 1 and {MAX_WINDOW_SIZE_HOURS}"
        )
    return value


def _clean_max_windows(value: int) -> int:
    if not isinstance(value, int):
        raise WindowDiscoveryInputError("max_windows must be an integer")
    if value < 1 or value > MAX_DISCOVERY_WINDOWS:
        raise WindowDiscoveryInputError(
            f"max_windows must be between 1 and {MAX_DISCOVERY_WINDOWS}"
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
        help="Timezone-aware ISO start for the discovery range.",
    )
    parser.add_argument(
        "--end-at",
        required=True,
        help="Timezone-aware ISO end for the discovery range.",
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
            f"1-{MAX_DISCOVERY_WINDOWS}; default {DEFAULT_MAX_WINDOWS}."
        ),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_DIGEST_ENTRY_LIMIT,
        help=f"Maximum visible items per section, 1-{MAX_DIGEST_ENTRY_LIMIT}.",
    )
    parser.add_argument(
        "--debug-evidence",
        action="store_true",
        help="Match drafts prepared with safe debug evidence enabled.",
    )
    parser.add_argument(
        "--include-empty",
        action="store_true",
        help="Include windows with zero persisted attention items.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="json",
        help="Output format.",
    )
    return parser.parse_args(argv)


def _query_from_args(args: argparse.Namespace) -> WindowDiscoveryQuery:
    start_at = _parse_datetime(args.start_at, field_name="start_at")
    end_at = _parse_datetime(args.end_at, field_name="end_at")
    if end_at <= start_at:
        raise WindowDiscoveryInputError("end_at must be after start_at")
    window_size_hours = _clean_window_size_hours(args.window_size_hours)
    max_windows = _clean_max_windows(args.max_windows)
    planned_count = _planned_window_count(
        start_at=start_at,
        end_at=end_at,
        window_size_hours=window_size_hours,
    )
    if planned_count > max_windows:
        raise WindowDiscoveryInputError(
            f"range would scan {planned_count} windows; max_windows is {max_windows}"
        )
    return WindowDiscoveryQuery(
        start_at=start_at,
        end_at=end_at,
        window_size_hours=window_size_hours,
        max_windows=max_windows,
        limit=_clean_limit(args.limit),
        debug_evidence=bool(args.debug_evidence),
        include_empty=bool(args.include_empty),
        output_format=args.format,
    )


def _candidate_windows(query: WindowDiscoveryQuery) -> list[tuple[datetime, datetime]]:
    step = timedelta(hours=query.window_size_hours)
    windows: list[tuple[datetime, datetime]] = []
    cursor = query.start_at
    while cursor < query.end_at:
        window_end = min(cursor + step, query.end_at)
        windows.append((cursor, window_end))
        if len(windows) > query.max_windows:
            raise WindowDiscoveryInputError(
                f"range would scan more than {query.max_windows} windows"
            )
        cursor = window_end
    return windows


def _safe_int(value: Any) -> int:
    return int(value) if isinstance(value, int) and not isinstance(value, bool) else 0


async def _synthetic_status_for_window(
    session: Any,
    *,
    start_at: datetime,
    end_at: datetime,
) -> str:
    from app.db.attention_models import AttentionTriageResultRecord

    count = await session.scalar(
        select(func.count())
        .select_from(AttentionTriageResultRecord)
        .where(AttentionTriageResultRecord.created_at >= start_at)
        .where(AttentionTriageResultRecord.created_at < end_at)
        .where(AttentionTriageResultRecord.source == "internal")
        .where(
            AttentionTriageResultRecord.source_object_id.like(
                f"{SYNTHETIC_SOURCE_OBJECT_PREFIX}%"
            )
        )
    )
    return (
        "synthetic_local_dev_detected"
        if int(count or 0) > 0
        else "no_synthetic_marker_detected"
    )


def _limitations_for_window(
    *,
    drafts: list[dict[str, Any]],
    synthetic_status: str,
) -> list[str]:
    notes = list(pilot_status_script._limitations(drafts=drafts, sample_id=None))
    notes.append("window_discovery_uses_deterministic_explicit_range_slicing")
    if synthetic_status == "synthetic_local_dev_detected":
        notes.append("synthetic_status_detected_from_safe_local_seed_marker")
    else:
        notes.append("no_synthetic_marker_is_not_proof_of_production_truth")
    return notes


def _window_summary(
    *,
    start_at: datetime,
    end_at: datetime,
    digest_summary: Mapping[str, Any],
    draft_summaries: list[dict[str, Any]],
    synthetic_status: str,
) -> dict[str, Any]:
    lifecycle_summary = pilot_status_script._lifecycle_summary(
        digest=digest_summary,
        drafts=draft_summaries,
    )
    recommended_next_action = pilot_status_script._recommended_next_action(
        digest=digest_summary,
        drafts=draft_summaries,
        lifecycle_summary=lifecycle_summary,
    )
    return {
        "start_at": start_at.isoformat(),
        "end_at": end_at.isoformat(),
        "digest": dict(digest_summary),
        "synthetic_status": synthetic_status,
        "lifecycle_summary": lifecycle_summary,
        "drafts": {
            "count": len(draft_summaries),
            "items": draft_summaries,
        },
        "recommended_next_action": recommended_next_action,
        "limitations": _limitations_for_window(
            drafts=draft_summaries,
            synthetic_status=synthetic_status,
        ),
    }


def _aggregate_summary(windows: list[dict[str, Any]]) -> dict[str, int]:
    def action_count(action: str) -> int:
        return sum(
            1 for window in windows if window.get("recommended_next_action") == action
        )

    return {
        "non_empty_window_count": sum(
            1 for window in windows if _safe_int(window["digest"].get("total")) > 0
        ),
        "visible_window_count": sum(
            1 for window in windows if _safe_int(window["digest"].get("visible")) > 0
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
        "already_sent_window_count": sum(
            1
            for window in windows
            if window["lifecycle_summary"].get("stale_or_already_sent_warning")
            is True
        ),
        "candidate_prepare_window_count": action_count(
            "prepare_manual_pilot_delivery_draft"
        ),
        "candidate_approval_window_count": action_count("approve_delivery_draft"),
        "candidate_handoff_window_count": action_count(
            "continue_approved_draft_handoff"
        ),
        "candidate_send_window_count": action_count(
            "review_gate_before_bounded_send"
        ),
    }


def _safety_metadata() -> dict[str, Any]:
    return {
        "provider_free": True,
        "read_only": True,
        "local_operator_command": True,
        "db_write_scope": "none",
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
        "raw_storage_touched": False,
        "obsidian_touched": False,
        "production_mode": False,
        "report_is_source_of_truth": False,
        "draft_is_source_of_truth": False,
        "intention_is_source_of_truth": False,
        "delivery_result_is_source_of_truth": False,
        "telegram_is_source_of_truth": False,
    }


async def build_persisted_attention_window_discovery(
    query: WindowDiscoveryQuery,
    *,
    session_factory: Callable[[], Any] | None = None,
    settings_override: Any | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    from app.core.config import settings
    from app.db.base import AsyncSessionLocal
    from app.services.digest import build_persisted_attention_digest_read_model
    from app.services.digest_delivery_drafts import (
        list_persisted_digest_delivery_drafts_for_window,
    )

    try:
        prepare_script._assert_local_environment(
            settings=settings_override or settings,
            environ=environ if environ is not None else os.environ,
        )
    except prepare_script.PrepareBlockedError as exc:
        raise WindowDiscoveryBlockedError(str(exc)) from exc

    candidate_windows = _candidate_windows(query)
    session_factory = session_factory or AsyncSessionLocal
    scanned_summaries: list[dict[str, Any]] = []

    try:
        async with session_factory() as session:
            for start_at, end_at in candidate_windows:
                digest = await build_persisted_attention_digest_read_model(
                    session,
                    start_at=start_at,
                    end_at=end_at,
                    limit_per_section=query.limit,
                )
                digest_summary = pilot_status_script._safe_digest_summary(digest)
                synthetic_status = await _synthetic_status_for_window(
                    session,
                    start_at=start_at,
                    end_at=end_at,
                )
                matching_drafts = await list_persisted_digest_delivery_drafts_for_window(
                    session,
                    start_at=start_at,
                    end_at=end_at,
                    limit=query.limit,
                    debug_evidence=query.debug_evidence,
                )
                draft_summaries = [
                    await pilot_status_script._draft_lifecycle_summary(
                        session,
                        draft=draft,
                    )
                    for draft in matching_drafts
                ]
                scanned_summaries.append(
                    _window_summary(
                        start_at=start_at,
                        end_at=end_at,
                        digest_summary=digest_summary,
                        draft_summaries=draft_summaries,
                        synthetic_status=synthetic_status,
                    )
                )
    except (
        WindowDiscoveryInputError,
        WindowDiscoveryBlockedError,
        WindowDiscoveryRuntimeError,
    ):
        raise
    except ValueError as exc:
        raise WindowDiscoveryInputError(str(exc)) from exc
    except Exception as exc:
        raise WindowDiscoveryRuntimeError(
            "persisted attention window discovery blocked; database, schema, or configuration is unavailable"
        ) from exc

    returned_windows = [
        window
        for window in scanned_summaries
        if query.include_empty or _safe_int(window["digest"].get("total")) > 0
    ]
    return {
        "status": "persisted_attention_window_discovery",
        "start_at": query.start_at.isoformat(),
        "end_at": query.end_at.isoformat(),
        "window_size_hours": query.window_size_hours,
        "max_windows": query.max_windows,
        "limit": query.limit,
        "debug_evidence": query.debug_evidence,
        "include_empty": query.include_empty,
        "scanned_window_count": len(scanned_summaries),
        "returned_window_count": len(returned_windows),
        "windows": returned_windows,
        "aggregate_summary": _aggregate_summary(scanned_summaries),
        "safety": _safety_metadata(),
        "limitations": [
            "window_discovery_summarizes_audit_metadata_only_not_company_facts",
            "window_association_uses_exact_window_limit_debug_evidence_and_channel",
            "absence_of_synthetic_marker_is_not_proof_of_production_truth",
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
        "Persisted attention window discovery (read-only; no send)",
        f"Range start: {report.get('start_at')}",
        f"Range end: {report.get('end_at')}",
        f"Window size hours: {report.get('window_size_hours')}",
        f"Scanned windows: {report.get('scanned_window_count')}",
        f"Returned windows: {report.get('returned_window_count')}",
        f"Non-empty windows: {aggregate.get('non_empty_window_count')}",
        f"Visible windows: {aggregate.get('visible_window_count')}",
        "Synthetic local/dev windows: "
        f"{aggregate.get('synthetic_local_dev_window_count')}",
        "No synthetic marker windows: "
        f"{aggregate.get('no_synthetic_marker_window_count')}",
        f"Already-sent windows: {aggregate.get('already_sent_window_count')}",
        "",
        "Candidate windows:",
    ]
    windows = report.get("windows") if isinstance(report.get("windows"), list) else []
    if not windows:
        lines.append("- none returned")
    for window in windows:
        if not isinstance(window, Mapping):
            continue
        digest = window.get("digest") if isinstance(window.get("digest"), Mapping) else {}
        lifecycle = (
            window.get("lifecycle_summary")
            if isinstance(window.get("lifecycle_summary"), Mapping)
            else {}
        )
        drafts = window.get("drafts") if isinstance(window.get("drafts"), Mapping) else {}
        lines.extend(
            [
                f"- Window: {window.get('start_at')} -> {window.get('end_at')}",
                f"  Total: {digest.get('total')}",
                f"  Visible: {digest.get('visible')}",
                f"  Hidden: {digest.get('hidden')}",
                f"  Synthetic status: {window.get('synthetic_status')}",
                f"  Delivery drafts: {drafts.get('count', 0)}",
                "  Duplicate guard would block any known intention: "
                f"{lifecycle.get('duplicate_guard_would_block_any_known_intention')}",
                "  Stale or already-sent warning: "
                f"{lifecycle.get('stale_or_already_sent_warning')}",
                f"  Recommended next action: {window.get('recommended_next_action')}",
            ]
        )
    lines.extend(
        [
            "",
            f"Read-only: {safety.get('read_only')}",
            f"DB write scope: {safety.get('db_write_scope')}",
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
        report = asyncio.run(build_persisted_attention_window_discovery(query))
    except WindowDiscoveryInputError as exc:
        output_format = getattr(locals().get("args", None), "format", "json")
        if output_format == "json":
            _print_json(_blocked_result(error_code="input_error", message=str(exc)))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 2
    except WindowDiscoveryBlockedError as exc:
        output_format = getattr(locals().get("args", None), "format", "json")
        if output_format == "json":
            _print_json(_blocked_result(error_code="blocked", message=str(exc)))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 1
    except WindowDiscoveryRuntimeError as exc:
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
