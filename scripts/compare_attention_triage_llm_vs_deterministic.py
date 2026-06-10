#!/usr/bin/env python
"""Compare guarded OpenAI attention triage with deterministic fallback.

The command is read-only: it selects normalized activity rows, runs the
conservative fallback and a guarded OpenAI attention triage provider, and
prints aggregate counts/classes only. It does not persist triage results.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import desc, func, select

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.agents.llm_runner import get_openai_client  # noqa: E402
from app.services.attention_triage import (  # noqa: E402
    AttentionContext,
    AttentionTriageProvider,
    AttentionTriageResult,
    ConservativeFallbackAttentionTriageProvider,
    NormalizedActivityItem,
    OpenAIAttentionTriageProvider,
    apply_attention_confidence_policy,
)
from app.services.provider_execution_guard import LIVE_PROVIDER_EXECUTION_ACK  # noqa: E402
from app.services.scheduler_execution_guard import (  # noqa: E402
    READ_ONLY_REVIEW_EXECUTION,
    require_no_scheduler_execution,
)
from scripts import prepare_manual_pilot_delivery_draft as prepare_script  # noqa: E402
from scripts import preview_normalized_activity_triage_readiness as readiness_script  # noqa: E402


REPORT_KIND = "attention_triage_llm_vs_deterministic_comparison"
COMPARISON_ID = "attention_triage_llm_vs_deterministic_v1"
CONFIRM_COMPARE_PHRASE = "COMPARE ATTENTION TRIAGE"
DEFAULT_LOOKBACK_HOURS = 24
DEFAULT_MAX_ITEMS = 5
MAX_COMPARE_ITEMS = 10
SCHEDULER_EXECUTION_DISABLED = "disabled"


class AttentionTriageComparisonInputError(ValueError):
    pass


class AttentionTriageComparisonBlockedError(RuntimeError):
    pass


class AttentionTriageComparisonRuntimeError(RuntimeError):
    pass


@dataclass(frozen=True)
class AttentionTriageComparisonQuery:
    confirm_compare: str
    acknowledge_live_provider_risk: str
    start_at: datetime | None = None
    end_at: datetime | None = None
    lookback_hours: int = DEFAULT_LOOKBACK_HOURS
    max_items: int = DEFAULT_MAX_ITEMS
    include_synthetic: bool = False
    output_format: str = "json"


class _CountingClient:
    def __init__(self, client: Any) -> None:
        self.client = client
        self.call_count = 0

    def __call__(self, payload: Mapping[str, Any]) -> Any:
        self.call_count += 1
        responses = getattr(self.client, "responses", None)
        create = getattr(responses, "create", None)
        if not callable(create):
            raise RuntimeError("openai_client_missing_responses_create")
        return create(**dict(payload))


def _parse_datetime(value: str | None, *, field_name: str) -> datetime | None:
    if value is None:
        return None
    try:
        return prepare_script._parse_datetime(value, field_name=field_name)
    except prepare_script.PrepareInputError as exc:
        raise AttentionTriageComparisonInputError(str(exc)) from exc


def _clean_confirm_compare(value: str) -> str:
    if not isinstance(value, str) or value != CONFIRM_COMPARE_PHRASE:
        raise AttentionTriageComparisonInputError("confirm_compare phrase did not match")
    return value


def _clean_acknowledgement(value: str | None) -> str:
    if value != LIVE_PROVIDER_EXECUTION_ACK:
        raise AttentionTriageComparisonInputError(
            "live provider acknowledgement phrase did not match"
        )
    return value


def _clean_max_items(value: int) -> int:
    if not isinstance(value, int) or value < 1 or value > MAX_COMPARE_ITEMS:
        raise AttentionTriageComparisonInputError(
            f"max_items must be between 1 and {MAX_COMPARE_ITEMS}"
        )
    return value


def _clean_lookback_hours(value: int) -> int:
    if not isinstance(value, int) or value < 1 or value > 24 * 30:
        raise AttentionTriageComparisonInputError(
            "lookback_hours must be between 1 and 720"
        )
    return value


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-at")
    parser.add_argument("--end-at")
    parser.add_argument("--lookback-hours", type=int, default=DEFAULT_LOOKBACK_HOURS)
    parser.add_argument("--max-items", type=int, default=DEFAULT_MAX_ITEMS)
    parser.add_argument("--include-synthetic", action="store_true")
    parser.add_argument("--confirm-compare", required=True)
    parser.add_argument("--acknowledge-live-provider-risk", required=True)
    parser.add_argument("--format", choices=("json", "text"), default="json")
    return parser.parse_args(argv)


def _query_from_args(args: argparse.Namespace) -> AttentionTriageComparisonQuery:
    start_at = _parse_datetime(args.start_at, field_name="start_at")
    end_at = _parse_datetime(args.end_at, field_name="end_at")
    if (start_at is None) != (end_at is None):
        raise AttentionTriageComparisonInputError(
            "start_at and end_at must be provided together"
        )
    if start_at is not None and end_at is not None and end_at <= start_at:
        raise AttentionTriageComparisonInputError("end_at must be after start_at")
    return AttentionTriageComparisonQuery(
        start_at=start_at,
        end_at=end_at,
        lookback_hours=_clean_lookback_hours(args.lookback_hours),
        max_items=_clean_max_items(args.max_items),
        include_synthetic=bool(args.include_synthetic),
        confirm_compare=_clean_confirm_compare(args.confirm_compare),
        acknowledge_live_provider_risk=_clean_acknowledgement(
            args.acknowledge_live_provider_risk
        ),
        output_format=args.format,
    )


def _safe_counts(results: Sequence[AttentionTriageResult]) -> dict[str, Any]:
    return {
        "by_attention_class": dict(
            sorted(Counter(result.attention_class for result in results).items())
        ),
        "by_priority": dict(sorted(Counter(result.priority for result in results).items())),
        "show_in_digest": dict(
            sorted(
                Counter(
                    "true" if result.show_in_digest is True else "false"
                    for result in results
                ).items()
            )
        ),
    }


def _attention_rank(result: AttentionTriageResult) -> int:
    rank_by_class = {
        "requires_my_attention": 5,
        "manual_action": 4,
        "waiting_on_external": 3,
        "important_info": 2,
        "review_optional": 1,
        "no_action_required": 0,
    }
    return rank_by_class[result.attention_class]


def _divergence_type(
    *,
    deterministic: AttentionTriageResult,
    llm: AttentionTriageResult,
) -> str:
    if (
        deterministic.attention_class == llm.attention_class
        and deterministic.priority == llm.priority
        and deterministic.show_in_digest == llm.show_in_digest
    ):
        return "exact_match"
    if deterministic.show_in_digest != llm.show_in_digest:
        return "visibility_changed"
    if deterministic.attention_class != llm.attention_class:
        llm_rank = _attention_rank(llm)
        deterministic_rank = _attention_rank(deterministic)
        if llm_rank > deterministic_rank:
            return "llm_more_urgent_class"
        if llm_rank < deterministic_rank:
            return "llm_less_urgent_class"
        return "attention_class_changed"
    if deterministic.priority != llm.priority:
        return "priority_changed"
    return "other_difference"


def compare_attention_triage_results(
    *,
    deterministic_results: Sequence[AttentionTriageResult],
    llm_results: Sequence[AttentionTriageResult],
) -> dict[str, Any]:
    if len(deterministic_results) != len(llm_results):
        raise AttentionTriageComparisonInputError(
            "deterministic and llm result counts differ"
        )
    divergence_counts = Counter(
        _divergence_type(deterministic=deterministic, llm=llm)
        for deterministic, llm in zip(deterministic_results, llm_results, strict=True)
    )
    return {
        "total": len(deterministic_results),
        "deterministic_counts": _safe_counts(deterministic_results),
        "llm_counts": _safe_counts(llm_results),
        "divergence_type_counts": dict(sorted(divergence_counts.items())),
    }


def _context() -> AttentionContext:
    return AttentionContext(
        instructions=(
            "Compare LLM attention triage against deterministic fallback. "
            "If uncertain, do not hide."
        )
    )


def _classify_many(
    *,
    activities: Iterable[NormalizedActivityItem],
    provider: AttentionTriageProvider,
    context: AttentionContext,
) -> list[AttentionTriageResult]:
    results: list[AttentionTriageResult] = []
    for activity in activities:
        result = provider.classify_activity(activity, context)
        results.append(apply_attention_confidence_policy(result))
    return results


def _safe_settings_status(settings: Any) -> dict[str, str]:
    return {
        "attention_triage_enabled": "enabled"
        if getattr(settings, "attention_triage_enabled", False) is True
        else "disabled",
        "llm_enabled": "enabled"
        if getattr(settings, "enable_llm", False) is True
        else "disabled",
        "openai_key_presence": "present"
        if bool(getattr(settings, "openai_api_key", None))
        else "missing",
    }


def _safety_metadata(*, openai_invoked: bool) -> dict[str, Any]:
    return {
        "read_only": True,
        "db_write_scope": "none",
        "source_events_created": False,
        "normalized_activity_created": False,
        "attention_results_created": False,
        "triage_write_invoked": False,
        "raw_storage_touched": False,
        "obsidian_touched": False,
        "delivery_invoked": False,
        "telegram_invoked": False,
        "slack_invoked": False,
        "scheduler_execution": SCHEDULER_EXECUTION_DISABLED,
        "provider_guard_used": True,
        "openai_invoked": openai_invoked,
        "credential_values_exposed": False,
        "raw_content_printed": False,
        "item_details_included": False,
        "evidence_refs_included": False,
        "private_content_printed": False,
    }


def _blocked_result(*, error_code: str) -> dict[str, Any]:
    return {
        "status": "blocked",
        "report_kind": REPORT_KIND,
        "comparison_id": COMPARISON_ID,
        "error_code": error_code,
        "total": 0,
        "deterministic_counts": _safe_counts([]),
        "llm_counts": _safe_counts([]),
        "divergence_type_counts": {},
        "safety": _safety_metadata(openai_invoked=False),
    }


async def _latest_window(session: Any, *, lookback_hours: int) -> tuple[datetime, datetime]:
    from app.db.event_models import NormalizedActivityItemRecord

    timestamp = func.coalesce(
        NormalizedActivityItemRecord.activity_created_at,
        NormalizedActivityItemRecord.created_at,
    )
    latest = await session.scalar(select(func.max(timestamp)))
    if latest is None:
        raise AttentionTriageComparisonInputError("no_normalized_activity_available")
    end_at = latest + timedelta(seconds=1)
    return end_at - timedelta(hours=lookback_hours), end_at


async def _records_for_window(
    session: Any,
    *,
    start_at: datetime,
    end_at: datetime,
    max_items: int,
) -> list[Any]:
    from app.db.event_models import NormalizedActivityItemRecord

    timestamp = func.coalesce(
        NormalizedActivityItemRecord.activity_created_at,
        NormalizedActivityItemRecord.created_at,
    )
    result = await session.execute(
        select(NormalizedActivityItemRecord)
        .where(timestamp >= start_at)
        .where(timestamp < end_at)
        .order_by(desc(timestamp), desc(NormalizedActivityItemRecord.id))
        .limit(max_items)
    )
    return list(result.scalars().all())


async def build_attention_triage_comparison_report(
    query: AttentionTriageComparisonQuery,
    *,
    session_factory: Callable[[], Any] | None = None,
    settings_override: Any | None = None,
    environ: Mapping[str, str] | None = None,
    llm_provider: AttentionTriageProvider | None = None,
) -> dict[str, Any]:
    from app.core.config import settings
    from app.db.base import AsyncSessionLocal

    active_settings = settings_override or settings
    active_environ = environ if environ is not None else os.environ
    try:
        prepare_script._assert_local_environment(
            settings=active_settings,
            environ=active_environ,
        )
    except prepare_script.PrepareBlockedError as exc:
        raise AttentionTriageComparisonBlockedError(
            "refusing to compare triage in production-like environment"
        ) from exc
    if getattr(active_settings, "attention_triage_enabled", False) is not True:
        raise AttentionTriageComparisonBlockedError("attention_triage_disabled")
    if getattr(active_settings, "enable_llm", False) is not True:
        raise AttentionTriageComparisonBlockedError("llm_disabled")
    if not getattr(active_settings, "openai_api_key", None) and llm_provider is None:
        raise AttentionTriageComparisonBlockedError("openai_key_missing")
    require_no_scheduler_execution(
        boundary=REPORT_KIND,
        execution_source=READ_ONLY_REVIEW_EXECUTION,
    )

    session_factory = session_factory or AsyncSessionLocal
    async with session_factory() as session:
        if query.start_at is None or query.end_at is None:
            start_at, end_at = await _latest_window(
                session,
                lookback_hours=query.lookback_hours,
            )
        else:
            start_at, end_at = query.start_at, query.end_at
        records = await _records_for_window(
            session,
            start_at=start_at,
            end_at=end_at,
            max_items=query.max_items,
        )

    selected_records = [
        record
        for record in records
        if query.include_synthetic or not readiness_script._is_synthetic_normalized_activity(record)
    ]
    if not selected_records:
        raise AttentionTriageComparisonInputError("no_supported_activity_in_window")

    activities = [
        readiness_script._normalized_activity_contract(record)
        for record in selected_records
    ]
    context = _context()
    deterministic_results = _classify_many(
        activities=activities,
        provider=ConservativeFallbackAttentionTriageProvider(),
        context=context,
    )

    counting_client: _CountingClient | None = None
    if llm_provider is None:
        client = get_openai_client(
            allow_live_provider_execution=True,
            provider_execution_ack=query.acknowledge_live_provider_risk,
        )
        counting_client = _CountingClient(client)
        llm_provider = OpenAIAttentionTriageProvider(
            client=counting_client,
            enabled=True,
            model=getattr(active_settings, "attention_triage_model", None),
            max_text_chars=getattr(active_settings, "attention_triage_max_text_chars", 6000),
            min_confidence_to_hide=getattr(
                active_settings,
                "attention_triage_min_confidence_to_hide",
                0.80,
            ),
            review_threshold=getattr(
                active_settings,
                "attention_triage_review_threshold",
                0.55,
            ),
        )

    llm_results = _classify_many(
        activities=activities,
        provider=llm_provider,
        context=context,
    )
    comparison = compare_attention_triage_results(
        deterministic_results=deterministic_results,
        llm_results=llm_results,
    )
    openai_call_count = counting_client.call_count if counting_client is not None else 0
    return {
        "status": "completed",
        "report_kind": REPORT_KIND,
        "comparison_id": COMPARISON_ID,
        "window_id": "latest_normalized_activity_window"
        if query.start_at is None
        else "operator_requested_window",
        "window": {
            "start_at": start_at.isoformat(),
            "end_at": end_at.isoformat(),
            "lookback_hours": query.lookback_hours,
        },
        "max_items": query.max_items,
        "include_synthetic": query.include_synthetic,
        "total": comparison["total"],
        "deterministic_counts": comparison["deterministic_counts"],
        "llm_counts": comparison["llm_counts"],
        "divergence_type_counts": comparison["divergence_type_counts"],
        "provider": {
            "provider_class": "openai_attention_triage",
            "provider_execution_guard": "provider_execution_allowed",
            "openai_call_count": openai_call_count,
            "settings_status": _safe_settings_status(active_settings),
        },
        "safety": _safety_metadata(openai_invoked=openai_call_count > 0),
    }


def _print_json(value: Mapping[str, Any]) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def format_text_report(report: Mapping[str, Any]) -> str:
    lines = [
        "Attention triage LLM vs deterministic comparison",
        f"Status: {report.get('status')}",
        f"Comparison ID: {report.get('comparison_id')}",
        f"Window ID: {report.get('window_id')}",
        f"Total: {report.get('total')}",
        f"LLM counts: {report.get('llm_counts')}",
        f"Deterministic counts: {report.get('deterministic_counts')}",
        f"Divergence type counts: {report.get('divergence_type_counts')}",
        f"Safety: {report.get('safety')}",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parse_args(argv)
        query = _query_from_args(args)
        report = asyncio.run(build_attention_triage_comparison_report(query))
    except AttentionTriageComparisonInputError as exc:
        report = _blocked_result(error_code=str(exc))
        args = locals().get("args")
        output_format = getattr(args, "format", "json")
        if output_format == "json":
            _print_json(report)
        else:
            print(format_text_report(report), end="")
        return 2
    except AttentionTriageComparisonBlockedError as exc:
        report = _blocked_result(error_code=str(exc))
        args = locals().get("args")
        output_format = getattr(args, "format", "json")
        if output_format == "json":
            _print_json(report)
        else:
            print(format_text_report(report), end="")
        return 1
    except Exception:
        report = _blocked_result(error_code="runtime_error")
        args = locals().get("args")
        output_format = getattr(args, "format", "json")
        if output_format == "json":
            _print_json(report)
        else:
            print(format_text_report(report), end="")
        return 1

    if query.output_format == "json":
        _print_json(report)
    else:
        print(format_text_report(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
