#!/usr/bin/env python
"""Provider-free doctor for grouped lifecycle review operator workflow."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import (  # noqa: E402
    report_no_marker_persisted_attention_grouped_lifecycle_compatibility as review_script,
)

DOCTOR_MODE = "grouped_lifecycle_review_doctor"
CHECK_STATUS_PASS = "pass"
CHECK_STATUS_FAIL = "fail"
DOCTOR_PASS_EXIT_CODE = 0
DOCTOR_FAIL_EXIT_CODE = 1
SAFE_DECISIONS = frozenset(review_script.REVIEW_DECISION_EXIT_CODES)
EXPECTED_SYNTHETIC_SCENARIOS = frozenset(
    {
        "current_grouped_hash_already_sent",
        "linked_canonical_hash_blocks_presentation_variant",
        "not_blocked",
        "manual_review_insufficient_hash_evidence",
    }
)
REQUIRED_REVIEW_SECTIONS = frozenset(
    {
        "lifecycle_compatibility",
        "canonical_hash_guard_evaluation",
        "operator_review_summary",
    }
)
REQUIRED_LIFECYCLE_FIELDS = frozenset(
    {
        "canonical_candidate_text_sha256",
        "grouped_preview_text_sha256",
        "grouped_preview_hash_differs_from_canonical",
        "grouped_variant_would_be_treated_as",
        "presentation_variant_duplicate_send_risk",
        "requires_guard_extension_before_grouped_send",
    }
)
REQUIRED_CANONICAL_GUARD_FIELDS = frozenset(
    {
        "current_hash_has_successful_delivery",
        "linked_canonical_hash_has_successful_delivery",
        "blocked_by_canonical_success",
        "blocker_code",
        "recommended_action",
        "enforced",
        "semantic_duplicate_claimed",
        "read_only",
    }
)
REQUIRED_OPERATOR_SUMMARY_FIELDS = frozenset(
    {
        "decision",
        "blocker_code",
        "recommended_action",
        "requires_human_review",
        "reason_codes",
        "enforced",
        "semantic_duplicate_claimed",
        "read_only",
    }
)
UNSAFE_OUTPUT_PATTERNS = (
    "rendered_digest_text",
    "rendered digest text",
    "grouped_preview_text",
    "grouped preview text",
    '"chunk_text":',
    "chunk text",
    "raw_payload",
    "raw payload",
    "provider_payload",
    '"credentials":',
    '"credential":',
    "credential value",
    "webhook",
    "bot_token",
    "chat_id",
    '"source_object_id":',
    "source object id",
    "item_title",
    "item_summary",
    "item_action",
    "author_email",
    "author_name",
    '"evidence_refs": [',
    "remote_url",
    "repository_name",
    "http://",
    "https://",
)


class DoctorCheckError(RuntimeError):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = _safe_reason_code(reason_code)


@dataclass(frozen=True)
class DoctorContext:
    artifact_dir: Path | None = None


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    run: Callable[[DoctorContext], None]


def _safe_reason_code(value: str) -> str:
    cleaned = "".join(
        character if character.isalnum() or character == "_" else "_"
        for character in value.casefold()
    ).strip("_")
    return cleaned or "check_failed"


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, str):
        return value
    return []


def _serialized_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


def _safe_serialized(value: Mapping[str, Any]) -> str:
    serialized = _serialized_json(value)
    return serialized.replace("grouped_preview_text_sha256", "").replace(
        "grouped_preview_text_included",
        "",
    )


def _assert_sanitized(value: Mapping[str, Any]) -> None:
    serialized = _safe_serialized(value).casefold()
    if any(pattern in serialized for pattern in UNSAFE_OUTPUT_PATTERNS):
        raise DoctorCheckError("unsafe_output_detected")


def _assert_required_fields(
    value: Mapping[str, Any],
    required_fields: frozenset[str],
    *,
    reason_code: str,
) -> None:
    if not required_fields.issubset(value):
        raise DoctorCheckError(reason_code)


def _assert_review_contract(report: Mapping[str, Any]) -> None:
    _assert_required_fields(
        report,
        REQUIRED_REVIEW_SECTIONS,
        reason_code="missing_review_section",
    )
    lifecycle = _mapping(report.get("lifecycle_compatibility"))
    guard = _mapping(report.get("canonical_hash_guard_evaluation"))
    summary = _mapping(report.get("operator_review_summary"))
    _assert_required_fields(
        lifecycle,
        REQUIRED_LIFECYCLE_FIELDS,
        reason_code="missing_lifecycle_field",
    )
    _assert_required_fields(
        guard,
        REQUIRED_CANONICAL_GUARD_FIELDS,
        reason_code="missing_guard_field",
    )
    _assert_required_fields(
        summary,
        REQUIRED_OPERATOR_SUMMARY_FIELDS,
        reason_code="missing_operator_summary_field",
    )
    if summary.get("decision") not in SAFE_DECISIONS:
        raise DoctorCheckError("unknown_operator_decision")
    if guard.get("enforced") is not False or summary.get("enforced") is not False:
        raise DoctorCheckError("enforcement_not_false")
    if (
        guard.get("semantic_duplicate_claimed") is not False
        or summary.get("semantic_duplicate_claimed") is not False
    ):
        raise DoctorCheckError("semantic_duplicate_claimed")
    if guard.get("read_only") is not True or summary.get("read_only") is not True:
        raise DoctorCheckError("read_only_not_true")
    _assert_sanitized(report)


def _synthetic_report_for_decision(decision: str) -> Mapping[str, Any]:
    smoke_report = review_script.build_synthetic_review_smoke_report()
    for scenario in _sequence(smoke_report.get("scenarios")):
        scenario_mapping = _mapping(scenario)
        summary = _mapping(scenario_mapping.get("operator_review_summary"))
        if summary.get("decision") == decision:
            return scenario_mapping
    raise DoctorCheckError("missing_synthetic_decision")


def _check_help_contract(_context: DoctorContext) -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        try:
            review_script.main(["--help"])
        except SystemExit as exc:
            if exc.code != 0:
                raise DoctorCheckError("help_nonzero_exit") from exc
        else:
            raise DoctorCheckError("help_did_not_exit")

    help_output = stdout.getvalue()
    if stderr.getvalue():
        raise DoctorCheckError("help_stderr_not_empty")
    for expected in (
        "--format",
        "text",
        "json",
        "review-json",
        "decision/review-only",
        "read-only",
        "--synthetic-review-smoke",
        "--review-exit-code",
        "--output-path",
        "sanitized review-json",
    ):
        if expected not in help_output:
            raise DoctorCheckError("help_contract_missing_field")
    _assert_sanitized({"help_output": help_output})


def _check_synthetic_smoke_contract(_context: DoctorContext) -> None:
    smoke_report = review_script.build_synthetic_review_smoke_report()
    for key, expected in (
        ("mode", "synthetic_review_smoke"),
        ("read_only", True),
        ("provider_free", True),
        ("local_synthetic_only", True),
        ("uses_real_local_data", False),
        ("enforced", False),
        ("semantic_duplicate_claimed", False),
    ):
        if smoke_report.get(key) != expected:
            raise DoctorCheckError("synthetic_smoke_flag_mismatch")
    scenarios = list(_sequence(smoke_report.get("scenarios")))
    if smoke_report.get("scenario_count") != len(scenarios):
        raise DoctorCheckError("synthetic_smoke_scenario_count_mismatch")
    scenario_names = {
        _mapping(scenario).get("scenario_name") for scenario in scenarios
    }
    if scenario_names != EXPECTED_SYNTHETIC_SCENARIOS:
        raise DoctorCheckError("synthetic_smoke_scenario_mismatch")
    for scenario in scenarios:
        _assert_review_contract(_mapping(scenario))
    _assert_sanitized(smoke_report)


def _check_review_json_contract(_context: DoctorContext) -> None:
    review_report = _synthetic_report_for_decision("not_blocked")
    review_json = review_script.format_review_json_report(review_report)
    _assert_review_contract(review_json)
    for full_report_only_key in (
        "candidate",
        "grouped_preview",
        "duplicate_quality",
        "warnings",
        "limitations",
    ):
        if full_report_only_key in review_json:
            raise DoctorCheckError("review_json_contains_full_report_field")
    _assert_sanitized(review_json)


def _check_review_exit_codes(_context: DoctorContext) -> None:
    for decision, expected_exit_code in review_script.REVIEW_DECISION_EXIT_CODES.items():
        if review_script._review_exit_code_for_decision(decision) != expected_exit_code:
            raise DoctorCheckError("review_exit_code_mismatch")
        report = _synthetic_report_for_decision(decision)
        if review_script._review_exit_code_for_report(report) != expected_exit_code:
            raise DoctorCheckError("review_report_exit_code_mismatch")
    if review_script._review_exit_code_for_decision("unknown") != 30:
        raise DoctorCheckError("unknown_review_exit_code_not_conservative")
    smoke_code = review_script._review_exit_code_for_smoke_report(
        review_script.build_synthetic_review_smoke_report()
    )
    if smoke_code != 30:
        raise DoctorCheckError("synthetic_smoke_exit_code_not_conservative")


def _artifact_dir(context: DoctorContext) -> Path:
    if context.artifact_dir is None:
        raise DoctorCheckError("artifact_dir_missing")
    return context.artifact_dir


def _check_sanitized_artifact_output(context: DoctorContext) -> None:
    review_json = review_script.format_review_json_report(
        _synthetic_report_for_decision("not_blocked")
    )
    artifact_path = _artifact_dir(context) / "grouped-lifecycle-review-doctor.json"
    safe_path = review_script._safe_artifact_path(str(artifact_path))
    review_script._write_json_artifact(review_json, safe_path)
    loaded = json.loads(artifact_path.read_text(encoding="utf-8"))
    if loaded != review_json:
        raise DoctorCheckError("artifact_payload_mismatch")
    _assert_review_contract(loaded)
    _assert_sanitized(loaded)


def _check_unsafe_artifact_rejection(_context: DoctorContext) -> None:
    if review_script._artifact_output_allowed(
        output_format="json",
        synthetic_review_smoke=False,
    ):
        raise DoctorCheckError("full_json_artifact_allowed")
    if review_script._artifact_output_allowed(
        output_format="text",
        synthetic_review_smoke=False,
    ):
        raise DoctorCheckError("text_artifact_allowed")
    for unsafe_path in (
        "raw_storage/review.json",
        "obsidian_vault/review.json",
        ".git/review.json",
        ".config/review.json",
        "credentials.json",
        "token-review.json",
    ):
        try:
            review_script._safe_artifact_path(unsafe_path)
        except review_script.NoMarkerGroupedLifecycleInputError:
            continue
        raise DoctorCheckError("unsafe_artifact_path_allowed")


DOCTOR_CHECKS: tuple[DoctorCheck, ...] = (
    DoctorCheck("help_contract", _check_help_contract),
    DoctorCheck("synthetic_smoke_contract", _check_synthetic_smoke_contract),
    DoctorCheck("review_json_contract", _check_review_json_contract),
    DoctorCheck("review_exit_codes", _check_review_exit_codes),
    DoctorCheck("sanitized_artifact_output", _check_sanitized_artifact_output),
    DoctorCheck("unsafe_artifact_rejection", _check_unsafe_artifact_rejection),
)


def _run_check(check: DoctorCheck, context: DoctorContext) -> dict[str, str | None]:
    try:
        check.run(context)
    except DoctorCheckError as exc:
        return {
            "name": check.name,
            "status": CHECK_STATUS_FAIL,
            "reason_code": exc.reason_code,
        }
    except Exception:
        return {
            "name": check.name,
            "status": CHECK_STATUS_FAIL,
            "reason_code": "unexpected_exception",
        }
    return {
        "name": check.name,
        "status": CHECK_STATUS_PASS,
        "reason_code": None,
    }


def build_doctor_report(*, artifact_dir: Path | None = None) -> dict[str, Any]:
    if artifact_dir is not None:
        artifact_dir.mkdir(parents=True, exist_ok=True)
        checks = [_run_check(check, DoctorContext(artifact_dir)) for check in DOCTOR_CHECKS]
    else:
        with tempfile.TemporaryDirectory(
            prefix="grouped_lifecycle_review_doctor_"
        ) as temp_dir:
            context = DoctorContext(Path(temp_dir))
            checks = [_run_check(check, context) for check in DOCTOR_CHECKS]

    failed_count = sum(1 for check in checks if check["status"] != CHECK_STATUS_PASS)
    summary = {
        "check_count": len(checks),
        "passed_count": len(checks) - failed_count,
        "failed_count": failed_count,
    }
    report = {
        "mode": DOCTOR_MODE,
        "status": CHECK_STATUS_PASS if failed_count == 0 else CHECK_STATUS_FAIL,
        "read_only": True,
        "provider_free": True,
        "local_synthetic_only": True,
        "uses_real_local_data": False,
        "enforced": False,
        "semantic_duplicate_claimed": False,
        "checks": checks,
        "summary": summary,
    }
    try:
        _assert_sanitized(report)
    except DoctorCheckError:
        report["status"] = CHECK_STATUS_FAIL
        report["checks"].append(
            {
                "name": "doctor_output_sanitization",
                "status": CHECK_STATUS_FAIL,
                "reason_code": "unsafe_output_detected",
            }
        )
        report["summary"] = {
            "check_count": len(report["checks"]),
            "passed_count": len(checks) - failed_count,
            "failed_count": failed_count + 1,
        }
    return report


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    return parser.parse_args(argv)


def _print_json(value: Mapping[str, Any]) -> None:
    print(_serialized_json(value), end="")


def main(argv: list[str] | None = None) -> int:
    _parse_args(argv)
    try:
        report = build_doctor_report()
    except Exception:
        report = {
            "mode": DOCTOR_MODE,
            "status": CHECK_STATUS_FAIL,
            "read_only": True,
            "provider_free": True,
            "local_synthetic_only": True,
            "uses_real_local_data": False,
            "enforced": False,
            "semantic_duplicate_claimed": False,
            "checks": [
                {
                    "name": "doctor_runtime",
                    "status": CHECK_STATUS_FAIL,
                    "reason_code": "unexpected_exception",
                }
            ],
            "summary": {
                "check_count": 1,
                "passed_count": 0,
                "failed_count": 1,
            },
        }
    _print_json(report)
    return (
        DOCTOR_PASS_EXIT_CODE
        if report.get("status") == CHECK_STATUS_PASS
        else DOCTOR_FAIL_EXIT_CODE
    )


if __name__ == "__main__":
    raise SystemExit(main())
