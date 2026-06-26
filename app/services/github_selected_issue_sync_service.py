from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.integration_models import (
    INTEGRATION_CONNECTION_STATUS_CONNECTED,
    INTEGRATION_PROVIDER_GITHUB,
    IntegrationConnection,
)
import app.services.github_issue_client as github_issue_client
from app.services.github_issue_client import GitHubIssueClientError
from app.services.github_normalization_service import (
    GitHubNormalizationOptions,
    normalize_github_sync_job_local,
)
from app.services.github_sync_job_service import (
    GitHubManualSyncJobInput,
    create_manual_github_sync_job,
)
from app.services.secret_encryption import SecretEncryptionError, decrypt_secret

GITHUB_SELECTED_ISSUE_SYNC_ALLOWLIST_REQUIRED = (
    "github selected issue sync allowed repositories are not configured"
)
GITHUB_SELECTED_ISSUE_SYNC_REPOSITORY_NOT_ALLOWED = (
    "github repository is not allowed for selected issue sync"
)
GITHUB_SELECTED_ISSUE_SYNC_CONNECTION_NOT_FOUND = "github connection not found"
GITHUB_SELECTED_ISSUE_SYNC_CONNECTION_NOT_CONNECTED = (
    "github connection is not connected"
)
GITHUB_SELECTED_ISSUE_SYNC_TOKEN_MISSING = (
    "github connection has no encrypted access token"
)
GITHUB_SELECTED_ISSUE_SYNC_TOKEN_UNAVAILABLE = "github token could not be decrypted"
GITHUB_SELECTED_ISSUE_SYNC_PROVIDER_READ_FAILED = "github selected issue read failed"
GITHUB_SELECTED_ISSUE_SYNC_INVALID_REPOSITORY = "invalid github repository full name"
GITHUB_SELECTED_ISSUE_SYNC_INVALID_STATE = "invalid github issue state"

_ALLOWED_STATES = {"open", "closed", "all"}
_ISSUE_STATES = {"open", "closed"}


class GitHubSelectedIssueSyncError(ValueError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class GitHubSelectedIssueSyncConflictError(GitHubSelectedIssueSyncError):
    pass


class GitHubSelectedIssueSyncNotFoundError(GitHubSelectedIssueSyncError):
    pass


class GitHubSelectedIssueSyncProviderReadError(GitHubSelectedIssueSyncError):
    pass


@dataclass(frozen=True)
class GitHubSelectedIssueSyncInput:
    connection_id: UUID
    repositories: list[str]
    states: list[str] = field(default_factory=lambda: ["open", "closed"])


async def sync_selected_repository_issues(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    input_payload: GitHubSelectedIssueSyncInput,
    requested_by: str = "operator_api_key",
) -> dict[str, Any]:
    repositories = _normalize_repositories(input_payload.repositories)
    states = _normalize_states(input_payload.states)
    _validate_sync_allowlist(repositories)

    connection = await _get_connection_or_raise(
        session,
        workspace_id=workspace_id,
        connection_id=input_payload.connection_id,
    )
    try:
        access_token = decrypt_secret(connection.encrypted_access_token or "")
    except SecretEncryptionError as exc:
        raise GitHubSelectedIssueSyncConflictError(
            GITHUB_SELECTED_ISSUE_SYNC_TOKEN_UNAVAILABLE
        ) from exc

    issue_records: list[dict[str, Any]] = []
    repository_records: list[dict[str, Any]] = []
    repository_summaries: list[dict[str, Any]] = []
    read_state = _github_read_state(states)
    observed_at = datetime.now(timezone.utc).isoformat()

    for repository_full_name in repositories:
        try:
            raw_issues = await github_issue_client.list_issues(
                access_token=access_token,
                repository_full_name=repository_full_name,
                state=read_state,
            )
        except GitHubIssueClientError as exc:
            raise GitHubSelectedIssueSyncProviderReadError(
                GITHUB_SELECTED_ISSUE_SYNC_PROVIDER_READ_FAILED
            ) from exc

        repo_issues: list[dict[str, Any]] = []
        skipped_pull_requests = 0
        for raw_issue in raw_issues:
            if not isinstance(raw_issue, Mapping):
                continue
            if raw_issue.get("pull_request") is not None:
                skipped_pull_requests += 1
                continue
            issue = _issue_record_from_github_response(
                raw_issue,
                repository_full_name=repository_full_name,
            )
            state = issue.get("state")
            if state not in _ISSUE_STATES:
                continue
            if "all" not in states and state not in states:
                continue
            repo_issues.append(issue)

        issue_records.extend(repo_issues)
        repository_records.append(
            _repository_record(
                repository_full_name=repository_full_name,
                observed_at=observed_at,
                issues=repo_issues,
            )
        )
        repository_summaries.append(
            {
                "full_name": repository_full_name,
                "synced_issues": len(repo_issues),
                "open_issues": sum(1 for issue in repo_issues if issue["state"] == "open"),
                "closed_issues": sum(
                    1 for issue in repo_issues if issue["state"] == "closed"
                ),
                "skipped_pull_requests": skipped_pull_requests,
            }
        )

    sync_job = await create_manual_github_sync_job(
        session,
        workspace_id=workspace_id,
        connection_id=connection.id,
        payload=GitHubManualSyncJobInput(
            cursor_before={
                "local_github": {
                    "repositories": repository_records,
                    "issues": issue_records,
                    "pull_requests": [],
                },
                "selected_repository_issue_sync": {
                    "repositories": repositories,
                    "states": states,
                    "read_state": read_state,
                    "provider_sync_started": True,
                    "external_writes": False,
                },
            },
            notes="selected repository GitHub issue read sync",
            requested_by=requested_by,
        ),
    )
    normalization = await normalize_github_sync_job_local(
        session,
        workspace_id=workspace_id,
        sync_job_id=sync_job["id"],
        options=GitHubNormalizationOptions(
            include_repositories=True,
            include_issues=True,
            include_pull_requests=False,
            persist_if_supported=True,
        ),
    )
    totals = _totals(repository_summaries)
    return {
        "workspace_id": workspace_id,
        "repositories": repository_summaries,
        "totals": totals,
        "sync_job": normalization["sync_job"],
        "counts": normalization["counts"],
        "capabilities": {
            "read_only_sync": True,
            "external_writes": False,
        },
        "is_live": True,
        "provider_sync_started": True,
        "external_write_performed": False,
        "warnings": _warnings(repository_summaries, normalization["warnings"]),
    }


def _normalize_repositories(repositories: list[str]) -> list[str]:
    normalized: list[str] = []
    for raw_repository in repositories:
        repository = _normalize_repository_full_name(raw_repository)
        if repository is None:
            raise GitHubSelectedIssueSyncError(
                GITHUB_SELECTED_ISSUE_SYNC_INVALID_REPOSITORY
            )
        if repository not in normalized:
            normalized.append(repository)
    if not normalized:
        raise GitHubSelectedIssueSyncError(GITHUB_SELECTED_ISSUE_SYNC_INVALID_REPOSITORY)
    return normalized


def _normalize_repository_full_name(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    parts = value.strip().removesuffix(".git").split("/")
    if len(parts) != 2:
        return None
    owner = _safe_repo_part(parts[0])
    repo = _safe_repo_part(parts[1])
    if owner and repo:
        return f"{owner}/{repo}"
    return None


def _safe_repo_part(value: str) -> str | None:
    text = value.strip()
    if not text or "/" in text:
        return None
    if not all(character.isalnum() or character in {"-", "_", "."} for character in text):
        return None
    return text


def _normalize_states(states: list[str]) -> list[str]:
    normalized: list[str] = []
    for raw_state in states or ["open", "closed"]:
        state = raw_state.strip().casefold() if isinstance(raw_state, str) else ""
        if state not in _ALLOWED_STATES:
            raise GitHubSelectedIssueSyncError(GITHUB_SELECTED_ISSUE_SYNC_INVALID_STATE)
        if state == "all":
            return ["all"]
        if state not in normalized:
            normalized.append(state)
    return normalized or ["open", "closed"]


def _github_read_state(states: list[str]) -> str:
    if "all" in states or {"open", "closed"}.issubset(set(states)):
        return "all"
    return states[0]


def _validate_sync_allowlist(repositories: list[str]) -> None:
    allowed_repositories = _github_sync_allowed_repositories()
    if not allowed_repositories:
        raise GitHubSelectedIssueSyncConflictError(
            GITHUB_SELECTED_ISSUE_SYNC_ALLOWLIST_REQUIRED
        )
    for repository in repositories:
        if repository.casefold() not in allowed_repositories:
            raise GitHubSelectedIssueSyncConflictError(
                GITHUB_SELECTED_ISSUE_SYNC_REPOSITORY_NOT_ALLOWED
            )


def _github_sync_allowed_repositories() -> set[str]:
    raw_value = settings.github_sync_allowed_repos or settings.github_repos
    if raw_value is None:
        return set()
    return {
        repository.casefold()
        for item in raw_value.replace("\n", ",").split(",")
        if (repository := _normalize_repository_full_name(item)) is not None
    }


async def _get_connection_or_raise(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    connection_id: UUID,
) -> IntegrationConnection:
    connection = await session.scalar(
        select(IntegrationConnection)
        .where(IntegrationConnection.workspace_id == workspace_id)
        .where(IntegrationConnection.provider == INTEGRATION_PROVIDER_GITHUB)
        .where(IntegrationConnection.id == connection_id)
    )
    if connection is None:
        raise GitHubSelectedIssueSyncNotFoundError(
            GITHUB_SELECTED_ISSUE_SYNC_CONNECTION_NOT_FOUND
        )
    if connection.status != INTEGRATION_CONNECTION_STATUS_CONNECTED:
        raise GitHubSelectedIssueSyncConflictError(
            GITHUB_SELECTED_ISSUE_SYNC_CONNECTION_NOT_CONNECTED
        )
    if not connection.encrypted_access_token:
        raise GitHubSelectedIssueSyncConflictError(
            GITHUB_SELECTED_ISSUE_SYNC_TOKEN_MISSING
        )
    return connection


def _issue_record_from_github_response(
    raw_issue: Mapping[str, Any],
    *,
    repository_full_name: str,
) -> dict[str, Any]:
    number = _safe_int(raw_issue.get("number"))
    source_url = _safe_url(raw_issue.get("html_url"))
    external_id = (
        _safe_text(raw_issue.get("id"), limit=255)
        or f"{repository_full_name}#issue/{number or 'unknown'}"
    )
    state = _safe_issue_state(raw_issue.get("state"))
    return {
        "id": external_id,
        "external_id": external_id,
        "number": number,
        "title": _safe_text(raw_issue.get("title"), limit=500)
        or f"GitHub issue {number or external_id}",
        "state": state,
        "html_url": source_url,
        "repository_full_name": repository_full_name,
        "created_at": _safe_text(raw_issue.get("created_at")),
        "updated_at": _safe_text(raw_issue.get("updated_at")),
        "evidence_refs": [
            {
                "kind": "github_issue",
                "source": "github",
                "ref": external_id,
                "url": source_url,
            }
        ],
        "metadata": {
            "source": "selected_repository_issue_sync",
            "repository_full_name": repository_full_name,
            "number": number,
            "state": state,
        },
    }


def _repository_record(
    *,
    repository_full_name: str,
    observed_at: str,
    issues: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "external_id": repository_full_name,
        "name": repository_full_name.rsplit("/", 1)[-1],
        "full_name": repository_full_name,
        "visibility": "unknown",
        "source_url": f"https://github.com/{repository_full_name}",
        "last_activity_at": _latest_issue_timestamp(issues) or observed_at,
        "source": "selected_repository_issue_sync",
        "evidence_refs": [
            {
                "kind": "github_repository",
                "source": "github",
                "ref": repository_full_name,
                "url": f"https://github.com/{repository_full_name}",
            }
        ],
        "metadata": {
            "source": "selected_repository_issue_sync",
            "issues_observed": len(issues),
        },
    }


def _latest_issue_timestamp(issues: list[dict[str, Any]]) -> str | None:
    values = [
        value
        for issue in issues
        if isinstance((value := issue.get("updated_at")), str) and value
    ]
    return max(values) if values else None


def _totals(repository_summaries: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "repositories": len(repository_summaries),
        "issues": sum(item["synced_issues"] for item in repository_summaries),
        "open_issues": sum(item["open_issues"] for item in repository_summaries),
        "closed_issues": sum(item["closed_issues"] for item in repository_summaries),
        "skipped_pull_requests": sum(
            item["skipped_pull_requests"] for item in repository_summaries
        ),
    }


def _warnings(
    repository_summaries: list[dict[str, Any]],
    normalization_warnings: list[str],
) -> list[str]:
    warnings = [
        "Selected repository issue sync used read-only GitHub issue access.",
        "No external write occurred during selected repository issue sync.",
    ]
    if any(summary["skipped_pull_requests"] for summary in repository_summaries):
        warnings.append(
            "GitHub issue API returned pull request shaped records; they were skipped."
        )
    warnings.extend(normalization_warnings)
    return _dedupe_warnings(warnings)


def _safe_issue_state(value: Any) -> str | None:
    text = _safe_text(value)
    if text is None:
        return None
    normalized = text.casefold()
    return normalized if normalized in _ISSUE_STATES else None


def _safe_int(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _safe_url(value: Any) -> str | None:
    text = _safe_text(value)
    if text and "@" not in text:
        return text[:1000]
    return None


def _safe_text(value: Any, *, limit: int = 1000) -> str | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)[:limit]
    return value.strip()[:limit] if isinstance(value, str) and value.strip() else None


def _dedupe_warnings(warnings: list[str]) -> list[str]:
    deduped: list[str] = []
    for warning in warnings:
        if warning and warning not in deduped:
            deduped.append(warning)
    return deduped
