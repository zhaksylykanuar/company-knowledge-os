from __future__ import annotations

import json
from typing import Any

import pytest

from app.services.operator_output_sanitizer import (
    assert_operator_output_safe,
    inspect_operator_output,
)
from app.services.production_operation_guard import require_production_operation_ack
from app.services.provider_execution_guard import require_live_provider_execution_ack
from app.services.scheduler_execution_guard import (
    OUTBOX_DRAIN,
    require_no_scheduler_execution,
)
from scripts import manual_no_marker_grouped_lifecycle_review as manual_script
from scripts import send_test_telegram_delivery_intention as send_script


def _unsafe_values() -> dict[str, str]:
    return {
        "url": "https" + "://unsafe.invalid/path",
        "email": "operator" + "@" + "unsafe.invalid",
        "token": "bot_token unsafe-token-value",
        "hash": "a" * 64,
        "db": "postgres" + "://unsafe-connection",
        "payload": "provider_payload unsafe body",
        "rendered": "rendered_digest_text unsafe body",
        "preview": "grouped_preview_text unsafe body",
        "chunk": "chunk_text unsafe body",
        "item": "item_title unsafe body",
        "source": "source_object_id unsafe body",
    }


def _assert_raw_values_absent(diagnostics: dict[str, Any]) -> None:
    serialized = json.dumps(diagnostics, sort_keys=True)
    for raw_value in _unsafe_values().values():
        assert raw_value not in serialized


def test_operator_output_sanitizer_reports_classes_and_counts_without_raw_values() -> None:
    unsafe = _unsafe_values()
    diagnostics = inspect_operator_output(
        {
            "safe_reason_code": "blocked",
            "contact": unsafe["email"],
            "database": unsafe["db"],
            "digest": unsafe["rendered"],
            "grouped_preview_text": unsafe["preview"],
            "item_title": unsafe["item"],
            "provider_payload": {"body": unsafe["payload"]},
            "sha256": unsafe["hash"],
            "source_object_id": unsafe["source"],
            "token_field": unsafe["token"],
            "url_field": unsafe["url"],
            "chunk_text": unsafe["chunk"],
        }
    ).as_dict()

    assert diagnostics["safe"] is False
    assert diagnostics["unsafe_pattern_count"] > 0
    assert diagnostics["raw_hash_shaped_value_count"] >= 1
    assert diagnostics["url_like_value_count"] >= 2
    assert diagnostics["email_like_value_count"] >= 1
    assert diagnostics["secret_like_value_count"] >= 1
    assert diagnostics["payload_like_value_count"] >= 1
    assert diagnostics["unsafe_json_flag_count"] >= 1
    assert set(diagnostics["unsafe_pattern_classes"]) >= {
        "database_connection_like",
        "email_like_value",
        "raw_hash_shaped_value",
        "payload_like_value",
        "rendered_text_like",
        "secret_like_value",
        "url_like_value",
    }
    _assert_raw_values_absent(diagnostics)


def test_operator_output_sanitizer_allows_safe_synthetic_summary() -> None:
    diagnostics = assert_operator_output_safe(
        {
            "status": "blocked",
            "reason_code": "provider_execution_default_denied",
            "safe_counts": {
                "unsafe_pattern_count": 0,
                "validated_artifact_count": 1,
            },
        }
    )

    assert diagnostics.safe is True
    assert diagnostics.unsafe_pattern_count == 0


def test_operator_output_sanitizer_raises_safe_reason_only() -> None:
    with pytest.raises(ValueError) as exc_info:
        assert_operator_output_safe({"message": _unsafe_values()["url"]})

    assert str(exc_info.value) == "operator_output_unsafe"
    assert _unsafe_values()["url"] not in repr(exc_info.value)


def test_guard_diagnostics_remain_safe_under_sanitizer() -> None:
    guard_diagnostics: list[dict[str, Any]] = []
    for call in (
        lambda: require_live_provider_execution_ack(
            provider="unsafe provider",
            boundary="unsafe boundary",
        ),
        lambda: require_production_operation_ack(
            operation_class="unsafe operation",
            boundary="source_of_truth_operation",
        ),
        lambda: require_no_scheduler_execution(
            boundary="test_telegram_delivery_execution",
            execution_source=OUTBOX_DRAIN,
        ),
    ):
        with pytest.raises(RuntimeError) as exc_info:
            call()
        guard_diagnostics.append(exc_info.value.diagnostics.as_dict())

    diagnostics = inspect_operator_output(guard_diagnostics).as_dict()
    assert diagnostics["safe"] is True
    assert diagnostics["unsafe_pattern_count"] == 0


def test_manual_delegated_contract_diagnostics_expose_sanitized_safety_counts() -> None:
    unsafe = _unsafe_values()
    diagnostics = manual_script._delegated_report_contract_diagnostics(
        exit_code=2,
        artifact_presence="present",
        artifact_contract_status="unsafe",
        validator_name="_normalize_delegated_report_artifact",
        payload={
            "status": "blocked",
            "provider_payload": unsafe["payload"],
            "rendered_text": unsafe["rendered"],
            "source_object_id": unsafe["source"],
        },
    )

    safety = diagnostics["operator_output_safety"]
    assert safety["safe"] is False
    assert safety["payload_like_value_count"] >= 1
    assert safety["unsafe_json_flag_count"] >= 1
    _assert_raw_values_absent(diagnostics)


def test_bounded_send_blocked_output_sanitizes_unsafe_message() -> None:
    unsafe_message = _unsafe_values()["url"]

    blocked = send_script._blocked_result(
        error_code="send_blocked",
        message=unsafe_message,
    )

    assert blocked["message"] == "blocked_message_sanitized"
    assert unsafe_message not in json.dumps(blocked, sort_keys=True)
    assert inspect_operator_output(blocked).safe is True
