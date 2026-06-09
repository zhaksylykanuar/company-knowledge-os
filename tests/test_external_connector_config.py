from __future__ import annotations

import json
from typing import Any

from app.services.external_connector_config import (
    ATLASSIAN_ADMIN_ENV_KEYS,
    GITHUB_ENV_KEYS,
    GITHUB_TARGET_ORG_ENV_KEYS,
    JIRA_ENV_KEYS,
    JIRA_WRITE_ENV_KEYS,
    external_connector_config_doctor_providers,
    external_connector_config_doctor_summary,
    external_connector_config_specs,
    is_provider_configured,
)
from app.services.operator_output_sanitizer import inspect_operator_output


def _unsafe_values() -> tuple[str, ...]:
    return (
        "https" + "://config.invalid/path",
        "operator" + "@" + "config.invalid",
        "bot_token config value",
        "a" * 64,
        "postgres" + "://config.invalid/db",
        "provider_payload config body",
        "source_object_id config body",
        "rendered_digest_text config body",
        "grouped_preview_text config body",
        "chunk_text config body",
        "item_title config body",
        "raw_config_doctor_json config body",
        "PROJECT" + "-123",
        "PR" + "-456",
    )


def _assert_no_raw_unsafe_values(value: Any) -> None:
    serialized = json.dumps(value, sort_keys=True)
    for raw_value in _unsafe_values():
        assert raw_value not in serialized


def _assert_config_output_safe(value: Any) -> None:
    assert inspect_operator_output(value).safe is True
    _assert_no_raw_unsafe_values(value)


def _configured_env() -> dict[str, str]:
    return {
        **dict.fromkeys(GITHUB_ENV_KEYS, "hidden_value"),
        **dict.fromkeys(JIRA_ENV_KEYS, "hidden_value"),
    }


def test_external_connector_config_specs_use_safe_metadata_only() -> None:
    specs = external_connector_config_specs()

    assert {spec["provider_key"] for spec in specs} == {"github", "jira"}
    assert all(spec["no_send"] is True for spec in specs)
    assert all(spec["no_source_of_truth_mutation"] is True for spec in specs)
    assert all(spec["scheduler_execution"] == "disabled" for spec in specs)
    assert any("FOS_GITHUB_READONLY_TOKEN" in spec["required_environment_variable_names"] for spec in specs)
    assert any("FOS_JIRA_READONLY_TOKEN" in spec["required_environment_variable_names"] for spec in specs)
    github_spec = next(spec for spec in specs if spec["provider_key"] == "github")
    assert github_spec["optional_environment_variable_names"] == [
        *GITHUB_TARGET_ORG_ENV_KEYS
    ]
    jira_spec = next(spec for spec in specs if spec["provider_key"] == "jira")
    assert set(jira_spec["optional_environment_variable_names"]) == {
        *JIRA_WRITE_ENV_KEYS,
        *ATLASSIAN_ADMIN_ENV_KEYS,
    }
    _assert_config_output_safe(specs)


def test_absent_connector_config_reports_not_configured() -> None:
    providers = external_connector_config_doctor_providers(environ={})
    summary = external_connector_config_doctor_summary(environ={})

    assert providers["github"]["configured_status"] == "not_configured"
    assert providers["jira"]["configured_status"] == "not_configured"
    assert providers["github"]["missing_required_variable_count"] == len(GITHUB_ENV_KEYS)
    assert providers["jira"]["missing_required_variable_count"] == len(JIRA_ENV_KEYS)
    assert summary["not_configured_provider_count"] == 2
    assert summary["live_readonly_ready_provider_count"] == 0
    assert providers["github"]["target_org_config_status"] == "missing"
    assert providers["github"]["target_org_planning_status"] == (
        "default_target_org_metadata_available"
    )
    assert summary["github_target_org_config_status"] == "missing"
    assert summary["github_target_org_planning_status"] == (
        "default_target_org_metadata_available"
    )
    assert summary["no_live_calls"] == "absent"
    _assert_config_output_safe({"providers": providers, "summary": summary})


def test_placeholder_connector_config_reports_not_configured() -> None:
    environment = {
        **dict.fromkeys(GITHUB_ENV_KEYS, "<set locally>"),
        **dict.fromkeys(JIRA_ENV_KEYS, "placeholder"),
    }
    providers = external_connector_config_doctor_providers(environ=environment)
    summary = external_connector_config_doctor_summary(environ=environment)

    assert providers["github"]["configured_status"] == "not_configured"
    assert providers["jira"]["configured_status"] == "not_configured"
    assert providers["github"]["present_required_variable_count"] == 0
    assert providers["jira"]["present_required_variable_count"] == 0
    assert summary["not_configured_provider_count"] == 2
    assert is_provider_configured("github", environment) is False
    assert is_provider_configured("jira", environment) is False
    assert providers["github"]["target_org_config_status"] == "missing"
    _assert_config_output_safe({"providers": providers, "summary": summary})


def test_partial_connector_config_reports_partially_configured() -> None:
    providers = external_connector_config_doctor_providers(
        environ={
            GITHUB_ENV_KEYS[0]: "hidden_value",
            JIRA_ENV_KEYS[0]: "hidden_value",
        }
    )

    assert providers["github"]["configured_status"] == "partially_configured"
    assert providers["jira"]["configured_status"] == "partially_configured"
    assert providers["github"]["live_readonly_readiness"] == (
        "blocked_by_missing_config"
    )
    assert providers["jira"]["live_readonly_readiness"] == "blocked_by_missing_config"
    _assert_config_output_safe(providers)


def test_complete_connector_config_reports_configured_ready_without_values() -> None:
    environment = _configured_env()
    providers = external_connector_config_doctor_providers(environ=environment)
    summary = external_connector_config_doctor_summary(environ=environment)

    assert providers["github"]["configured_status"] == "configured"
    assert providers["jira"]["configured_status"] == "configured"
    assert providers["github"]["live_readonly_readiness"] == "ready"
    assert providers["jira"]["live_readonly_readiness"] == "ready"
    assert providers["github"]["target_org_config_status"] == "missing"
    assert providers["github"]["target_org_planning_status"] == (
        "default_target_org_metadata_available"
    )
    assert set(providers["jira"]["optional_environment_variable_names"]) == {
        *JIRA_WRITE_ENV_KEYS,
        *ATLASSIAN_ADMIN_ENV_KEYS,
    }
    assert summary["configured_provider_count"] == 2
    assert summary["live_readonly_ready_provider_count"] == 2
    assert is_provider_configured("github", environment) is True
    assert is_provider_configured("jira", environment) is True
    serialized = json.dumps({"providers": providers, "summary": summary}, sort_keys=True)
    for raw_value in set(environment.values()):
        assert raw_value not in serialized
    _assert_config_output_safe({"providers": providers, "summary": summary})


def test_github_target_org_config_is_optional_and_value_hidden() -> None:
    environment = {
        **_configured_env(),
        GITHUB_TARGET_ORG_ENV_KEYS[0]: "qtwin-io",
    }
    providers = external_connector_config_doctor_providers(environ=environment)
    summary = external_connector_config_doctor_summary(environ=environment)

    assert providers["github"]["configured_status"] == "configured"
    assert providers["github"]["target_org_config_status"] == "present"
    assert providers["github"]["target_org_planning_status"] == (
        "configured_for_future_inventory"
    )
    assert summary["github_target_org_config_status"] == "present"
    assert summary["github_target_org_planning_status"] == (
        "configured_for_future_inventory"
    )
    serialized = json.dumps({"providers": providers, "summary": summary}, sort_keys=True)
    assert "qtwin-io" not in serialized
    _assert_config_output_safe({"providers": providers, "summary": summary})


def test_connector_config_values_are_hidden_for_unsafe_looking_values() -> None:
    environment = {
        **dict.fromkeys(GITHUB_ENV_KEYS, _unsafe_values()[0]),
        **dict.fromkeys(JIRA_ENV_KEYS, _unsafe_values()[1]),
    }
    providers = external_connector_config_doctor_providers(environ=environment)

    assert providers["github"]["configured_status"] == "configured"
    assert providers["jira"]["configured_status"] == "configured"
    serialized = json.dumps(providers, sort_keys=True)
    for raw_value in set(environment.values()):
        assert raw_value not in serialized
    _assert_config_output_safe(providers)
