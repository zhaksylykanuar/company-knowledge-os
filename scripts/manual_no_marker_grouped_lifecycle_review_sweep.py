#!/usr/bin/env python
"""Gated manual grouped lifecycle review window sweep runner."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import manual_no_marker_grouped_lifecycle_review as manual_script  # noqa: E402
from scripts import (  # noqa: E402
    report_no_marker_persisted_attention_grouped_lifecycle_compatibility as review_script,
)

SWEEP_MODE = "manual_grouped_lifecycle_review_sweep"
DEFAULT_LOOKBACK_HOURS = (6.0, 24.0, 72.0)
DELEGATED_REVIEW_DECISION_EXIT_CODES = dict(review_script.REVIEW_DECISION_EXIT_CODES)
DELEGATED_REVIEW_EXIT_CODE_DECISIONS = {
    exit_code: decision
    for decision, exit_code in DELEGATED_REVIEW_DECISION_EXIT_CODES.items()
}
EXIT_LOCAL_DATA_ACK_REQUIRED = manual_script.EXIT_LOCAL_DATA_ACK_REQUIRED
EXIT_DOCTOR_FAILED = manual_script.EXIT_DOCTOR_FAILED
EXIT_UNSAFE_OUTPUT_PATH = manual_script.EXIT_UNSAFE_OUTPUT_PATH
EXIT_INVALID_WINDOW = manual_script.EXIT_INVALID_WINDOW
EXIT_INVALID_USAGE = manual_script.EXIT_INVALID_USAGE
SAFE_REPORT_EXIT_CODES = frozenset(DELEGATED_REVIEW_EXIT_CODE_DECISIONS)
AGGREGATE_DECISION_ORDER = (
    "manual_review_needed",
    "blocked_by_linked_canonical_hash",
    "already_sent_by_current_hash",
    "not_blocked",
)
UNSAFE_OUTPUT_DIR_PARTS = {
    ".config",
    ".git",
    ".ssh",
    "obsidian_vault",
    "raw_storage",
}
UNSAFE_OUTPUT_DIR_FRAGMENTS = (
    "credential",
    "secret",
    "token",
    "webhook",
)


class SweepRunnerError(RuntimeError):
    def __init__(
        self,
        reason_code: str,
        exit_code: int = EXIT_INVALID_USAGE,
        *,
        diagnostics: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(reason_code)
        self.reason_code = manual_script._safe_reason_code(reason_code)
        self.exit_code = exit_code
        self.diagnostics = dict(diagnostics or {})


@dataclass(frozen=True)
class SweepPlan:
    lookback_hours: tuple[float, ...]
    output_dir: Path


def _json_text(value: Mapping[str, Any]) -> str:
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


def _print_json(value: Mapping[str, Any]) -> None:
    print(_json_text(value), end="")


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
            "review sweep. Without this flag, no window delegation is attempted."
        ),
    )
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="Validate the sweep configuration without executing window reviews.",
    )
    parser.add_argument(
        "--lookback-hours-list",
        default=",".join(str(int(value)) for value in DEFAULT_LOOKBACK_HOURS),
        help=(
            "Comma-separated bounded UTC lookback windows in hours, default "
            "6,24,72. Values must be positive, unique, and at most 168."
        ),
    )
    parser.add_argument(
        "--end-at",
        help=(
            "Optional timezone-aware ISO end for every lookback window. "
            "Defaults to current UTC time inside each delegated manual review."
        ),
    )
    parser.add_argument(
        "--output-dir",
        help="Required safe local directory for sanitized per-window artifacts.",
    )
    parser.add_argument("--activity-start-at")
    parser.add_argument("--activity-end-at")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--debug-evidence", action="store_true")
    parser.add_argument("--cluster-threshold", type=int)
    parser.add_argument("--group-by")
    return parser.parse_args(argv)


def _normalize_lookback(value: float) -> float:
    return float(int(value)) if value.is_integer() else value


def parse_lookback_hours_list(value: str | None) -> tuple[float, ...]:
    raw_value = value if value is not None else ""
    parts = raw_value.split(",")
    if not parts or any(not part.strip() for part in parts):
        raise SweepRunnerError("invalid_window", EXIT_INVALID_WINDOW)
    lookbacks: list[float] = []
    seen: set[float] = set()
    for part in parts:
        try:
            parsed = float(part.strip())
        except ValueError as exc:
            raise SweepRunnerError("invalid_window", EXIT_INVALID_WINDOW) from exc
        normalized = _normalize_lookback(parsed)
        if normalized <= 0 or normalized > manual_script.MAX_LOOKBACK_HOURS:
            raise SweepRunnerError("invalid_window", EXIT_INVALID_WINDOW)
        if normalized in seen:
            raise SweepRunnerError("invalid_window", EXIT_INVALID_WINDOW)
        seen.add(normalized)
        lookbacks.append(normalized)
    return tuple(lookbacks)


def _safe_output_dir(path_value: str | None) -> Path:
    if path_value is None:
        raise SweepRunnerError("output_dir_required", EXIT_UNSAFE_OUTPUT_PATH)
    path = Path(path_value).expanduser()
    name = path.name.casefold()
    parts = [part.casefold() for part in path.parts]
    if not name or name in {".", ".."}:
        raise SweepRunnerError("unsafe_output_path", EXIT_UNSAFE_OUTPUT_PATH)
    if any(part in UNSAFE_OUTPUT_DIR_PARTS for part in parts):
        raise SweepRunnerError("unsafe_output_path", EXIT_UNSAFE_OUTPUT_PATH)
    if name.startswith(".env") or any(
        fragment in name for fragment in UNSAFE_OUTPUT_DIR_FRAGMENTS
    ):
        raise SweepRunnerError("unsafe_output_path", EXIT_UNSAFE_OUTPUT_PATH)
    try:
        resolved = path.resolve(strict=False)
        repo_root = REPO_ROOT.resolve(strict=True)
    except OSError as exc:
        raise SweepRunnerError("unsafe_output_path", EXIT_UNSAFE_OUTPUT_PATH) from exc
    if resolved == repo_root or repo_root in resolved.parents:
        raise SweepRunnerError("unsafe_output_path", EXIT_UNSAFE_OUTPUT_PATH)
    if path.exists() and not path.is_dir():
        raise SweepRunnerError("unsafe_output_path", EXIT_UNSAFE_OUTPUT_PATH)
    return path


def _validate_sweep_plan(args: argparse.Namespace) -> SweepPlan:
    if not args.allow_local_data_readonly:
        raise SweepRunnerError(
            "local_data_ack_required",
            EXIT_LOCAL_DATA_ACK_REQUIRED,
        )
    return SweepPlan(
        lookback_hours=parse_lookback_hours_list(args.lookback_hours_list),
        output_dir=_safe_output_dir(args.output_dir),
    )


def _check(name: str, status: str, reason_code: str | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "reason_code": reason_code,
    }


def _safe_base_result(
    *,
    status: str,
    reason_code: str | None,
    local_data_acknowledged: bool,
    lookback_hours: Sequence[float] = (),
    executed_report_count: int = 0,
    checks: list[dict[str, Any]] | None = None,
    windows: list[dict[str, Any]] | None = None,
    aggregate_decision: str | None = None,
    aggregate_reason_codes: list[str] | None = None,
    recommended_operator_action: str | None = None,
    delegated_contract_diagnostics: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    result = {
        "mode": SWEEP_MODE,
        "status": status,
        "reason_code": reason_code,
        "read_only": True,
        "provider_free": False,
        "local_synthetic_only": False,
        "uses_real_local_data": local_data_acknowledged
        and executed_report_count > 0,
        "local_data_acknowledged": local_data_acknowledged,
        "executed_report_count": executed_report_count,
        "window_count": len(lookback_hours),
        "lookback_hours": list(lookback_hours),
        "windows": windows or [],
        "aggregate_decision": aggregate_decision,
        "aggregate_reason_codes": aggregate_reason_codes or [],
        "recommended_operator_action": recommended_operator_action,
        "output_format": "review-json",
        "enforced": False,
        "semantic_duplicate_claimed": False,
        "checks": checks or [],
    }
    if delegated_contract_diagnostics:
        result["delegated_contract_diagnostics"] = dict(
            delegated_contract_diagnostics
        )
    return result


def _run_doctor() -> Mapping[str, Any]:
    try:
        return manual_script._run_doctor()
    except manual_script.ManualReviewRunnerError as exc:
        raise SweepRunnerError(exc.reason_code, exc.exit_code) from exc


def run_preflight(args: argparse.Namespace) -> tuple[int, Mapping[str, Any]]:
    checks: list[dict[str, Any]] = []
    if not args.allow_local_data_readonly:
        checks.append(_check("acknowledgement", "blocked", "local_data_ack_required"))
        result = _safe_base_result(
            status="blocked",
            reason_code="local_data_ack_required",
            local_data_acknowledged=False,
            checks=checks,
        )
        return EXIT_LOCAL_DATA_ACK_REQUIRED, result

    checks.append(_check("acknowledgement", "pass"))
    try:
        plan = _validate_sweep_plan(args)
    except SweepRunnerError as exc:
        if exc.exit_code == EXIT_INVALID_WINDOW:
            checks.append(_check("window_list", "fail", exc.reason_code))
        elif exc.exit_code == EXIT_UNSAFE_OUTPUT_PATH:
            checks.append(_check("output_dir", "blocked", exc.reason_code))
        else:
            checks.append(_check("configuration", "fail", exc.reason_code))
        status = "blocked" if exc.exit_code in {40, 41, 42} else "fail"
        result = _safe_base_result(
            status=status,
            reason_code=exc.reason_code,
            local_data_acknowledged=True,
            checks=checks,
        )
        return exc.exit_code, result

    checks.append(_check("window_list", "pass"))
    checks.append(_check("output_dir", "pass"))
    try:
        _run_doctor()
    except SweepRunnerError as exc:
        checks.append(_check("doctor", "blocked", exc.reason_code))
        result = _safe_base_result(
            status="blocked",
            reason_code=exc.reason_code,
            local_data_acknowledged=True,
            lookback_hours=plan.lookback_hours,
            checks=checks,
        )
        return exc.exit_code, result
    checks.append(_check("doctor", "pass"))
    checks.append(_check("output_contract", "pass"))
    windows = [
        {
            "lookback_hours": lookback,
            "status": "preflight_only",
            "exit_code": None,
            "decision": None,
            "diagnostic_status": None,
            "reason_codes": [],
            "safe_next_step": None,
            "recommended_operator_action": None,
            "artifact_written": False,
        }
        for lookback in plan.lookback_hours
    ]
    result = _safe_base_result(
        status="pass",
        reason_code=None,
        local_data_acknowledged=True,
        lookback_hours=plan.lookback_hours,
        checks=checks,
        windows=windows,
        aggregate_decision=None,
        aggregate_reason_codes=[],
        recommended_operator_action=None,
    )
    manual_script._assert_sanitized(result)
    return 0, result


def _window_artifact_path(output_dir: Path, lookback_hours: float) -> Path:
    label = str(lookback_hours).replace(".", "p")
    return output_dir / f"grouped-lifecycle-review-{label}h.json"


def _manual_argv_for_window(
    args: argparse.Namespace,
    *,
    lookback_hours: float,
    output_path: Path,
) -> list[str]:
    manual_argv = [
        "--allow-local-data-readonly",
        "--lookback-hours",
        str(lookback_hours),
        "--format",
        "review-json",
        "--output-path",
        str(output_path),
    ]
    optional_string_args = (
        ("--end-at", args.end_at),
        ("--activity-start-at", args.activity_start_at),
        ("--activity-end-at", args.activity_end_at),
        ("--group-by", args.group_by),
    )
    for flag, value in optional_string_args:
        if value is not None:
            manual_argv.extend([flag, value])
    optional_int_args = (
        ("--limit", args.limit),
        ("--cluster-threshold", args.cluster_threshold),
    )
    for flag, value in optional_int_args:
        if value is not None:
            manual_argv.extend([flag, str(value)])
    if args.debug_evidence:
        manual_argv.append("--debug-evidence")
    return manual_argv


def _decision_from_delegated_exit_code(exit_code: int) -> str | None:
    return DELEGATED_REVIEW_EXIT_CODE_DECISIONS.get(exit_code)


def _decision_from_payload(payload: Mapping[str, Any]) -> str | None:
    summary = payload.get("operator_review_summary")
    if isinstance(summary, Mapping):
        decision = summary.get("decision")
        return decision if isinstance(decision, str) else None
    return None


def _window_summary(
    *,
    lookback_hours: float,
    exit_code: int,
    decision: str,
    payload: Mapping[str, Any],
    artifact_written: bool,
) -> dict[str, Any]:
    summary = payload.get("operator_review_summary")
    diagnostics = payload.get("manual_review_diagnostics")
    summary_mapping = summary if isinstance(summary, Mapping) else {}
    diagnostics_mapping = diagnostics if isinstance(diagnostics, Mapping) else {}
    reason_codes = diagnostics_mapping.get("reason_codes")
    if not isinstance(reason_codes, list):
        reason_codes = summary_mapping.get("reason_codes")
    safe_reason_codes = [
        reason_code
        for reason_code in reason_codes or []
        if isinstance(reason_code, str) and reason_code
    ]
    return {
        "lookback_hours": lookback_hours,
        "status": "completed",
        "exit_code": exit_code,
        "decision": decision,
        "diagnostic_status": diagnostics_mapping.get("diagnostic_status"),
        "reason_codes": list(dict.fromkeys(safe_reason_codes)),
        "safe_next_step": diagnostics_mapping.get("safe_next_step"),
        "recommended_operator_action": diagnostics_mapping.get(
            "recommended_operator_action"
        ),
        "artifact_written": artifact_written,
    }


def _aggregate_decision(windows: Sequence[Mapping[str, Any]]) -> str:
    decisions = [
        window.get("decision")
        for window in windows
        if isinstance(window.get("decision"), str)
    ]
    if len(decisions) != len(windows):
        return "manual_review_needed"
    for decision in AGGREGATE_DECISION_ORDER:
        if decision == "not_blocked":
            if decisions and all(value == "not_blocked" for value in decisions):
                return "not_blocked"
        elif decision in decisions:
            return decision
    return "manual_review_needed"


def _aggregate_reason_codes(windows: Sequence[Mapping[str, Any]]) -> list[str]:
    reason_codes: list[str] = []
    for window in windows:
        reason_codes.extend(
            reason
            for reason in window.get("reason_codes", [])
            if isinstance(reason, str) and reason
        )
    return list(dict.fromkeys(reason_codes))


def _recommended_action_for_aggregate(
    *,
    aggregate_decision: str,
    windows: Sequence[Mapping[str, Any]],
) -> str:
    if aggregate_decision == "not_blocked":
        return "no_action_required"
    for window in windows:
        if window.get("decision") == aggregate_decision and isinstance(
            window.get("recommended_operator_action"),
            str,
        ):
            return str(window["recommended_operator_action"])
    if aggregate_decision == "manual_review_needed":
        return "keep_manual_review"
    return "inspect_review_artifact"


def _exit_code_for_aggregate(aggregate_decision: str) -> int:
    return DELEGATED_REVIEW_DECISION_EXIT_CODES.get(aggregate_decision, 30)


def _extract_delegated_contract_diagnostics(
    delegated_stdout: str,
) -> Mapping[str, Any] | None:
    try:
        payload = json.loads(delegated_stdout)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, Mapping):
        return None
    diagnostics = payload.get("delegated_contract_diagnostics")
    if not isinstance(diagnostics, Mapping):
        return None
    return dict(diagnostics)


def _delegate_window_review(
    args: argparse.Namespace,
    *,
    lookback_hours: float,
    output_path: Path,
) -> manual_script.DelegatedReportResult:
    manual_argv = _manual_argv_for_window(
        args,
        lookback_hours=lookback_hours,
        output_path=output_path,
    )
    delegated_stdout = io.StringIO()
    with contextlib.redirect_stdout(delegated_stdout), contextlib.redirect_stderr(
        io.StringIO()
    ):
        exit_code = manual_script.main(manual_argv)
    delegated_decision = _decision_from_delegated_exit_code(exit_code)
    if delegated_decision is None:
        raise SweepRunnerError(
            "delegated_report_failed",
            EXIT_INVALID_USAGE,
            diagnostics=_extract_delegated_contract_diagnostics(
                delegated_stdout.getvalue()
            ),
        )
    # The per-window artifact is the manual runner's durable sanitized contract.
    # Captured stdout can contain safe diagnostics and must not decide success.
    try:
        payload = json.loads(output_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SweepRunnerError("delegated_report_failed", EXIT_INVALID_USAGE) from exc
    if not isinstance(payload, Mapping):
        raise SweepRunnerError("delegated_report_failed", EXIT_INVALID_USAGE)
    if _decision_from_payload(payload) != delegated_decision:
        raise SweepRunnerError("delegated_report_failed", EXIT_INVALID_USAGE)
    try:
        manual_script._assert_sanitized(payload)
    except Exception as exc:
        raise SweepRunnerError("delegated_report_failed", EXIT_INVALID_USAGE) from exc
    return manual_script.DelegatedReportResult(
        exit_code=exit_code,
        payload=payload,
    )


def run_sweep(args: argparse.Namespace) -> tuple[int, Mapping[str, Any]]:
    checks: list[dict[str, Any]] = []
    try:
        plan = _validate_sweep_plan(args)
    except SweepRunnerError as exc:
        result = _safe_base_result(
            status="blocked" if exc.exit_code in {40, 42} else "fail",
            reason_code=exc.reason_code,
            local_data_acknowledged=bool(args.allow_local_data_readonly),
            checks=[
                _check(
                    "acknowledgement",
                    "blocked",
                    "local_data_ack_required",
                )
            ]
            if exc.exit_code == EXIT_LOCAL_DATA_ACK_REQUIRED
            else [],
        )
        return exc.exit_code, result

    checks.append(_check("acknowledgement", "pass"))
    checks.append(_check("window_list", "pass"))
    checks.append(_check("output_dir", "pass"))
    try:
        _run_doctor()
    except SweepRunnerError as exc:
        checks.append(_check("doctor", "blocked", exc.reason_code))
        result = _safe_base_result(
            status="blocked",
            reason_code=exc.reason_code,
            local_data_acknowledged=True,
            lookback_hours=plan.lookback_hours,
            checks=checks,
        )
        return exc.exit_code, result
    checks.append(_check("doctor", "pass"))

    plan.output_dir.mkdir(parents=True, exist_ok=True)
    windows: list[dict[str, Any]] = []
    for lookback in plan.lookback_hours:
        artifact_path = _window_artifact_path(plan.output_dir, lookback)
        try:
            delegated = _delegate_window_review(
                args,
                lookback_hours=lookback,
                output_path=artifact_path,
            )
        except SweepRunnerError:
            raise
        except Exception as exc:
            raise SweepRunnerError("delegated_report_failed", EXIT_INVALID_USAGE) from exc
        delegated_decision = _decision_from_delegated_exit_code(delegated.exit_code)
        if delegated_decision is None:
            raise SweepRunnerError("delegated_report_failed", EXIT_INVALID_USAGE)
        windows.append(
            _window_summary(
                lookback_hours=lookback,
                exit_code=delegated.exit_code,
                decision=delegated_decision,
                payload=delegated.payload,
                artifact_written=artifact_path.exists(),
            )
        )

    aggregate_decision = _aggregate_decision(windows)
    aggregate_reason_codes = _aggregate_reason_codes(windows)
    recommended_operator_action = _recommended_action_for_aggregate(
        aggregate_decision=aggregate_decision,
        windows=windows,
    )
    result = _safe_base_result(
        status="pass",
        reason_code=None,
        local_data_acknowledged=True,
        lookback_hours=plan.lookback_hours,
        executed_report_count=len(windows),
        checks=checks,
        windows=windows,
        aggregate_decision=aggregate_decision,
        aggregate_reason_codes=aggregate_reason_codes,
        recommended_operator_action=recommended_operator_action,
    )
    manual_script._assert_sanitized(result)
    return _exit_code_for_aggregate(aggregate_decision), result


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parse_args(argv)
        if args.preflight_only:
            exit_code, result = run_preflight(args)
        else:
            exit_code, result = run_sweep(args)
        manual_script._assert_sanitized(result)
    except SweepRunnerError as exc:
        result = _safe_base_result(
            status="blocked" if exc.exit_code in {40, 41, 42} else "fail",
            reason_code=exc.reason_code,
            local_data_acknowledged=bool(
                getattr(locals().get("args", None), "allow_local_data_readonly", False)
            ),
            delegated_contract_diagnostics=exc.diagnostics,
        )
        _print_json(result)
        return exc.exit_code
    except Exception:
        result = _safe_base_result(
            status="fail",
            reason_code="unexpected_sanitized_failure",
            local_data_acknowledged=bool(
                getattr(locals().get("args", None), "allow_local_data_readonly", False)
            ),
        )
        _print_json(result)
        return EXIT_INVALID_USAGE

    _print_json(result)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
