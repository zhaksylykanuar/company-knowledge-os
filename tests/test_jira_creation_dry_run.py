from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from app.services.guarded_execution_contracts import (
    validate_jira_creation_dry_run_contract,
)
from app.services.jira_creation_dry_run import (
    BLOCKED_WRITE_OPERATION_CLASSES,
    BOARD_CLASSES,
    FOLLOW_UP_CLASSES,
    GOVERNANCE_RULE_CLASSES,
    ISSUE_TYPE_CLASSES,
    MIGRATION_STEP_CLASSES,
    MODEL_PRODUCT_AREA,
    PROJECT_CLASSES,
    WORKFLOW_STATUS_CLASSES,
    jira_creation_dry_run_plan,
    jira_creation_dry_run_readiness_summary,
)
from app.services.operator_output_sanitizer import inspect_operator_output
from scripts import plan_jira_creation_dry_run as dry_run_cli

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "plan_jira_creation_dry_run.py"


def _unsafe_values() -> tuple[str, ...]:
    return (
        "https" + "://jira-creation.invalid/path",
        "operator" + "@" + "jira-creation.invalid",
        "bot_token dry run value",
        "a" * 64,
        "postgres" + "://jira-creation.invalid/db",
        "provider_payload dry run body",
        "source_object_id dry run body",
        "PROJECT" + "-123",
        "ISSUE" + "-456",
        "issue title dry run body",
        "rendered_digest_text dry run body",
        "grouped_preview_text dry run body",
        "chunk_text dry run body",
    )


def _assert_safe(value: Any) -> None:
    serialized = json.dumps(value, sort_keys=True)
    for raw_value in _unsafe_values():
        assert raw_value not in serialized
    assert inspect_operator_output(value).safe is True


def test_jira_creation_dry_run_plan_is_classes_counts_and_disabled_writes() -> None:
    plan = jira_creation_dry_run_plan()

    assert plan["report_kind"] == "jira_creation_dry_run"
    assert plan["dry_run_only"] is True
    assert plan["jira_write_operations"] == "disabled"
    assert plan["manual_approval_required"] is True
    assert plan["recommended_model_class"] == MODEL_PRODUCT_AREA
    assert plan["current_jira_assessment_class"] == "existing_projects_visible"
    assert plan["migration_recommendation_class"] == (
        "new_clean_structure_recommended"
    )
    assert plan["proposed_project_count"] == 6
    assert plan["proposed_project_classes"] == list(PROJECT_CLASSES)
    assert plan["proposed_issue_type_classes"] == list(ISSUE_TYPE_CLASSES)
    assert plan["proposed_workflow_status_classes"] == list(WORKFLOW_STATUS_CLASSES)
    assert plan["proposed_board_classes"] == list(BOARD_CLASSES)
    assert plan["proposed_governance_rule_classes"] == list(GOVERNANCE_RULE_CLASSES)
    assert plan["proposed_migration_step_classes"] == list(MIGRATION_STEP_CLASSES)
    assert plan["blocked_write_operation_classes"] == list(BLOCKED_WRITE_OPERATION_CLASSES)
    assert plan["follow_up_classes"] == list(FOLLOW_UP_CLASSES)
    assert plan["no_provider_calls"] is True
    assert plan["no_source_of_truth_mutation"] is True
    assert plan["scheduler_execution"] == "disabled"
    _assert_safe(plan)


def test_jira_creation_dry_run_structure_counts_match_operating_model() -> None:
    plan = jira_creation_dry_run_plan()
    structure = plan["proposed_structure"]

    assert structure["recommended_model_class"] == MODEL_PRODUCT_AREA
    assert structure["project_class_count"] == 6
    assert structure["component_strategy_class"] == "repo_as_component"
    assert structure["secondary_component_strategy_class"] == "service_as_component"
    assert structure["component_count_class"] == "nonzero_count"
    assert structure["issue_type_class_count"] == 8
    assert structure["workflow_status_class_count"] == 8
    assert structure["board_class_count"] == 4
    assert structure["governance_rule_count"] == 7
    assert plan["diagnostics"]["issue_search_follow_up"] == "needed"
    assert plan["diagnostics"]["manual_mapping_required_count_class"] == (
        "nonzero_count"
    )
    _assert_safe(plan)


def test_jira_creation_dry_run_cli_output_is_strict_contract_valid_json() -> None:
    result = dry_run_cli.run_jira_creation_dry_run()
    validation = validate_jira_creation_dry_run_contract(result)

    assert result["status"] == "pass"
    assert result["reason_code"] == "jira_creation_dry_run_passed"
    assert result["report_kind"] == "jira_creation_dry_run"
    assert result["dry_run_only"] is True
    assert result["no_send"] is True
    assert result["no_provider_calls"] is True
    assert result["no_source_of_truth_mutation"] is True
    assert result["scheduler_execution"] == "disabled"
    assert result["jira_write_operations"] == "disabled"
    assert result["manual_approval_required"] is True
    assert result["proposed_structure"]["project_class_count"] == 6
    assert result["proposed_structure"]["issue_type_class_count"] == 8
    assert result["proposed_structure"]["workflow_status_class_count"] == 8
    assert result["proposed_structure"]["board_class_count"] == 4
    assert result["proposed_structure"]["governance_rule_count"] == 7
    assert "issue_search_inventory_follow_up" in result["follow_up_classes"]
    assert result["contract_validation"]["validation_status"] == "pass"
    assert validation.passed is True
    _assert_safe(result)
    _assert_safe(validation.as_dict())


def test_jira_creation_dry_run_cli_script_outputs_safe_json() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--json"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        env={},
    )

    assert completed.returncode == 0
    assert completed.stderr == ""
    payload = json.loads(completed.stdout)
    assert payload["report_kind"] == "jira_creation_dry_run"
    assert payload["contract_validation"]["validation_status"] == "pass"
    assert payload["proposed_structure"]["component_count_class"] == "nonzero_count"
    _assert_safe(payload)


def test_jira_creation_dry_run_readiness_summary_is_safe() -> None:
    summary = jira_creation_dry_run_readiness_summary()

    assert summary == {
        "jira_creation_dry_run": "present",
        "jira_creation_execution": "disabled",
        "manual_approval_required": "yes",
        "jira_write_operations": "disabled",
        "recommended_model_class": "product_area_model",
        "source_of_truth_mutation": "absent",
        "scheduler_execution": "disabled",
        "current_jira_project_visibility": "confirmed",
        "issue_search_follow_up": "needed",
        "no_send": True,
        "no_provider_calls": True,
        "no_source_of_truth_mutation": True,
    }
    _assert_safe(summary)
