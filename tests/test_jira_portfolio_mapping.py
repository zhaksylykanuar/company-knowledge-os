from __future__ import annotations

import json
from typing import Any

from app.services.jira_portfolio_mapping import (
    JIRA_INVENTORY_STATUS_LIVE_READONLY_VERIFIED,
    JIRA_INVENTORY_STATUS_NOT_RUN,
    JIRA_INVENTORY_STATUS_SYNTHETIC_VERIFIED,
    MAPPING_STATUS_LIVE_READONLY_OBSERVED,
    MAPPING_STATUS_PLANNED_NOT_VERIFIED,
    MAPPING_STATUS_SYNTHETIC_VERIFIED,
    jira_inventory_readiness_summary,
    jira_portfolio_mapping_summary,
)
from app.services.operator_output_sanitizer import inspect_operator_output


def _unsafe_values() -> tuple[str, ...]:
    return (
        "https" + "://jira-mapping.invalid/path",
        "operator" + "@" + "jira-mapping.invalid",
        "bot_token mapping value",
        "a" * 64,
        "postgres" + "://jira-mapping.invalid/db",
        "provider_payload mapping body",
        "source_object_id mapping body",
        "PROJECT" + "-123",
        "issue title mapping body",
    )


def _assert_safe(value: Any) -> None:
    serialized = json.dumps(value, sort_keys=True)
    for raw_value in _unsafe_values():
        assert raw_value not in serialized
    assert inspect_operator_output(value).safe is True


def test_jira_portfolio_mapping_default_is_planned_counts_only() -> None:
    summary = jira_portfolio_mapping_summary()

    assert summary["portfolio_area_count"] == 7
    assert summary["mapping_status"] == MAPPING_STATUS_PLANNED_NOT_VERIFIED
    assert summary["jira_inventory_status"] == JIRA_INVENTORY_STATUS_NOT_RUN
    assert summary["mapped_area_count_class"] == "zero_count"
    assert summary["unmapped_area_count_class"] == "nonzero_count"
    assert summary["needs_manual_mapping_count_class"] == "nonzero_count"
    assert summary["no_send"] is True
    assert summary["no_source_of_truth_mutation"] is True
    assert summary["scheduler_execution"] == "disabled"
    _assert_safe(summary)


def test_jira_portfolio_mapping_synthetic_can_match_portfolio_area_count() -> None:
    summary = jira_portfolio_mapping_summary(
        jira_inventory_status=JIRA_INVENTORY_STATUS_SYNTHETIC_VERIFIED,
        mapping_status=MAPPING_STATUS_SYNTHETIC_VERIFIED,
    )

    assert summary["portfolio_area_count"] == 7
    assert summary["mapped_area_count_class"] == "matches_portfolio_area_count"
    assert summary["unmapped_area_count_class"] == "zero_count"
    assert summary["needs_manual_mapping_count_class"] == "zero_count"
    _assert_safe(summary)


def test_jira_portfolio_mapping_live_observed_still_needs_manual_mapping() -> None:
    summary = jira_portfolio_mapping_summary(
        jira_inventory_status=JIRA_INVENTORY_STATUS_LIVE_READONLY_VERIFIED,
        mapping_status=MAPPING_STATUS_LIVE_READONLY_OBSERVED,
    )

    assert summary["mapping_status"] == MAPPING_STATUS_LIVE_READONLY_OBSERVED
    assert summary["mapped_area_count_class"] == "zero_count"
    assert summary["needs_manual_mapping_count_class"] == "nonzero_count"
    _assert_safe(summary)


def test_jira_inventory_readiness_summary_is_safe() -> None:
    summary = jira_inventory_readiness_summary()

    assert summary == {
        "jira_inventory_cli": "present",
        "jira_inventory_live_readonly": "gated",
        "jira_portfolio_mapping": "synthetic_ready",
        "source_of_truth_mutation": "absent",
        "no_send": True,
        "no_source_of_truth_mutation": True,
        "scheduler_execution": "disabled",
    }
    _assert_safe(summary)
