"""Safe source connector contract and noop adapters.

Adapters in this module do not call external providers. They expose a stable
interface for the orchestrator, report masked readiness, and return terminal
results that are safe to persist in audit/result summaries.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol

from app.services.source_control import (
    ACTION_BACKFILL,
    ACTION_SYNC,
    ACTION_TEST,
    SOURCE_BY_TYPE,
    connector_setup_for_source,
    connector_setup_status,
)

CONNECTOR_STATUS_MISSING_CONFIG = "missing_config"
CONNECTOR_STATUS_SKIPPED = "skipped"
CONNECTOR_STATUS_SUCCEEDED = "succeeded"
CONNECTOR_STATUS_FAILED = "failed"

_INTERNAL_SOURCES = {
    "declarations",
    "manual_inputs",
    "generated_evidence",
    "share_packs",
}


@dataclass(frozen=True)
class ConnectorReadiness:
    source_type: str
    configured: bool
    missing_env_vars: list[str]
    masked_config_status: list[dict[str, Any]]
    can_test: bool
    can_sync: bool
    can_backfill: bool
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ConnectorRunResult:
    status: str
    source_type: str
    action_type: str
    started_at: datetime
    finished_at: datetime
    input_watermark: str | None = None
    output_watermark: str | None = None
    events_seen: int = 0
    events_ingested: int = 0
    normalized_events: int = 0
    graph_updates: int = 0
    findings_generated: int = 0
    proposals_generated: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    external_side_effect: bool = False
    sanitized_summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["started_at"] = self.started_at.isoformat()
        data["finished_at"] = self.finished_at.isoformat()
        return data


class SourceConnector(Protocol):
    source_type: str

    async def readiness(self) -> ConnectorReadiness: ...

    async def test_connection(self) -> ConnectorRunResult: ...

    async def sync(self, watermark: str | None = None) -> ConnectorRunResult: ...

    async def backfill(
        self,
        *,
        since: str | None = None,
        until: str | None = None,
        limit: int | None = None,
    ) -> ConnectorRunResult: ...


def _now() -> datetime:
    return datetime.now(timezone.utc)


class NoopSourceConnector:
    def __init__(self, source_type: str) -> None:
        if source_type not in SOURCE_BY_TYPE:
            raise ValueError(f"unknown source: {source_type}")
        self.source_type = source_type

    @property
    def _is_internal(self) -> bool:
        return self.source_type in _INTERNAL_SOURCES

    async def readiness(self) -> ConnectorReadiness:
        setup = connector_setup_for_source(self.source_type)
        status = connector_setup_status(self.source_type)
        missing = [
            str(item["name"])
            for item in setup
            if item.get("status") == "missing"
        ]
        configured = self._is_internal or status in {"ready", "not_required"}
        warnings: list[str] = []
        if missing:
            warnings.append("missing_config")
        elif not self._is_internal:
            warnings.append("adapter_noop_no_external_call")
        return ConnectorReadiness(
            source_type=self.source_type,
            configured=configured,
            missing_env_vars=missing,
            masked_config_status=setup,
            can_test=configured,
            can_sync=configured,
            can_backfill=configured,
            warnings=warnings,
        )

    async def test_connection(self) -> ConnectorRunResult:
        return await self._run(ACTION_TEST)

    async def sync(self, watermark: str | None = None) -> ConnectorRunResult:
        return await self._run(ACTION_SYNC, input_watermark=watermark)

    async def backfill(
        self,
        *,
        since: str | None = None,
        until: str | None = None,
        limit: int | None = None,
    ) -> ConnectorRunResult:
        return await self._run(
            ACTION_BACKFILL,
            sanitized_input={"since": since, "until": until, "limit": limit},
        )

    async def _run(
        self,
        action_type: str,
        *,
        input_watermark: str | None = None,
        sanitized_input: dict[str, Any] | None = None,
    ) -> ConnectorRunResult:
        started = _now()
        readiness = await self.readiness()
        if not readiness.configured:
            status = CONNECTOR_STATUS_MISSING_CONFIG
            warnings = ["missing_config", *readiness.warnings]
            summary = {
                "mode": "missing_config",
                "missing_env_vars": readiness.missing_env_vars,
            }
            output_watermark = input_watermark
        elif self._is_internal:
            status = CONNECTOR_STATUS_SUCCEEDED
            warnings = list(readiness.warnings)
            summary = {
                "mode": "local_noop",
                "source_type": self.source_type,
                "action_type": action_type,
            }
            output_watermark = started.isoformat()
        else:
            status = CONNECTOR_STATUS_SKIPPED
            warnings = ["adapter_noop_no_external_call"]
            summary = {
                "mode": "external_adapter_noop",
                "source_type": self.source_type,
                "action_type": action_type,
            }
            output_watermark = input_watermark
        if sanitized_input:
            summary["input"] = {
                key: value
                for key, value in sanitized_input.items()
                if value is not None
            }
        finished = _now()
        return ConnectorRunResult(
            status=status,
            source_type=self.source_type,
            action_type=action_type,
            started_at=started,
            finished_at=finished,
            input_watermark=input_watermark,
            output_watermark=output_watermark,
            warnings=warnings,
            external_side_effect=False,
            sanitized_summary=summary,
        )


def default_connector_registry() -> dict[str, SourceConnector]:
    return {
        source_type: NoopSourceConnector(source_type)
        for source_type in SOURCE_BY_TYPE
    }
