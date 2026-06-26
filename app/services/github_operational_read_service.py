from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.canonical_models import (
    PULL_REQUEST_STATE_CLOSED,
    PULL_REQUEST_STATE_MERGED,
    PULL_REQUEST_STATE_OPEN,
    TASK_PROVIDER_GITHUB,
    PullRequest,
    Repository,
    Task,
)

GITHUB_OPERATIONAL_WORK_SOURCE = "canonical_github_operational_work"
_VALID_STATES = {
    PULL_REQUEST_STATE_OPEN,
    PULL_REQUEST_STATE_CLOSED,
    PULL_REQUEST_STATE_MERGED,
    "all",
}


async def list_workspace_github_operational_work(
    *,
    session: AsyncSession,
    workspace_id: UUID,
    state: str = PULL_REQUEST_STATE_OPEN,
    limit: int = 100,
) -> dict[str, Any]:
    selected_state = state if state in _VALID_STATES else PULL_REQUEST_STATE_OPEN
    issues = await _github_issues(
        session=session,
        workspace_id=workspace_id,
        state=selected_state,
        limit=limit,
    )
    pull_requests = await _github_pull_requests(
        session=session,
        workspace_id=workspace_id,
        state=selected_state,
        limit=limit,
    )
    return {
        "issues": issues,
        "pull_requests": pull_requests,
        "counts": {
            "issues": len(issues),
            "pull_requests": len(pull_requests),
        },
        "state": selected_state,
        "source": GITHUB_OPERATIONAL_WORK_SOURCE,
        "is_live": False,
        "warnings": [],
    }


async def _github_issues(
    *,
    session: AsyncSession,
    workspace_id: UUID,
    state: str,
    limit: int,
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(Task)
            .where(Task.workspace_id == workspace_id)
            .where(Task.source_provider == TASK_PROVIDER_GITHUB)
            .order_by(
                Task.source_updated_at.desc().nullslast(),
                Task.updated_at.desc(),
                Task.created_at.desc(),
            )
            .limit(max(limit * 3, limit))
        )
    ).scalars()
    issues: list[dict[str, Any]] = []
    seen_issue_keys: set[str] = set()
    for row in rows:
        if not _is_github_issue(row):
            continue
        issue_key = _issue_identity_key(row)
        if issue_key in seen_issue_keys:
            continue
        seen_issue_keys.add(issue_key)
        if not _issue_state_matches(row.status, state):
            continue
        issues.append(_issue_payload(row))
        if len(issues) >= limit:
            break
    return issues


async def _github_pull_requests(
    *,
    session: AsyncSession,
    workspace_id: UUID,
    state: str,
    limit: int,
) -> list[dict[str, Any]]:
    statement = (
        select(PullRequest)
        .where(PullRequest.workspace_id == workspace_id)
        .order_by(PullRequest.updated_at_source.desc().nullslast(), PullRequest.created_at.desc())
        .limit(limit)
    )
    if state != "all":
        statement = statement.where(PullRequest.state == state)
    rows = list((await session.execute(statement)).scalars())
    repository_ids = {row.repository_id for row in rows}
    repositories: dict[UUID, Repository] = {}
    if repository_ids:
        repositories = {
            repository.id: repository
            for repository in (
                await session.execute(
                    select(Repository).where(Repository.id.in_(repository_ids))
                )
            ).scalars()
        }
    return [_pull_request_payload(row, repositories.get(row.repository_id)) for row in rows]


def _is_github_issue(task: Task) -> bool:
    metadata = task.task_metadata if isinstance(task.task_metadata, Mapping) else {}
    return metadata.get("github_object_type") == "issue"


def _issue_state_matches(status: str | None, state: str) -> bool:
    if state == "all":
        return True
    if state == PULL_REQUEST_STATE_MERGED:
        return False
    return status == state


def _issue_payload(task: Task) -> dict[str, Any]:
    metadata = task.task_metadata if isinstance(task.task_metadata, Mapping) else {}
    return {
        "id": task.id,
        "external_id": task.external_id,
        "number": _safe_int(metadata.get("number")),
        "title": task.title,
        "state": task.status,
        "source_url": task.source_url,
        "repository_full_name": _safe_text(metadata.get("repository_full_name")),
        "repository_external_id": _safe_text(metadata.get("repository_external_id")),
        "source_record_id": task.source_record_id,
        "source_updated_at": task.source_updated_at,
        "metadata": _safe_metadata(metadata),
    }


def _issue_identity_key(task: Task) -> str:
    metadata = task.task_metadata if isinstance(task.task_metadata, Mapping) else {}
    repository_full_name = _safe_text(metadata.get("repository_full_name"))
    number = _safe_int(metadata.get("number"))
    if repository_full_name and number is not None:
        return f"{repository_full_name}#issue/{number}"
    if task.external_id:
        return task.external_id
    return str(task.id)


def _pull_request_payload(
    pull_request: PullRequest,
    repository: Repository | None,
) -> dict[str, Any]:
    return {
        "id": pull_request.id,
        "external_id": pull_request.external_id,
        "number": pull_request.number,
        "title": pull_request.title,
        "state": pull_request.state,
        "source_url": pull_request.source_url,
        "repository_id": pull_request.repository_id,
        "repository_full_name": repository.full_name if repository else None,
        "repository_external_id": repository.external_id if repository else None,
        "created_at_source": pull_request.created_at_source,
        "updated_at_source": pull_request.updated_at_source,
        "merged_at_source": pull_request.merged_at_source,
        "metadata": _safe_metadata(
            pull_request.pr_metadata
            if isinstance(pull_request.pr_metadata, Mapping)
            else {}
        ),
    }


def _safe_text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _safe_int(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _safe_metadata(value: Mapping[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, raw in value.items():
        if not isinstance(key, str) or _metadata_key_is_sensitive(key):
            continue
        if isinstance(raw, datetime):
            safe[key] = raw.isoformat()
        elif isinstance(raw, str):
            safe[key] = raw[:500]
        elif isinstance(raw, bool | int | float) or raw is None:
            safe[key] = raw
        elif isinstance(raw, list):
            safe[key] = raw[:20]
        elif isinstance(raw, Mapping):
            safe[key] = _safe_metadata(raw)
        else:
            safe[key] = str(raw)[:500]
    return safe


def _metadata_key_is_sensitive(key: str) -> bool:
    normalized = key.casefold().replace("-", "_")
    return any(
        marker in normalized
        for marker in (
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
    )
