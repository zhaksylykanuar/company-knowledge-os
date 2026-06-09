from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.services.operator_output_sanitizer import inspect_operator_output
from app.services.repository_portfolio import repository_portfolio_public_summary

MODEL_COMPACT = "compact_model"
MODEL_PRODUCT_AREA = "product_area_model"
MODEL_PORTFOLIO_PROGRAM = "portfolio_program_model"

PROJECT_CLASSES = (
    "ssap_digital_twin",
    "kazscan_corporate",
    "infrastructure_data",
    "rd_3d_ar",
    "marketing_corporate",
    "ops_support",
)
ISSUE_TYPE_CLASSES = (
    "epic",
    "story",
    "task",
    "bug",
    "subtask",
    "incident",
    "tech_debt",
    "spike",
)
WORKFLOW_STATUS_CLASSES = (
    "backlog",
    "ready",
    "in_progress",
    "code_review",
    "validation",
    "ready_for_release",
    "done",
    "blocked",
)
COMPONENT_STRATEGY_REPO = "repo_as_component"
COMPONENT_STRATEGY_SERVICE = "service_as_component"
COMPONENT_STRATEGY_PRODUCT_AREA_GROUP = "product_area_component_group"
PRIORITY_CLASSES = (
    "p0_critical",
    "p1_high",
    "p2_normal",
    "p3_low",
    "p4_idea",
)
GOVERNANCE_RULE_CLASSES = (
    "require_component",
    "require_owner",
    "require_acceptance_criteria",
    "require_blocker_reason",
    "done_requires_validation",
    "bugs_require_reproduction_context",
    "incidents_require_impact_resolution",
)

SOURCE_OF_TRUTH_MUTATION_ABSENT = "absent"
SCHEDULER_EXECUTION_DISABLED = "disabled"


def jira_operating_model_summary() -> dict[str, Any]:
    portfolio_summary = repository_portfolio_public_summary()
    portfolio_area_count = int(portfolio_summary["product_area_count"])
    summary = {
        "recommended_model_class": recommended_model_class(portfolio_area_count),
        "model_option_count": 3,
        "portfolio_area_count": portfolio_area_count,
        "recommended_project_class_count": len(PROJECT_CLASSES),
        "recommended_issue_type_class_count": len(ISSUE_TYPE_CLASSES),
        "recommended_workflow_status_class_count": len(WORKFLOW_STATUS_CLASSES),
        "repo_component_strategy": COMPONENT_STRATEGY_REPO,
        "component_strategy_option_count": 3,
        "recommended_priority_class_count": len(PRIORITY_CLASSES),
        "governance_rule_count": len(GOVERNANCE_RULE_CLASSES),
        "jira_write_operations": "disabled",
        "source_of_truth_mutation": SOURCE_OF_TRUTH_MUTATION_ABSENT,
        "no_send": True,
        "no_source_of_truth_mutation": True,
        "scheduler_execution": SCHEDULER_EXECUTION_DISABLED,
    }
    _assert_safe(summary)
    return summary


def recommended_model_class(portfolio_area_count: int) -> str:
    if portfolio_area_count <= 2:
        return MODEL_COMPACT
    if portfolio_area_count <= 10:
        return MODEL_PRODUCT_AREA
    return MODEL_PORTFOLIO_PROGRAM


def _assert_safe(value: Mapping[str, Any]) -> None:
    if inspect_operator_output(value).safe is not True:
        raise ValueError("jira_operating_model_unsafe")
