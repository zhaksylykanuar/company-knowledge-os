#!/usr/bin/env python
"""Triage normalized activity rows locally with the provider-free fallback."""

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

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.services import attention_results as attention_results_service  # noqa: E402
from app.services.attention_results import AttentionResultValidationError  # noqa: E402
from app.services.attention_triage import (  # noqa: E402
    ConservativeFallbackAttentionTriageProvider,
)
from scripts import prepare_manual_pilot_delivery_draft as prepare_script  # noqa: E402
from scripts import preview_normalized_activity_triage_readiness as readiness_script  # noqa: E402
from scripts import preview_stored_source_event_normalization as preview_script  # noqa: E402

CONFIRM_TRIAGE_PHRASE = "TRIAGE NORMALIZED ACTIVITY"
DEFAULT_MAX_ITEMS = readiness_script.DEFAULT_MAX_ITEMS
MAX_TRIAGE_ITEMS = readiness_script.MAX_TRIAGE_READINESS_ITEMS


class NormalizedActivityTriageInputError(ValueError):
    pass


class NormalizedActivityTriageBlockedError(RuntimeError):
    pass


class NormalizedActivityTriageRuntimeError(RuntimeError):
    pass


@dataclass(frozen=True)
class NormalizedActivityTriageQuery:
    start_at: datetime
    end_at: datetime
    confirm_triage: str
    max_items: int = DEFAULT_MAX_ITEMS
    include_synthetic: bool = False
    output_format: str = "json"


def _parse_datetime(value: str, *, field_name: str) -> datetime:
    try:
        return prepare_script._parse_datetime(value, field_name=field_name)
    except prepare_script.PrepareInputError as exc:
        raise NormalizedActivityTriageInputError(str(exc)) from exc


def _clean_max_items(value: int) -> int:
    if not isinstance(value, int):
        raise NormalizedActivityTriageInputError("max_items must be an integer")
    if value < 1 or value > MAX_TRIAGE_ITEMS:
        raise NormalizedActivityTriageInputError(
            f"max_items must be between 1 and {MAX_TRIAGE_ITEMS}"
        )
    return value


def _clean_confirm_triage(value: str) -> str:
    if not isinstance(value, str) or value != CONFIRM_TRIAGE_PHRASE:
        raise NormalizedActivityTriageInputError("confirm_triage phrase did not match")
    return value


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--start-at",
        required=True,
        help="Timezone-aware ISO start for the normalized activity triage window.",
    )
    parser.add_argument(
        "--end-at",
        required=True,
        help="Timezone-aware ISO end for the normalized activity triage window.",
    )
    parser.add_argument(
        "--confirm-triage",
        required=True,
        help=f'Exact confirmation phrase: "{CONFIRM_TRIAGE_PHRASE}".',
    )
    parser.add_argument(
        "--max-items",
        type=int,
        default=DEFAULT_MAX_ITEMS,
        help=(
            "Maximum normalized activity items to scan, "
            f"1-{MAX_TRIAGE_ITEMS}; default {DEFAULT_MAX_ITEMS}."
        ),
    )
    parser.add_argument(
        "--include-synthetic",
        action="store_true",
        help="Include clearly synthetic local/dev normalized activity rows.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="json",
        help="Output format.",
    )
    return parser.parse_args(argv)


def _query_from_args(args: argparse.Namespace) -> NormalizedActivityTriageQuery:
    start_at = _parse_datetime(args.start_at, field_name="start_at")
    end_at = _parse_datetime(args.end_at, field_name="end_at")
    if end_at <= start_at:
        raise NormalizedActivityTriageInputError("end_at must be after start_at")
    return NormalizedActivityTriageQuery(
        start_at=start_at,
        end_at=end_at,
        confirm_triage=_clean_confirm_triage(args.confirm_triage),
        max_items=_clean_max_items(args.max_items),
        include_synthetic=bool(args.include_synthetic),
        output_format=args.format,
    )


def _empty_normalized_activity_summary() -> dict[str, Any]:
    return {
        "total": 0,
        "by_source": {},
        "by_activity_type": {},
        "synthetic_marker_count": 0,
        "no_marker_count": 0,
        "synthetic_status": "unknown",
    }


def _empty_triage_summary() -> dict[str, Any]:
    return {
        "created_count": 0,
        "already_triaged_count": 0,
        "unsupported_or_unknown_count": 0,
        "invalid_or_unpreviewable_count": 0,
        "synthetic_skipped_count": 0,
        "no_marker_created_count": 0,
        "synthetic_created_count": 0,
        "by_attention_class": {},
        "by_priority": {},
        "visible_candidate_count": 0,
        "hidden_count": 0,
    }


def _recommended_next_action(
    *,
    normalized_activity_count: int,
    triage: Mapping[str, Any],
) -> str:
    created = preview_script._safe_int(triage.get("created_count"))
    already = preview_script._safe_int(triage.get("already_triaged_count"))
    unsupported = preview_script._safe_int(triage.get("unsupported_or_unknown_count"))
    invalid = preview_script._safe_int(triage.get("invalid_or_unpreviewable_count"))
    skipped = preview_script._safe_int(triage.get("synthetic_skipped_count"))

    if normalized_activity_count == 0:
        return "normalize_source_events_before_triage"
    if created > 0:
        return "run_real_stored_local_data_readiness_report"
    if already > 0 and unsupported == 0 and invalid == 0:
        return "run_real_stored_local_data_readiness_report"
    if skipped > 0 and already == 0 and unsupported == 0 and invalid == 0:
        return "rerun_with_include_synthetic_for_dev_preview_or_choose_no_marker_window"
    return "no_supported_normalized_activity_for_provider_free_triage"


def _safety_metadata(*, created_count: int) -> dict[str, Any]:
    created = created_count > 0
    return {
        "provider_free": True,
        "read_only": False,
        "local_operator_command": True,
        "local_dev_only": True,
        "db_write_scope": "attention_triage_results_only" if created else "none",
        "source_events_created": False,
        "normalized_activity_created": False,
        "attention_results_created": created,
        "triage_write_invoked": created,
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
        "triage_is_source_of_truth": False,
        "telegram_is_source_of_truth": False,
    }


def _limitations(*, include_synthetic: bool) -> list[str]:
    notes = [
        "triage_reports_counts_only_not_company_facts",
        "triage_uses_existing_provider_free_fallback_service",
        "attention_results_are_strict_schema_validated",
        "row_identifiers_are_not_returned",
        "row_details_are_omitted_count_only_report",
        "no_synthetic_marker_is_not_proof_of_production_truth",
        "real_data_digest_pilot_requires_separate_readiness_and_window_checks",
    ]
    if include_synthetic:
        notes.append("synthetic_local_dev_rows_included_for_dev_triage")
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


async def triage_normalized_activity_items(
    query: NormalizedActivityTriageQuery,
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
        raise NormalizedActivityTriageBlockedError(
            "refusing to triage normalized activity in production-like environment"
        ) from exc

    if query.confirm_triage != CONFIRM_TRIAGE_PHRASE:
        raise NormalizedActivityTriageInputError("confirm_triage phrase did not match")

    session_factory = session_factory or AsyncSessionLocal
    normalized_activity = _empty_normalized_activity_summary()
    triage = _empty_triage_summary()
    provider = ConservativeFallbackAttentionTriageProvider()

    try:
        async with session_factory() as session:
            normalized_activity_count = (
                await readiness_script._normalized_activity_count_for_window(
                    session,
                    start_at=query.start_at,
                    end_at=query.end_at,
                )
            )
            if normalized_activity_count > query.max_items:
                raise NormalizedActivityTriageInputError(
                    f"range contains {normalized_activity_count} normalized_activity_items; max_items is {query.max_items}"
                )

            records = await readiness_script._normalized_activity_for_window(
                session,
                start_at=query.start_at,
                end_at=query.end_at,
            )
            normalized_activity = readiness_script._summarize_normalized_activity(records)
            activity_item_ids = {
                record.activity_item_id
                for record in records
                if isinstance(record.activity_item_id, str) and record.activity_item_id
            }
            triaged_activity_item_ids = (
                await readiness_script._linked_attention_activity_item_ids(
                    session,
                    activity_item_ids=activity_item_ids,
                )
            )

            for record in records:
                is_synthetic = readiness_script._is_synthetic_normalized_activity(record)
                if is_synthetic and not query.include_synthetic:
                    triage["synthetic_skipped_count"] += 1
                    continue

                if record.activity_item_id in triaged_activity_item_ids:
                    triage["already_triaged_count"] += 1
                    continue

                try:
                    stored = await attention_results_service.triage_normalized_activity_item(
                        session,
                        activity_item_id=record.activity_item_id,
                        provider=provider,
                    )
                except AttentionResultValidationError:
                    triage["invalid_or_unpreviewable_count"] += 1
                    continue
                except Exception:
                    triage["unsupported_or_unknown_count"] += 1
                    continue

                triage["created_count"] += 1
                if is_synthetic:
                    triage["synthetic_created_count"] += 1
                else:
                    triage["no_marker_created_count"] += 1
                preview_script._bump(
                    triage["by_attention_class"],
                    stored.attention_class,
                )
                preview_script._bump(triage["by_priority"], stored.priority)
                if stored.show_in_digest is True:
                    triage["visible_candidate_count"] += 1
                else:
                    triage["hidden_count"] += 1

            if triage["created_count"] > 0:
                await session.commit()
            else:
                await session.rollback()
    except (
        NormalizedActivityTriageInputError,
        NormalizedActivityTriageBlockedError,
        NormalizedActivityTriageRuntimeError,
    ):
        raise
    except ValueError as exc:
        raise NormalizedActivityTriageInputError(str(exc)) from exc
    except Exception as exc:
        raise NormalizedActivityTriageRuntimeError(
            "normalized activity triage blocked; database, schema, or configuration is unavailable"
        ) from exc

    triage["by_attention_class"] = dict(sorted(triage["by_attention_class"].items()))
    triage["by_priority"] = dict(sorted(triage["by_priority"].items()))
    created_count = preview_script._safe_int(triage.get("created_count"))
    return {
        "status": "normalized_activity_provider_free_triage",
        "start_at": query.start_at.isoformat(),
        "end_at": query.end_at.isoformat(),
        "max_items": query.max_items,
        "include_synthetic": query.include_synthetic,
        "scanned_normalized_activity_count": normalized_activity["total"],
        "normalized_activity": normalized_activity,
        "triage": triage,
        "recommended_next_action": _recommended_next_action(
            normalized_activity_count=normalized_activity["total"],
            triage=triage,
        ),
        "limitations": _limitations(include_synthetic=query.include_synthetic),
        "safety": _safety_metadata(created_count=created_count),
    }


def _print_json(value: Mapping[str, Any]) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def format_text_report(report: Mapping[str, Any]) -> str:
    normalized = (
        report.get("normalized_activity")
        if isinstance(report.get("normalized_activity"), Mapping)
        else {}
    )
    triage = report.get("triage") if isinstance(report.get("triage"), Mapping) else {}
    safety = report.get("safety") if isinstance(report.get("safety"), Mapping) else {}
    lines = [
        "Normalized activity provider-free triage (local/dev write command)",
        f"Window start: {report.get('start_at')}",
        f"Window end: {report.get('end_at')}",
        f"Max items: {report.get('max_items')}",
        f"Include synthetic: {report.get('include_synthetic')}",
        f"Scanned normalized activity: {report.get('scanned_normalized_activity_count')}",
        f"Synthetic status: {normalized.get('synthetic_status')}",
        f"Synthetic marker count: {normalized.get('synthetic_marker_count')}",
        f"No-marker count: {normalized.get('no_marker_count')}",
        f"Created attention results: {triage.get('created_count')}",
        f"Already triaged: {triage.get('already_triaged_count')}",
        f"Unsupported/unknown: {triage.get('unsupported_or_unknown_count')}",
        f"Invalid/unpreviewable: {triage.get('invalid_or_unpreviewable_count')}",
        f"Synthetic skipped: {triage.get('synthetic_skipped_count')}",
        f"No-marker created: {triage.get('no_marker_created_count')}",
        f"Synthetic created: {triage.get('synthetic_created_count')}",
        f"Attention classes: {triage.get('by_attention_class')}",
        f"Priorities: {triage.get('by_priority')}",
        f"Visible candidates: {triage.get('visible_candidate_count')}",
        f"Hidden count: {triage.get('hidden_count')}",
        f"Recommended next action: {report.get('recommended_next_action')}",
        "",
        f"Local/dev only: {safety.get('local_dev_only')}",
        f"Provider free: {safety.get('provider_free')}",
        f"DB write scope: {safety.get('db_write_scope')}",
        f"Source events created: {safety.get('source_events_created')}",
        f"Normalized activity created: {safety.get('normalized_activity_created')}",
        f"Attention results created: {safety.get('attention_results_created')}",
        f"Triage write invoked: {safety.get('triage_write_invoked')}",
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
        report = asyncio.run(triage_normalized_activity_items(query))
    except NormalizedActivityTriageInputError as exc:
        output_format = getattr(locals().get("args", None), "format", "json")
        if output_format == "json":
            _print_json(_blocked_result(error_code="input_error", message=str(exc)))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 2
    except NormalizedActivityTriageBlockedError as exc:
        output_format = getattr(locals().get("args", None), "format", "json")
        if output_format == "json":
            _print_json(_blocked_result(error_code="blocked", message=str(exc)))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 1
    except NormalizedActivityTriageRuntimeError as exc:
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
