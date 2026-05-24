#!/usr/bin/env python
"""Send a stored digest delivery intention to Telegram in test mode only."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from sqlalchemy import select

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

CONFIRM_SEND_PHRASE = "SEND TEST TELEGRAM DIGEST"
MAX_TEST_SEND_CHUNKS = 3
_SETTING_UNSET = object()
_ALLOWED_OPERATOR_GATE_BLOCKERS = {
    "delivery_execution_not_implemented",
    "bounded_operator_request_required",
}

TelegramSendMessageTransport = Callable[
    [str, Mapping[str, str]],
    Awaitable[Mapping[str, Any]],
]


class SendInputError(ValueError):
    pass


class SendNotFoundError(RuntimeError):
    pass


class SendBlockedError(RuntimeError):
    pass


class SendRuntimeError(RuntimeError):
    pass


@dataclass(frozen=True)
class SendQuery:
    delivery_intention_id: str
    execution_attempt_id: str
    max_chunks: int
    test_mode: bool
    confirm_send: str
    output_format: str = "text"


@dataclass(frozen=True)
class _BoundedTelegramSendResult:
    attempted_chunk_count: int
    delivered_chunk_count: int
    failed_chunk_count: int
    safe_message_refs: tuple[dict[str, Any], ...]
    safe_error_code: str | None = None
    safe_error_summary: str | None = None


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--delivery-intention-id",
        required=True,
        help="Stored delivery intention id to send.",
    )
    parser.add_argument(
        "--execution-attempt-id",
        required=True,
        help="Operator-provided idempotency key for this bounded test attempt.",
    )
    parser.add_argument(
        "--max-chunks",
        required=True,
        type=int,
        help=f"Maximum chunks to send, capped at {MAX_TEST_SEND_CHUNKS}.",
    )
    parser.add_argument(
        "--test-mode",
        required=True,
        help="Must be exactly true.",
    )
    parser.add_argument(
        "--confirm-send",
        required=True,
        help=f'Must be exactly "{CONFIRM_SEND_PHRASE}".',
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format.",
    )
    return parser.parse_args(argv)


def _clean_required_text(value: str, *, field_name: str, max_length: int = 120) -> str:
    if not isinstance(value, str):
        raise SendInputError(f"{field_name} must be a non-empty string")

    cleaned = value.strip()
    if not cleaned:
        raise SendInputError(f"{field_name} must not be empty")
    if len(cleaned) > max_length:
        raise SendInputError(f"{field_name} must be at most {max_length} characters")
    return cleaned


def _clean_max_chunks(value: int) -> int:
    if not isinstance(value, int):
        raise SendInputError("max_chunks must be an integer")
    if value < 1:
        raise SendInputError("max_chunks must be at least 1")
    if value > MAX_TEST_SEND_CHUNKS:
        raise SendInputError(
            f"max_chunks must be at most {MAX_TEST_SEND_CHUNKS} for test sends"
        )
    return value


def _clean_test_mode(value: str) -> bool:
    cleaned = _clean_required_text(value, field_name="test_mode", max_length=20)
    if cleaned != "true":
        raise SendInputError("test_mode must be exactly true")
    return True


def _clean_confirm_send(value: str) -> str:
    cleaned = _clean_required_text(value, field_name="confirm_send", max_length=120)
    if cleaned != CONFIRM_SEND_PHRASE:
        raise SendInputError("confirm_send phrase did not match")
    return cleaned


def _query_from_args(args: argparse.Namespace) -> SendQuery:
    return SendQuery(
        delivery_intention_id=_clean_required_text(
            args.delivery_intention_id,
            field_name="delivery_intention_id",
        ),
        execution_attempt_id=_clean_required_text(
            args.execution_attempt_id,
            field_name="execution_attempt_id",
        ),
        max_chunks=_clean_max_chunks(args.max_chunks),
        test_mode=_clean_test_mode(args.test_mode),
        confirm_send=_clean_confirm_send(args.confirm_send),
        output_format=args.format,
    )


def _setting_value(value: Any) -> str | None:
    if value is None:
        return None

    get_secret_value = getattr(value, "get_secret_value", None)
    if callable(get_secret_value):
        value = get_secret_value()

    if not isinstance(value, str):
        return None

    cleaned = value.strip()
    return cleaned or None


def _blocked_safety_metadata() -> dict[str, Any]:
    return {
        "provider_free": True,
        "test_mode_required": True,
        "credential_values_exposed": False,
        "telegram_raw_api_response_stored": False,
        "rendered_text_included": False,
        "chunk_text_included": False,
        "delivery_invoked": False,
        "delivery_adapter_invoked": False,
        "approval_execution_invoked": False,
        "scheduler_invoked": False,
        "outbox_record_created": False,
        "api_clients_invoked": False,
        "delivery_worker_invoked": False,
        "production_mode": False,
    }


def _result_output(
    result: Mapping[str, Any],
    *,
    idempotent_replay: bool,
    delivery_result_record_created: bool,
) -> dict[str, Any]:
    safe = {
        "status": "telegram_test_send_result",
        "delivery_intention_id": result.get("delivery_intention_id"),
        "delivery_result_id": result.get("delivery_result_id"),
        "execution_attempt_id": result.get("execution_attempt_id"),
        "result_status": result.get("result_status"),
        "text_sha256": result.get("text_sha256"),
        "planned_chunk_count": result.get("planned_chunk_count"),
        "attempted_chunk_count": result.get("attempted_chunk_count"),
        "delivered_chunk_count": result.get("delivered_chunk_count"),
        "failed_chunk_count": result.get("failed_chunk_count"),
        "delivery_invoked": bool(result.get("delivery_invoked")),
        "delivery_adapter_invoked": bool(result.get("delivery_adapter_invoked")),
        "scheduler_invoked": bool(result.get("scheduler_invoked")),
        "approval_execution_invoked": bool(result.get("approval_execution_invoked")),
        "sent": bool(result.get("sent")),
        "idempotent_replay": idempotent_replay,
        "delivery_result_record_created": delivery_result_record_created,
        "test_mode": True,
    }
    if result.get("safe_error_code") is not None:
        safe["safe_error_code"] = result.get("safe_error_code")
    if result.get("safe_error_summary") is not None:
        safe["safe_error_summary"] = result.get("safe_error_summary")

    safety = result.get("safety")
    if isinstance(safety, Mapping):
        safe["safety"] = {
            "provider_free": bool(safety.get("provider_free")),
            "test_mode": True,
            "credential_values_exposed": bool(
                safety.get("credential_values_exposed")
            ),
            "credential_validation_invoked": bool(
                safety.get("credential_validation_invoked")
            ),
            "telegram_raw_api_response_stored": bool(
                safety.get("telegram_raw_api_response_stored")
            ),
            "rendered_text_included": bool(safety.get("rendered_text_included")),
            "chunk_text_included": bool(safety.get("chunk_text_included")),
            "delivery_invoked": bool(safety.get("delivery_invoked")),
            "delivery_adapter_invoked": bool(
                safety.get("delivery_adapter_invoked")
            ),
            "approval_execution_invoked": bool(
                safety.get("approval_execution_invoked")
            ),
            "scheduler_invoked": bool(safety.get("scheduler_invoked")),
            "outbox_record_created": bool(safety.get("outbox_record_created")),
            "production_mode": False,
            "automatic_retry": False,
        }

    audit_log = result.get("audit_log")
    if isinstance(audit_log, Mapping):
        safe["audit_log"] = {
            "event_type": audit_log.get("event_type"),
            "after_ref": audit_log.get("after_ref"),
            "created_at": audit_log.get("created_at"),
        }
    return safe


def _blocked_result(*, error_code: str, message: str) -> dict[str, Any]:
    return {
        "status": "blocked",
        "error_code": error_code,
        "message": message,
        "safety": _blocked_safety_metadata(),
    }


def _validate_gate_for_send(gate: Mapping[str, Any]) -> None:
    if gate.get("status") != "telegram_execution_gate":
        raise SendBlockedError("execution gate status is not safe")

    required_ready_flags = (
        "approval_ready",
        "readiness_ready",
        "telegram_plan_ready",
        "credential_presence_ready",
        "result_audit_contract_ready",
        "within_chunk_bounds",
    )
    missing_ready = [flag for flag in required_ready_flags if gate.get(flag) is not True]
    if missing_ready:
        raise SendBlockedError("execution gate has unmet readiness checks")

    blockers = gate.get("blockers")
    if not isinstance(blockers, list):
        raise SendBlockedError("execution gate blockers are unavailable")

    unsafe_blockers = [
        blocker
        for blocker in blockers
        if not isinstance(blocker, str)
        or blocker not in _ALLOWED_OPERATOR_GATE_BLOCKERS
    ]
    if unsafe_blockers:
        raise SendBlockedError("execution gate has unresolved blockers")


async def _get_existing_result_for_attempt(
    session: Any,
    *,
    delivery_intention_id: str,
    execution_attempt_id: str,
) -> dict[str, Any] | None:
    from app.db.models import AuditLog
    from app.services.digest_delivery_drafts import (
        DIGEST_DELIVERY_RESULT_RECORDED_EVENT_TYPE,
        get_digest_delivery_result,
    )

    records = await session.scalars(
        select(AuditLog)
        .where(AuditLog.event_type == DIGEST_DELIVERY_RESULT_RECORDED_EVENT_TYPE)
        .where(AuditLog.before_ref == delivery_intention_id)
        .order_by(AuditLog.id)
    )
    for record in records:
        payload = record.payload
        if not isinstance(payload, Mapping):
            continue
        if payload.get("execution_attempt_id") != execution_attempt_id:
            continue
        return await get_digest_delivery_result(
            session,
            delivery_result_id=str(record.after_ref),
        )
    return None


async def _send_bounded_chunks(
    *,
    bot_token: str,
    chat_id: str,
    chunks: list[str],
    transport: TelegramSendMessageTransport | None,
) -> _BoundedTelegramSendResult:
    from app.services.telegram_delivery import (
        DEFAULT_TELEGRAM_CHUNK_SIZE,
        send_telegram_plain_text,
    )

    attempted_chunk_count = 0
    delivered_chunk_count = 0
    safe_message_refs: list[dict[str, Any]] = []
    safe_error_code: str | None = None
    safe_error_summary: str | None = None

    for index, chunk in enumerate(chunks, start=1):
        result = await send_telegram_plain_text(
            bot_token=bot_token,
            chat_id=chat_id,
            text=chunk,
            transport=transport,
            chunk_size=DEFAULT_TELEGRAM_CHUNK_SIZE,
        )
        attempted_chunk_count += result.attempted_chunks
        delivered_chunk_count += result.sent_chunks

        for message_id in result.message_ids:
            safe_message_refs.append(
                {
                    "chunk_index": index,
                    "message_id": str(message_id),
                    "chunk_sha256": sha256(chunk.encode("utf-8")).hexdigest(),
                    "status": "sent",
                }
            )

        if not result.success:
            safe_error_code = "telegram_send_failed"
            safe_error_summary = result.error_summary or "Telegram send failed"
            break

    failed_chunk_count = attempted_chunk_count - delivered_chunk_count
    return _BoundedTelegramSendResult(
        attempted_chunk_count=attempted_chunk_count,
        delivered_chunk_count=delivered_chunk_count,
        failed_chunk_count=failed_chunk_count,
        safe_message_refs=tuple(safe_message_refs),
        safe_error_code=safe_error_code,
        safe_error_summary=safe_error_summary,
    )


def _result_status(
    *,
    planned_chunk_count: int,
    delivered_chunk_count: int,
    failed_chunk_count: int,
) -> str:
    if delivered_chunk_count == planned_chunk_count and failed_chunk_count == 0:
        return "succeeded"
    if delivered_chunk_count == 0:
        return "failed"
    return "partial"


async def execute_test_send(
    query: SendQuery,
    *,
    session_factory: Callable[[], Any] | None = None,
    telegram_transport: TelegramSendMessageTransport | None = None,
    telegram_bot_token: Any = _SETTING_UNSET,
    telegram_chat_id: Any = _SETTING_UNSET,
) -> dict[str, Any]:
    from app.core.config import settings
    from app.db.base import AsyncSessionLocal
    from app.services.digest_delivery_drafts import (
        DeliveryResultConflictError,
        DeliveryTelegramExecutionGateConflictError,
        get_digest_delivery_intention,
        get_digest_delivery_intention_telegram_execution_gate,
        get_digest_delivery_intention_telegram_plan,
        get_persisted_digest_delivery_draft,
        record_digest_delivery_result,
    )
    from app.services.telegram_delivery import split_telegram_plain_text

    if query.test_mode is not True:
        raise SendInputError("test_mode must be exactly true")

    delivery_intention_id = _clean_required_text(
        query.delivery_intention_id,
        field_name="delivery_intention_id",
    )
    execution_attempt_id = _clean_required_text(
        query.execution_attempt_id,
        field_name="execution_attempt_id",
    )
    max_chunks = _clean_max_chunks(query.max_chunks)

    bot_token = _setting_value(
        settings.telegram_bot_token
        if telegram_bot_token is _SETTING_UNSET
        else telegram_bot_token
    )
    chat_id = _setting_value(
        settings.telegram_chat_id
        if telegram_chat_id is _SETTING_UNSET
        else telegram_chat_id
    )

    session_factory = session_factory or AsyncSessionLocal
    try:
        async with session_factory() as session:
            existing_result = await _get_existing_result_for_attempt(
                session,
                delivery_intention_id=delivery_intention_id,
                execution_attempt_id=execution_attempt_id,
            )
            if existing_result is not None:
                return _result_output(
                    existing_result,
                    idempotent_replay=True,
                    delivery_result_record_created=False,
                )

            gate = await get_digest_delivery_intention_telegram_execution_gate(
                session,
                delivery_intention_id=delivery_intention_id,
                telegram_bot_token=bot_token,
                telegram_chat_id=chat_id,
                max_chunks_allowed=max_chunks,
            )
            if gate is None:
                raise SendNotFoundError("delivery intention was not found")
            _validate_gate_for_send(gate)

            if bot_token is None or chat_id is None:
                raise SendBlockedError("Telegram credential presence is not ready")

            intention = await get_digest_delivery_intention(
                session,
                delivery_intention_id=delivery_intention_id,
            )
            if intention is None:
                raise SendNotFoundError("delivery intention was not found")

            delivery_draft_id = str(gate.get("delivery_draft_id", "")).strip()
            if not delivery_draft_id:
                raise SendBlockedError("delivery draft reference is unavailable")
            draft = await get_persisted_digest_delivery_draft(
                session,
                delivery_draft_id=delivery_draft_id,
            )
            if draft is None:
                raise SendBlockedError("referenced delivery draft was not found")

            telegram_plan = await get_digest_delivery_intention_telegram_plan(
                session,
                delivery_intention_id=delivery_intention_id,
            )
            if telegram_plan is None:
                raise SendNotFoundError("delivery intention was not found")

            rendered_text = draft.get("rendered_text")
            if not isinstance(rendered_text, str) or not rendered_text.strip():
                raise SendBlockedError("stored rendered draft text is unavailable")
            if sha256(rendered_text.encode("utf-8")).hexdigest() != gate.get(
                "text_sha256"
            ):
                raise SendBlockedError("stored rendered draft text hash is unsafe")

            chunks = split_telegram_plain_text(rendered_text)
            planned_chunk_count = int(telegram_plan.get("chunk_count") or 0)
            if len(chunks) != planned_chunk_count:
                raise SendBlockedError("stored rendered draft chunk count is unsafe")
            if len(chunks) > max_chunks:
                raise SendBlockedError("planned chunks exceed max_chunks")

            bounded_result = await _send_bounded_chunks(
                bot_token=bot_token,
                chat_id=chat_id,
                chunks=chunks,
                transport=telegram_transport,
            )
            result_status = _result_status(
                planned_chunk_count=planned_chunk_count,
                delivered_chunk_count=bounded_result.delivered_chunk_count,
                failed_chunk_count=bounded_result.failed_chunk_count,
            )
            delivery_result = await record_digest_delivery_result(
                session,
                delivery_intention_id=delivery_intention_id,
                execution_attempt_id=execution_attempt_id,
                result_status=result_status,
                attempted_chunk_count=bounded_result.attempted_chunk_count,
                delivered_chunk_count=bounded_result.delivered_chunk_count,
                failed_chunk_count=bounded_result.failed_chunk_count,
                safe_message_refs=list(bounded_result.safe_message_refs),
                safe_error_code=bounded_result.safe_error_code,
                safe_error_summary=bounded_result.safe_error_summary,
                delivery_invoked=True,
                delivery_adapter_invoked=True,
                actor="operator_test_send",
            )
            await session.commit()
    except (SendInputError, SendNotFoundError, SendBlockedError, SendRuntimeError):
        raise
    except (
        DeliveryResultConflictError,
        DeliveryTelegramExecutionGateConflictError,
        ValueError,
    ) as exc:
        raise SendBlockedError(str(exc)) from exc
    except Exception as exc:
        raise SendRuntimeError(
            "bounded test Telegram send blocked; database, schema, or configuration is unavailable"
        ) from exc

    return _result_output(
        delivery_result,
        idempotent_replay=False,
        delivery_result_record_created=True,
    )


def format_text_result(result: Mapping[str, Any]) -> str:
    if result.get("status") == "blocked":
        return f"Bounded test Telegram send blocked: {result.get('message')}\n"

    lines = [
        "Bounded test-mode Telegram delivery attempt",
        f"Delivery intention ID: {result.get('delivery_intention_id')}",
        f"Delivery result ID: {result.get('delivery_result_id')}",
        f"Execution attempt ID: {result.get('execution_attempt_id')}",
        f"Result status: {result.get('result_status')}",
        f"Planned chunks: {result.get('planned_chunk_count')}",
        f"Attempted chunks: {result.get('attempted_chunk_count')}",
        f"Delivered chunks: {result.get('delivered_chunk_count')}",
        f"Failed chunks: {result.get('failed_chunk_count')}",
        f"Idempotent replay: {result.get('idempotent_replay')}",
        f"Delivery result audit recorded: {result.get('delivery_result_record_created')}",
        f"Delivery invoked: {result.get('delivery_invoked')}",
        f"Delivery adapter invoked: {result.get('delivery_adapter_invoked')}",
        f"Scheduler invoked: {result.get('scheduler_invoked')}",
        f"Sent: {result.get('sent')}",
    ]
    if result.get("safe_error_code") is not None:
        lines.append(f"Safe error code: {result.get('safe_error_code')}")
    if result.get("safe_error_summary") is not None:
        lines.append(f"Safe error summary: {result.get('safe_error_summary')}")
    return "\n".join(lines) + "\n"


def _print_json(value: Mapping[str, Any]) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parse_args(argv)
        query = _query_from_args(args)
        result = asyncio.run(execute_test_send(query))
    except SendInputError as exc:
        output_format = getattr(locals().get("args", None), "format", "text")
        if output_format == "json":
            _print_json(_blocked_result(error_code="input_error", message=str(exc)))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 2
    except SendNotFoundError as exc:
        output_format = getattr(locals().get("args", None), "format", "text")
        if output_format == "json":
            _print_json(_blocked_result(error_code="not_found", message=str(exc)))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 1
    except SendBlockedError as exc:
        output_format = getattr(locals().get("args", None), "format", "text")
        if output_format == "json":
            _print_json(_blocked_result(error_code="send_blocked", message=str(exc)))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 1
    except SendRuntimeError as exc:
        output_format = getattr(locals().get("args", None), "format", "text")
        if output_format == "json":
            _print_json(_blocked_result(error_code="runtime_error", message=str(exc)))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 1

    if query.output_format == "json":
        _print_json(result)
    else:
        print(format_text_result(result), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
