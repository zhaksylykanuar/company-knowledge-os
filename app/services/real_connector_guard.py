from __future__ import annotations

from app.core.config import Settings, settings

REAL_CONNECTORS_DISABLED_DETAIL = "real provider connectors are disabled"


class RealConnectorsDisabledError(RuntimeError):
    def __init__(self, detail: str = REAL_CONNECTORS_DISABLED_DETAIL) -> None:
        super().__init__(detail)
        self.detail = detail


def require_real_connectors_enabled(*, config: Settings = settings) -> None:
    """Fail closed before any real provider credential or network operation."""

    if not config.enable_real_connectors:
        raise RealConnectorsDisabledError
