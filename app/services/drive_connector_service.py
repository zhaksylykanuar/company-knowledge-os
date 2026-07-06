"""Local Google Drive connector foundation.

This module implements only the safe MVP slice for Drive: deterministic local
file metadata import into canonical ``SourceRecord`` rows and a read-only list
surface. It never calls Google Drive, never performs external writes, never
invokes an LLM, and never reads encrypted connection token fields.

Drive files are not tasks, so they are persisted to ``SourceRecord`` only. Raw
document contents are intentionally not persisted; only a narrow evidence-backed
metadata projection is stored.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any
from uuid import UUID

from sqlalchemy import literal_column, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.canonical_models import SOURCE_RECORD_PROVIDER_DRIVE, SourceRecord
from app.db.integration_models import INTEGRATION_PROVIDER_DRIVE, IntegrationConnection

DRIVE_SOURCE_RECORD_TYPE_FILE = "file"
DRIVE_IMPORT_SOURCE = "local_json_import"
DRIVE_IMPORT_BOUNDARY_NOTE = (
    "Local Google Drive file import writes only founderOS canonical SourceRecord "
    "rows with a narrow metadata projection (no raw document body); it starts no "
    "Drive provider call, no sync, no external write, and no LLM."
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


class DriveConnectorError(ValueError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


@dataclass(frozen=True)
class DriveImportFailure:
    index: int
    reason: str

    def as_payload(self) -> dict[str, Any]:
        return {"index": self.index, "reason": self.reason}


@dataclass
class DriveImportCounts:
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
class DriveFileImportResult:
    counts: DriveImportCounts
    files: list[dict[str, Any]] = field(default_factory=list)
    failures: list[DriveImportFailure] = field(default_factory=list)
    warnings: list[str] = field(default_factory=lambda: [DRIVE_IMPORT_BOUNDARY_NOTE])

    def as_payload(self, *, workspace_id: UUID) -> dict[str, Any]:
        return {
            "workspace_id": str(workspace_id),
            "counts": self.counts.as_payload(),
            "files": self.files,
            "failures": [failure.as_payload() for failure in self.failures],
            "boundary": drive_connector_boundary(),
            "warnings": self.warnings,
        }


async def list_workspace_drive_files(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    limit: int = 100,
) -> dict[str, Any]:
    """List locally imported Google Drive file source records for a workspace.

    Read-only: no provider calls, no sync, no external writes, no secret reads.
    """

    bounded_limit = max(1, min(limit, 200))
    records = list(
        (
            await session.execute(
                select(SourceRecord)
                .where(SourceRecord.workspace_id == workspace_id)
                .where(SourceRecord.provider == SOURCE_RECORD_PROVIDER_DRIVE)
                .where(SourceRecord.record_type == DRIVE_SOURCE_RECORD_TYPE_FILE)
                .where(SourceRecord.is_deleted.is_(False))
                .order_by(
                    SourceRecord.source_updated_at.desc().nullslast(),
                    SourceRecord.created_at.desc(),
                )
                .limit(bounded_limit)
            )
        ).scalars()
    )
    files = [_drive_file_payload(record) for record in records]
    shared_count = sum(1 for file in files if file.get("shared"))
    return {
        "workspace_id": str(workspace_id),
        "files": files,
        "counts": {
            "total": len(files),
            "shared": shared_count,
            "not_shared": len(files) - shared_count,
        },
        "boundary": drive_connector_boundary(),
        "warnings": [] if files else ["No local Google Drive file records have been imported yet."],
    }


async def import_drive_files_local(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    raw_files: list[Mapping[str, Any]],
    connection_id: UUID | None = None,
) -> DriveFileImportResult:
    """Import user-supplied Drive file snapshots into canonical local rows.

    The input is treated as untrusted provider data. Only a narrow metadata
    projection is persisted (no raw body/content). Sensitive-looking keys are
    dropped, and no provider calls/writes/LLM calls are performed.
    """

    validated_connection_id = None
    if connection_id is not None:
        validated_connection_id = await _load_drive_connection_id(
            session,
            workspace_id=workspace_id,
            connection_id=connection_id,
        )

    observed_at = datetime.now(timezone.utc)
    result = DriveFileImportResult(counts=DriveImportCounts(received=len(raw_files)))

    for index, raw_file in enumerate(raw_files):
        try:
            normalized = build_normalized_drive_file(raw_file)
        except DriveConnectorError as exc:
            result.failures.append(DriveImportFailure(index=index, reason=exc.detail))
            continue

        source_record, created = await _upsert_drive_source_record(
            session,
            workspace_id=workspace_id,
            connection_id=validated_connection_id,
            file=normalized,
            observed_at=observed_at,
        )
        result.files.append(_drive_file_payload(source_record))
        result.counts.imported += 1
        if created:
            result.counts.source_records_created += 1
        else:
            result.counts.source_records_updated += 1

    result.counts.failed = len(result.failures)
    if result.failures:
        result.warnings.append(
            "Some Google Drive file entries were skipped because they lacked a file id."
        )
    return result


def build_normalized_drive_file(record: Mapping[str, Any]) -> dict[str, Any]:
    external_id = _safe_text(
        record.get("id")
        or record.get("file_id")
        or record.get("external_id"),
        limit=255,
    )
    if external_id is None:
        raise DriveConnectorError("google drive file id is required")

    source_url = _file_source_url(record)
    modified_at = _parse_optional_datetime(
        record.get("modified_at")
        or record.get("modifiedTime")
        or record.get("updated_at")
        or record.get("updated")
    )
    evidence_refs = _safe_evidence_refs(
        record.get("evidence_refs"),
        file_id=external_id,
        source_url=source_url,
    )

    normalized = {
        "entity_type": "drive_file",
        "provider": INTEGRATION_PROVIDER_DRIVE,
        "external_id": external_id,
        "file_id": external_id,
        "name": _safe_text(record.get("name") or record.get("title"), limit=500)
        or f"Drive file {external_id}",
        "mime_type": _safe_text(record.get("mime_type") or record.get("mimeType"), limit=255),
        # Raw Drive document body/content is intentionally not persisted in this
        # first local connector slice; store only metadata and evidence refs.
        "owners": _string_list(record.get("owners") or record.get("owner_emails"), limit=40),
        "drive_id": _safe_text(record.get("drive_id") or record.get("driveId"), limit=255),
        "folder_path": _safe_text(
            record.get("folder_path") or record.get("path"),
            limit=500,
        ),
        "shared": _shared(record),
        "size_bytes": _safe_int(record.get("size_bytes") or record.get("size")),
        "modified_at": modified_at.isoformat() if modified_at else None,
        "source_url": source_url,
        "evidence_refs": evidence_refs,
        "metadata": _sanitize_payload(
            {
                "drive_object_type": "file",
                "file_id": external_id,
                "import_source": DRIVE_IMPORT_SOURCE,
                "provider_sync_started": False,
                "external_write_performed": False,
                "llm_used": False,
            }
        ),
    }
    return _sanitize_payload(normalized)


def drive_connector_boundary() -> dict[str, bool]:
    return {
        "provider_calls": False,
        "sync_started": False,
        "external_writes": False,
        "llm": False,
        "reads_secrets": False,
    }


async def _load_drive_connection_id(
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
        .where(IntegrationConnection.provider == INTEGRATION_PROVIDER_DRIVE)
    )
    if found_connection_id is None:
        raise DriveConnectorError("google drive connection not found")
    return found_connection_id


async def _upsert_drive_source_record(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    connection_id: UUID | None,
    file: Mapping[str, Any],
    observed_at: datetime,
) -> tuple[SourceRecord, bool]:
    source_updated_at = _parse_optional_datetime(file.get("modified_at"))
    payload = _source_record_payload(file)
    payload_hash = _stable_payload_hash(payload)
    external_id = _safe_text(file.get("external_id"), limit=255) or "unknown-drive-file"
    mutable = {
        SourceRecord.connection_id: connection_id,
        SourceRecord.record_type: DRIVE_SOURCE_RECORD_TYPE_FILE,
        SourceRecord.source_url: _safe_url(file.get("source_url")),
        SourceRecord.payload: payload,
        SourceRecord.payload_hash: payload_hash,
        SourceRecord.observed_at: observed_at,
        SourceRecord.source_updated_at: source_updated_at,
        SourceRecord.sync_job_id: None,
        SourceRecord.is_deleted: False,
    }
    statement = (
        pg_insert(SourceRecord)
        .values(
            {
                SourceRecord.workspace_id: workspace_id,
                SourceRecord.provider: SOURCE_RECORD_PROVIDER_DRIVE,
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
    return source_record, bool(row[1])


def _source_record_payload(file: Mapping[str, Any]) -> dict[str, Any]:
    return _sanitize_payload(
        {
            "record_type": DRIVE_SOURCE_RECORD_TYPE_FILE,
            "normalized_file": dict(file),
            "evidence_refs": file.get("evidence_refs") or [],
            "boundary": drive_connector_boundary(),
        }
    )


def _drive_file_payload(source_record: SourceRecord) -> dict[str, Any]:
    payload = source_record.payload if isinstance(source_record.payload, Mapping) else {}
    normalized = payload.get("normalized_file")
    file = normalized if isinstance(normalized, Mapping) else {}
    external_id = source_record.external_id
    source_url = _safe_url(file.get("source_url")) or _safe_url(source_record.source_url)
    return {
        "source_record_id": source_record.id,
        "file_id": _safe_text(file.get("file_id"), limit=255) or external_id,
        "name": _safe_text(file.get("name"), limit=500) or f"Drive file {external_id}",
        "mime_type": _safe_text(file.get("mime_type"), limit=255),
        "owners": _string_list(file.get("owners"), limit=40),
        "drive_id": _safe_text(file.get("drive_id"), limit=255),
        "folder_path": _safe_text(file.get("folder_path"), limit=500),
        "shared": bool(file.get("shared")),
        "size_bytes": _safe_int(file.get("size_bytes")),
        "modified_at": source_record.source_updated_at,
        "source_url": source_url,
        "evidence_refs": _safe_evidence_refs(
            file.get("evidence_refs"),
            file_id=external_id or "drive-file",
            source_url=source_url,
        ),
    }


def _shared(record: Mapping[str, Any]) -> bool:
    if isinstance(record.get("shared"), bool):
        return bool(record.get("shared"))
    visibility = _safe_text(record.get("visibility") or record.get("sharing"))
    return visibility.casefold() in {"anyone", "public", "shared"} if visibility else False


def _file_source_url(record: Mapping[str, Any]) -> str | None:
    for value in (
        record.get("source_url"),
        record.get("webViewLink"),
        record.get("web_view_link"),
        record.get("alternateLink"),
        record.get("url"),
    ):
        if (url := _safe_url(value)) is not None:
            return url
    return None


def _safe_evidence_refs(
    value: Any,
    *,
    file_id: str,
    source_url: str | None,
) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    if isinstance(value, list):
        for item in value[:20]:
            if not isinstance(item, Mapping):
                continue
            ref = {
                "kind": _safe_text(item.get("kind"), limit=120) or "drive_file",
                "source": _safe_text(item.get("source"), limit=40) or SOURCE_RECORD_PROVIDER_DRIVE,
                "ref": _safe_text(item.get("ref") or item.get("label"), limit=255),
                "url": _safe_url(item.get("url")) or source_url,
            }
            if ref["ref"]:
                refs.append(ref)
    if refs:
        return refs
    return [
        {
            "kind": "drive_file",
            "source": SOURCE_RECORD_PROVIDER_DRIVE,
            "ref": file_id,
            "url": source_url,
        }
    ]


def _string_list(value: Any, *, limit: int) -> list[str]:
    if isinstance(value, str):
        candidates: list[Any] = [value]
    elif isinstance(value, list):
        candidates = value[:limit]
    else:
        return []
    values: list[str] = []
    for item in candidates:
        if isinstance(item, Mapping):
            text = _safe_text(item.get("emailAddress") or item.get("email") or item.get("name"))
        else:
            text = _safe_text(item)
        if text and text not in values:
            values.append(text)
    return values


def _parse_optional_datetime(value: Any) -> datetime | None:
    text = _safe_text(value)
    if text is None:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _safe_int(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
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
