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
from datetime import UTC, datetime, timedelta
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
MANUAL_RUNNER_PREFLIGHT_MODE = "manual_grouped_lifecycle_review_preflight"
MAX_LOOKBACK_HOURS = 168.0
EXIT_LOCAL_DATA_ACK_REQUIRED = 40
EXIT_DOCTOR_FAILED = 41
EXIT_UNSAFE_OUTPUT_PATH = 42
EXIT_INVALID_WINDOW = 43
EXIT_INVALID_USAGE = 2
REPORT_EXIT_CODE_DECISIONS = {
    exit_code: decision
    for decision, exit_code in review_script.REVIEW_DECISION_EXIT_CODES.items()
}
SAFE_REPORT_EXIT_CODES = frozenset(REPORT_EXIT_CODE_DECISIONS)


class ManualReviewRunnerError(RuntimeError):
    def __init__(self, reason_code: str, exit_code: int = EXIT_INVALID_USAGE) -> None:
        super().__init__(reason_code)
        self.reason_code = _safe_reason_code(reason_code)
        self.exit_code = exit_code


@dataclass(frozen=True)
class DelegatedReportResult:
    exit_code: int
    payload: Mapping[str, Any]


@dataclass(frozen=True)
class ResolvedWindow:
    start_at: str
    end_at: str
    source: str
    lookback_hours: float | None


@dataclass(frozen=True)
class ManualReviewPlan:
    artifact_path: Path
    resolved_window: ResolvedWindow


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


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _utc_iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


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


def _safe_preflight_result(
    *,
    status: str,
    reason_code: str | None,
    local_data_acknowledged: bool,
    resolved_window: ResolvedWindow | None = None,
    checks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "mode": MANUAL_RUNNER_PREFLIGHT_MODE,
        "status": status,
        "reason_code": reason_code,
        "read_only": True,
        "provider_free": False,
        "local_synthetic_only": False,
        "uses_real_local_data": False,
        "local_data_acknowledged": local_data_acknowledged,
        "executed_report": False,
        "output_format": "review-json",
        "enforced": False,
        "semantic_duplicate_claimed": False,
        "resolved_window": (
            {
                "start_at": resolved_window.start_at,
                "end_at": resolved_window.end_at,
                "source": resolved_window.source,
                "lookback_hours": resolved_window.lookback_hours,
            }
            if resolved_window is not None
            else None
        ),
        "checks": checks or [],
    }


def _assert_sanitized(value: Mapping[str, Any]) -> None:
    doctor_script._assert_sanitized(value)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Safety:\n"
            "- default-blocked without explicit local data acknowledgement.\n"
            "- doctor-gated before delegation.\n"
            "- sanitized output/artifact only.\n"
            "- no send, no enforcement, and no source-of-truth mutation."
        ),
    )
    parser.add_argument(
        "--allow-local-data-readonly",
        action="store_true",
        help=(
            "Explicitly acknowledge a read-only local-data grouped lifecycle "
            "review run. Without this flag, no report execution is attempted."
        ),
    )
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help=(
            "Validate the gated manual review configuration without executing "
            "the grouped lifecycle report."
        ),
    )
    parser.add_argument(
        "--start-at",
        help="Timezone-aware ISO start for the persisted attention window.",
    )
    parser.add_argument(
        "--end-at",
        help=(
            "Timezone-aware ISO end for the persisted attention window. With "
            "--lookback-hours, defaults to current UTC time when omitted."
        ),
    )
    parser.add_argument(
        "--lookback-hours",
        help=(
            "Bounded relative UTC window, greater than 0 and at most 168 hours. "
            "Use this instead of --start-at to avoid guessing timestamps."
        ),
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


def _parse_datetime(value: str, *, field_name: str) -> datetime:
    try:
        return review_script._parse_datetime(value, field_name=field_name)
    except review_script.NoMarkerGroupedLifecycleInputError as exc:
        raise ManualReviewRunnerError("invalid_window", EXIT_INVALID_WINDOW) from exc


def _parse_lookback_hours(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        lookback_hours = float(value)
    except (TypeError, ValueError) as exc:
        raise ManualReviewRunnerError("invalid_window", EXIT_INVALID_WINDOW) from exc
    if lookback_hours <= 0 or lookback_hours > MAX_LOOKBACK_HOURS:
        raise ManualReviewRunnerError("invalid_window", EXIT_INVALID_WINDOW)
    return lookback_hours


def _resolve_window(args: argparse.Namespace) -> ResolvedWindow:
    lookback_hours = _parse_lookback_hours(args.lookback_hours)
    if lookback_hours is not None:
        if args.start_at is not None:
            raise ManualReviewRunnerError("invalid_window", EXIT_INVALID_WINDOW)
        end_at = (
            _parse_datetime(args.end_at, field_name="end_at")
            if args.end_at is not None
            else _utc_now()
        )
        start_at = end_at - timedelta(hours=lookback_hours)
        return ResolvedWindow(
            start_at=_utc_iso(start_at),
            end_at=_utc_iso(end_at),
            source="lookback_hours",
            lookback_hours=lookback_hours,
        )

    if args.start_at is None or args.end_at is None:
        raise ManualReviewRunnerError("invalid_window", EXIT_INVALID_WINDOW)
    start_at = _parse_datetime(args.start_at, field_name="start_at")
    end_at = _parse_datetime(args.end_at, field_name="end_at")
    if end_at <= start_at:
        raise ManualReviewRunnerError("invalid_window", EXIT_INVALID_WINDOW)
    return ResolvedWindow(
        start_at=_utc_iso(start_at),
        end_at=_utc_iso(end_at),
        source="explicit",
        lookback_hours=None,
    )


def _validate_manual_gate(args: argparse.Namespace) -> ManualReviewPlan:
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
    resolved_window = _resolve_window(args)
    return ManualReviewPlan(
        artifact_path=artifact_path,
        resolved_window=resolved_window,
    )


def _run_doctor() -> Mapping[str, Any]:
    try:
        doctor_report = doctor_script.build_doctor_report()
    except Exception as exc:
        raise ManualReviewRunnerError("doctor_failed", EXIT_DOCTOR_FAILED) from exc
    _assert_sanitized(doctor_report)
    if doctor_report.get("status") != "pass":
        raise ManualReviewRunnerError("doctor_failed", EXIT_DOCTOR_FAILED)
    return doctor_report


def _check(name: str, status: str, reason_code: str | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "reason_code": reason_code,
    }


def run_preflight(args: argparse.Namespace) -> tuple[int, Mapping[str, Any]]:
    checks: list[dict[str, Any]] = []
    if not args.allow_local_data_readonly:
        checks.append(_check("acknowledgement", "blocked", "local_data_ack_required"))
        report = _safe_preflight_result(
            status="blocked",
            reason_code="local_data_ack_required",
            local_data_acknowledged=False,
            checks=checks,
        )
        return EXIT_LOCAL_DATA_ACK_REQUIRED, report

    checks.append(_check("acknowledgement", "pass"))
    try:
        plan = _validate_manual_gate(args)
    except ManualReviewRunnerError as exc:
        if exc.reason_code in {"unsafe_output_path", "output_path_required"}:
            checks.append(_check("artifact_path", "blocked", exc.reason_code))
        elif exc.reason_code == "invalid_window":
            checks.append(_check("window", "fail", exc.reason_code))
        else:
            checks.append(_check("configuration", "fail", exc.reason_code))
        status = "blocked" if exc.exit_code in {40, 41, 42} else "fail"
        report = _safe_preflight_result(
            status=status,
            reason_code=exc.reason_code,
            local_data_acknowledged=True,
            checks=checks,
        )
        return exc.exit_code, report

    checks.append(_check("output_mode", "pass"))
    checks.append(_check("artifact_path", "pass"))
    checks.append(_check("resolved_window", "pass"))
    try:
        _run_doctor()
    except ManualReviewRunnerError as exc:
        checks.append(_check("doctor", "blocked", exc.reason_code))
        report = _safe_preflight_result(
            status="blocked",
            reason_code=exc.reason_code,
            local_data_acknowledged=True,
            resolved_window=plan.resolved_window,
            checks=checks,
        )
        return exc.exit_code, report
    checks.append(_check("doctor", "pass"))
    report = _safe_preflight_result(
        status="pass",
        reason_code=None,
        local_data_acknowledged=True,
        resolved_window=plan.resolved_window,
        checks=checks,
    )
    _assert_sanitized(report)
    return 0, report


def _report_args(
    args: argparse.Namespace,
    resolved_window: ResolvedWindow,
    *,
    artifact_path: Path,
) -> list[str]:
    report_args = [
        "--start-at",
        resolved_window.start_at,
        "--end-at",
        resolved_window.end_at,
        "--format",
        "review-json",
        "--output-path",
        str(artifact_path),
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


def _normalize_delegated_report_artifact(
    payload: Mapping[str, Any],
) -> Mapping[str, Any]:
    if review_script.is_review_json_artifact(payload):
        return payload
    if review_script.is_legacy_review_json_artifact(payload):
        return review_script.format_review_json_report(payload)
    if review_script.is_full_compatibility_report_artifact(payload):
        return review_script.format_review_json_report(payload)
    raise ManualReviewRunnerError("delegated_report_failed", EXIT_INVALID_USAGE)


def _decision_from_review_artifact(payload: Mapping[str, Any]) -> str | None:
    summary = payload.get("operator_review_summary")
    diagnostics = payload.get("manual_review_diagnostics")
    if not isinstance(summary, Mapping) or not isinstance(diagnostics, Mapping):
        return None
    decision = summary.get("decision")
    diagnostic_status = diagnostics.get("diagnostic_status")
    if not isinstance(decision, str) or diagnostic_status != decision:
        return None
    return decision


def _delegate_report(
    args: argparse.Namespace,
    resolved_window: ResolvedWindow,
    *,
    artifact_path: Path,
) -> DelegatedReportResult:
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(
        io.StringIO()
    ):
        exit_code = review_script.main(
            _report_args(args, resolved_window, artifact_path=artifact_path)
        )
    delegated_decision = REPORT_EXIT_CODE_DECISIONS.get(exit_code)
    if delegated_decision is None:
        raise ManualReviewRunnerError("delegated_report_failed", EXIT_INVALID_USAGE)
    try:
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManualReviewRunnerError(
            "delegated_report_invalid_json",
            EXIT_INVALID_USAGE,
        ) from exc
    if not isinstance(payload, Mapping):
        raise ManualReviewRunnerError(
            "delegated_report_invalid_json",
            EXIT_INVALID_USAGE,
        )
    payload = _normalize_delegated_report_artifact(payload)
    payload_decision = _decision_from_review_artifact(payload)
    if payload_decision != delegated_decision:
        raise ManualReviewRunnerError("delegated_report_failed", EXIT_INVALID_USAGE)
    try:
        _assert_sanitized(payload)
    except Exception as exc:
        raise ManualReviewRunnerError(
            "delegated_report_failed",
            EXIT_INVALID_USAGE,
        ) from exc
    return DelegatedReportResult(exit_code=exit_code, payload=payload)


def run_manual_review(args: argparse.Namespace) -> DelegatedReportResult:
    plan = _validate_manual_gate(args)
    _run_doctor()
    delegated = _delegate_report(
        args,
        plan.resolved_window,
        artifact_path=plan.artifact_path,
    )
    if delegated.exit_code not in SAFE_REPORT_EXIT_CODES:
        raise ManualReviewRunnerError("delegated_report_failed", EXIT_INVALID_USAGE)
    review_script._write_json_artifact(delegated.payload, plan.artifact_path)
    return delegated


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parse_args(argv)
        if args.preflight_only:
            exit_code, preflight = run_preflight(args)
            _print_json(preflight)
            return exit_code
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
