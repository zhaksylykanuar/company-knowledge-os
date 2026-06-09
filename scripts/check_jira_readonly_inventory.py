#!/usr/bin/env python
"""Read-only Jira inventory and portfolio mapping report."""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.parse
import urllib.request
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.connectors import jira  # noqa: E402
from app.services.external_connector_config import (  # noqa: E402
    PROVIDER_JIRA,
    external_connector_config_doctor_providers,
)
from app.services.guarded_execution_contracts import (  # noqa: E402
    validate_jira_readonly_inventory_contract,
)
from app.services.jira_portfolio_mapping import (  # noqa: E402
    JIRA_INVENTORY_STATUS_CONFIGURED_NOT_EXECUTED,
    JIRA_INVENTORY_STATUS_LIVE_READONLY_VERIFIED,
    JIRA_INVENTORY_STATUS_NOT_CONFIGURED,
    JIRA_INVENTORY_STATUS_NOT_RUN,
    JIRA_INVENTORY_STATUS_SYNTHETIC_VERIFIED,
    MAPPING_STATUS_LIVE_READONLY_OBSERVED,
    MAPPING_STATUS_PLANNED_NOT_VERIFIED,
    MAPPING_STATUS_SYNTHETIC_VERIFIED,
    jira_portfolio_mapping_summary,
)
from app.services.local_connector_env import (  # noqa: E402
    add_connector_env_file_arguments,
    connector_env_cli_kwargs,
    load_local_connector_environment,
)
from app.services.operator_output_sanitizer import inspect_operator_output  # noqa: E402
from app.services.provider_execution_guard import (  # noqa: E402
    LIVE_PROVIDER_EXECUTION_ACK,
    PROVIDER_EXECUTION_ACK_REQUIRED,
)
from scripts import check_external_connectors_readonly as smoke  # noqa: E402

REPORT_KIND = "jira_readonly_inventory"
STATUS_PASS = "pass"
STATUS_FAIL = "fail"
PROVIDER_CALLS_NONE = "none"
PROVIDER_CALLS_SYNTHETIC = "synthetic"
PROVIDER_CALLS_LIVE_READONLY_ATTEMPTED = "live_readonly_attempted"
SCHEDULER_DISABLED = "disabled"
REQUIRES_ACKNOWLEDGEMENT = "requires_acknowledgement"
CONFIGURED = "configured"
NOT_CONFIGURED = "not_configured"
PARTIALLY_CONFIGURED = "partially_configured"
INVENTORY_PASSED = "jira_readonly_inventory_passed"
INVENTORY_FAILED = "jira_readonly_inventory_failed"
INVENTORY_OUTPUT_UNSAFE = "jira_readonly_inventory_output_unsafe"
INVENTORY_CONTRACT_INVALID = "jira_readonly_inventory_contract_invalid"
PAYLOAD_VISIBILITY_SUPPRESSED = "suppressed"


def run_jira_readonly_inventory(
    *,
    synthetic: bool = False,
    allow_live_readonly_apis: bool = False,
    acknowledge_live_readonly_risk: str | None = None,
    compare_portfolio: bool = False,
    max_results: int = 50,
    jira_live_transport: jira.JiraTransport | None = None,
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
    config_status = _jira_config_status(environment)
    jira_result = _base_jira_result(config_status=config_status)
    provider_calls = PROVIDER_CALLS_NONE
    status = STATUS_PASS
    reason_code: str | None = REQUIRES_ACKNOWLEDGEMENT

    if synthetic:
        inventory = jira.fetch_readonly_inventory_summary(
            transport=_synthetic_inventory_transport(),
            execution_mode=jira.SYNTHETIC_EXECUTION_MODE,
            max_results=max_results,
        )
        jira_result.update(
            {
                **inventory,
                "inventory_status": JIRA_INVENTORY_STATUS_SYNTHETIC_VERIFIED,
                "failure_class": None,
            }
        )
        provider_calls = PROVIDER_CALLS_SYNTHETIC
        reason_code = None
    elif not allow_live_readonly_apis:
        jira_result.update(
            {
                "inventory_status": JIRA_INVENTORY_STATUS_CONFIGURED_NOT_EXECUTED
                if config_status == CONFIGURED
                else JIRA_INVENTORY_STATUS_NOT_CONFIGURED,
                "failure_class": REQUIRES_ACKNOWLEDGEMENT
                if config_status == CONFIGURED
                else NOT_CONFIGURED,
            }
        )
    elif acknowledge_live_readonly_risk != LIVE_PROVIDER_EXECUTION_ACK:
        status = STATUS_FAIL
        reason_code = PROVIDER_EXECUTION_ACK_REQUIRED
        jira_result.update(
            {
                "status": STATUS_FAIL,
                "inventory_status": JIRA_INVENTORY_STATUS_NOT_RUN,
                "failure_class": PROVIDER_EXECUTION_ACK_REQUIRED,
            }
        )
    elif config_status != CONFIGURED:
        jira_result.update(
            {
                "inventory_status": JIRA_INVENTORY_STATUS_NOT_CONFIGURED,
                "failure_class": config_status,
            }
        )
        reason_code = config_status
    else:
        provider_calls = PROVIDER_CALLS_LIVE_READONLY_ATTEMPTED
        try:
            transport = jira_live_transport or _jira_inventory_http_transport(
                environment,
                max_results=max_results,
            )
            inventory = jira.fetch_readonly_inventory_summary(
                transport=transport,
                execution_mode=jira.LIVE_EXECUTION_MODE,
                allow_live_provider_execution=True,
                provider_execution_ack=acknowledge_live_readonly_risk,
                max_results=max_results,
            )
            jira_result.update(
                {
                    **inventory,
                    "inventory_status": JIRA_INVENTORY_STATUS_LIVE_READONLY_VERIFIED,
                    "failure_class": None,
                }
            )
            reason_code = INVENTORY_PASSED
        except Exception as exc:
            failure = smoke._classify_jira_live_readonly_failure(exc)
            status = STATUS_FAIL
            reason_code = failure.failure_class
            jira_result.update(
                {
                    "status": STATUS_FAIL,
                    "inventory_status": STATUS_FAIL,
                    "failure_class": failure.failure_class,
                    "auth_status_class": failure.auth_status_class,
                    "transport_status_class": failure.transport_status_class,
                    "response_contract_status": failure.response_contract_status,
                    "provider_payload_visibility": PAYLOAD_VISIBILITY_SUPPRESSED,
                }
            )

    mapping_status = MAPPING_STATUS_PLANNED_NOT_VERIFIED
    if synthetic:
        mapping_status = MAPPING_STATUS_SYNTHETIC_VERIFIED
    elif jira_result.get("inventory_status") == JIRA_INVENTORY_STATUS_LIVE_READONLY_VERIFIED:
        mapping_status = MAPPING_STATUS_LIVE_READONLY_OBSERVED
    portfolio_mapping = (
        jira_portfolio_mapping_summary(
            jira_inventory_status=str(jira_result["inventory_status"]),
            mapping_status=mapping_status,
        )
        if compare_portfolio
        else jira_portfolio_mapping_summary()
    )

    result = {
        "status": status,
        "reason_code": reason_code,
        "report_kind": REPORT_KIND,
        "no_send": True,
        "no_provider_calls": provider_calls != PROVIDER_CALLS_LIVE_READONLY_ATTEMPTED,
        "no_source_of_truth_mutation": True,
        "scheduler_execution": SCHEDULER_DISABLED,
        "provider_calls": provider_calls,
        "jira": jira_result,
        "portfolio_mapping": portfolio_mapping,
        "diagnostics": {
            "synthetic_mode": synthetic,
            "portfolio_compare_requested": compare_portfolio,
            "max_results_class": "bounded",
            "connector_env_file": dict(env_result.diagnostics),
        },
    }
    return _finalize_result(result)


def _base_jira_result(*, config_status: str) -> dict[str, Any]:
    return {
        "status": STATUS_PASS,
        "config_status": config_status,
        "inventory_status": JIRA_INVENTORY_STATUS_NOT_RUN,
        "project_count": 0,
        "project_count_class": jira.COUNT_NOT_OBSERVED,
        "issue_count_class": jira.COUNT_NOT_OBSERVED,
        "accessible_project_count_class": jira.COUNT_NOT_OBSERVED,
        "inaccessible_project_count_class": jira.COUNT_NOT_OBSERVED,
        "permission_limited_count_class": jira.COUNT_NOT_OBSERVED,
        "failure_class": None,
        "auth_status_class": smoke.JIRA_TRANSPORT_NOT_OBSERVED,
        "transport_status_class": smoke.JIRA_TRANSPORT_NOT_OBSERVED,
        "response_contract_status": smoke.JIRA_RESPONSE_CONTRACT_NOT_OBSERVED,
        "provider_payload_visibility": PAYLOAD_VISIBILITY_SUPPRESSED,
        "no_send": True,
        "no_source_of_truth_mutation": True,
        "scheduler_execution": SCHEDULER_DISABLED,
    }


def _jira_config_status(environ: Mapping[str, str]) -> str:
    providers = external_connector_config_doctor_providers(environ=environ)
    provider = providers.get(PROVIDER_JIRA, {})
    status = provider.get("configured_status")
    if status in {CONFIGURED, NOT_CONFIGURED, PARTIALLY_CONFIGURED}:
        return str(status)
    return NOT_CONFIGURED


def _synthetic_inventory_transport() -> jira.JiraTransport:
    def transport(request: jira.JiraConnectorRequest) -> Iterable[Mapping[str, Any]]:
        return (
            {"accessible": True, "issue_count": 2},
            {"accessible": True, "issue_count": 1},
            {"accessible": False, "permission_limited": True},
        )

    return transport


def _jira_inventory_http_transport(
    environ: Mapping[str, str],
    *,
    max_results: int,
) -> jira.JiraTransport:
    site = smoke._normalize_jira_site_config(environ.get("FOS_JIRA_READONLY_SITE", ""))
    user = environ["FOS_JIRA_READONLY_USER"]
    api_key = environ["FOS_JIRA_READONLY_TOKEN"]
    bounded_max_results = min(max(max_results, 1), 100)

    def transport(request: jira.JiraConnectorRequest) -> Iterable[Mapping[str, Any]]:
        endpoint = (
            site
            + "/rest/api/3/project/search?maxResults="
            + urllib.parse.quote(str(bounded_max_results), safe="")
        )
        auth_value = base64.b64encode(f"{user}:{api_key}".encode("utf-8")).decode(
            "ascii"
        )
        api_request = urllib.request.Request(
            endpoint,
            headers={
                "Authorization": "Basic " + auth_value,
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(api_request, timeout=10) as response:
                response_bytes = response.read(1_000_000)
        except Exception as exc:
            raise smoke._classify_jira_live_readonly_failure(exc) from None
        try:
            response_data = json.loads(response_bytes.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise smoke.JiraLiveReadonlySmokeError(
                smoke.JIRA_RESPONSE_MALFORMED,
                transport_status_class=smoke.JIRA_TRANSPORT_PASS,
                response_contract_status=smoke.JIRA_RESPONSE_MALFORMED,
            ) from None
        projects = (
            response_data.get("values", [])
            if isinstance(response_data, Mapping)
            else response_data
        )
        if not isinstance(projects, list):
            raise smoke.JiraLiveReadonlySmokeError(
                smoke.JIRA_RESPONSE_MALFORMED,
                transport_status_class=smoke.JIRA_TRANSPORT_PASS,
                response_contract_status=smoke.JIRA_RESPONSE_MALFORMED,
            )
        if any(not isinstance(project, Mapping) for project in projects):
            raise smoke.JiraLiveReadonlySmokeError(
                smoke.JIRA_RESPONSE_CONTRACT_MISMATCH,
                transport_status_class=smoke.JIRA_TRANSPORT_PASS,
                response_contract_status=smoke.JIRA_RESPONSE_CONTRACT_MISMATCH,
            )
        return [{"accessible": True} for project in projects]

    return transport


def _finalize_result(result: dict[str, Any]) -> dict[str, Any]:
    safety = inspect_operator_output(result)
    if not safety.safe:
        return _failure_report(
            INVENTORY_OUTPUT_UNSAFE,
            operator_output_safety=safety.as_dict(),
        )
    validation = validate_jira_readonly_inventory_contract(result).as_dict()
    result["contract_validation"] = validation
    if validation["validation_status"] != STATUS_PASS:
        return _failure_report(
            INVENTORY_CONTRACT_INVALID,
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
        "scheduler_execution": SCHEDULER_DISABLED,
        "provider_calls": PROVIDER_CALLS_NONE,
        "jira": _base_jira_result(config_status=NOT_CONFIGURED),
        "portfolio_mapping": jira_portfolio_mapping_summary(),
        "diagnostics": {
            "synthetic_mode": False,
            "portfolio_compare_requested": False,
            "max_results_class": "bounded",
            "operator_output_safety": dict(operator_output_safety or {}),
        },
    }
    result["contract_validation"] = dict(
        contract_validation
        or validate_jira_readonly_inventory_contract(result).as_dict()
    )
    return result


def _safe_reason_code(value: str) -> str:
    cleaned = "".join(
        character if character.isalnum() or character == "_" else "_"
        for character in value.casefold()
    ).strip("_")
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned or INVENTORY_FAILED


def _json_text(value: Mapping[str, Any]) -> str:
    return json.dumps(dict(value), indent=2, sort_keys=True) + "\n"


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--synthetic", action="store_true")
    parser.add_argument("--allow-live-readonly-apis", action="store_true")
    parser.add_argument("--acknowledge-live-readonly-risk")
    parser.add_argument("--compare-portfolio", action="store_true")
    parser.add_argument("--max-results", type=int, default=50)
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output strict JSON. This is the default and only output mode.",
    )
    add_connector_env_file_arguments(parser)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    result = run_jira_readonly_inventory(
        synthetic=args.synthetic,
        allow_live_readonly_apis=args.allow_live_readonly_apis,
        acknowledge_live_readonly_risk=args.acknowledge_live_readonly_risk,
        compare_portfolio=args.compare_portfolio,
        max_results=args.max_results,
        **connector_env_cli_kwargs(args),
    )
    print(_json_text(result), end="")
    return 0 if result["status"] == STATUS_PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
