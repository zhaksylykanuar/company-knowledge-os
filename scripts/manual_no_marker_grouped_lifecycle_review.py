#!/usr/bin/env python
"""Gated manual local runner for grouped lifecycle review."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import doctor_no_marker_grouped_lifecycle_review as doctor_script  # noqa: E402
from scripts import (  # noqa: E402
    report_no_marker_persisted_attention_grouped_lifecycle_compatibility as review_script,
)

MANUAL_RUNNER_MODE = "manual_grouped_lifecycle_review"
EXIT_LOCAL_DATA_ACK_REQUIRED = 40
EXIT_DOCTOR_FAILED = 41
EXIT_UNSAFE_OUTPUT_PATH = 42
EXIT_INVALID_USAGE = 2
SAFE_REPORT_EXIT_CODES = frozenset({0, 10, 20, 30})


class ManualReviewRunnerError(RuntimeError):
    def __init__(self, reason_code: str, exit_code: int = EXIT_INVALID_USAGE) -> None:
        super().__init__(reason_code)
        self.reason_code = _safe_reason_code(reason_code)
        self.exit_code = exit_code


@dataclass(frozen=True)
class DelegatedReportResult:
    exit_code: int
    payload: Mapping[str, Any]


def _safe_reason_code(value: str) -> str:
    cleaned = "".join(
        character if character.isalnum() or character == "_" else "_"
        for character in value.casefold()
    ).strip("_")
    return cleaned or "manual_review_runner_error"


def _json_text(value: Mapping[str, Any]) -> str:
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


def _print_json(value: Mapping[str, Any]) -> None:
    print(_json_text(value), end="")


def _safe_blocked_result(
    *,
    reason_code: str,
    local_data_acknowledged: bool,
    executed_report: bool = False,
) -> dict[str, Any]:
    return {
        "mode": MANUAL_RUNNER_MODE,
        "status": "blocked",
        "reason_code": _safe_reason_code(reason_code),
        "read_only": True,
        "provider_free": False,
        "local_synthetic_only": False,
        "uses_real_local_data": False,
        "local_data_acknowledged": local_data_acknowledged,
        "executed_report": executed_report,
        "output_format": "review-json",
        "enforced": False,
        "semantic_duplicate_claimed": False,
    }


def _assert_sanitized(value: Mapping[str, Any]) -> None:
    doctor_script._assert_sanitized(value)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-local-data-readonly",
        action="store_true",
        help=(
            "Explicitly acknowledge a read-only local-data grouped lifecycle "
            "review run. Without this flag, no report execution is attempted."
        ),
    )
    parser.add_argument(
        "--start-at",
        help="Timezone-aware ISO start for the persisted attention window.",
    )
    parser.add_argument(
        "--end-at",
        help="Timezone-aware ISO end for the persisted attention window.",
    )
    parser.add_argument(
        "--activity-start-at",
        help="Optional timezone-aware ISO start for linked source/activity rows.",
    )
    parser.add_argument(
        "--activity-end-at",
        help="Optional timezone-aware ISO end for linked source/activity rows.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Optional maximum visible items per section.",
    )
    parser.add_argument(
        "--debug-evidence",
        action="store_true",
        help="Forward existing debug-evidence hash semantics to the report.",
    )
    parser.add_argument(
        "--cluster-threshold",
        type=int,
        help="Optional duplicate-looking group threshold for the report.",
    )
    parser.add_argument(
        "--group-by",
        help="Optional grouping dimension for the report.",
    )
    parser.add_argument(
        "--format",
        choices=("review-json", "json", "text"),
        default="review-json",
        help=(
            "Manual local runs are gated to review-json. Full JSON and text "
            "output are rejected before report execution."
        ),
    )
    parser.add_argument(
        "--output-path",
        help="Required safe local path for sanitized review-json artifact output.",
    )
    return parser.parse_args(argv)


def _validate_manual_gate(args: argparse.Namespace) -> Path:
    if not args.allow_local_data_readonly:
        raise ManualReviewRunnerError(
            "local_data_ack_required",
            EXIT_LOCAL_DATA_ACK_REQUIRED,
        )
    if args.format != "review-json":
        raise ManualReviewRunnerError("safe_review_json_required", EXIT_INVALID_USAGE)
    if args.output_path is None:
        raise ManualReviewRunnerError("output_path_required", EXIT_UNSAFE_OUTPUT_PATH)
    try:
        artifact_path = review_script._safe_artifact_path(args.output_path)
    except review_script.NoMarkerGroupedLifecycleInputError as exc:
        raise ManualReviewRunnerError(
            "unsafe_output_path",
            EXIT_UNSAFE_OUTPUT_PATH,
        ) from exc
    if artifact_path is None:
        raise ManualReviewRunnerError("output_path_required", EXIT_UNSAFE_OUTPUT_PATH)
    if args.start_at is None or args.end_at is None:
        raise ManualReviewRunnerError("report_window_required", EXIT_INVALID_USAGE)
    return artifact_path


def _run_doctor() -> Mapping[str, Any]:
    try:
        doctor_report = doctor_script.build_doctor_report()
    except Exception as exc:
        raise ManualReviewRunnerError("doctor_failed", EXIT_DOCTOR_FAILED) from exc
    _assert_sanitized(doctor_report)
    if doctor_report.get("status") != "pass":
        raise ManualReviewRunnerError("doctor_failed", EXIT_DOCTOR_FAILED)
    return doctor_report


def _report_args(args: argparse.Namespace) -> list[str]:
    report_args = [
        "--start-at",
        args.start_at,
        "--end-at",
        args.end_at,
        "--format",
        "review-json",
        "--review-exit-code",
    ]
    optional_string_args = (
        ("--activity-start-at", args.activity_start_at),
        ("--activity-end-at", args.activity_end_at),
        ("--group-by", args.group_by),
    )
    for flag, value in optional_string_args:
        if value is not None:
            report_args.extend([flag, value])
    optional_int_args = (
        ("--limit", args.limit),
        ("--cluster-threshold", args.cluster_threshold),
    )
    for flag, value in optional_int_args:
        if value is not None:
            report_args.extend([flag, str(value)])
    if args.debug_evidence:
        report_args.append("--debug-evidence")
    return report_args


def _delegate_report(args: argparse.Namespace) -> DelegatedReportResult:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        exit_code = review_script.main(_report_args(args))
    if stderr.getvalue():
        raise ManualReviewRunnerError("delegated_report_stderr", EXIT_INVALID_USAGE)
    try:
        payload = json.loads(stdout.getvalue())
    except json.JSONDecodeError as exc:
        raise ManualReviewRunnerError(
            "delegated_report_invalid_json",
            EXIT_INVALID_USAGE,
        ) from exc
    if not isinstance(payload, Mapping):
        raise ManualReviewRunnerError(
            "delegated_report_invalid_json",
            EXIT_INVALID_USAGE,
        )
    _assert_sanitized(payload)
    return DelegatedReportResult(exit_code=exit_code, payload=payload)


def run_manual_review(args: argparse.Namespace) -> DelegatedReportResult:
    artifact_path = _validate_manual_gate(args)
    _run_doctor()
    delegated = _delegate_report(args)
    review_script._write_json_artifact(delegated.payload, artifact_path)
    if delegated.exit_code not in SAFE_REPORT_EXIT_CODES:
        raise ManualReviewRunnerError("delegated_report_failed", EXIT_INVALID_USAGE)
    return delegated


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parse_args(argv)
        delegated = run_manual_review(args)
    except ManualReviewRunnerError as exc:
        local_data_acknowledged = bool(
            getattr(locals().get("args", None), "allow_local_data_readonly", False)
        )
        result = _safe_blocked_result(
            reason_code=exc.reason_code,
            local_data_acknowledged=local_data_acknowledged,
        )
        _print_json(result)
        return exc.exit_code
    except Exception:
        result = _safe_blocked_result(
            reason_code="unexpected_sanitized_failure",
            local_data_acknowledged=bool(
                getattr(locals().get("args", None), "allow_local_data_readonly", False)
            ),
        )
        _print_json(result)
        return EXIT_INVALID_USAGE

    _print_json(delegated.payload)
    return delegated.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
