#!/usr/bin/env python
"""Preview normalized activity triage readiness without writing rows."""

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

from app.services.attention_triage import (  # noqa: E402
    AttentionContext,
    ConservativeFallbackAttentionTriageProvider,
    NormalizedActivityItem,
    apply_attention_confidence_policy,
)
from scripts import prepare_manual_pilot_delivery_draft as prepare_script  # noqa: E402
from scripts import preview_stored_source_event_normalization as preview_script  # noqa: E402

DEFAULT_MAX_ITEMS = 100
MAX_TRIAGE_READINESS_ITEMS = 500


class TriageReadinessInputError(ValueError):
    pass


class TriageReadinessBlockedError(RuntimeError):
    pass


class TriageReadinessRuntimeError(RuntimeError):
    pass


@dataclass(frozen=True)
class TriageReadinessQuery:
    start_at: datetime
    end_at: datetime
    max_items: int = DEFAULT_MAX_ITEMS
    include_synthetic: bool = False
    sources: tuple[str, ...] = ()
    output_format: str = "json"


def _parse_datetime(value: str, *, field_name: str) -> datetime:
    try:
        return prepare_script._parse_datetime(value, field_name=field_name)
    except prepare_script.PrepareInputError as exc:
        raise TriageReadinessInputError(str(exc)) from exc


def _clean_max_items(value: int) -> int:
    if not isinstance(value, int):
        raise TriageReadinessInputError("max_items must be an integer")
    if value < 1 or value > MAX_TRIAGE_READINESS_ITEMS:
        raise TriageReadinessInputError(
            f"max_items must be between 1 and {MAX_TRIAGE_READINESS_ITEMS}"
        )
    return value


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--start-at",
        required=True,
        help="Timezone-aware ISO start for the normalized activity readiness window.",
    )
    parser.add_argument(
        "--end-at",
        required=True,
        help="Timezone-aware ISO end for the normalized activity readiness window.",
    )
    parser.add_argument(
        "--max-items",
        type=int,
        default=DEFAULT_MAX_ITEMS,
        help=(
            "Maximum normalized activity items to scan, "
            f"1-{MAX_TRIAGE_READINESS_ITEMS}; default {DEFAULT_MAX_ITEMS}."
        ),
    )
    parser.add_argument(
        "--include-synthetic",
        action="store_true",
        help="Include clearly synthetic local/dev normalized activity rows.",
    )
    parser.add_argument(
        "--source",
        action="append",
        default=[],
        help="Limit preview to a normalized activity source; may be provided more than once.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="json",
        help="Output format.",
    )
    return parser.parse_args(argv)


def _query_from_args(args: argparse.Namespace) -> TriageReadinessQuery:
    start_at = _parse_datetime(args.start_at, field_name="start_at")
    end_at = _parse_datetime(args.end_at, field_name="end_at")
    if end_at <= start_at:
        raise TriageReadinessInputError("end_at must be after start_at")
    return TriageReadinessQuery(
        start_at=start_at,
        end_at=end_at,
        max_items=_clean_max_items(args.max_items),
        include_synthetic=bool(args.include_synthetic),
        sources=preview_script._clean_sources(args.source),
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


def _empty_triage_readiness() -> dict[str, Any]:
    return {
        "already_triaged_count": 0,
        "untriaged_count": 0,
        "eligible_for_provider_free_triage_count": 0,
        "unsupported_or_unknown_count": 0,
        "invalid_or_unpreviewable_count": 0,
        "synthetic_skipped_count": 0,
        "no_marker_eligible_count": 0,
        "synthetic_eligible_count": 0,
    }


def _empty_projected_triage() -> dict[str, Any]:
    return {
        "available": True,
        "by_attention_class": {},
        "by_priority": {},
        "visible_candidate_count": 0,
        "hidden_count": 0,
        "limitations": [
            "projected_counts_use_provider_free_conservative_fallback_only",
            "projected_counts_are_not_persisted_attention_results",
        ],
    }


async def _normalized_activity_count_for_window(
    session: Any,
    *,
    start_at: datetime,
    end_at: datetime,
    sources: tuple[str, ...] = (),
) -> int:
    from app.db.event_models import NormalizedActivityItemRecord

    activity_time = func.coalesce(
        NormalizedActivityItemRecord.activity_created_at,
        NormalizedActivityItemRecord.created_at,
    )
    statement = (
        select(func.count())
        .select_from(NormalizedActivityItemRecord)
        .where(activity_time >= start_at, activity_time < end_at)
    )
    if sources:
        statement = statement.where(NormalizedActivityItemRecord.source.in_(sources))
    return int(
        await session.scalar(statement)
        or 0
    )


async def _normalized_activity_for_window(
    session: Any,
    *,
    start_at: datetime,
    end_at: datetime,
    sources: tuple[str, ...] = (),
) -> list[Any]:
    from app.db.event_models import NormalizedActivityItemRecord

    activity_time = func.coalesce(
        NormalizedActivityItemRecord.activity_created_at,
        NormalizedActivityItemRecord.created_at,
    )
    statement = (
        select(NormalizedActivityItemRecord)
        .where(activity_time >= start_at, activity_time < end_at)
        .order_by(NormalizedActivityItemRecord.id)
    )
    if sources:
        statement = statement.where(NormalizedActivityItemRecord.source.in_(sources))
    return (
        await session.scalars(statement)
    ).all()


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


def _is_synthetic_normalized_activity(record: Any) -> bool:
    return (
        getattr(record, "source", None) == "internal"
        and isinstance(getattr(record, "source_object_id", None), str)
        and record.source_object_id.startswith(
            preview_script.SYNTHETIC_SOURCE_OBJECT_PREFIX
        )
    )


def _summarize_normalized_activity(records: list[Any]) -> dict[str, Any]:
    by_source: dict[str, int] = {}
    by_activity_type: dict[str, int] = {}
    synthetic_count = 0

    for record in records:
        if _is_synthetic_normalized_activity(record):
            synthetic_count += 1
        preview_script._bump(by_source, record.source)
        preview_script._bump(by_activity_type, record.activity_type)

    no_marker_count = max(len(records) - synthetic_count, 0)
    return {
        "total": len(records),
        "by_source": dict(sorted(by_source.items())),
        "by_activity_type": dict(sorted(by_activity_type.items())),
        "synthetic_marker_count": synthetic_count,
        "no_marker_count": no_marker_count,
        "synthetic_status": preview_script._synthetic_status(
            synthetic_count=synthetic_count,
            no_marker_count=no_marker_count,
            total=len(records),
        ),
    }


def _normalized_activity_contract(record: Any) -> NormalizedActivityItem:
    return NormalizedActivityItem(
        source=record.source,
        source_object_id=record.source_object_id,
        activity_type=record.activity_type,
        title=record.title,
        actor=record.actor,
        created_at=record.activity_created_at,
        project=record.project,
        safe_summary=record.safe_summary,
        related_people=[
            value for value in record.related_people if isinstance(value, str)
        ],
        related_jira_keys=[
            value for value in record.related_jira_keys if isinstance(value, str)
        ],
        related_prs=[value for value in record.related_prs if isinstance(value, str)],
        related_files=[
            value for value in record.related_files if isinstance(value, str)
        ],
        evidence_refs=[dict(ref) for ref in record.evidence_refs if isinstance(ref, dict)],
    )


def _preview_provider_free_triage(record: Any) -> Any:
    provider = ConservativeFallbackAttentionTriageProvider()
    context = AttentionContext(
        instructions=(
            "Provider-free readiness preview only. Produce aggregate counts; "
            "do not persist triage output."
        )
    )
    result = provider.classify_activity(_normalized_activity_contract(record), context)
    return apply_attention_confidence_policy(result)


def _recommended_next_action(
    *,
    normalized_activity_count: int,
    include_synthetic: bool,
    triage_readiness: Mapping[str, Any],
    projected_provider_free_triage: Mapping[str, Any],
) -> str:
    already = preview_script._safe_int(triage_readiness.get("already_triaged_count"))
    eligible = preview_script._safe_int(
        triage_readiness.get("eligible_for_provider_free_triage_count")
    )
    no_marker_eligible = preview_script._safe_int(
        triage_readiness.get("no_marker_eligible_count")
    )
    synthetic_skipped = preview_script._safe_int(
        triage_readiness.get("synthetic_skipped_count")
    )
    unsupported = preview_script._safe_int(
        triage_readiness.get("unsupported_or_unknown_count")
    )
    invalid = preview_script._safe_int(
        triage_readiness.get("invalid_or_unpreviewable_count")
    )

    if normalized_activity_count == 0:
        return "normalize_source_events_before_triage"
    if (
        synthetic_skipped > 0
        and not include_synthetic
        and eligible == 0
        and already == 0
    ):
        return "rerun_with_include_synthetic_for_dev_preview_or_choose_no_marker_window"
    if no_marker_eligible > 0 and projected_provider_free_triage.get("available") is True:
        return "review_triage_readiness_before_local_provider_free_triage"
    if no_marker_eligible > 0:
        return "inspect_provider_free_triage_support_before_write"
    if eligible > 0 and projected_provider_free_triage.get("available") is True:
        return "review_triage_readiness_before_local_provider_free_triage"
    if already > 0 and eligible == 0 and unsupported == 0 and invalid == 0:
        return "run_real_stored_local_data_readiness_report"
    if unsupported > 0 or invalid > 0:
        return "no_supported_normalized_activity_for_provider_free_triage"
    return "no_supported_normalized_activity_for_provider_free_triage"


def _safety_metadata() -> dict[str, Any]:
    return {
        "provider_free": True,
        "read_only": True,
        "local_operator_command": True,
        "db_write_scope": "none",
        "source_events_created": False,
        "normalized_activity_created": False,
        "attention_results_created": False,
        "triage_write_invoked": False,
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
        "triage_readiness_reports_counts_only_not_company_facts",
        "projected_triage_uses_provider_free_conservative_fallback_only",
        "projected_triage_is_not_persisted_attention_result_data",
        "row_identifiers_are_not_returned",
        "row_details_are_omitted_count_only_report",
        "no_synthetic_marker_is_not_proof_of_production_truth",
        "future_triage_write_requires_separate_explicit_local_command",
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


async def build_normalized_activity_triage_readiness_preview(
    query: TriageReadinessQuery,
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
        raise TriageReadinessBlockedError(str(exc)) from exc

    session_factory = session_factory or AsyncSessionLocal
    normalized_activity = _empty_normalized_activity_summary()
    triage_readiness = _empty_triage_readiness()
    projected_triage = _empty_projected_triage()

    try:
        async with session_factory() as session:
            normalized_activity_count = await _normalized_activity_count_for_window(
                session,
                start_at=query.start_at,
                end_at=query.end_at,
                sources=query.sources,
            )
            if normalized_activity_count > query.max_items:
                raise TriageReadinessInputError(
                    f"range contains {normalized_activity_count} normalized_activity_items; max_items is {query.max_items}"
                )

            records = await _normalized_activity_for_window(
                session,
                start_at=query.start_at,
                end_at=query.end_at,
                sources=query.sources,
            )
            normalized_activity = _summarize_normalized_activity(records)
            activity_item_ids = {
                record.activity_item_id
                for record in records
                if isinstance(record.activity_item_id, str) and record.activity_item_id
            }
            triaged_activity_item_ids = await _linked_attention_activity_item_ids(
                session,
                activity_item_ids=activity_item_ids,
            )

            for record in records:
                is_synthetic = _is_synthetic_normalized_activity(record)
                if is_synthetic and not query.include_synthetic:
                    triage_readiness["synthetic_skipped_count"] += 1
                    continue

                if record.activity_item_id in triaged_activity_item_ids:
                    triage_readiness["already_triaged_count"] += 1
                    continue

                triage_readiness["untriaged_count"] += 1
                try:
                    result = _preview_provider_free_triage(record)
                except ValueError:
                    triage_readiness["invalid_or_unpreviewable_count"] += 1
                    continue
                except Exception:
                    triage_readiness["unsupported_or_unknown_count"] += 1
                    continue

                triage_readiness["eligible_for_provider_free_triage_count"] += 1
                if is_synthetic:
                    triage_readiness["synthetic_eligible_count"] += 1
                else:
                    triage_readiness["no_marker_eligible_count"] += 1
                preview_script._bump(
                    projected_triage["by_attention_class"],
                    result.attention_class,
                )
                preview_script._bump(projected_triage["by_priority"], result.priority)
                if result.show_in_digest is True:
                    projected_triage["visible_candidate_count"] += 1
                else:
                    projected_triage["hidden_count"] += 1
    except (
        TriageReadinessInputError,
        TriageReadinessBlockedError,
        TriageReadinessRuntimeError,
    ):
        raise
    except ValueError as exc:
        raise TriageReadinessInputError(str(exc)) from exc
    except Exception as exc:
        raise TriageReadinessRuntimeError(
            "normalized activity triage readiness preview blocked; database, schema, or configuration is unavailable"
        ) from exc

    projected_triage["by_attention_class"] = dict(
        sorted(projected_triage["by_attention_class"].items())
    )
    projected_triage["by_priority"] = dict(
        sorted(projected_triage["by_priority"].items())
    )
    return {
        "status": "normalized_activity_triage_readiness_preview",
        "start_at": query.start_at.isoformat(),
        "end_at": query.end_at.isoformat(),
        "max_items": query.max_items,
        "include_synthetic": query.include_synthetic,
        "sources": list(query.sources),
        "scanned_normalized_activity_count": normalized_activity["total"],
        "normalized_activity": normalized_activity,
        "triage_readiness": triage_readiness,
        "projected_provider_free_triage": projected_triage,
        "recommended_next_action": _recommended_next_action(
            normalized_activity_count=normalized_activity["total"],
            include_synthetic=query.include_synthetic,
            triage_readiness=triage_readiness,
            projected_provider_free_triage=projected_triage,
        ),
        "limitations": _limitations(include_synthetic=query.include_synthetic),
        "safety": _safety_metadata(),
    }


def _print_json(value: Mapping[str, Any]) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def format_text_report(report: Mapping[str, Any]) -> str:
    normalized = (
        report.get("normalized_activity")
        if isinstance(report.get("normalized_activity"), Mapping)
        else {}
    )
    readiness = (
        report.get("triage_readiness")
        if isinstance(report.get("triage_readiness"), Mapping)
        else {}
    )
    projected = (
        report.get("projected_provider_free_triage")
        if isinstance(report.get("projected_provider_free_triage"), Mapping)
        else {}
    )
    safety = report.get("safety") if isinstance(report.get("safety"), Mapping) else {}
    lines = [
        "Normalized activity triage readiness preview (read-only; no writes)",
        f"Window start: {report.get('start_at')}",
        f"Window end: {report.get('end_at')}",
        f"Max items: {report.get('max_items')}",
        f"Include synthetic: {report.get('include_synthetic')}",
        f"Scanned normalized activity: {report.get('scanned_normalized_activity_count')}",
        f"Synthetic status: {normalized.get('synthetic_status')}",
        f"Synthetic marker count: {normalized.get('synthetic_marker_count')}",
        f"No-marker count: {normalized.get('no_marker_count')}",
        f"Already triaged: {readiness.get('already_triaged_count')}",
        f"Untriaged: {readiness.get('untriaged_count')}",
        "Eligible for provider-free triage: "
        f"{readiness.get('eligible_for_provider_free_triage_count')}",
        f"No-marker eligible: {readiness.get('no_marker_eligible_count')}",
        f"Synthetic eligible: {readiness.get('synthetic_eligible_count')}",
        f"Unsupported/unknown: {readiness.get('unsupported_or_unknown_count')}",
        f"Invalid/unpreviewable: {readiness.get('invalid_or_unpreviewable_count')}",
        f"Synthetic skipped: {readiness.get('synthetic_skipped_count')}",
        f"Projected attention classes: {projected.get('by_attention_class')}",
        f"Projected priorities: {projected.get('by_priority')}",
        f"Projected visible candidates: {projected.get('visible_candidate_count')}",
        f"Projected hidden count: {projected.get('hidden_count')}",
        f"Recommended next action: {report.get('recommended_next_action')}",
        "",
        f"Read-only: {safety.get('read_only')}",
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
        report = asyncio.run(build_normalized_activity_triage_readiness_preview(query))
    except TriageReadinessInputError as exc:
        output_format = getattr(locals().get("args", None), "format", "json")
        if output_format == "json":
            _print_json(_blocked_result(error_code="input_error", message=str(exc)))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 2
    except TriageReadinessBlockedError as exc:
        output_format = getattr(locals().get("args", None), "format", "json")
        if output_format == "json":
            _print_json(_blocked_result(error_code="blocked", message=str(exc)))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 1
    except TriageReadinessRuntimeError as exc:
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
