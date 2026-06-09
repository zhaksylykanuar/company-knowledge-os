from __future__ import annotations

import json
from typing import Any

from app.services.atlassian_api_profiles import (
    AUTH_BASIC_EMAIL_API_TOKEN,
    AUTH_BEARER_ADMIN_API_KEY,
    ENDPOINT_ATLASSIAN_ADMIN_API,
    ENDPOINT_JIRA_SITE_REST_API,
    PROFILE_ATLASSIAN_ADMIN_SCOPED,
    PROFILE_ATLASSIAN_ADMIN_UNSCOPED,
    PROFILE_JIRA_READONLY,
    PROFILE_JIRA_WRITE,
    atlassian_api_profile_summary,
)
from app.services.external_connector_config import (
    ATLASSIAN_ADMIN_ENV_KEYS,
    JIRA_ENV_KEYS,
    JIRA_WRITE_ENV_KEYS,
)
from app.services.guarded_execution_contracts import (
    validate_atlassian_api_profile_summary_contract,
)
from app.services.operator_output_sanitizer import inspect_operator_output


def _unsafe_values() -> tuple[str, ...]:
    return (
        "https" + "://atlassian-profile.invalid/path",
        "operator" + "@" + "atlassian-profile.invalid",
        "bot_token profile value",
        "a" * 64,
        "postgres" + "://atlassian-profile.invalid/db",
        "provider_payload profile body",
        "source_object_id profile body",
        "PROJECT" + "-123",
        "ISSUE" + "-456",
        "issue title profile body",
    )


def _assert_safe(value: Any) -> None:
    serialized = json.dumps(value, sort_keys=True)
    for raw_value in _unsafe_values():
        assert raw_value not in serialized
    assert inspect_operator_output(value).safe is True


def _full_env() -> dict[str, str]:
    return {
        **dict.fromkeys(JIRA_ENV_KEYS, "hidden_value"),
        **dict.fromkeys(JIRA_WRITE_ENV_KEYS, "hidden_value"),
        **dict.fromkeys(ATLASSIAN_ADMIN_ENV_KEYS, "hidden_value"),
    }


def test_atlassian_api_profiles_are_separated_by_auth_and_endpoint_classes() -> None:
    summary = atlassian_api_profile_summary(environ=_full_env())

    readonly = summary["profiles"][PROFILE_JIRA_READONLY]
    write = summary["profiles"][PROFILE_JIRA_WRITE]
    scoped = summary["profiles"][PROFILE_ATLASSIAN_ADMIN_SCOPED]
    unscoped = summary["profiles"][PROFILE_ATLASSIAN_ADMIN_UNSCOPED]

    assert readonly["auth_class"] == AUTH_BASIC_EMAIL_API_TOKEN
    assert readonly["endpoint_class"] == ENDPOINT_JIRA_SITE_REST_API
    assert readonly["intended_operation_class"] == "jira_readonly_inventory"
    assert readonly["live_write_status"] == "disabled"
    assert write["auth_class"] == AUTH_BASIC_EMAIL_API_TOKEN
    assert write["endpoint_class"] == ENDPOINT_JIRA_SITE_REST_API
    assert write["intended_operation_class"] == "jira_creation_write_dry_run"
    assert write["live_write_status"] == "dry_run_only"
    assert scoped["auth_class"] == AUTH_BEARER_ADMIN_API_KEY
    assert scoped["endpoint_class"] == ENDPOINT_ATLASSIAN_ADMIN_API
    assert scoped["live_write_status"] == "dry_run_only"
    assert unscoped["auth_class"] == AUTH_BEARER_ADMIN_API_KEY
    assert unscoped["endpoint_class"] == ENDPOINT_ATLASSIAN_ADMIN_API
    assert unscoped["live_write_status"] == "disabled"
    assert summary["org_id_presence_class"] == "present"
    assert summary["write_operations"] == "disabled"
    assert summary["admin_live_calls"] == "not_run"
    assert validate_atlassian_api_profile_summary_contract(summary).passed is True
    _assert_safe(summary)


def test_atlassian_admin_tokens_are_optional_and_values_hidden() -> None:
    raw_value = "local_profile_value"
    summary = atlassian_api_profile_summary(environ=dict.fromkeys(JIRA_ENV_KEYS, raw_value))

    assert summary["jira_readonly_profile_status"] == "configured"
    assert summary["jira_write_profile_status"] == "partially_configured"
    assert summary["atlassian_admin_scoped_profile_status"] == "not_configured"
    assert summary["atlassian_admin_unscoped_profile_status"] == "not_configured"
    assert summary["org_id_presence_class"] == "missing"
    assert summary["configured_profile_count_class"] == "nonzero_count"
    assert summary["missing_profile_count_class"] == "nonzero_count"
    assert raw_value not in json.dumps(summary, sort_keys=True)
    _assert_safe(summary)


def test_placeholder_values_are_missing_and_org_id_never_echoes() -> None:
    environment = {
        **dict.fromkeys(JIRA_ENV_KEYS, "<set locally>"),
        **dict.fromkeys(JIRA_WRITE_ENV_KEYS, "placeholder"),
        **dict.fromkeys(ATLASSIAN_ADMIN_ENV_KEYS, "change-me"),
    }
    summary = atlassian_api_profile_summary(environ=environment)

    assert summary["jira_readonly_profile_status"] == "not_configured"
    assert summary["jira_write_profile_status"] == "not_configured"
    assert summary["atlassian_admin_scoped_profile_status"] == "not_configured"
    assert summary["atlassian_admin_unscoped_profile_status"] == "not_configured"
    assert summary["org_id_presence_class"] == "missing"
    serialized = json.dumps(summary, sort_keys=True)
    for raw_value in set(environment.values()):
        assert raw_value not in serialized
    _assert_safe(summary)
