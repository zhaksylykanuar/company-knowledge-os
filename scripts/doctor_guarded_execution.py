#!/usr/bin/env python
"""Read-only guarded-execution doctor for local operator safety gates."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.services.guarded_execution_audit import (  # noqa: E402
    audit_event_from_operator_output_safety,
    audit_event_from_production_diagnostics,
    audit_event_from_provider_diagnostics,
    audit_event_from_scheduler_diagnostics,
    audit_event_summary,
)
from app.services.operator_output_sanitizer import inspect_operator_output  # noqa: E402
from app.services.production_operation_guard import (  # noqa: E402
    PRODUCTION_OPERATION_DEFAULT_DENIED,
    SOURCE_OF_TRUTH_MUTATION,
    ProductionOperationBlockedError,
    require_production_operation_ack,
)
from app.services.provider_execution_guard import (  # noqa: E402
    PROVIDER_EXECUTION_DEFAULT_DENIED,
    ProviderExecutionBlockedError,
    require_live_provider_execution_ack,
)
from app.services.scheduler_execution_guard import (  # noqa: E402
    OUTBOX_DRAIN,
    OUTBOX_DRAIN_DISABLED,
    SchedulerExecutionBlockedError,
    require_no_scheduler_execution,
)

DOCTOR_MODE = "guarded_execution_doctor"
DOCTOR_PASS_EXIT_CODE = 0
DOCTOR_FAIL_EXIT_CODE = 1
CHECK_PASS = "pass"
CHECK_FAIL = "fail"


class DoctorCheckError(RuntimeError):
    def __init__(self, reason_code: str) -> None:
        super().__init__(_safe_reason_code(reason_code))
        self.reason_code = _safe_reason_code(reason_code)


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    run: Callable[[], Mapping[str, Any] | None]


def _safe_reason_code(value: str) -> str:
    cleaned = "".join(
        character if character.isalnum() or character == "_" else "_"
        for character in value.casefold()
    ).strip("_")
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned or "guarded_execution_check_failed"


def _check_result(
    *,
    name: str,
    status: str,
    reason_code: str | None = None,
    diagnostics: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "name": name,
        "status": status,
        "reason_code": _safe_reason_code(reason_code) if reason_code else None,
    }
    if diagnostics:
        result["diagnostics"] = dict(diagnostics)
    return result


def _unsafe_synthetic_values() -> dict[str, str]:
    return {
        "database": "postgres" + "://synthetic.invalid/db",
        "email": "operator" + "@" + "synthetic.invalid",
        "hash": "a" * 64,
        "payload": "provider_payload synthetic body",
        "preview": "grouped_preview_text synthetic body",
        "secret": "bot_token synthetic value",
        "source": "source_object_id synthetic value",
        "text": "rendered_digest_text synthetic body",
        "url": "https" + "://synthetic.invalid/path",
    }


def _guard_safety_diagnostics(payload: Mapping[str, Any]) -> dict[str, Any]:
    safety = inspect_operator_output(payload).as_dict()
    if safety["safe"] is not True:
        raise DoctorCheckError("unsafe_guard_diagnostics")
    return {
        "unsafe_pattern_count": safety["unsafe_pattern_count"],
        "unsafe_pattern_classes": safety["unsafe_pattern_classes"],
    }


def _safe_audit_summary(event: Mapping[str, Any]) -> dict[str, Any]:
    summary = audit_event_summary(event)
    safety = inspect_operator_output(summary).as_dict()
    if safety["safe"] is not True:
        raise DoctorCheckError("unsafe_audit_event_summary")
    return summary


def _check_provider_guard_default_denied() -> Mapping[str, Any]:
    callback_called = False

    def forbidden_callback() -> None:
        nonlocal callback_called
        callback_called = True

    try:
        require_live_provider_execution_ack(
            provider="telegram",
            boundary="telegram_send_message",
        )
        forbidden_callback()
    except ProviderExecutionBlockedError as exc:
        diagnostics = exc.diagnostics.as_dict()
    else:
        raise DoctorCheckError("provider_guard_allowed")

    if callback_called:
        raise DoctorCheckError("provider_callback_called")
    if diagnostics.get("reason_code") != PROVIDER_EXECUTION_DEFAULT_DENIED:
        raise DoctorCheckError("provider_guard_reason_mismatch")
    guard_safety = _guard_safety_diagnostics(diagnostics)
    audit_event = audit_event_from_provider_diagnostics(diagnostics)
    return {
        "guard": "provider_execution_guard",
        "blocked_callback_called": False,
        "reason_code": diagnostics["reason_code"],
        "guard_safety": guard_safety,
        "audit_event": _safe_audit_summary(audit_event),
    }


def _check_production_guard_default_denied() -> Mapping[str, Any]:
    callback_called = False

    def forbidden_callback() -> None:
        nonlocal callback_called
        callback_called = True

    try:
        require_production_operation_ack(
            operation_class=SOURCE_OF_TRUTH_MUTATION,
            boundary="source_of_truth_operation",
        )
        forbidden_callback()
    except ProductionOperationBlockedError as exc:
        diagnostics = exc.diagnostics.as_dict()
    else:
        raise DoctorCheckError("production_guard_allowed")

    if callback_called:
        raise DoctorCheckError("production_callback_called")
    if diagnostics.get("reason_code") != PRODUCTION_OPERATION_DEFAULT_DENIED:
        raise DoctorCheckError("production_guard_reason_mismatch")
    guard_safety = _guard_safety_diagnostics(diagnostics)
    audit_event = audit_event_from_production_diagnostics(diagnostics)
    return {
        "guard": "production_operation_guard",
        "blocked_callback_called": False,
        "reason_code": diagnostics["reason_code"],
        "guard_safety": guard_safety,
        "audit_event": _safe_audit_summary(audit_event),
    }


def _check_scheduler_guard_default_disabled() -> Mapping[str, Any]:
    callback_called = False

    def forbidden_callback() -> None:
        nonlocal callback_called
        callback_called = True

    try:
        require_no_scheduler_execution(
            boundary="test_telegram_delivery_execution",
            execution_source=OUTBOX_DRAIN,
        )
        forbidden_callback()
    except SchedulerExecutionBlockedError as exc:
        diagnostics = exc.diagnostics.as_dict()
    else:
        raise DoctorCheckError("scheduler_guard_allowed")

    if callback_called:
        raise DoctorCheckError("scheduler_callback_called")
    if diagnostics.get("reason_code") != OUTBOX_DRAIN_DISABLED:
        raise DoctorCheckError("scheduler_guard_reason_mismatch")
    guard_safety = _guard_safety_diagnostics(diagnostics)
    audit_event = audit_event_from_scheduler_diagnostics(diagnostics)
    return {
        "guard": "scheduler_execution_guard",
        "blocked_callback_called": False,
        "reason_code": diagnostics["reason_code"],
        "guard_safety": guard_safety,
        "audit_event": _safe_audit_summary(audit_event),
    }


def _check_operator_output_sanitizer() -> Mapping[str, Any]:
    unsafe = _unsafe_synthetic_values()
    diagnostics = inspect_operator_output(
        {
            "contact": unsafe["email"],
            "database": unsafe["database"],
            "preview_text": unsafe["preview"],
            "rendered_text": unsafe["text"],
            "safe_reason_code": "synthetic_check",
            "secret_marker": unsafe["secret"],
            "source_marker": unsafe["source"],
            "payload_marker": unsafe["payload"],
            "url_marker": unsafe["url"],
            "value_hash": unsafe["hash"],
        }
    ).as_dict()
    if diagnostics["safe"] is not False:
        raise DoctorCheckError("sanitizer_did_not_detect_unsafe_synthetic")

    audit_event = audit_event_from_operator_output_safety(diagnostics)
    return {
        "safe": False,
        "unsafe_pattern_count": diagnostics["unsafe_pattern_count"],
        "unsafe_pattern_classes": diagnostics["unsafe_pattern_classes"],
        "raw_hash_shaped_value_count": diagnostics["raw_hash_shaped_value_count"],
        "url_like_value_count": diagnostics["url_like_value_count"],
        "email_like_value_count": diagnostics["email_like_value_count"],
        "secret_like_value_count": diagnostics["secret_like_value_count"],
        "payload_like_value_count": diagnostics["payload_like_value_count"],
        "unsafe_json_flag_count": diagnostics["unsafe_json_flag_count"],
        "audit_event": _safe_audit_summary(audit_event),
    }


async def _bounded_send_outbox_check() -> Mapping[str, Any]:
    from scripts import send_test_telegram_delivery_intention as send_script

    adapter_called = False

    async def forbidden_transport(*args: Any, **kwargs: Any) -> Mapping[str, Any]:
        nonlocal adapter_called
        adapter_called = True
        return {"ok": True}

    try:
        await send_script._send_bounded_chunks(
            bot_token="synthetic_bot",
            chat_id="synthetic_chat",
            chunks=["synthetic digest"],
            transport=forbidden_transport,
            execution_source=OUTBOX_DRAIN,
        )
    except SchedulerExecutionBlockedError as exc:
        diagnostics = exc.diagnostics.as_dict()
    else:
        raise DoctorCheckError("bounded_send_scheduler_source_allowed")

    if adapter_called:
        raise DoctorCheckError("bounded_send_adapter_called")
    if diagnostics.get("reason_code") != OUTBOX_DRAIN_DISABLED:
        raise DoctorCheckError("bounded_send_scheduler_reason_mismatch")
    audit_event = audit_event_from_scheduler_diagnostics(diagnostics)
    return {
        "guard": "scheduler_execution_guard",
        "adapter_called": False,
        "reason_code": diagnostics["reason_code"],
        "guard_safety": _guard_safety_diagnostics(diagnostics),
        "audit_event": _safe_audit_summary(audit_event),
    }


def _check_bounded_send_guarded() -> Mapping[str, Any]:
    return asyncio.run(_bounded_send_outbox_check())


def _check_read_only_paths_no_send() -> Mapping[str, Any]:
    read_only_paths = (
        REPO_ROOT / "scripts" / "review_digest_delivery_intention.py",
        REPO_ROOT / "scripts" / "report_digest_delivery_intention_send_status.py",
    )
    missing_paths = [path.name for path in read_only_paths if not path.exists()]
    if missing_paths:
        raise DoctorCheckError("read_only_script_missing")
    for path in read_only_paths:
        source = path.read_text(encoding="utf-8")
        if "send_" + "telegram_plain_text" in source:
            raise DoctorCheckError("read_only_path_references_sender")
        if "scheduler_invoked" not in source:
            raise DoctorCheckError("read_only_path_missing_scheduler_safety")
    return {
        "read_only_scripts_checked": len(read_only_paths),
        "no_send": True,
        "no_source_of_truth_mutation": True,
        "scheduler_execution": "disabled",
    }


DEFAULT_CHECKS = (
    DoctorCheck("provider_guard_default_denied", _check_provider_guard_default_denied),
    DoctorCheck(
        "production_operation_guard_default_denied",
        _check_production_guard_default_denied,
    ),
    DoctorCheck(
        "scheduler_execution_guard_default_disabled",
        _check_scheduler_guard_default_disabled,
    ),
    DoctorCheck("operator_output_sanitizer", _check_operator_output_sanitizer),
    DoctorCheck("bounded_send_path_guarded", _check_bounded_send_guarded),
    DoctorCheck("read_only_paths_no_send", _check_read_only_paths_no_send),
)


def run_doctor(
    checks: Sequence[DoctorCheck] = DEFAULT_CHECKS,
) -> dict[str, Any]:
    check_results: list[dict[str, Any]] = []
    failed_reason_codes: list[str] = []
    for check in checks:
        try:
            diagnostics = check.run()
        except DoctorCheckError as exc:
            reason_code = exc.reason_code
            failed_reason_codes.append(reason_code)
            check_results.append(
                _check_result(
                    name=check.name,
                    status=CHECK_FAIL,
                    reason_code=reason_code,
                )
            )
        except Exception:
            reason_code = "guarded_execution_check_exception"
            failed_reason_codes.append(reason_code)
            check_results.append(
                _check_result(
                    name=check.name,
                    status=CHECK_FAIL,
                    reason_code=reason_code,
                )
            )
        else:
            check_results.append(
                _check_result(
                    name=check.name,
                    status=CHECK_PASS,
                    diagnostics=diagnostics,
                )
            )

    status = CHECK_PASS if not failed_reason_codes else CHECK_FAIL
    result = {
        "mode": DOCTOR_MODE,
        "status": status,
        "reason_code": None if status == CHECK_PASS else "guarded_execution_doctor_failed",
        "checks": check_results,
        "no_send": True,
        "no_provider_calls": True,
        "no_source_of_truth_mutation": True,
        "scheduler_execution": "disabled",
        "diagnostics": {
            "check_count": len(check_results),
            "failed_check_count": len(failed_reason_codes),
            "reason_codes": sorted(set(failed_reason_codes)),
            "operator_output_safety": inspect_operator_output(check_results).as_dict(),
        },
    }
    if inspect_operator_output(result).safe is not True:
        return {
            "mode": DOCTOR_MODE,
            "status": CHECK_FAIL,
            "reason_code": "guarded_execution_doctor_output_unsafe",
            "checks": [],
            "no_send": True,
            "no_provider_calls": True,
            "no_source_of_truth_mutation": True,
            "scheduler_execution": "disabled",
            "diagnostics": {
                "check_count": 0,
                "failed_check_count": 1,
                "reason_codes": ["guarded_execution_doctor_output_unsafe"],
            },
        }
    return result


def _json_text(value: Mapping[str, Any]) -> str:
    return json.dumps(dict(value), indent=2, sort_keys=True) + "\n"


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--format",
        choices=("json",),
        default="json",
        help="Output format. JSON is the only supported format.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    _parse_args(argv)
    result = run_doctor()
    print(_json_text(result), end="")
    return DOCTOR_PASS_EXIT_CODE if result["status"] == CHECK_PASS else DOCTOR_FAIL_EXIT_CODE


if __name__ == "__main__":
    raise SystemExit(main())
