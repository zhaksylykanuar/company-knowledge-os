from __future__ import annotations

from dataclasses import dataclass

PRODUCTION_OPERATION_ACK = "ALLOW PRODUCTION OPERATION"
PRODUCTION_OPERATION_ALLOWED = "production_operation_allowed"
PRODUCTION_OPERATION_DEFAULT_DENIED = "production_operation_default_denied"
PRODUCTION_OPERATION_ACK_REQUIRED = "production_operation_ack_required"

PRODUCTION_DB_OPERATION = "production_db_operation"
MIGRATION_OPERATION = "migration_operation"
SOURCE_OF_TRUTH_MUTATION = "source_of_truth_mutation"
RAW_STORAGE_MUTATION = "raw_storage_mutation"
OBSIDIAN_VAULT_MUTATION = "obsidian_vault_mutation"
DELIVERY_EXECUTION = "delivery_execution"
DESTRUCTIVE_CLEANUP = "destructive_cleanup"
SCHEDULER_EXECUTION = "scheduler_execution"

SAFE_OPERATION_CLASSES = frozenset(
    {
        PRODUCTION_DB_OPERATION,
        MIGRATION_OPERATION,
        SOURCE_OF_TRUTH_MUTATION,
        RAW_STORAGE_MUTATION,
        OBSIDIAN_VAULT_MUTATION,
        DELIVERY_EXECUTION,
        DESTRUCTIVE_CLEANUP,
        SCHEDULER_EXECUTION,
    }
)


@dataclass(frozen=True)
class ProductionOperationDiagnostics:
    operation_class: str
    boundary: str
    reason_code: str
    allowed: bool

    def as_dict(self) -> dict[str, str | bool]:
        return {
            "operation_class": self.operation_class,
            "boundary": self.boundary,
            "reason_code": self.reason_code,
            "allowed": self.allowed,
        }


class ProductionOperationBlockedError(RuntimeError):
    def __init__(
        self,
        *,
        operation_class: str,
        boundary: str,
        reason_code: str,
    ) -> None:
        super().__init__(reason_code)
        self.diagnostics = ProductionOperationDiagnostics(
            operation_class=operation_class,
            boundary=boundary,
            reason_code=reason_code,
            allowed=False,
        )

    @property
    def reason_code(self) -> str:
        return self.diagnostics.reason_code


def _safe_operation_class(operation_class: str) -> str:
    if operation_class in SAFE_OPERATION_CLASSES:
        return operation_class
    return "source_of_truth_mutation"


def require_production_operation_ack(
    *,
    operation_class: str,
    boundary: str,
    allow_production_operation: bool = False,
    production_operation_ack: str | None = None,
) -> ProductionOperationDiagnostics:
    safe_class = _safe_operation_class(operation_class)

    if allow_production_operation is not True:
        raise ProductionOperationBlockedError(
            operation_class=safe_class,
            boundary=boundary,
            reason_code=PRODUCTION_OPERATION_DEFAULT_DENIED,
        )

    if production_operation_ack != PRODUCTION_OPERATION_ACK:
        raise ProductionOperationBlockedError(
            operation_class=safe_class,
            boundary=boundary,
            reason_code=PRODUCTION_OPERATION_ACK_REQUIRED,
        )

    return ProductionOperationDiagnostics(
        operation_class=safe_class,
        boundary=boundary,
        reason_code=PRODUCTION_OPERATION_ALLOWED,
        allowed=True,
    )
