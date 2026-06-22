from __future__ import annotations

import json
from pathlib import Path
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
    summarize_org_migration_readiness,
    summarize_portfolio_migration_counts,
    summarize_target_org_status,
    validate_repository_portfolio,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


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
    assert summary["legacy_seed_repo_count"] == 19
    assert summary["repo_total_count"] == summary["operational_repo_count"]
    assert summary["repo_total_count_source"] == summary["operational_repo_source"]
    assert summary["operational_repo_count"] >= summary["legacy_seed_repo_count"]
    assert summary["catalog_drift"]["legacy_seed_count"] == 19
    assert summary["lifecycle_status_counts"] == {
        LIFECYCLE_ACTIVE: 8,
        LIFECYCLE_LEGACY: 2,
        LIFECYCLE_SUPPORT: 9,
    }
    assert summary["product_area_count"] == 7
    assert sum(summary["product_area_counts"].values()) == 19
    assert summary["seed_source_class"] == "legacy_personal_account_seed"
    assert summary["seed_portfolio_status"] == "present"
    assert summary["target_owner_class"] == "github_organization"
    assert summary["target_org_key"] == "qtwin-io"
    assert summary["target_expected_migration_count"] == summary["operational_repo_count"]
    assert summary["legacy_seed_migration_candidate_count"] == 19
    assert summary["source_of_truth_status"] == "planning_metadata_only"


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


def test_repository_portfolio_target_org_status_is_safe_and_non_executing() -> None:
    target = summarize_target_org_status()
    counts = summarize_portfolio_migration_counts()
    readiness = summarize_org_migration_readiness()

    assert target["target_owner_class"] == "github_organization"
    assert target["target_org_key"] == "qtwin-io"
    assert target["target_org_status_class"] == "manual_migration_target"
    assert target["migration_status_class"] == "manual_org_migration_planned"
    assert target["target_org_inventory_status"] == "gated_not_verified"
    assert target["target_org_current_repo_count_class"] == (
        "one_repo_reported_by_operator"
    )
    assert target["target_org_existing_role_class"] == "frontend_repo_present"
    assert counts["seed_portfolio_count"] == 19
    assert counts["legacy_seed_migration_candidate_count"] == 19
    assert counts["target_expected_migration_count"] == counts["operational_repo_count"]
    assert readiness["operational_repo_count"] == counts["operational_repo_count"]
    assert counts["target_remaining_migration_count_class"] == "nonzero_count"
    assert readiness["seed_source_class"] == "legacy_personal_account_seed"
    assert readiness["github_write_operations"] == "disabled"
    assert readiness["github_repo_transfer_operations"] == "disabled"
    assert readiness["github_repo_edit_operations"] == "disabled"
    _assert_public_safe({"target": target, "counts": counts, "readiness": readiness})


def test_repository_portfolio_onboarding_plan_is_non_executing() -> None:
    plan = repository_portfolio_onboarding_plan_summary()

    assert plan["github_inventory_step"] == "target_org_manual_readonly_gated"
    assert plan["github_seed_comparison_step"] == (
        "operational_inventory_with_legacy_seed_reconciliation"
    )
    assert plan["github_target_owner_class"] == "github_organization"
    assert plan["github_target_org_key"] == "qtwin-io"
    assert plan["github_org_migration_status"] == "manual_org_migration_planned"
    assert plan["github_org_live_inventory_status"] == "gated_not_verified"
    assert plan["jira_mapping_step"] == "manual_mapping_planned"
    assert plan["metadata_update_execution"] == "not_implemented"
    assert plan["archive_execution"] == "not_implemented"
    assert plan["secret_rotation_execution"] == "not_implemented"
    assert plan["target_expected_migration_count"] == plan["operational_repo_count"]
    assert plan["legacy_seed_migration_candidate_count"] == 19
    assert plan["target_remaining_migration_count_class"] == "nonzero_count"
    assert plan["github_write_operations"] == "disabled"
    assert plan["github_repo_transfer_operations"] == "disabled"
    assert plan["github_repo_edit_operations"] == "disabled"
    assert plan["no_send"] is True
    assert plan["no_source_of_truth_mutation"] is True
    assert plan["scheduler_execution"] == "disabled"
    _assert_public_safe(plan)


def test_repository_portfolio_docs_frame_legacy_seed_as_planning_metadata() -> None:
    docs = "\n".join(
        (
            REPO_ROOT / "docs" / path
        ).read_text(encoding="utf-8")
        for path in (
            "runbooks/guarded-operations.md",
            "runbooks/jira-operating-model.md",
            "data-model.md",
            "features/attention.md",
            "features/telegram-digest.md",
        )
    )

    assert "qtwin-io" in docs
    assert "planning metadata" in docs
    assert "future canonical owner is the legacy" not in docs.casefold()
    assert "legacy account is the future canonical" not in docs.casefold()
