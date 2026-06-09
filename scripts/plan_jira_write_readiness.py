#!/usr/bin/env python
"""Sanitized Jira write-readiness dry-run report."""

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

from app.services.guarded_execution_contracts import (  # noqa: E402
    validate_jira_write_readiness_contract,
)
from app.services.jira_write_readiness import (  # noqa: E402
    READINESS_PASSED,
    STATUS_FAIL,
    STATUS_PASS,
    jira_write_readiness_plan,
)
from app.services.local_connector_env import (  # noqa: E402
    add_connector_env_file_arguments,
    connector_env_cli_kwargs,
    load_local_connector_environment,
)
from app.services.operator_output_sanitizer import inspect_operator_output  # noqa: E402

WRITE_READINESS_OUTPUT_UNSAFE = "jira_write_readiness_output_unsafe"
WRITE_READINESS_CONTRACT_INVALID = "jira_write_readiness_contract_invalid"
SCHEDULER_EXECUTION_DISABLED = "disabled"


def run_jira_write_readiness(
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
    plan = jira_write_readiness_plan(environ=env_result.environment)
    result = {
        "status": STATUS_PASS,
        "reason_code": READINESS_PASSED,
        **plan,
        "diagnostics": {
            **dict(plan["diagnostics"]),
            "connector_env_file": dict(env_result.diagnostics),
        },
    }
    return _finalize_result(result)


def _finalize_result(result: dict[str, Any]) -> dict[str, Any]:
    safety = inspect_operator_output(result)
    if not safety.safe:
        return _failure_report(
            WRITE_READINESS_OUTPUT_UNSAFE,
            operator_output_safety=safety.as_dict(),
        )
    validation = validate_jira_write_readiness_contract(result).as_dict()
    result["contract_validation"] = validation
    if validation["validation_status"] != STATUS_PASS:
        return _failure_report(
            WRITE_READINESS_CONTRACT_INVALID,
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
        "report_kind": "jira_write_readiness",
        "write_execution_status": "disabled",
        "dry_run_only": True,
        "manual_approval_required": True,
        "no_send": True,
        "no_provider_calls": True,
        "no_source_of_truth_mutation": True,
        "scheduler_execution": SCHEDULER_EXECUTION_DISABLED,
        "required_profile_classes": [],
        "configured_profile_count_class": "zero_count",
        "missing_profile_count_class": "zero_count",
        "blocked_write_operation_classes": [],
        "next_approval_class": "approve_jira_write_execution_prompt",
        "creation_dry_run_status": "present",
        "credential_profiles": {},
        "diagnostics": {
            "operator_output_safety": dict(operator_output_safety or {}),
        },
    }
    result["contract_validation"] = dict(
        contract_validation
        or validate_jira_write_readiness_contract(result).as_dict()
    )
    return result


def _safe_reason_code(value: str) -> str:
    cleaned = "".join(
        character if character.isalnum() or character == "_" else "_"
        for character in value.casefold()
    ).strip("_")
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned or "jira_write_readiness_failed"


def _json_text(value: Mapping[str, Any]) -> str:
    return json.dumps(dict(value), indent=2, sort_keys=True) + "\n"


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output strict JSON. This is the default and only output mode.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Keep write-readiness in dry-run mode. This is always enforced.",
    )
    add_connector_env_file_arguments(parser)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    result = run_jira_write_readiness(**connector_env_cli_kwargs(args))
    print(_json_text(result), end="")
    return 0 if result["status"] == STATUS_PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
