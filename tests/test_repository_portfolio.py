from __future__ import annotations

import json
from typing import Any

from app.services.operator_output_sanitizer import inspect_operator_output
from app.services.repository_portfolio import (
    ACTION_ARCHIVE_CANDIDATE,
    ACTION_GITHUB_DESCRIPTION_MISSING,
    ACTION_README_MISSING,
    ACTION_SECRET_ROTATION_REQUIRED,
    ACTION_TOPICS_MISSING,
    LIFECYCLE_ACTIVE,
    LIFECYCLE_LEGACY,
    LIFECYCLE_SUPPORT,
    repository_portfolio_catalog,
    repository_portfolio_onboarding_plan_summary,
    repository_portfolio_public_summary,
    validate_repository_portfolio,
)


def _unsafe_values() -> tuple[str, ...]:
    return (
        "https" + "://portfolio.invalid/path",
        "operator" + "@" + "portfolio.invalid",
        "bot_token portfolio value",
        "a" * 64,
        "postgres" + "://portfolio.invalid/db",
        "provider_payload portfolio body",
        "source_object_id portfolio body",
        "rendered_digest_text portfolio body",
        "grouped_preview_text portfolio body",
        "chunk_text portfolio body",
        "remote_url portfolio body",
    )


def _assert_public_safe(value: Any) -> None:
    serialized = json.dumps(value, sort_keys=True)
    for raw_value in _unsafe_values():
        assert raw_value not in serialized
    assert inspect_operator_output(value).safe is True


def test_repository_portfolio_catalog_has_expected_counts() -> None:
    catalog = repository_portfolio_catalog()
    summary = repository_portfolio_public_summary()

    assert len(catalog) == 19
    assert summary["repo_total_count"] == 19
    assert summary["lifecycle_status_counts"] == {
        LIFECYCLE_ACTIVE: 8,
        LIFECYCLE_LEGACY: 2,
        LIFECYCLE_SUPPORT: 9,
    }
    assert summary["product_area_count"] == 7
    assert sum(summary["product_area_counts"].values()) == 19


def test_repository_portfolio_catalog_entries_have_required_safe_fields() -> None:
    catalog = repository_portfolio_catalog()

    for entry in catalog:
        assert entry["provider_key"] == "github"
        assert entry["product_area"]
        assert entry["lifecycle_status"]
        assert entry["connector_priority"]
        assert entry["live_api_status"] == "not_verified"
        assert entry["jira_mapping_status"] == "not_mapped"
        assert entry["no_send"] is True
        assert entry["no_source_of_truth_mutation"] is True


def test_repository_portfolio_action_class_summary_uses_counts_only() -> None:
    summary = repository_portfolio_public_summary()
    action_counts = summary["action_class_counts"]

    assert set(action_counts) == {
        ACTION_ARCHIVE_CANDIDATE,
        ACTION_GITHUB_DESCRIPTION_MISSING,
        ACTION_README_MISSING,
        ACTION_SECRET_ROTATION_REQUIRED,
        ACTION_TOPICS_MISSING,
    }
    assert action_counts[ACTION_SECRET_ROTATION_REQUIRED] == 1
    assert action_counts[ACTION_ARCHIVE_CANDIDATE] == 2
    _assert_public_safe(summary)


def test_repository_portfolio_validation_reports_safe_classes_only() -> None:
    validation = validate_repository_portfolio()

    assert validation == {
        "validation_status": "pass",
        "reason_code": "repository_portfolio_valid",
        "error_classes": [],
        "repo_total_count": 19,
        "no_send": True,
        "no_source_of_truth_mutation": True,
        "scheduler_execution": "disabled",
    }
    _assert_public_safe(validation)


def test_repository_portfolio_public_summary_does_not_dump_raw_catalog() -> None:
    catalog = repository_portfolio_catalog()
    summary = repository_portfolio_public_summary()
    serialized_summary = json.dumps(summary, sort_keys=True)

    assert "repo_key" not in serialized_summary
    for entry in catalog:
        assert entry["repo_key"] not in serialized_summary
    _assert_public_safe(summary)


def test_repository_portfolio_onboarding_plan_is_non_executing() -> None:
    plan = repository_portfolio_onboarding_plan_summary()

    assert plan["github_inventory_step"] == "manual_readonly_gated"
    assert plan["jira_mapping_step"] == "manual_mapping_planned"
    assert plan["metadata_update_execution"] == "not_implemented"
    assert plan["archive_execution"] == "not_implemented"
    assert plan["secret_rotation_execution"] == "not_implemented"
    assert plan["no_send"] is True
    assert plan["no_source_of_truth_mutation"] is True
    assert plan["scheduler_execution"] == "disabled"
    _assert_public_safe(plan)
