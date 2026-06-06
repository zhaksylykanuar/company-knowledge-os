from __future__ import annotations

from dataclasses import dataclass

LIVE_PROVIDER_EXECUTION_ACK = "ALLOW LIVE PROVIDER EXECUTION"
PROVIDER_EXECUTION_ALLOWED = "provider_execution_allowed"
PROVIDER_EXECUTION_DEFAULT_DENIED = "provider_execution_default_denied"
PROVIDER_EXECUTION_ACK_REQUIRED = "provider_execution_ack_required"


@dataclass(frozen=True)
class ProviderExecutionDiagnostics:
    provider: str
    boundary: str
    execution_mode: str
    reason_code: str
    allowed: bool

    def as_dict(self) -> dict[str, str | bool]:
        return {
            "provider": self.provider,
            "boundary": self.boundary,
            "execution_mode": self.execution_mode,
            "reason_code": self.reason_code,
            "allowed": self.allowed,
        }


class ProviderExecutionBlockedError(RuntimeError):
    def __init__(
        self,
        *,
        provider: str,
        boundary: str,
        reason_code: str,
        execution_mode: str = "live_provider",
    ) -> None:
        super().__init__(reason_code)
        self.diagnostics = ProviderExecutionDiagnostics(
            provider=provider,
            boundary=boundary,
            execution_mode=execution_mode,
            reason_code=reason_code,
            allowed=False,
        )

    @property
    def reason_code(self) -> str:
        return self.diagnostics.reason_code


def require_live_provider_execution_ack(
    *,
    provider: str,
    boundary: str,
    allow_live_provider_execution: bool = False,
    provider_execution_ack: str | None = None,
) -> ProviderExecutionDiagnostics:
    if allow_live_provider_execution is not True:
        raise ProviderExecutionBlockedError(
            provider=provider,
            boundary=boundary,
            reason_code=PROVIDER_EXECUTION_DEFAULT_DENIED,
        )

    if provider_execution_ack != LIVE_PROVIDER_EXECUTION_ACK:
        raise ProviderExecutionBlockedError(
            provider=provider,
            boundary=boundary,
            reason_code=PROVIDER_EXECUTION_ACK_REQUIRED,
        )

    return ProviderExecutionDiagnostics(
        provider=provider,
        boundary=boundary,
        execution_mode="live_provider",
        reason_code=PROVIDER_EXECUTION_ALLOWED,
        allowed=True,
    )
