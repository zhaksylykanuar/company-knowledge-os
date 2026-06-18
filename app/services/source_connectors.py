"""Safe source connector contract and noop adapters.

Adapters in this module do not call external providers. They expose a stable
interface for the orchestrator, report masked readiness, and return terminal
results that are safe to persist in audit/result summaries.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Protocol

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.agent_models import AgentProposal
from app.db.declaration_models import FounderDeclaration
from app.db.gmail_models import EmailThreadState, GmailMessage
from app.db.second_opinion_models import SecondOpinionFinding
from app.db.share_pack_models import SharePack
from app.db.source_models import SourceDocument
from app.services.browser_config import sanitize_for_logs
from app.services.connector_scope import connector_limits
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
CONNECTOR_STATUS_PARTIAL_SUCCEEDED = "partial_succeeded"

_INTERNAL_SOURCES = {
    "declarations",
    "manual_inputs",
    "generated_evidence",
    "share_packs",
    "meetings",
}

# External sources that have a real read-only client boundary (gated behind
# FOUNDEROS_ENABLE_REAL_CONNECTORS). Gmail stays local-only in Stage 15.
REAL_CLIENT_SOURCES = {"jira", "github"}

_CONNECTOR_SENSITIVE_KEY_PARTS = (
    "authorization",
    "body",
    "cookie",
    "html",
    "oauth",
    "raw",
)


def _sanitize_connector_payload(value: Any) -> Any:
    value = sanitize_for_logs(value)
    if isinstance(value, dict):
        safe: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key).casefold()
            if any(part in key_text for part in _CONNECTOR_SENSITIVE_KEY_PARTS):
                safe[str(key)] = "***redacted***" if item not in (None, "") else item
            else:
                safe[str(key)] = _sanitize_connector_payload(item)
        return safe
    if isinstance(value, list):
        return [_sanitize_connector_payload(item) for item in value]
    return value


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


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
class ConnectorEvent:
    source_type: str
    external_id: str
    object_type: str
    event_type: str
    occurred_at: datetime | None = None
    title: str | None = None
    summary: str | None = None
    actor: str | None = None
    url: str | None = None
    sanitized_payload: dict[str, Any] = field(default_factory=dict)
    raw_object_ref: str | None = None
    content_hash: str | None = None
    visibility_scope: str = "founder"
    source_metadata: dict[str, Any] = field(default_factory=dict)
    run_id: str | None = None
    correlation_id: str | None = None

    def safe_payload(self) -> dict[str, Any]:
        payload = _sanitize_connector_payload(dict(self.sanitized_payload or {}))
        if not isinstance(payload, dict):
            payload = {}
        payload.setdefault("source_object_type", self.object_type)
        if self.title:
            payload.setdefault("title", self.title)
        if self.summary:
            payload.setdefault("summary", self.summary)
        if self.actor:
            payload.setdefault("actor_external_id", self.actor)
        if self.url:
            payload.setdefault("source_url", self.url)
        payload.setdefault("visibility_scope", self.visibility_scope)
        if self.occurred_at:
            payload.setdefault("occurred_at", self.occurred_at.isoformat())
        metadata = sanitize_for_logs(dict(self.source_metadata or {}))
        if isinstance(metadata, dict) and metadata:
            payload.setdefault("source_metadata", metadata)
        return payload

    def payload_was_redacted(self) -> bool:
        original = dict(self.sanitized_payload or {})
        sanitized = _sanitize_connector_payload(original)
        return _stable_json(original) != _stable_json(sanitized)

    def stable_content_hash(self) -> str:
        if self.content_hash:
            return self.content_hash
        payload = {
            "source_type": self.source_type,
            "external_id": self.external_id,
            "object_type": self.object_type,
            "event_type": self.event_type,
            "occurred_at": self.occurred_at.isoformat() if self.occurred_at else None,
            "title": self.title,
            "summary": self.summary,
            "actor": self.actor,
            "url": self.url,
            "sanitized_payload": self.safe_payload(),
        }
        blob = _stable_json(payload).encode("utf-8")
        return sha256(blob).hexdigest()

    def safe_raw_object_ref(self) -> str:
        if self.raw_object_ref:
            return self.raw_object_ref
        return f"raw://{self.source_type}/{self.object_type}/{self.external_id}/{self.stable_content_hash()}.json"

    def to_connector_payload(self) -> dict[str, Any]:
        content_hash = self.stable_content_hash()
        return {
            "source_system": self.source_type,
            "source_object_type": self.object_type,
            "source_object_id": self.external_id,
            "event_type": self.event_type,
            "idempotency_key": f"{self.source_type}:{self.external_id}:{content_hash}",
            "raw_object_ref": self.safe_raw_object_ref(),
            "correlation_id": self.correlation_id,
            "trace_id": self.run_id,
            "payload": {
                **self.safe_payload(),
                "content_hash": content_hash,
                "run_id": self.run_id,
                "correlation_id": self.correlation_id,
            },
        }

    def to_safe_summary(self) -> dict[str, Any]:
        return {
            "source_type": self.source_type,
            "external_id": self.external_id,
            "object_type": self.object_type,
            "event_type": self.event_type,
            "occurred_at": self.occurred_at.isoformat() if self.occurred_at else None,
            "title": self.title,
            "content_hash": self.stable_content_hash(),
            "visibility_scope": self.visibility_scope,
        }


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
    pages_read: int = 0
    page_size: int | None = None
    limit_applied: int | None = None
    stopped_reason: str | None = None
    retry_after_seconds: int | None = None
    rate_limit_remaining: int | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    external_side_effect: bool = False
    sanitized_summary: dict[str, Any] = field(default_factory=dict)
    events: list[ConnectorEvent] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["started_at"] = self.started_at.isoformat()
        data["finished_at"] = self.finished_at.isoformat()
        data["events"] = [event.to_safe_summary() for event in self.events]
        data["event_count"] = len(self.events)
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


class ReadOnlyConnectorClient(Protocol):
    async def test_connection(self, source_type: str) -> dict[str, Any]: ...

    async def sync_events(
        self,
        source_type: str,
        *,
        watermark: str | None = None,
    ) -> list[ConnectorEvent]: ...

    async def backfill_events(
        self,
        source_type: str,
        *,
        since: str | None = None,
        until: str | None = None,
        limit: int | None = None,
    ) -> list[ConnectorEvent]: ...


def _now() -> datetime:
    return datetime.now(timezone.utc)


class NoopSourceConnector:
    def __init__(
        self,
        source_type: str,
        *,
        session: AsyncSession | None = None,
        client: ReadOnlyConnectorClient | None = None,
        real_disabled: bool = False,
    ) -> None:
        if source_type not in SOURCE_BY_TYPE:
            raise ValueError(f"unknown source: {source_type}")
        self.source_type = source_type
        self._session = session
        self._client = client
        self._real_disabled = real_disabled

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
        has_local_gmail = self.source_type == "gmail" and await _has_local_gmail_data(
            self._session
        )
        configured = self._is_internal or has_local_gmail or status in {"ready", "not_required"}
        warnings: list[str] = []
        if missing and not has_local_gmail:
            warnings.append("missing_config")
        elif not self._is_internal:
            warnings.append(
                "local_email_records"
                if has_local_gmail
                else "adapter_noop_no_external_call"
            )
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
            events: list[ConnectorEvent] = []
        elif self._real_disabled and self._client is None and not self._is_internal:
            # Configured external source, but real connector execution is off.
            # Skip safely (no network, no fake success).
            status = CONNECTOR_STATUS_SKIPPED
            warnings = ["real_connectors_disabled", *readiness.warnings]
            summary = {
                "mode": "real_connectors_disabled",
                "reason": "real_connectors_disabled",
                "real_execution": "disabled",
                "source_type": self.source_type,
                "action_type": action_type,
            }
            output_watermark = input_watermark
            events = []
        elif self._client is not None:
            status = CONNECTOR_STATUS_SUCCEEDED
            warnings = list(readiness.warnings)
            summary = {
                "mode": "read_only_client",
                "real_execution": "enabled",
                "source_type": self.source_type,
                "action_type": action_type,
            }
            if action_type == ACTION_TEST:
                check = sanitize_for_logs(
                    await self._client.test_connection(self.source_type)
                )
                summary["test_connection"] = check
                events = []
                output_watermark = input_watermark
            elif action_type == ACTION_SYNC:
                events = await self._client.sync_events(
                    self.source_type,
                    watermark=input_watermark,
                )
                output_watermark = _events_watermark(events) or input_watermark
            else:
                events = await self._client.backfill_events(
                    self.source_type,
                    since=(sanitized_input or {}).get("since"),
                    until=(sanitized_input or {}).get("until"),
                    limit=(sanitized_input or {}).get("limit"),
                )
                output_watermark = input_watermark
        elif self._is_internal or "local_email_records" in readiness.warnings:
            # Internal sources and email read from already-ingested local
            # records (no external call). This keeps local-only mode honest:
            # a real successful run, not a fake "connected" from env presence.
            status = CONNECTOR_STATUS_SUCCEEDED
            warnings = list(readiness.warnings)
            events = [] if action_type == ACTION_TEST else await self._local_events()
            summary = {
                "mode": "local_noop" if self._is_internal else "local_records",
                "source_type": self.source_type,
                "action_type": action_type,
                "events_generated": len(events),
            }
            output_watermark = _events_watermark(events) or started.isoformat()
        else:
            status = CONNECTOR_STATUS_SKIPPED
            warnings = ["adapter_noop_no_external_call"]
            summary = {
                "mode": "external_adapter_noop",
                "source_type": self.source_type,
                "action_type": action_type,
            }
            output_watermark = input_watermark
            events = []
        if sanitized_input:
            summary["input"] = {
                key: value
                for key, value in sanitized_input.items()
                if value is not None
            }
        finished = _now()
        limits = connector_limits()
        limit_applied = (
            limits["sync_limit"]
            if action_type == ACTION_SYNC
            else limits["backfill_limit"]
            if action_type == ACTION_BACKFILL
            else None
        )
        stopped_reason = "no_more_results"
        if status == CONNECTOR_STATUS_MISSING_CONFIG:
            stopped_reason = "missing_config"
        elif status == CONNECTOR_STATUS_SKIPPED:
            stopped_reason = summary.get("reason") or "disabled"
        elif limit_applied is not None and len(events) >= int(limit_applied):
            stopped_reason = "limit_reached"
        return ConnectorRunResult(
            status=status,
            source_type=self.source_type,
            action_type=action_type,
            started_at=started,
            finished_at=finished,
            input_watermark=input_watermark,
            output_watermark=output_watermark,
            events_seen=len(events),
            pages_read=1 if action_type in {ACTION_SYNC, ACTION_BACKFILL} and events else 0,
            page_size=limit_applied,
            limit_applied=limit_applied,
            stopped_reason=stopped_reason,
            warnings=warnings,
            external_side_effect=False,
            sanitized_summary=summary,
            events=events,
        )

    async def _local_events(self) -> list[ConnectorEvent]:
        if self._session is None:
            return []
        if self.source_type == "declarations":
            return await _declaration_events(self._session)
        if self.source_type == "manual_inputs":
            return await _manual_input_events(self._session)
        if self.source_type == "meetings":
            return await _meeting_events(self._session)
        if self.source_type == "gmail":
            return await _gmail_local_events(self._session)
        if self.source_type == "generated_evidence":
            return await _generated_evidence_events(self._session)
        if self.source_type == "share_packs":
            return await _share_pack_events(self._session)
        return []


def _events_watermark(events: list[ConnectorEvent]) -> str | None:
    occurred = [event.occurred_at for event in events if event.occurred_at is not None]
    if not occurred:
        return None
    return max(occurred).isoformat()


def _internal_event(
    *,
    external_id: str,
    object_type: str,
    title: str,
    summary: str | None = None,
    occurred_at: datetime | None = None,
    source_metadata: dict[str, Any] | None = None,
    raw_object_ref: str | None = None,
) -> ConnectorEvent:
    return ConnectorEvent(
        source_type="internal",
        external_id=external_id,
        object_type="system_event",
        event_type="internal.system_event.recorded",
        occurred_at=occurred_at,
        title=title,
        summary=summary,
        raw_object_ref=raw_object_ref,
        sanitized_payload={
            "title": title,
            "summary": summary or title,
            "source_object_type": "system_event",
        },
        source_metadata=source_metadata or {"object_type": object_type},
    )


async def _declaration_events(session: AsyncSession) -> list[ConnectorEvent]:
    rows = (
        await session.execute(
            select(FounderDeclaration).order_by(FounderDeclaration.updated_at.desc()).limit(100)
        )
    ).scalars()
    events: list[ConnectorEvent] = []
    for row in rows:
        payload = sanitize_for_logs(row.payload or {})
        events.append(
            _internal_event(
                external_id=f"declaration:{row.declaration_key}",
                object_type="declaration",
                title=f"Declaration updated: {row.declaration_key}",
                summary=str(payload)[:500],
                occurred_at=row.updated_at,
                source_metadata={
                    "source_type": "declarations",
                    "declaration_key": row.declaration_key,
                    "payload": payload,
                },
            )
        )
    return events


async def _manual_input_events(session: AsyncSession) -> list[ConnectorEvent]:
    rows = (
        await session.execute(
            select(SourceDocument)
            .where(SourceDocument.source_system == "manual")
            .order_by(SourceDocument.updated_at.desc())
            .limit(100)
        )
    ).scalars()
    return [
        _internal_event(
            external_id=f"manual:{row.source_document_id}",
            object_type="manual_input",
            title=row.title or row.source_document_id,
            summary=f"Manual input document {row.source_document_id}",
            occurred_at=row.updated_at,
            raw_object_ref=row.raw_object_ref,
            source_metadata={
                "source_type": "manual_inputs",
                "source_document_id": row.source_document_id,
                "content_hash": row.content_hash,
            },
        )
        for row in rows
    ]


async def _meeting_events(session: AsyncSession) -> list[ConnectorEvent]:
    rows = (
        await session.execute(
            select(SourceDocument)
            .where(SourceDocument.source_system.in_(("meeting", "meetings", "calendar", "drive")))
            .order_by(SourceDocument.updated_at.desc())
            .limit(100)
        )
    ).scalars()
    events: list[ConnectorEvent] = []
    for row in rows:
        if row.source_system == "drive":
            events.append(
                ConnectorEvent(
                    source_type="drive",
                    external_id=row.source_object_id,
                    object_type="file",
                    event_type="drive.file.ingested",
                    occurred_at=row.updated_at,
                    title=row.title or row.source_object_id,
                    summary=f"Meeting/document source {row.source_document_id}",
                    url=row.source_url,
                    raw_object_ref=row.raw_object_ref,
                    sanitized_payload={
                        "title": row.title or row.source_object_id,
                        "source_object_type": "file",
                        "source_document_id": row.source_document_id,
                    },
                    source_metadata={"source_type": "meetings"},
                )
            )
        else:
            events.append(
                _internal_event(
                    external_id=f"meeting:{row.source_document_id}",
                    object_type="meeting_note",
                    title=row.title or row.source_document_id,
                    summary=f"Meeting source document {row.source_document_id}",
                    occurred_at=row.updated_at,
                    raw_object_ref=row.raw_object_ref,
                    source_metadata={"source_type": "meetings"},
                )
            )
    return events


async def _gmail_local_events(session: AsyncSession) -> list[ConnectorEvent]:
    thread_rows = (
        await session.execute(
            select(EmailThreadState)
            .order_by(EmailThreadState.updated_at.desc())
            .limit(100)
        )
    ).scalars()
    events = [
        ConnectorEvent(
            source_type="gmail",
            external_id=row.provider_thread_id or row.thread_key,
            object_type="message",
            event_type="gmail.message.ingested",
            occurred_at=row.last_message_at or row.updated_at,
            title=row.subject_display or row.subject_normalized or row.thread_key,
            summary=row.thread_summary or row.last_message_summary,
            actor=row.last_message_from,
            raw_object_ref=f"raw://gmail/thread_state/{row.thread_key}",
            sanitized_payload={
                "subject": row.subject_display or row.subject_normalized or row.thread_key,
                "summary": row.thread_summary or row.last_message_summary or "",
                "source_object_type": "message",
                "thread_key": row.thread_key,
                "status": row.status,
            },
            source_metadata={"source_type": "gmail", "messages_count": row.messages_count},
        )
        for row in thread_rows
    ]
    if events:
        return events
    message_rows = (
        await session.execute(
            select(GmailMessage).order_by(GmailMessage.created_at.desc()).limit(100)
        )
    ).scalars()
    return [
        ConnectorEvent(
            source_type="gmail",
            external_id=row.message_id,
            object_type="message",
            event_type="gmail.message.ingested",
            occurred_at=row.created_at,
            title=str((row.payload or {}).get("subject") or row.message_id),
            summary=row.snippet,
            raw_object_ref=row.raw_object_ref,
            sanitized_payload={
                "subject": str((row.payload or {}).get("subject") or row.message_id),
                "summary": row.snippet or "",
                "source_object_type": "message",
                "thread_id": row.thread_id,
            },
            source_metadata={"source_type": "gmail"},
        )
        for row in message_rows
    ]


async def _has_local_gmail_data(session: AsyncSession | None) -> bool:
    if session is None:
        return False
    thread_count = await session.scalar(select(func.count(EmailThreadState.id)))
    if int(thread_count or 0) > 0:
        return True
    message_count = await session.scalar(select(func.count(GmailMessage.id)))
    return int(message_count or 0) > 0


async def _generated_evidence_events(session: AsyncSession) -> list[ConnectorEvent]:
    findings = (
        await session.execute(
            select(SecondOpinionFinding)
            .order_by(SecondOpinionFinding.updated_at.desc())
            .limit(100)
        )
    ).scalars()
    events = [
        _internal_event(
            external_id=f"finding:{row.finding_key}",
            object_type="finding",
            title=row.summary,
            summary=f"{row.finding_type}; severity={row.severity}; status={row.status}",
            occurred_at=row.updated_at,
            source_metadata={
                "source_type": "generated_evidence",
                "finding_key": row.finding_key,
                "entity_id": row.entity_id,
                "confidence": row.confidence,
            },
        )
        for row in findings
    ]
    proposals = (
        await session.execute(
            select(AgentProposal).order_by(AgentProposal.created_at.desc()).limit(100)
        )
    ).scalars()
    events.extend(
        _internal_event(
            external_id=f"proposal:{row.proposal_id}",
            object_type="proposal",
            title=row.title,
            summary=f"{row.kind}; status={row.status}",
            occurred_at=row.created_at,
            source_metadata={
                "source_type": "generated_evidence",
                "proposal_id": row.proposal_id,
                "confidence": row.confidence,
            },
        )
        for row in proposals
    )
    return events


async def _share_pack_events(session: AsyncSession) -> list[ConnectorEvent]:
    rows = (
        await session.execute(
            select(SharePack).order_by(SharePack.updated_at.desc()).limit(100)
        )
    ).scalars()
    return [
        _internal_event(
            external_id=f"share_pack:{row.pack_id}:{row.status}:{row.content_hash}",
            object_type="share_pack",
            title=row.title,
            summary=f"{row.pack_type}; audience={row.audience}; status={row.status}",
            occurred_at=row.updated_at,
            source_metadata={
                "source_type": "share_packs",
                "pack_id": row.pack_id,
                "status": row.status,
                "content_hash": row.content_hash,
            },
        )
        for row in rows
    ]


def default_connector_registry(
    *,
    session: AsyncSession | None = None,
    clients: dict[str, ReadOnlyConnectorClient] | None = None,
    config: Any = None,
) -> dict[str, SourceConnector]:
    """Build the connector registry.

    Real Jira/GitHub clients are wired ONLY when ``enable_real_connectors`` is
    true. When it is false, those sources get ``real_disabled=True`` so a
    configured source is safely skipped (no network, no fake success) instead of
    silently succeeding. Internal and local sources are unaffected. Explicit
    ``clients`` (used by tests) always take precedence.
    """

    from app.core.config import settings as default_settings

    cfg = config if config is not None else default_settings
    overrides = clients or {}
    enabled = bool(getattr(cfg, "enable_real_connectors", False))
    real_clients: dict[str, ReadOnlyConnectorClient] = {}
    if enabled:
        from app.services.connector_clients import build_real_connector_clients

        real_clients = build_real_connector_clients(cfg)

    registry: dict[str, SourceConnector] = {}
    for source_type in SOURCE_BY_TYPE:
        client = overrides.get(source_type)
        real_disabled = False
        if client is None and source_type in REAL_CLIENT_SOURCES:
            if enabled:
                client = real_clients.get(source_type)
            else:
                real_disabled = True
        registry[source_type] = NoopSourceConnector(
            source_type,
            session=session,
            client=client,
            real_disabled=real_disabled,
        )
    return registry
