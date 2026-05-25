#!/usr/bin/env python
"""Report read-only manual pilot lifecycle status for a digest window."""

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

from sqlalchemy import select

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.services.digest import (  # noqa: E402
    DEFAULT_DIGEST_ENTRY_LIMIT,
    MAX_DIGEST_ENTRY_LIMIT,
)
from scripts import continue_manual_pilot_delivery_draft as continue_script  # noqa: E402
from scripts import prepare_manual_pilot_delivery_draft as prepare_script  # noqa: E402
from scripts import report_digest_delivery_intention_send_status as status_script  # noqa: E402
from scripts import seed_local_persisted_attention_digest as seed_script  # noqa: E402
from scripts import send_test_telegram_delivery_intention as send_script  # noqa: E402


class ManualPilotStatusInputError(ValueError):
    pass


class ManualPilotStatusBlockedError(RuntimeError):
    pass


class ManualPilotStatusRuntimeError(RuntimeError):
    pass


@dataclass(frozen=True)
class ManualPilotStatusQuery:
    start_at: datetime
    end_at: datetime
    sample_id: str | None = None
    limit: int = DEFAULT_DIGEST_ENTRY_LIMIT
    debug_evidence: bool = False
    output_format: str = "json"


def _parse_datetime(value: str, *, field_name: str) -> datetime:
    try:
        return prepare_script._parse_datetime(value, field_name=field_name)
    except prepare_script.PrepareInputError as exc:
        raise ManualPilotStatusInputError(str(exc)) from exc


def _clean_limit(value: int) -> int:
    if not isinstance(value, int):
        raise ManualPilotStatusInputError("limit must be an integer")
    if value < 1 or value > MAX_DIGEST_ENTRY_LIMIT:
        raise ManualPilotStatusInputError(
            f"limit must be between 1 and {MAX_DIGEST_ENTRY_LIMIT}"
        )
    return value


def _clean_sample_id(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        return seed_script._clean_sample_id(value)
    except seed_script.SeedInputError as exc:
        raise ManualPilotStatusInputError(str(exc)) from exc


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--start-at",
        required=True,
        help="Timezone-aware ISO start for the persisted attention digest window.",
    )
    parser.add_argument(
        "--end-at",
        required=True,
        help="Timezone-aware ISO end for the persisted attention digest window.",
    )
    parser.add_argument(
        "--sample-id",
        help="Optional synthetic sample id to summarize if safely discoverable.",
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
        "--format",
        choices=("text", "json"),
        default="json",
        help="Output format.",
    )
    return parser.parse_args(argv)


def _query_from_args(args: argparse.Namespace) -> ManualPilotStatusQuery:
    start_at = _parse_datetime(args.start_at, field_name="start_at")
    end_at = _parse_datetime(args.end_at, field_name="end_at")
    if end_at <= start_at:
        raise ManualPilotStatusInputError("end_at must be after start_at")
    return ManualPilotStatusQuery(
        start_at=start_at,
        end_at=end_at,
        sample_id=_clean_sample_id(args.sample_id),
        limit=_clean_limit(args.limit),
        debug_evidence=bool(args.debug_evidence),
        output_format=args.format,
    )


def _safe_int(value: Any) -> int:
    return int(value) if isinstance(value, int) and not isinstance(value, bool) else 0


def _safe_count_mapping(value: Any) -> dict[str, int]:
    if not isinstance(value, Mapping):
        return {}
    return {
        str(key): _safe_int(count)
        for key, count in sorted(value.items())
        if isinstance(key, str)
    }


def _safe_digest_summary(digest: Mapping[str, Any]) -> dict[str, Any]:
    counts = digest.get("counts") if isinstance(digest.get("counts"), Mapping) else {}
    hidden_summary = (
        digest.get("hidden_low_priority_summary")
        if isinstance(digest.get("hidden_low_priority_summary"), Mapping)
        else {}
    )
    metadata = digest.get("metadata") if isinstance(digest.get("metadata"), Mapping) else {}
    return {
        "total": _safe_int(counts.get("total")),
        "visible": _safe_int(counts.get("visible")),
        "hidden": _safe_int(counts.get("hidden")),
        "shown": _safe_int(counts.get("shown")),
        "hidden_low_priority_count": _safe_int(hidden_summary.get("total")),
        "by_attention_class": _safe_count_mapping(counts.get("by_attention_class")),
        "by_priority": _safe_count_mapping(counts.get("by_priority")),
        "by_show_in_digest": _safe_count_mapping(counts.get("by_show_in_digest")),
        "by_source": _safe_count_mapping(counts.get("by_source")),
        "metadata": status_script._safe_keys(
            metadata,
            (
                "source_model",
                "enrichment_model",
                "group_limit",
                "truncated",
                "llm_used",
                "read_model_only",
                "source_activity_digest_replaced",
            ),
        ),
    }


def _safe_draft_usage_status(value: Mapping[str, Any]) -> dict[str, Any]:
    return status_script._safe_keys(
        value,
        (
            "status",
            "delivery_draft_id",
            "associated_delivery_intention_count",
            "stale_or_already_sent_warning",
            "blocker",
            "prior_successful_delivery_intention_id",
            "prior_successful_delivery_result_id",
            "prior_successful_execution_attempt_id",
            "prior_successful_delivered_chunk_count",
            "recommended_next_action",
        ),
    ) | {
        "delivery_results_summary": dict(value.get("delivery_results_summary", {}))
        if isinstance(value.get("delivery_results_summary"), Mapping)
        else {},
    }


def _report_safety_metadata() -> dict[str, Any]:
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


async def _sample_metadata(
    session: Any,
    *,
    sample_id: str | None,
    start_at: datetime,
    end_at: datetime,
) -> dict[str, Any]:
    if sample_id is None:
        return {
            "provided": False,
            "sample_id": None,
            "match_found": False,
            "synthetic_local_dev_only": None,
            "not_company_truth": True,
        }

    from app.db.attention_models import AttentionTriageResultRecord

    records = list(
        (
            await session.scalars(
                select(AttentionTriageResultRecord)
                .where(AttentionTriageResultRecord.created_at >= start_at)
                .where(AttentionTriageResultRecord.created_at < end_at)
                .order_by(AttentionTriageResultRecord.id)
            )
        ).all()
    )
    prefix = f"local.synthetic.persisted_attention_seed:{sample_id}:"
    matches = [
        record
        for record in records
        if record.source == "internal"
        and isinstance(record.source_object_id, str)
        and record.source_object_id.startswith(prefix)
    ]
    return {
        "provided": True,
        "sample_id": sample_id,
        "match_found": bool(matches),
        "synthetic_local_dev_only": bool(matches),
        "not_company_truth": True,
        "matched_attention_result_count": len(matches),
        "visible_matched_attention_result_count": sum(
            1 for record in matches if record.show_in_digest is True
        ),
    }


def _safe_delivery_intention(value: Mapping[str, Any]) -> dict[str, Any]:
    return status_script._safe_keys(
        value,
        (
            "delivery_intention_id",
            "delivery_draft_id",
            "digest_type",
            "channel",
            "current_decision",
            "eligible_for_delivery",
            "text_sha256",
            "char_count",
            "chunk_count",
            "sent",
            "scheduler_invoked",
            "recorded_at",
        ),
    )


async def _draft_lifecycle_summary(
    session: Any,
    *,
    draft: Mapping[str, Any],
) -> dict[str, Any]:
    from app.services.digest_delivery_drafts import (
        get_delivery_draft_send_status,
        get_digest_delivery_draft_approval_status,
        get_digest_delivery_draft_delivery_readiness,
        get_successful_delivery_result_for_delivery_intention,
        list_delivery_intentions_for_delivery_draft,
        list_delivery_results_for_delivery_intention,
    )

    delivery_draft_id = str(draft.get("delivery_draft_id") or "")
    approval_status = await get_digest_delivery_draft_approval_status(
        session,
        delivery_draft_id=delivery_draft_id,
    )
    readiness = await get_digest_delivery_draft_delivery_readiness(
        session,
        delivery_draft_id=delivery_draft_id,
    )
    draft_usage_status = await get_delivery_draft_send_status(
        session,
        delivery_draft_id=delivery_draft_id,
    )
    intentions = await list_delivery_intentions_for_delivery_draft(
        session,
        delivery_draft_id=delivery_draft_id,
    )

    intention_summaries = []
    for intention in intentions:
        delivery_intention_id = str(intention.get("delivery_intention_id") or "")
        if not delivery_intention_id:
            continue
        delivery_results = await list_delivery_results_for_delivery_intention(
            session,
            delivery_intention_id=delivery_intention_id,
        )
        prior_success = await get_successful_delivery_result_for_delivery_intention(
            session,
            delivery_intention_id=delivery_intention_id,
        )
        duplicate_guard = status_script._duplicate_guard_summary(prior_success)
        intention_summaries.append(
            {
                **_safe_delivery_intention(intention),
                "delivery_results": status_script._delivery_result_summary(
                    delivery_results
                ),
                "duplicate_guard": duplicate_guard,
                "recommended_next_action": (
                    "do_not_resend_same_intention"
                    if duplicate_guard["would_block_new_execution_attempt"]
                    else "safe_to_consider_new_bounded_attempt"
                ),
            }
        )

    safe_usage_status = (
        _safe_draft_usage_status(draft_usage_status)
        if isinstance(draft_usage_status, Mapping)
        else {}
    )
    return {
        "delivery_draft_id": draft.get("delivery_draft_id"),
        "digest_type": draft.get("digest_type"),
        "channel": draft.get("channel"),
        "status": draft.get("status"),
        "persisted": bool(draft.get("persisted")),
        "start_at": draft.get("start_at"),
        "end_at": draft.get("end_at"),
        "limit": draft.get("limit"),
        "debug_evidence": bool(draft.get("debug_evidence")),
        "text_sha256": draft.get("text_sha256"),
        "char_count": draft.get("char_count"),
        "chunk_count": draft.get("chunk_count"),
        "recorded_at": draft.get("recorded_at"),
        "approval_status": status_script._safe_approval_status(approval_status or {}),
        "readiness": status_script._safe_readiness(readiness or {}),
        "draft_usage_status": safe_usage_status,
        "associated_delivery_intentions": intention_summaries,
        "delivery_results_summary": safe_usage_status.get(
            "delivery_results_summary",
            {},
        ),
        "stale_or_already_sent_warning": bool(
            safe_usage_status.get("stale_or_already_sent_warning")
        ),
        "blocker": safe_usage_status.get("blocker"),
    }


def _lifecycle_summary(
    *,
    digest: Mapping[str, Any],
    drafts: list[dict[str, Any]],
) -> dict[str, Any]:
    has_successful_result = any(
        draft.get("delivery_results_summary", {}).get("successful_count", 0) > 0
        for draft in drafts
    )
    duplicate_guard_blocks = any(
        intention.get("duplicate_guard", {}).get("would_block_new_execution_attempt")
        is True
        for draft in drafts
        for intention in draft.get("associated_delivery_intentions", [])
        if isinstance(intention, Mapping)
    )
    return {
        "has_digest_items": _safe_int(digest.get("total")) > 0,
        "has_visible_items": _safe_int(digest.get("visible")) > 0,
        "has_delivery_draft": bool(drafts),
        "has_approved_draft": any(
            draft.get("approval_status", {}).get("approved") is True
            for draft in drafts
        ),
        "has_delivery_intention": any(
            draft.get("associated_delivery_intentions") for draft in drafts
        ),
        "has_successful_delivery_result": has_successful_result,
        "duplicate_guard_would_block_any_known_intention": duplicate_guard_blocks,
        "stale_or_already_sent_warning": any(
            draft.get("stale_or_already_sent_warning") is True for draft in drafts
        ),
    }


def _recommended_next_action(
    *,
    digest: Mapping[str, Any],
    drafts: list[dict[str, Any]],
    lifecycle_summary: Mapping[str, Any],
) -> str:
    if _safe_int(digest.get("visible")) < 1:
        return "seed_or_choose_non_empty_window"
    if not drafts:
        return "prepare_manual_pilot_delivery_draft"

    active_drafts = [
        draft
        for draft in drafts
        if draft.get("stale_or_already_sent_warning") is not True
    ]
    if not active_drafts and lifecycle_summary.get("stale_or_already_sent_warning"):
        return "create_new_digest_window_or_synthetic_sample_before_another_send"

    for draft in active_drafts:
        approval = draft.get("approval_status", {})
        if (
            isinstance(approval, Mapping)
            and approval.get("approved") is not True
            and approval.get("rejected") is not True
        ):
            return "approve_delivery_draft"

    for draft in active_drafts:
        approval = draft.get("approval_status", {})
        if (
            isinstance(approval, Mapping)
            and approval.get("approved") is True
            and not draft.get("associated_delivery_intentions")
        ):
            return "continue_approved_draft_handoff"

    for draft in active_drafts:
        for intention in draft.get("associated_delivery_intentions", []):
            if not isinstance(intention, Mapping):
                continue
            duplicate_guard = intention.get("duplicate_guard", {})
            if (
                isinstance(duplicate_guard, Mapping)
                and duplicate_guard.get("would_block_new_execution_attempt") is not True
            ):
                return "review_gate_before_bounded_send"

    if lifecycle_summary.get("has_successful_delivery_result"):
        return "create_new_digest_window_or_synthetic_sample_before_another_send"
    return "seed_or_choose_non_empty_window"


def _first_known_id(
    drafts: list[dict[str, Any]],
    *,
    field: str,
    placeholder: str,
) -> str:
    for draft in drafts:
        if field == "delivery_draft_id":
            value = draft.get("delivery_draft_id")
            if isinstance(value, str) and value:
                return value
        for intention in draft.get("associated_delivery_intentions", []):
            if isinstance(intention, Mapping):
                value = intention.get(field)
                if isinstance(value, str) and value:
                    return value
    return placeholder


def _next_step_commands(
    *,
    query: ManualPilotStatusQuery,
    drafts: list[dict[str, Any]],
) -> dict[str, str]:
    delivery_draft_id = _first_known_id(
        drafts,
        field="delivery_draft_id",
        placeholder="<DELIVERY_DRAFT_ID>",
    )
    delivery_intention_id = _first_known_id(
        drafts,
        field="delivery_intention_id",
        placeholder="<DELIVERY_INTENTION_ID>",
    )
    sample_arg = f" --sample-id {query.sample_id}" if query.sample_id else ""
    debug_arg = " --debug-evidence" if query.debug_evidence else ""
    return {
        "check_manual_pilot_status": (
            "python scripts/report_manual_pilot_status.py "
            f"--start-at {query.start_at.isoformat()} "
            f"--end-at {query.end_at.isoformat()}{sample_arg} "
            f"--limit {query.limit}{debug_arg} --format json"
        ),
        "seed_and_prepare_fresh_draft": (
            "python scripts/seed_and_prepare_manual_pilot_delivery_draft.py "
            "--sample-id <NEW_SAMPLE_ID> --created-at <CREATED_AT> "
            f"--confirm-local-seed \"{seed_script.CONFIRM_LOCAL_SEED_PHRASE}\" "
            f"--confirm-prepare \"{prepare_script.CONFIRM_PREPARE_PHRASE}\" "
            f"--limit {query.limit}{debug_arg} --format json"
        ),
        "prepare_manual_pilot_delivery_draft": (
            "python scripts/prepare_manual_pilot_delivery_draft.py "
            f"--start-at {query.start_at.isoformat()} "
            f"--end-at {query.end_at.isoformat()} "
            f"--confirm-prepare \"{prepare_script.CONFIRM_PREPARE_PHRASE}\" "
            f"--limit {query.limit}{debug_arg} --format json"
        ),
        "approve_draft": (
            "curl -sS -X POST '<API_BASE_URL>/v1/digest/delivery-drafts/"
            f"{delivery_draft_id}/approve' "
            "-H '<AUTH_HEADER>: <AUTH_VALUE>' "
            "-H 'Content-Type: application/json' "
            "-d '{\"reviewer\":\"<REVIEWER>\",\"note\":\"<SAFE_NOTE>\"}'"
        ),
        "continue_approved_draft_handoff": (
            "python scripts/continue_manual_pilot_delivery_draft.py "
            f"--delivery-draft-id {delivery_draft_id} "
            f"--confirm-create-intention \"{continue_script.CONFIRM_CREATE_INTENTION_PHRASE}\" "
            "--format json"
        ),
        "review_delivery_intention": (
            "python scripts/review_digest_delivery_intention.py "
            f"--delivery-intention-id {delivery_intention_id} --format json"
        ),
        "check_send_status": (
            "python scripts/report_digest_delivery_intention_send_status.py "
            f"--delivery-intention-id {delivery_intention_id} --format json"
        ),
        "check_execution_gate": (
            "curl -sS '<API_BASE_URL>/v1/digest/delivery-intentions/"
            f"{delivery_intention_id}/telegram-execution-gate' "
            "-H '<AUTH_HEADER>: <AUTH_VALUE>'"
        ),
        "bounded_test_send_do_not_run_until_checks_pass": (
            "DO NOT RUN UNTIL CHECKS PASS: "
            "python scripts/send_test_telegram_delivery_intention.py "
            f"--delivery-intention-id {delivery_intention_id} "
            "--execution-attempt-id <EXECUTION_ATTEMPT_ID> "
            "--max-chunks 1 --test-mode true "
            f"--confirm-send \"{send_script.CONFIRM_SEND_PHRASE}\" --format json"
        ),
    }


def _limitations(*, drafts: list[dict[str, Any]], sample_id: str | None) -> list[str]:
    notes = [
        "delivery_draft_association_uses_exact_window_limit_debug_evidence_and_channel",
        "report_summarizes_audit_metadata_only_not_company_facts",
    ]
    if sample_id is not None:
        notes.append("sample_id_metadata_is_best_effort_from_synthetic_seed_rows")
    if not drafts:
        notes.append("no_matching_delivery_draft_audit_rows_found_for_exact_window")
    return notes


async def build_manual_pilot_status_report(
    query: ManualPilotStatusQuery,
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
        raise ManualPilotStatusBlockedError(str(exc)) from exc

    session_factory = session_factory or AsyncSessionLocal
    try:
        async with session_factory() as session:
            digest = await build_persisted_attention_digest_read_model(
                session,
                start_at=query.start_at,
                end_at=query.end_at,
                limit_per_section=query.limit,
            )
            digest_summary = _safe_digest_summary(digest)
            sample_metadata = await _sample_metadata(
                session,
                sample_id=query.sample_id,
                start_at=query.start_at,
                end_at=query.end_at,
            )
            matching_drafts = await list_persisted_digest_delivery_drafts_for_window(
                session,
                start_at=query.start_at,
                end_at=query.end_at,
                limit=query.limit,
                debug_evidence=query.debug_evidence,
            )
            draft_summaries = [
                await _draft_lifecycle_summary(session, draft=draft)
                for draft in matching_drafts
            ]
    except (
        ManualPilotStatusInputError,
        ManualPilotStatusBlockedError,
        ManualPilotStatusRuntimeError,
    ):
        raise
    except ValueError as exc:
        raise ManualPilotStatusInputError(str(exc)) from exc
    except Exception as exc:
        raise ManualPilotStatusRuntimeError(
            "manual pilot status report blocked; database, schema, or configuration is unavailable"
        ) from exc

    lifecycle_summary = _lifecycle_summary(
        digest=digest_summary,
        drafts=draft_summaries,
    )
    recommended_next_action = _recommended_next_action(
        digest=digest_summary,
        drafts=draft_summaries,
        lifecycle_summary=lifecycle_summary,
    )
    return {
        "status": "manual_pilot_status",
        "sample_id": query.sample_id,
        "start_at": query.start_at.isoformat(),
        "end_at": query.end_at.isoformat(),
        "limit": query.limit,
        "debug_evidence": query.debug_evidence,
        "sample": sample_metadata,
        "digest": digest_summary,
        "drafts": {
            "count": len(draft_summaries),
            "items": draft_summaries,
        },
        "lifecycle_summary": lifecycle_summary,
        "recommended_next_action": recommended_next_action,
        "next_steps": _next_step_commands(query=query, drafts=draft_summaries),
        "safety": _report_safety_metadata(),
        "limitations": _limitations(
            drafts=draft_summaries,
            sample_id=query.sample_id,
        ),
    }


def _blocked_result(*, error_code: str, message: str) -> dict[str, Any]:
    return {
        "status": "blocked",
        "error_code": error_code,
        "message": message,
        "safety": _report_safety_metadata(),
    }


def _print_json(value: Mapping[str, Any]) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def format_text_report(report: Mapping[str, Any]) -> str:
    digest = report.get("digest") if isinstance(report.get("digest"), Mapping) else {}
    drafts = report.get("drafts") if isinstance(report.get("drafts"), Mapping) else {}
    lifecycle = (
        report.get("lifecycle_summary")
        if isinstance(report.get("lifecycle_summary"), Mapping)
        else {}
    )
    next_steps = (
        report.get("next_steps") if isinstance(report.get("next_steps"), Mapping) else {}
    )
    safety = report.get("safety") if isinstance(report.get("safety"), Mapping) else {}
    lines = [
        "Manual pilot status (read-only; no send)",
        f"Sample ID: {report.get('sample_id')}",
        f"Window start: {report.get('start_at')}",
        f"Window end: {report.get('end_at')}",
        f"Limit: {report.get('limit')}",
        f"Debug evidence: {report.get('debug_evidence')}",
        f"Digest total: {digest.get('total')}",
        f"Digest visible: {digest.get('visible')}",
        f"Digest hidden: {digest.get('hidden')}",
        f"Hidden low-priority count: {digest.get('hidden_low_priority_count')}",
        f"Delivery draft count: {drafts.get('count', 0)}",
        f"Has approved draft: {lifecycle.get('has_approved_draft')}",
        f"Has delivery intention: {lifecycle.get('has_delivery_intention')}",
        "Has successful delivery result: "
        f"{lifecycle.get('has_successful_delivery_result')}",
        "Duplicate guard would block any known intention: "
        f"{lifecycle.get('duplicate_guard_would_block_any_known_intention')}",
        "Stale or already-sent warning: "
        f"{lifecycle.get('stale_or_already_sent_warning')}",
        f"Recommended next action: {report.get('recommended_next_action')}",
        "",
        "Next steps:",
        f"Check manual pilot status: {next_steps.get('check_manual_pilot_status')}",
        f"Seed and prepare fresh draft: {next_steps.get('seed_and_prepare_fresh_draft')}",
        f"Prepare draft: {next_steps.get('prepare_manual_pilot_delivery_draft')}",
        f"Approve draft: {next_steps.get('approve_draft')}",
        f"Continue approved draft handoff: {next_steps.get('continue_approved_draft_handoff')}",
        f"Review delivery intention: {next_steps.get('review_delivery_intention')}",
        f"Check send status: {next_steps.get('check_send_status')}",
        f"Check execution gate: {next_steps.get('check_execution_gate')}",
        "Bounded test send, DO NOT RUN UNTIL CHECKS PASS: "
        f"{next_steps.get('bounded_test_send_do_not_run_until_checks_pass')}",
        "",
        f"Read-only: {safety.get('read_only')}",
        f"DB write scope: {safety.get('db_write_scope')}",
        f"Delivery invoked: {safety.get('delivery_invoked')}",
        f"Telegram invoked: {safety.get('telegram_invoked')}",
        f"Scheduler invoked: {safety.get('scheduler_invoked')}",
        f"Delivery result created: {safety.get('delivery_result_created')}",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parse_args(argv)
        query = _query_from_args(args)
        report = asyncio.run(build_manual_pilot_status_report(query))
    except ManualPilotStatusInputError as exc:
        output_format = getattr(locals().get("args", None), "format", "json")
        if output_format == "json":
            _print_json(_blocked_result(error_code="input_error", message=str(exc)))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 2
    except ManualPilotStatusBlockedError as exc:
        output_format = getattr(locals().get("args", None), "format", "json")
        if output_format == "json":
            _print_json(_blocked_result(error_code="blocked", message=str(exc)))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 1
    except ManualPilotStatusRuntimeError as exc:
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
