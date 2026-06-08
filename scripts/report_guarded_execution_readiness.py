#!/usr/bin/env python
"""Read-only guarded-execution readiness report."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.services.guarded_execution_audit import (  # noqa: E402
    guarded_execution_audit_coverage_summary,
)
from app.services.guarded_execution_contracts import (  # noqa: E402
    validate_readiness_report_contract,
)
from app.services.operator_output_sanitizer import inspect_operator_output  # noqa: E402
from app.services.external_connector_registry import (  # noqa: E402
    connector_readiness_summary,
)
from app.services.repository_portfolio import (  # noqa: E402
    repository_portfolio_public_summary,
)
from scripts import doctor_guarded_execution as doctor  # noqa: E402

REPORT_KIND = "guarded_execution_readiness"
REPORT_PASS_EXIT_CODE = 0
REPORT_FAIL_EXIT_CODE = 1
STATUS_PASS = "pass"
STATUS_FAIL = "fail"

CHECK_NAMES = (
    "provider_execution_guard",
    "production_operation_guard",
    "scheduler_execution_guard",
    "operator_output_sanitizer",
    "guarded_execution_doctor",
    "guarded_execution_audit",
    "audit_sink",
    "external_connector_registry",
    "repository_portfolio_catalog",
    "github_connector",
    "jira_connector",
    "guarded_operations_runbook",
    "core_docs_references",
)
REMAINING_RISKS = {
    "production_deploy_ops": "not_implemented",
    "persistent_audit_logging": "not_implemented",
    "scheduler_outbox_execution": "intentionally_disabled",
    "live_provider_execution": "gated_only",
    "production_db_migrations": "out_of_scope",
}
DOC_REFERENCE_LABELS = (
    "guarded_operations_runbook",
    "data_model",
    "attention_feature",
    "telegram_digest_feature",
)


class ReadinessReportError(RuntimeError):
    def __init__(self, reason_code: str) -> None:
        super().__init__(_safe_reason_code(reason_code))
        self.reason_code = _safe_reason_code(reason_code)


def _safe_reason_code(value: str) -> str:
    cleaned = "".join(
        character if character.isalnum() or character == "_" else "_"
        for character in value.casefold()
    ).strip("_")
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned or "guarded_execution_readiness_failed"


def run_readiness_report(
    *,
    doctor_runner: Callable[[], Mapping[str, Any]] = doctor.run_doctor,
    docs_root: Path | None = None,
) -> dict[str, Any]:
    try:
        return _run_readiness_report(
            doctor_runner=doctor_runner,
            docs_root=docs_root or REPO_ROOT / "docs",
        )
    except ReadinessReportError as exc:
        return _failure_report(exc.reason_code)
    except Exception:
        return _failure_report("guarded_execution_readiness_exception")


def _run_readiness_report(
    *,
    doctor_runner: Callable[[], Mapping[str, Any]],
    docs_root: Path,
) -> dict[str, Any]:
    doctor_result = dict(doctor_runner())
    doctor_summary = _doctor_summary(doctor_result)
    docs_summary = _docs_summary(docs_root)
    guard_summary = _guard_summary(doctor_result, doctor_summary)
    connector_summary = connector_readiness_summary()
    portfolio_summary = repository_portfolio_public_summary()
    checks = _checks(guard_summary, docs_summary, connector_summary, portfolio_summary)
    failed_checks = [check["name"] for check in checks if check["status"] != STATUS_PASS]
    status = STATUS_PASS if not failed_checks else STATUS_FAIL
    result = {
        "status": status,
        "reason_code": None
        if status == STATUS_PASS
        else "guarded_execution_readiness_failed",
        "report_kind": REPORT_KIND,
        "no_send": True,
        "no_provider_calls": True,
        "no_source_of_truth_mutation": True,
        "scheduler_execution": "disabled",
        "checks": checks,
        "guard_summary": guard_summary,
        "connector_summary": connector_summary,
        "portfolio_summary": portfolio_summary,
        "docs_summary": docs_summary,
        "remaining_risks": dict(REMAINING_RISKS),
        "diagnostics": {
            "check_count": len(checks),
            "failed_check_count": len(failed_checks),
            "failed_check_names": sorted(failed_checks),
            "doctor": doctor_summary,
            "guarded_execution_audit_coverage": guarded_execution_audit_coverage_summary(),
            "operator_output_safety": inspect_operator_output(
                {
                    "checks": checks,
                    "guard_summary": guard_summary,
                    "connector_summary": connector_summary,
                    "portfolio_summary": portfolio_summary,
                    "docs_summary": docs_summary,
                    "remaining_risks": REMAINING_RISKS,
                    "doctor": doctor_summary,
                }
            ).as_dict(),
        },
    }
    if inspect_operator_output(result).safe is not True:
        raise ReadinessReportError("guarded_execution_readiness_output_unsafe")
    validation = validate_readiness_report_contract(result).as_dict()
    result["contract_validation"] = validation
    if validation["validation_status"] != STATUS_PASS:
        return _failure_report(
            "guarded_execution_readiness_contract_invalid",
            contract_validation=validation,
        )
    return result


def _doctor_summary(doctor_result: Mapping[str, Any]) -> dict[str, Any]:
    diagnostics = doctor_result.get("diagnostics", {})
    if not isinstance(diagnostics, Mapping):
        diagnostics = {}
    sink = diagnostics.get("guarded_execution_audit_sink", {})
    if not isinstance(sink, Mapping):
        sink = {}
    coverage = diagnostics.get("guarded_execution_audit_coverage", {})
    if not isinstance(coverage, Mapping):
        coverage = {}
    safety = diagnostics.get("operator_output_safety", {})
    if not isinstance(safety, Mapping):
        safety = {}
    return {
        "status": _safe_status(doctor_result.get("status")),
        "reason_code": _safe_reason_or_none(doctor_result.get("reason_code")),
        "check_count": _safe_int(diagnostics.get("check_count")),
        "failed_check_count": _safe_int(diagnostics.get("failed_check_count")),
        "audit_sink_event_count": _safe_int(sink.get("event_count")),
        "audit_sink_unsafe_pattern_count": _safe_int(sink.get("unsafe_pattern_count")),
        "audit_coverage_count": _safe_int(coverage.get("coverage_count")),
        "unsafe_pattern_count": _safe_int(safety.get("unsafe_pattern_count")),
        "unsafe_pattern_classes": _safe_list(safety.get("unsafe_pattern_classes")),
    }


def _guard_summary(
    doctor_result: Mapping[str, Any],
    doctor_summary: Mapping[str, Any],
) -> dict[str, str]:
    by_name = _doctor_checks_by_name(doctor_result)
    return {
        "provider_execution_guard": _guard_status(
            by_name,
            "provider_guard_default_denied",
            "present/default_denied",
        ),
        "production_operation_guard": _guard_status(
            by_name,
            "production_operation_guard_default_denied",
            "present/default_denied",
        ),
        "scheduler_execution_guard": _guard_status(
            by_name,
            "scheduler_execution_guard_default_disabled",
            "present/default_disabled",
        ),
        "operator_output_sanitizer": _guard_status(
            by_name,
            "operator_output_sanitizer",
            "present/safe_counts_only",
        ),
        "guarded_execution_doctor": "present/pass"
        if doctor_summary.get("status") == STATUS_PASS
        else "present/fail",
        "guarded_execution_audit": "present/sanitized_metadata"
        if doctor_summary.get("audit_coverage_count", 0) >= 6
        else "present/incomplete",
        "audit_sink": "present/non_persistent"
        if doctor_summary.get("audit_sink_event_count", 0) >= 5
        else "present/incomplete",
    }


def _docs_summary(docs_root: Path) -> dict[str, Any]:
    docs = {
        "guarded_operations_runbook": docs_root / "runbooks" / "guarded-operations.md",
        "data_model": docs_root / "data-model.md",
        "attention_feature": docs_root / "features" / "attention.md",
        "telegram_digest_feature": docs_root / "features" / "telegram-digest.md",
    }
    present = {name: path.exists() for name, path in docs.items()}
    return {
        "guarded_operations_runbook": "present"
        if present["guarded_operations_runbook"]
        else "missing",
        "core_docs_references": "present" if all(present.values()) else "missing",
        "reference_count": sum(1 for exists in present.values() if exists),
        "reference_labels": [name for name in DOC_REFERENCE_LABELS if present.get(name)],
    }


def _checks(
    guard_summary: Mapping[str, str],
    docs_summary: Mapping[str, Any],
    connector_summary: Mapping[str, Any],
    portfolio_summary: Mapping[str, Any],
) -> list[dict[str, str]]:
    statuses = {
        "provider_execution_guard": guard_summary["provider_execution_guard"],
        "production_operation_guard": guard_summary["production_operation_guard"],
        "scheduler_execution_guard": guard_summary["scheduler_execution_guard"],
        "operator_output_sanitizer": guard_summary["operator_output_sanitizer"],
        "guarded_execution_doctor": guard_summary["guarded_execution_doctor"],
        "guarded_execution_audit": guard_summary["guarded_execution_audit"],
        "audit_sink": guard_summary["audit_sink"],
        "external_connector_registry": connector_summary["registry"],
        "repository_portfolio_catalog": portfolio_summary["portfolio_catalog"],
        "github_connector": connector_summary["github_connector"],
        "jira_connector": connector_summary["jira_connector"],
        "guarded_operations_runbook": docs_summary["guarded_operations_runbook"],
        "core_docs_references": docs_summary["core_docs_references"],
    }
    return [
        {
            "name": name,
            "status": STATUS_PASS
            if statuses[name]
            in {
                "present",
                "present/default_denied",
                "present/default_disabled",
                "present/non_persistent",
                "present/pass",
                "present/guarded/synthetic_ready",
                "present/safe_counts_only",
                "present/safe_metadata_only",
                "present/sanitized_metadata",
            }
            else STATUS_FAIL,
            "state": statuses[name],
        }
        for name in CHECK_NAMES
    ]


def _doctor_checks_by_name(doctor_result: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    checks = doctor_result.get("checks", [])
    if not isinstance(checks, list):
        return {}
    return {
        str(check.get("name")): check
        for check in checks
        if isinstance(check, Mapping) and isinstance(check.get("name"), str)
    }


def _guard_status(
    by_name: Mapping[str, Mapping[str, Any]],
    check_name: str,
    pass_state: str,
) -> str:
    check = by_name.get(check_name, {})
    return pass_state if check.get("status") == STATUS_PASS else "present/fail"


def _failure_report(
    reason_code: str,
    *,
    contract_validation: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    result = {
        "status": STATUS_FAIL,
        "reason_code": _safe_reason_code(reason_code),
        "report_kind": REPORT_KIND,
        "no_send": True,
        "no_provider_calls": True,
        "no_source_of_truth_mutation": True,
        "scheduler_execution": "disabled",
        "checks": [],
        "guard_summary": {},
        "connector_summary": {},
        "portfolio_summary": {},
        "docs_summary": {},
        "remaining_risks": dict(REMAINING_RISKS),
        "diagnostics": {
            "check_count": 0,
            "failed_check_count": 1,
            "failed_check_names": [],
        },
    }
    if contract_validation is None:
        contract_validation = validate_readiness_report_contract(result).as_dict()
    result["contract_validation"] = dict(contract_validation)
    return result


def _safe_status(value: Any) -> str:
    return value if value in {STATUS_PASS, STATUS_FAIL} else STATUS_FAIL


def _safe_reason_or_none(value: Any) -> str | None:
    if value is None:
        return None
    return _safe_reason_code(str(value))


def _safe_int(value: Any) -> int:
    if isinstance(value, int) and value >= 0:
        return value
    return 0


def _safe_list(value: Any) -> list[str]:
    if not isinstance(value, list | tuple | set | frozenset):
        return []
    return sorted(_safe_reason_code(str(item)) for item in value)


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
    result = run_readiness_report()
    print(_json_text(result), end="")
    return REPORT_PASS_EXIT_CODE if result["status"] == STATUS_PASS else REPORT_FAIL_EXIT_CODE


if __name__ == "__main__":
    raise SystemExit(main())
