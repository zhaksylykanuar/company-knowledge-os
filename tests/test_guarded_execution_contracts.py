from __future__ import annotations

import json
from typing import Any

import pytest

from app.services.guarded_execution_audit import (
    DECISION_BLOCKED,
    InMemoryGuardedExecutionAuditSink,
    PROVIDER_GUARD,
    SCHEDULER_NOT_REQUESTED,
    guarded_execution_audit_event,
)
from app.services.guarded_execution_contracts import (
    CONTRACT_MISSING_REQUIRED_FIELDS,
    CONTRACT_UNKNOWN_FIELDS,
    CONTRACT_UNSAFE_OUTPUT,
    CONTRACT_VALIDATION_PASSED,
    VALIDATION_FAIL,
    VALIDATION_PASS,
    validate_audit_event_contract,
    validate_audit_sink_summary_contract,
    validate_connector_readonly_smoke_contract,
    validate_doctor_output_contract,
    validate_external_connector_config_doctor_contract,
    validate_readiness_report_contract,
)
from app.services.operator_output_sanitizer import inspect_operator_output
from app.services.provider_execution_guard import (
    PROVIDER_EXECUTION_DEFAULT_DENIED,
    ProviderExecutionBlockedError,
    require_live_provider_execution_ack,
)
from scripts import doctor_guarded_execution as doctor
from scripts import check_external_connectors_readonly as connector_smoke
from scripts import doctor_external_connector_config as config_doctor
from scripts import report_guarded_execution_readiness as readiness


def _unsafe_values() -> tuple[str, ...]:
    return (
        "https" + "://contract.invalid/path",
        "operator" + "@" + "contract.invalid",
        "bot_token contract value",
        "a" * 64,
        "postgres" + "://contract.invalid/db",
        "provider_payload contract body",
        "source_object_id contract body",
        "rendered_digest_text contract body",
        "grouped_preview_text contract body",
        "chunk_text contract body",
        "item_title contract body",
        "raw_audit_json contract body",
        "raw_config_doctor_json contract body",
        "raw_doctor_json contract body",
        "raw_readiness_json contract body",
        "raw_sink_contents contract body",
        "raw_smoke_json contract body",
    )


def _assert_no_raw_unsafe_values(value: Any) -> None:
    serialized = json.dumps(value, sort_keys=True)
    for raw_value in _unsafe_values():
        assert raw_value not in serialized


def _assert_validation_safe(value: Any) -> None:
    assert inspect_operator_output(value).safe is True
    _assert_no_raw_unsafe_values(value)


def _provider_blocked_event() -> dict[str, Any]:
    return guarded_execution_audit_event(
        guard_name=PROVIDER_GUARD,
        operation_class="telegram",
        decision=DECISION_BLOCKED,
        reason_code=PROVIDER_EXECUTION_DEFAULT_DENIED,
        scheduler_execution=SCHEDULER_NOT_REQUESTED,
    )


def test_valid_audit_event_contract_passes() -> None:
    validation = validate_audit_event_contract(_provider_blocked_event())

    assert validation.passed is True
    assert validation.as_dict()["validation_status"] == VALIDATION_PASS
    assert validation.as_dict()["reason_code"] == CONTRACT_VALIDATION_PASSED
    _assert_validation_safe(validation.as_dict())


def test_valid_audit_sink_summary_contract_passes() -> None:
    sink = InMemoryGuardedExecutionAuditSink()
    sink.record(_provider_blocked_event())

    validation = validate_audit_sink_summary_contract(sink.summary())

    assert validation.passed is True
    _assert_validation_safe(validation.as_dict())


def test_valid_doctor_output_contract_passes() -> None:
    result = doctor.run_doctor()
    validation = validate_doctor_output_contract(result)

    assert result["contract_validation"]["validation_status"] == VALIDATION_PASS
    assert validation.passed is True
    assert json.loads(json.dumps(result, sort_keys=True))["status"] == "pass"
    assert result["no_send"] is True
    assert result["no_provider_calls"] is True
    assert result["no_source_of_truth_mutation"] is True
    assert result["scheduler_execution"] == "disabled"
    _assert_validation_safe(result)
    _assert_validation_safe(validation.as_dict())


def test_valid_readiness_report_contract_passes() -> None:
    result = readiness.run_readiness_report()
    validation = validate_readiness_report_contract(result)

    assert result["contract_validation"]["validation_status"] == VALIDATION_PASS
    assert validation.passed is True
    assert json.loads(json.dumps(result, sort_keys=True))["status"] == "pass"
    assert result["no_send"] is True
    assert result["no_provider_calls"] is True
    assert result["no_source_of_truth_mutation"] is True
    assert result["scheduler_execution"] == "disabled"
    _assert_validation_safe(result)
    _assert_validation_safe(validation.as_dict())


def test_valid_connector_readonly_smoke_contract_passes() -> None:
    result = connector_smoke.run_connector_readonly_smoke(
        provider="all",
        synthetic=True,
        compare_portfolio=True,
    )
    validation = validate_connector_readonly_smoke_contract(result)

    assert result["contract_validation"]["validation_status"] == VALIDATION_PASS
    assert validation.passed is True
    assert json.loads(json.dumps(result, sort_keys=True))["status"] == "pass"
    assert result["no_send"] is True
    assert result["no_provider_calls"] is True
    assert result["no_source_of_truth_mutation"] is True
    assert result["scheduler_execution"] == "disabled"
    assert result["provider_calls"] == "synthetic"
    _assert_validation_safe(result)
    _assert_validation_safe(validation.as_dict())


def test_valid_external_connector_config_doctor_contract_passes() -> None:
    result = config_doctor.run_external_connector_config_doctor(environ={})
    validation = validate_external_connector_config_doctor_contract(result)

    assert result["contract_validation"]["validation_status"] == VALIDATION_PASS
    assert validation.passed is True
    assert json.loads(json.dumps(result, sort_keys=True))["status"] == "pass"
    assert result["no_send"] is True
    assert result["no_provider_calls"] is True
    assert result["no_source_of_truth_mutation"] is True
    assert result["scheduler_execution"] == "disabled"
    assert result["summary"]["not_configured_provider_count"] == 2
    _assert_validation_safe(result)
    _assert_validation_safe(validation.as_dict())


def test_missing_required_fields_fail_with_field_names_only() -> None:
    payload = _provider_blocked_event()
    payload.pop("guard_name")

    validation = validate_audit_event_contract(payload).as_dict()

    assert validation["validation_status"] == VALIDATION_FAIL
    assert validation["reason_code"] == CONTRACT_MISSING_REQUIRED_FIELDS
    assert validation["missing_required_field_names"] == ["guard_name"]
    _assert_validation_safe(validation)


def test_unknown_unsafe_field_names_fail_without_raw_echo() -> None:
    payload = _provider_blocked_event()
    payload[_unsafe_values()[0]] = "safe_value"

    validation = validate_audit_event_contract(payload).as_dict()

    assert validation["validation_status"] == VALIDATION_FAIL
    assert validation["reason_code"] == CONTRACT_UNKNOWN_FIELDS
    assert validation["unknown_field_names"] == ["unsafe_field_name"]
    _assert_validation_safe(validation)


def test_unsafe_values_fail_with_classes_counts_only() -> None:
    payload = _provider_blocked_event()
    payload["diagnostics"] = {
        "url": _unsafe_values()[0],
        "email": _unsafe_values()[1],
        "token": _unsafe_values()[2],
        "hash": _unsafe_values()[3],
        "database": _unsafe_values()[4],
        "payload": _unsafe_values()[5],
        "source": _unsafe_values()[6],
        "rendered": _unsafe_values()[7],
        "preview": _unsafe_values()[8],
        "chunk": _unsafe_values()[9],
        "item": _unsafe_values()[10],
    }

    validation = validate_audit_event_contract(payload).as_dict()

    assert validation["validation_status"] == VALIDATION_FAIL
    assert validation["reason_code"] == CONTRACT_UNSAFE_OUTPUT
    assert validation["unsafe_pattern_count"] > 0
    assert validation["unsafe_pattern_classes"]
    _assert_validation_safe(validation)


def test_validation_result_is_sanitized_for_raw_output_markers() -> None:
    payload = dict(doctor.run_doctor())
    payload["diagnostics"] = {
        "raw_audit_json": _unsafe_values()[11],
        "raw_config_doctor_json": _unsafe_values()[12],
        "raw_doctor_json": _unsafe_values()[13],
        "raw_readiness_json": _unsafe_values()[14],
        "raw_sink_contents": _unsafe_values()[15],
        "raw_smoke_json": _unsafe_values()[16],
    }

    validation = validate_doctor_output_contract(payload).as_dict()

    assert validation["validation_status"] == VALIDATION_FAIL
    assert validation["reason_code"] == CONTRACT_UNSAFE_OUTPUT
    _assert_validation_safe(validation)


def test_blocked_synthetic_callback_is_not_called_by_contract_path() -> None:
    callback_called = False

    def forbidden_callback() -> None:
        nonlocal callback_called
        callback_called = True

    with pytest.raises(ProviderExecutionBlockedError) as exc_info:
        require_live_provider_execution_ack(
            provider="telegram",
            boundary="telegram_send_message",
        )
        forbidden_callback()

    event = guarded_execution_audit_event(
        guard_name=PROVIDER_GUARD,
        operation_class="telegram",
        decision=DECISION_BLOCKED,
        reason_code=exc_info.value.diagnostics.reason_code,
        scheduler_execution=SCHEDULER_NOT_REQUESTED,
    )
    validation = validate_audit_event_contract(event)

    assert callback_called is False
    assert validation.passed is True


def test_doctor_and_readiness_scripts_use_contract_helpers() -> None:
    doctor_source = (doctor.REPO_ROOT / "scripts" / "doctor_guarded_execution.py").read_text(
        encoding="utf-8"
    )
    config_doctor_source = (
        config_doctor.REPO_ROOT / "scripts" / "doctor_external_connector_config.py"
    ).read_text(encoding="utf-8")
    smoke_source = (
        connector_smoke.REPO_ROOT / "scripts" / "check_external_connectors_readonly.py"
    ).read_text(encoding="utf-8")
    readiness_source = (
        readiness.REPO_ROOT / "scripts" / "report_guarded_execution_readiness.py"
    ).read_text(encoding="utf-8")

    assert "validate_doctor_output_contract" in doctor_source
    assert "validate_external_connector_config_doctor_contract" in config_doctor_source
    assert "validate_connector_readonly_smoke_contract" in smoke_source
    assert "validate_readiness_report_contract" in readiness_source
