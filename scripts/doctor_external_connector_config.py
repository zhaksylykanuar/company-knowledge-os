#!/usr/bin/env python
"""Read-only external connector configuration doctor."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.services.external_connector_config import (  # noqa: E402
    READINESS_READY,
    external_connector_config_doctor_providers,
    external_connector_config_doctor_summary,
)
from app.services.atlassian_api_profiles import (  # noqa: E402
    atlassian_api_profile_summary,
)
from app.services.guarded_execution_contracts import (  # noqa: E402
    validate_external_connector_config_doctor_contract,
)
from app.services.local_connector_env import (  # noqa: E402
    add_connector_env_file_arguments,
    connector_env_cli_kwargs,
    load_local_connector_environment,
)
from app.services.operator_output_sanitizer import inspect_operator_output  # noqa: E402

REPORT_KIND = "external_connector_config_doctor"
STATUS_PASS = "pass"
STATUS_FAIL = "fail"
CONFIG_DOCTOR_PASSED = "external_connector_config_doctor_passed"
CONFIG_DOCTOR_FAILED = "external_connector_config_doctor_failed"
CONFIG_DOCTOR_OUTPUT_UNSAFE = "external_connector_config_doctor_output_unsafe"
CONFIG_DOCTOR_CONTRACT_INVALID = "external_connector_config_doctor_contract_invalid"
SCHEDULER_EXECUTION_DISABLED = "disabled"


def run_external_connector_config_doctor(
    *,
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
    try:
        providers = external_connector_config_doctor_providers(environ=environment)
        summary = external_connector_config_doctor_summary(environ=environment)
        credential_profiles = atlassian_api_profile_summary(environ=environment)
        summary = {
            **summary,
            "jira_readonly_profile_status": credential_profiles[
                "jira_readonly_profile_status"
            ],
            "jira_write_profile_status": credential_profiles[
                "jira_write_profile_status"
            ],
            "atlassian_admin_scoped_profile_status": credential_profiles[
                "atlassian_admin_scoped_profile_status"
            ],
            "atlassian_admin_unscoped_profile_status": credential_profiles[
                "atlassian_admin_unscoped_profile_status"
            ],
            "org_id_presence_class": credential_profiles["org_id_presence_class"],
            "write_operations": credential_profiles["write_operations"],
            "admin_live_calls": credential_profiles["admin_live_calls"],
        }
        checks = _checks(providers)
        result = {
            "status": STATUS_PASS,
            "reason_code": None,
            "report_kind": REPORT_KIND,
            "no_send": True,
            "no_provider_calls": True,
            "no_source_of_truth_mutation": True,
            "scheduler_execution": SCHEDULER_EXECUTION_DISABLED,
            "providers": providers,
            "summary": summary,
            "credential_profiles": credential_profiles,
            "checks": checks,
            "diagnostics": {
                "provider_count": summary["provider_count"],
                "configured_provider_count": summary["configured_provider_count"],
                "partially_configured_provider_count": summary[
                    "partially_configured_provider_count"
                ],
                "not_configured_provider_count": summary[
                    "not_configured_provider_count"
                ],
                "live_readonly_ready_provider_count": summary[
                    "live_readonly_ready_provider_count"
                ],
                "missing_required_variable_count": summary[
                    "missing_required_variable_count"
                ],
                "check_count": len(checks),
                "failed_check_count": 0,
                "no_live_calls": summary["no_live_calls"],
                "jira_readonly_profile_status": credential_profiles[
                    "jira_readonly_profile_status"
                ],
                "jira_write_profile_status": credential_profiles[
                    "jira_write_profile_status"
                ],
                "atlassian_admin_scoped_profile_status": credential_profiles[
                    "atlassian_admin_scoped_profile_status"
                ],
                "atlassian_admin_unscoped_profile_status": credential_profiles[
                    "atlassian_admin_unscoped_profile_status"
                ],
                "org_id_presence_class": credential_profiles["org_id_presence_class"],
                "write_operations": credential_profiles["write_operations"],
                "admin_live_calls": credential_profiles["admin_live_calls"],
                "connector_env_file": dict(env_result.diagnostics),
            },
        }
        return _finalize_result(result)
    except Exception:
        return _failure_report(CONFIG_DOCTOR_FAILED)


def _checks(providers: Mapping[str, Mapping[str, Any]]) -> list[dict[str, str]]:
    return [
        {
            "name": f"{provider_key}_config_presence",
            "status": STATUS_PASS,
            "state": str(provider.get("configured_status", "unknown")),
            "live_readonly_readiness": str(
                provider.get("live_readonly_readiness", "not_ready")
            ),
        }
        for provider_key, provider in sorted(providers.items())
    ] + [
        {
            "name": "live_readonly_smoke_ready_count",
            "status": STATUS_PASS,
            "state": "ready"
            if any(
                provider.get("live_readonly_readiness") == READINESS_READY
                for provider in providers.values()
            )
            else "not_ready",
            "live_readonly_readiness": "counts_only",
        }
    ]


def _finalize_result(result: dict[str, Any]) -> dict[str, Any]:
    safety = inspect_operator_output(result)
    if not safety.safe:
        return _failure_report(
            CONFIG_DOCTOR_OUTPUT_UNSAFE,
            operator_output_safety=safety.as_dict(),
        )

    validation = validate_external_connector_config_doctor_contract(result).as_dict()
    result["contract_validation"] = validation
    if validation["validation_status"] != STATUS_PASS:
        return _failure_report(
            CONFIG_DOCTOR_CONTRACT_INVALID,
            contract_validation=validation,
        )
    return result


def _failure_report(
    reason_code: str,
    *,
    contract_validation: Mapping[str, Any] | None = None,
    operator_output_safety: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    result = {
        "status": STATUS_FAIL,
        "reason_code": _safe_reason_code(reason_code),
        "report_kind": REPORT_KIND,
        "no_send": True,
        "no_provider_calls": True,
        "no_source_of_truth_mutation": True,
        "scheduler_execution": SCHEDULER_EXECUTION_DISABLED,
        "providers": {},
        "summary": {},
        "credential_profiles": {},
        "checks": [],
        "diagnostics": {
            "provider_count": 0,
            "configured_provider_count": 0,
            "partially_configured_provider_count": 0,
            "not_configured_provider_count": 0,
            "live_readonly_ready_provider_count": 0,
            "missing_required_variable_count": 0,
            "check_count": 0,
            "failed_check_count": 1,
            "no_live_calls": "absent",
            "operator_output_safety": dict(operator_output_safety or {}),
        },
    }
    result["contract_validation"] = dict(
        contract_validation
        or validate_external_connector_config_doctor_contract(result).as_dict()
    )
    return result


def _safe_reason_code(value: str) -> str:
    cleaned = "".join(
        character if character.isalnum() or character == "_" else "_"
        for character in value.casefold()
    ).strip("_")
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned or CONFIG_DOCTOR_FAILED


def _json_text(value: Mapping[str, Any]) -> str:
    return json.dumps(dict(value), indent=2, sort_keys=True) + "\n"


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output strict JSON. This is the default and only output mode.",
    )
    add_connector_env_file_arguments(parser)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    result = run_external_connector_config_doctor(**connector_env_cli_kwargs(args))
    print(_json_text(result), end="")
    return 0 if result["status"] == STATUS_PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
