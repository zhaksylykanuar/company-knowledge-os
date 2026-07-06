from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.canonical_models import (
    PULL_REQUEST_STATE_MERGED,
    PULL_REQUEST_STATE_OPEN,
    SOURCE_RECORD_PROVIDER_DRIVE,
    SOURCE_RECORD_PROVIDER_GITHUB,
    SOURCE_RECORD_PROVIDER_GMAIL,
    TASK_PROVIDER_GITHUB,
    TASK_PROVIDER_JIRA,
    PullRequest,
    Repository,
    SourceRecord,
    Task,
)
from app.db.document_models import DOCUMENT_STATUS_ARCHIVED, Document

COMPANY_BRAIN_GITHUB_MODE = "github_first_canonical"
COMPANY_BRAIN_GITHUB_SOURCE = "canonical_github_company_brain"


async def build_workspace_company_brain(
    *,
    session: AsyncSession,
    workspace_id: UUID,
    limit: int = 10,
) -> dict[str, Any]:
    repositories = await _repositories(session=session, workspace_id=workspace_id)
    github_tasks = await _github_issue_tasks(session=session, workspace_id=workspace_id)
    jira_tasks = await _jira_issue_tasks(session=session, workspace_id=workspace_id)
    tasks = [*github_tasks, *jira_tasks]
    pull_requests = await _pull_requests(session=session, workspace_id=workspace_id)
    gmail_message_records = await _source_records_by_provider_record_type(
        session=session,
        workspace_id=workspace_id,
        provider=SOURCE_RECORD_PROVIDER_GMAIL,
        record_type="message",
        limit=limit,
    )
    drive_file_records = await _source_records_by_provider_record_type(
        session=session,
        workspace_id=workspace_id,
        provider=SOURCE_RECORD_PROVIDER_DRIVE,
        record_type="file",
        limit=limit,
    )
    internal_documents = await _internal_documents(
        session=session,
        workspace_id=workspace_id,
        limit=limit,
    )
    source_record_coverage = await _source_record_coverage(
        session=session,
        workspace_id=workspace_id,
    )

    repository_source_records = await _source_records_by_external_id(
        session=session,
        workspace_id=workspace_id,
        record_type="repository",
        external_ids=[repository.external_id for repository in repositories],
    )
    issue_source_records = await _source_records_for_tasks(
        session=session,
        workspace_id=workspace_id,
        tasks=tasks,
    )
    pull_request_source_records = await _source_records_by_external_id(
        session=session,
        workspace_id=workspace_id,
        record_type="pull_request",
        external_ids=[pull_request.external_id for pull_request in pull_requests],
    )

    repository_by_id = {repository.id: repository for repository in repositories}
    repository_rows = [
        _repository_payload(
            repository,
            repository_source_records.get(repository.external_id),
        )
        for repository in repositories[:limit]
    ]
    issue_rows = [
        _issue_payload(task, issue_source_records.get(task.id))
        for task in _open_issues(tasks)[:limit]
    ]
    pull_request_rows = [
        _pull_request_payload(
            pull_request,
            repository_by_id.get(pull_request.repository_id),
            pull_request_source_records.get(pull_request.external_id),
        )
        for pull_request in _open_pull_requests(pull_requests)[:limit]
    ]
    recent_rows = _recent_work(
        tasks=tasks,
        pull_requests=pull_requests,
        repositories=repository_by_id,
        task_source_records=issue_source_records,
        pull_request_source_records=pull_request_source_records,
        limit=limit,
    )
    gmail_message_rows = [
        _gmail_message_payload(source_record)
        for source_record in gmail_message_records[:limit]
    ]
    drive_file_rows = [
        _drive_file_payload(source_record)
        for source_record in drive_file_records[:limit]
    ]
    document_rows = [_internal_document_payload(document) for document in internal_documents]
    evidence = _unique_source_refs(
        [
            *[row["source_refs"] for row in repository_rows],
            *[row["source_refs"] for row in issue_rows],
            *[row["source_refs"] for row in pull_request_rows],
            *[row["source_refs"] for row in recent_rows],
            *[row["source_refs"] for row in gmail_message_rows],
            *[row["source_refs"] for row in drive_file_rows],
            *[row["source_refs"] for row in document_rows],
        ]
    )
    summary = {
        "repositories": len(repositories),
        "open_issues": len(_open_issues(tasks)),
        "open_pull_requests": len(_open_pull_requests(pull_requests)),
        "closed_issues": len(_closed_issues(tasks)),
        "merged_pull_requests": len(_merged_pull_requests(pull_requests)),
    }
    warnings: list[str] = []
    if not any(summary.values()):
        warnings.append("No canonical GitHub records have been synced for this workspace yet.")
    if repositories and not any(row["source_refs"] for row in repository_rows):
        warnings.append("Some canonical repository records do not have source refs yet.")

    return {
        "workspace_id": workspace_id,
        "mode": COMPANY_BRAIN_GITHUB_MODE,
        "source": COMPANY_BRAIN_GITHUB_SOURCE,
        "summary": summary,
        "source_records": source_record_coverage,
        "repositories": repository_rows,
        "work": {
            "issues": issue_rows,
            "pull_requests": pull_request_rows,
            "recent": recent_rows,
        },
        "communications": {
            "messages": gmail_message_rows,
        },
        "documents": {
            "files": drive_file_rows,
            "notes": document_rows,
        },
        "evidence": evidence,
        "capabilities": {
            "live_github_oauth": False,
            "live_provider_sync": False,
            "local_sync": True,
            "llm_briefing": False,
        },
        "is_live": False,
        "llm_used": False,
        "warnings": warnings,
    }


async def _repositories(
    *,
    session: AsyncSession,
    workspace_id: UUID,
) -> list[Repository]:
    return list(
        (
            await session.execute(
                select(Repository)
                .where(Repository.workspace_id == workspace_id)
                .where(Repository.provider == SOURCE_RECORD_PROVIDER_GITHUB)
                .order_by(
                    Repository.last_activity_at.desc().nullslast(),
                    Repository.updated_at.desc(),
                )
            )
        ).scalars()
    )


async def _source_record_coverage(
    *,
    session: AsyncSession,
    workspace_id: UUID,
) -> dict[str, Any]:
    rows = (
        await session.execute(
            select(
                SourceRecord.provider,
                SourceRecord.record_type,
                func.count(SourceRecord.id),
            )
            .where(SourceRecord.workspace_id == workspace_id)
            .where(SourceRecord.is_deleted.is_(False))
            .group_by(SourceRecord.provider, SourceRecord.record_type)
            .order_by(SourceRecord.provider.asc(), SourceRecord.record_type.asc())
        )
    ).all()

    by_provider: dict[str, int] = {}
    by_record_type: dict[str, int] = {}
    total = 0
    for provider, record_type, count in rows:
        safe_provider = _safe_text(provider) or "unknown"
        safe_record_type = _safe_text(record_type) or "unknown"
        row_count = int(count or 0)
        total += row_count
        by_provider[safe_provider] = by_provider.get(safe_provider, 0) + row_count
        by_record_type[safe_record_type] = (
            by_record_type.get(safe_record_type, 0) + row_count
        )

    return {
        "total": total,
        "by_provider": [
            {"provider": provider, "count": count}
            for provider, count in sorted(by_provider.items())
        ],
        "by_record_type": [
            {"record_type": record_type, "count": count}
            for record_type, count in sorted(by_record_type.items())
        ],
    }


async def _github_issue_tasks(
    *,
    session: AsyncSession,
    workspace_id: UUID,
) -> list[Task]:
    rows = (
        await session.execute(
            select(Task)
            .where(Task.workspace_id == workspace_id)
            .where(Task.source_provider == TASK_PROVIDER_GITHUB)
            .order_by(Task.source_updated_at.desc().nullslast(), Task.updated_at.desc())
        )
    ).scalars()
    tasks: list[Task] = []
    seen_issue_keys: set[str] = set()
    for task in rows:
        if not _is_github_issue(task):
            continue
        issue_key = _issue_identity_key(task)
        if issue_key in seen_issue_keys:
            continue
        seen_issue_keys.add(issue_key)
        tasks.append(task)
    return tasks


async def _jira_issue_tasks(
    *,
    session: AsyncSession,
    workspace_id: UUID,
) -> list[Task]:
    rows = (
        await session.execute(
            select(Task)
            .where(Task.workspace_id == workspace_id)
            .where(Task.source_provider == TASK_PROVIDER_JIRA)
            .order_by(Task.source_updated_at.desc().nullslast(), Task.updated_at.desc())
        )
    ).scalars()
    tasks: list[Task] = []
    seen_issue_keys: set[str] = set()
    for task in rows:
        if not _is_jira_issue(task):
            continue
        issue_key = _issue_identity_key(task)
        if issue_key in seen_issue_keys:
            continue
        seen_issue_keys.add(issue_key)
        tasks.append(task)
    return tasks


async def _pull_requests(
    *,
    session: AsyncSession,
    workspace_id: UUID,
) -> list[PullRequest]:
    rows = list(
        (
            await session.execute(
                select(PullRequest)
                .where(PullRequest.workspace_id == workspace_id)
                .order_by(
                    PullRequest.updated_at_source.desc().nullslast(),
                    PullRequest.created_at.desc(),
                )
            )
        ).scalars()
    )
    pull_requests: list[PullRequest] = []
    seen_pull_request_keys: set[str] = set()
    for pull_request in rows:
        pull_request_key = _pull_request_identity_key(pull_request)
        if pull_request_key in seen_pull_request_keys:
            continue
        seen_pull_request_keys.add(pull_request_key)
        pull_requests.append(pull_request)
    return pull_requests


async def _source_records_by_external_id(
    *,
    session: AsyncSession,
    workspace_id: UUID,
    provider: str = SOURCE_RECORD_PROVIDER_GITHUB,
    record_type: str,
    external_ids: list[str | None],
) -> dict[str, SourceRecord]:
    selected_ids = sorted({external_id for external_id in external_ids if external_id})
    if not selected_ids:
        return {}
    rows = (
        await session.execute(
                select(SourceRecord)
                .where(SourceRecord.workspace_id == workspace_id)
                .where(SourceRecord.provider == provider)
                .where(SourceRecord.record_type == record_type)
                .where(SourceRecord.external_id.in_(selected_ids))
        )
    ).scalars()
    return {row.external_id: row for row in rows}


async def _source_records_by_provider_record_type(
    *,
    session: AsyncSession,
    workspace_id: UUID,
    provider: str,
    record_type: str,
    limit: int,
) -> list[SourceRecord]:
    return list(
        (
            await session.execute(
                select(SourceRecord)
                .where(SourceRecord.workspace_id == workspace_id)
                .where(SourceRecord.provider == provider)
                .where(SourceRecord.record_type == record_type)
                .where(SourceRecord.is_deleted.is_(False))
                .order_by(
                    SourceRecord.source_updated_at.desc().nullslast(),
                    SourceRecord.created_at.desc(),
                )
                .limit(limit)
            )
        ).scalars()
    )


async def _internal_documents(
    *,
    session: AsyncSession,
    workspace_id: UUID,
    limit: int,
) -> list[Document]:
    # Company Brain surfaces authored internal documents that are not archived
    # (draft/published), newest-updated first (§4.7: a saved document appears in
    # Brain). Archived documents are intentionally excluded from the brain view.
    return list(
        (
            await session.execute(
                select(Document)
                .where(Document.workspace_id == workspace_id)
                .where(Document.status != DOCUMENT_STATUS_ARCHIVED)
                .order_by(Document.updated_at.desc(), Document.id.desc())
                .limit(limit)
            )
        ).scalars()
    )


async def _source_records_for_tasks(
    *,
    session: AsyncSession,
    workspace_id: UUID,
    tasks: list[Task],
) -> dict[UUID, SourceRecord]:
    source_record_ids = sorted(
        {task.source_record_id for task in tasks if task.source_record_id},
        key=str,
    )
    by_id: dict[UUID, SourceRecord] = {}
    if source_record_ids:
        rows = (
            await session.execute(
                select(SourceRecord)
                .where(SourceRecord.workspace_id == workspace_id)
                .where(SourceRecord.id.in_(source_record_ids))
            )
        ).scalars()
        by_id = {row.id: row for row in rows}

    external_ids_by_provider: dict[str, list[str | None]] = {}
    for task in tasks:
        external_ids_by_provider.setdefault(task.source_provider, []).append(task.external_id)
    by_external_id: dict[tuple[str, str | None], SourceRecord] = {}
    for provider, external_ids in external_ids_by_provider.items():
        provider_records = await _source_records_by_external_id(
            session=session,
            workspace_id=workspace_id,
            provider=provider,
            record_type="issue",
            external_ids=external_ids,
        )
        by_external_id.update(
            {(provider, external_id): record for external_id, record in provider_records.items()}
        )
    return {
        task.id: by_id.get(task.source_record_id)
        or by_external_id.get((task.source_provider, task.external_id))
        for task in tasks
        if by_id.get(task.source_record_id)
        or by_external_id.get((task.source_provider, task.external_id))
    }


def _open_issues(tasks: list[Task]) -> list[Task]:
    return [task for task in tasks if _is_open_issue_task(task)]


def _closed_issues(tasks: list[Task]) -> list[Task]:
    return [task for task in tasks if _is_done_issue_task(task)]


def _issue_identity_key(task: Task) -> str:
    metadata = task.task_metadata if isinstance(task.task_metadata, Mapping) else {}
    repository_full_name = _safe_text(metadata.get("repository_full_name"))
    number = _safe_int(metadata.get("number"))
    if repository_full_name and number is not None:
        return f"{repository_full_name}#issue/{number}"
    if task.external_id:
        return task.external_id
    return str(task.id)


def _open_pull_requests(pull_requests: list[PullRequest]) -> list[PullRequest]:
    return [
        pull_request
        for pull_request in pull_requests
        if pull_request.state == PULL_REQUEST_STATE_OPEN
    ]


def _merged_pull_requests(pull_requests: list[PullRequest]) -> list[PullRequest]:
    return [
        pull_request
        for pull_request in pull_requests
        if pull_request.state == PULL_REQUEST_STATE_MERGED
    ]


def _pull_request_identity_key(pull_request: PullRequest) -> str:
    metadata = (
        pull_request.pr_metadata if isinstance(pull_request.pr_metadata, Mapping) else {}
    )
    repository_full_name = _safe_text(metadata.get("repository_full_name"))
    if repository_full_name and pull_request.number is not None:
        return f"{repository_full_name}#pull/{pull_request.number}"
    return pull_request.external_id or str(pull_request.id)


def _repository_payload(
    repository: Repository,
    source_record: SourceRecord | None,
) -> dict[str, Any]:
    return {
        "id": repository.id,
        "provider": repository.provider,
        "external_id": repository.external_id,
        "name": repository.name,
        "full_name": repository.full_name,
        "visibility": repository.visibility,
        "archived": repository.archived,
        "source_url": _safe_url(repository.source_url),
        "last_activity_at": repository.last_activity_at,
        "source_refs": _source_refs(source_record),
    }


def _issue_payload(
    task: Task,
    source_record: SourceRecord | None,
) -> dict[str, Any]:
    metadata = task.task_metadata if isinstance(task.task_metadata, Mapping) else {}
    return {
        "id": task.id,
        "type": "issue",
        "source_provider": task.source_provider,
        "external_id": task.external_id,
        "number": _safe_int(metadata.get("number")),
        "title": task.title,
        "state": task.status,
        "repository_full_name": _safe_text(metadata.get("repository_full_name")),
        "repository_external_id": _safe_text(metadata.get("repository_external_id")),
        "project_key": _safe_text(metadata.get("project_key")),
        "source_url": _safe_url(task.source_url),
        "updated_at": task.source_updated_at or task.updated_at,
        "source_refs": _source_refs(source_record),
    }


def _pull_request_payload(
    pull_request: PullRequest,
    repository: Repository | None,
    source_record: SourceRecord | None,
) -> dict[str, Any]:
    return {
        "id": pull_request.id,
        "type": "pull_request",
        "source_provider": SOURCE_RECORD_PROVIDER_GITHUB,
        "external_id": pull_request.external_id,
        "number": pull_request.number,
        "title": pull_request.title,
        "state": pull_request.state,
        "repository_full_name": repository.full_name if repository else None,
        "repository_external_id": repository.external_id if repository else None,
        "project_key": None,
        "source_url": _safe_url(pull_request.source_url),
        "updated_at": pull_request.updated_at_source or pull_request.created_at,
        "source_refs": _source_refs(source_record),
    }


def _gmail_message_payload(source_record: SourceRecord) -> dict[str, Any]:
    payload = source_record.payload if isinstance(source_record.payload, Mapping) else {}
    normalized = payload.get("normalized_message")
    message = normalized if isinstance(normalized, Mapping) else {}
    labels = _safe_string_list(message.get("labels"))
    return {
        "source_record_id": source_record.id,
        "message_id": _safe_text(message.get("message_id")) or source_record.external_id,
        "thread_id": _safe_text(message.get("thread_id")),
        "subject": _safe_text(message.get("subject")) or "(no subject)",
        "snippet": _safe_text(message.get("snippet")),
        "from_address": _safe_text(message.get("from_address")),
        "to_addresses": _safe_string_list(message.get("to_addresses")),
        "labels": labels,
        "unread": _safe_bool(message.get("unread"))
        or "unread" in {label.casefold() for label in labels},
        "received_at": source_record.source_updated_at,
        "source_url": _safe_url(message.get("source_url")) or _safe_url(source_record.source_url),
        "source_refs": _source_refs(source_record),
    }


def _drive_file_payload(source_record: SourceRecord) -> dict[str, Any]:
    payload = source_record.payload if isinstance(source_record.payload, Mapping) else {}
    normalized = payload.get("normalized_file")
    file = normalized if isinstance(normalized, Mapping) else {}
    return {
        "source_record_id": source_record.id,
        "file_id": _safe_text(file.get("file_id")) or source_record.external_id,
        "name": _safe_text(file.get("name")) or f"Drive file {source_record.external_id}",
        "mime_type": _safe_text(file.get("mime_type")),
        "owners": _safe_string_list(file.get("owners")),
        "drive_id": _safe_text(file.get("drive_id")),
        "folder_path": _safe_text(file.get("folder_path")),
        "shared": _safe_bool(file.get("shared")),
        "size_bytes": _safe_int(file.get("size_bytes")),
        "modified_at": source_record.source_updated_at,
        "source_url": _safe_url(file.get("source_url")) or _safe_url(source_record.source_url),
        "source_refs": _source_refs(source_record),
    }


def _internal_document_payload(document: Document) -> dict[str, Any]:
    # Internal documents are authored in founderOS, so their "source ref" is the
    # local document row itself (no external provider). Raw body is not included
    # here; the brain surfaces a short excerpt for context.
    excerpt = _document_excerpt(document.body_text)
    return {
        "document_id": document.id,
        "title": _safe_text(document.title) or "(untitled)",
        "status": document.status,
        "tags": _safe_string_list(document.tags),
        "excerpt": excerpt,
        "updated_at": document.updated_at,
        "source_refs": [
            {
                "id": f"{document.id}:document",
                "kind": "internal_document",
                "source": "internal",
                "label": _safe_text(document.title) or str(document.id),
                "url": None,
                "record_type": "document",
                "record_id": document.id,
            }
        ],
    }


def _document_excerpt(body_text: Any, *, limit: int = 240) -> str:
    text = _safe_text(body_text)
    if not text:
        return ""
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    return f"{collapsed[: limit - 1]}…"


def _recent_work(
    *,
    tasks: list[Task],
    pull_requests: list[PullRequest],
    repositories: dict[UUID, Repository],
    task_source_records: dict[UUID, SourceRecord],
    pull_request_source_records: dict[str, SourceRecord],
    limit: int,
) -> list[dict[str, Any]]:
    rows = [
        _issue_payload(task, task_source_records.get(task.id))
        for task in tasks
    ] + [
        _pull_request_payload(
            pull_request,
            repositories.get(pull_request.repository_id),
            pull_request_source_records.get(pull_request.external_id),
        )
        for pull_request in pull_requests
    ]
    return sorted(
        rows,
        key=lambda row: row.get("updated_at") or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )[:limit]


def _is_github_issue(task: Task) -> bool:
    metadata = task.task_metadata if isinstance(task.task_metadata, Mapping) else {}
    return metadata.get("github_object_type") == "issue"


def _is_jira_issue(task: Task) -> bool:
    metadata = task.task_metadata if isinstance(task.task_metadata, Mapping) else {}
    return metadata.get("jira_object_type") == "issue"


def _is_open_issue_task(task: Task) -> bool:
    if task.source_provider == TASK_PROVIDER_GITHUB:
        return task.status == PULL_REQUEST_STATE_OPEN
    if task.source_provider == TASK_PROVIDER_JIRA:
        return not _is_done_issue_task(task)
    return False


def _is_done_issue_task(task: Task) -> bool:
    if task.source_provider == TASK_PROVIDER_GITHUB:
        return task.status == "closed"
    if task.source_provider == TASK_PROVIDER_JIRA:
        metadata = task.task_metadata if isinstance(task.task_metadata, Mapping) else {}
        category = _safe_text(metadata.get("status_category"))
        if category == "done":
            return True
        status = (_safe_text(task.status) or "").casefold()
        return status in {"closed", "done", "resolved"}
    return False


def _source_refs(source_record: SourceRecord | None) -> list[dict[str, Any]]:
    if source_record is None:
        return []
    raw_refs = []
    if isinstance(source_record.payload, Mapping):
        candidate = source_record.payload.get("evidence_refs")
        if isinstance(candidate, list):
            raw_refs = candidate
    refs = [
        normalized
        for index, raw in enumerate(raw_refs[:20])
        if (normalized := _normalize_source_ref(source_record, raw, index)) is not None
    ]
    if refs:
        return refs
    return [
        {
            "id": f"{source_record.id}:source-record",
            "kind": "source_record",
            "source": source_record.provider,
            "label": source_record.external_id,
            "url": _safe_url(source_record.source_url),
            "record_type": source_record.record_type,
            "record_id": source_record.id,
        }
    ]


def _normalize_source_ref(
    source_record: SourceRecord,
    raw: Any,
    index: int,
) -> dict[str, Any] | None:
    if not isinstance(raw, Mapping):
        return None
    label = _safe_text(raw.get("ref")) or _safe_text(raw.get("label"))
    if not label:
        return None
    return {
        "id": f"{source_record.id}:{index}",
        "kind": _safe_text(raw.get("kind")) or source_record.record_type,
        "source": _safe_text(raw.get("source")) or source_record.provider,
        "label": label,
        "url": _safe_url(raw.get("url")) or _safe_url(source_record.source_url),
        "record_type": source_record.record_type,
        "record_id": source_record.id,
    }


def _unique_source_refs(source_ref_groups: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    refs: list[dict[str, Any]] = []
    for group in source_ref_groups:
        for ref in group:
            key = str(ref.get("id") or ref.get("label"))
            if key in seen:
                continue
            seen.add(key)
            refs.append(ref)
    return refs


def _safe_text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _safe_url(value: Any) -> str | None:
    text = _safe_text(value)
    if text and text.startswith(("http://", "https://")) and "@" not in text:
        return text[:1000]
    return None


def _safe_int(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _safe_bool(value: Any) -> bool:
    return bool(value) if isinstance(value, bool) else False


def _safe_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    strings: list[str] = []
    for item in value[:40]:
        text = _safe_text(item)
        if text and text not in strings:
            strings.append(text)
    return strings
