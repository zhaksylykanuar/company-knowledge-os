"""Local Jira connector foundation.

This module intentionally implements only the safe MVP slice for Jira: deterministic
local issue import into canonical ``SourceRecord`` + ``Task`` rows and a read-only
list surface. It never calls Jira, never performs external writes, never invokes
an LLM, and never reads encrypted connection token fields.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from hashlib import sha256
from typing import Any
from uuid import UUID

from sqlalchemy import func, literal_column, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.canonical_models import (
    SOURCE_RECORD_PROVIDER_JIRA,
    TASK_PROVIDER_JIRA,
    SourceRecord,
    Task,
)
from app.db.integration_models import INTEGRATION_PROVIDER_JIRA, IntegrationConnection

JIRA_SOURCE_RECORD_TYPE_ISSUE = "issue"
JIRA_IMPORT_SOURCE = "local_json_import"
JIRA_IMPORT_BOUNDARY_NOTE = (
    "Local Jira issue import writes only founderOS canonical SourceRecord/Task rows; "
    "it starts no Jira provider call, no sync, no external write, and no LLM."
)

_JIRA_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]+-\d+$")
_DONE_STATUS_NAMES = {"closed", "done", "resolved"}
_OPEN_STATUS_NAMES = {"backlog", "new", "open", "selected for development", "to do", "todo"}
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


class JiraConnectorError(ValueError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


@dataclass(frozen=True)
class JiraImportFailure:
    index: int
    reason: str

    def as_payload(self) -> dict[str, Any]:
        return {"index": self.index, "reason": self.reason}


@dataclass
class JiraImportCounts:
    received: int = 0
    imported: int = 0
    failed: int = 0
    source_records_created: int = 0
    source_records_updated: int = 0
    tasks_created: int = 0
    tasks_updated: int = 0

    def as_payload(self) -> dict[str, int]:
        return {
            "received": self.received,
            "imported": self.imported,
            "failed": self.failed,
            "source_records_created": self.source_records_created,
            "source_records_updated": self.source_records_updated,
            "tasks_created": self.tasks_created,
            "tasks_updated": self.tasks_updated,
        }


@dataclass
class JiraIssueImportResult:
    counts: JiraImportCounts
    issues: list[dict[str, Any]] = field(default_factory=list)
    failures: list[JiraImportFailure] = field(default_factory=list)
    warnings: list[str] = field(default_factory=lambda: [JIRA_IMPORT_BOUNDARY_NOTE])

    def as_payload(self, *, workspace_id: UUID) -> dict[str, Any]:
        return {
            "workspace_id": str(workspace_id),
            "counts": self.counts.as_payload(),
            "issues": self.issues,
            "failures": [failure.as_payload() for failure in self.failures],
            "boundary": jira_connector_boundary(),
            "warnings": self.warnings,
        }


async def list_workspace_jira_issues(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    limit: int = 100,
) -> dict[str, Any]:
    """List locally imported Jira issue tasks for a workspace.

    Read-only: no provider calls, no sync, no external writes, no secret reads.
    """

    bounded_limit = max(1, min(limit, 200))
    tasks = list(
        (
            await session.execute(
                select(Task)
                .outerjoin(SourceRecord, SourceRecord.id == Task.source_record_id)
                .where(Task.workspace_id == workspace_id)
                .where(Task.source_provider == TASK_PROVIDER_JIRA)
                .where(
                    or_(
                        Task.source_record_id.is_(None),
                        SourceRecord.is_deleted.is_(False),
                    )
                )
                .order_by(Task.source_updated_at.desc().nullslast(), Task.updated_at.desc())
                .limit(bounded_limit)
            )
        ).scalars()
    )
    issues = [_jira_issue_payload(task) for task in tasks]
    done_count = sum(1 for issue in issues if issue.get("status_category") == "done")
    return {
        "workspace_id": str(workspace_id),
        "issues": issues,
        "counts": {
            "total": len(issues),
            "not_done": len(issues) - done_count,
            "done": done_count,
        },
        "boundary": jira_connector_boundary(),
        "warnings": [] if issues else ["No local Jira issue records have been imported yet."],
    }


async def import_jira_issues_local(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    raw_issues: list[Mapping[str, Any]],
    connection_id: UUID | None = None,
) -> JiraIssueImportResult:
    """Import user-supplied Jira issue snapshots into canonical local rows.

    The input is treated as untrusted provider data. Only a narrow normalized
    projection is persisted. Sensitive-looking keys are dropped, and no provider
    calls/writes/LLM calls are performed.
    """

    validated_connection_id = None
    if connection_id is not None:
        validated_connection_id = await _load_jira_connection_id(
            session,
            workspace_id=workspace_id,
            connection_id=connection_id,
        )

    observed_at = datetime.now(timezone.utc)
    result = JiraIssueImportResult(counts=JiraImportCounts(received=len(raw_issues)))

    for index, raw_issue in enumerate(raw_issues):
        try:
            normalized = build_normalized_jira_issue(raw_issue)
        except JiraConnectorError as exc:
            result.failures.append(JiraImportFailure(index=index, reason=exc.detail))
            continue

        source_record, source_record_created = await _upsert_jira_source_record(
            session,
            workspace_id=workspace_id,
            connection_id=validated_connection_id,
            issue=normalized,
            observed_at=observed_at,
        )
        task, task_created = await _upsert_jira_task(
            session,
            workspace_id=workspace_id,
            source_record=source_record,
            issue=normalized,
        )
        result.issues.append(_jira_issue_payload(task))
        result.counts.imported += 1
        if source_record_created:
            result.counts.source_records_created += 1
        else:
            result.counts.source_records_updated += 1
        if task_created:
            result.counts.tasks_created += 1
        else:
            result.counts.tasks_updated += 1

    result.counts.failed = len(result.failures)
    if result.failures:
        result.warnings.append(
            "Some Jira issue entries were skipped because they lacked a valid Jira key."
        )
    return result


def build_normalized_jira_issue(record: Mapping[str, Any]) -> dict[str, Any]:
    fields = record.get("fields") if isinstance(record.get("fields"), Mapping) else {}
    key = _jira_key(
        record.get("key")
        or record.get("issue_key")
        or record.get("external_id")
        or fields.get("key")
    )
    if key is None:
        raise JiraConnectorError("jira issue key is required, e.g. FOS-123")

    summary = _safe_text(
        record.get("summary") or record.get("title") or fields.get("summary"),
        limit=500,
    )
    status = _status_name(record.get("status") or fields.get("status"))
    priority = _priority_name(record.get("priority") or fields.get("priority"))
    source_url = _source_url(record, fields)
    source_updated_at = _parse_optional_datetime(
        record.get("updated_at")
        or record.get("updated")
        or record.get("updatedAt")
        or fields.get("updated")
    )
    due_date = _parse_optional_date(
        record.get("due_date")
        or record.get("dueDate")
        or record.get("duedate")
        or fields.get("duedate")
    )
    project_key = key.split("-", 1)[0]
    status_category = _status_category(record.get("status") or fields.get("status"), status)
    issue_type = _issue_type_name(record.get("issue_type") or fields.get("issuetype"))
    evidence_refs = _safe_evidence_refs(record.get("evidence_refs"), key=key, source_url=source_url)

    normalized = {
        "entity_type": "task",
        "provider": INTEGRATION_PROVIDER_JIRA,
        "external_id": key,
        "key": key,
        "title": summary or f"Jira issue {key}",
        # Do not persist raw Jira descriptions/body content in this first local
        # connector slice; store only a narrow evidence-backed issue projection.
        "status": status,
        "status_category": status_category,
        "priority": priority,
        "due_date": due_date.isoformat() if due_date is not None else None,
        "source_url": source_url,
        "source_updated_at": source_updated_at.isoformat() if source_updated_at else None,
        "project_key": project_key,
        "issue_type": issue_type,
        "evidence_refs": evidence_refs,
        "metadata": _sanitize_payload(
            {
                "jira_object_type": "issue",
                "key": key,
                "project_key": project_key,
                "issue_type": issue_type,
                "status_category": status_category,
                "import_source": JIRA_IMPORT_SOURCE,
                "provider_sync_started": False,
                "external_write_performed": False,
                "llm_used": False,
                "evidence_refs": evidence_refs,
            }
        ),
    }
    return _sanitize_payload(normalized)


def jira_connector_boundary() -> dict[str, bool]:
    return {
        "provider_calls": False,
        "sync_started": False,
        "external_writes": False,
        "llm": False,
        "reads_secrets": False,
    }


async def _load_jira_connection_id(
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
        .where(IntegrationConnection.provider == INTEGRATION_PROVIDER_JIRA)
    )
    if found_connection_id is None:
        raise JiraConnectorError("jira connection not found")
    return found_connection_id


async def _upsert_jira_source_record(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    connection_id: UUID | None,
    issue: Mapping[str, Any],
    observed_at: datetime,
) -> tuple[SourceRecord, bool]:
    source_updated_at = _parse_optional_datetime(issue.get("source_updated_at"))
    payload = _source_record_payload(issue)
    payload_hash = _stable_payload_hash(payload)
    mutable = {
        SourceRecord.connection_id: connection_id,
        SourceRecord.record_type: JIRA_SOURCE_RECORD_TYPE_ISSUE,
        SourceRecord.source_url: _safe_url(issue.get("source_url")),
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
    statement = (
        pg_insert(SourceRecord)
        .values(
            {
                SourceRecord.workspace_id: workspace_id,
                SourceRecord.provider: SOURCE_RECORD_PROVIDER_JIRA,
                SourceRecord.external_id: _safe_text(issue.get("external_id"), limit=255)
                or _safe_text(issue.get("key"), limit=255)
                or "unknown-jira-issue",
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


async def _upsert_jira_task(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    source_record: SourceRecord,
    issue: Mapping[str, Any],
) -> tuple[Task, bool]:
    due_date = _parse_optional_date(issue.get("due_date"))
    source_updated_at = _parse_optional_datetime(issue.get("source_updated_at"))
    external_id = _safe_text(issue.get("external_id"), limit=255) or "unknown-jira-issue"
    mutable = {
        Task.source_record_id: source_record.id,
        Task.title: _safe_text(issue.get("title"), limit=500) or f"Jira issue {external_id}",
        Task.description: None,
        Task.status: _safe_text(issue.get("status"), limit=120),
        Task.priority: _safe_text(issue.get("priority"), limit=40),
        Task.due_date: due_date,
        Task.source_url: _safe_url(issue.get("source_url")),
        Task.task_metadata: _task_metadata(issue),
        Task.source_updated_at: source_updated_at,
    }
    statement = (
        pg_insert(Task)
        .values(
            {
                Task.workspace_id: workspace_id,
                Task.source_provider: TASK_PROVIDER_JIRA,
                Task.external_id: external_id,
                **mutable,
            }
        )
        .on_conflict_do_update(
            index_elements=["workspace_id", "source_provider", "external_id"],
            index_where=Task.external_id.isnot(None),
            set_={**mutable, Task.updated_at: func.now()},
        )
        .returning(Task.id, literal_column("(xmax = 0)"))
    )
    row = (await session.execute(statement)).one()
    task = await session.get(Task, row[0], populate_existing=True)
    return task, bool(row[1])


def _source_record_payload(issue: Mapping[str, Any]) -> dict[str, Any]:
    return _sanitize_payload(
        {
            "record_type": JIRA_SOURCE_RECORD_TYPE_ISSUE,
            "normalized_issue": dict(issue),
            "evidence_refs": issue.get("evidence_refs") or [],
            "boundary": jira_connector_boundary(),
        }
    )


def _task_metadata(issue: Mapping[str, Any]) -> dict[str, Any]:
    metadata = issue.get("metadata") if isinstance(issue.get("metadata"), Mapping) else {}
    merged = {
        **dict(metadata),
        "jira_object_type": "issue",
        "key": _safe_text(issue.get("key"), limit=255),
        "project_key": _safe_text(issue.get("project_key"), limit=80),
        "issue_type": _safe_text(issue.get("issue_type"), limit=120),
        "status_category": _safe_text(issue.get("status_category"), limit=40),
        "evidence_refs": issue.get("evidence_refs") or [],
    }
    return _sanitize_payload(merged)


def _jira_issue_payload(task: Task) -> dict[str, Any]:
    metadata = task.task_metadata if isinstance(task.task_metadata, Mapping) else {}
    return {
        "task_id": task.id,
        "source_record_id": task.source_record_id,
        "key": _safe_text(metadata.get("key"), limit=255) or task.external_id,
        "title": task.title,
        "status": task.status,
        "status_category": _safe_text(metadata.get("status_category"), limit=40),
        "priority": task.priority,
        "due_date": task.due_date,
        "source_url": _safe_url(task.source_url),
        "updated_at": task.source_updated_at or task.updated_at,
        "project_key": _safe_text(metadata.get("project_key"), limit=80),
        "issue_type": _safe_text(metadata.get("issue_type"), limit=120),
        "evidence_refs": _safe_evidence_refs(
            metadata.get("evidence_refs"),
            key=_safe_text(metadata.get("key"), limit=255) or task.external_id or "jira-issue",
            source_url=_safe_url(task.source_url),
        ),
    }


def _jira_key(value: Any) -> str | None:
    text = _safe_text(value, limit=80)
    if not text:
        return None
    normalized = text.upper()
    return normalized if _JIRA_KEY_RE.fullmatch(normalized) else None


def _status_name(value: Any) -> str | None:
    if isinstance(value, Mapping):
        return _safe_text(value.get("name") or value.get("status"), limit=120)
    return _safe_text(value, limit=120)


def _priority_name(value: Any) -> str | None:
    if isinstance(value, Mapping):
        return _safe_text(value.get("name") or value.get("priority"), limit=40)
    return _safe_text(value, limit=40)


def _issue_type_name(value: Any) -> str | None:
    if isinstance(value, Mapping):
        return _safe_text(value.get("name") or value.get("type"), limit=120)
    return _safe_text(value, limit=120)


def _status_category(value: Any, status: str | None) -> str:
    if isinstance(value, Mapping):
        raw_category = value.get("statusCategory") or value.get("category")
        if isinstance(raw_category, Mapping):
            category = _safe_text(raw_category.get("key") or raw_category.get("name"))
            if category:
                return _normalize_status_category(category)
    if status:
        return _normalize_status_category(status)
    return "unknown"


def _normalize_status_category(value: str) -> str:
    normalized = value.strip().casefold().replace("_", " ")
    if normalized in _DONE_STATUS_NAMES:
        return "done"
    if normalized in _OPEN_STATUS_NAMES:
        return "not_done"
    if normalized in {"in progress", "indeterminate"}:
        return "not_done"
    return "unknown"


def _source_url(record: Mapping[str, Any], fields: Mapping[str, Any]) -> str | None:
    for value in (
        record.get("source_url"),
        record.get("browse_url"),
        record.get("html_url"),
        record.get("web_url"),
        record.get("url"),
        record.get("self"),
        fields.get("source_url"),
    ):
        if (url := _safe_url(value)) is not None:
            return url
    return None


def _safe_evidence_refs(value: Any, *, key: str, source_url: str | None) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    if isinstance(value, list):
        for item in value[:20]:
            if not isinstance(item, Mapping):
                continue
            ref = {
                "kind": _safe_text(item.get("kind"), limit=120) or "jira_issue",
                "source": _safe_text(item.get("source"), limit=40) or SOURCE_RECORD_PROVIDER_JIRA,
                "ref": _safe_text(item.get("ref") or item.get("label"), limit=255),
                "url": _safe_url(item.get("url")) or source_url,
            }
            if ref["ref"]:
                refs.append(ref)
    if refs:
        return refs
    return [
        {
            "kind": "jira_issue",
            "source": SOURCE_RECORD_PROVIDER_JIRA,
            "ref": key,
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


def _parse_optional_date(value: Any) -> date | None:
    text = _safe_text(value, limit=20)
    if text is None:
        return None
    try:
        return date.fromisoformat(text[:10])
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
    if isinstance(value, date | datetime):
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
