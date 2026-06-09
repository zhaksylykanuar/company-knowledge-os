from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from app.services.external_connector_config import (
    JIRA_ENV_KEYS,
    JIRA_WRITE_ENV_KEYS,
    PRESENCE_MISSING,
    PRESENCE_PRESENT,
    STATUS_CONFIGURED,
    STATUS_NOT_CONFIGURED,
    STATUS_PARTIALLY_CONFIGURED,
    is_configured_environment_value,
)
from app.services.operator_output_sanitizer import inspect_operator_output

PROFILE_JIRA_READONLY = "jira_readonly_data_api"
PROFILE_JIRA_WRITE = "jira_write_site_api"
PROFILE_ATLASSIAN_ADMIN_SCOPED = "atlassian_admin_org_api_scoped"
PROFILE_ATLASSIAN_ADMIN_UNSCOPED = "atlassian_admin_org_api_unscoped"

AUTH_BASIC_EMAIL_API_TOKEN = "basic_email_api_token"
AUTH_BEARER_ADMIN_API_KEY = "bearer_admin_api_key"
ENDPOINT_JIRA_SITE_REST_API = "jira_site_rest_api"
ENDPOINT_ATLASSIAN_ADMIN_API = "atlassian_admin_api"

OPERATION_JIRA_READONLY_INVENTORY = "jira_readonly_inventory"
OPERATION_JIRA_CREATION_WRITE_DRY_RUN = "jira_creation_write_dry_run"
OPERATION_ATLASSIAN_ORG_ADMIN_DIAGNOSTICS_DRY_RUN = (
    "atlassian_org_admin_diagnostics_dry_run"
)

LIVE_READ_GATED = "gated"
LIVE_READ_CONFIGURED = "configured"
LIVE_READ_NOT_CONFIGURED = "not_configured"
LIVE_WRITE_DISABLED = "disabled"
LIVE_WRITE_DRY_RUN_ONLY = "dry_run_only"
ADMIN_LIVE_CALLS_NOT_RUN = "not_run"
WRITE_OPERATIONS_DISABLED = "disabled"
SCHEDULER_EXECUTION_DISABLED = "disabled"
COUNT_ZERO = "zero_count"
COUNT_NONZERO = "nonzero_count"

ORG_ID_ENV_KEY = "FOS_ATLASSIAN_ORG_ID"
SCOPED_ADMIN_TOKEN_ENV_KEY = "FOS_ATLASSIAN_ADMIN_API_TOKEN_SCOPED"
UNSCOPED_ADMIN_TOKEN_ENV_KEY = "FOS_ATLASSIAN_ADMIN_API_TOKEN_UNSCOPED"


@dataclass(frozen=True)
class AtlassianApiProfileSpec:
    profile_key: str
    auth_class: str
    endpoint_class: str
    intended_operation_class: str
    required_environment_variable_names: tuple[str, ...]
    live_write_status: str


PROFILE_SPECS = (
    AtlassianApiProfileSpec(
        profile_key=PROFILE_JIRA_READONLY,
        auth_class=AUTH_BASIC_EMAIL_API_TOKEN,
        endpoint_class=ENDPOINT_JIRA_SITE_REST_API,
        intended_operation_class=OPERATION_JIRA_READONLY_INVENTORY,
        required_environment_variable_names=JIRA_ENV_KEYS,
        live_write_status=LIVE_WRITE_DISABLED,
    ),
    AtlassianApiProfileSpec(
        profile_key=PROFILE_JIRA_WRITE,
        auth_class=AUTH_BASIC_EMAIL_API_TOKEN,
        endpoint_class=ENDPOINT_JIRA_SITE_REST_API,
        intended_operation_class=OPERATION_JIRA_CREATION_WRITE_DRY_RUN,
        required_environment_variable_names=(JIRA_ENV_KEYS[0], *JIRA_WRITE_ENV_KEYS),
        live_write_status=LIVE_WRITE_DRY_RUN_ONLY,
    ),
    AtlassianApiProfileSpec(
        profile_key=PROFILE_ATLASSIAN_ADMIN_SCOPED,
        auth_class=AUTH_BEARER_ADMIN_API_KEY,
        endpoint_class=ENDPOINT_ATLASSIAN_ADMIN_API,
        intended_operation_class=OPERATION_ATLASSIAN_ORG_ADMIN_DIAGNOSTICS_DRY_RUN,
        required_environment_variable_names=(
            ORG_ID_ENV_KEY,
            SCOPED_ADMIN_TOKEN_ENV_KEY,
        ),
        live_write_status=LIVE_WRITE_DRY_RUN_ONLY,
    ),
    AtlassianApiProfileSpec(
        profile_key=PROFILE_ATLASSIAN_ADMIN_UNSCOPED,
        auth_class=AUTH_BEARER_ADMIN_API_KEY,
        endpoint_class=ENDPOINT_ATLASSIAN_ADMIN_API,
        intended_operation_class=OPERATION_ATLASSIAN_ORG_ADMIN_DIAGNOSTICS_DRY_RUN,
        required_environment_variable_names=(
            ORG_ID_ENV_KEY,
            UNSCOPED_ADMIN_TOKEN_ENV_KEY,
        ),
        live_write_status=LIVE_WRITE_DISABLED,
    ),
)


def atlassian_api_profile_summary(
    *,
    environ: Mapping[str, str],
) -> dict[str, Any]:
    profiles = {
        spec.profile_key: _profile_status(spec, environ)
        for spec in PROFILE_SPECS
    }
    configured_count = sum(
        1
        for profile in profiles.values()
        if profile["profile_status"] == STATUS_CONFIGURED
    )
    missing_count = len(profiles) - configured_count
    summary = {
        "report_kind": "atlassian_api_profile_summary",
        "profile_count": len(profiles),
        "configured_profile_count": configured_count,
        "configured_profile_count_class": _zero_nonzero_count_class(configured_count),
        "missing_profile_count": missing_count,
        "missing_profile_count_class": _zero_nonzero_count_class(missing_count),
        "jira_readonly_profile_status": profiles[PROFILE_JIRA_READONLY][
            "profile_status"
        ],
        "jira_write_profile_status": profiles[PROFILE_JIRA_WRITE]["profile_status"],
        "atlassian_admin_scoped_profile_status": profiles[
            PROFILE_ATLASSIAN_ADMIN_SCOPED
        ]["profile_status"],
        "atlassian_admin_unscoped_profile_status": profiles[
            PROFILE_ATLASSIAN_ADMIN_UNSCOPED
        ]["profile_status"],
        "org_id_presence_class": _presence_status(environ, ORG_ID_ENV_KEY),
        "values_visibility": "hidden",
        "write_operations": WRITE_OPERATIONS_DISABLED,
        "admin_live_calls": ADMIN_LIVE_CALLS_NOT_RUN,
        "profiles": profiles,
        "no_send": True,
        "no_provider_calls": True,
        "no_source_of_truth_mutation": True,
        "scheduler_execution": SCHEDULER_EXECUTION_DISABLED,
    }
    _assert_safe(summary)
    return summary


def _profile_status(
    spec: AtlassianApiProfileSpec,
    environ: Mapping[str, str],
) -> dict[str, Any]:
    required_variables = [
        {
            "variable_name": variable_name,
            "presence_status": _presence_status(environ, variable_name),
            "value_visibility": "hidden",
        }
        for variable_name in spec.required_environment_variable_names
    ]
    present_count = sum(
        1
        for variable in required_variables
        if variable["presence_status"] == PRESENCE_PRESENT
    )
    profile_status = _configured_status(
        required_count=len(required_variables),
        present_count=present_count,
    )
    return {
        "profile_key": spec.profile_key,
        "profile_status": profile_status,
        "auth_class": spec.auth_class,
        "endpoint_class": spec.endpoint_class,
        "intended_operation_class": spec.intended_operation_class,
        "live_read_status": _live_read_status(profile_status),
        "live_write_status": spec.live_write_status,
        "required_environment_variables": required_variables,
        "required_environment_variable_count": len(required_variables),
        "present_required_variable_count": present_count,
        "missing_required_variable_count": len(required_variables) - present_count,
        "org_id_presence_class": _presence_status(environ, ORG_ID_ENV_KEY)
        if spec.endpoint_class == ENDPOINT_ATLASSIAN_ADMIN_API
        else "not_required",
        "values_visibility": "hidden",
        "write_operations": WRITE_OPERATIONS_DISABLED,
        "admin_live_calls": ADMIN_LIVE_CALLS_NOT_RUN,
        "no_send": True,
        "no_provider_calls": True,
        "no_source_of_truth_mutation": True,
        "scheduler_execution": SCHEDULER_EXECUTION_DISABLED,
    }


def _presence_status(environ: Mapping[str, str], variable_name: str) -> str:
    return (
        PRESENCE_PRESENT
        if is_configured_environment_value(environ.get(variable_name))
        else PRESENCE_MISSING
    )


def _configured_status(*, required_count: int, present_count: int) -> str:
    if present_count == required_count:
        return STATUS_CONFIGURED
    if present_count == 0:
        return STATUS_NOT_CONFIGURED
    return STATUS_PARTIALLY_CONFIGURED


def _live_read_status(profile_status: str) -> str:
    if profile_status == STATUS_CONFIGURED:
        return LIVE_READ_GATED
    if profile_status == STATUS_PARTIALLY_CONFIGURED:
        return LIVE_READ_NOT_CONFIGURED
    return LIVE_READ_NOT_CONFIGURED


def _zero_nonzero_count_class(count: int) -> str:
    return COUNT_ZERO if count == 0 else COUNT_NONZERO


def _assert_safe(value: Mapping[str, Any]) -> None:
    if inspect_operator_output(value).safe is not True:
        raise ValueError("atlassian_api_profile_summary_unsafe")
