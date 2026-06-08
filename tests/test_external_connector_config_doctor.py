from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from app.services.external_connector_config import GITHUB_ENV_KEYS, JIRA_ENV_KEYS
from app.services.guarded_execution_contracts import (
    validate_external_connector_config_doctor_contract,
)
from app.services.operator_output_sanitizer import inspect_operator_output
from scripts import doctor_external_connector_config as config_doctor

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "doctor_external_connector_config.py"


def _unsafe_values() -> tuple[str, ...]:
    return (
        "https" + "://config-doctor.invalid/path",
        "operator" + "@" + "config-doctor.invalid",
        "bot_token config doctor value",
        "a" * 64,
        "postgres" + "://config-doctor.invalid/db",
        "provider_payload config doctor body",
        "source_object_id config doctor body",
        "rendered_digest_text config doctor body",
        "grouped_preview_text config doctor body",
        "chunk_text config doctor body",
        "item_title config doctor body",
        "raw_config_doctor_json config doctor body",
        "raw_smoke_json config doctor body",
        "raw_readiness_json config doctor body",
        "raw_doctor_json config doctor body",
        "PROJECT" + "-123",
        "PR" + "-456",
    )


def _assert_no_raw_unsafe_values(value: Any) -> None:
    serialized = json.dumps(value, sort_keys=True)
    for raw_value in _unsafe_values():
        assert raw_value not in serialized


def _assert_config_doctor_safe(value: dict[str, Any]) -> None:
    assert inspect_operator_output(value).safe is True
    assert value["contract_validation"]["validation_status"] == "pass"
    validate_external_connector_config_doctor_contract(value)
    _assert_no_raw_unsafe_values(value)


def _configured_env() -> dict[str, str]:
    return {
        **dict.fromkeys(GITHUB_ENV_KEYS, "hidden_value"),
        **dict.fromkeys(JIRA_ENV_KEYS, "hidden_value"),
    }


def test_config_doctor_absent_variables_reports_not_configured() -> None:
    result = config_doctor.run_external_connector_config_doctor(environ={})

    assert result["status"] == "pass"
    assert result["no_send"] is True
    assert result["no_provider_calls"] is True
    assert result["no_source_of_truth_mutation"] is True
    assert result["scheduler_execution"] == "disabled"
    assert result["providers"]["github"]["configured_status"] == "not_configured"
    assert result["providers"]["jira"]["configured_status"] == "not_configured"
    assert result["summary"]["not_configured_provider_count"] == 2
    assert result["summary"]["live_readonly_ready_provider_count"] == 0
    _assert_config_doctor_safe(result)


def test_config_doctor_partial_variables_reports_partially_configured() -> None:
    result = config_doctor.run_external_connector_config_doctor(
        environ={
            GITHUB_ENV_KEYS[0]: "hidden_value",
            JIRA_ENV_KEYS[0]: "hidden_value",
        }
    )

    assert result["providers"]["github"]["configured_status"] == "partially_configured"
    assert result["providers"]["jira"]["configured_status"] == "partially_configured"
    assert result["summary"]["partially_configured_provider_count"] == 2
    assert result["summary"]["live_readonly_ready_provider_count"] == 0
    _assert_config_doctor_safe(result)


def test_config_doctor_complete_variables_reports_ready_without_values() -> None:
    environment = _configured_env()
    result = config_doctor.run_external_connector_config_doctor(environ=environment)

    assert result["providers"]["github"]["configured_status"] == "configured"
    assert result["providers"]["jira"]["configured_status"] == "configured"
    assert result["providers"]["github"]["live_readonly_readiness"] == "ready"
    assert result["providers"]["jira"]["live_readonly_readiness"] == "ready"
    assert result["summary"]["configured_provider_count"] == 2
    assert result["summary"]["live_readonly_ready_provider_count"] == 2
    serialized = json.dumps(result, sort_keys=True)
    for raw_value in set(environment.values()):
        assert raw_value not in serialized
    _assert_config_doctor_safe(result)


def test_config_doctor_hides_unsafe_looking_values() -> None:
    environment = {
        **dict.fromkeys(GITHUB_ENV_KEYS, _unsafe_values()[0]),
        **dict.fromkeys(JIRA_ENV_KEYS, _unsafe_values()[1]),
    }

    result = config_doctor.run_external_connector_config_doctor(environ=environment)

    assert result["status"] == "pass"
    assert result["summary"]["configured_provider_count"] == 2
    serialized = json.dumps(result, sort_keys=True)
    for raw_value in set(environment.values()):
        assert raw_value not in serialized
    _assert_config_doctor_safe(result)


def test_config_doctor_cli_outputs_strict_json_without_live_imports() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--json"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        env={},
    )

    assert completed.returncode == 0
    assert completed.stderr == ""
    payload = json.loads(completed.stdout)
    assert payload["report_kind"] == "external_connector_config_doctor"
    assert payload["status"] == "pass"
    assert payload["summary"]["not_configured_provider_count"] == 2
    _assert_config_doctor_safe(payload)


def test_config_doctor_source_does_not_use_live_provider_clients_or_dotenv() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    blocked_markers = (
        "app.connectors",
        "urllib.request",
        "requests.",
        "googleapiclient",
        "OpenAI(",
        "dotenv",
        "Path('.env')",
        'Path(".env")',
        "send_telegram_plain_text",
    )
    for marker in blocked_markers:
        assert marker not in source
