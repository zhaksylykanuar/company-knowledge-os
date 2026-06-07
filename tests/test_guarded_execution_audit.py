from __future__ import annotations

import json
from typing import Any

import pytest

from app.services.guarded_execution_audit import (
    DECISION_ALLOWED,
    DECISION_BLOCKED,
    DECISION_DISABLED,
    DECISION_REVIEW_REQUIRED,
    EVENT_KIND,
    OPERATOR_OUTPUT_SANITIZER,
    PRODUCTION_OPERATION_GUARD,
    PROVIDER_GUARD,
    SCHEMA_VERSION,
    SCHEDULER_DISABLED,
    SCHEDULER_EXECUTION_GUARD,
    audit_event_from_operator_output_safety,
    audit_event_from_production_diagnostics,
    audit_event_from_provider_diagnostics,
    audit_event_from_scheduler_diagnostics,
    audit_event_summary,
    guarded_execution_audit_event,
)
from app.services.operator_output_sanitizer import inspect_operator_output
from app.services.production_operation_guard import (
    PRODUCTION_OPERATION_ACK,
    PRODUCTION_OPERATION_ALLOWED,
    PRODUCTION_OPERATION_DEFAULT_DENIED,
    SOURCE_OF_TRUTH_MUTATION,
    ProductionOperationBlockedError,
    require_production_operation_ack,
)
from app.services.provider_execution_guard import (
    LIVE_PROVIDER_EXECUTION_ACK,
    PROVIDER_EXECUTION_ALLOWED,
    PROVIDER_EXECUTION_DEFAULT_DENIED,
    ProviderExecutionBlockedError,
    require_live_provider_execution_ack,
)
from app.services.scheduler_execution_guard import (
    MANUAL_OPERATOR_EXECUTION,
    OUTBOX_DRAIN,
    OUTBOX_DRAIN_DISABLED,
    SCHEDULER_EXECUTION_NOT_REQUESTED,
    SchedulerExecutionBlockedError,
    require_no_scheduler_execution,
)
from scripts import doctor_guarded_execution as doctor


def _unsafe_values() -> tuple[str, ...]:
    return (
        "https" + "://audit.invalid/path",
        "operator" + "@" + "audit.invalid",
        "bot_token audit-token",
        "a" * 64,
        "postgres" + "://audit.invalid/db",
        "provider_payload audit body",
        "source_object_id audit body",
        "rendered_digest_text audit body",
        "grouped_preview_text audit body",
        "chunk_text audit body",
        "item_title audit body",
    )


def _assert_json_serializable_and_sanitized(event: dict[str, Any]) -> None:
    serialized = json.dumps(event, sort_keys=True)
    for raw_value in _unsafe_values():
        assert raw_value not in serialized
    assert inspect_operator_output(event).safe is True


def test_provider_default_denied_decision_has_sanitized_audit_event() -> None:
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

    event = audit_event_from_provider_diagnostics(exc_info.value.diagnostics)

    assert callback_called is False
    assert event["schema_version"] == SCHEMA_VERSION
    assert event["event_kind"] == EVENT_KIND
    assert event["guard_name"] == PROVIDER_GUARD
    assert event["operation_class"] == "telegram"
    assert event["decision"] == DECISION_BLOCKED
    assert event["reason_code"] == PROVIDER_EXECUTION_DEFAULT_DENIED
    assert event["no_send"] is True
    assert event["no_provider_calls"] is True
    assert event["no_source_of_truth_mutation"] is True
    assert event["scheduler_execution"] == "not_requested"
    _assert_json_serializable_and_sanitized(event)


def test_production_default_denied_decision_has_sanitized_audit_event() -> None:
    callback_called = False

    def forbidden_callback() -> None:
        nonlocal callback_called
        callback_called = True

    with pytest.raises(ProductionOperationBlockedError) as exc_info:
        require_production_operation_ack(
            operation_class=SOURCE_OF_TRUTH_MUTATION,
            boundary="source_of_truth_operation",
        )
        forbidden_callback()

    event = audit_event_from_production_diagnostics(exc_info.value.diagnostics)

    assert callback_called is False
    assert event["guard_name"] == PRODUCTION_OPERATION_GUARD
    assert event["operation_class"] == SOURCE_OF_TRUTH_MUTATION
    assert event["decision"] == DECISION_BLOCKED
    assert event["reason_code"] == PRODUCTION_OPERATION_DEFAULT_DENIED
    assert event["no_send"] is True
    assert event["no_provider_calls"] is True
    assert event["no_source_of_truth_mutation"] is True
    _assert_json_serializable_and_sanitized(event)


def test_scheduler_default_disabled_decision_has_sanitized_audit_event() -> None:
    callback_called = False

    def forbidden_callback() -> None:
        nonlocal callback_called
        callback_called = True

    with pytest.raises(SchedulerExecutionBlockedError) as exc_info:
        require_no_scheduler_execution(
            boundary="test_telegram_delivery_execution",
            execution_source=OUTBOX_DRAIN,
        )
        forbidden_callback()

    event = audit_event_from_scheduler_diagnostics(exc_info.value.diagnostics)

    assert callback_called is False
    assert event["guard_name"] == SCHEDULER_EXECUTION_GUARD
    assert event["operation_class"] == OUTBOX_DRAIN
    assert event["decision"] == DECISION_DISABLED
    assert event["reason_code"] == OUTBOX_DRAIN_DISABLED
    assert event["scheduler_execution"] == SCHEDULER_DISABLED
    _assert_json_serializable_and_sanitized(event)


def test_acknowledged_synthetic_guard_decisions_do_not_imply_execution() -> None:
    provider = require_live_provider_execution_ack(
        provider="telegram",
        boundary="telegram_send_message",
        allow_live_provider_execution=True,
        provider_execution_ack=LIVE_PROVIDER_EXECUTION_ACK,
    )
    production = require_production_operation_ack(
        operation_class=SOURCE_OF_TRUTH_MUTATION,
        boundary="source_of_truth_operation",
        allow_production_operation=True,
        production_operation_ack=PRODUCTION_OPERATION_ACK,
    )
    scheduler = require_no_scheduler_execution(
        boundary="test_telegram_delivery_execution",
        execution_source=MANUAL_OPERATOR_EXECUTION,
    )

    events = (
        audit_event_from_provider_diagnostics(provider),
        audit_event_from_production_diagnostics(production),
        audit_event_from_scheduler_diagnostics(scheduler),
    )

    assert events[0]["decision"] == DECISION_ALLOWED
    assert events[0]["reason_code"] == PROVIDER_EXECUTION_ALLOWED
    assert events[1]["decision"] == DECISION_ALLOWED
    assert events[1]["reason_code"] == PRODUCTION_OPERATION_ALLOWED
    assert events[2]["decision"] == DECISION_ALLOWED
    assert events[2]["reason_code"] == SCHEDULER_EXECUTION_NOT_REQUESTED
    for event in events:
        assert event["no_send"] is True
        assert event["no_provider_calls"] is True
        assert event["no_source_of_truth_mutation"] is True
        _assert_json_serializable_and_sanitized(event)


def test_unsafe_operation_labels_and_exception_text_are_not_echoed() -> None:
    unsafe = _unsafe_values()
    event = guarded_execution_audit_event(
        guard_name=unsafe[0],
        operation_class=unsafe[1],
        decision=unsafe[2],
        reason_code=unsafe[3],
        diagnostics={
            "boundary": unsafe[0],
            "raw_exception_text": unsafe[2],
            "provider_payload": unsafe[5],
            "source_object_id": unsafe[6],
            "rendered_digest_text": unsafe[7],
        },
    )

    assert event["guard_name"] == "guarded_execution_guard"
    assert event["operation_class"] == "guarded_execution_operation"
    assert event["decision"] == DECISION_REVIEW_REQUIRED
    assert event["reason_code"] == "guarded_execution_reason_code"
    assert event["diagnostics"]["input_safety"]["unsafe_pattern_count"] > 0
    _assert_json_serializable_and_sanitized(event)


def test_sanitizer_counts_classes_can_be_included_without_raw_matches() -> None:
    unsafe = _unsafe_values()
    diagnostics = inspect_operator_output(
        {
            "contact": unsafe[1],
            "database": unsafe[4],
            "hash": unsafe[3],
            "payload": unsafe[5],
            "rendered": unsafe[7],
            "preview": unsafe[8],
            "chunk": unsafe[9],
            "item": unsafe[10],
        }
    ).as_dict()

    event = audit_event_from_operator_output_safety(diagnostics)

    assert event["guard_name"] == OPERATOR_OUTPUT_SANITIZER
    assert event["decision"] == DECISION_REVIEW_REQUIRED
    assert event["reason_code"] == "operator_output_unsafe"
    assert event["unsafe_pattern_counts"]["unsafe_pattern_count"] > 0
    assert event["unsafe_pattern_counts"]["raw_hash_shaped_value_count"] > 0
    _assert_json_serializable_and_sanitized(event)


def test_audit_event_summary_uses_safe_status_classes_only() -> None:
    with pytest.raises(ProviderExecutionBlockedError) as exc_info:
        require_live_provider_execution_ack(
            provider="unsafe provider",
            boundary=_unsafe_values()[0],
        )

    event = audit_event_from_provider_diagnostics(exc_info.value.diagnostics)
    summary = audit_event_summary(event)

    assert summary == {
        "schema_version": SCHEMA_VERSION,
        "event_kind": EVENT_KIND,
        "guard_name": PROVIDER_GUARD,
        "decision": DECISION_BLOCKED,
        "reason_code": PROVIDER_EXECUTION_DEFAULT_DENIED,
        "unsafe_pattern_count": 0,
        "unsafe_pattern_classes": [],
    }
    _assert_json_serializable_and_sanitized(summary)


def test_doctor_output_includes_sanitized_audit_summaries() -> None:
    result = doctor.run_doctor()
    by_name = {check["name"]: check for check in result["checks"]}

    assert result["status"] == "pass"
    assert by_name["provider_guard_default_denied"]["diagnostics"]["audit_event"][
        "guard_name"
    ] == PROVIDER_GUARD
    assert by_name["production_operation_guard_default_denied"]["diagnostics"][
        "audit_event"
    ]["guard_name"] == PRODUCTION_OPERATION_GUARD
    assert by_name["scheduler_execution_guard_default_disabled"]["diagnostics"][
        "audit_event"
    ]["guard_name"] == SCHEDULER_EXECUTION_GUARD
    assert by_name["operator_output_sanitizer"]["diagnostics"]["audit_event"][
        "guard_name"
    ] == OPERATOR_OUTPUT_SANITIZER
    _assert_json_serializable_and_sanitized(result)
