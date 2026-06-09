from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from app.services.operator_output_sanitizer import inspect_operator_output
from scripts import report_guarded_execution_readiness as readiness

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "report_guarded_execution_readiness.py"


def _unsafe_values() -> tuple[str, ...]:
    return (
        "https" + "://readiness.invalid/path",
        "operator" + "@" + "readiness.invalid",
        "bot_token readiness value",
        "a" * 64,
        "postgres" + "://readiness.invalid/db",
        "provider_payload readiness body",
        "source_object_id readiness body",
        "rendered_digest_text readiness body",
        "grouped_preview_text readiness body",
        "chunk_text readiness body",
        "item_title readiness body",
    )


def _assert_no_raw_unsafe_values(value: Any) -> None:
    serialized = json.dumps(value, sort_keys=True)
    for raw_value in _unsafe_values():
        assert raw_value not in serialized


def test_guarded_execution_readiness_report_passes_synthetic_run() -> None:
    result = readiness.run_readiness_report()

    assert result["status"] == "pass"
    assert result["reason_code"] is None
    assert result["report_kind"] == "guarded_execution_readiness"
    assert result["no_send"] is True
    assert result["no_provider_calls"] is True
    assert result["no_source_of_truth_mutation"] is True
    assert result["scheduler_execution"] == "disabled"
    assert result["contract_validation"]["validation_status"] == "pass"
    assert result["contract_validation"]["reason_code"] == "contract_validation_passed"
    assert {check["name"] for check in result["checks"]} == {
        "audit_sink",
        "connector_smoke_cli",
        "core_docs_references",
        "external_connector_config_doctor",
        "external_connector_registry",
        "github_connector",
        "github_org_current_repo_count_class",
        "github_org_live_inventory_status",
        "github_org_migration_status",
        "github_repo_edit_operations",
        "github_repo_transfer_operations",
        "github_target_org_key",
        "github_target_owner_class",
        "github_write_operations",
        "guarded_execution_audit",
        "guarded_execution_doctor",
        "guarded_operations_runbook",
        "jira_connector",
        "jira_creation_dry_run",
        "jira_creation_execution",
        "jira_inventory_diagnostics",
        "current_jira_project_visibility",
        "issue_search_follow_up",
        "jira_mapping_readiness",
        "jira_operating_model",
        "jira_portfolio_mapping",
        "jira_readonly_inventory_cli",
        "jira_write_operations",
        "atlassian_api_profiles",
        "jira_readonly_profile",
        "jira_write_profile",
        "atlassian_admin_profiles",
        "jira_write_readiness",
        "admin_api_live_calls",
        "manual_approval_required",
        "operator_output_sanitizer",
        "repository_portfolio_catalog",
        "repository_portfolio_seed",
        "production_operation_guard",
        "provider_execution_guard",
        "scheduler_execution_guard",
    }
    assert all(check["status"] == "pass" for check in result["checks"])
    _assert_no_raw_unsafe_values(result)
    assert inspect_operator_output(result).safe is True


def test_guarded_execution_readiness_report_confirms_safe_guard_summary() -> None:
    result = readiness.run_readiness_report()

    assert result["guard_summary"] == {
        "audit_sink": "present/non_persistent",
        "guarded_execution_audit": "present/sanitized_metadata",
        "guarded_execution_doctor": "present/pass",
        "operator_output_sanitizer": "present/safe_counts_only",
        "production_operation_guard": "present/default_denied",
        "provider_execution_guard": "present/default_denied",
        "scheduler_execution_guard": "present/default_disabled",
    }
    assert result["diagnostics"]["doctor"]["audit_sink_event_count"] == 5
    assert result["diagnostics"]["doctor"]["failed_check_count"] == 0
    assert result["diagnostics"]["doctor"]["unsafe_pattern_count"] == 0
    assert result["connector_summary"]["registry"] == "present/safe_metadata_only"
    assert result["connector_summary"]["github_connector"] == (
        "present/guarded/synthetic_ready"
    )
    assert result["connector_summary"]["jira_connector"] == (
        "present/guarded/synthetic_ready"
    )
    assert result["connector_summary"]["live_calls"] == "default_denied"
    assert result["connector_summary"]["source_of_truth_mutation"] == "absent"
    assert result["connector_summary"]["scheduler_execution"] == "disabled"
    assert result["connector_summary"]["payload_leakage"] == "absent"
    assert result["connector_summary"]["repository_portfolio"] == (
        "present/safe_counts_only"
    )
    assert result["connector_summary"]["github_target_owner_class"] == (
        "github_organization"
    )
    assert result["connector_summary"]["github_target_org_key"] == "qtwin-io"
    assert result["connector_summary"]["github_legacy_seed_status"] == "present"
    assert result["connector_summary"]["github_org_migration_status"] == (
        "manual_org_migration_planned"
    )
    assert result["connector_summary"]["github_org_live_inventory_status"] == (
        "gated_not_verified"
    )
    assert result["connector_summary"]["github_write_operations"] == "disabled"
    assert result["connector_summary"]["github_repo_transfer_operations"] == (
        "disabled"
    )
    assert result["connector_summary"]["github_repo_edit_operations"] == "disabled"
    assert result["connector_smoke_summary"] == {
        "connector_smoke_cli": "present",
        "github_live_readonly_smoke": "gated",
        "jira_live_readonly_smoke": "gated",
        "no_send": True,
        "no_source_of_truth_mutation": True,
        "portfolio_compare": "counts_only",
        "scheduler_execution": "disabled",
    }
    assert result["jira_inventory_summary"] == {
        "jira_inventory_cli": "present",
        "jira_inventory_live_readonly": "gated",
        "jira_inventory_diagnostics": "present",
        "jira_portfolio_mapping": "synthetic_ready",
        "jira_mapping_readiness": "planned_or_observed",
        "jira_operating_model": "present",
        "jira_creation_dry_run": "present",
        "jira_creation_execution": "disabled",
        "manual_approval_required": "yes",
        "current_jira_project_visibility": "confirmed",
        "issue_search_follow_up": "needed",
        "atlassian_api_profiles": "present",
        "jira_readonly_profile": "not_configured",
        "jira_write_profile": "not_configured",
        "atlassian_admin_profiles_configured_count_class": "zero_count",
        "atlassian_admin_profiles_missing_count_class": "nonzero_count",
        "jira_write_readiness": "dry_run_only",
        "admin_api_live_calls": "disabled",
        "write_execution_status": "disabled",
        "jira_write_operations": "disabled",
        "recommended_model_class": "product_area_model",
        "source_of_truth_mutation": "absent",
        "no_send": True,
        "no_provider_calls": True,
        "no_source_of_truth_mutation": True,
        "scheduler_execution": "disabled",
    }
    config_summary = result["external_connector_config_summary"]
    assert config_summary["external_connector_config_doctor"] == "present"
    assert config_summary["github_config_status"] in {
        "configured",
        "not_configured",
        "partially_configured",
    }
    assert config_summary["jira_config_status"] in {
        "configured",
        "not_configured",
        "partially_configured",
    }
    assert config_summary["github_live_readonly_ready"] in {"ready", "not_ready"}
    assert config_summary["jira_live_readonly_ready"] in {"ready", "not_ready"}
    assert config_summary["no_live_calls"] == "absent"
    assert config_summary["no_send"] is True
    assert config_summary["no_source_of_truth_mutation"] is True
    assert config_summary["scheduler_execution"] == "disabled"
    assert result["portfolio_summary"]["portfolio_catalog"] == "present/safe_counts_only"
    assert result["portfolio_summary"]["seed_source_class"] == (
        "legacy_personal_account_seed"
    )
    assert result["portfolio_summary"]["seed_portfolio_status"] == "present"
    assert result["portfolio_summary"]["repo_total_count"] == 19
    assert result["portfolio_summary"]["product_area_count"] == 7
    assert result["portfolio_summary"]["target_owner_class"] == "github_organization"
    assert result["portfolio_summary"]["target_org_key"] == "qtwin-io"
    assert result["portfolio_summary"]["migration_status_class"] == (
        "manual_org_migration_planned"
    )
    assert result["portfolio_summary"]["target_org_current_repo_count_class"] == (
        "one_repo_reported_by_operator"
    )
    assert result["portfolio_summary"]["target_expected_migration_count"] == 19
    assert result["portfolio_summary"]["target_remaining_migration_count_class"] == (
        "nonzero_count"
    )
    assert result["portfolio_summary"]["github_repo_transfer_operations"] == "disabled"
    assert result["portfolio_summary"]["github_repo_edit_operations"] == "disabled"
    assert result["portfolio_summary"]["github_write_operations"] == "disabled"
    assert result["portfolio_summary"]["github_live_inventory_status"] == (
        "gated_not_verified"
    )
    assert result["portfolio_summary"]["jira_mapping_status"] == (
        "planned_not_verified"
    )
    assert result["portfolio_summary"]["action_class_counts"][
        "secret_rotation_required"
    ] == 1


def test_guarded_execution_readiness_report_reports_remaining_risks_as_classes() -> None:
    result = readiness.run_readiness_report()

    assert result["remaining_risks"] == {
        "live_provider_execution": "gated_only",
        "persistent_audit_logging": "not_implemented",
        "production_db_migrations": "out_of_scope",
        "production_deploy_ops": "not_implemented",
        "scheduler_outbox_execution": "intentionally_disabled",
    }
    _assert_no_raw_unsafe_values(result["remaining_risks"])


def test_guarded_execution_readiness_report_docs_summary_is_safe() -> None:
    result = readiness.run_readiness_report()

    assert result["docs_summary"]["guarded_operations_runbook"] == "present"
    assert result["docs_summary"]["core_docs_references"] == "present"
    assert result["docs_summary"]["reference_count"] == 4
    assert set(result["docs_summary"]["reference_labels"]) == {
        "attention_feature",
        "data_model",
        "guarded_operations_runbook",
        "telegram_digest_feature",
    }
    _assert_no_raw_unsafe_values(result["docs_summary"])


def test_guarded_execution_readiness_report_cli_outputs_strict_json() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert completed.stderr == ""
    payload = json.loads(completed.stdout)
    assert payload["status"] == "pass"
    assert payload["report_kind"] == "guarded_execution_readiness"
    assert payload["contract_validation"]["validation_status"] == "pass"
    assert payload["diagnostics"]["failed_check_count"] == 0
    _assert_no_raw_unsafe_values(payload)
    assert inspect_operator_output(payload).safe is True


def test_guarded_execution_readiness_report_failure_mode_is_sanitized() -> None:
    def failing_doctor_runner() -> dict[str, Any]:
        raise RuntimeError("unsafe " + _unsafe_values()[0])

    result = readiness.run_readiness_report(doctor_runner=failing_doctor_runner)

    assert result["status"] == "fail"
    assert result["reason_code"] == "guarded_execution_readiness_exception"
    assert result["checks"] == []
    assert result["no_send"] is True
    assert result["no_provider_calls"] is True
    assert result["no_source_of_truth_mutation"] is True
    assert result["scheduler_execution"] == "disabled"
    assert result["contract_validation"]["validation_status"] == "pass"
    assert result["connector_summary"] == {}
    assert result["external_connector_config_summary"] == {}
    assert result["connector_smoke_summary"] == {}
    assert result["jira_inventory_summary"] == {}
    assert result["portfolio_summary"] == {}
    _assert_no_raw_unsafe_values(result)
    assert inspect_operator_output(result).safe is True


def test_guarded_execution_readiness_report_missing_docs_fails_safely(
    tmp_path: Path,
) -> None:
    result = readiness.run_readiness_report(docs_root=tmp_path)

    assert result["status"] == "fail"
    assert result["reason_code"] == "guarded_execution_readiness_failed"
    assert result["docs_summary"]["guarded_operations_runbook"] == "missing"
    assert result["docs_summary"]["core_docs_references"] == "missing"
    assert result["diagnostics"]["failed_check_count"] == 2
    assert result["contract_validation"]["validation_status"] == "pass"
    _assert_no_raw_unsafe_values(result)
    assert inspect_operator_output(result).safe is True


def test_guarded_execution_readiness_report_does_not_import_live_provider_clients() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    blocked_import_markers = (
        "app.connectors",
        "app.agents.llm_runner",
        "get_openai_client",
        "googleapiclient",
        "OpenAI(",
        "send_telegram_plain_text",
        "AsyncSessionLocal",
    )
    for marker in blocked_import_markers:
        assert marker not in source
