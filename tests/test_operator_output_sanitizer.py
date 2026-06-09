from __future__ import annotations

import json
from typing import Any

import pytest

from app.services.operator_output_sanitizer import (
    assert_operator_output_safe,
    inspect_operator_output,
)
from app.services.production_operation_guard import require_production_operation_ack
from app.services.provider_execution_guard import require_live_provider_execution_ack
from app.services.scheduler_execution_guard import (
    OUTBOX_DRAIN,
    require_no_scheduler_execution,
)
from scripts import manual_no_marker_grouped_lifecycle_review as manual_script
from scripts import send_test_telegram_delivery_intention as send_script


def _unsafe_values() -> dict[str, str]:
    return {
        "url": "https" + "://unsafe.invalid/path",
        "email": "operator" + "@" + "unsafe.invalid",
        "token": "bot_token unsafe-token-value",
        "hash": "a" * 64,
        "db": "postgres" + "://unsafe-connection",
        "payload": "provider_payload unsafe body",
        "rendered": "rendered_digest_text unsafe body",
        "preview": "grouped_preview_text unsafe body",
        "chunk": "chunk_text unsafe body",
        "item": "item_title unsafe body",
        "source": "source_object_id unsafe body",
    }


def _assert_raw_values_absent(diagnostics: dict[str, Any]) -> None:
    serialized = json.dumps(diagnostics, sort_keys=True)
    for raw_value in _unsafe_values().values():
        assert raw_value not in serialized


def test_operator_output_sanitizer_reports_classes_and_counts_without_raw_values() -> None:
    unsafe = _unsafe_values()
    diagnostics = inspect_operator_output(
        {
            "safe_reason_code": "blocked",
            "contact": unsafe["email"],
            "database": unsafe["db"],
            "digest": unsafe["rendered"],
            "grouped_preview_text": unsafe["preview"],
            "item_title": unsafe["item"],
            "provider_payload": {"body": unsafe["payload"]},
            "sha256": unsafe["hash"],
            "source_object_id": unsafe["source"],
            "token_field": unsafe["token"],
            "url_field": unsafe["url"],
            "chunk_text": unsafe["chunk"],
        }
    ).as_dict()

    assert diagnostics["safe"] is False
    assert diagnostics["unsafe_pattern_count"] > 0
    assert diagnostics["raw_hash_shaped_value_count"] >= 1
    assert diagnostics["url_like_value_count"] >= 2
    assert diagnostics["email_like_value_count"] >= 1
    assert diagnostics["secret_like_value_count"] >= 1
    assert diagnostics["payload_like_value_count"] >= 1
    assert diagnostics["unsafe_json_flag_count"] >= 1
    assert set(diagnostics["unsafe_pattern_classes"]) >= {
        "database_connection_like",
        "email_like_value",
        "raw_hash_shaped_value",
        "payload_like_value",
        "rendered_text_like",
        "secret_like_value",
        "url_like_value",
    }
    _assert_raw_values_absent(diagnostics)


def test_operator_output_sanitizer_allows_safe_synthetic_summary() -> None:
    diagnostics = assert_operator_output_safe(
        {
            "status": "blocked",
            "reason_code": "provider_execution_default_denied",
            "safe_counts": {
                "unsafe_pattern_count": 0,
                "validated_artifact_count": 1,
            },
        }
    )

    assert diagnostics.safe is True
    assert diagnostics.unsafe_pattern_count == 0


def test_operator_output_sanitizer_detects_raw_guarded_execution_payload_markers() -> None:
    diagnostics = inspect_operator_output(
        {
            "raw_audit_json": "synthetic marker",
            "raw_config_doctor_json": "synthetic marker",
            "raw_contract_validation_payload": "synthetic marker",
            "raw_doctor_json": "synthetic marker",
            "raw_readiness_json": "synthetic marker",
            "raw_sink_contents": "synthetic marker",
            "raw_smoke_json": "synthetic marker",
        }
    ).as_dict()

    assert diagnostics["safe"] is False
    assert diagnostics["unsafe_json_flag_count"] == 7
    assert diagnostics["unsafe_pattern_classes"] == [
        "raw_guarded_execution_payload_like"
    ]
    _assert_raw_values_absent(diagnostics)


def test_operator_output_sanitizer_allows_safe_secret_rotation_action_class() -> None:
    diagnostics = inspect_operator_output(
        {
            "action_class_counts": {
                "secret_rotation_required": 1,
            }
        }
    ).as_dict()

    assert diagnostics["safe"] is True
    assert diagnostics["secret_like_value_count"] == 0
    assert diagnostics["unsafe_pattern_count"] == 0


def test_operator_output_sanitizer_allows_expected_connector_env_names() -> None:
    diagnostics = inspect_operator_output(
        {
            "required_environment_variables": [
                "FOS_GITHUB_READONLY_TOKEN",
                "FOS_GITHUB_READONLY_ACCOUNT",
                "FOS_GITHUB_TARGET_ORG",
                "FOS_JIRA_READONLY_SITE",
                "FOS_JIRA_READONLY_USER",
                "FOS_JIRA_READONLY_TOKEN",
                "FOS_OPENAI_API_KEY",
                "FOS_TELEGRAM_BOT_TOKEN",
                "FOS_TELEGRAM_CHAT_ID",
                "FOS_SLACK_BOT_TOKEN",
                "FOS_SLACK_CHANNEL_ID",
                "FOS_GMAIL_READONLY_CLIENT_ID",
                "FOS_GMAIL_READONLY_CLIENT_SECRET",
                "FOS_GOOGLE_DRIVE_READONLY_CLIENT_ID",
                "FOS_GOOGLE_DRIVE_READONLY_CLIENT_SECRET",
            ]
        }
    ).as_dict()

    assert diagnostics["safe"] is True
    assert diagnostics["secret_like_value_count"] == 0
    assert diagnostics["unsafe_pattern_count"] == 0


def test_operator_output_sanitizer_allows_cleanup_planner_classes() -> None:
    diagnostics = inspect_operator_output(
        {
            "class_counts": {
                "env_secret_file": 1,
                "cache_directory": 1,
                "python_cache": 1,
                "node_modules": 1,
                "build_output": 1,
                "test_artifact": 1,
                "temp_artifact": 1,
                "log_file": 1,
                "local_database": 1,
                "raw_source_of_truth_store": 1,
                "obsidian_vault_store": 1,
                "unknown_ignored": 1,
            },
            "action_class_counts": {
                "keep_local_secret": 1,
                "safe_to_delete_candidate": 1,
                "review_before_delete": 1,
                "keep_cache": 1,
                "ignore_rule_review": 1,
                "source_of_truth_do_not_touch": 1,
            },
        }
    ).as_dict()

    assert diagnostics["safe"] is True
    assert diagnostics["secret_like_value_count"] == 0
    assert diagnostics["unsafe_pattern_count"] == 0


def test_operator_output_sanitizer_allows_jira_live_smoke_safe_fields() -> None:
    diagnostics = inspect_operator_output(
        {
            "live_failure_class": "jira_auth_failed",
            "auth_status_class": "jira_auth_failed",
            "transport_status_class": "jira_transport_http_error",
            "response_contract_status": "not_observed",
            "provider_payload_visibility": "suppressed",
        }
    ).as_dict()

    assert diagnostics["safe"] is True
    assert diagnostics["payload_like_value_count"] == 0
    assert diagnostics["unsafe_pattern_count"] == 0


def test_operator_output_sanitizer_allows_jira_inventory_safe_fields() -> None:
    diagnostics = inspect_operator_output(
        {
            "report_kind": "jira_readonly_inventory",
            "inventory_status": "synthetic_verified",
            "project_inventory_status": "permission_limited",
            "project_count_class": "nonzero_count",
            "issue_inventory_status": "not_observed",
            "issue_count_class": "not_observed",
            "accessible_project_count_class": "nonzero_count",
            "inaccessible_project_count_class": "zero_count",
            "permission_limited_count_class": "zero_count",
            "access_diagnostic_class": "jira_project_inventory_permission_limited",
            "portfolio_mapping": {
                "mapping_status": "planned_not_verified",
                "mapping_readiness_status": "ready_for_manual_mapping",
                "mapped_area_count_class": "zero_count",
                "needs_manual_mapping_count_class": "nonzero_count",
                "manual_mapping_required_count_class": "nonzero_count",
                "repo_component_strategy": "repo_as_component",
            },
            "operating_model": {
                "recommended_model_class": "product_area_model",
                "recommended_project_class_count": 6,
                "repo_component_strategy": "repo_as_component",
            },
            "recommended_next_action_class": "verify_jira_project_permissions",
        }
    ).as_dict()

    assert diagnostics["safe"] is True
    assert diagnostics["unsafe_pattern_count"] == 0


def test_operator_output_sanitizer_allows_github_org_migration_safe_fields() -> None:
    diagnostics = inspect_operator_output(
        {
            "target_owner_class": "github_organization",
            "target_org_key": "qtwin-io",
            "seed_source_class": "legacy_personal_account_seed",
            "seed_portfolio_status": "present",
            "migration_status_class": "manual_org_migration_planned",
            "target_org_inventory_status": "gated_not_verified",
            "target_org_current_repo_count_class": "one_repo_reported_by_operator",
            "target_remaining_migration_count_class": "nonzero_count",
            "source_of_truth_status": "planning_metadata_only",
            "github_write_operations": "disabled",
            "github_repo_transfer_operations": "disabled",
            "github_repo_edit_operations": "disabled",
        }
    ).as_dict()

    assert diagnostics["safe"] is True
    assert diagnostics["unsafe_pattern_count"] == 0


def test_operator_output_sanitizer_allows_jira_creation_dry_run_safe_fields() -> None:
    diagnostics = inspect_operator_output(
        {
            "report_kind": "jira_creation_dry_run",
            "dry_run_only": True,
            "jira_write_operations": "disabled",
            "manual_approval_required": True,
            "current_jira_assessment_class": "existing_projects_visible",
            "migration_recommendation_class": "new_clean_structure_recommended",
            "proposed_structure": {
                "recommended_model_class": "product_area_model",
                "project_class_count": 6,
                "component_strategy_class": "repo_as_component",
                "component_count_class": "nonzero_count",
                "issue_type_class_count": 8,
                "workflow_status_class_count": 8,
                "board_class_count": 4,
                "governance_rule_count": 7,
            },
            "proposed_project_classes": [
                "ssap_digital_twin",
                "kazscan_corporate",
                "infrastructure_data",
                "rd_3d_ar",
                "marketing_corporate",
                "ops_support",
            ],
            "follow_up_classes": [
                "issue_search_inventory_follow_up",
                "current_jira_project_visibility_confirmed",
                "creation_requires_write_approval",
                "migration_requires_manual_mapping",
            ],
            "blocked_write_operation_classes": [
                "create_jira_projects_blocked",
                "create_jira_components_blocked",
            ],
        }
    ).as_dict()

    assert diagnostics["safe"] is True
    assert diagnostics["unsafe_pattern_count"] == 0


def test_operator_output_sanitizer_allows_atlassian_profile_safe_fields() -> None:
    diagnostics = inspect_operator_output(
        {
            "report_kind": "atlassian_api_profile_summary",
            "profile_key": "atlassian_admin_org_api_scoped",
            "auth_class": "bearer_admin_api_key",
            "endpoint_class": "atlassian_admin_api",
            "intended_operation_class": "atlassian_org_admin_diagnostics_dry_run",
            "live_read_status": "gated",
            "live_write_status": "dry_run_only",
            "org_id_presence_class": "present",
            "values_visibility": "hidden",
            "write_operations": "disabled",
            "admin_live_calls": "not_run",
            "required_environment_variable_names": [
                "FOS_ATLASSIAN_ORG_ID",
                "FOS_ATLASSIAN_ADMIN_API_TOKEN_SCOPED",
                "FOS_ATLASSIAN_ADMIN_API_TOKEN_UNSCOPED",
                "FOS_JIRA_WRITE_USER",
                "FOS_JIRA_WRITE_TOKEN",
            ],
        }
    ).as_dict()

    assert diagnostics["safe"] is True
    assert diagnostics["unsafe_pattern_count"] == 0


def test_operator_output_sanitizer_allows_jira_write_readiness_safe_fields() -> None:
    diagnostics = inspect_operator_output(
        {
            "report_kind": "jira_write_readiness",
            "write_execution_status": "disabled",
            "dry_run_only": True,
            "manual_approval_required": True,
            "required_profile_classes": [
                "jira_write_site_api",
                "atlassian_admin_org_api_scoped",
            ],
            "configured_profile_count_class": "zero_count",
            "missing_profile_count_class": "nonzero_count",
            "blocked_write_operation_classes": [
                "create_jira_project",
                "create_jira_component",
                "create_jira_board",
                "configure_jira_workflow",
                "configure_jira_issue_type",
            ],
            "next_approval_class": "approve_jira_write_execution_prompt",
            "creation_dry_run_status": "present",
        }
    ).as_dict()

    assert diagnostics["safe"] is True
    assert diagnostics["unsafe_pattern_count"] == 0


def test_operator_output_sanitizer_raises_safe_reason_only() -> None:
    with pytest.raises(ValueError) as exc_info:
        assert_operator_output_safe({"message": _unsafe_values()["url"]})

    assert str(exc_info.value) == "operator_output_unsafe"
    assert _unsafe_values()["url"] not in repr(exc_info.value)


def test_guard_diagnostics_remain_safe_under_sanitizer() -> None:
    guard_diagnostics: list[dict[str, Any]] = []
    for call in (
        lambda: require_live_provider_execution_ack(
            provider="unsafe provider",
            boundary="unsafe boundary",
        ),
        lambda: require_production_operation_ack(
            operation_class="unsafe operation",
            boundary="source_of_truth_operation",
        ),
        lambda: require_no_scheduler_execution(
            boundary="test_telegram_delivery_execution",
            execution_source=OUTBOX_DRAIN,
        ),
    ):
        with pytest.raises(RuntimeError) as exc_info:
            call()
        guard_diagnostics.append(exc_info.value.diagnostics.as_dict())

    diagnostics = inspect_operator_output(guard_diagnostics).as_dict()
    assert diagnostics["safe"] is True
    assert diagnostics["unsafe_pattern_count"] == 0


def test_manual_delegated_contract_diagnostics_expose_sanitized_safety_counts() -> None:
    unsafe = _unsafe_values()
    diagnostics = manual_script._delegated_report_contract_diagnostics(
        exit_code=2,
        artifact_presence="present",
        artifact_contract_status="unsafe",
        validator_name="_normalize_delegated_report_artifact",
        payload={
            "status": "blocked",
            "provider_payload": unsafe["payload"],
            "rendered_text": unsafe["rendered"],
            "source_object_id": unsafe["source"],
        },
    )

    safety = diagnostics["operator_output_safety"]
    assert safety["safe"] is False
    assert safety["payload_like_value_count"] >= 1
    assert safety["unsafe_json_flag_count"] >= 1
    _assert_raw_values_absent(diagnostics)


def test_bounded_send_blocked_output_sanitizes_unsafe_message() -> None:
    unsafe_message = _unsafe_values()["url"]

    blocked = send_script._blocked_result(
        error_code="send_blocked",
        message=unsafe_message,
    )

    assert blocked["message"] == "blocked_message_sanitized"
    assert unsafe_message not in json.dumps(blocked, sort_keys=True)
    assert inspect_operator_output(blocked).safe is True
