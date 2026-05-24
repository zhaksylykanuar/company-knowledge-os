#!/usr/bin/env python
"""Report read-only send status for a stored digest delivery intention."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_CREDENTIAL_BLOCKERS = {
    "telegram_bot_token_missing",
    "telegram_chat_id_missing",
}


class SendStatusInputError(ValueError):
    pass


class SendStatusNotFoundError(RuntimeError):
    pass


class SendStatusRuntimeError(RuntimeError):
    pass


@dataclass(frozen=True)
class SendStatusQuery:
    delivery_intention_id: str
    output_format: str = "text"


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--delivery-intention-id",
        required=True,
        help="Stored delivery intention id to report.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format.",
    )
    return parser.parse_args(argv)


def _clean_delivery_intention_id(value: str) -> str:
    if not isinstance(value, str):
        raise SendStatusInputError(
            "delivery_intention_id must be a non-empty string"
        )

    cleaned = value.strip()
    if not cleaned:
        raise SendStatusInputError("delivery_intention_id must not be empty")
    return cleaned


def _query_from_args(args: argparse.Namespace) -> SendStatusQuery:
    return SendStatusQuery(
        delivery_intention_id=_clean_delivery_intention_id(
            args.delivery_intention_id
        ),
        output_format=args.format,
    )


def _safe_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _safe_keys(value: Mapping[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    return {key: value[key] for key in keys if value.get(key) is not None}


def _safe_source_of_truth(value: Any) -> dict[str, Any]:
    source_of_truth = _safe_mapping(value)
    safe = _safe_keys(
        source_of_truth,
        (
            "source",
            "raw_storage_authoritative",
            "postgres_authoritative",
            "draft_is_source_of_truth",
            "intention_is_source_of_truth",
            "telegram_plan_is_source_of_truth",
            "telegram_is_source_of_truth",
            "digest_source_model",
            "digest_enrichment_model",
        ),
    )
    derived_from = source_of_truth.get("derived_from")
    if isinstance(derived_from, list):
        safe["derived_from"] = [str(item) for item in derived_from]
    safe["delivery_results_source"] = "audit_logs"
    safe["delivery_results_are_source_of_truth"] = False
    safe["send_status_report_is_source_of_truth"] = False
    return safe


def _safe_approval_status(value: Mapping[str, Any]) -> dict[str, Any]:
    return _safe_keys(
        value,
        (
            "delivery_draft_id",
            "draft_exists",
            "current_decision",
            "approved",
            "rejected",
            "delivery_enabled",
            "sent",
            "delivery_invoked",
            "approval_execution_invoked",
        ),
    )


def _safe_readiness(value: Mapping[str, Any]) -> dict[str, Any]:
    safe = _safe_keys(
        value,
        (
            "delivery_draft_id",
            "draft_exists",
            "status",
            "digest_type",
            "channel",
            "current_decision",
            "approved",
            "rejected",
            "eligible_for_delivery",
            "delivery_execution_enabled",
            "delivery_enabled",
            "delivery_invoked",
            "approval_execution_invoked",
            "sent",
            "text_sha256",
            "char_count",
            "chunk_count",
            "start_at",
            "end_at",
            "limit",
            "debug_evidence",
        ),
    )
    reasons = value.get("ineligible_reasons")
    safe["ineligible_reasons"] = list(reasons) if isinstance(reasons, list) else []
    return safe


def _safe_telegram_plan(value: Mapping[str, Any]) -> dict[str, Any]:
    return _safe_keys(
        value,
        (
            "status",
            "delivery_intention_id",
            "delivery_draft_id",
            "digest_type",
            "channel",
            "text_sha256",
            "char_count",
            "chunk_count",
            "chunks_text_included",
            "delivery_execution_enabled",
            "delivery_enabled",
            "delivery_invoked",
            "delivery_adapter_invoked",
            "approval_execution_invoked",
            "scheduler_invoked",
            "sent",
            "start_at",
            "end_at",
            "limit",
            "debug_evidence",
        ),
    )


def _safe_execution_gate(value: Mapping[str, Any]) -> dict[str, Any]:
    safe = _safe_keys(
        value,
        (
            "status",
            "delivery_intention_id",
            "delivery_draft_id",
            "digest_type",
            "channel",
            "text_sha256",
            "char_count",
            "chunk_count",
            "approval_ready",
            "readiness_ready",
            "telegram_plan_ready",
            "result_audit_contract_ready",
            "bounded_operator_request_required",
            "max_chunks_allowed",
            "planned_chunk_count",
            "within_chunk_bounds",
            "execution_gate_ready",
            "delivery_execution_enabled",
            "delivery_enabled",
            "delivery_invoked",
            "delivery_adapter_invoked",
            "approval_execution_invoked",
            "scheduler_invoked",
            "sent",
        ),
    )
    blockers = value.get("blockers")
    if isinstance(blockers, list):
        safe["blockers"] = [
            blocker
            for blocker in blockers
            if isinstance(blocker, str) and blocker not in _CREDENTIAL_BLOCKERS
        ]
    else:
        safe["blockers"] = []
    warnings = value.get("warnings")
    safe["warnings"] = [
        warning for warning in warnings if isinstance(warning, str)
    ] if isinstance(warnings, list) else []
    required_fields = value.get("required_operator_fields")
    safe["required_operator_fields"] = [
        field for field in required_fields if isinstance(field, str)
    ] if isinstance(required_fields, list) else []
    safe["credential_presence_evaluated"] = False
    return safe


def _safe_delivery_result(value: Mapping[str, Any]) -> dict[str, Any]:
    return _safe_keys(
        value,
        (
            "delivery_result_id",
            "delivery_intention_id",
            "execution_attempt_id",
            "result_status",
            "sent",
            "attempted_chunk_count",
            "delivered_chunk_count",
            "failed_chunk_count",
            "recorded_at",
        ),
    )


def _delivery_result_is_successful(value: Mapping[str, Any]) -> bool:
    delivered_chunk_count = value.get("delivered_chunk_count")
    return (
        value.get("result_status") == "succeeded"
        and value.get("sent") is True
        and isinstance(delivered_chunk_count, int)
        and not isinstance(delivered_chunk_count, bool)
        and delivered_chunk_count > 0
    )


def _delivery_result_summary(
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    safe_results = [_safe_delivery_result(result) for result in results]
    statuses = [result.get("result_status") for result in safe_results]
    return {
        "count": len(safe_results),
        "successful_count": sum(
            1 for result in safe_results if _delivery_result_is_successful(result)
        ),
        "failed_count": statuses.count("failed"),
        "partial_count": statuses.count("partial"),
        "skipped_count": statuses.count("skipped"),
        "results": safe_results,
    }


def _duplicate_guard_summary(
    prior_success: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if prior_success is None:
        return {
            "would_block_new_execution_attempt": False,
            "blocker": None,
            "prior_successful_delivery_result_id": None,
            "prior_successful_execution_attempt_id": None,
            "prior_successful_result_status": None,
            "prior_successful_delivered_chunk_count": None,
        }

    return {
        "would_block_new_execution_attempt": True,
        "blocker": "delivery_intention_already_successfully_sent",
        "prior_successful_delivery_result_id": prior_success.get(
            "delivery_result_id"
        ),
        "prior_successful_execution_attempt_id": prior_success.get(
            "execution_attempt_id"
        ),
        "prior_successful_result_status": prior_success.get("result_status"),
        "prior_successful_delivered_chunk_count": prior_success.get(
            "delivered_chunk_count"
        ),
    }


def _report_safety_metadata() -> dict[str, Any]:
    return {
        "provider_free": True,
        "read_only": True,
        "db_write_scope": "none",
        "credential_values_exposed": False,
        "telegram_raw_api_response_stored": False,
        "rendered_text_included": False,
        "chunk_text_included": False,
        "raw_payloads_exposed": False,
        "delivery_invoked": False,
        "delivery_adapter_invoked": False,
        "approval_execution_invoked": False,
        "scheduler_invoked": False,
        "outbox_record_created": False,
        "delivery_worker_invoked": False,
        "api_clients_invoked": False,
        "delivery_result_audit_event_created": False,
        "sent": False,
        "production_mode": False,
        "report_is_source_of_truth": False,
    }


async def build_send_status_report(
    query: SendStatusQuery,
    *,
    session_factory: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    from app.db.base import AsyncSessionLocal
    from app.services.digest_delivery_drafts import (
        DeliveryTelegramExecutionGateConflictError,
        DeliveryTelegramPlanConflictError,
        get_digest_delivery_draft_approval_status,
        get_digest_delivery_draft_delivery_readiness,
        get_digest_delivery_intention,
        get_digest_delivery_intention_telegram_execution_gate,
        get_digest_delivery_intention_telegram_plan,
        get_persisted_digest_delivery_draft,
        get_successful_delivery_result_for_delivery_intention,
        list_delivery_results_for_delivery_intention,
    )

    delivery_intention_id = _clean_delivery_intention_id(
        query.delivery_intention_id
    )
    session_factory = session_factory or AsyncSessionLocal

    try:
        async with session_factory() as session:
            intention = await get_digest_delivery_intention(
                session,
                delivery_intention_id=delivery_intention_id,
            )
            if intention is None:
                raise SendStatusNotFoundError("delivery intention was not found")

            delivery_draft_id = str(intention.get("delivery_draft_id", "")).strip()
            if not delivery_draft_id:
                raise SendStatusRuntimeError(
                    "stored delivery intention is missing a delivery_draft_id"
                )

            draft = await get_persisted_digest_delivery_draft(
                session,
                delivery_draft_id=delivery_draft_id,
            )
            if draft is None:
                raise SendStatusRuntimeError(
                    "referenced delivery draft was not found"
                )

            approval_status = await get_digest_delivery_draft_approval_status(
                session,
                delivery_draft_id=delivery_draft_id,
            )
            if approval_status is None:
                raise SendStatusRuntimeError("approval status was not found")

            readiness = await get_digest_delivery_draft_delivery_readiness(
                session,
                delivery_draft_id=delivery_draft_id,
            )
            if readiness is None:
                raise SendStatusRuntimeError("delivery readiness was not found")

            telegram_plan = await get_digest_delivery_intention_telegram_plan(
                session,
                delivery_intention_id=delivery_intention_id,
            )
            if telegram_plan is None:
                raise SendStatusNotFoundError("delivery intention was not found")

            execution_gate = await get_digest_delivery_intention_telegram_execution_gate(
                session,
                delivery_intention_id=delivery_intention_id,
                telegram_bot_token=None,
                telegram_chat_id=None,
            )
            if execution_gate is None:
                raise SendStatusNotFoundError("delivery intention was not found")

            delivery_results = await list_delivery_results_for_delivery_intention(
                session,
                delivery_intention_id=delivery_intention_id,
            )
            prior_success = (
                await get_successful_delivery_result_for_delivery_intention(
                    session,
                    delivery_intention_id=delivery_intention_id,
                )
            )
    except (SendStatusInputError, SendStatusNotFoundError, SendStatusRuntimeError):
        raise
    except (
        DeliveryTelegramExecutionGateConflictError,
        DeliveryTelegramPlanConflictError,
        ValueError,
    ) as exc:
        raise SendStatusRuntimeError(str(exc)) from exc
    except Exception as exc:
        raise SendStatusRuntimeError(
            "delivery intention send status report blocked; database, schema, or configuration is unavailable"
        ) from exc

    duplicate_guard = _duplicate_guard_summary(prior_success)
    return {
        "status": "delivery_intention_send_status",
        "delivery_intention_id": delivery_intention_id,
        "delivery_draft_id": delivery_draft_id,
        "digest_type": intention.get("digest_type"),
        "channel": intention.get("channel"),
        "text_sha256": intention.get("text_sha256"),
        "char_count": intention.get("char_count"),
        "chunk_count": intention.get("chunk_count"),
        "approval_status": _safe_approval_status(approval_status),
        "readiness": _safe_readiness(readiness),
        "telegram_plan": _safe_telegram_plan(telegram_plan),
        "execution_gate": _safe_execution_gate(execution_gate),
        "delivery_results": _delivery_result_summary(delivery_results),
        "duplicate_guard": duplicate_guard,
        "recommended_next_action": (
            "do_not_resend_same_intention"
            if duplicate_guard["would_block_new_execution_attempt"]
            else "safe_to_consider_new_bounded_attempt"
        ),
        "source_of_truth": _safe_source_of_truth(intention.get("source_of_truth")),
        "safety": _report_safety_metadata(),
    }


def format_text_report(report: Mapping[str, Any]) -> str:
    results = _safe_mapping(report.get("delivery_results"))
    duplicate_guard = _safe_mapping(report.get("duplicate_guard"))
    safety = _safe_mapping(report.get("safety"))

    lines = [
        "Delivery intention send status (read-only; no send)",
        f"Delivery intention ID: {report.get('delivery_intention_id')}",
        f"Delivery draft ID: {report.get('delivery_draft_id')}",
        f"Digest type: {report.get('digest_type')}",
        f"Channel: {report.get('channel')}",
        f"Text SHA-256: {report.get('text_sha256')}",
        f"Characters: {report.get('char_count')}",
        f"Telegram chunks: {report.get('chunk_count')}",
        f"Delivery result count: {results.get('count', 0)}",
        f"Successful result count: {results.get('successful_count', 0)}",
        f"Failed result count: {results.get('failed_count', 0)}",
        f"Partial result count: {results.get('partial_count', 0)}",
        f"Skipped result count: {results.get('skipped_count', 0)}",
        "Duplicate guard would block new execution attempt: "
        f"{duplicate_guard.get('would_block_new_execution_attempt')}",
        f"Duplicate guard blocker: {duplicate_guard.get('blocker')}",
        "Prior successful delivery result ID: "
        f"{duplicate_guard.get('prior_successful_delivery_result_id')}",
        "Prior successful execution attempt ID: "
        f"{duplicate_guard.get('prior_successful_execution_attempt_id')}",
        f"Recommended next action: {report.get('recommended_next_action')}",
        f"Delivery invoked by report: {safety.get('delivery_invoked')}",
        f"Delivery adapter invoked by report: {safety.get('delivery_adapter_invoked')}",
        f"Scheduler invoked by report: {safety.get('scheduler_invoked')}",
        f"Sent by report: {safety.get('sent')}",
    ]
    return "\n".join(lines) + "\n"


def _blocked_result(*, error_code: str, message: str) -> dict[str, Any]:
    return {
        "status": "blocked",
        "error_code": error_code,
        "message": message,
        "safety": _report_safety_metadata(),
    }


def _print_json(value: Mapping[str, Any]) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parse_args(argv)
        query = _query_from_args(args)
        report = asyncio.run(build_send_status_report(query))
    except SendStatusInputError as exc:
        output_format = getattr(locals().get("args", None), "format", "text")
        if output_format == "json":
            _print_json(_blocked_result(error_code="input_error", message=str(exc)))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 2
    except SendStatusNotFoundError as exc:
        output_format = getattr(locals().get("args", None), "format", "text")
        if output_format == "json":
            _print_json(_blocked_result(error_code="not_found", message=str(exc)))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 1
    except SendStatusRuntimeError as exc:
        output_format = getattr(locals().get("args", None), "format", "text")
        if output_format == "json":
            _print_json(
                _blocked_result(error_code="status_report_blocked", message=str(exc))
            )
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
