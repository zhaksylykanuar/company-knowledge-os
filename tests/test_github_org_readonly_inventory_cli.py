from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from app.connectors import github
from app.services.external_connector_config import GITHUB_ENV_KEYS
from app.services.guarded_execution_contracts import (
    validate_github_org_readonly_inventory_contract,
)
from app.services.operator_output_sanitizer import inspect_operator_output
from app.services.provider_execution_guard import LIVE_PROVIDER_EXECUTION_ACK
from app.services.repository_portfolio import repository_portfolio_catalog
from scripts import check_github_org_readonly_inventory as inventory_cli

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "check_github_org_readonly_inventory.py"


def _configured_github_env() -> dict[str, str]:
    return dict.fromkeys(GITHUB_ENV_KEYS, "configured_value")


def _unsafe_values() -> tuple[str, ...]:
    return (
        "https" + "://github-org-cli.invalid/path",
        "operator" + "@" + "github-org-cli.invalid",
        "bot_token github org cli value",
        "a" * 64,
        "postgres" + "://github-org-cli.invalid/db",
        "provider_payload github org cli body",
        "source_object_id github org cli body",
        "repo name github org cli body",
        "owner name github org cli body",
        "PR" + "-456",
        "issue title github org cli body",
    )


def _assert_cli_output_safe(value: dict[str, Any]) -> None:
    serialized = json.dumps(value, sort_keys=True)
    for raw_value in _unsafe_values():
        assert raw_value not in serialized
    for entry in repository_portfolio_catalog():
        assert entry["repo_key"] not in serialized
    assert inspect_operator_output(value).safe is True
    assert value["contract_validation"]["validation_status"] == "pass"
    assert validate_github_org_readonly_inventory_contract(value).passed is True


def test_github_org_inventory_cli_default_no_live_outputs_strict_json() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--json",
            "--compare-portfolio",
            "--no-connector-env-file",
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        env={},
    )

    assert completed.returncode == 0
    assert completed.stderr == ""
    payload = json.loads(completed.stdout)
    assert payload["report_kind"] == "github_org_readonly_inventory"
    assert payload["status"] == "pass"
    assert payload["provider_calls"] == "none"
    assert payload["no_provider_calls"] is True
    assert payload["github"]["target_org_key"] == "qtwin-io"
    assert payload["github"]["target_owner_class"] == "github_organization"
    assert payload["github"]["seed_repo_count"] == 19
    assert payload["github"]["expected_migration_count"] == 19
    assert payload["github"]["write_operations"] == "disabled"
    assert payload["github"]["repo_transfer_operations"] == "disabled"
    assert payload["github"]["repo_edit_operations"] == "disabled"
    _assert_cli_output_safe(payload)


def test_github_org_inventory_cli_synthetic_outputs_safe_counts() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--json",
            "--synthetic",
            "--compare-portfolio",
            "--no-connector-env-file",
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        env={},
    )

    assert completed.returncode == 0
    assert completed.stderr == ""
    payload = json.loads(completed.stdout)
    assert payload["report_kind"] == "github_org_readonly_inventory"
    assert payload["status"] == "pass"
    assert payload["provider_calls"] == "synthetic"
    assert payload["github"]["org_inventory_status"] == "synthetic_verified"
    assert payload["github"]["org_repo_count_class"] == "nonzero_count"
    assert payload["github"]["matched_count_class"] == "nonzero_count"
    assert payload["github"]["missing_count_class"] == "nonzero_count"
    assert payload["github"]["extra_count_class"] == "zero_count"
    _assert_cli_output_safe(payload)


def test_github_org_inventory_cli_live_mode_uses_mocked_transport_once() -> None:
    seed_key = str(repository_portfolio_catalog()[0]["repo_key"])
    call_count = 0

    def mocked_transport(
        request: github.GitHubConnectorRequest,
    ) -> list[dict[str, str]]:
        nonlocal call_count
        call_count += 1
        return [{"repo_key": seed_key}]

    result = inventory_cli.run_github_org_readonly_inventory(
        allow_live_readonly_apis=True,
        acknowledge_live_readonly_risk=LIVE_PROVIDER_EXECUTION_ACK,
        compare_portfolio=True,
        github_live_transport=mocked_transport,
        environ=_configured_github_env(),
    )

    assert result["status"] == "pass"
    assert result["provider_calls"] == "live_readonly_attempted"
    assert result["no_provider_calls"] is False
    assert call_count == 1
    assert result["github"]["org_inventory_status"] == "live_readonly_verified"
    assert result["github"]["org_repo_count_class"] == "nonzero_count"
    assert result["github"]["provider_payload_visibility"] == "suppressed"
    _assert_cli_output_safe(result)
