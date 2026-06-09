#!/usr/bin/env python
"""Read-only GitHub organization inventory and migration readiness report."""

from __future__ import annotations

import argparse
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

from app.connectors import github  # noqa: E402
from app.services.github_org_inventory import (  # noqa: E402
    REPORT_KIND,
    STATUS_FAIL,
    STATUS_PASS,
    TARGET_ORG_KEY,
    run_github_org_readonly_inventory as _run_github_org_readonly_inventory,
)
from app.services.guarded_execution_contracts import (  # noqa: E402
    validate_github_org_readonly_inventory_contract,
)
from app.services.local_connector_env import (  # noqa: E402
    add_connector_env_file_arguments,
    connector_env_cli_kwargs,
)
from app.services.operator_output_sanitizer import inspect_operator_output  # noqa: E402

INVENTORY_OUTPUT_UNSAFE = "github_org_readonly_inventory_output_unsafe"
INVENTORY_CONTRACT_INVALID = "github_org_readonly_inventory_contract_invalid"
SCHEDULER_EXECUTION_DISABLED = "disabled"


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
    environment = environ if environ is not None else os.environ
    live_transport = github_live_transport
    if allow_live_readonly_apis and live_transport is None:
        live_transport = _github_org_http_transport(
            environment,
            target_org=target_org or TARGET_ORG_KEY,
            max_results=max_results,
        )
    result = _run_github_org_readonly_inventory(
        synthetic=synthetic,
        allow_live_readonly_apis=allow_live_readonly_apis,
        acknowledge_live_readonly_risk=acknowledge_live_readonly_risk,
        compare_portfolio=compare_portfolio,
        target_org=target_org,
        max_results=max_results,
        github_live_transport=live_transport,
        environ=environment,
        connector_env_file=connector_env_file,
        use_connector_env_file=use_connector_env_file,
    )
    return _finalize_result(result)


def _github_org_http_transport(
    environ: Mapping[str, str],
    *,
    target_org: str,
    max_results: int,
) -> github.GitHubTransport:
    def transport(
        request: github.GitHubConnectorRequest,
    ) -> Iterable[Mapping[str, Any]]:
        token = environ["FOS_GITHUB_READONLY_TOKEN"]
        bounded_max = max(1, min(max_results, 100))
        endpoint = (
            _https_base("api.github.com")
            + "/orgs/"
            + urllib.parse.quote(target_org.strip(), safe="")
            + "/repos?per_page="
            + str(bounded_max)
            + "&type=all"
        )
        api_request = urllib.request.Request(
            endpoint,
            headers={
                "Authorization": "Bearer " + token,
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(api_request, timeout=10) as response:
            response_data = json.loads(response.read(1_000_000).decode("utf-8"))
        if not isinstance(response_data, list):
            return []
        payloads: list[dict[str, str]] = []
        for item in response_data:
            if not isinstance(item, Mapping):
                continue
            repo_key = item.get("name")
            if isinstance(repo_key, str) and repo_key:
                payloads.append({"repo_key": repo_key})
        return payloads

    return transport


def _finalize_result(result: dict[str, Any]) -> dict[str, Any]:
    safety = inspect_operator_output(result)
    if not safety.safe:
        return _failure_report(
            INVENTORY_OUTPUT_UNSAFE,
            operator_output_safety=safety.as_dict(),
        )
    validation = validate_github_org_readonly_inventory_contract(result).as_dict()
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
        "scheduler_execution": SCHEDULER_EXECUTION_DISABLED,
        "provider_calls": "none",
        "github": {},
        "migration_readiness": {},
        "diagnostics": {
            "operator_output_safety": dict(operator_output_safety or {}),
        },
    }
    result["contract_validation"] = dict(
        contract_validation
        or validate_github_org_readonly_inventory_contract(result).as_dict()
    )
    return result


def _safe_reason_code(value: str) -> str:
    cleaned = "".join(
        character if character.isalnum() or character == "_" else "_"
        for character in value.casefold()
    ).strip("_")
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned or "github_org_readonly_inventory_failed"


def _https_base(host: str) -> str:
    return "https" + (chr(58) + "//") + host


def _json_text(value: Mapping[str, Any]) -> str:
    return json.dumps(dict(value), indent=2, sort_keys=True) + "\n"


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output strict JSON. This is the default and only output mode.",
    )
    parser.add_argument("--synthetic", action="store_true")
    parser.add_argument("--compare-portfolio", action="store_true")
    parser.add_argument("--allow-live-readonly-apis", action="store_true")
    parser.add_argument("--acknowledge-live-readonly-risk")
    parser.add_argument("--target-org", default=TARGET_ORG_KEY)
    parser.add_argument("--max-results", type=int, default=50)
    add_connector_env_file_arguments(parser)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    result = run_github_org_readonly_inventory(
        synthetic=args.synthetic,
        allow_live_readonly_apis=args.allow_live_readonly_apis,
        acknowledge_live_readonly_risk=args.acknowledge_live_readonly_risk,
        compare_portfolio=args.compare_portfolio,
        target_org=args.target_org,
        max_results=args.max_results,
        **connector_env_cli_kwargs(args),
    )
    print(_json_text(result), end="")
    return 0 if result["status"] == STATUS_PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
