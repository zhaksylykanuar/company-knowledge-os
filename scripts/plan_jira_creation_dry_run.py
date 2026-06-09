#!/usr/bin/env python
"""Sanitized Jira creation dry-run plan."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.services.guarded_execution_contracts import (  # noqa: E402
    validate_jira_creation_dry_run_contract,
)
from app.services.jira_creation_dry_run import (  # noqa: E402
    NEXT_STEP_REVIEW_AND_APPROVE,
    REPORT_KIND,
    STATUS_FAIL,
    STATUS_PASS,
    jira_creation_dry_run_plan,
)
from app.services.operator_output_sanitizer import inspect_operator_output  # noqa: E402

DRY_RUN_PASSED = "jira_creation_dry_run_passed"
DRY_RUN_OUTPUT_UNSAFE = "jira_creation_dry_run_output_unsafe"
DRY_RUN_CONTRACT_INVALID = "jira_creation_dry_run_contract_invalid"
SCHEDULER_EXECUTION_DISABLED = "disabled"


def run_jira_creation_dry_run(
    *,
    include_safe_detail_classes: bool = False,
    compact: bool = False,
) -> dict[str, Any]:
    plan = jira_creation_dry_run_plan()
    result = {
        "status": STATUS_PASS,
        "reason_code": DRY_RUN_PASSED,
        "report_kind": REPORT_KIND,
        "dry_run_only": True,
        "no_send": True,
        "no_provider_calls": True,
        "no_source_of_truth_mutation": True,
        "scheduler_execution": SCHEDULER_EXECUTION_DISABLED,
        "jira_write_operations": "disabled",
        "manual_approval_required": True,
        "current_jira_assessment_class": plan["current_jira_assessment_class"],
        "migration_recommendation_class": plan["migration_recommendation_class"],
        "proposed_structure": dict(plan["proposed_structure"]),
        "proposed_project_classes": list(plan["proposed_project_classes"]),
        "proposed_issue_type_classes": list(plan["proposed_issue_type_classes"]),
        "proposed_workflow_status_classes": list(
            plan["proposed_workflow_status_classes"]
        ),
        "proposed_board_classes": list(plan["proposed_board_classes"]),
        "governance_rule_classes": list(plan["proposed_governance_rule_classes"]),
        "migration_step_classes": list(plan["proposed_migration_step_classes"]),
        "blocked_write_operation_classes": list(plan["blocked_write_operation_classes"]),
        "follow_up_classes": list(plan["follow_up_classes"]),
        "next_step_class": NEXT_STEP_REVIEW_AND_APPROVE,
        "diagnostics": {
            "include_safe_detail_classes": include_safe_detail_classes,
            "compact": compact,
            **dict(plan["diagnostics"]),
        },
    }
    if compact:
        result["diagnostics"]["detail_visibility"] = "counts_only"
    return _finalize_result(result)


def _finalize_result(result: dict[str, Any]) -> dict[str, Any]:
    safety = inspect_operator_output(result)
    if not safety.safe:
        return _failure_report(
            DRY_RUN_OUTPUT_UNSAFE,
            operator_output_safety=safety.as_dict(),
        )
    validation = validate_jira_creation_dry_run_contract(result).as_dict()
    result["contract_validation"] = validation
    if validation["validation_status"] != STATUS_PASS:
        return _failure_report(
            DRY_RUN_CONTRACT_INVALID,
            contract_validation=validation,
        )
    return result


def _failure_report(
    reason_code: str,
    *,
    contract_validation: Mapping[str, Any] | None = None,
    operator_output_safety: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    result = {
        "status": STATUS_FAIL,
        "reason_code": _safe_reason_code(reason_code),
        "report_kind": REPORT_KIND,
        "dry_run_only": True,
        "no_send": True,
        "no_provider_calls": True,
        "no_source_of_truth_mutation": True,
        "scheduler_execution": SCHEDULER_EXECUTION_DISABLED,
        "jira_write_operations": "disabled",
        "manual_approval_required": True,
        "current_jira_assessment_class": "unknown",
        "migration_recommendation_class": "manual_review_required",
        "proposed_structure": {},
        "proposed_project_classes": [],
        "proposed_issue_type_classes": [],
        "proposed_workflow_status_classes": [],
        "proposed_board_classes": [],
        "governance_rule_classes": [],
        "migration_step_classes": [],
        "blocked_write_operation_classes": [],
        "follow_up_classes": [],
        "next_step_class": "review_contract_failure",
        "diagnostics": {
            "operator_output_safety": dict(operator_output_safety or {}),
        },
    }
    result["contract_validation"] = dict(
        contract_validation
        or validate_jira_creation_dry_run_contract(result).as_dict()
    )
    return result


def _safe_reason_code(value: str) -> str:
    cleaned = "".join(
        character if character.isalnum() or character == "_" else "_"
        for character in value.casefold()
    ).strip("_")
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned or "jira_creation_dry_run_failed"


def _json_text(value: Mapping[str, Any]) -> str:
    return json.dumps(dict(value), indent=2, sort_keys=True) + "\n"


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output strict JSON. This is the default and only output mode.",
    )
    parser.add_argument("--include-safe-detail-classes", action="store_true")
    parser.add_argument("--compact", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    result = run_jira_creation_dry_run(
        include_safe_detail_classes=args.include_safe_detail_classes,
        compact=args.compact,
    )
    print(_json_text(result), end="")
    return 0 if result["status"] == STATUS_PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
