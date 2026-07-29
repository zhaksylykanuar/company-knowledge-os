"""Local Gmail connector foundation.

This module implements only the safe MVP slice for Gmail: deterministic local
message import into canonical ``SourceRecord`` rows and a read-only list surface.
It never calls Gmail, never performs external writes, never invokes an LLM, and
never reads encrypted connection token fields.

Unlike the Jira slice, Gmail messages are not tasks, so they are persisted to
``SourceRecord`` only (no ``Task`` row). Raw email bodies are intentionally not
persisted; only a narrow evidence-backed projection (subject, participants,
labels, dates, and a bounded snippet) is stored.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any
from uuid import UUID

from sqlalchemy import literal_column, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.canonical_models import SOURCE_RECORD_PROVIDER_GMAIL, SourceRecord
from app.db.integration_models import INTEGRATION_PROVIDER_GMAIL, IntegrationConnection

GMAIL_SOURCE_RECORD_TYPE_MESSAGE = "message"
GMAIL_IMPORT_SOURCE = "local_json_import"
GMAIL_SNIPPET_LIMIT = 500
GMAIL_UNREAD_LABEL = "unread"
GMAIL_IMPORT_BOUNDARY_NOTE = (
    "Local Gmail message import writes only founderOS canonical SourceRecord rows "
    "with a narrow projection (no raw body); it starts no Gmail provider call, no "
    "sync, no external write, and no LLM."
)

_SENSITIVE_KEY_MARKERS = (
    "api_key",
    "auth_header",
    "authorization",
    "credential",
    "password",
    "private_key",
    "secret",
    "token",
    "webhook",
)


class GmailConnectorError(ValueError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


@dataclass(frozen=True)
class GmailImportFailure:
    index: int
    reason: str

    def as_payload(self) -> dict[str, Any]:
        return {"index": self.index, "reason": self.reason}


@dataclass
class GmailImportCounts:
    received: int = 0
    imported: int = 0
    failed: int = 0
    source_records_created: int = 0
    source_records_updated: int = 0

    def as_payload(self) -> dict[str, int]:
        return {
            "received": self.received,
            "imported": self.imported,
            "failed": self.failed,
            "source_records_created": self.source_records_created,
            "source_records_updated": self.source_records_updated,
        }


@dataclass
class GmailMessageImportResult:
    counts: GmailImportCounts
    messages: list[dict[str, Any]] = field(default_factory=list)
    failures: list[GmailImportFailure] = field(default_factory=list)
    warnings: list[str] = field(default_factory=lambda: [GMAIL_IMPORT_BOUNDARY_NOTE])

    def as_payload(self, *, workspace_id: UUID) -> dict[str, Any]:
        return {
            "workspace_id": str(workspace_id),
            "counts": self.counts.as_payload(),
            "messages": self.messages,
            "failures": [failure.as_payload() for failure in self.failures],
            "boundary": gmail_connector_boundary(),
            "warnings": self.warnings,
        }


async def list_workspace_gmail_messages(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    limit: int = 100,
) -> dict[str, Any]:
    """List locally imported Gmail message source records for a workspace.

    Read-only: no provider calls, no sync, no external writes, no secret reads.
    """

    bounded_limit = max(1, min(limit, 200))
    records = list(
        (
            await session.execute(
                select(SourceRecord)
                .where(SourceRecord.workspace_id == workspace_id)
                .where(SourceRecord.provider == SOURCE_RECORD_PROVIDER_GMAIL)
                .where(SourceRecord.record_type == GMAIL_SOURCE_RECORD_TYPE_MESSAGE)
                .where(SourceRecord.is_deleted.is_(False))
                .order_by(
                    SourceRecord.source_updated_at.desc().nullslast(),
                    SourceRecord.created_at.desc(),
                )
                .limit(bounded_limit)
            )
        ).scalars()
    )
    messages = [_gmail_message_payload(record) for record in records]
    unread_count = sum(1 for message in messages if message.get("unread"))
    return {
        "workspace_id": str(workspace_id),
        "messages": messages,
        "counts": {
            "total": len(messages),
            "unread": unread_count,
            "read": len(messages) - unread_count,
        },
        "boundary": gmail_connector_boundary(),
        "warnings": []
        if messages
        else ["No local Gmail message records have been imported yet."],
    }


async def import_gmail_messages_local(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    raw_messages: Sequence[Mapping[str, Any]],
    connection_id: UUID | None = None,
) -> GmailMessageImportResult:
    """Import user-supplied Gmail message snapshots into canonical local rows.

    The input is treated as untrusted provider data. Only a narrow normalized
    projection is persisted (no raw body). Sensitive-looking keys are dropped,
    and no provider calls/writes/LLM calls are performed.
    """

    validated_connection_id = None
    if connection_id is not None:
        validated_connection_id = await _load_gmail_connection_id(
            session,
            workspace_id=workspace_id,
            connection_id=connection_id,
        )

    observed_at = datetime.now(timezone.utc)
    result = GmailMessageImportResult(counts=GmailImportCounts(received=len(raw_messages)))

    for index, raw_message in enumerate(raw_messages):
        try:
            normalized = build_normalized_gmail_message(raw_message)
        except GmailConnectorError as exc:
            result.failures.append(GmailImportFailure(index=index, reason=exc.detail))
            continue

        source_record, created = await _upsert_gmail_source_record(
            session,
            workspace_id=workspace_id,
            connection_id=validated_connection_id,
            message=normalized,
            observed_at=observed_at,
        )
        result.messages.append(_gmail_message_payload(source_record))
        result.counts.imported += 1
        if created:
            result.counts.source_records_created += 1
        else:
            result.counts.source_records_updated += 1

    result.counts.failed = len(result.failures)
    if result.failures:
        result.warnings.append(
            "Some Gmail message entries were skipped because they lacked a message id."
        )
    return result


def build_normalized_gmail_message(record: Mapping[str, Any]) -> dict[str, Any]:
    external_id = _safe_text(
        record.get("id")
        or record.get("message_id")
        or record.get("external_id"),
        limit=255,
    )
    if external_id is None:
        raise GmailConnectorError("gmail message id is required")

    subject = _safe_text(record.get("subject") or record.get("title"), limit=500)
    labels = _labels(record.get("labels") or record.get("labelIds"))
    source_url = _message_source_url(record)
    received_at = _parse_optional_datetime(
        record.get("received_at")
        or record.get("internal_date")
        or record.get("internalDate")
        or record.get("date")
    )
    evidence_refs = _safe_evidence_refs(
        record.get("evidence_refs"),
        message_id=external_id,
        source_url=source_url,
    )

    normalized = {
        "entity_type": "message",
        "provider": INTEGRATION_PROVIDER_GMAIL,
        "external_id": external_id,
        "message_id": external_id,
        "thread_id": _safe_text(record.get("thread_id") or record.get("threadId"), limit=255),
        "subject": subject or "(no subject)",
        # Raw email bodies are intentionally not persisted in this first local
        # connector slice; store only a bounded provider-supplied snippet.
        "snippet": _safe_text(record.get("snippet"), limit=GMAIL_SNIPPET_LIMIT),
        "from_address": _address(record.get("from") or record.get("from_address")),
        "to_addresses": _address_list(record.get("to") or record.get("to_addresses")),
        "labels": labels,
        "unread": GMAIL_UNREAD_LABEL in {label.casefold() for label in labels},
        "received_at": received_at.isoformat() if received_at else None,
        "source_url": source_url,
        "evidence_refs": evidence_refs,
        "metadata": _sanitize_payload(
            {
                "gmail_object_type": "message",
                "message_id": external_id,
                "import_source": GMAIL_IMPORT_SOURCE,
                "provider_sync_started": False,
                "external_write_performed": False,
                "llm_used": False,
            }
        ),
    }
    return _sanitize_payload(normalized)


def gmail_connector_boundary() -> dict[str, bool]:
    return {
        "provider_calls": False,
        "sync_started": False,
        "external_writes": False,
        "llm": False,
        "reads_secrets": False,
    }


async def _load_gmail_connection_id(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    connection_id: UUID,
) -> UUID:
    # Select only the non-secret id column. The service never reads or returns
    # encrypted token columns, and the import path works without a connection row.
    found_connection_id = await session.scalar(
        select(IntegrationConnection.id)
        .where(IntegrationConnection.id == connection_id)
        .where(IntegrationConnection.workspace_id == workspace_id)
        .where(IntegrationConnection.provider == INTEGRATION_PROVIDER_GMAIL)
    )
    if found_connection_id is None:
        raise GmailConnectorError("gmail connection not found")
    return found_connection_id


async def _upsert_gmail_source_record(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    connection_id: UUID | None,
    message: Mapping[str, Any],
    observed_at: datetime,
) -> tuple[SourceRecord, bool]:
    source_updated_at = _parse_optional_datetime(message.get("received_at"))
    payload = _source_record_payload(message)
    payload_hash = _stable_payload_hash(payload)
    external_id = _safe_text(message.get("external_id"), limit=255) or "unknown-gmail-message"
    mutable = {
        SourceRecord.connection_id: connection_id,
        SourceRecord.record_type: GMAIL_SOURCE_RECORD_TYPE_MESSAGE,
        SourceRecord.source_url: _safe_url(message.get("source_url")),
        SourceRecord.payload: payload,
        SourceRecord.payload_hash: payload_hash,
        SourceRecord.observed_at: observed_at,
        SourceRecord.source_updated_at: source_updated_at,
        SourceRecord.sync_job_id: None,
        SourceRecord.is_deleted: False,
        SourceRecord.tombstoned_at: None,
        SourceRecord.tombstone_observed_at: None,
        SourceRecord.tombstone_sync_job_id: None,
        SourceRecord.tombstone_reason: None,
    }
    statement: Any = (
        pg_insert(SourceRecord)
        .values(
            {
                SourceRecord.workspace_id: workspace_id,
                SourceRecord.provider: SOURCE_RECORD_PROVIDER_GMAIL,
                SourceRecord.external_id: external_id,
                **mutable,
            }
        )
        .on_conflict_do_update(
            constraint="uq_source_records_workspace_provider_external_id",
            set_=mutable,
        )
        .returning(SourceRecord.id, literal_column("(xmax = 0)"))
    )
    row = (await session.execute(statement)).one()
    source_record = await session.get(SourceRecord, row[0], populate_existing=True)
    if source_record is None:
        raise GmailConnectorError("gmail source record persistence failed")
    return source_record, bool(row[1])


def _source_record_payload(message: Mapping[str, Any]) -> dict[str, Any]:
    return _sanitize_payload(
        {
            "record_type": GMAIL_SOURCE_RECORD_TYPE_MESSAGE,
            "normalized_message": dict(message),
            "evidence_refs": message.get("evidence_refs") or [],
            "boundary": gmail_connector_boundary(),
        }
    )


def _gmail_message_payload(source_record: SourceRecord) -> dict[str, Any]:
    payload = source_record.payload if isinstance(source_record.payload, Mapping) else {}
    normalized = payload.get("normalized_message")
    message = normalized if isinstance(normalized, Mapping) else {}
    labels = _labels(message.get("labels"))
    external_id = source_record.external_id
    source_url = _safe_url(message.get("source_url")) or _safe_url(source_record.source_url)
    return {
        "source_record_id": source_record.id,
        "message_id": _safe_text(message.get("message_id"), limit=255) or external_id,
        "thread_id": _safe_text(message.get("thread_id"), limit=255),
        "subject": _safe_text(message.get("subject"), limit=500) or "(no subject)",
        "snippet": _safe_text(message.get("snippet"), limit=GMAIL_SNIPPET_LIMIT),
        "from_address": _address(message.get("from_address")),
        "to_addresses": _address_list(message.get("to_addresses")),
        "labels": labels,
        "unread": bool(message.get("unread"))
        or GMAIL_UNREAD_LABEL in {label.casefold() for label in labels},
        "received_at": source_record.source_updated_at,
        "source_url": source_url,
        "evidence_refs": _safe_evidence_refs(
            message.get("evidence_refs"),
            message_id=external_id or "gmail-message",
            source_url=source_url,
        ),
    }


def _labels(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    labels: list[str] = []
    for item in value[:40]:
        label = _safe_text(item, limit=120)
        if label and label not in labels:
            labels.append(label)
    return labels


def _address(value: Any) -> str | None:
    if isinstance(value, Mapping):
        return _safe_text(value.get("email") or value.get("address") or value.get("name"), limit=320)
    return _safe_text(value, limit=320)


def _address_list(value: Any) -> list[str]:
    if isinstance(value, str):
        candidates: list[Any] = [value]
    elif isinstance(value, list):
        candidates = value[:40]
    else:
        return []
    addresses: list[str] = []
    for item in candidates:
        address = _address(item)
        if address and address not in addresses:
            addresses.append(address)
    return addresses


def _message_source_url(record: Mapping[str, Any]) -> str | None:
    for value in (
        record.get("source_url"),
        record.get("permalink"),
        record.get("html_url"),
        record.get("web_url"),
        record.get("url"),
    ):
        if (url := _safe_url(value)) is not None:
            return url
    return None


def _safe_evidence_refs(
    value: Any,
    *,
    message_id: str,
    source_url: str | None,
) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    if isinstance(value, list):
        for item in value[:20]:
            if not isinstance(item, Mapping):
                continue
            ref = {
                "kind": _safe_text(item.get("kind"), limit=120) or "gmail_message",
                "source": _safe_text(item.get("source"), limit=40) or SOURCE_RECORD_PROVIDER_GMAIL,
                "ref": _safe_text(item.get("ref") or item.get("label"), limit=255),
                "url": _safe_url(item.get("url")) or source_url,
            }
            if ref["ref"]:
                refs.append(ref)
    if refs:
        return refs
    return [
        {
            "kind": "gmail_message",
            "source": SOURCE_RECORD_PROVIDER_GMAIL,
            "ref": message_id,
            "url": source_url,
        }
    ]


def _parse_optional_datetime(value: Any) -> datetime | None:
    text = _safe_text(value)
    if text is None:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _stable_payload_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _sanitize_payload(value: Any) -> Any:
    if isinstance(value, Mapping):
        safe: dict[str, Any] = {}
        for key, raw in value.items():
            if not isinstance(key, str) or _metadata_key_is_sensitive(key):
                continue
            safe[key] = _sanitize_payload(raw)
        return safe
    if isinstance(value, list):
        return [_sanitize_payload(item) for item in value[:100]]
    if isinstance(value, str):
        return value[:1000]
    if isinstance(value, bool | int | float) or value is None:
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)[:1000]


def _safe_text(value: Any, *, limit: int = 1000) -> str | None:
    return value.strip()[:limit] if isinstance(value, str) and value.strip() else None


def _safe_url(value: Any) -> str | None:
    text = _safe_text(value)
    if text and text.startswith(("http://", "https://")) and "@" not in text:
        return text[:1000]
    return None


def _metadata_key_is_sensitive(key: str) -> bool:
    normalized = key.casefold().replace("-", "_")
    return any(marker in normalized for marker in _SENSITIVE_KEY_MARKERS)
