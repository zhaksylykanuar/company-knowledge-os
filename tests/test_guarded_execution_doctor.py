from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from app.services.operator_output_sanitizer import inspect_operator_output
from scripts import doctor_guarded_execution as doctor

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "doctor_guarded_execution.py"


def _unsafe_values() -> tuple[str, ...]:
    return (
        "https" + "://synthetic.invalid/path",
        "operator" + "@" + "synthetic.invalid",
        "bot_token synthetic value",
        "a" * 64,
        "postgres" + "://synthetic.invalid/db",
        "provider_payload synthetic body",
        "source_object_id synthetic value",
        "rendered_digest_text synthetic body",
        "grouped_preview_text synthetic body",
        "chunk_text synthetic body",
    )


def _assert_no_raw_unsafe_values(value: Any) -> None:
    serialized = json.dumps(value, sort_keys=True)
    for raw_value in _unsafe_values():
        assert raw_value not in serialized


def test_guarded_execution_doctor_passes_synthetic_run() -> None:
    result = doctor.run_doctor()

    assert result["status"] == "pass"
    assert result["reason_code"] is None
    assert result["no_send"] is True
    assert result["no_provider_calls"] is True
    assert result["no_source_of_truth_mutation"] is True
    assert result["scheduler_execution"] == "disabled"
    assert result["diagnostics"]["failed_check_count"] == 0
    audit_sink = result["diagnostics"]["guarded_execution_audit_sink"]
    assert audit_sink["event_count"] == 5
    assert audit_sink["unsafe_pattern_count"] == 0
    assert audit_sink["unsafe_pattern_classes"] == []
    assert audit_sink["no_send"] is True
    assert audit_sink["no_provider_calls"] is True
    assert audit_sink["no_source_of_truth_mutation"] is True
    assert audit_sink["scheduler_execution"] == "disabled"
    assert {check["name"] for check in result["checks"]} == {
        "bounded_send_path_guarded",
        "operator_output_sanitizer",
        "production_operation_guard_default_denied",
        "provider_guard_default_denied",
        "read_only_paths_no_send",
        "scheduler_execution_guard_default_disabled",
    }
    _assert_no_raw_unsafe_values(result)
    assert inspect_operator_output(result).safe is True


def test_guarded_execution_doctor_cli_outputs_strict_json() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert completed.stderr == ""
    payload = json.loads(completed.stdout)
    assert payload["status"] == "pass"
    assert payload["no_send"] is True
    assert payload["no_provider_calls"] is True
    assert payload["no_source_of_truth_mutation"] is True
    assert payload["scheduler_execution"] == "disabled"
    _assert_no_raw_unsafe_values(payload)


def test_guarded_execution_doctor_reports_guard_default_blocks() -> None:
    result = doctor.run_doctor()
    by_name = {check["name"]: check for check in result["checks"]}

    provider = by_name["provider_guard_default_denied"]["diagnostics"]
    production = by_name["production_operation_guard_default_denied"]["diagnostics"]
    scheduler = by_name["scheduler_execution_guard_default_disabled"]["diagnostics"]
    bounded = by_name["bounded_send_path_guarded"]["diagnostics"]

    assert provider["reason_code"] == "provider_execution_default_denied"
    assert provider["blocked_callback_called"] is False
    assert production["reason_code"] == "production_operation_default_denied"
    assert production["blocked_callback_called"] is False
    assert scheduler["reason_code"] == "outbox_drain_disabled"
    assert scheduler["blocked_callback_called"] is False
    assert bounded["reason_code"] == "outbox_drain_disabled"
    assert bounded["adapter_called"] is False


def test_guarded_execution_doctor_sanitizer_reports_classes_counts_only() -> None:
    result = doctor.run_doctor()
    sanitizer = {
        check["name"]: check for check in result["checks"]
    }["operator_output_sanitizer"]["diagnostics"]

    assert sanitizer["safe"] is False
    assert sanitizer["unsafe_pattern_count"] > 0
    assert sanitizer["raw_hash_shaped_value_count"] > 0
    assert sanitizer["url_like_value_count"] > 0
    assert sanitizer["email_like_value_count"] > 0
    assert sanitizer["secret_like_value_count"] > 0
    assert sanitizer["payload_like_value_count"] > 0
    assert sanitizer["unsafe_json_flag_count"] > 0
    _assert_no_raw_unsafe_values(sanitizer)


def test_guarded_execution_doctor_failure_mode_is_sanitized() -> None:
    def failing_check() -> None:
        raise doctor.DoctorCheckError("unsafe " + _unsafe_values()[0])

    result = doctor.run_doctor(
        checks=(doctor.DoctorCheck("synthetic_failure", failing_check),)
    )

    assert result["status"] == "fail"
    assert result["reason_code"] == "guarded_execution_doctor_failed"
    assert result["checks"] == [
        {
            "name": "synthetic_failure",
            "status": "fail",
            "reason_code": "unsafe_https_synthetic_invalid_path",
        }
    ]
    _assert_no_raw_unsafe_values(result)


def test_guarded_execution_doctor_does_not_import_live_provider_clients() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    blocked_import_markers = (
        "app.connectors",
        "app.agents.llm_runner",
        "get_openai_client",
        "googleapiclient",
        "OpenAI(",
        "send_telegram_plain_text",
        "AsyncSessionLocal",
    )
    for marker in blocked_import_markers:
        assert marker not in source
