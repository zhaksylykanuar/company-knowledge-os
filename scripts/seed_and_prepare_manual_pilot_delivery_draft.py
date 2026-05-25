#!/usr/bin/env python
"""Seed a fresh synthetic digest item and prepare an inert manual pilot draft."""

from __future__ import annotations

import argparse
import asyncio
import json
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
from scripts import prepare_manual_pilot_delivery_draft as prepare_script  # noqa: E402
from scripts import seed_local_persisted_attention_digest as seed_script  # noqa: E402


class SeedAndPrepareInputError(ValueError):
    pass


class SeedAndPrepareBlockedError(RuntimeError):
    pass


class SeedAndPrepareConflictError(RuntimeError):
    pass


class SeedAndPrepareRuntimeError(RuntimeError):
    pass


@dataclass(frozen=True)
class SeedAndPrepareQuery:
    sample_id: str
    created_at: datetime
    confirm_local_seed: str
    confirm_prepare: str
    limit: int
    debug_evidence: bool
    output_format: str = "json"


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sample-id",
        required=True,
        help="Deterministic local synthetic sample id.",
    )
    parser.add_argument(
        "--created-at",
        required=True,
        help="Timezone-aware ISO datetime for the synthetic attention item.",
    )
    parser.add_argument(
        "--confirm-local-seed",
        required=True,
        help=f'Must be exactly "{seed_script.CONFIRM_LOCAL_SEED_PHRASE}".',
    )
    parser.add_argument(
        "--confirm-prepare",
        required=True,
        help=f'Must be exactly "{prepare_script.CONFIRM_PREPARE_PHRASE}".',
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


def _query_from_args(args: argparse.Namespace) -> SeedAndPrepareQuery:
    try:
        sample_id = seed_script._clean_sample_id(args.sample_id)
        created_at = seed_script._parse_datetime(
            args.created_at,
            field_name="created_at",
        )
        confirm_local_seed = seed_script._clean_confirm(args.confirm_local_seed)
        confirm_prepare = prepare_script._clean_confirm(args.confirm_prepare)
        limit = prepare_script._clean_limit(args.limit)
    except (seed_script.SeedInputError, prepare_script.PrepareInputError) as exc:
        raise SeedAndPrepareInputError(str(exc)) from exc

    return SeedAndPrepareQuery(
        sample_id=sample_id,
        created_at=created_at,
        confirm_local_seed=confirm_local_seed,
        confirm_prepare=confirm_prepare,
        limit=limit,
        debug_evidence=bool(args.debug_evidence),
        output_format=args.format,
    )


def _db_write_scope(*, seed_created: bool, draft_created: bool) -> str:
    if seed_created and draft_created:
        return "local_seed_rows_and_delivery_draft_audit"
    if seed_created:
        return "local_seed_rows_only"
    if draft_created:
        return "audit_logs_delivery_draft_only"
    return "none"


def _combined_safety_metadata(*, seed_created: bool, draft_created: bool) -> dict[str, Any]:
    return {
        "synthetic": True,
        "local_dev_only": True,
        "provider_free": True,
        "local_operator_command": True,
        "db_write_scope": _db_write_scope(
            seed_created=seed_created,
            draft_created=draft_created,
        ),
        "seed_rows_created": seed_created,
        "delivery_draft_created": draft_created,
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
        "synthetic_data_is_company_truth": False,
        "draft_is_source_of_truth": False,
        "telegram_is_source_of_truth": False,
    }


def _safe_seed_summary(seed_result: Mapping[str, Any]) -> dict[str, Any]:
    digest_preview = seed_result.get("digest_preview")
    digest_counts = {}
    if isinstance(digest_preview, Mapping) and isinstance(
        digest_preview.get("counts"),
        Mapping,
    ):
        digest_counts = dict(digest_preview["counts"])
    return {
        "status": seed_result.get("status"),
        "seeded": bool(seed_result.get("seeded")),
        "idempotent": bool(seed_result.get("idempotent")),
        "ids": dict(seed_result.get("ids", {}))
        if isinstance(seed_result.get("ids"), Mapping)
        else {},
        "created": dict(seed_result.get("created", {}))
        if isinstance(seed_result.get("created"), Mapping)
        else {},
        "row_counts": dict(seed_result.get("row_counts", {}))
        if isinstance(seed_result.get("row_counts"), Mapping)
        else {},
        "digest_counts": digest_counts,
    }


async def execute_seed_and_prepare(
    query: SeedAndPrepareQuery,
    *,
    session_factory: Callable[[], Any] | None = None,
    settings_override: Any | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    try:
        seed_result = await seed_script.execute_seed(
            seed_script.SeedQuery(
                sample_id=query.sample_id,
                created_at=query.created_at,
                confirm_local_seed=query.confirm_local_seed,
                output_format="json",
            ),
            session_factory=session_factory,
            settings_override=settings_override,
            environ=environ,
        )

        window = seed_result.get("window")
        if not isinstance(window, Mapping):
            raise SeedAndPrepareRuntimeError("seed result did not include a window")
        start_at = prepare_script._parse_datetime(
            str(window.get("start_at", "")),
            field_name="start_at",
        )
        end_at = prepare_script._parse_datetime(
            str(window.get("end_at", "")),
            field_name="end_at",
        )

        prepare_result = await prepare_script.prepare_manual_pilot_delivery_draft(
            prepare_script.PrepareQuery(
                start_at=start_at,
                end_at=end_at,
                limit=query.limit,
                debug_evidence=query.debug_evidence,
                confirm_prepare=query.confirm_prepare,
                output_format="json",
            ),
            session_factory=session_factory,
            settings_override=settings_override,
            environ=environ,
        )
    except (seed_script.SeedInputError, prepare_script.PrepareInputError) as exc:
        raise SeedAndPrepareInputError(str(exc)) from exc
    except (seed_script.SeedBlockedError, prepare_script.PrepareBlockedError) as exc:
        raise SeedAndPrepareBlockedError(str(exc)) from exc
    except seed_script.SeedConflictError as exc:
        raise SeedAndPrepareConflictError(str(exc)) from exc
    except (seed_script.SeedRuntimeError, prepare_script.PrepareRuntimeError) as exc:
        raise SeedAndPrepareRuntimeError(str(exc)) from exc
    except SeedAndPrepareRuntimeError:
        raise
    except Exception as exc:
        raise SeedAndPrepareRuntimeError(
            "manual pilot seed-and-draft preparation blocked; database, schema, or configuration is unavailable"
        ) from exc

    seed_created = bool(seed_result.get("seeded"))
    draft_created = bool(prepare_result.get("delivery_draft_record_created"))
    return {
        "status": "manual_pilot_seed_and_draft_prepared",
        "seeded": seed_created,
        "seed_idempotent": bool(seed_result.get("idempotent")),
        "sample_id": query.sample_id,
        "created_at": query.created_at.isoformat(),
        "start_at": prepare_result.get("start_at"),
        "end_at": prepare_result.get("end_at"),
        "limit": prepare_result.get("limit"),
        "debug_evidence": bool(prepare_result.get("debug_evidence")),
        "delivery_draft_id": prepare_result.get("delivery_draft_id"),
        "delivery_draft_record_created": draft_created,
        "digest_type": prepare_result.get("digest_type"),
        "channel": prepare_result.get("channel"),
        "text_sha256": prepare_result.get("text_sha256"),
        "char_count": prepare_result.get("char_count"),
        "chunk_count": prepare_result.get("chunk_count"),
        "digest_counts": prepare_result.get("digest_counts", {}),
        "hidden_low_priority_count": prepare_result.get(
            "hidden_low_priority_count",
        ),
        "seed": _safe_seed_summary(seed_result),
        "draft_usage_status": prepare_result.get("draft_usage_status", {}),
        "associated_delivery_intentions": prepare_result.get(
            "associated_delivery_intentions",
            [],
        ),
        "delivery_results_summary": prepare_result.get(
            "delivery_results_summary",
            {},
        ),
        "stale_or_already_sent_warning": bool(
            prepare_result.get("stale_or_already_sent_warning")
        ),
        "recommended_next_action": prepare_result.get("recommended_next_action"),
        "next_steps": prepare_result.get("next_steps", {}),
        "safety": _combined_safety_metadata(
            seed_created=seed_created,
            draft_created=draft_created,
        ),
    }


def _blocked_result(*, error_code: str, message: str) -> dict[str, Any]:
    return {
        "status": "blocked",
        "seeded": False,
        "prepared": False,
        "error_code": error_code,
        "message": message,
        "safety": _combined_safety_metadata(
            seed_created=False,
            draft_created=False,
        ),
    }


def _print_json(value: Mapping[str, Any]) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def format_text_result(result: Mapping[str, Any]) -> str:
    if result.get("status") == "blocked":
        return f"Manual pilot seed-and-draft preparation blocked: {result.get('message')}\n"

    counts = (
        result.get("digest_counts")
        if isinstance(result.get("digest_counts"), Mapping)
        else {}
    )
    usage = (
        result.get("draft_usage_status")
        if isinstance(result.get("draft_usage_status"), Mapping)
        else {}
    )
    results = (
        result.get("delivery_results_summary")
        if isinstance(result.get("delivery_results_summary"), Mapping)
        else {}
    )
    next_steps = (
        result.get("next_steps")
        if isinstance(result.get("next_steps"), Mapping)
        else {}
    )
    lines = [
        "Manual pilot seed-and-draft prepared",
        f"Sample ID: {result.get('sample_id')}",
        f"Created at: {result.get('created_at')}",
        f"Seeded new rows: {result.get('seeded')}",
        f"Seed idempotent: {result.get('seed_idempotent')}",
        f"Window start: {result.get('start_at')}",
        f"Window end: {result.get('end_at')}",
        f"Limit: {result.get('limit')}",
        f"Debug evidence: {result.get('debug_evidence')}",
        f"Delivery draft ID: {result.get('delivery_draft_id')}",
        f"Delivery draft record created: {result.get('delivery_draft_record_created')}",
        f"Digest type: {result.get('digest_type')}",
        f"Channel: {result.get('channel')}",
        f"Text SHA-256: {result.get('text_sha256')}",
        f"Characters: {result.get('char_count')}",
        f"Telegram chunks: {result.get('chunk_count')}",
        f"Digest total: {counts.get('total')}",
        f"Digest visible: {counts.get('visible')}",
        f"Digest hidden: {counts.get('hidden')}",
        f"Hidden low-priority count: {result.get('hidden_low_priority_count')}",
        f"Associated delivery intentions: {usage.get('associated_delivery_intention_count', 0)}",
        f"Delivery result count: {results.get('count', 0)}",
        f"Successful delivery result count: {results.get('successful_count', 0)}",
        f"Already-sent warning: {result.get('stale_or_already_sent_warning')}",
        f"Already-sent blocker: {usage.get('blocker')}",
        "Prior successful delivery intention ID: "
        f"{usage.get('prior_successful_delivery_intention_id')}",
        "Prior successful delivery result ID: "
        f"{usage.get('prior_successful_delivery_result_id')}",
        "Prior successful execution attempt ID: "
        f"{usage.get('prior_successful_execution_attempt_id')}",
        f"Recommended next action: {result.get('recommended_next_action')}",
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
        result = asyncio.run(execute_seed_and_prepare(query))
    except SeedAndPrepareInputError as exc:
        output_format = getattr(locals().get("args", None), "format", "json")
        if output_format == "json":
            _print_json(_blocked_result(error_code="input_error", message=str(exc)))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 2
    except SeedAndPrepareBlockedError as exc:
        output_format = getattr(locals().get("args", None), "format", "json")
        if output_format == "json":
            _print_json(_blocked_result(error_code="prepare_blocked", message=str(exc)))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 1
    except SeedAndPrepareConflictError as exc:
        output_format = getattr(locals().get("args", None), "format", "json")
        if output_format == "json":
            _print_json(_blocked_result(error_code="seed_conflict", message=str(exc)))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 1
    except SeedAndPrepareRuntimeError as exc:
        output_format = getattr(locals().get("args", None), "format", "json")
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
