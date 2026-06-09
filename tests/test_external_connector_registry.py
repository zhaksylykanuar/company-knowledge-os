from __future__ import annotations

import json
from typing import Any

from app.services.external_connector_registry import (
    connector_catalog,
    connector_inventory_categories,
    connector_readiness_summary,
    get_connector_spec,
)
from app.services.operator_output_sanitizer import inspect_operator_output


def _unsafe_values() -> tuple[str, ...]:
    return (
        "https" + "://registry.invalid/path",
        "operator" + "@" + "registry.invalid",
        "bot_token registry value",
        "a" * 64,
        "postgres" + "://registry.invalid/db",
        "provider_payload registry body",
        "source_object_id registry body",
        "repository_name registry body",
        "remote_url registry body",
    )


def _assert_safe(value: Any) -> None:
    serialized = json.dumps(value, sort_keys=True)
    for raw_value in _unsafe_values():
        assert raw_value not in serialized
    assert inspect_operator_output(value).safe is True


def test_external_connector_registry_includes_known_provider_classes() -> None:
    catalog = connector_catalog()
    by_provider = {item["provider_key"]: item for item in catalog}

    assert set(by_provider) == {
        "github",
        "gmail",
        "google_drive",
        "jira",
        "openai",
        "slack",
        "telegram",
    }
    assert by_provider["github"]["readiness_category"] == (
        "present/guarded/synthetic_ready"
    )
    assert by_provider["jira"]["readiness_category"] == (
        "present/guarded/synthetic_ready"
    )
    assert by_provider["github"]["source_of_truth_role"] == "raw_event_source_only"
    assert by_provider["jira"]["source_of_truth_role"] == "raw_event_source_only"
    _assert_safe(catalog)


def test_external_connector_registry_contains_safe_metadata_only() -> None:
    catalog = connector_catalog()

    for item in catalog:
        assert item["no_send"] is True
        assert item["no_source_of_truth_mutation"] is True
        assert "provider_execution_guard" in item["guard_requirements"]
    _assert_safe(catalog)


def test_external_connector_readiness_summary_uses_safe_classes_only() -> None:
    summary = connector_readiness_summary()

    assert summary["registry"] == "present/safe_metadata_only"
    assert summary["github_connector"] == "present/guarded/synthetic_ready"
    assert summary["jira_connector"] == "present/guarded/synthetic_ready"
    assert summary["live_calls"] == "default_denied"
    assert summary["source_of_truth_mutation"] == "absent"
    assert summary["scheduler_execution"] == "disabled"
    assert summary["payload_leakage"] == "absent"
    assert summary["repository_portfolio"] == "present/safe_counts_only"
    assert summary["repository_portfolio_repo_count"] == 19
    assert summary["github_live_inventory_status"] == "gated_not_verified"
    assert summary["github_target_owner_class"] == "github_organization"
    assert summary["github_target_org_key"] == "qtwin-io"
    assert summary["github_legacy_seed_status"] == "present"
    assert summary["github_org_migration_status"] == "manual_org_migration_planned"
    assert summary["github_org_live_inventory_status"] == "gated_not_verified"
    assert summary["github_write_operations"] == "disabled"
    assert summary["github_repo_transfer_operations"] == "disabled"
    assert summary["github_repo_edit_operations"] == "disabled"
    assert summary["jira_mapping_status"] == "planned_not_verified"
    assert summary["synthetic_connector_count"] == 2
    _assert_safe(summary)


def test_external_connector_inventory_categories_are_sanitized() -> None:
    categories = connector_inventory_categories()

    assert categories["github"] == "guarded_live_boundary"
    assert categories["jira"] == "guarded_live_boundary"
    assert categories["payload_mapper"] == "read_only_local_transform"
    assert set(categories.values()) <= {
        "already_guarded",
        "already_guarded_delivery_interface",
        "guarded_live_boundary",
        "planned_connector",
        "read_only_local_transform",
    }
    _assert_safe(categories)


def test_external_connector_spec_lookup_returns_safe_metadata() -> None:
    spec = get_connector_spec("github")

    assert spec is not None
    assert spec.provider_key == "github"
    assert spec.synthetic_fetch_supported is True
    _assert_safe(spec.as_dict())
