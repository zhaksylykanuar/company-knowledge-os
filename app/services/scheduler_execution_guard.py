from __future__ import annotations

from dataclasses import dataclass

MANUAL_OPERATOR_EXECUTION = "manual_operator_execution"
READ_ONLY_REVIEW_EXECUTION = "read_only_review_execution"
LOCAL_SYNTHETIC_EXECUTION = "local_synthetic_execution"

SCHEDULER_EXECUTION = "scheduler_execution"
OUTBOX_DRAIN = "outbox_drain"
AUTOMATIC_DELIVERY = "automatic_delivery"
BACKGROUND_DISPATCH = "background_dispatch"
RETRY_WORKER = "retry_worker"

SCHEDULER_EXECUTION_NOT_REQUESTED = "scheduler_execution_not_requested"
SCHEDULER_EXECUTION_DISABLED = "scheduler_execution_disabled"
OUTBOX_DRAIN_DISABLED = "outbox_drain_disabled"
AUTOMATIC_DELIVERY_DISABLED = "automatic_delivery_disabled"
BACKGROUND_DISPATCH_DISABLED = "background_dispatch_disabled"
RETRY_WORKER_DISABLED = "retry_worker_disabled"

SAFE_NON_SCHEDULER_EXECUTION_SOURCES = frozenset(
    {
        MANUAL_OPERATOR_EXECUTION,
        READ_ONLY_REVIEW_EXECUTION,
        LOCAL_SYNTHETIC_EXECUTION,
    }
)
SAFE_DISABLED_EXECUTION_SOURCES = frozenset(
    {
        SCHEDULER_EXECUTION,
        OUTBOX_DRAIN,
        AUTOMATIC_DELIVERY,
        BACKGROUND_DISPATCH,
        RETRY_WORKER,
    }
)
SAFE_EXECUTION_SOURCES = (
    SAFE_NON_SCHEDULER_EXECUTION_SOURCES | SAFE_DISABLED_EXECUTION_SOURCES
)
DISABLED_REASON_BY_SOURCE = {
    SCHEDULER_EXECUTION: SCHEDULER_EXECUTION_DISABLED,
    OUTBOX_DRAIN: OUTBOX_DRAIN_DISABLED,
    AUTOMATIC_DELIVERY: AUTOMATIC_DELIVERY_DISABLED,
    BACKGROUND_DISPATCH: BACKGROUND_DISPATCH_DISABLED,
    RETRY_WORKER: RETRY_WORKER_DISABLED,
}


@dataclass(frozen=True)
class SchedulerExecutionDiagnostics:
    execution_source: str
    boundary: str
    reason_code: str
    allowed: bool

    def as_dict(self) -> dict[str, str | bool]:
        return {
            "execution_source": self.execution_source,
            "boundary": self.boundary,
            "reason_code": self.reason_code,
            "allowed": self.allowed,
        }


class SchedulerExecutionBlockedError(RuntimeError):
    def __init__(
        self,
        *,
        execution_source: str,
        boundary: str,
        reason_code: str,
    ) -> None:
        super().__init__(reason_code)
        self.diagnostics = SchedulerExecutionDiagnostics(
            execution_source=execution_source,
            boundary=boundary,
            reason_code=reason_code,
            allowed=False,
        )

    @property
    def reason_code(self) -> str:
        return self.diagnostics.reason_code


def _safe_execution_source(execution_source: str) -> str:
    if execution_source in SAFE_EXECUTION_SOURCES:
        return execution_source
    return SCHEDULER_EXECUTION


def require_no_scheduler_execution(
    *,
    boundary: str,
    execution_source: str = MANUAL_OPERATOR_EXECUTION,
) -> SchedulerExecutionDiagnostics:
    safe_source = _safe_execution_source(execution_source)
    disabled_reason = DISABLED_REASON_BY_SOURCE.get(safe_source)
    if disabled_reason is not None:
        raise SchedulerExecutionBlockedError(
            execution_source=safe_source,
            boundary=boundary,
            reason_code=disabled_reason,
        )

    return SchedulerExecutionDiagnostics(
        execution_source=safe_source,
        boundary=boundary,
        reason_code=SCHEDULER_EXECUTION_NOT_REQUESTED,
        allowed=True,
    )
