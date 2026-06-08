from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from app.services.operator_output_sanitizer import inspect_operator_output
from scripts import report_guarded_execution_readiness as readiness

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "report_guarded_execution_readiness.py"


def _unsafe_values() -> tuple[str, ...]:
    return (
        "https" + "://readiness.invalid/path",
        "operator" + "@" + "readiness.invalid",
        "bot_token readiness value",
        "a" * 64,
        "postgres" + "://readiness.invalid/db",
        "provider_payload readiness body",
        "source_object_id readiness body",
        "rendered_digest_text readiness body",
        "grouped_preview_text readiness body",
        "chunk_text readiness body",
        "item_title readiness body",
    )


def _assert_no_raw_unsafe_values(value: Any) -> None:
    serialized = json.dumps(value, sort_keys=True)
    for raw_value in _unsafe_values():
        assert raw_value not in serialized


def test_guarded_execution_readiness_report_passes_synthetic_run() -> None:
    result = readiness.run_readiness_report()

    assert result["status"] == "pass"
    assert result["reason_code"] is None
    assert result["report_kind"] == "guarded_execution_readiness"
    assert result["no_send"] is True
    assert result["no_provider_calls"] is True
    assert result["no_source_of_truth_mutation"] is True
    assert result["scheduler_execution"] == "disabled"
    assert result["contract_validation"]["validation_status"] == "pass"
    assert result["contract_validation"]["reason_code"] == "contract_validation_passed"
    assert {check["name"] for check in result["checks"]} == {
        "audit_sink",
        "core_docs_references",
        "external_connector_registry",
        "github_connector",
        "guarded_execution_audit",
        "guarded_execution_doctor",
        "guarded_operations_runbook",
        "jira_connector",
        "operator_output_sanitizer",
        "production_operation_guard",
        "provider_execution_guard",
        "scheduler_execution_guard",
    }
    assert all(check["status"] == "pass" for check in result["checks"])
    _assert_no_raw_unsafe_values(result)
    assert inspect_operator_output(result).safe is True


def test_guarded_execution_readiness_report_confirms_safe_guard_summary() -> None:
    result = readiness.run_readiness_report()

    assert result["guard_summary"] == {
        "audit_sink": "present/non_persistent",
        "guarded_execution_audit": "present/sanitized_metadata",
        "guarded_execution_doctor": "present/pass",
        "operator_output_sanitizer": "present/safe_counts_only",
        "production_operation_guard": "present/default_denied",
        "provider_execution_guard": "present/default_denied",
        "scheduler_execution_guard": "present/default_disabled",
    }
    assert result["diagnostics"]["doctor"]["audit_sink_event_count"] == 5
    assert result["diagnostics"]["doctor"]["failed_check_count"] == 0
    assert result["diagnostics"]["doctor"]["unsafe_pattern_count"] == 0
    assert result["connector_summary"]["registry"] == "present/safe_metadata_only"
    assert result["connector_summary"]["github_connector"] == (
        "present/guarded/synthetic_ready"
    )
    assert result["connector_summary"]["jira_connector"] == (
        "present/guarded/synthetic_ready"
    )
    assert result["connector_summary"]["live_calls"] == "default_denied"
    assert result["connector_summary"]["source_of_truth_mutation"] == "absent"
    assert result["connector_summary"]["scheduler_execution"] == "disabled"
    assert result["connector_summary"]["payload_leakage"] == "absent"


def test_guarded_execution_readiness_report_reports_remaining_risks_as_classes() -> None:
    result = readiness.run_readiness_report()

    assert result["remaining_risks"] == {
        "live_provider_execution": "gated_only",
        "persistent_audit_logging": "not_implemented",
        "production_db_migrations": "out_of_scope",
        "production_deploy_ops": "not_implemented",
        "scheduler_outbox_execution": "intentionally_disabled",
    }
    _assert_no_raw_unsafe_values(result["remaining_risks"])


def test_guarded_execution_readiness_report_docs_summary_is_safe() -> None:
    result = readiness.run_readiness_report()

    assert result["docs_summary"]["guarded_operations_runbook"] == "present"
    assert result["docs_summary"]["core_docs_references"] == "present"
    assert result["docs_summary"]["reference_count"] == 4
    assert set(result["docs_summary"]["reference_labels"]) == {
        "attention_feature",
        "data_model",
        "guarded_operations_runbook",
        "telegram_digest_feature",
    }
    _assert_no_raw_unsafe_values(result["docs_summary"])


def test_guarded_execution_readiness_report_cli_outputs_strict_json() -> None:
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
    assert payload["report_kind"] == "guarded_execution_readiness"
    assert payload["contract_validation"]["validation_status"] == "pass"
    assert payload["diagnostics"]["failed_check_count"] == 0
    _assert_no_raw_unsafe_values(payload)
    assert inspect_operator_output(payload).safe is True


def test_guarded_execution_readiness_report_failure_mode_is_sanitized() -> None:
    def failing_doctor_runner() -> dict[str, Any]:
        raise RuntimeError("unsafe " + _unsafe_values()[0])

    result = readiness.run_readiness_report(doctor_runner=failing_doctor_runner)

    assert result["status"] == "fail"
    assert result["reason_code"] == "guarded_execution_readiness_exception"
    assert result["checks"] == []
    assert result["no_send"] is True
    assert result["no_provider_calls"] is True
    assert result["no_source_of_truth_mutation"] is True
    assert result["scheduler_execution"] == "disabled"
    assert result["contract_validation"]["validation_status"] == "pass"
    assert result["connector_summary"] == {}
    _assert_no_raw_unsafe_values(result)
    assert inspect_operator_output(result).safe is True


def test_guarded_execution_readiness_report_missing_docs_fails_safely(
    tmp_path: Path,
) -> None:
    result = readiness.run_readiness_report(docs_root=tmp_path)

    assert result["status"] == "fail"
    assert result["reason_code"] == "guarded_execution_readiness_failed"
    assert result["docs_summary"]["guarded_operations_runbook"] == "missing"
    assert result["docs_summary"]["core_docs_references"] == "missing"
    assert result["diagnostics"]["failed_check_count"] == 2
    assert result["contract_validation"]["validation_status"] == "pass"
    _assert_no_raw_unsafe_values(result)
    assert inspect_operator_output(result).safe is True


def test_guarded_execution_readiness_report_does_not_import_live_provider_clients() -> None:
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
