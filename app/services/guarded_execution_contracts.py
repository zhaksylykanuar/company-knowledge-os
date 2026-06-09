from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
from typing import Any

from app.services.guarded_execution_audit import (
    AUDIT_SINK_ACCEPTED,
    EVENT_KIND,
    IN_MEMORY_AUDIT_SINK,
    NOOP_AUDIT_SINK,
    SAFE_DECISIONS,
    SAFE_GUARD_NAMES,
    SAFE_OPERATION_CLASSES,
    SAFE_REASON_CODES as AUDIT_SAFE_REASON_CODES,
    SAFE_SCHEDULER_STATUS,
    SCHEMA_VERSION as AUDIT_SCHEMA_VERSION,
    UNKNOWN_GUARD,
    UNKNOWN_OPERATION_CLASS,
    UNKNOWN_REASON_CODE,
)
from app.services.operator_output_sanitizer import inspect_operator_output

CONTRACT_VALIDATION_SCHEMA_VERSION = "guarded_execution_contract_validation.v1"
CONTRACT_VALIDATION_CLASS = "guarded_execution_json_contract"

AUDIT_EVENT_CONTRACT = "guarded_execution_audit_event"
AUDIT_SINK_SUMMARY_CONTRACT = "guarded_execution_audit_sink_summary"
DOCTOR_OUTPUT_CONTRACT = "guarded_execution_doctor_output"
READINESS_REPORT_CONTRACT = "guarded_execution_readiness_report"
CONNECTOR_READONLY_SMOKE_CONTRACT = "external_connector_readonly_smoke"
EXTERNAL_CONNECTOR_CONFIG_DOCTOR_CONTRACT = "external_connector_config_doctor"
JIRA_READONLY_INVENTORY_CONTRACT = "jira_readonly_inventory"
JIRA_CREATION_DRY_RUN_CONTRACT = "jira_creation_dry_run"

VALIDATION_PASS = "pass"
VALIDATION_FAIL = "fail"
CONTRACT_VALIDATION_PASSED = "contract_validation_passed"
CONTRACT_NOT_JSON_SERIALIZABLE = "contract_not_json_serializable"
CONTRACT_WRONG_SHAPE = "contract_wrong_shape"
CONTRACT_MISSING_REQUIRED_FIELDS = "contract_missing_required_fields"
CONTRACT_UNKNOWN_FIELDS = "contract_unknown_fields"
CONTRACT_UNSAFE_OUTPUT = "contract_unsafe_output"
CONTRACT_SCHEMA_MISMATCH = "contract_schema_mismatch"

AUDIT_EVENT_REQUIRED_FIELDS = frozenset(
    {
        "schema_version",
        "event_kind",
        "guard_name",
        "operation_class",
        "decision",
        "reason_code",
        "no_send",
        "no_provider_calls",
        "no_source_of_truth_mutation",
        "scheduler_execution",
        "diagnostics",
    }
)
AUDIT_EVENT_ALLOWED_FIELDS = AUDIT_EVENT_REQUIRED_FIELDS | {"unsafe_pattern_counts"}

AUDIT_SINK_SUMMARY_REQUIRED_FIELDS = frozenset(
    {
        "sink_kind",
        "event_count",
        "accepted",
        "reason_code",
        "guard_counts",
        "decision_counts",
        "reason_counts",
        "unsafe_pattern_count",
        "unsafe_pattern_classes",
        "no_send",
        "no_provider_calls",
        "no_source_of_truth_mutation",
        "scheduler_execution",
    }
)
AUDIT_SINK_SUMMARY_ALLOWED_FIELDS = AUDIT_SINK_SUMMARY_REQUIRED_FIELDS

DOCTOR_OUTPUT_REQUIRED_FIELDS = frozenset(
    {
        "mode",
        "status",
        "reason_code",
        "checks",
        "no_send",
        "no_provider_calls",
        "no_source_of_truth_mutation",
        "scheduler_execution",
        "diagnostics",
    }
)
DOCTOR_OUTPUT_ALLOWED_FIELDS = DOCTOR_OUTPUT_REQUIRED_FIELDS | {"contract_validation"}

READINESS_REPORT_REQUIRED_FIELDS = frozenset(
    {
        "status",
        "reason_code",
        "report_kind",
        "no_send",
        "no_provider_calls",
        "no_source_of_truth_mutation",
        "scheduler_execution",
        "checks",
        "connector_summary",
        "external_connector_config_summary",
        "connector_smoke_summary",
        "jira_inventory_summary",
        "guard_summary",
        "portfolio_summary",
        "docs_summary",
        "remaining_risks",
        "diagnostics",
    }
)
READINESS_REPORT_ALLOWED_FIELDS = READINESS_REPORT_REQUIRED_FIELDS | {
    "contract_validation"
}

CONNECTOR_READONLY_SMOKE_REQUIRED_FIELDS = frozenset(
    {
        "status",
        "reason_code",
        "report_kind",
        "no_send",
        "no_provider_calls",
        "no_source_of_truth_mutation",
        "scheduler_execution",
        "provider_calls",
        "providers",
        "diagnostics",
    }
)
CONNECTOR_READONLY_SMOKE_ALLOWED_FIELDS = (
    CONNECTOR_READONLY_SMOKE_REQUIRED_FIELDS | {"contract_validation"}
)

EXTERNAL_CONNECTOR_CONFIG_DOCTOR_REQUIRED_FIELDS = frozenset(
    {
        "status",
        "reason_code",
        "report_kind",
        "no_send",
        "no_provider_calls",
        "no_source_of_truth_mutation",
        "scheduler_execution",
        "providers",
        "summary",
        "checks",
        "diagnostics",
    }
)
EXTERNAL_CONNECTOR_CONFIG_DOCTOR_ALLOWED_FIELDS = (
    EXTERNAL_CONNECTOR_CONFIG_DOCTOR_REQUIRED_FIELDS | {"contract_validation"}
)

JIRA_READONLY_INVENTORY_REQUIRED_FIELDS = frozenset(
    {
        "status",
        "reason_code",
        "report_kind",
        "no_send",
        "no_provider_calls",
        "no_source_of_truth_mutation",
        "scheduler_execution",
        "provider_calls",
        "jira",
        "portfolio_mapping",
        "operating_model",
        "recommended_next_action_class",
        "diagnostics",
    }
)
JIRA_READONLY_INVENTORY_ALLOWED_FIELDS = JIRA_READONLY_INVENTORY_REQUIRED_FIELDS | {
    "contract_validation"
}
JIRA_CREATION_DRY_RUN_REQUIRED_FIELDS = frozenset(
    {
        "status",
        "reason_code",
        "report_kind",
        "dry_run_only",
        "no_send",
        "no_provider_calls",
        "no_source_of_truth_mutation",
        "scheduler_execution",
        "jira_write_operations",
        "manual_approval_required",
        "current_jira_assessment_class",
        "migration_recommendation_class",
        "proposed_structure",
        "proposed_project_classes",
        "proposed_issue_type_classes",
        "proposed_workflow_status_classes",
        "proposed_board_classes",
        "governance_rule_classes",
        "migration_step_classes",
        "blocked_write_operation_classes",
        "follow_up_classes",
        "next_step_class",
        "diagnostics",
    }
)
JIRA_CREATION_DRY_RUN_ALLOWED_FIELDS = JIRA_CREATION_DRY_RUN_REQUIRED_FIELDS | {
    "contract_validation"
}

CONTRACT_REQUIRED_FIELDS = {
    AUDIT_EVENT_CONTRACT: AUDIT_EVENT_REQUIRED_FIELDS,
    AUDIT_SINK_SUMMARY_CONTRACT: AUDIT_SINK_SUMMARY_REQUIRED_FIELDS,
    DOCTOR_OUTPUT_CONTRACT: DOCTOR_OUTPUT_REQUIRED_FIELDS,
    READINESS_REPORT_CONTRACT: READINESS_REPORT_REQUIRED_FIELDS,
    CONNECTOR_READONLY_SMOKE_CONTRACT: CONNECTOR_READONLY_SMOKE_REQUIRED_FIELDS,
    EXTERNAL_CONNECTOR_CONFIG_DOCTOR_CONTRACT: (
        EXTERNAL_CONNECTOR_CONFIG_DOCTOR_REQUIRED_FIELDS
    ),
    JIRA_READONLY_INVENTORY_CONTRACT: JIRA_READONLY_INVENTORY_REQUIRED_FIELDS,
    JIRA_CREATION_DRY_RUN_CONTRACT: JIRA_CREATION_DRY_RUN_REQUIRED_FIELDS,
}
CONTRACT_ALLOWED_FIELDS = {
    AUDIT_EVENT_CONTRACT: AUDIT_EVENT_ALLOWED_FIELDS,
    AUDIT_SINK_SUMMARY_CONTRACT: AUDIT_SINK_SUMMARY_ALLOWED_FIELDS,
    DOCTOR_OUTPUT_CONTRACT: DOCTOR_OUTPUT_ALLOWED_FIELDS,
    READINESS_REPORT_CONTRACT: READINESS_REPORT_ALLOWED_FIELDS,
    CONNECTOR_READONLY_SMOKE_CONTRACT: CONNECTOR_READONLY_SMOKE_ALLOWED_FIELDS,
    EXTERNAL_CONNECTOR_CONFIG_DOCTOR_CONTRACT: (
        EXTERNAL_CONNECTOR_CONFIG_DOCTOR_ALLOWED_FIELDS
    ),
    JIRA_READONLY_INVENTORY_CONTRACT: JIRA_READONLY_INVENTORY_ALLOWED_FIELDS,
    JIRA_CREATION_DRY_RUN_CONTRACT: JIRA_CREATION_DRY_RUN_ALLOWED_FIELDS,
}
SAFE_CONTRACT_NAMES = frozenset(CONTRACT_REQUIRED_FIELDS)
SAFE_STATUS_VALUES = frozenset({VALIDATION_PASS, VALIDATION_FAIL})
SAFE_OUTPUT_STATUS_VALUES = frozenset({"pass", "fail"})
SAFE_REASON_CODES = AUDIT_SAFE_REASON_CODES | {
    AUDIT_SINK_ACCEPTED,
    CONTRACT_MISSING_REQUIRED_FIELDS,
    CONTRACT_NOT_JSON_SERIALIZABLE,
    CONTRACT_SCHEMA_MISMATCH,
    CONTRACT_UNSAFE_OUTPUT,
    CONTRACT_UNKNOWN_FIELDS,
    CONTRACT_VALIDATION_PASSED,
    CONTRACT_WRONG_SHAPE,
    "guarded_execution_check_exception",
    "guarded_execution_doctor_contract_invalid",
    "guarded_execution_doctor_failed",
    "guarded_execution_doctor_output_unsafe",
    "guarded_execution_readiness_contract_invalid",
    "guarded_execution_readiness_failed",
    "guarded_execution_readiness_exception",
}
SAFE_REPORT_KIND_VALUES = frozenset({"guarded_execution_readiness"})
SAFE_CONNECTOR_SMOKE_REPORT_KIND_VALUES = frozenset(
    {"external_connector_readonly_smoke"}
)
SAFE_CONNECTOR_CONFIG_DOCTOR_REPORT_KIND_VALUES = frozenset(
    {"external_connector_config_doctor"}
)
SAFE_JIRA_READONLY_INVENTORY_REPORT_KIND_VALUES = frozenset(
    {"jira_readonly_inventory"}
)
SAFE_JIRA_CREATION_DRY_RUN_REPORT_KIND_VALUES = frozenset({"jira_creation_dry_run"})
SAFE_DOCTOR_MODE_VALUES = frozenset({"guarded_execution_doctor"})
SAFE_SINK_KIND_VALUES = frozenset({NOOP_AUDIT_SINK, IN_MEMORY_AUDIT_SINK})
SAFE_PROVIDER_CALL_MODES = frozenset(
    {"none", "synthetic", "live_readonly_attempted"}
)


@dataclass(frozen=True)
class GuardedExecutionContractValidation:
    contract_name: str
    validation_status: str
    reason_code: str
    missing_required_field_names: tuple[str, ...] = ()
    unknown_field_names: tuple[str, ...] = ()
    unsafe_pattern_count: int = 0
    unsafe_pattern_classes: tuple[str, ...] = ()
    schema_version: str = CONTRACT_VALIDATION_SCHEMA_VERSION
    safe_contract_class: str = CONTRACT_VALIDATION_CLASS

    @property
    def passed(self) -> bool:
        return self.validation_status == VALIDATION_PASS

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "contract_name": self.contract_name,
            "validation_status": self.validation_status,
            "reason_code": self.reason_code,
            "missing_required_field_names": list(self.missing_required_field_names),
            "unknown_field_names": list(self.unknown_field_names),
            "unsafe_pattern_count": self.unsafe_pattern_count,
            "unsafe_pattern_classes": list(self.unsafe_pattern_classes),
            "safe_contract_class": self.safe_contract_class,
        }


def validate_guarded_execution_contract(
    contract_name: str,
    payload: Any,
) -> GuardedExecutionContractValidation:
    safe_contract_name = _safe_contract_name(contract_name)
    if not _is_json_serializable(payload):
        return _validation_failure(
            safe_contract_name,
            CONTRACT_NOT_JSON_SERIALIZABLE,
        )
    if not isinstance(payload, Mapping):
        return _validation_failure(safe_contract_name, CONTRACT_WRONG_SHAPE)

    required_fields = CONTRACT_REQUIRED_FIELDS[safe_contract_name]
    allowed_fields = CONTRACT_ALLOWED_FIELDS[safe_contract_name]
    missing_fields = tuple(sorted(required_fields - set(payload)))
    if missing_fields:
        return _validation_failure(
            safe_contract_name,
            CONTRACT_MISSING_REQUIRED_FIELDS,
            missing_required_field_names=missing_fields,
        )

    unknown_fields = tuple(
        sorted(
            _safe_field_name(field_name)
            for field_name in set(payload) - allowed_fields
        )
    )
    if unknown_fields:
        return _validation_failure(
            safe_contract_name,
            CONTRACT_UNKNOWN_FIELDS,
            unknown_field_names=unknown_fields,
        )

    safety = inspect_operator_output(payload)
    if not safety.safe:
        return _validation_failure(
            safe_contract_name,
            CONTRACT_UNSAFE_OUTPUT,
            unsafe_pattern_count=safety.unsafe_pattern_count,
            unsafe_pattern_classes=safety.unsafe_pattern_classes,
        )

    if not _matches_contract_schema(safe_contract_name, payload):
        return _validation_failure(safe_contract_name, CONTRACT_SCHEMA_MISMATCH)

    return GuardedExecutionContractValidation(
        contract_name=safe_contract_name,
        validation_status=VALIDATION_PASS,
        reason_code=CONTRACT_VALIDATION_PASSED,
    )


def validate_audit_event_contract(
    payload: Any,
) -> GuardedExecutionContractValidation:
    return validate_guarded_execution_contract(AUDIT_EVENT_CONTRACT, payload)


def validate_audit_sink_summary_contract(
    payload: Any,
) -> GuardedExecutionContractValidation:
    return validate_guarded_execution_contract(AUDIT_SINK_SUMMARY_CONTRACT, payload)


def validate_doctor_output_contract(
    payload: Any,
) -> GuardedExecutionContractValidation:
    return validate_guarded_execution_contract(DOCTOR_OUTPUT_CONTRACT, payload)


def validate_readiness_report_contract(
    payload: Any,
) -> GuardedExecutionContractValidation:
    return validate_guarded_execution_contract(READINESS_REPORT_CONTRACT, payload)


def validate_connector_readonly_smoke_contract(
    payload: Any,
) -> GuardedExecutionContractValidation:
    return validate_guarded_execution_contract(CONNECTOR_READONLY_SMOKE_CONTRACT, payload)


def validate_external_connector_config_doctor_contract(
    payload: Any,
) -> GuardedExecutionContractValidation:
    return validate_guarded_execution_contract(
        EXTERNAL_CONNECTOR_CONFIG_DOCTOR_CONTRACT,
        payload,
    )


def validate_jira_readonly_inventory_contract(
    payload: Any,
) -> GuardedExecutionContractValidation:
    return validate_guarded_execution_contract(JIRA_READONLY_INVENTORY_CONTRACT, payload)


def validate_jira_creation_dry_run_contract(
    payload: Any,
) -> GuardedExecutionContractValidation:
    return validate_guarded_execution_contract(JIRA_CREATION_DRY_RUN_CONTRACT, payload)


def _matches_contract_schema(contract_name: str, payload: Mapping[str, Any]) -> bool:
    if contract_name == EXTERNAL_CONNECTOR_CONFIG_DOCTOR_CONTRACT:
        return (
            payload.get("report_kind") in SAFE_CONNECTOR_CONFIG_DOCTOR_REPORT_KIND_VALUES
            and payload.get("status") in SAFE_OUTPUT_STATUS_VALUES
            and _safe_reason_or_none(payload.get("reason_code"))
            and _common_safety_flags(payload)
            and isinstance(payload.get("providers"), Mapping)
            and isinstance(payload.get("summary"), Mapping)
            and isinstance(payload.get("checks"), list)
            and isinstance(payload.get("diagnostics"), Mapping)
        )
    if contract_name == CONNECTOR_READONLY_SMOKE_CONTRACT:
        return (
            payload.get("report_kind") in SAFE_CONNECTOR_SMOKE_REPORT_KIND_VALUES
            and payload.get("status") in SAFE_OUTPUT_STATUS_VALUES
            and _safe_reason_or_none(payload.get("reason_code"))
            and payload.get("no_send") is True
            and isinstance(payload.get("no_provider_calls"), bool)
            and payload.get("no_source_of_truth_mutation") is True
            and payload.get("scheduler_execution") in SAFE_SCHEDULER_STATUS
            and payload.get("provider_calls") in SAFE_PROVIDER_CALL_MODES
            and isinstance(payload.get("providers"), Mapping)
            and isinstance(payload.get("diagnostics"), Mapping)
        )
    if contract_name == JIRA_READONLY_INVENTORY_CONTRACT:
        return (
            payload.get("report_kind") in SAFE_JIRA_READONLY_INVENTORY_REPORT_KIND_VALUES
            and payload.get("status") in SAFE_OUTPUT_STATUS_VALUES
            and _safe_reason_or_none(payload.get("reason_code"))
            and payload.get("no_send") is True
            and isinstance(payload.get("no_provider_calls"), bool)
            and payload.get("no_source_of_truth_mutation") is True
            and payload.get("scheduler_execution") in SAFE_SCHEDULER_STATUS
            and payload.get("provider_calls") in SAFE_PROVIDER_CALL_MODES
            and isinstance(payload.get("jira"), Mapping)
            and isinstance(payload.get("portfolio_mapping"), Mapping)
            and isinstance(payload.get("operating_model"), Mapping)
            and _safe_reason_or_none(payload.get("recommended_next_action_class"))
            and isinstance(payload.get("diagnostics"), Mapping)
        )
    if contract_name == JIRA_CREATION_DRY_RUN_CONTRACT:
        return (
            payload.get("report_kind") in SAFE_JIRA_CREATION_DRY_RUN_REPORT_KIND_VALUES
            and payload.get("status") in SAFE_OUTPUT_STATUS_VALUES
            and _safe_reason_or_none(payload.get("reason_code"))
            and payload.get("dry_run_only") is True
            and _common_safety_flags(payload)
            and payload.get("jira_write_operations") == "disabled"
            and payload.get("manual_approval_required") is True
            and isinstance(payload.get("current_jira_assessment_class"), str)
            and isinstance(payload.get("migration_recommendation_class"), str)
            and isinstance(payload.get("proposed_structure"), Mapping)
            and _is_safe_string_list(payload.get("proposed_project_classes"))
            and _is_safe_string_list(payload.get("proposed_issue_type_classes"))
            and _is_safe_string_list(payload.get("proposed_workflow_status_classes"))
            and _is_safe_string_list(payload.get("proposed_board_classes"))
            and _is_safe_string_list(payload.get("governance_rule_classes"))
            and _is_safe_string_list(payload.get("migration_step_classes"))
            and _is_safe_string_list(payload.get("blocked_write_operation_classes"))
            and _is_safe_string_list(payload.get("follow_up_classes"))
            and isinstance(payload.get("next_step_class"), str)
            and isinstance(payload.get("diagnostics"), Mapping)
        )
    if not _common_safety_flags(payload):
        return False
    if contract_name == AUDIT_EVENT_CONTRACT:
        return (
            payload.get("schema_version") == AUDIT_SCHEMA_VERSION
            and payload.get("event_kind") == EVENT_KIND
            and payload.get("guard_name") in SAFE_GUARD_NAMES | {UNKNOWN_GUARD}
            and payload.get("operation_class")
            in SAFE_OPERATION_CLASSES | {UNKNOWN_OPERATION_CLASS}
            and payload.get("decision") in SAFE_DECISIONS
            and payload.get("reason_code") in SAFE_REASON_CODES | {UNKNOWN_REASON_CODE}
            and isinstance(payload.get("diagnostics"), Mapping)
        )
    if contract_name == AUDIT_SINK_SUMMARY_CONTRACT:
        return (
            payload.get("sink_kind") in SAFE_SINK_KIND_VALUES
            and isinstance(payload.get("event_count"), int)
            and payload.get("event_count", -1) >= 0
            and payload.get("accepted") is True
            and payload.get("reason_code") == AUDIT_SINK_ACCEPTED
            and isinstance(payload.get("guard_counts"), Mapping)
            and isinstance(payload.get("decision_counts"), Mapping)
            and isinstance(payload.get("reason_counts"), Mapping)
            and isinstance(payload.get("unsafe_pattern_count"), int)
            and payload.get("unsafe_pattern_count", -1) >= 0
            and _is_safe_string_list(payload.get("unsafe_pattern_classes"))
        )
    if contract_name == DOCTOR_OUTPUT_CONTRACT:
        return (
            payload.get("mode") in SAFE_DOCTOR_MODE_VALUES
            and payload.get("status") in SAFE_OUTPUT_STATUS_VALUES
            and _safe_reason_or_none(payload.get("reason_code"))
            and isinstance(payload.get("checks"), list)
            and isinstance(payload.get("diagnostics"), Mapping)
        )
    if contract_name == READINESS_REPORT_CONTRACT:
        return (
            payload.get("report_kind") in SAFE_REPORT_KIND_VALUES
            and payload.get("status") in SAFE_OUTPUT_STATUS_VALUES
            and _safe_reason_or_none(payload.get("reason_code"))
            and isinstance(payload.get("checks"), list)
            and isinstance(payload.get("connector_summary"), Mapping)
            and isinstance(payload.get("external_connector_config_summary"), Mapping)
            and isinstance(payload.get("connector_smoke_summary"), Mapping)
            and isinstance(payload.get("guard_summary"), Mapping)
            and isinstance(payload.get("portfolio_summary"), Mapping)
            and isinstance(payload.get("docs_summary"), Mapping)
            and isinstance(payload.get("remaining_risks"), Mapping)
            and isinstance(payload.get("diagnostics"), Mapping)
        )
    return False


def _common_safety_flags(payload: Mapping[str, Any]) -> bool:
    return (
        payload.get("no_send") is True
        and payload.get("no_provider_calls") is True
        and payload.get("no_source_of_truth_mutation") is True
        and payload.get("scheduler_execution") in SAFE_SCHEDULER_STATUS
    )


def _safe_reason_or_none(value: Any) -> bool:
    return value is None or (
        isinstance(value, str)
        and inspect_operator_output({"reason_code": value}).safe is True
    )


def _validation_failure(
    contract_name: str,
    reason_code: str,
    *,
    missing_required_field_names: tuple[str, ...] = (),
    unknown_field_names: tuple[str, ...] = (),
    unsafe_pattern_count: int = 0,
    unsafe_pattern_classes: tuple[str, ...] = (),
) -> GuardedExecutionContractValidation:
    return GuardedExecutionContractValidation(
        contract_name=contract_name,
        validation_status=VALIDATION_FAIL,
        reason_code=reason_code,
        missing_required_field_names=tuple(
            _safe_field_name(name) for name in missing_required_field_names
        ),
        unknown_field_names=tuple(_safe_field_name(name) for name in unknown_field_names),
        unsafe_pattern_count=max(0, unsafe_pattern_count),
        unsafe_pattern_classes=tuple(
            sorted(_safe_pattern_class(name) for name in unsafe_pattern_classes)
        ),
    )


def _safe_contract_name(contract_name: str) -> str:
    if contract_name in SAFE_CONTRACT_NAMES:
        return contract_name
    return AUDIT_EVENT_CONTRACT


def _safe_field_name(field_name: Any) -> str:
    value = str(field_name)
    if not value or inspect_operator_output({"field_name": value}).safe is not True:
        return "unsafe_field_name"
    cleaned = "".join(
        character if character.isalnum() or character == "_" else "_"
        for character in value.casefold()
    ).strip("_")
    return cleaned or "unknown_field"


def _safe_pattern_class(pattern_class: Any) -> str:
    value = str(pattern_class)
    if inspect_operator_output({"pattern_class": value}).safe is True:
        return _safe_field_name(value)
    return "unsafe_pattern_class"


def _is_json_serializable(payload: Any) -> bool:
    try:
        json.dumps(payload, sort_keys=True)
    except (TypeError, ValueError):
        return False
    return True


def _is_safe_string_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)
