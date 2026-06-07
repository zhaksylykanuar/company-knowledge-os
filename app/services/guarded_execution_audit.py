from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.services.operator_output_sanitizer import inspect_operator_output
from app.services.production_operation_guard import (
    DELIVERY_EXECUTION,
    DESTRUCTIVE_CLEANUP,
    MIGRATION_OPERATION,
    OBSIDIAN_VAULT_MUTATION,
    PRODUCTION_DB_OPERATION,
    PRODUCTION_OPERATION_ACK_REQUIRED,
    PRODUCTION_OPERATION_ALLOWED,
    PRODUCTION_OPERATION_DEFAULT_DENIED,
    RAW_STORAGE_MUTATION,
    SCHEDULER_EXECUTION as PRODUCTION_SCHEDULER_EXECUTION,
    SOURCE_OF_TRUTH_MUTATION,
)
from app.services.provider_execution_guard import (
    PROVIDER_EXECUTION_ACK_REQUIRED,
    PROVIDER_EXECUTION_ALLOWED,
    PROVIDER_EXECUTION_DEFAULT_DENIED,
    SAFE_PROVIDER_BOUNDARIES,
    SAFE_PROVIDERS,
    UNKNOWN_PROVIDER,
)
from app.services.scheduler_execution_guard import (
    AUTOMATIC_DELIVERY,
    AUTOMATIC_DELIVERY_DISABLED,
    BACKGROUND_DISPATCH,
    BACKGROUND_DISPATCH_DISABLED,
    LOCAL_SYNTHETIC_EXECUTION,
    MANUAL_OPERATOR_EXECUTION,
    OUTBOX_DRAIN,
    OUTBOX_DRAIN_DISABLED,
    READ_ONLY_REVIEW_EXECUTION,
    RETRY_WORKER,
    RETRY_WORKER_DISABLED,
    SCHEDULER_EXECUTION,
    SCHEDULER_EXECUTION_DISABLED,
    SCHEDULER_EXECUTION_NOT_REQUESTED,
)

SCHEMA_VERSION = "guarded_execution_audit.v1"
EVENT_KIND = "guarded_execution_decision"

PROVIDER_GUARD = "provider_execution_guard"
PRODUCTION_OPERATION_GUARD = "production_operation_guard"
SCHEDULER_EXECUTION_GUARD = "scheduler_execution_guard"
OPERATOR_OUTPUT_SANITIZER = "operator_output_sanitizer"

DECISION_ALLOWED = "allowed"
DECISION_BLOCKED = "blocked"
DECISION_DISABLED = "disabled"
DECISION_REVIEW_REQUIRED = "review_required"

SCHEDULER_DISABLED = "disabled"
SCHEDULER_NOT_REQUESTED = "not_requested"

UNKNOWN_GUARD = "guarded_execution_guard"
UNKNOWN_OPERATION_CLASS = "guarded_execution_operation"
UNKNOWN_REASON_CODE = "guarded_execution_reason_code"
UNKNOWN_BOUNDARY_CLASS = "guarded_execution_boundary"

SAFE_GUARD_NAMES = frozenset(
    {
        PROVIDER_GUARD,
        PRODUCTION_OPERATION_GUARD,
        SCHEDULER_EXECUTION_GUARD,
        OPERATOR_OUTPUT_SANITIZER,
    }
)
SAFE_DECISIONS = frozenset(
    {
        DECISION_ALLOWED,
        DECISION_BLOCKED,
        DECISION_DISABLED,
        DECISION_REVIEW_REQUIRED,
    }
)
SAFE_OPERATION_CLASSES = frozenset(
    {
        *SAFE_PROVIDERS,
        UNKNOWN_PROVIDER,
        DELIVERY_EXECUTION,
        DESTRUCTIVE_CLEANUP,
        MIGRATION_OPERATION,
        OBSIDIAN_VAULT_MUTATION,
        PRODUCTION_DB_OPERATION,
        PRODUCTION_SCHEDULER_EXECUTION,
        RAW_STORAGE_MUTATION,
        SOURCE_OF_TRUTH_MUTATION,
        AUTOMATIC_DELIVERY,
        BACKGROUND_DISPATCH,
        LOCAL_SYNTHETIC_EXECUTION,
        MANUAL_OPERATOR_EXECUTION,
        OUTBOX_DRAIN,
        READ_ONLY_REVIEW_EXECUTION,
        RETRY_WORKER,
        SCHEDULER_EXECUTION,
        OPERATOR_OUTPUT_SANITIZER,
    }
)
SAFE_REASON_CODES = frozenset(
    {
        PROVIDER_EXECUTION_ACK_REQUIRED,
        PROVIDER_EXECUTION_ALLOWED,
        PROVIDER_EXECUTION_DEFAULT_DENIED,
        PRODUCTION_OPERATION_ACK_REQUIRED,
        PRODUCTION_OPERATION_ALLOWED,
        PRODUCTION_OPERATION_DEFAULT_DENIED,
        AUTOMATIC_DELIVERY_DISABLED,
        BACKGROUND_DISPATCH_DISABLED,
        OUTBOX_DRAIN_DISABLED,
        RETRY_WORKER_DISABLED,
        SCHEDULER_EXECUTION_DISABLED,
        SCHEDULER_EXECUTION_NOT_REQUESTED,
        "operator_output_safe",
        "operator_output_unsafe",
    }
)
SAFE_SCHEDULER_STATUS = frozenset({SCHEDULER_DISABLED, SCHEDULER_NOT_REQUESTED})
SAFE_EXECUTION_MODES = frozenset({"live_provider"})


def guarded_execution_audit_event(
    *,
    guard_name: str,
    operation_class: str,
    decision: str,
    reason_code: str,
    diagnostics: Mapping[str, Any] | None = None,
    unsafe_pattern_counts: Mapping[str, Any] | None = None,
    no_send: bool = True,
    no_provider_calls: bool = True,
    no_source_of_truth_mutation: bool = True,
    scheduler_execution: str = SCHEDULER_DISABLED,
) -> dict[str, Any]:
    """Build a JSON-serializable, sanitized guarded-execution audit envelope."""

    diagnostics = diagnostics or {}
    event: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "event_kind": EVENT_KIND,
        "guard_name": _safe_enum(guard_name, SAFE_GUARD_NAMES, UNKNOWN_GUARD),
        "operation_class": _safe_enum(
            operation_class,
            SAFE_OPERATION_CLASSES,
            UNKNOWN_OPERATION_CLASS,
        ),
        "decision": _safe_enum(
            decision,
            SAFE_DECISIONS,
            DECISION_REVIEW_REQUIRED,
        ),
        "reason_code": _safe_enum(
            reason_code,
            SAFE_REASON_CODES,
            UNKNOWN_REASON_CODE,
        ),
        "no_send": bool(no_send),
        "no_provider_calls": bool(no_provider_calls),
        "no_source_of_truth_mutation": bool(no_source_of_truth_mutation),
        "scheduler_execution": _safe_enum(
            scheduler_execution,
            SAFE_SCHEDULER_STATUS,
            SCHEDULER_DISABLED,
        ),
        "diagnostics": _safe_diagnostics(diagnostics),
    }
    if unsafe_pattern_counts is not None:
        event["unsafe_pattern_counts"] = _safe_safety_counts(unsafe_pattern_counts)

    output_safety = inspect_operator_output(event)
    if not output_safety.safe:
        return _unsafe_audit_event()
    return event


def audit_event_from_provider_diagnostics(diagnostics: Any) -> dict[str, Any]:
    payload = _diagnostics_payload(diagnostics)
    return guarded_execution_audit_event(
        guard_name=PROVIDER_GUARD,
        operation_class=_safe_enum(
            payload.get("provider"),
            {*SAFE_PROVIDERS, UNKNOWN_PROVIDER},
            UNKNOWN_PROVIDER,
        ),
        decision=DECISION_ALLOWED if payload.get("allowed") is True else DECISION_BLOCKED,
        reason_code=str(payload.get("reason_code") or UNKNOWN_REASON_CODE),
        diagnostics=payload,
        scheduler_execution=SCHEDULER_NOT_REQUESTED,
    )


def audit_event_from_production_diagnostics(diagnostics: Any) -> dict[str, Any]:
    payload = _diagnostics_payload(diagnostics)
    return guarded_execution_audit_event(
        guard_name=PRODUCTION_OPERATION_GUARD,
        operation_class=str(payload.get("operation_class") or SOURCE_OF_TRUTH_MUTATION),
        decision=DECISION_ALLOWED if payload.get("allowed") is True else DECISION_BLOCKED,
        reason_code=str(payload.get("reason_code") or UNKNOWN_REASON_CODE),
        diagnostics=payload,
        scheduler_execution=SCHEDULER_NOT_REQUESTED,
    )


def audit_event_from_scheduler_diagnostics(diagnostics: Any) -> dict[str, Any]:
    payload = _diagnostics_payload(diagnostics)
    allowed = payload.get("allowed") is True
    return guarded_execution_audit_event(
        guard_name=SCHEDULER_EXECUTION_GUARD,
        operation_class=str(payload.get("execution_source") or SCHEDULER_EXECUTION),
        decision=DECISION_ALLOWED if allowed else DECISION_DISABLED,
        reason_code=str(payload.get("reason_code") or UNKNOWN_REASON_CODE),
        diagnostics=payload,
        scheduler_execution=SCHEDULER_NOT_REQUESTED if allowed else SCHEDULER_DISABLED,
    )


def audit_event_from_operator_output_safety(diagnostics: Any) -> dict[str, Any]:
    payload = _diagnostics_payload(diagnostics)
    safe = payload.get("safe") is True
    reason_code = "operator_output_safe" if safe else "operator_output_unsafe"
    return guarded_execution_audit_event(
        guard_name=OPERATOR_OUTPUT_SANITIZER,
        operation_class=OPERATOR_OUTPUT_SANITIZER,
        decision=DECISION_ALLOWED if safe else DECISION_REVIEW_REQUIRED,
        reason_code=reason_code,
        diagnostics=payload,
        unsafe_pattern_counts=payload,
        scheduler_execution=SCHEDULER_DISABLED,
    )


def audit_event_summary(event: Mapping[str, Any]) -> dict[str, Any]:
    diagnostics = event.get("diagnostics", {})
    input_safety = {}
    if isinstance(diagnostics, Mapping):
        input_safety = diagnostics.get("input_safety", {})
    if not isinstance(input_safety, Mapping):
        input_safety = {}
    return {
        "schema_version": _safe_enum(
            event.get("schema_version"),
            {SCHEMA_VERSION},
            SCHEMA_VERSION,
        ),
        "event_kind": _safe_enum(event.get("event_kind"), {EVENT_KIND}, EVENT_KIND),
        "guard_name": _safe_enum(event.get("guard_name"), SAFE_GUARD_NAMES, UNKNOWN_GUARD),
        "decision": _safe_enum(
            event.get("decision"),
            SAFE_DECISIONS,
            DECISION_REVIEW_REQUIRED,
        ),
        "reason_code": _safe_enum(
            event.get("reason_code"),
            SAFE_REASON_CODES,
            UNKNOWN_REASON_CODE,
        ),
        "unsafe_pattern_count": _safe_int(input_safety.get("unsafe_pattern_count")),
        "unsafe_pattern_classes": _safe_string_list(
            input_safety.get("unsafe_pattern_classes"),
        ),
    }


def _diagnostics_payload(diagnostics: Any) -> Mapping[str, Any]:
    if hasattr(diagnostics, "as_dict"):
        payload = diagnostics.as_dict()
    else:
        payload = diagnostics
    if isinstance(payload, Mapping):
        return payload
    return {}


def _safe_diagnostics(diagnostics: Mapping[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = {
        "input_safety": _safe_safety_counts(inspect_operator_output(diagnostics).as_dict()),
        "field_count": len(diagnostics),
    }

    if "allowed" in diagnostics:
        output["allowed"] = diagnostics.get("allowed") is True
    if "provider" in diagnostics:
        output["provider_class"] = _safe_enum(
            diagnostics.get("provider"),
            {*SAFE_PROVIDERS, UNKNOWN_PROVIDER},
            UNKNOWN_PROVIDER,
        )
    if "boundary" in diagnostics and diagnostics.get("boundary") in SAFE_PROVIDER_BOUNDARIES:
        output["boundary_class"] = diagnostics["boundary"]
    elif "boundary" in diagnostics:
        output["boundary_class"] = UNKNOWN_BOUNDARY_CLASS
    if "execution_mode" in diagnostics:
        output["execution_mode"] = _safe_enum(
            diagnostics.get("execution_mode"),
            SAFE_EXECUTION_MODES,
            "live_provider",
        )
    if "operation_class" in diagnostics:
        output["operation_class"] = _safe_enum(
            diagnostics.get("operation_class"),
            SAFE_OPERATION_CLASSES,
            SOURCE_OF_TRUTH_MUTATION,
        )
    if "execution_source" in diagnostics:
        output["execution_source"] = _safe_enum(
            diagnostics.get("execution_source"),
            SAFE_OPERATION_CLASSES,
            SCHEDULER_EXECUTION,
        )
    return output


def _safe_safety_counts(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "safe": value.get("safe") is True,
        "unsafe_pattern_count": _safe_int(value.get("unsafe_pattern_count")),
        "unsafe_pattern_classes": _safe_string_list(value.get("unsafe_pattern_classes")),
        "raw_hash_shaped_value_count": _safe_int(
            value.get("raw_hash_shaped_value_count")
        ),
        "url_like_value_count": _safe_int(value.get("url_like_value_count")),
        "email_like_value_count": _safe_int(value.get("email_like_value_count")),
        "secret_like_value_count": _safe_int(value.get("secret_like_value_count")),
        "payload_like_value_count": _safe_int(value.get("payload_like_value_count")),
        "unsafe_json_flag_count": _safe_int(value.get("unsafe_json_flag_count")),
    }


def _safe_string_list(value: Any) -> list[str]:
    if not isinstance(value, list | tuple | set | frozenset):
        return []
    return sorted(
        _safe_enum(item, SAFE_REASON_CODES | SAFE_OPERATION_CLASSES, UNKNOWN_REASON_CODE)
        if str(item).endswith("_disabled")
        else _safe_enum(
            item,
            {
                "chunk_text_like",
                "database_connection_like",
                "email_like_value",
                "item_text_like",
                "payload_like_value",
                "preview_text_like",
                "raw_hash_shaped_value",
                "rendered_text_like",
                "secret_like_value",
                "source_identifier",
                "url_like_value",
            },
            UNKNOWN_REASON_CODE,
        )
        for item in value
    )


def _safe_enum(value: Any, allowed: set[str] | frozenset[str], fallback: str) -> str:
    if isinstance(value, str) and value in allowed:
        return value
    return fallback


def _safe_int(value: Any) -> int:
    if isinstance(value, int) and value >= 0:
        return value
    return 0


def _unsafe_audit_event() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "event_kind": EVENT_KIND,
        "guard_name": UNKNOWN_GUARD,
        "operation_class": UNKNOWN_OPERATION_CLASS,
        "decision": DECISION_REVIEW_REQUIRED,
        "reason_code": UNKNOWN_REASON_CODE,
        "no_send": True,
        "no_provider_calls": True,
        "no_source_of_truth_mutation": True,
        "scheduler_execution": SCHEDULER_DISABLED,
        "diagnostics": {
            "input_safety": {
                "safe": False,
                "unsafe_pattern_count": 1,
                "unsafe_pattern_classes": [UNKNOWN_REASON_CODE],
                "raw_hash_shaped_value_count": 0,
                "url_like_value_count": 0,
                "email_like_value_count": 0,
                "secret_like_value_count": 0,
                "payload_like_value_count": 0,
                "unsafe_json_flag_count": 0,
            },
            "field_count": 0,
        },
    }
