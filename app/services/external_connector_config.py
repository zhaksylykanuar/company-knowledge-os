from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import os
from typing import Any

from app.services.operator_output_sanitizer import inspect_operator_output

PROVIDER_GITHUB = "github"
PROVIDER_JIRA = "jira"

GITHUB_ENV_KEYS = (
    "FOS_GITHUB_READONLY_TOKEN",
    "FOS_GITHUB_READONLY_ACCOUNT",
)
JIRA_ENV_KEYS = (
    "FOS_JIRA_READONLY_SITE",
    "FOS_JIRA_READONLY_USER",
    "FOS_JIRA_READONLY_TOKEN",
)

STATUS_CONFIGURED = "configured"
STATUS_NOT_CONFIGURED = "not_configured"
STATUS_PARTIALLY_CONFIGURED = "partially_configured"
STATUS_UNKNOWN = "unknown"

READINESS_READY = "ready"
READINESS_NOT_READY = "not_ready"
READINESS_BLOCKED_BY_MISSING_CONFIG = "blocked_by_missing_config"

PRESENCE_PRESENT = "present"
PRESENCE_MISSING = "missing"

ACKNOWLEDGEMENT_CLASS = "provider_execution_guard_ack_required"
SMOKE_COMMAND_GITHUB = "github_live_readonly_smoke"
SMOKE_COMMAND_JIRA = "jira_live_readonly_smoke"
ACTION_RUN_GITHUB_SMOKE = "run_gated_github_live_readonly_smoke"
ACTION_RUN_JIRA_SMOKE = "run_gated_jira_live_readonly_smoke"
ACTION_SET_GITHUB_CONFIG = "set_github_readonly_config"
ACTION_SET_JIRA_CONFIG = "set_jira_readonly_config"

CONFIG_DOCTOR_PRESENT = "present"
NO_LIVE_CALLS_IN_CONFIG_DOCTOR = "absent"
SCHEDULER_EXECUTION_DISABLED = "disabled"


@dataclass(frozen=True)
class ExternalConnectorConfigSpec:
    provider_key: str
    required_environment_variable_names: tuple[str, ...]
    optional_environment_variable_names: tuple[str, ...]
    expected_smoke_command_class: str
    missing_config_action_class: str
    ready_action_class: str
    required_acknowledgement_class: str = ACKNOWLEDGEMENT_CLASS
    no_send: bool = True
    no_source_of_truth_mutation: bool = True
    scheduler_execution: str = SCHEDULER_EXECUTION_DISABLED

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider_key": self.provider_key,
            "required_environment_variable_names": list(
                self.required_environment_variable_names
            ),
            "optional_environment_variable_names": list(
                self.optional_environment_variable_names
            ),
            "required_environment_variable_count": len(
                self.required_environment_variable_names
            ),
            "optional_environment_variable_count": len(
                self.optional_environment_variable_names
            ),
            "expected_smoke_command_class": self.expected_smoke_command_class,
            "required_acknowledgement_class": self.required_acknowledgement_class,
            "missing_config_action_class": self.missing_config_action_class,
            "ready_action_class": self.ready_action_class,
            "no_send": self.no_send,
            "no_source_of_truth_mutation": self.no_source_of_truth_mutation,
            "scheduler_execution": self.scheduler_execution,
        }


CONNECTOR_CONFIG_SPECS = (
    ExternalConnectorConfigSpec(
        provider_key=PROVIDER_GITHUB,
        required_environment_variable_names=GITHUB_ENV_KEYS,
        optional_environment_variable_names=(),
        expected_smoke_command_class=SMOKE_COMMAND_GITHUB,
        missing_config_action_class=ACTION_SET_GITHUB_CONFIG,
        ready_action_class=ACTION_RUN_GITHUB_SMOKE,
    ),
    ExternalConnectorConfigSpec(
        provider_key=PROVIDER_JIRA,
        required_environment_variable_names=JIRA_ENV_KEYS,
        optional_environment_variable_names=(),
        expected_smoke_command_class=SMOKE_COMMAND_JIRA,
        missing_config_action_class=ACTION_SET_JIRA_CONFIG,
        ready_action_class=ACTION_RUN_JIRA_SMOKE,
    ),
)


def external_connector_config_specs() -> tuple[dict[str, Any], ...]:
    specs = tuple(spec.as_dict() for spec in CONNECTOR_CONFIG_SPECS)
    _assert_config_output_safe(specs)
    return specs


def external_connector_config_doctor_summary(
    *,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    environment = environ if environ is not None else os.environ
    providers = {
        spec.provider_key: _provider_config_summary(spec, environment)
        for spec in CONNECTOR_CONFIG_SPECS
    }
    configured_count = sum(
        1
        for provider in providers.values()
        if provider["configured_status"] == STATUS_CONFIGURED
    )
    partially_configured_count = sum(
        1
        for provider in providers.values()
        if provider["configured_status"] == STATUS_PARTIALLY_CONFIGURED
    )
    not_configured_count = sum(
        1
        for provider in providers.values()
        if provider["configured_status"] == STATUS_NOT_CONFIGURED
    )
    ready_count = sum(
        1
        for provider in providers.values()
        if provider["live_readonly_readiness"] == READINESS_READY
    )
    missing_required_variable_count = sum(
        int(provider["missing_required_variable_count"])
        for provider in providers.values()
    )
    summary = {
        "external_connector_config_doctor": CONFIG_DOCTOR_PRESENT,
        "provider_count": len(providers),
        "configured_provider_count": configured_count,
        "partially_configured_provider_count": partially_configured_count,
        "not_configured_provider_count": not_configured_count,
        "live_readonly_ready_provider_count": ready_count,
        "missing_required_variable_count": missing_required_variable_count,
        "github_config_status": providers[PROVIDER_GITHUB]["configured_status"],
        "jira_config_status": providers[PROVIDER_JIRA]["configured_status"],
        "github_live_readonly_ready": _ready_status(providers[PROVIDER_GITHUB]),
        "jira_live_readonly_ready": _ready_status(providers[PROVIDER_JIRA]),
        "no_live_calls": NO_LIVE_CALLS_IN_CONFIG_DOCTOR,
        "no_send": True,
        "no_source_of_truth_mutation": True,
        "scheduler_execution": SCHEDULER_EXECUTION_DISABLED,
    }
    _assert_config_output_safe(summary)
    return summary


def external_connector_config_doctor_providers(
    *,
    environ: Mapping[str, str] | None = None,
) -> dict[str, dict[str, Any]]:
    environment = environ if environ is not None else os.environ
    providers = {
        spec.provider_key: _provider_config_summary(spec, environment)
        for spec in CONNECTOR_CONFIG_SPECS
    }
    _assert_config_output_safe(providers)
    return providers


def get_required_environment_variable_names(provider_key: str) -> tuple[str, ...]:
    spec = _get_spec(provider_key)
    return spec.required_environment_variable_names if spec else ()


def is_provider_configured(
    provider_key: str,
    environ: Mapping[str, str],
) -> bool:
    summary = _provider_config_summary(_get_required_spec(provider_key), environ)
    return summary["configured_status"] == STATUS_CONFIGURED


def _provider_config_summary(
    spec: ExternalConnectorConfigSpec,
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
    missing_count = len(required_variables) - present_count
    configured_status = _configured_status(
        required_count=len(required_variables),
        present_count=present_count,
    )
    live_readonly_readiness = (
        READINESS_READY
        if configured_status == STATUS_CONFIGURED
        else READINESS_BLOCKED_BY_MISSING_CONFIG
    )
    next_action_classes = (
        [spec.ready_action_class]
        if live_readonly_readiness == READINESS_READY
        else [spec.missing_config_action_class]
    )
    summary = {
        "provider_key": spec.provider_key,
        "configured_status": configured_status,
        "live_readonly_readiness": live_readonly_readiness,
        "required_environment_variables": required_variables,
        "optional_environment_variable_names": list(
            spec.optional_environment_variable_names
        ),
        "required_environment_variable_count": len(required_variables),
        "present_required_variable_count": present_count,
        "missing_required_variable_count": missing_count,
        "expected_smoke_command_class": spec.expected_smoke_command_class,
        "required_acknowledgement_class": spec.required_acknowledgement_class,
        "next_action_classes": next_action_classes,
        "no_send": True,
        "no_source_of_truth_mutation": True,
        "scheduler_execution": SCHEDULER_EXECUTION_DISABLED,
    }
    _assert_config_output_safe(summary)
    return summary


def _presence_status(environ: Mapping[str, str], variable_name: str) -> str:
    return PRESENCE_PRESENT if bool(environ.get(variable_name)) else PRESENCE_MISSING


def _configured_status(*, required_count: int, present_count: int) -> str:
    if required_count <= 0:
        return STATUS_UNKNOWN
    if present_count == required_count:
        return STATUS_CONFIGURED
    if present_count == 0:
        return STATUS_NOT_CONFIGURED
    return STATUS_PARTIALLY_CONFIGURED


def _ready_status(provider_summary: Mapping[str, Any]) -> str:
    return (
        READINESS_READY
        if provider_summary.get("live_readonly_readiness") == READINESS_READY
        else READINESS_NOT_READY
    )


def _get_spec(provider_key: str) -> ExternalConnectorConfigSpec | None:
    for spec in CONNECTOR_CONFIG_SPECS:
        if spec.provider_key == provider_key:
            return spec
    return None


def _get_required_spec(provider_key: str) -> ExternalConnectorConfigSpec:
    spec = _get_spec(provider_key)
    if spec is None:
        raise ValueError("external_connector_config_provider_unknown")
    return spec


def _assert_config_output_safe(value: Any) -> None:
    if inspect_operator_output(value).safe is not True:
        raise ValueError("external_connector_config_output_unsafe")
