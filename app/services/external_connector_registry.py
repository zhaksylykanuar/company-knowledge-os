from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.operator_output_sanitizer import inspect_operator_output

CONNECTOR_STATUS_IMPLEMENTED = "implemented"
CONNECTOR_STATUS_PLANNED = "planned"
CONNECTOR_STATUS_SYNTHETIC_ONLY = "synthetic_only"

EXECUTION_MODE_LIVE_DEFAULT_DENIED = "live_default_denied"
EXECUTION_MODE_READ_ONLY_TRANSFORM = "read_only_transform"
EXECUTION_MODE_SYNTHETIC_ALLOWED = "synthetic_allowed"

ROLE_RAW_EVENT_SOURCE_ONLY = "raw_event_source_only"
ROLE_DELIVERY_INTERFACE_ONLY = "delivery_interface_only"
ROLE_MODEL_PROVIDER_ONLY = "model_provider_only"

PROVIDER_EXECUTION_GUARD = "provider_execution_guard"
PRODUCTION_OPERATION_GUARD = "production_operation_guard"
SCHEDULER_EXECUTION_GUARD = "scheduler_execution_guard"

REGISTRY_PRESENT = "present/safe_metadata_only"
LIVE_CALLS_DEFAULT_DENIED = "default_denied"
SOURCE_OF_TRUTH_MUTATION_ABSENT = "absent"
SCHEDULER_EXECUTION_DISABLED = "disabled"
PROVIDER_PAYLOAD_LEAKAGE_ABSENT = "absent"


@dataclass(frozen=True)
class ExternalConnectorSpec:
    provider_key: str
    connector_status: str
    execution_mode: str
    source_of_truth_role: str
    guard_requirements: tuple[str, ...]
    readiness_category: str
    synthetic_fetch_supported: bool
    no_send: bool = True
    no_source_of_truth_mutation: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider_key": self.provider_key,
            "connector_status": self.connector_status,
            "execution_mode": self.execution_mode,
            "source_of_truth_role": self.source_of_truth_role,
            "guard_requirements": list(self.guard_requirements),
            "readiness_category": self.readiness_category,
            "synthetic_fetch_supported": self.synthetic_fetch_supported,
            "no_send": self.no_send,
            "no_source_of_truth_mutation": self.no_source_of_truth_mutation,
        }


CONNECTOR_CATALOG: tuple[ExternalConnectorSpec, ...] = (
    ExternalConnectorSpec(
        provider_key="github",
        connector_status=CONNECTOR_STATUS_IMPLEMENTED,
        execution_mode=EXECUTION_MODE_LIVE_DEFAULT_DENIED,
        source_of_truth_role=ROLE_RAW_EVENT_SOURCE_ONLY,
        guard_requirements=(PROVIDER_EXECUTION_GUARD,),
        readiness_category="present/guarded/synthetic_ready",
        synthetic_fetch_supported=True,
    ),
    ExternalConnectorSpec(
        provider_key="jira",
        connector_status=CONNECTOR_STATUS_IMPLEMENTED,
        execution_mode=EXECUTION_MODE_LIVE_DEFAULT_DENIED,
        source_of_truth_role=ROLE_RAW_EVENT_SOURCE_ONLY,
        guard_requirements=(PROVIDER_EXECUTION_GUARD,),
        readiness_category="present/guarded/synthetic_ready",
        synthetic_fetch_supported=True,
    ),
    ExternalConnectorSpec(
        provider_key="gmail",
        connector_status=CONNECTOR_STATUS_IMPLEMENTED,
        execution_mode=EXECUTION_MODE_LIVE_DEFAULT_DENIED,
        source_of_truth_role=ROLE_RAW_EVENT_SOURCE_ONLY,
        guard_requirements=(PROVIDER_EXECUTION_GUARD,),
        readiness_category="present/guarded",
        synthetic_fetch_supported=False,
    ),
    ExternalConnectorSpec(
        provider_key="google_drive",
        connector_status=CONNECTOR_STATUS_IMPLEMENTED,
        execution_mode=EXECUTION_MODE_LIVE_DEFAULT_DENIED,
        source_of_truth_role=ROLE_RAW_EVENT_SOURCE_ONLY,
        guard_requirements=(PROVIDER_EXECUTION_GUARD,),
        readiness_category="present/guarded",
        synthetic_fetch_supported=False,
    ),
    ExternalConnectorSpec(
        provider_key="openai",
        connector_status=CONNECTOR_STATUS_IMPLEMENTED,
        execution_mode=EXECUTION_MODE_LIVE_DEFAULT_DENIED,
        source_of_truth_role=ROLE_MODEL_PROVIDER_ONLY,
        guard_requirements=(PROVIDER_EXECUTION_GUARD,),
        readiness_category="present/guarded",
        synthetic_fetch_supported=False,
    ),
    ExternalConnectorSpec(
        provider_key="telegram",
        connector_status=CONNECTOR_STATUS_IMPLEMENTED,
        execution_mode=EXECUTION_MODE_LIVE_DEFAULT_DENIED,
        source_of_truth_role=ROLE_DELIVERY_INTERFACE_ONLY,
        guard_requirements=(
            PROVIDER_EXECUTION_GUARD,
            PRODUCTION_OPERATION_GUARD,
            SCHEDULER_EXECUTION_GUARD,
        ),
        readiness_category="present/guarded",
        synthetic_fetch_supported=False,
    ),
    ExternalConnectorSpec(
        provider_key="slack",
        connector_status=CONNECTOR_STATUS_PLANNED,
        execution_mode=EXECUTION_MODE_LIVE_DEFAULT_DENIED,
        source_of_truth_role=ROLE_DELIVERY_INTERFACE_ONLY,
        guard_requirements=(
            PROVIDER_EXECUTION_GUARD,
            PRODUCTION_OPERATION_GUARD,
            SCHEDULER_EXECUTION_GUARD,
        ),
        readiness_category="planned/default_denied",
        synthetic_fetch_supported=False,
    ),
)


def connector_catalog() -> tuple[dict[str, Any], ...]:
    catalog = tuple(spec.as_dict() for spec in CONNECTOR_CATALOG)
    _assert_registry_safe(catalog)
    return catalog


def get_connector_spec(provider_key: str) -> ExternalConnectorSpec | None:
    for spec in CONNECTOR_CATALOG:
        if spec.provider_key == provider_key:
            return spec
    return None


def connector_readiness_summary() -> dict[str, Any]:
    catalog = connector_catalog()
    provider_statuses = {
        item["provider_key"]: item["readiness_category"] for item in catalog
    }
    summary = {
        "registry": REGISTRY_PRESENT,
        "provider_count": len(catalog),
        "synthetic_connector_count": sum(
            1 for item in catalog if item["synthetic_fetch_supported"] is True
        ),
        "provider_statuses": dict(sorted(provider_statuses.items())),
        "github_connector": provider_statuses.get("github", "missing"),
        "jira_connector": provider_statuses.get("jira", "missing"),
        "live_calls": LIVE_CALLS_DEFAULT_DENIED,
        "source_of_truth_mutation": SOURCE_OF_TRUTH_MUTATION_ABSENT,
        "scheduler_execution": SCHEDULER_EXECUTION_DISABLED,
        "payload_leakage": PROVIDER_PAYLOAD_LEAKAGE_ABSENT,
    }
    _assert_registry_safe(summary)
    return summary


def connector_inventory_categories() -> dict[str, str]:
    return {
        "github": "guarded_live_boundary",
        "jira": "guarded_live_boundary",
        "gmail": "already_guarded",
        "google_drive": "already_guarded",
        "openai": "already_guarded",
        "telegram": "already_guarded_delivery_interface",
        "slack": "planned_connector",
        "source_activity": "read_only_local_transform",
        "payload_mapper": "read_only_local_transform",
    }


def _assert_registry_safe(value: Any) -> None:
    diagnostics = inspect_operator_output(value)
    if not diagnostics.safe:
        raise ValueError("external_connector_registry_unsafe")
