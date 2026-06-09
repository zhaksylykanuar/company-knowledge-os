from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from app.services.external_connector_config import (
    ATLASSIAN_ADMIN_ENV_KEYS,
    JIRA_ENV_KEYS,
    JIRA_WRITE_ENV_KEYS,
)
from app.services.guarded_execution_contracts import validate_jira_write_readiness_contract
from app.services.jira_write_readiness import (
    BLOCKED_WRITE_OPERATION_CLASSES,
    REQUIRED_PROFILE_CLASSES,
    jira_write_readiness_plan,
    jira_write_readiness_readiness_summary,
)
from app.services.operator_output_sanitizer import inspect_operator_output
from scripts import plan_jira_write_readiness as write_readiness_cli

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "plan_jira_write_readiness.py"


def _unsafe_values() -> tuple[str, ...]:
    return (
        "https" + "://jira-write-readiness.invalid/path",
        "operator" + "@" + "jira-write-readiness.invalid",
        "bot_token write readiness value",
        "a" * 64,
        "postgres" + "://jira-write-readiness.invalid/db",
        "provider_payload write readiness body",
        "source_object_id write readiness body",
        "PROJECT" + "-123",
        "ISSUE" + "-456",
        "issue title write readiness body",
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


def test_jira_write_readiness_requires_manual_approval_and_disables_writes() -> None:
    result = jira_write_readiness_plan(environ=_full_env())

    assert result["report_kind"] == "jira_write_readiness"
    assert result["write_execution_status"] == "disabled"
    assert result["dry_run_only"] is True
    assert result["manual_approval_required"] is True
    assert result["required_profile_classes"] == list(REQUIRED_PROFILE_CLASSES)
    assert result["configured_profile_count_class"] == "nonzero_count"
    assert result["missing_profile_count_class"] == "zero_count"
    assert result["blocked_write_operation_classes"] == list(
        BLOCKED_WRITE_OPERATION_CLASSES
    )
    assert result["next_approval_class"] == "approve_jira_write_execution_prompt"
    assert result["creation_dry_run_status"] == "present"
    assert result["no_provider_calls"] is True
    assert result["no_source_of_truth_mutation"] is True
    assert result["scheduler_execution"] == "disabled"
    _assert_safe(result)


def test_jira_write_readiness_missing_future_profiles_remains_dry_run_only() -> None:
    result = jira_write_readiness_plan(environ={})

    assert result["configured_profile_count_class"] == "zero_count"
    assert result["missing_profile_count_class"] == "nonzero_count"
    assert result["write_execution_status"] == "disabled"
    assert result["manual_approval_required"] is True
    assert result["credential_profiles"]["admin_live_calls"] == "not_run"
    _assert_safe(result)


def test_jira_write_readiness_cli_is_contract_valid_and_no_live(tmp_path: Path) -> None:
    env_file = tmp_path / "connectors.env"
    env_file.write_text(
        "\n".join(
            f"{key}=hidden_value"
            for key in (*JIRA_ENV_KEYS, *JIRA_WRITE_ENV_KEYS, *ATLASSIAN_ADMIN_ENV_KEYS)
        )
        + "\n",
        encoding="utf-8",
    )

    result = write_readiness_cli.run_jira_write_readiness(
        environ={},
        connector_env_file=env_file,
        use_connector_env_file=True,
    )
    validation = validate_jira_write_readiness_contract(result)

    assert result["status"] == "pass"
    assert result["reason_code"] == "jira_write_readiness_passed"
    assert result["contract_validation"]["validation_status"] == "pass"
    assert validation.passed is True
    assert result["no_provider_calls"] is True
    assert result["write_execution_status"] == "disabled"
    assert result["credential_profiles"]["jira_write_profile_status"] == "configured"
    assert "hidden_value" not in json.dumps(result, sort_keys=True)
    _assert_safe(result)
    _assert_safe(validation.as_dict())


def test_jira_write_readiness_cli_script_outputs_strict_json() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--json", "--dry-run", "--no-connector-env-file"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        env={},
    )

    assert completed.returncode == 0
    assert completed.stderr == ""
    payload = json.loads(completed.stdout)
    assert payload["report_kind"] == "jira_write_readiness"
    assert payload["status"] == "pass"
    assert payload["write_execution_status"] == "disabled"
    assert payload["contract_validation"]["validation_status"] == "pass"
    _assert_safe(payload)


def test_jira_write_readiness_readiness_summary_is_safe() -> None:
    summary = jira_write_readiness_readiness_summary(environ={})

    assert summary["atlassian_api_profiles"] == "present"
    assert summary["jira_readonly_profile"] == "not_configured"
    assert summary["jira_write_profile"] == "not_configured"
    assert summary["jira_write_readiness"] == "dry_run_only"
    assert summary["jira_creation_execution"] == "disabled"
    assert summary["admin_api_live_calls"] == "disabled"
    assert summary["manual_approval_required"] == "yes"
    assert summary["write_execution_status"] == "disabled"
    assert summary["no_provider_calls"] is True
    _assert_safe(summary)
