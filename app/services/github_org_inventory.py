from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
import os
import re
import socket
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
    PROVIDER_EXECUTION_DEFAULT_DENIED,
    ProviderExecutionBlockedError,
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

GITHUB_ORG_CONFIG_INVALID = "github_org_config_invalid"
GITHUB_AUTH_FAILED = "github_auth_failed"
GITHUB_PERMISSION_DENIED = "github_permission_denied"
GITHUB_ORG_NOT_FOUND_OR_NO_ACCESS = "github_org_not_found_or_no_access"
GITHUB_RATE_LIMITED = "github_rate_limited"
GITHUB_SERVER_ERROR = "github_server_error"
GITHUB_TRANSPORT_ERROR = "github_transport_error"
GITHUB_TIMEOUT = "github_timeout"
GITHUB_RESPONSE_MALFORMED = "github_response_malformed"
GITHUB_RESPONSE_CONTRACT_MISMATCH = "github_response_contract_mismatch"
GITHUB_EMPTY_ORG_INVENTORY = "github_empty_org_inventory"
GITHUB_UNKNOWN_LIVE_INVENTORY_FAILURE = "github_unknown_live_inventory_failure"
GITHUB_LIVE_PROVIDER_DEFAULT_DENIED = "live_provider_default_denied"
GITHUB_ORG_INVENTORY_VISIBLE = "github_org_inventory_visible"

LIVE_READONLY_STATUS_NOT_RUN = "not_run"
LIVE_READONLY_STATUS_PASS = "pass"
LIVE_READONLY_STATUS_FAIL = "fail"
STATUS_NOT_CHECKED = "not_checked"
STATUS_SYNTHETIC_NOT_CHECKED = "synthetic_not_checked"
STATUS_TRANSPORT_NOT_RUN = "not_run"
STATUS_TRANSPORT_SYNTHETIC = "synthetic"
STATUS_CLASS_PASS = "pass"

NEXT_ACTION_RUN_GATED_INVENTORY = "run_gated_github_org_inventory"
NEXT_ACTION_REVIEW_MANUAL_MIGRATION = "review_manual_org_migration_status"
NEXT_ACTION_FIX_GITHUB_CONFIG = "set_github_readonly_config"
NEXT_ACTION_INVESTIGATE_INVENTORY = "investigate_github_org_inventory"

TARGET_ORG_CONFIGURED_SAFE_CLASS = "configured_target_org"
TARGET_ORG_DEFAULT_OR_EXPECTED = "target_org_default_or_expected"
TARGET_ORG_INVALID = "target_org_invalid"
TARGET_ORG_SAFE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,38}$")


@dataclass(frozen=True)
class NormalizedGitHubTargetOrg:
    value: str
    public_key: str
    status_class: str
    failure_class: str | None = None


class GitHubOrgInventoryLiveError(RuntimeError):
    def __init__(
        self,
        failure_class: str,
        *,
        auth_status_class: str | None = None,
        permission_status_class: str | None = None,
        transport_status_class: str | None = None,
        response_contract_status: str | None = None,
        org_visibility_status_class: str | None = None,
    ) -> None:
        super().__init__(failure_class)
        self.failure_class = failure_class
        self.auth_status_class = auth_status_class or _auth_status_for_failure(
            failure_class
        )
        self.permission_status_class = (
            permission_status_class or _permission_status_for_failure(failure_class)
        )
        self.transport_status_class = (
            transport_status_class or _transport_status_for_failure(failure_class)
        )
        self.response_contract_status = (
            response_contract_status or _response_status_for_failure(failure_class)
        )
        self.org_visibility_status_class = (
            org_visibility_status_class or _org_visibility_for_failure(failure_class)
        )


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
    normalized_target_org = normalize_github_target_org(
        target_org=target_org,
        environ=environment,
    )
    github_summary = _base_github_summary(
        config_status=config_status,
        compare_portfolio=compare_portfolio,
        target_org_public_key=normalized_target_org.public_key,
    )
    provider_calls = PROVIDER_CALLS_NONE
    status = STATUS_PASS
    reason_code: str | None = REQUIRES_ACKNOWLEDGEMENT

    if normalized_target_org.failure_class:
        status = STATUS_FAIL
        reason_code = normalized_target_org.failure_class
        github_summary.update(_failure_fields(normalized_target_org.failure_class))
    elif synthetic:
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
                "live_readonly_status": LIVE_READONLY_STATUS_NOT_RUN,
                "live_failure_class": None,
                "auth_status_class": STATUS_SYNTHETIC_NOT_CHECKED,
                "permission_status_class": STATUS_SYNTHETIC_NOT_CHECKED,
                "transport_status_class": STATUS_TRANSPORT_SYNTHETIC,
                "response_contract_status": STATUS_CLASS_PASS,
                "org_visibility_status_class": (
                    GITHUB_ORG_INVENTORY_VISIBLE
                    if inventory.get("target_org_repo_count_class") == COUNT_NONZERO
                    else GITHUB_EMPTY_ORG_INVENTORY
                ),
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
                "live_failure_class": REQUIRES_ACKNOWLEDGEMENT
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
                **_failure_fields(PROVIDER_EXECUTION_ACK_REQUIRED),
            }
        )
    elif config_status != CONFIGURED:
        reason_code = config_status
        github_summary.update(
            {
                "org_inventory_status": ORG_INVENTORY_STATUS_NOT_RUN,
                "failure_class": config_status,
                **_failure_fields(config_status),
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
                    "live_readonly_status": LIVE_READONLY_STATUS_PASS,
                    "live_failure_class": None,
                    "auth_status_class": STATUS_CLASS_PASS,
                    "permission_status_class": STATUS_CLASS_PASS,
                    "transport_status_class": STATUS_CLASS_PASS,
                    "response_contract_status": STATUS_CLASS_PASS,
                    "org_visibility_status_class": (
                        GITHUB_ORG_INVENTORY_VISIBLE
                        if inventory.get("target_org_repo_count_class")
                        == COUNT_NONZERO
                        else GITHUB_EMPTY_ORG_INVENTORY
                    ),
                }
            )
            if inventory.get("target_org_repo_count_class") == COUNT_ZERO:
                status = STATUS_FAIL
                reason_code = GITHUB_EMPTY_ORG_INVENTORY
                github_summary.update(_failure_fields(GITHUB_EMPTY_ORG_INVENTORY))
            else:
                reason_code = INVENTORY_PASSED
        except Exception as exc:
            failure = _classify_live_inventory_exception(exc)
            status = STATUS_FAIL
            reason_code = failure.failure_class
            github_summary.update(_failure_fields_from_error(failure))

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
            "target_org_argument_status": normalized_target_org.status_class,
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
    target_org_public_key: str,
) -> dict[str, Any]:
    portfolio = repository_portfolio_public_summary()
    return {
        "status": STATUS_PASS,
        "config_status": config_status,
        "target_owner_class": TARGET_OWNER_CLASS,
        "target_org_key": target_org_public_key,
        "org_inventory_status": ORG_INVENTORY_STATUS_NOT_RUN,
        "live_readonly_status": LIVE_READONLY_STATUS_NOT_RUN,
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
        "live_failure_class": None,
        "auth_status_class": STATUS_NOT_CHECKED,
        "permission_status_class": STATUS_NOT_CHECKED,
        "transport_status_class": STATUS_TRANSPORT_NOT_RUN,
        "response_contract_status": STATUS_NOT_CHECKED,
        "org_visibility_status_class": COUNT_NOT_OBSERVED,
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


def _failure_fields(failure_class: str) -> dict[str, Any]:
    return _failure_fields_from_error(GitHubOrgInventoryLiveError(failure_class))


def _failure_fields_from_error(error: GitHubOrgInventoryLiveError) -> dict[str, Any]:
    return {
        "status": STATUS_FAIL,
        "org_inventory_status": ORG_INVENTORY_STATUS_FAIL,
        "live_readonly_status": LIVE_READONLY_STATUS_FAIL,
        "failure_class": error.failure_class,
        "live_failure_class": error.failure_class,
        "auth_status_class": error.auth_status_class,
        "permission_status_class": error.permission_status_class,
        "transport_status_class": error.transport_status_class,
        "response_contract_status": error.response_contract_status,
        "org_visibility_status_class": error.org_visibility_status_class,
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


def normalize_github_target_org(
    *,
    target_org: str | None,
    environ: Mapping[str, str],
) -> NormalizedGitHubTargetOrg:
    configured_value = target_org
    if configured_value is None:
        configured_value = environ.get("FOS_GITHUB_TARGET_ORG")
    if configured_value is None or _placeholder_or_blank(configured_value):
        return NormalizedGitHubTargetOrg(
            value=TARGET_ORG_KEY,
            public_key=TARGET_ORG_KEY,
            status_class=TARGET_ORG_DEFAULT_OR_EXPECTED,
        )
    cleaned = configured_value.strip()
    if not TARGET_ORG_SAFE_PATTERN.fullmatch(cleaned):
        return NormalizedGitHubTargetOrg(
            value=TARGET_ORG_KEY,
            public_key=TARGET_ORG_KEY,
            status_class=TARGET_ORG_INVALID,
            failure_class=GITHUB_ORG_CONFIG_INVALID,
        )
    return NormalizedGitHubTargetOrg(
        value=cleaned,
        public_key=TARGET_ORG_KEY
        if cleaned == TARGET_ORG_KEY
        else TARGET_ORG_CONFIGURED_SAFE_CLASS,
        status_class=TARGET_ORG_DEFAULT_OR_EXPECTED
        if cleaned == TARGET_ORG_KEY
        else TARGET_ORG_CONFIGURED_SAFE_CLASS,
    )


def _placeholder_or_blank(value: str) -> bool:
    stripped = value.strip()
    if not stripped:
        return True
    return stripped in {"<set locally>", "set_locally", "placeholder"}


def github_org_inventory_error_for_http_status(
    status_code: int,
) -> GitHubOrgInventoryLiveError:
    if status_code == 401:
        return GitHubOrgInventoryLiveError(GITHUB_AUTH_FAILED)
    if status_code == 403:
        return GitHubOrgInventoryLiveError(GITHUB_PERMISSION_DENIED)
    if status_code == 404:
        return GitHubOrgInventoryLiveError(GITHUB_ORG_NOT_FOUND_OR_NO_ACCESS)
    if status_code == 429:
        return GitHubOrgInventoryLiveError(GITHUB_RATE_LIMITED)
    if 500 <= status_code <= 599:
        return GitHubOrgInventoryLiveError(GITHUB_SERVER_ERROR)
    return GitHubOrgInventoryLiveError(GITHUB_UNKNOWN_LIVE_INVENTORY_FAILURE)


def _classify_live_inventory_exception(
    exc: Exception,
) -> GitHubOrgInventoryLiveError:
    if isinstance(exc, GitHubOrgInventoryLiveError):
        return exc
    if isinstance(exc, ProviderExecutionBlockedError):
        reason = exc.reason_code
        if reason == PROVIDER_EXECUTION_DEFAULT_DENIED:
            return GitHubOrgInventoryLiveError(GITHUB_LIVE_PROVIDER_DEFAULT_DENIED)
        if reason == PROVIDER_EXECUTION_ACK_REQUIRED:
            return GitHubOrgInventoryLiveError(PROVIDER_EXECUTION_ACK_REQUIRED)
        return GitHubOrgInventoryLiveError(GITHUB_UNKNOWN_LIVE_INVENTORY_FAILURE)
    if isinstance(exc, github.GitHubConnectorError):
        if exc.reason_code == github.GITHUB_CONNECTOR_TRANSPORT_MISSING:
            return GitHubOrgInventoryLiveError(GITHUB_TRANSPORT_ERROR)
        if exc.reason_code == github.GITHUB_ORG_INVENTORY_RESPONSE_MALFORMED:
            return GitHubOrgInventoryLiveError(GITHUB_RESPONSE_MALFORMED)
        if exc.reason_code == github.GITHUB_ORG_INVENTORY_RESPONSE_CONTRACT_MISMATCH:
            return GitHubOrgInventoryLiveError(GITHUB_RESPONSE_CONTRACT_MISMATCH)
        if exc.reason_code == github.GITHUB_ORG_INVENTORY_CONTRACT_INVALID:
            return GitHubOrgInventoryLiveError(GITHUB_RESPONSE_CONTRACT_MISMATCH)
        return GitHubOrgInventoryLiveError(GITHUB_UNKNOWN_LIVE_INVENTORY_FAILURE)
    if isinstance(exc, TimeoutError | socket.timeout):
        return GitHubOrgInventoryLiveError(GITHUB_TIMEOUT)
    if isinstance(exc, OSError):
        return GitHubOrgInventoryLiveError(GITHUB_TRANSPORT_ERROR)
    return GitHubOrgInventoryLiveError(GITHUB_UNKNOWN_LIVE_INVENTORY_FAILURE)


def _auth_status_for_failure(failure_class: str) -> str:
    if failure_class == GITHUB_AUTH_FAILED:
        return GITHUB_AUTH_FAILED
    if failure_class in {
        GITHUB_PERMISSION_DENIED,
        GITHUB_ORG_NOT_FOUND_OR_NO_ACCESS,
        GITHUB_RATE_LIMITED,
        GITHUB_SERVER_ERROR,
        GITHUB_TRANSPORT_ERROR,
        GITHUB_TIMEOUT,
        GITHUB_RESPONSE_MALFORMED,
        GITHUB_RESPONSE_CONTRACT_MISMATCH,
        GITHUB_EMPTY_ORG_INVENTORY,
        GITHUB_UNKNOWN_LIVE_INVENTORY_FAILURE,
    }:
        return STATUS_CLASS_PASS
    return STATUS_NOT_CHECKED


def _permission_status_for_failure(failure_class: str) -> str:
    if failure_class == GITHUB_PERMISSION_DENIED:
        return GITHUB_PERMISSION_DENIED
    if failure_class == GITHUB_ORG_NOT_FOUND_OR_NO_ACCESS:
        return GITHUB_ORG_NOT_FOUND_OR_NO_ACCESS
    if failure_class == GITHUB_AUTH_FAILED:
        return STATUS_NOT_CHECKED
    if failure_class in {
        GITHUB_RATE_LIMITED,
        GITHUB_SERVER_ERROR,
        GITHUB_TRANSPORT_ERROR,
        GITHUB_TIMEOUT,
        GITHUB_RESPONSE_MALFORMED,
        GITHUB_RESPONSE_CONTRACT_MISMATCH,
        GITHUB_EMPTY_ORG_INVENTORY,
        GITHUB_UNKNOWN_LIVE_INVENTORY_FAILURE,
    }:
        return STATUS_CLASS_PASS
    return STATUS_NOT_CHECKED


def _transport_status_for_failure(failure_class: str) -> str:
    if failure_class in {GITHUB_TRANSPORT_ERROR, GITHUB_TIMEOUT}:
        return failure_class
    if failure_class in {
        GITHUB_AUTH_FAILED,
        GITHUB_PERMISSION_DENIED,
        GITHUB_ORG_NOT_FOUND_OR_NO_ACCESS,
        GITHUB_RATE_LIMITED,
        GITHUB_SERVER_ERROR,
        GITHUB_RESPONSE_MALFORMED,
        GITHUB_RESPONSE_CONTRACT_MISMATCH,
        GITHUB_EMPTY_ORG_INVENTORY,
        GITHUB_UNKNOWN_LIVE_INVENTORY_FAILURE,
    }:
        return STATUS_CLASS_PASS
    return STATUS_TRANSPORT_NOT_RUN


def _response_status_for_failure(failure_class: str) -> str:
    if failure_class in {GITHUB_RESPONSE_MALFORMED, GITHUB_RESPONSE_CONTRACT_MISMATCH}:
        return failure_class
    if failure_class in {
        GITHUB_AUTH_FAILED,
        GITHUB_PERMISSION_DENIED,
        GITHUB_ORG_NOT_FOUND_OR_NO_ACCESS,
        GITHUB_RATE_LIMITED,
        GITHUB_SERVER_ERROR,
        GITHUB_TRANSPORT_ERROR,
        GITHUB_TIMEOUT,
        GITHUB_EMPTY_ORG_INVENTORY,
        GITHUB_UNKNOWN_LIVE_INVENTORY_FAILURE,
    }:
        return STATUS_NOT_CHECKED
    return STATUS_NOT_CHECKED


def _org_visibility_for_failure(failure_class: str) -> str:
    if failure_class == GITHUB_EMPTY_ORG_INVENTORY:
        return GITHUB_EMPTY_ORG_INVENTORY
    if failure_class == GITHUB_ORG_NOT_FOUND_OR_NO_ACCESS:
        return GITHUB_ORG_NOT_FOUND_OR_NO_ACCESS
    return COUNT_NOT_OBSERVED


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


def _safe_count_class(value: Any) -> str:
    if value in {COUNT_ZERO, COUNT_NONZERO, COUNT_NOT_OBSERVED}:
        return str(value)
    return COUNT_NOT_OBSERVED


def _assert_safe(value: Mapping[str, Any]) -> None:
    if inspect_operator_output(value).safe is not True:
        raise ValueError("github_org_inventory_unsafe")
