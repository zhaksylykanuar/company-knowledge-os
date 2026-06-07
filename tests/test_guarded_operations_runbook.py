from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.services.operator_output_sanitizer import inspect_operator_output
from app.services.production_operation_guard import (
    PRODUCTION_OPERATION_DEFAULT_DENIED,
    SOURCE_OF_TRUTH_MUTATION,
    ProductionOperationBlockedError,
    require_production_operation_ack,
)
from app.services.provider_execution_guard import (
    PROVIDER_EXECUTION_DEFAULT_DENIED,
    UNKNOWN_PROVIDER,
    UNKNOWN_PROVIDER_BOUNDARY,
    ProviderExecutionBlockedError,
    require_live_provider_execution_ack,
)
from app.services.scheduler_execution_guard import (
    SCHEDULER_EXECUTION,
    SCHEDULER_EXECUTION_DISABLED,
    SchedulerExecutionBlockedError,
    require_no_scheduler_execution,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNBOOK_PATH = REPO_ROOT / "docs" / "runbooks" / "guarded-operations.md"


def _unsafe_markers() -> tuple[str, ...]:
    return (
        "secret",
        "token",
        "webhook",
        "chat_id",
        "http" + "://",
        "postgres" + "://",
        "64hex:" + ("a" * 64),
        "person" + "@" + "example.invalid",
        "provider_payload",
        "rendered_digest_text",
        "grouped_preview_text",
        "source_object_id",
        "item_title",
    )


def _assert_no_unsafe_marker(value: Any) -> None:
    serialized = json.dumps(value, sort_keys=True).casefold()
    for marker in _unsafe_markers():
        if marker.casefold() in serialized:
            raise AssertionError("unsafe diagnostic marker leaked")
    assert inspect_operator_output(value).safe is True


def test_provider_guard_sanitizes_unknown_provider_and_boundary_labels() -> None:
    unsafe_provider = "unsafe " + _unsafe_markers()[0]
    unsafe_boundary = "unsafe " + _unsafe_markers()[4]

    with pytest.raises(ProviderExecutionBlockedError) as exc_info:
        require_live_provider_execution_ack(
            provider=unsafe_provider,
            boundary=unsafe_boundary,
        )

    diagnostics = exc_info.value.diagnostics.as_dict()
    assert diagnostics == {
        "provider": UNKNOWN_PROVIDER,
        "boundary": UNKNOWN_PROVIDER_BOUNDARY,
        "execution_mode": "live_provider",
        "reason_code": PROVIDER_EXECUTION_DEFAULT_DENIED,
        "allowed": False,
    }
    _assert_no_unsafe_marker(diagnostics)


def test_production_guard_diagnostics_are_sanitized_for_unknown_classes() -> None:
    unsafe_operation_class = "unsafe " + _unsafe_markers()[5]

    with pytest.raises(ProductionOperationBlockedError) as exc_info:
        require_production_operation_ack(
            operation_class=unsafe_operation_class,
            boundary="source_of_truth_operation",
        )

    diagnostics = exc_info.value.diagnostics.as_dict()
    assert diagnostics == {
        "operation_class": SOURCE_OF_TRUTH_MUTATION,
        "boundary": "source_of_truth_operation",
        "reason_code": PRODUCTION_OPERATION_DEFAULT_DENIED,
        "allowed": False,
    }
    _assert_no_unsafe_marker(diagnostics)


def test_scheduler_guard_diagnostics_are_sanitized_for_unknown_sources() -> None:
    unsafe_execution_source = "unsafe " + _unsafe_markers()[8]

    with pytest.raises(SchedulerExecutionBlockedError) as exc_info:
        require_no_scheduler_execution(
            boundary="test_telegram_delivery_execution",
            execution_source=unsafe_execution_source,
        )

    diagnostics = exc_info.value.diagnostics.as_dict()
    assert diagnostics == {
        "execution_source": SCHEDULER_EXECUTION,
        "boundary": "test_telegram_delivery_execution",
        "reason_code": SCHEDULER_EXECUTION_DISABLED,
        "allowed": False,
    }
    _assert_no_unsafe_marker(diagnostics)


def test_guarded_operations_runbook_contains_required_safe_boundary_statements() -> None:
    text = RUNBOOK_PATH.read_text(encoding="utf-8").casefold()

    required_phrases = (
        "provider execution guard",
        "live provider calls are default-denied",
        "raw event or interface sources",
        "production-operation guard",
        "source-of-truth mutation",
        "scheduler execution guard",
        "scheduler, outbox drain, background dispatch",
        "read-only review, digest drafting, compatibility reports",
        "no-send and no-source-of-truth mutation",
        "durable handoff artifact",
        "execution outcome metadata",
        "telegram and slack are delivery or interface surfaces only",
        "human approval",
        "provider execution guard",
        "production-operation guard",
        "duplicate-success",
    )
    for phrase in required_phrases:
        assert phrase in text


def test_guarded_operations_runbook_omits_unsafe_placeholder_examples() -> None:
    text = RUNBOOK_PATH.read_text(encoding="utf-8").casefold()
    for marker in _unsafe_markers():
        if marker.casefold() in text:
            raise AssertionError("unsafe runbook marker leaked")


def test_guarded_operations_docs_are_linked_from_index() -> None:
    index = (REPO_ROOT / "docs" / "index.md").read_text(encoding="utf-8")

    assert "runbooks/guarded-operations.md" in index
