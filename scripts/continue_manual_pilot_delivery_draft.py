#!/usr/bin/env python
"""Continue an approved manual pilot delivery draft to intention handoff."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import prepare_manual_pilot_delivery_draft as prepare_script  # noqa: E402
from scripts import report_digest_delivery_intention_send_status as status_script  # noqa: E402
from scripts import send_test_telegram_delivery_intention as send_script  # noqa: E402

CONFIRM_CREATE_INTENTION_PHRASE = "CREATE MANUAL PILOT DELIVERY INTENTION"


class ContinueInputError(ValueError):
    pass


class ContinueNotFoundError(RuntimeError):
    pass


class ContinueBlockedError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        blocker: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.blocker = blocker
        self.metadata = dict(metadata or {})


class ContinueRuntimeError(RuntimeError):
    pass


@dataclass(frozen=True)
class ContinueQuery:
    delivery_draft_id: str
    confirm_create_intention: str
    output_format: str = "json"


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--delivery-draft-id",
        required=True,
        help="Stored delivery draft id that has already been approved by a human.",
    )
    parser.add_argument(
        "--confirm-create-intention",
        required=True,
        help=f'Must be exactly "{CONFIRM_CREATE_INTENTION_PHRASE}".',
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="json",
        help="Output format.",
    )
    return parser.parse_args(argv)


def _clean_required_text(
    value: str,
    *,
    field_name: str,
    max_length: int = 160,
) -> str:
    if not isinstance(value, str):
        raise ContinueInputError(f"{field_name} must be a non-empty string")

    cleaned = value.strip()
    if not cleaned:
        raise ContinueInputError(f"{field_name} must not be empty")
    if len(cleaned) > max_length:
        raise ContinueInputError(f"{field_name} must be at most {max_length} characters")
    return cleaned


def _clean_confirm_create_intention(value: str) -> str:
    cleaned = _clean_required_text(
        value,
        field_name="confirm_create_intention",
        max_length=160,
    )
    if cleaned != CONFIRM_CREATE_INTENTION_PHRASE:
        raise ContinueInputError("confirm_create_intention phrase did not match")
    return cleaned


def _query_from_args(args: argparse.Namespace) -> ContinueQuery:
    return ContinueQuery(
        delivery_draft_id=_clean_required_text(
            args.delivery_draft_id,
            field_name="delivery_draft_id",
        ),
        confirm_create_intention=_clean_confirm_create_intention(
            args.confirm_create_intention
        ),
        output_format=args.format,
    )


def _safe_delivery_intention(value: Mapping[str, Any]) -> dict[str, Any]:
    return status_script._safe_keys(
        value,
        (
            "status",
            "delivery_intention_id",
            "delivery_draft_id",
            "digest_type",
            "channel",
            "current_decision",
            "eligible_for_delivery",
            "delivery_execution_enabled",
            "delivery_enabled",
            "delivery_invoked",
            "delivery_adapter_invoked",
            "approval_execution_invoked",
            "scheduler_invoked",
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


def _next_step_commands(delivery_intention_id: str) -> dict[str, str]:
    return {
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
            "python scripts/send_test_telegram_delivery_intention.py "
            f"--delivery-intention-id {delivery_intention_id} "
            "--execution-attempt-id <EXECUTION_ATTEMPT_ID> "
            "--max-chunks 1 --test-mode true "
            f"--confirm-send \"{send_script.CONFIRM_SEND_PHRASE}\" --format json"
        ),
    }


def _handoff_safety_metadata(*, delivery_intention_created: bool) -> dict[str, Any]:
    return {
        "provider_free": True,
        "local_operator_command": True,
        "db_write_scope": (
            "audit_logs_delivery_intention_only"
            if delivery_intention_created
            else "none"
        ),
        "approval_created": False,
        "rejection_created": False,
        "delivery_intention_created": delivery_intention_created,
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
        "draft_is_source_of_truth": False,
        "intention_is_source_of_truth": False,
        "telegram_is_source_of_truth": False,
    }


def _blocked_result(
    *,
    error_code: str,
    message: str,
    blocker: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    safe_metadata = dict(metadata or {})
    result = {
        "status": "blocked",
        "continued": False,
        "error_code": error_code,
        "message": message,
        "blocker": blocker,
        "safety": _handoff_safety_metadata(delivery_intention_created=False),
    }
    result.update(
        {
            key: safe_metadata[key]
            for key in (
                "delivery_draft_id",
                "delivery_intention_id",
                "delivery_result_id",
                "execution_attempt_id",
                "delivered_chunk_count",
                "recommended_next_action",
            )
            if safe_metadata.get(key) is not None
        }
    )
    return result


async def continue_manual_pilot_delivery_draft(
    query: ContinueQuery,
    *,
    session_factory: Callable[[], Any] | None = None,
    settings_override: Any | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    from app.core.config import settings
    from app.db.base import AsyncSessionLocal
    from app.services.digest_delivery_drafts import (
        DeliveryIntentionConflictError,
        DeliveryIntentionNotReadyError,
        DeliveryTelegramExecutionGateConflictError,
        DeliveryTelegramPlanConflictError,
        create_digest_delivery_intention,
        get_delivery_draft_send_status,
        get_digest_delivery_draft_approval_status,
        get_digest_delivery_draft_delivery_readiness,
        get_digest_delivery_intention_telegram_execution_gate,
        get_digest_delivery_intention_telegram_plan,
        get_persisted_digest_delivery_draft,
        get_successful_delivery_result_for_delivery_intention,
        list_delivery_intentions_for_delivery_draft,
        list_delivery_results_for_delivery_intention,
    )

    try:
        prepare_script._assert_local_environment(
            settings=settings_override or settings,
            environ=environ if environ is not None else os.environ,
        )
    except prepare_script.PrepareBlockedError as exc:
        raise ContinueBlockedError(
            str(exc),
            blocker="production_like_environment",
        ) from exc
    if query.confirm_create_intention != CONFIRM_CREATE_INTENTION_PHRASE:
        raise ContinueInputError("confirm_create_intention phrase did not match")

    delivery_draft_id = _clean_required_text(
        query.delivery_draft_id,
        field_name="delivery_draft_id",
    )
    session_factory = session_factory or AsyncSessionLocal

    try:
        async with session_factory() as session:
            draft = await get_persisted_digest_delivery_draft(
                session,
                delivery_draft_id=delivery_draft_id,
            )
            if draft is None:
                raise ContinueNotFoundError("delivery draft was not found")

            draft_send_status = await get_delivery_draft_send_status(
                session,
                delivery_draft_id=delivery_draft_id,
            )
            if draft_send_status is None:
                raise ContinueRuntimeError("delivery draft send status was not found")
            if draft_send_status.get("stale_or_already_sent_warning") is True:
                raise ContinueBlockedError(
                    "delivery draft already has a successful sent result",
                    blocker="delivery_draft_already_successfully_sent",
                    metadata={
                        "delivery_draft_id": delivery_draft_id,
                        "delivery_intention_id": draft_send_status.get(
                            "prior_successful_delivery_intention_id"
                        ),
                        "delivery_result_id": draft_send_status.get(
                            "prior_successful_delivery_result_id"
                        ),
                        "execution_attempt_id": draft_send_status.get(
                            "prior_successful_execution_attempt_id"
                        ),
                        "delivered_chunk_count": draft_send_status.get(
                            "prior_successful_delivered_chunk_count"
                        ),
                        "recommended_next_action": draft_send_status.get(
                            "recommended_next_action"
                        ),
                    },
                )

            approval_status = await get_digest_delivery_draft_approval_status(
                session,
                delivery_draft_id=delivery_draft_id,
            )
            if approval_status is None:
                raise ContinueRuntimeError("approval status was not found")
            if approval_status.get("rejected") is True:
                raise ContinueBlockedError(
                    "delivery draft is rejected",
                    blocker="rejected",
                    metadata={"delivery_draft_id": delivery_draft_id},
                )
            if approval_status.get("approved") is not True:
                raise ContinueBlockedError(
                    "delivery draft is not approved",
                    blocker="not_approved",
                    metadata={"delivery_draft_id": delivery_draft_id},
                )

            readiness = await get_digest_delivery_draft_delivery_readiness(
                session,
                delivery_draft_id=delivery_draft_id,
            )
            if readiness is None:
                raise ContinueRuntimeError("delivery readiness was not found")
            if readiness.get("eligible_for_delivery") is not True:
                reasons = readiness.get("ineligible_reasons")
                blocker = (
                    str(reasons[0])
                    if isinstance(reasons, list) and reasons
                    else "not_ready"
                )
                raise ContinueBlockedError(
                    "delivery draft is not eligible for delivery",
                    blocker=blocker,
                    metadata={"delivery_draft_id": delivery_draft_id},
                )

            existing_intentions = await list_delivery_intentions_for_delivery_draft(
                session,
                delivery_draft_id=delivery_draft_id,
            )
            intention = await create_digest_delivery_intention(
                session,
                delivery_draft_id=delivery_draft_id,
                actor="operator_manual_pilot_handoff",
            )
            delivery_intention_id = str(intention.get("delivery_intention_id", ""))
            delivery_intention_created = not any(
                item.get("delivery_intention_id") == delivery_intention_id
                for item in existing_intentions
            )
            if delivery_intention_created:
                await session.commit()

            telegram_plan = await get_digest_delivery_intention_telegram_plan(
                session,
                delivery_intention_id=delivery_intention_id,
            )
            if telegram_plan is None:
                raise ContinueNotFoundError("delivery intention was not found")

            execution_gate = await get_digest_delivery_intention_telegram_execution_gate(
                session,
                delivery_intention_id=delivery_intention_id,
                telegram_bot_token=None,
                telegram_chat_id=None,
                max_chunks_allowed=1,
            )
            if execution_gate is None:
                raise ContinueNotFoundError("delivery intention was not found")

            delivery_results = await list_delivery_results_for_delivery_intention(
                session,
                delivery_intention_id=delivery_intention_id,
            )
            prior_success = await get_successful_delivery_result_for_delivery_intention(
                session,
                delivery_intention_id=delivery_intention_id,
            )
    except (
        ContinueInputError,
        ContinueNotFoundError,
        ContinueBlockedError,
        ContinueRuntimeError,
    ):
        raise
    except (
        DeliveryIntentionConflictError,
        DeliveryIntentionNotReadyError,
        DeliveryTelegramExecutionGateConflictError,
        DeliveryTelegramPlanConflictError,
        ValueError,
    ) as exc:
        raise ContinueBlockedError(str(exc), blocker="delivery_intention_not_ready") from exc
    except Exception as exc:
        raise ContinueRuntimeError(
            "manual pilot delivery draft handoff blocked; database, schema, or configuration is unavailable"
        ) from exc

    delivery_results_summary = status_script._delivery_result_summary(delivery_results)
    duplicate_guard = status_script._duplicate_guard_summary(prior_success)
    safe_execution_gate = status_script._safe_execution_gate(execution_gate)
    return {
        "status": "manual_pilot_delivery_intention_ready",
        "continued": True,
        "delivery_draft_id": delivery_draft_id,
        "delivery_intention_id": delivery_intention_id,
        "delivery_intention_record_created": delivery_intention_created,
        "existing": not delivery_intention_created,
        "idempotent": not delivery_intention_created,
        "digest_type": intention.get("digest_type"),
        "channel": intention.get("channel"),
        "text_sha256": intention.get("text_sha256"),
        "char_count": intention.get("char_count"),
        "chunk_count": intention.get("chunk_count"),
        "approval_status": status_script._safe_approval_status(approval_status),
        "readiness": status_script._safe_readiness(readiness),
        "delivery_intention": _safe_delivery_intention(intention),
        "send_status": {
            "status": "delivery_intention_send_status",
            "delivery_results": delivery_results_summary,
            "duplicate_guard": duplicate_guard,
            "recommended_next_action": (
                "do_not_resend_same_intention"
                if duplicate_guard["would_block_new_execution_attempt"]
                else "safe_to_consider_new_bounded_attempt"
            ),
        },
        "duplicate_guard": duplicate_guard,
        "telegram_plan": status_script._safe_telegram_plan(telegram_plan),
        "execution_gate": safe_execution_gate,
        "blockers": list(safe_execution_gate.get("blockers", [])),
        "warnings": list(safe_execution_gate.get("warnings", [])),
        "recommended_next_action": (
            "do_not_resend_same_intention"
            if duplicate_guard["would_block_new_execution_attempt"]
            else "run_bounded_test_send_after_human_checks"
        ),
        "source_of_truth": status_script._safe_source_of_truth(
            intention.get("source_of_truth")
        ),
        "next_steps": _next_step_commands(delivery_intention_id),
        "safety": _handoff_safety_metadata(
            delivery_intention_created=delivery_intention_created,
        ),
    }


def _print_json(value: Mapping[str, Any]) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def format_text_result(result: Mapping[str, Any]) -> str:
    if result.get("status") == "blocked":
        return (
            "Manual pilot delivery draft handoff blocked: "
            f"{result.get('message')}\n"
        )

    approval = (
        result.get("approval_status")
        if isinstance(result.get("approval_status"), Mapping)
        else {}
    )
    readiness = (
        result.get("readiness")
        if isinstance(result.get("readiness"), Mapping)
        else {}
    )
    duplicate_guard = (
        result.get("duplicate_guard")
        if isinstance(result.get("duplicate_guard"), Mapping)
        else {}
    )
    execution_gate = (
        result.get("execution_gate")
        if isinstance(result.get("execution_gate"), Mapping)
        else {}
    )
    next_steps = (
        result.get("next_steps")
        if isinstance(result.get("next_steps"), Mapping)
        else {}
    )
    safety = (
        result.get("safety") if isinstance(result.get("safety"), Mapping) else {}
    )
    lines = [
        "Manual pilot delivery intention ready",
        f"Delivery draft ID: {result.get('delivery_draft_id')}",
        f"Delivery intention ID: {result.get('delivery_intention_id')}",
        "Delivery intention record created: "
        f"{result.get('delivery_intention_record_created')}",
        f"Existing/idempotent: {result.get('idempotent')}",
        f"Digest type: {result.get('digest_type')}",
        f"Channel: {result.get('channel')}",
        f"Text SHA-256: {result.get('text_sha256')}",
        f"Characters: {result.get('char_count')}",
        f"Telegram chunks: {result.get('chunk_count')}",
        f"Current decision: {approval.get('current_decision')}",
        f"Eligible for delivery: {readiness.get('eligible_for_delivery')}",
        f"Ineligible reasons: {readiness.get('ineligible_reasons', [])}",
        "Duplicate guard would block new execution attempt: "
        f"{duplicate_guard.get('would_block_new_execution_attempt')}",
        f"Duplicate guard blocker: {duplicate_guard.get('blocker')}",
        f"Gate blockers: {execution_gate.get('blockers', [])}",
        f"Gate warnings: {execution_gate.get('warnings', [])}",
        f"Recommended next action: {result.get('recommended_next_action')}",
        "",
        "Next steps:",
        f"Review delivery intention: {next_steps.get('review_delivery_intention')}",
        f"Check send status: {next_steps.get('check_send_status')}",
        f"Check execution gate: {next_steps.get('check_execution_gate')}",
        "Bounded test send, DO NOT RUN UNTIL CHECKS PASS: "
        f"{next_steps.get('bounded_test_send_do_not_run_until_checks_pass')}",
        "",
        f"Approval created: {safety.get('approval_created')}",
        f"Delivery result created: {safety.get('delivery_result_created')}",
        f"Delivery invoked: {safety.get('delivery_invoked')}",
        f"Scheduler invoked: {safety.get('scheduler_invoked')}",
        f"Outbox record created: {safety.get('outbox_record_created')}",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    try:
        query = _query_from_args(_parse_args(argv))
        result = asyncio.run(continue_manual_pilot_delivery_draft(query))
    except ContinueInputError as exc:
        result = _blocked_result(error_code="input_error", message=str(exc))
        _print_json(result)
        return 2
    except ContinueNotFoundError as exc:
        result = _blocked_result(error_code="not_found", message=str(exc))
        _print_json(result)
        return 1
    except ContinueBlockedError as exc:
        result = _blocked_result(
            error_code="blocked",
            message=str(exc),
            blocker=exc.blocker,
            metadata=exc.metadata,
        )
        _print_json(result)
        return 1
    except ContinueRuntimeError as exc:
        result = _blocked_result(error_code="runtime_error", message=str(exc))
        _print_json(result)
        return 1

    if query.output_format == "json":
        _print_json(result)
    else:
        print(format_text_result(result), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
