from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.services.jira_operating_model import (
    COMPONENT_STRATEGY_REPO,
    jira_operating_model_summary,
)
from app.services.operator_output_sanitizer import inspect_operator_output
from app.services.repository_portfolio import repository_portfolio_public_summary

MAPPING_STATUS_PLANNED_NOT_VERIFIED = "planned_not_verified"
MAPPING_STATUS_SYNTHETIC_VERIFIED = "synthetic_verified"
MAPPING_STATUS_LIVE_READONLY_OBSERVED = "live_readonly_observed"
MAPPING_STATUS_NEEDS_MANUAL_MAPPING = "needs_manual_mapping"

MAPPING_READINESS_PLANNED_NOT_VERIFIED = "planned_not_verified"
MAPPING_READINESS_INVENTORY_OBSERVED_MAPPING_PENDING = (
    "inventory_observed_mapping_pending"
)
MAPPING_READINESS_READY_FOR_MANUAL_MAPPING = "ready_for_manual_mapping"
MAPPING_READINESS_SYNTHETIC_VERIFIED = "synthetic_verified"

JIRA_INVENTORY_STATUS_NOT_RUN = "not_run"
JIRA_INVENTORY_STATUS_NOT_CONFIGURED = "not_configured"
JIRA_INVENTORY_STATUS_CONFIGURED_NOT_EXECUTED = "configured_not_executed"
JIRA_INVENTORY_STATUS_SYNTHETIC_VERIFIED = "synthetic_verified"
JIRA_INVENTORY_STATUS_LIVE_READONLY_VERIFIED = "live_readonly_verified"

COUNT_ZERO = "zero_count"
COUNT_NONZERO = "nonzero_count"
COUNT_MATCHES_PORTFOLIO_AREAS = "matches_portfolio_area_count"
SOURCE_OF_TRUTH_MUTATION_ABSENT = "absent"
SCHEDULER_EXECUTION_DISABLED = "disabled"


def jira_portfolio_mapping_summary(
    *,
    jira_inventory_status: str = JIRA_INVENTORY_STATUS_NOT_RUN,
    mapping_status: str = MAPPING_STATUS_PLANNED_NOT_VERIFIED,
) -> dict[str, Any]:
    portfolio_summary = repository_portfolio_public_summary()
    portfolio_area_count = int(portfolio_summary["product_area_count"])
    operating_model = jira_operating_model_summary()
    if mapping_status == MAPPING_STATUS_SYNTHETIC_VERIFIED:
        mapped_area_count = portfolio_area_count
        unmapped_area_count = 0
        needs_manual_mapping_count = 0
    else:
        mapped_area_count = 0
        unmapped_area_count = portfolio_area_count
        needs_manual_mapping_count = portfolio_area_count

    summary = {
        "portfolio_area_count": portfolio_area_count,
        "mapping_status": _safe_mapping_status(mapping_status),
        "jira_inventory_status": _safe_inventory_status(jira_inventory_status),
        "mapping_readiness_status": _mapping_readiness_status(
            jira_inventory_status=jira_inventory_status,
            mapping_status=mapping_status,
        ),
        "recommended_jira_project_class_count": operating_model[
            "recommended_project_class_count"
        ],
        "repo_component_strategy": COMPONENT_STRATEGY_REPO,
        "mapped_area_count_class": _area_count_class(
            mapped_area_count,
            portfolio_area_count,
        ),
        "unmapped_area_count_class": _zero_nonzero_count_class(unmapped_area_count),
        "needs_manual_mapping_count_class": _zero_nonzero_count_class(
            needs_manual_mapping_count
        ),
        "manual_mapping_required_count_class": _zero_nonzero_count_class(
            needs_manual_mapping_count
        ),
        "source_of_truth_mutation": SOURCE_OF_TRUTH_MUTATION_ABSENT,
        "no_send": True,
        "no_source_of_truth_mutation": True,
        "scheduler_execution": SCHEDULER_EXECUTION_DISABLED,
    }
    _assert_safe(summary)
    return summary


def jira_inventory_readiness_summary() -> dict[str, Any]:
    summary = {
        "jira_inventory_cli": "present",
        "jira_inventory_live_readonly": "gated",
        "jira_inventory_diagnostics": "present",
        "jira_portfolio_mapping": "synthetic_ready",
        "jira_mapping_readiness": "planned_or_observed",
        "jira_operating_model": "present",
        "jira_write_operations": "disabled",
        "source_of_truth_mutation": SOURCE_OF_TRUTH_MUTATION_ABSENT,
        "no_send": True,
        "no_source_of_truth_mutation": True,
        "scheduler_execution": SCHEDULER_EXECUTION_DISABLED,
    }
    _assert_safe(summary)
    return summary


def _safe_mapping_status(value: str) -> str:
    if value in {
        MAPPING_STATUS_PLANNED_NOT_VERIFIED,
        MAPPING_STATUS_SYNTHETIC_VERIFIED,
        MAPPING_STATUS_LIVE_READONLY_OBSERVED,
        MAPPING_STATUS_NEEDS_MANUAL_MAPPING,
    }:
        return value
    return MAPPING_STATUS_NEEDS_MANUAL_MAPPING


def _safe_inventory_status(value: str) -> str:
    if value in {
        JIRA_INVENTORY_STATUS_NOT_RUN,
        JIRA_INVENTORY_STATUS_NOT_CONFIGURED,
        JIRA_INVENTORY_STATUS_CONFIGURED_NOT_EXECUTED,
        JIRA_INVENTORY_STATUS_SYNTHETIC_VERIFIED,
        JIRA_INVENTORY_STATUS_LIVE_READONLY_VERIFIED,
    }:
        return value
    return JIRA_INVENTORY_STATUS_NOT_RUN


def _mapping_readiness_status(
    *,
    jira_inventory_status: str,
    mapping_status: str,
) -> str:
    if mapping_status == MAPPING_STATUS_SYNTHETIC_VERIFIED:
        return MAPPING_READINESS_SYNTHETIC_VERIFIED
    if jira_inventory_status == JIRA_INVENTORY_STATUS_LIVE_READONLY_VERIFIED:
        if mapping_status == MAPPING_STATUS_LIVE_READONLY_OBSERVED:
            return MAPPING_READINESS_READY_FOR_MANUAL_MAPPING
        return MAPPING_READINESS_INVENTORY_OBSERVED_MAPPING_PENDING
    return MAPPING_READINESS_PLANNED_NOT_VERIFIED


def _area_count_class(count: int, expected_count: int) -> str:
    if count == expected_count:
        return COUNT_MATCHES_PORTFOLIO_AREAS
    return _zero_nonzero_count_class(count)


def _zero_nonzero_count_class(count: int) -> str:
    return COUNT_ZERO if count == 0 else COUNT_NONZERO


def _assert_safe(value: Mapping[str, Any]) -> None:
    if inspect_operator_output(value).safe is not True:
        raise ValueError("jira_portfolio_mapping_unsafe")
