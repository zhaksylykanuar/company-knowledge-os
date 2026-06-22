from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from app.services.operator_output_sanitizer import inspect_operator_output

PORTFOLIO_PROVIDER_KEY = "github"
PORTFOLIO_SOURCE_CLASS = "static_repository_overview"
PORTFOLIO_CURRENT_AS_OF = "2026_06_01"
PORTFOLIO_TOTAL_COUNT = 19
PORTFOLIO_SEED_SOURCE_CLASS = "legacy_personal_account_seed"
PORTFOLIO_SEED_STATUS = "present"
PORTFOLIO_SOURCE_OF_TRUTH_STATUS = "planning_metadata_only"

TARGET_OWNER_CLASS = "github_organization"
TARGET_ORG_KEY = "qtwin-io"
TARGET_ORG_STATUS_CLASS = "manual_migration_target"
TARGET_ORG_INVENTORY_STATUS = "gated_not_verified"
TARGET_ORG_CURRENT_REPO_COUNT_CLASS = "one_repo_reported_by_operator"
TARGET_ORG_EXISTING_ROLE_CLASS = "frontend_repo_present"
TARGET_REMAINING_MIGRATION_COUNT_CLASS = "nonzero_count"
MIGRATION_STATUS_CLASS = "manual_org_migration_planned"
GITHUB_WRITE_OPERATIONS_DISABLED = "disabled"
GITHUB_REPO_TRANSFER_OPERATIONS_DISABLED = "disabled"
GITHUB_REPO_EDIT_OPERATIONS_DISABLED = "disabled"

LIFECYCLE_ACTIVE = "active"
LIFECYCLE_SUPPORT = "support_or_periodic"
LIFECYCLE_LEGACY = "legacy_or_archive"

CONNECTOR_PRIORITY_HIGH = "priority_high"
CONNECTOR_PRIORITY_MEDIUM = "priority_medium"
CONNECTOR_PRIORITY_LOW = "priority_low"

ROLE_RAW_EVENT_SOURCE_CANDIDATE = "raw_event_source_candidate"
ROLE_APP_CODEBASE = "app_codebase"
ROLE_INFRASTRUCTURE_CODEBASE = "infrastructure_codebase"
ROLE_LEGACY_REFERENCE = "legacy_reference"

ACTION_GITHUB_DESCRIPTION_MISSING = "github_description_missing"
ACTION_README_MISSING = "readme_missing"
ACTION_TOPICS_MISSING = "topics_missing"
ACTION_ARCHIVE_CANDIDATE = "archive_candidate"
ACTION_SECRET_ROTATION_REQUIRED = "secret_rotation_required"

LIVE_API_NOT_VERIFIED = "not_verified"
JIRA_MAPPING_NOT_MAPPED = "not_mapped"
GITHUB_LIVE_INVENTORY_GATED_NOT_VERIFIED = "gated_not_verified"
JIRA_MAPPING_PLANNED_NOT_VERIFIED = "planned_not_verified"
PORTFOLIO_CATALOG_PRESENT = "present/safe_counts_only"
SOURCE_OF_TRUTH_MUTATION_ABSENT = "absent"
SCHEDULER_EXECUTION_DISABLED = "disabled"

SAFE_PRODUCT_AREAS = frozenset(
    {
        "ar_mr",
        "infrastructure_monitoring_collectors",
        "kazscan_corporate_site",
        "marketing_landing",
        "ssap_digital_twin",
        "three_d_gaussian_splatting",
        "video",
    }
)
SAFE_LIFECYCLE_STATUSES = frozenset(
    {LIFECYCLE_ACTIVE, LIFECYCLE_SUPPORT, LIFECYCLE_LEGACY}
)
SAFE_CONNECTOR_PRIORITIES = frozenset(
    {CONNECTOR_PRIORITY_HIGH, CONNECTOR_PRIORITY_MEDIUM, CONNECTOR_PRIORITY_LOW}
)
SAFE_SOURCE_ROLES = frozenset(
    {
        ROLE_RAW_EVENT_SOURCE_CANDIDATE,
        ROLE_APP_CODEBASE,
        ROLE_INFRASTRUCTURE_CODEBASE,
        ROLE_LEGACY_REFERENCE,
    }
)
SAFE_ACTION_CLASSES = frozenset(
    {
        ACTION_GITHUB_DESCRIPTION_MISSING,
        ACTION_README_MISSING,
        ACTION_TOPICS_MISSING,
        ACTION_ARCHIVE_CANDIDATE,
        ACTION_SECRET_ROTATION_REQUIRED,
    }
)


@dataclass(frozen=True)
class RepositoryPortfolioEntry:
    repo_key: str
    provider_key: str
    product_area: str
    lifecycle_status: str
    stack_class: str
    connector_priority: str
    source_role: str
    action_classes: tuple[str, ...]
    live_api_status: str = LIVE_API_NOT_VERIFIED
    jira_mapping_status: str = JIRA_MAPPING_NOT_MAPPED
    no_send: bool = True
    no_source_of_truth_mutation: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "repo_key": self.repo_key,
            "provider_key": self.provider_key,
            "product_area": self.product_area,
            "lifecycle_status": self.lifecycle_status,
            "stack_class": self.stack_class,
            "connector_priority": self.connector_priority,
            "source_role": self.source_role,
            "action_classes": list(self.action_classes),
            "live_api_status": self.live_api_status,
            "jira_mapping_status": self.jira_mapping_status,
            "no_send": self.no_send,
            "no_source_of_truth_mutation": self.no_source_of_truth_mutation,
        }


REPOSITORY_PORTFOLIO: tuple[RepositoryPortfolioEntry, ...] = (
    RepositoryPortfolioEntry(
        repo_key="qaztwin-ssap-frontend",
        provider_key=PORTFOLIO_PROVIDER_KEY,
        product_area="ssap_digital_twin",
        lifecycle_status=LIFECYCLE_ACTIVE,
        stack_class="frontend_app",
        connector_priority=CONNECTOR_PRIORITY_HIGH,
        source_role=ROLE_APP_CODEBASE,
        action_classes=(ACTION_TOPICS_MISSING,),
    ),
    RepositoryPortfolioEntry(
        repo_key="qaztwin-ssap-backend",
        provider_key=PORTFOLIO_PROVIDER_KEY,
        product_area="ssap_digital_twin",
        lifecycle_status=LIFECYCLE_ACTIVE,
        stack_class="backend_api",
        connector_priority=CONNECTOR_PRIORITY_HIGH,
        source_role=ROLE_APP_CODEBASE,
        action_classes=(ACTION_TOPICS_MISSING,),
    ),
    RepositoryPortfolioEntry(
        repo_key="qaztwin-ssap-chat",
        provider_key=PORTFOLIO_PROVIDER_KEY,
        product_area="ssap_digital_twin",
        lifecycle_status=LIFECYCLE_ACTIVE,
        stack_class="chat_service",
        connector_priority=CONNECTOR_PRIORITY_HIGH,
        source_role=ROLE_RAW_EVENT_SOURCE_CANDIDATE,
        action_classes=(ACTION_GITHUB_DESCRIPTION_MISSING,),
    ),
    RepositoryPortfolioEntry(
        repo_key="qaztwin-ssap-worker",
        provider_key=PORTFOLIO_PROVIDER_KEY,
        product_area="ssap_digital_twin",
        lifecycle_status=LIFECYCLE_ACTIVE,
        stack_class="worker_service",
        connector_priority=CONNECTOR_PRIORITY_HIGH,
        source_role=ROLE_APP_CODEBASE,
        action_classes=(ACTION_TOPICS_MISSING,),
    ),
    RepositoryPortfolioEntry(
        repo_key="qaztwin-ssap-zone-slicer",
        provider_key=PORTFOLIO_PROVIDER_KEY,
        product_area="ssap_digital_twin",
        lifecycle_status=LIFECYCLE_ACTIVE,
        stack_class="geospatial_processing",
        connector_priority=CONNECTOR_PRIORITY_HIGH,
        source_role=ROLE_RAW_EVENT_SOURCE_CANDIDATE,
        action_classes=(ACTION_GITHUB_DESCRIPTION_MISSING, ACTION_README_MISSING),
    ),
    RepositoryPortfolioEntry(
        repo_key="qaztwin-ssap-voice-transcribe",
        provider_key=PORTFOLIO_PROVIDER_KEY,
        product_area="ssap_digital_twin",
        lifecycle_status=LIFECYCLE_SUPPORT,
        stack_class="audio_ml_service",
        connector_priority=CONNECTOR_PRIORITY_MEDIUM,
        source_role=ROLE_RAW_EVENT_SOURCE_CANDIDATE,
        action_classes=(ACTION_README_MISSING,),
    ),
    RepositoryPortfolioEntry(
        repo_key="qaztwin-ssap-test",
        provider_key=PORTFOLIO_PROVIDER_KEY,
        product_area="ssap_digital_twin",
        lifecycle_status=LIFECYCLE_SUPPORT,
        stack_class="test_harness",
        connector_priority=CONNECTOR_PRIORITY_MEDIUM,
        source_role=ROLE_APP_CODEBASE,
        action_classes=(ACTION_GITHUB_DESCRIPTION_MISSING,),
    ),
    RepositoryPortfolioEntry(
        repo_key="ssap-potree-converter",
        provider_key=PORTFOLIO_PROVIDER_KEY,
        product_area="ssap_digital_twin",
        lifecycle_status=LIFECYCLE_SUPPORT,
        stack_class="data_converter",
        connector_priority=CONNECTOR_PRIORITY_MEDIUM,
        source_role=ROLE_RAW_EVENT_SOURCE_CANDIDATE,
        action_classes=(ACTION_README_MISSING,),
    ),
    RepositoryPortfolioEntry(
        repo_key="kazscan-corp",
        provider_key=PORTFOLIO_PROVIDER_KEY,
        product_area="kazscan_corporate_site",
        lifecycle_status=LIFECYCLE_ACTIVE,
        stack_class="corporate_site",
        connector_priority=CONNECTOR_PRIORITY_HIGH,
        source_role=ROLE_APP_CODEBASE,
        action_classes=(ACTION_TOPICS_MISSING,),
    ),
    RepositoryPortfolioEntry(
        repo_key="kazscan-corp-backend",
        provider_key=PORTFOLIO_PROVIDER_KEY,
        product_area="kazscan_corporate_site",
        lifecycle_status=LIFECYCLE_ACTIVE,
        stack_class="backend_api",
        connector_priority=CONNECTOR_PRIORITY_HIGH,
        source_role=ROLE_APP_CODEBASE,
        action_classes=(ACTION_TOPICS_MISSING,),
    ),
    RepositoryPortfolioEntry(
        repo_key="supersplat-viewer",
        provider_key=PORTFOLIO_PROVIDER_KEY,
        product_area="three_d_gaussian_splatting",
        lifecycle_status=LIFECYCLE_ACTIVE,
        stack_class="three_d_viewer",
        connector_priority=CONNECTOR_PRIORITY_HIGH,
        source_role=ROLE_RAW_EVENT_SOURCE_CANDIDATE,
        action_classes=(ACTION_GITHUB_DESCRIPTION_MISSING,),
    ),
    RepositoryPortfolioEntry(
        repo_key="influx-puller",
        provider_key=PORTFOLIO_PROVIDER_KEY,
        product_area="infrastructure_monitoring_collectors",
        lifecycle_status=LIFECYCLE_SUPPORT,
        stack_class="data_collector",
        connector_priority=CONNECTOR_PRIORITY_MEDIUM,
        source_role=ROLE_INFRASTRUCTURE_CODEBASE,
        action_classes=(ACTION_TOPICS_MISSING,),
    ),
    RepositoryPortfolioEntry(
        repo_key="qaztwin-monitor",
        provider_key=PORTFOLIO_PROVIDER_KEY,
        product_area="infrastructure_monitoring_collectors",
        lifecycle_status=LIFECYCLE_SUPPORT,
        stack_class="monitoring_service",
        connector_priority=CONNECTOR_PRIORITY_MEDIUM,
        source_role=ROLE_INFRASTRUCTURE_CODEBASE,
        action_classes=(ACTION_GITHUB_DESCRIPTION_MISSING,),
    ),
    RepositoryPortfolioEntry(
        repo_key="qaztwin-scada-collector",
        provider_key=PORTFOLIO_PROVIDER_KEY,
        product_area="infrastructure_monitoring_collectors",
        lifecycle_status=LIFECYCLE_SUPPORT,
        stack_class="scada_collector",
        connector_priority=CONNECTOR_PRIORITY_MEDIUM,
        source_role=ROLE_INFRASTRUCTURE_CODEBASE,
        action_classes=(ACTION_TOPICS_MISSING,),
    ),
    RepositoryPortfolioEntry(
        repo_key="base-collector",
        provider_key=PORTFOLIO_PROVIDER_KEY,
        product_area="infrastructure_monitoring_collectors",
        lifecycle_status=LIFECYCLE_LEGACY,
        stack_class="data_collector",
        connector_priority=CONNECTOR_PRIORITY_LOW,
        source_role=ROLE_LEGACY_REFERENCE,
        action_classes=(
            ACTION_ARCHIVE_CANDIDATE,
            ACTION_SECRET_ROTATION_REQUIRED,
        ),
    ),
    RepositoryPortfolioEntry(
        repo_key="qaztwin-tsk-collector",
        provider_key=PORTFOLIO_PROVIDER_KEY,
        product_area="infrastructure_monitoring_collectors",
        lifecycle_status=LIFECYCLE_SUPPORT,
        stack_class="data_collector",
        connector_priority=CONNECTOR_PRIORITY_MEDIUM,
        source_role=ROLE_INFRASTRUCTURE_CODEBASE,
        action_classes=(ACTION_TOPICS_MISSING,),
    ),
    RepositoryPortfolioEntry(
        repo_key="qtwin-frigate-nvr",
        provider_key=PORTFOLIO_PROVIDER_KEY,
        product_area="video",
        lifecycle_status=LIFECYCLE_SUPPORT,
        stack_class="video_nvr",
        connector_priority=CONNECTOR_PRIORITY_MEDIUM,
        source_role=ROLE_INFRASTRUCTURE_CODEBASE,
        action_classes=(ACTION_GITHUB_DESCRIPTION_MISSING,),
    ),
    RepositoryPortfolioEntry(
        repo_key="Project-Megane",
        provider_key=PORTFOLIO_PROVIDER_KEY,
        product_area="ar_mr",
        lifecycle_status=LIFECYCLE_LEGACY,
        stack_class="ar_mr_app",
        connector_priority=CONNECTOR_PRIORITY_LOW,
        source_role=ROLE_LEGACY_REFERENCE,
        action_classes=(ACTION_ARCHIVE_CANDIDATE, ACTION_README_MISSING),
    ),
    RepositoryPortfolioEntry(
        repo_key="landing-qaztwin",
        provider_key=PORTFOLIO_PROVIDER_KEY,
        product_area="marketing_landing",
        lifecycle_status=LIFECYCLE_SUPPORT,
        stack_class="landing_page",
        connector_priority=CONNECTOR_PRIORITY_MEDIUM,
        source_role=ROLE_APP_CODEBASE,
        action_classes=(ACTION_GITHUB_DESCRIPTION_MISSING, ACTION_TOPICS_MISSING),
    ),
)


def repository_portfolio_catalog() -> tuple[dict[str, Any], ...]:
    return tuple(entry.as_dict() for entry in REPOSITORY_PORTFOLIO)


def repository_portfolio_public_summary() -> dict[str, Any]:
    validation = validate_repository_portfolio()
    target_org = summarize_target_org_status()
    migration_counts = summarize_portfolio_migration_counts()
    inventory = _repository_source_inventory_snapshot()
    summary = {
        "portfolio_catalog": PORTFOLIO_CATALOG_PRESENT,
        "provider_key": PORTFOLIO_PROVIDER_KEY,
        "source_class": PORTFOLIO_SOURCE_CLASS,
        "seed_source_class": PORTFOLIO_SEED_SOURCE_CLASS,
        "seed_portfolio_status": PORTFOLIO_SEED_STATUS,
        "overview_current_as_of": PORTFOLIO_CURRENT_AS_OF,
        "repo_total_count": inventory["operational_repo_count"],
        "repo_total_count_source": inventory["operational_repo_source"],
        "operational_repo_count": inventory["operational_repo_count"],
        "operational_repo_source": inventory["operational_repo_source"],
        "operational_repo_count_class": inventory["operational_repo_count_class"],
        "source_event_repo_count": inventory["source_event_repo_count"],
        "discovery_repo_count": inventory["discovery_repo_count"],
        "legacy_seed_repo_count": inventory["legacy_seed_repo_count"],
        "catalog_drift": _catalog_drift_counts(inventory["catalog_drift"]),
        "repository_inventory_source_priority": inventory["source_priority"],
        "product_area_count": len(_count_by("product_area")),
        "product_area_counts": _count_by("product_area"),
        "lifecycle_status_counts": _count_by("lifecycle_status"),
        "action_class_counts": _action_class_counts(),
        "connector_priority_counts": _count_by("connector_priority"),
        "stack_class_count": len(_count_by("stack_class")),
        "github_live_inventory_status": GITHUB_LIVE_INVENTORY_GATED_NOT_VERIFIED,
        "target_owner_class": target_org["target_owner_class"],
        "target_org_key": target_org["target_org_key"],
        "target_org_status_class": target_org["target_org_status_class"],
        "migration_status_class": target_org["migration_status_class"],
        "target_org_inventory_status": target_org["target_org_inventory_status"],
        "target_org_current_repo_count_class": target_org[
            "target_org_current_repo_count_class"
        ],
        "target_org_existing_role_class": target_org["target_org_existing_role_class"],
        "target_expected_migration_count": migration_counts[
            "target_expected_migration_count"
        ],
        "operational_migration_candidate_count": migration_counts[
            "operational_migration_candidate_count"
        ],
        "legacy_seed_migration_candidate_count": migration_counts[
            "legacy_seed_migration_candidate_count"
        ],
        "target_remaining_migration_count_class": migration_counts[
            "target_remaining_migration_count_class"
        ],
        "source_of_truth_status": PORTFOLIO_SOURCE_OF_TRUTH_STATUS,
        "github_write_operations": GITHUB_WRITE_OPERATIONS_DISABLED,
        "github_repo_transfer_operations": GITHUB_REPO_TRANSFER_OPERATIONS_DISABLED,
        "github_repo_edit_operations": GITHUB_REPO_EDIT_OPERATIONS_DISABLED,
        "jira_mapping_status": JIRA_MAPPING_PLANNED_NOT_VERIFIED,
        "validation_status": validation["validation_status"],
        "validation_reason_code": validation["reason_code"],
        "no_send": True,
        "no_source_of_truth_mutation": True,
        "scheduler_execution": SCHEDULER_EXECUTION_DISABLED,
        "source_of_truth_mutation": SOURCE_OF_TRUTH_MUTATION_ABSENT,
    }
    _assert_public_summary_safe(summary)
    return summary


def validate_repository_portfolio() -> dict[str, Any]:
    errors: list[str] = []
    entries = REPOSITORY_PORTFOLIO
    if len(entries) != PORTFOLIO_TOTAL_COUNT:
        errors.append("portfolio_total_count_mismatch")

    expected_lifecycle_counts = {
        LIFECYCLE_ACTIVE: 8,
        LIFECYCLE_SUPPORT: 9,
        LIFECYCLE_LEGACY: 2,
    }
    if _count_by("lifecycle_status") != expected_lifecycle_counts:
        errors.append("portfolio_lifecycle_count_mismatch")

    for entry in entries:
        if entry.provider_key != PORTFOLIO_PROVIDER_KEY:
            errors.append("portfolio_provider_key_invalid")
        if entry.product_area not in SAFE_PRODUCT_AREAS:
            errors.append("portfolio_product_area_invalid")
        if entry.lifecycle_status not in SAFE_LIFECYCLE_STATUSES:
            errors.append("portfolio_lifecycle_status_invalid")
        if entry.connector_priority not in SAFE_CONNECTOR_PRIORITIES:
            errors.append("portfolio_connector_priority_invalid")
        if entry.source_role not in SAFE_SOURCE_ROLES:
            errors.append("portfolio_source_role_invalid")
        if not set(entry.action_classes) <= SAFE_ACTION_CLASSES:
            errors.append("portfolio_action_class_invalid")
        if not entry.no_send or not entry.no_source_of_truth_mutation:
            errors.append("portfolio_safety_flag_invalid")
        if _entry_contains_unsafe_action_material(entry):
            errors.append("portfolio_action_material_unsafe")

    secret_rotation_count = _action_class_counts().get(ACTION_SECRET_ROTATION_REQUIRED, 0)
    if secret_rotation_count != 1:
        errors.append("portfolio_secret_rotation_count_mismatch")

    return {
        "validation_status": "pass" if not errors else "fail",
        "reason_code": "repository_portfolio_valid"
        if not errors
        else "repository_portfolio_invalid",
        "error_classes": sorted(set(errors)),
        "repo_total_count": len(entries),
        "no_send": True,
        "no_source_of_truth_mutation": True,
        "scheduler_execution": SCHEDULER_EXECUTION_DISABLED,
    }


def repository_portfolio_onboarding_plan_summary() -> dict[str, Any]:
    summary = repository_portfolio_public_summary()
    plan = {
        "github_inventory_step": "target_org_manual_readonly_gated",
        "github_seed_comparison_step": "operational_inventory_with_legacy_seed_reconciliation",
        "github_target_owner_class": summary["target_owner_class"],
        "github_target_org_key": summary["target_org_key"],
        "github_org_migration_status": summary["migration_status_class"],
        "github_org_live_inventory_status": summary["target_org_inventory_status"],
        "jira_mapping_step": "manual_mapping_planned",
        "metadata_update_execution": "not_implemented",
        "archive_execution": "not_implemented",
        "secret_rotation_execution": "not_implemented",
        "repo_total_count": summary["repo_total_count"],
        "operational_repo_count": summary["operational_repo_count"],
        "operational_repo_source": summary["operational_repo_source"],
        "target_expected_migration_count": summary["target_expected_migration_count"],
        "legacy_seed_migration_candidate_count": summary[
            "legacy_seed_migration_candidate_count"
        ],
        "target_remaining_migration_count_class": summary[
            "target_remaining_migration_count_class"
        ],
        "github_write_operations": summary["github_write_operations"],
        "github_repo_transfer_operations": summary["github_repo_transfer_operations"],
        "github_repo_edit_operations": summary["github_repo_edit_operations"],
        "action_class_counts": summary["action_class_counts"],
        "no_send": True,
        "no_source_of_truth_mutation": True,
        "scheduler_execution": SCHEDULER_EXECUTION_DISABLED,
    }
    _assert_public_summary_safe(plan)
    return plan


def summarize_target_org_status() -> dict[str, Any]:
    summary = {
        "target_owner_class": TARGET_OWNER_CLASS,
        "target_org_key": TARGET_ORG_KEY,
        "target_org_status_class": TARGET_ORG_STATUS_CLASS,
        "migration_status_class": MIGRATION_STATUS_CLASS,
        "target_org_inventory_status": TARGET_ORG_INVENTORY_STATUS,
        "target_org_current_repo_count_class": TARGET_ORG_CURRENT_REPO_COUNT_CLASS,
        "target_org_existing_role_class": TARGET_ORG_EXISTING_ROLE_CLASS,
        "github_write_operations": GITHUB_WRITE_OPERATIONS_DISABLED,
        "github_repo_transfer_operations": GITHUB_REPO_TRANSFER_OPERATIONS_DISABLED,
        "github_repo_edit_operations": GITHUB_REPO_EDIT_OPERATIONS_DISABLED,
        "no_send": True,
        "no_source_of_truth_mutation": True,
        "scheduler_execution": SCHEDULER_EXECUTION_DISABLED,
    }
    _assert_public_summary_safe(summary)
    return summary


def summarize_portfolio_migration_counts() -> dict[str, Any]:
    inventory = _repository_source_inventory_snapshot()
    operational_count = int(inventory["operational_repo_count"])
    legacy_seed_count = int(inventory["legacy_seed_repo_count"])
    summary = {
        "seed_portfolio_count": legacy_seed_count,
        "legacy_seed_repo_count": legacy_seed_count,
        "legacy_seed_migration_candidate_count": legacy_seed_count,
        "operational_repo_count": operational_count,
        "operational_repo_source": inventory["operational_repo_source"],
        "operational_migration_candidate_count": operational_count,
        "target_expected_migration_count": operational_count,
        "target_org_current_repo_count_class": TARGET_ORG_CURRENT_REPO_COUNT_CLASS,
        "target_remaining_migration_count_class": TARGET_REMAINING_MIGRATION_COUNT_CLASS,
        "migration_status_class": MIGRATION_STATUS_CLASS,
        "source_of_truth_status": PORTFOLIO_SOURCE_OF_TRUTH_STATUS,
        "repo_mapping_policy": inventory["repo_mapping_policy"],
        "no_send": True,
        "no_source_of_truth_mutation": True,
        "scheduler_execution": SCHEDULER_EXECUTION_DISABLED,
    }
    _assert_public_summary_safe(summary)
    return summary


def summarize_org_migration_readiness() -> dict[str, Any]:
    target_org = summarize_target_org_status()
    migration_counts = summarize_portfolio_migration_counts()
    summary = {
        "seed_source_class": PORTFOLIO_SEED_SOURCE_CLASS,
        "seed_portfolio_status": PORTFOLIO_SEED_STATUS,
        "seed_portfolio_count": migration_counts["seed_portfolio_count"],
        "operational_repo_count": migration_counts["operational_repo_count"],
        "operational_repo_source": migration_counts["operational_repo_source"],
        "target_owner_class": target_org["target_owner_class"],
        "target_org_key": target_org["target_org_key"],
        "target_org_current_repo_count_class": target_org[
            "target_org_current_repo_count_class"
        ],
        "target_expected_migration_count": migration_counts[
            "target_expected_migration_count"
        ],
        "target_remaining_migration_count_class": migration_counts[
            "target_remaining_migration_count_class"
        ],
        "migration_status_class": target_org["migration_status_class"],
        "target_org_inventory_status": target_org["target_org_inventory_status"],
        "source_of_truth_status": PORTFOLIO_SOURCE_OF_TRUTH_STATUS,
        "github_write_operations": target_org["github_write_operations"],
        "github_repo_transfer_operations": target_org[
            "github_repo_transfer_operations"
        ],
        "github_repo_edit_operations": target_org["github_repo_edit_operations"],
        "no_send": True,
        "no_source_of_truth_mutation": True,
        "scheduler_execution": SCHEDULER_EXECUTION_DISABLED,
    }
    _assert_public_summary_safe(summary)
    return summary


def _count_by(field_name: str) -> dict[str, int]:
    counts = Counter(getattr(entry, field_name) for entry in REPOSITORY_PORTFOLIO)
    return dict(sorted(counts.items()))


def _action_class_counts() -> dict[str, int]:
    counts: Counter[str] = Counter()
    for entry in REPOSITORY_PORTFOLIO:
        counts.update(entry.action_classes)
    return dict(sorted(counts.items()))


def _entry_contains_unsafe_action_material(entry: RepositoryPortfolioEntry) -> bool:
    action_values = " ".join(entry.action_classes)
    return "token" in action_values.casefold() or "://" in action_values


def _catalog_drift_counts(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": str(value.get("status") or "unknown"),
        "operational_count": int(value.get("operational_count") or 0),
        "legacy_seed_count": int(value.get("legacy_seed_count") or 0),
        "matched_count": int(value.get("matched_count") or 0),
        "operational_only_count": len(
            value.get("in_operational_not_in_legacy_seed") or []
        ),
        "legacy_seed_only_count": len(
            value.get("in_legacy_seed_not_in_operational") or []
        ),
        "repo_mapping_policy": str(value.get("repo_mapping_policy") or ""),
    }


def _repository_source_inventory_snapshot() -> dict[str, Any]:
    from app.services.repository_source_inventory import (
        load_repository_source_inventory_snapshot,
    )

    return load_repository_source_inventory_snapshot()


def _assert_public_summary_safe(value: Mapping[str, Any]) -> None:
    diagnostics = inspect_operator_output(value)
    if not diagnostics.safe:
        raise ValueError("repository_portfolio_summary_unsafe")


def _repo_keys(entries: Iterable[RepositoryPortfolioEntry]) -> set[str]:
    return {entry.repo_key for entry in entries}
