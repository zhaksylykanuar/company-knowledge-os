from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
import os
from typing import Any

from app.connectors import github
from app.services.external_connector_config import (
    PROVIDER_GITHUB,
    external_connector_config_doctor_providers,
)
from app.services.local_connector_env import load_local_connector_environment
from app.services.operator_output_sanitizer import inspect_operator_output
from app.services.provider_execution_guard import (
    LIVE_PROVIDER_EXECUTION_ACK,
    PROVIDER_EXECUTION_ACK_REQUIRED,
)
from app.services.repository_portfolio import (
    GITHUB_REPO_EDIT_OPERATIONS_DISABLED,
    GITHUB_REPO_TRANSFER_OPERATIONS_DISABLED,
    GITHUB_WRITE_OPERATIONS_DISABLED,
    MIGRATION_STATUS_CLASS,
    PORTFOLIO_SEED_STATUS,
    TARGET_ORG_CURRENT_REPO_COUNT_CLASS,
    TARGET_ORG_INVENTORY_STATUS,
    TARGET_ORG_KEY,
    TARGET_OWNER_CLASS,
    repository_portfolio_catalog,
    repository_portfolio_public_summary,
)

REPORT_KIND = "github_org_readonly_inventory"
STATUS_PASS = "pass"
STATUS_FAIL = "fail"
PROVIDER_CALLS_NONE = "none"
PROVIDER_CALLS_SYNTHETIC = "synthetic"
PROVIDER_CALLS_LIVE_READONLY_ATTEMPTED = "live_readonly_attempted"
SCHEDULER_EXECUTION_DISABLED = "disabled"

CONFIGURED = "configured"
NOT_CONFIGURED = "not_configured"
PARTIALLY_CONFIGURED = "partially_configured"
REQUIRES_ACKNOWLEDGEMENT = "requires_acknowledgement"
CONFIGURED_NOT_EXECUTED = "configured_not_executed"

ORG_INVENTORY_STATUS_NOT_RUN = "not_run"
ORG_INVENTORY_STATUS_SYNTHETIC_VERIFIED = "synthetic_verified"
ORG_INVENTORY_STATUS_LIVE_READONLY_VERIFIED = "live_readonly_verified"
ORG_INVENTORY_STATUS_FAIL = "fail"

COUNT_ZERO = "zero_count"
COUNT_NONZERO = "nonzero_count"
COUNT_NOT_OBSERVED = "not_observed"
PAYLOAD_VISIBILITY_SUPPRESSED = "suppressed"

INVENTORY_PASSED = "github_org_readonly_inventory_passed"
INVENTORY_FAILED = "github_org_readonly_inventory_failed"

NEXT_ACTION_RUN_GATED_INVENTORY = "run_gated_github_org_inventory"
NEXT_ACTION_REVIEW_MANUAL_MIGRATION = "review_manual_org_migration_status"
NEXT_ACTION_FIX_GITHUB_CONFIG = "set_github_readonly_config"
NEXT_ACTION_INVESTIGATE_INVENTORY = "investigate_github_org_inventory"


def run_github_org_readonly_inventory(
    *,
    synthetic: bool = False,
    allow_live_readonly_apis: bool = False,
    acknowledge_live_readonly_risk: str | None = None,
    compare_portfolio: bool = False,
    target_org: str | None = None,
    max_results: int = 50,
    github_live_transport: github.GitHubTransport | None = None,
    environ: Mapping[str, str] | None = None,
    connector_env_file: str | Path | None = None,
    use_connector_env_file: bool = False,
) -> dict[str, Any]:
    env_result = load_local_connector_environment(
        environ=environ if environ is not None else os.environ,
        connector_env_file=connector_env_file,
        use_connector_env_file=use_connector_env_file,
    )
    environment = env_result.environment
    config_status = _github_config_status(environment)
    target_org_status = _target_org_argument_status(target_org)
    github_summary = _base_github_summary(
        config_status=config_status,
        compare_portfolio=compare_portfolio,
    )
    provider_calls = PROVIDER_CALLS_NONE
    status = STATUS_PASS
    reason_code: str | None = REQUIRES_ACKNOWLEDGEMENT

    if synthetic:
        inventory = github.fetch_org_repository_inventory_summary(
            transport=_synthetic_org_inventory_transport(),
            execution_mode=github.SYNTHETIC_EXECUTION_MODE,
            seed_repository_keys=_seed_repo_keys(),
            max_results=max_results,
        )
        github_summary.update(
            {
                **_connector_inventory_fields(inventory),
                "org_inventory_status": ORG_INVENTORY_STATUS_SYNTHETIC_VERIFIED,
                "failure_class": None,
            }
        )
        provider_calls = PROVIDER_CALLS_SYNTHETIC
        reason_code = INVENTORY_PASSED
    elif not allow_live_readonly_apis:
        github_summary.update(
            {
                "org_inventory_status": CONFIGURED_NOT_EXECUTED
                if config_status == CONFIGURED
                else ORG_INVENTORY_STATUS_NOT_RUN,
                "failure_class": REQUIRES_ACKNOWLEDGEMENT
                if config_status == CONFIGURED
                else config_status,
            }
        )
    elif acknowledge_live_readonly_risk != LIVE_PROVIDER_EXECUTION_ACK:
        status = STATUS_FAIL
        reason_code = PROVIDER_EXECUTION_ACK_REQUIRED
        github_summary.update(
            {
                "status": STATUS_FAIL,
                "org_inventory_status": ORG_INVENTORY_STATUS_NOT_RUN,
                "failure_class": PROVIDER_EXECUTION_ACK_REQUIRED,
            }
        )
    elif config_status != CONFIGURED:
        reason_code = config_status
        github_summary.update(
            {
                "org_inventory_status": ORG_INVENTORY_STATUS_NOT_RUN,
                "failure_class": config_status,
            }
        )
    else:
        provider_calls = PROVIDER_CALLS_LIVE_READONLY_ATTEMPTED
        try:
            inventory = github.fetch_org_repository_inventory_summary(
                transport=github_live_transport,
                execution_mode=github.LIVE_EXECUTION_MODE,
                allow_live_provider_execution=True,
                provider_execution_ack=acknowledge_live_readonly_risk,
                seed_repository_keys=_seed_repo_keys(),
                max_results=max_results,
            )
            github_summary.update(
                {
                    **_connector_inventory_fields(inventory),
                    "org_inventory_status": (
                        ORG_INVENTORY_STATUS_LIVE_READONLY_VERIFIED
                    ),
                    "failure_class": None,
                }
            )
            reason_code = INVENTORY_PASSED
        except Exception:
            status = STATUS_FAIL
            reason_code = INVENTORY_FAILED
            github_summary.update(
                {
                    "status": STATUS_FAIL,
                    "org_inventory_status": ORG_INVENTORY_STATUS_FAIL,
                    "failure_class": INVENTORY_FAILED,
                }
            )

    migration_readiness = _migration_readiness(
        github_summary=github_summary,
        synthetic=synthetic,
        allow_live_readonly_apis=allow_live_readonly_apis,
    )
    result = {
        "status": status,
        "reason_code": reason_code,
        "report_kind": REPORT_KIND,
        "no_send": True,
        "no_provider_calls": provider_calls != PROVIDER_CALLS_LIVE_READONLY_ATTEMPTED,
        "no_source_of_truth_mutation": True,
        "scheduler_execution": SCHEDULER_EXECUTION_DISABLED,
        "provider_calls": provider_calls,
        "github": github_summary,
        "migration_readiness": migration_readiness,
        "diagnostics": {
            "synthetic_mode": synthetic,
            "portfolio_compare_requested": compare_portfolio,
            "target_org_argument_status": target_org_status,
            "max_results_class": "bounded",
            "connector_env_file": dict(env_result.diagnostics),
        },
    }
    _assert_safe(result)
    return result


def github_org_inventory_readiness_summary() -> dict[str, Any]:
    summary = {
        "github_org_inventory_cli": "present",
        "github_target_org_key": TARGET_ORG_KEY,
        "github_target_owner_class": TARGET_OWNER_CLASS,
        "github_org_live_inventory": "gated",
        "github_org_migration_status": MIGRATION_STATUS_CLASS,
        "github_repo_transfer_operations": GITHUB_REPO_TRANSFER_OPERATIONS_DISABLED,
        "github_repo_edit_operations": GITHUB_REPO_EDIT_OPERATIONS_DISABLED,
        "github_write_operations": GITHUB_WRITE_OPERATIONS_DISABLED,
        "source_of_truth_mutation": "absent",
        "no_send": True,
        "no_provider_calls": True,
        "no_source_of_truth_mutation": True,
        "scheduler_execution": SCHEDULER_EXECUTION_DISABLED,
    }
    _assert_safe(summary)
    return summary


def _base_github_summary(
    *,
    config_status: str,
    compare_portfolio: bool,
) -> dict[str, Any]:
    portfolio = repository_portfolio_public_summary()
    return {
        "status": STATUS_PASS,
        "config_status": config_status,
        "target_owner_class": TARGET_OWNER_CLASS,
        "target_org_key": TARGET_ORG_KEY,
        "org_inventory_status": ORG_INVENTORY_STATUS_NOT_RUN,
        "org_repo_count_class": COUNT_NOT_OBSERVED,
        "seed_portfolio_status": PORTFOLIO_SEED_STATUS,
        "seed_repo_count": portfolio["repo_total_count"],
        "expected_migration_count": portfolio["target_expected_migration_count"],
        "matched_count_class": COUNT_NOT_OBSERVED,
        "missing_count_class": COUNT_NOT_OBSERVED,
        "extra_count_class": COUNT_NOT_OBSERVED,
        "frontend_repo_reported_class": TARGET_ORG_CURRENT_REPO_COUNT_CLASS,
        "migration_status_class": MIGRATION_STATUS_CLASS,
        "live_inventory_status_class": TARGET_ORG_INVENTORY_STATUS,
        "portfolio_compare_scope": "seed_portfolio_counts_only"
        if compare_portfolio
        else "not_requested",
        "write_operations": GITHUB_WRITE_OPERATIONS_DISABLED,
        "repo_transfer_operations": GITHUB_REPO_TRANSFER_OPERATIONS_DISABLED,
        "repo_edit_operations": GITHUB_REPO_EDIT_OPERATIONS_DISABLED,
        "provider_payload_visibility": PAYLOAD_VISIBILITY_SUPPRESSED,
        "failure_class": None,
        "no_send": True,
        "no_source_of_truth_mutation": True,
        "scheduler_execution": SCHEDULER_EXECUTION_DISABLED,
    }


def _connector_inventory_fields(inventory: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "org_repo_count_class": _safe_count_class(
            inventory.get("target_org_repo_count_class")
        ),
        "matched_count_class": _safe_count_class(
            inventory.get("matched_seed_count_class")
        ),
        "missing_count_class": _safe_count_class(
            inventory.get("missing_seed_count_class")
        ),
        "extra_count_class": _safe_count_class(inventory.get("extra_org_count_class")),
        "provider_payload_visibility": PAYLOAD_VISIBILITY_SUPPRESSED,
    }


def _migration_readiness(
    *,
    github_summary: Mapping[str, Any],
    synthetic: bool,
    allow_live_readonly_apis: bool,
) -> dict[str, Any]:
    inventory_status = str(github_summary.get("org_inventory_status"))
    if inventory_status == ORG_INVENTORY_STATUS_LIVE_READONLY_VERIFIED:
        next_action = NEXT_ACTION_REVIEW_MANUAL_MIGRATION
    elif synthetic:
        next_action = NEXT_ACTION_REVIEW_MANUAL_MIGRATION
    elif github_summary.get("config_status") != CONFIGURED:
        next_action = NEXT_ACTION_FIX_GITHUB_CONFIG
    elif not allow_live_readonly_apis:
        next_action = NEXT_ACTION_RUN_GATED_INVENTORY
    else:
        next_action = NEXT_ACTION_INVESTIGATE_INVENTORY

    return {
        "migration_status_class": MIGRATION_STATUS_CLASS,
        "target_org_current_status_class": TARGET_ORG_CURRENT_REPO_COUNT_CLASS,
        "live_inventory_status_class": TARGET_ORG_INVENTORY_STATUS
        if inventory_status != ORG_INVENTORY_STATUS_LIVE_READONLY_VERIFIED
        else ORG_INVENTORY_STATUS_LIVE_READONLY_VERIFIED,
        "next_action_class": next_action,
        "write_operations": GITHUB_WRITE_OPERATIONS_DISABLED,
        "repo_transfer_operations": GITHUB_REPO_TRANSFER_OPERATIONS_DISABLED,
        "repo_edit_operations": GITHUB_REPO_EDIT_OPERATIONS_DISABLED,
        "no_send": True,
        "no_source_of_truth_mutation": True,
        "scheduler_execution": SCHEDULER_EXECUTION_DISABLED,
    }


def _github_config_status(environ: Mapping[str, str]) -> str:
    providers = external_connector_config_doctor_providers(environ=environ)
    provider = providers.get(PROVIDER_GITHUB, {})
    status = provider.get("configured_status")
    if status in {CONFIGURED, NOT_CONFIGURED, PARTIALLY_CONFIGURED}:
        return str(status)
    return NOT_CONFIGURED


def _synthetic_org_inventory_transport() -> github.GitHubTransport:
    seed_keys = tuple(_seed_repo_keys())

    def transport(
        request: github.GitHubConnectorRequest,
    ) -> Iterable[Mapping[str, Any]]:
        if seed_keys:
            return ({"repo_key": seed_keys[0]},)
        return ()

    return transport


def _seed_repo_keys() -> tuple[str, ...]:
    return tuple(
        str(entry["repo_key"])
        for entry in repository_portfolio_catalog()
        if isinstance(entry.get("repo_key"), str)
    )


def _target_org_argument_status(target_org: str | None) -> str:
    if target_org is None or target_org == TARGET_ORG_KEY:
        return "target_org_default_or_expected"
    return "unsupported_target_org_ignored"


def _safe_count_class(value: Any) -> str:
    if value in {COUNT_ZERO, COUNT_NONZERO, COUNT_NOT_OBSERVED}:
        return str(value)
    return COUNT_NOT_OBSERVED


def _assert_safe(value: Mapping[str, Any]) -> None:
    if inspect_operator_output(value).safe is not True:
        raise ValueError("github_org_inventory_unsafe")
