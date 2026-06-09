from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.services.atlassian_api_profiles import (
    PROFILE_ATLASSIAN_ADMIN_SCOPED,
    PROFILE_JIRA_WRITE,
    atlassian_api_profile_summary,
)
from app.services.jira_creation_dry_run import jira_creation_dry_run_plan
from app.services.operator_output_sanitizer import inspect_operator_output

REPORT_KIND = "jira_write_readiness"
STATUS_PASS = "pass"
STATUS_FAIL = "fail"
WRITE_EXECUTION_DISABLED = "disabled"
SCHEDULER_EXECUTION_DISABLED = "disabled"
NEXT_APPROVAL_CLASS = "approve_jira_write_execution_prompt"
READINESS_PASSED = "jira_write_readiness_passed"

REQUIRED_PROFILE_CLASSES = (
    PROFILE_JIRA_WRITE,
    PROFILE_ATLASSIAN_ADMIN_SCOPED,
)
BLOCKED_WRITE_OPERATION_CLASSES = (
    "create_jira_project",
    "create_jira_component",
    "create_jira_board",
    "configure_jira_workflow",
    "configure_jira_issue_type",
)


def jira_write_readiness_plan(
    *,
    environ: Mapping[str, str],
) -> dict[str, Any]:
    profiles = atlassian_api_profile_summary(environ=environ)
    creation_plan = jira_creation_dry_run_plan()
    required_profile_statuses = [
        profiles["profiles"][profile_class]["profile_status"]
        for profile_class in REQUIRED_PROFILE_CLASSES
    ]
    configured_count = sum(1 for status in required_profile_statuses if status == "configured")
    missing_count = len(REQUIRED_PROFILE_CLASSES) - configured_count
    result = {
        "report_kind": REPORT_KIND,
        "write_execution_status": WRITE_EXECUTION_DISABLED,
        "dry_run_only": True,
        "manual_approval_required": True,
        "required_profile_classes": list(REQUIRED_PROFILE_CLASSES),
        "configured_profile_count_class": _zero_nonzero_count_class(configured_count),
        "missing_profile_count_class": _zero_nonzero_count_class(missing_count),
        "blocked_write_operation_classes": list(BLOCKED_WRITE_OPERATION_CLASSES),
        "next_approval_class": NEXT_APPROVAL_CLASS,
        "creation_dry_run_status": "present",
        "credential_profiles": profiles,
        "no_send": True,
        "no_provider_calls": True,
        "no_source_of_truth_mutation": True,
        "scheduler_execution": SCHEDULER_EXECUTION_DISABLED,
        "diagnostics": {
            "required_profile_count": len(REQUIRED_PROFILE_CLASSES),
            "creation_project_class_count": creation_plan["proposed_project_count"],
            "creation_component_count_class": creation_plan[
                "proposed_component_count_class"
            ],
            "write_operations": WRITE_EXECUTION_DISABLED,
            "admin_live_calls": profiles["admin_live_calls"],
            "manual_approval_required": "yes",
        },
    }
    _assert_safe(result)
    return result


def jira_write_readiness_readiness_summary(
    *,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    profiles = atlassian_api_profile_summary(environ=environ or {})
    summary = {
        "atlassian_api_profiles": "present",
        "jira_readonly_profile": profiles["jira_readonly_profile_status"],
        "jira_write_profile": profiles["jira_write_profile_status"],
        "atlassian_admin_profiles_configured_count_class": profiles[
            "configured_profile_count_class"
        ],
        "atlassian_admin_profiles_missing_count_class": profiles[
            "missing_profile_count_class"
        ],
        "jira_write_readiness": "dry_run_only",
        "jira_creation_execution": WRITE_EXECUTION_DISABLED,
        "admin_api_live_calls": "disabled",
        "manual_approval_required": "yes",
        "write_execution_status": WRITE_EXECUTION_DISABLED,
        "no_send": True,
        "no_provider_calls": True,
        "no_source_of_truth_mutation": True,
        "scheduler_execution": SCHEDULER_EXECUTION_DISABLED,
    }
    _assert_safe(summary)
    return summary


def _zero_nonzero_count_class(count: int) -> str:
    return "zero_count" if count == 0 else "nonzero_count"


def _assert_safe(value: Mapping[str, Any]) -> None:
    if inspect_operator_output(value).safe is not True:
        raise ValueError("jira_write_readiness_unsafe")
