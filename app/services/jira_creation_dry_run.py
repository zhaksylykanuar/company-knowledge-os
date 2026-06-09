from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.services.jira_operating_model import (
    COMPONENT_STRATEGY_REPO,
    COMPONENT_STRATEGY_SERVICE,
    GOVERNANCE_RULE_CLASSES,
    ISSUE_TYPE_CLASSES,
    MODEL_PRODUCT_AREA,
    PROJECT_CLASSES,
    WORKFLOW_STATUS_CLASSES,
    jira_operating_model_summary,
)
from app.services.jira_portfolio_mapping import (
    JIRA_INVENTORY_STATUS_LIVE_READONLY_VERIFIED,
    MAPPING_STATUS_LIVE_READONLY_OBSERVED,
    jira_portfolio_mapping_summary,
)
from app.services.operator_output_sanitizer import inspect_operator_output
from app.services.repository_portfolio import repository_portfolio_public_summary

REPORT_KIND = "jira_creation_dry_run"
STATUS_PASS = "pass"
STATUS_FAIL = "fail"
SCHEDULER_EXECUTION_DISABLED = "disabled"
JIRA_WRITE_OPERATIONS_DISABLED = "disabled"
SOURCE_OF_TRUTH_MUTATION_ABSENT = "absent"

CURRENT_JIRA_EXISTING_PROJECTS_VISIBLE = "existing_projects_visible"
MIGRATION_NEW_CLEAN_STRUCTURE_RECOMMENDED = "new_clean_structure_recommended"
NEXT_STEP_REVIEW_AND_APPROVE = "review_and_approve_creation_plan"
NEXT_MANUAL_APPROVAL_WRITE_PLAN = "jira_creation_write_plan_approval"

COMPONENT_COUNT_ZERO = "zero_count"
COMPONENT_COUNT_NONZERO = "nonzero_count"

BOARD_CLASSES = (
    "product_roadmap_board",
    "engineering_sprint_board",
    "support_bugs_kanban",
    "infrastructure_ops_kanban",
)
MIGRATION_STEP_CLASSES = (
    "approve_new_jira_structure",
    "create_project_area_model",
    "create_components_from_repo_portfolio",
    "configure_issue_types",
    "configure_workflows",
    "create_boards",
    "map_existing_open_work",
    "migrate_open_work_only_first",
    "keep_old_jira_readonly_during_transition",
    "validate_with_team",
    "enable_reports_after_mapping",
    "defer_automation_until_after_manual_approval",
)
BLOCKED_WRITE_OPERATION_CLASSES = (
    "create_jira_projects_blocked",
    "create_jira_components_blocked",
    "create_issue_types_blocked",
    "create_workflows_blocked",
    "create_boards_blocked",
    "create_fields_blocked",
    "migrate_issues_blocked",
)
FOLLOW_UP_CLASSES = (
    "issue_search_inventory_follow_up",
    "current_jira_project_visibility_confirmed",
    "creation_requires_write_approval",
    "migration_requires_manual_mapping",
)


def jira_creation_dry_run_plan() -> dict[str, Any]:
    portfolio_summary = repository_portfolio_public_summary()
    operating_model = jira_operating_model_summary()
    mapping = jira_portfolio_mapping_summary(
        jira_inventory_status=JIRA_INVENTORY_STATUS_LIVE_READONLY_VERIFIED,
        mapping_status=MAPPING_STATUS_LIVE_READONLY_OBSERVED,
    )
    repo_total_count = int(portfolio_summary["repo_total_count"])
    component_count_class = _zero_nonzero_count_class(repo_total_count)
    proposed_structure = {
        "recommended_model_class": MODEL_PRODUCT_AREA,
        "project_class_count": len(PROJECT_CLASSES),
        "component_strategy_class": COMPONENT_STRATEGY_REPO,
        "secondary_component_strategy_class": COMPONENT_STRATEGY_SERVICE,
        "component_count_class": component_count_class,
        "issue_type_class_count": len(ISSUE_TYPE_CLASSES),
        "workflow_status_class_count": len(WORKFLOW_STATUS_CLASSES),
        "board_class_count": len(BOARD_CLASSES),
        "governance_rule_count": len(GOVERNANCE_RULE_CLASSES),
    }
    result = {
        "report_kind": REPORT_KIND,
        "dry_run_only": True,
        "jira_write_operations": JIRA_WRITE_OPERATIONS_DISABLED,
        "manual_approval_required": True,
        "recommended_model_class": MODEL_PRODUCT_AREA,
        "current_jira_assessment_class": CURRENT_JIRA_EXISTING_PROJECTS_VISIBLE,
        "migration_recommendation_class": MIGRATION_NEW_CLEAN_STRUCTURE_RECOMMENDED,
        "proposed_structure": proposed_structure,
        "proposed_project_classes": list(PROJECT_CLASSES),
        "proposed_project_count": len(PROJECT_CLASSES),
        "proposed_component_strategy_class": COMPONENT_STRATEGY_REPO,
        "proposed_component_count_class": component_count_class,
        "proposed_issue_type_classes": list(ISSUE_TYPE_CLASSES),
        "proposed_workflow_status_classes": list(WORKFLOW_STATUS_CLASSES),
        "proposed_board_classes": list(BOARD_CLASSES),
        "proposed_governance_rule_classes": list(GOVERNANCE_RULE_CLASSES),
        "proposed_migration_step_classes": list(MIGRATION_STEP_CLASSES),
        "blocked_write_operation_classes": list(BLOCKED_WRITE_OPERATION_CLASSES),
        "follow_up_classes": list(FOLLOW_UP_CLASSES),
        "next_manual_approval_class": NEXT_MANUAL_APPROVAL_WRITE_PLAN,
        "source_of_truth_mutation": SOURCE_OF_TRUTH_MUTATION_ABSENT,
        "no_send": True,
        "no_provider_calls": True,
        "no_source_of_truth_mutation": True,
        "scheduler_execution": SCHEDULER_EXECUTION_DISABLED,
        "diagnostics": {
            "portfolio_area_count": portfolio_summary["product_area_count"],
            "portfolio_repo_count_class": component_count_class,
            "mapping_readiness_status": mapping["mapping_readiness_status"],
            "manual_mapping_required_count_class": mapping[
                "manual_mapping_required_count_class"
            ],
            "operating_model_project_class_count": operating_model[
                "recommended_project_class_count"
            ],
            "issue_search_follow_up": "needed",
            "jira_creation_execution": JIRA_WRITE_OPERATIONS_DISABLED,
        },
    }
    _assert_safe(result)
    return result


def jira_creation_dry_run_readiness_summary() -> dict[str, Any]:
    summary = {
        "jira_creation_dry_run": "present",
        "jira_creation_execution": JIRA_WRITE_OPERATIONS_DISABLED,
        "manual_approval_required": "yes",
        "jira_write_operations": JIRA_WRITE_OPERATIONS_DISABLED,
        "recommended_model_class": MODEL_PRODUCT_AREA,
        "source_of_truth_mutation": SOURCE_OF_TRUTH_MUTATION_ABSENT,
        "scheduler_execution": SCHEDULER_EXECUTION_DISABLED,
        "current_jira_project_visibility": "confirmed",
        "issue_search_follow_up": "needed",
        "no_send": True,
        "no_provider_calls": True,
        "no_source_of_truth_mutation": True,
    }
    _assert_safe(summary)
    return summary


def _zero_nonzero_count_class(count: int) -> str:
    return COMPONENT_COUNT_ZERO if count == 0 else COMPONENT_COUNT_NONZERO


def _assert_safe(value: Mapping[str, Any]) -> None:
    if inspect_operator_output(value).safe is not True:
        raise ValueError("jira_creation_dry_run_unsafe")
