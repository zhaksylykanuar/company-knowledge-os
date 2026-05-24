#!/usr/bin/env python
"""Prepare an inert delivery draft for the manual Telegram pilot flow."""

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

from app.services.digest import (  # noqa: E402
    DEFAULT_DIGEST_ENTRY_LIMIT,
    MAX_DIGEST_ENTRY_LIMIT,
)

CONFIRM_PREPARE_PHRASE = "PREPARE MANUAL PILOT DRAFT"
PRODUCTION_ENV_NAMES = (
    "APP_ENV",
    "ENV",
    "ENVIRONMENT",
    "FOUNDEROS_ENV",
    "RAILS_ENV",
    "NODE_ENV",
)
PRODUCTION_ENV_PREFIXES = ("prod", "production", "stag", "staging")


class PrepareInputError(ValueError):
    pass


class PrepareBlockedError(RuntimeError):
    pass


class PrepareRuntimeError(RuntimeError):
    pass


@dataclass(frozen=True)
class PrepareQuery:
    start_at: datetime
    end_at: datetime
    limit: int
    debug_evidence: bool
    confirm_prepare: str
    output_format: str = "json"


def _parse_datetime(value: str, *, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise PrepareInputError(f"{field_name} must be a timezone-aware ISO datetime")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise PrepareInputError(
            f"{field_name} must be a timezone-aware ISO datetime"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PrepareInputError(f"{field_name} must be timezone-aware")
    return parsed


def _clean_limit(value: int) -> int:
    if not isinstance(value, int):
        raise PrepareInputError("limit must be an integer")
    if value < 1 or value > MAX_DIGEST_ENTRY_LIMIT:
        raise PrepareInputError(f"limit must be between 1 and {MAX_DIGEST_ENTRY_LIMIT}")
    return value


def _clean_confirm(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PrepareInputError("confirm_prepare must not be empty")
    cleaned = value.strip()
    if cleaned != CONFIRM_PREPARE_PHRASE:
        raise PrepareInputError("confirm_prepare phrase did not match")
    return cleaned


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
        "--confirm-prepare",
        required=True,
        help=f'Must be exactly "{CONFIRM_PREPARE_PHRASE}".',
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
        help="Include safe debug evidence in the stored draft only.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="json",
        help="Output format.",
    )
    return parser.parse_args(argv)


def _query_from_args(args: argparse.Namespace) -> PrepareQuery:
    start_at = _parse_datetime(args.start_at, field_name="start_at")
    end_at = _parse_datetime(args.end_at, field_name="end_at")
    if end_at <= start_at:
        raise PrepareInputError("end_at must be after start_at")
    return PrepareQuery(
        start_at=start_at,
        end_at=end_at,
        limit=_clean_limit(args.limit),
        debug_evidence=bool(args.debug_evidence),
        confirm_prepare=_clean_confirm(args.confirm_prepare),
        output_format=args.format,
    )


def _env_value_is_production_like(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    normalized = value.strip().casefold()
    if not normalized:
        return False
    return any(
        normalized == prefix or normalized.startswith(f"{prefix}-")
        for prefix in PRODUCTION_ENV_PREFIXES
    )


def _assert_local_environment(*, settings: Any, environ: Mapping[str, str]) -> None:
    if _env_value_is_production_like(getattr(settings, "app_env", None)):
        raise PrepareBlockedError(
            "refusing to prepare draft in production-like environment"
        )
    for name in PRODUCTION_ENV_NAMES:
        if _env_value_is_production_like(environ.get(name)):
            raise PrepareBlockedError(
                "refusing to prepare draft in production-like environment"
            )


def _safe_counts(digest: Mapping[str, Any]) -> dict[str, Any]:
    counts = digest.get("counts")
    if not isinstance(counts, Mapping):
        return {"total": 0, "visible": 0, "hidden": 0, "shown": 0}
    return {
        "total": int(counts.get("total") or 0),
        "visible": int(counts.get("visible") or 0),
        "hidden": int(counts.get("hidden") or 0),
        "shown": int(counts.get("shown") or 0),
    }


def _hidden_low_priority_count(digest: Mapping[str, Any]) -> int:
    hidden = digest.get("hidden_low_priority_summary")
    if not isinstance(hidden, Mapping):
        return 0
    value = hidden.get("total")
    return int(value) if isinstance(value, int) and not isinstance(value, bool) else 0


def _next_step_commands(delivery_draft_id: str) -> dict[str, str]:
    return {
        "approve_draft": (
            "curl -sS -X POST '<API_BASE_URL>/v1/digest/delivery-drafts/"
            f"{delivery_draft_id}/approve' "
            "-H '<AUTH_HEADER>: <AUTH_VALUE>' "
            "-H 'Content-Type: application/json' "
            "-d '{\"reviewer\":\"<REVIEWER>\",\"note\":\"<SAFE_NOTE>\"}'"
        ),
        "check_readiness": (
            "curl -sS '<API_BASE_URL>/v1/digest/delivery-drafts/"
            f"{delivery_draft_id}/delivery-readiness' "
            "-H '<AUTH_HEADER>: <AUTH_VALUE>'"
        ),
        "create_delivery_intention": (
            "curl -sS -X POST '<API_BASE_URL>/v1/digest/delivery-drafts/"
            f"{delivery_draft_id}/delivery-intention' "
            "-H '<AUTH_HEADER>: <AUTH_VALUE>'"
        ),
        "review_delivery_intention": (
            "python scripts/review_digest_delivery_intention.py "
            "--delivery-intention-id <DELIVERY_INTENTION_ID> --format json"
        ),
        "check_send_status": (
            "python scripts/report_digest_delivery_intention_send_status.py "
            "--delivery-intention-id <DELIVERY_INTENTION_ID> --format json"
        ),
        "check_execution_gate": (
            "curl -sS '<API_BASE_URL>/v1/digest/delivery-intentions/"
            "<DELIVERY_INTENTION_ID>/telegram-execution-gate' "
            "-H '<AUTH_HEADER>: <AUTH_VALUE>'"
        ),
        "bounded_test_send_do_not_run_until_checks_pass": (
            "python scripts/send_test_telegram_delivery_intention.py "
            "--delivery-intention-id <DELIVERY_INTENTION_ID> "
            "--execution-attempt-id <EXECUTION_ATTEMPT_ID> "
            "--max-chunks 1 --test-mode true "
            "--confirm-send \"SEND TEST TELEGRAM DIGEST\" --format json"
        ),
    }


def _safety_metadata(*, delivery_draft_record_created: bool) -> dict[str, Any]:
    return {
        "provider_free": True,
        "local_operator_command": True,
        "db_write_scope": (
            "audit_logs_delivery_draft_only"
            if delivery_draft_record_created
            else "none"
        ),
        "delivery_draft_created": delivery_draft_record_created,
        "approval_created": False,
        "rejection_created": False,
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
        "draft_is_source_of_truth": False,
        "telegram_is_source_of_truth": False,
    }


async def prepare_manual_pilot_delivery_draft(
    query: PrepareQuery,
    *,
    session_factory: Callable[[], Any] | None = None,
    settings_override: Any | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    from app.core.config import settings
    from app.db.base import AsyncSessionLocal
    from app.services.digest import build_persisted_attention_digest_read_model
    from app.services.digest_delivery_drafts import (
        build_persisted_attention_digest_delivery_draft,
        get_persisted_digest_delivery_draft,
        persist_digest_delivery_draft,
        sanitize_persisted_attention_digest_for_delivery_draft,
    )
    from app.services.digest_rendering import render_persisted_attention_digest_text

    _assert_local_environment(
        settings=settings_override or settings,
        environ=environ if environ is not None else os.environ,
    )
    if query.confirm_prepare != CONFIRM_PREPARE_PHRASE:
        raise PrepareInputError("confirm_prepare phrase did not match")

    session_factory = session_factory or AsyncSessionLocal
    try:
        async with session_factory() as session:
            digest = await build_persisted_attention_digest_read_model(
                session,
                start_at=query.start_at,
                end_at=query.end_at,
                limit_per_section=query.limit,
            )
            counts = _safe_counts(digest)
            if counts["total"] < 1 or counts["visible"] < 1:
                raise PrepareBlockedError(
                    "persisted attention digest window has no visible items"
                )

            safe_digest = sanitize_persisted_attention_digest_for_delivery_draft(
                digest,
                debug_evidence=query.debug_evidence,
            )
            rendered_text = render_persisted_attention_digest_text(
                safe_digest,
                debug_evidence=query.debug_evidence,
            )
            draft = build_persisted_attention_digest_delivery_draft(
                digest=safe_digest,
                rendered_text=rendered_text,
                start_at=query.start_at,
                end_at=query.end_at,
                limit=query.limit,
                debug_evidence=query.debug_evidence,
            )
            delivery_draft_id = str(draft.get("delivery_draft_id", ""))
            existing = await get_persisted_digest_delivery_draft(
                session,
                delivery_draft_id=delivery_draft_id,
            )
            persisted = await persist_digest_delivery_draft(
                session,
                draft=draft,
                actor="operator_manual_pilot_prepare",
            )
            delivery_draft_record_created = existing is None
            if delivery_draft_record_created:
                await session.commit()
    except (PrepareInputError, PrepareBlockedError, PrepareRuntimeError):
        raise
    except ValueError as exc:
        raise PrepareInputError(str(exc)) from exc
    except Exception as exc:
        raise PrepareRuntimeError(
            "manual pilot delivery draft preparation blocked; database, schema, or configuration is unavailable"
        ) from exc

    return {
        "status": "manual_pilot_delivery_draft_prepared",
        "prepared": True,
        "delivery_draft_id": persisted.get("delivery_draft_id"),
        "digest_type": persisted.get("digest_type"),
        "channel": persisted.get("channel"),
        "start_at": persisted.get("start_at"),
        "end_at": persisted.get("end_at"),
        "limit": persisted.get("limit"),
        "debug_evidence": bool(persisted.get("debug_evidence")),
        "text_sha256": persisted.get("text_sha256"),
        "char_count": persisted.get("char_count"),
        "chunk_count": persisted.get("chunk_count"),
        "persisted": bool(persisted.get("persisted")),
        "existing": not delivery_draft_record_created,
        "idempotent": not delivery_draft_record_created,
        "delivery_draft_record_created": delivery_draft_record_created,
        "digest_counts": counts,
        "hidden_low_priority_count": _hidden_low_priority_count(digest),
        "next_steps": _next_step_commands(str(persisted.get("delivery_draft_id"))),
        "safety": _safety_metadata(
            delivery_draft_record_created=delivery_draft_record_created,
        ),
    }


def _blocked_result(*, error_code: str, message: str) -> dict[str, Any]:
    return {
        "status": "blocked",
        "prepared": False,
        "error_code": error_code,
        "message": message,
        "safety": _safety_metadata(delivery_draft_record_created=False),
    }


def _print_json(value: Mapping[str, Any]) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def format_text_prepare(result: Mapping[str, Any]) -> str:
    if result.get("status") == "blocked":
        return f"Manual pilot delivery draft preparation blocked: {result.get('message')}\n"

    counts = result.get("digest_counts") if isinstance(result.get("digest_counts"), Mapping) else {}
    next_steps = result.get("next_steps") if isinstance(result.get("next_steps"), Mapping) else {}
    lines = [
        "Manual pilot delivery draft prepared",
        f"Delivery draft ID: {result.get('delivery_draft_id')}",
        f"Digest type: {result.get('digest_type')}",
        f"Channel: {result.get('channel')}",
        f"Window start: {result.get('start_at')}",
        f"Window end: {result.get('end_at')}",
        f"Limit: {result.get('limit')}",
        f"Debug evidence: {result.get('debug_evidence')}",
        f"Text SHA-256: {result.get('text_sha256')}",
        f"Characters: {result.get('char_count')}",
        f"Telegram chunks: {result.get('chunk_count')}",
        f"Persisted: {result.get('persisted')}",
        f"Existing/idempotent: {result.get('idempotent')}",
        f"Delivery draft record created: {result.get('delivery_draft_record_created')}",
        f"Digest total: {counts.get('total')}",
        f"Digest visible: {counts.get('visible')}",
        f"Digest hidden: {counts.get('hidden')}",
        f"Hidden low-priority count: {result.get('hidden_low_priority_count')}",
        "",
        "Next steps (human approval remains separate):",
        f"Approve draft: {next_steps.get('approve_draft')}",
        f"Check readiness: {next_steps.get('check_readiness')}",
        f"Create delivery intention: {next_steps.get('create_delivery_intention')}",
        f"Review delivery intention: {next_steps.get('review_delivery_intention')}",
        f"Check send status: {next_steps.get('check_send_status')}",
        f"Check execution gate: {next_steps.get('check_execution_gate')}",
        "Bounded test send, DO NOT RUN UNTIL CHECKS PASS: "
        f"{next_steps.get('bounded_test_send_do_not_run_until_checks_pass')}",
        "",
        "Approval created: False",
        "Delivery intention created: False",
        "Delivery result created: False",
        "Delivery invoked: False",
        "Scheduler invoked: False",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parse_args(argv)
        query = _query_from_args(args)
        result = asyncio.run(prepare_manual_pilot_delivery_draft(query))
    except PrepareInputError as exc:
        output_format = getattr(locals().get("args", None), "format", "json")
        if output_format == "json":
            _print_json(_blocked_result(error_code="input_error", message=str(exc)))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 2
    except PrepareBlockedError as exc:
        output_format = getattr(locals().get("args", None), "format", "json")
        if output_format == "json":
            _print_json(_blocked_result(error_code="prepare_blocked", message=str(exc)))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 1
    except PrepareRuntimeError as exc:
        output_format = getattr(locals().get("args", None), "format", "json")
        if output_format == "json":
            _print_json(_blocked_result(error_code="runtime_error", message=str(exc)))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 1

    if query.output_format == "json":
        _print_json(result)
    else:
        print(format_text_prepare(result), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
