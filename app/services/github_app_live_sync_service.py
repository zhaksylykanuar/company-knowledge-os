from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.integration_models import (
    INTEGRATION_CONNECTION_STATUS_CONNECTED,
    INTEGRATION_PROVIDER_GITHUB,
    IntegrationConnection,
)
from app.services import (
    github_app_token_service,
    github_issue_client,
    github_pull_request_client,
    github_repository_client,
)
from app.services.github_app_token_service import GitHubAppTokenError
from app.services.github_connection_service import GITHUB_APP_CONNECTION_METHOD
from app.services.github_issue_client import GitHubIssueClientError
from app.services.github_normalization_service import (
    GitHubNormalizationOptions,
    normalize_github_sync_job_local,
)
from app.services.github_pull_request_client import GitHubPullRequestClientError
from app.services.github_repository_client import GitHubRepositoryClientError
from app.services.github_sync_job_service import (
    GitHubManualSyncJobInput,
    create_manual_github_sync_job,
)

GITHUB_APP_LIVE_SYNC_CONNECTION_NOT_FOUND = "github connection not found"
GITHUB_APP_LIVE_SYNC_CONNECTION_NOT_CONNECTED = "github connection is not connected"
GITHUB_APP_LIVE_SYNC_CONNECTION_NOT_APP_INSTALLATION = (
    "github app installation connection required"
)
GITHUB_APP_LIVE_SYNC_INSTALLATION_ID_MISSING = (
    "github app installation_id is missing"
)
GITHUB_APP_LIVE_SYNC_TOKEN_UNAVAILABLE = "github app installation token unavailable"
GITHUB_APP_LIVE_SYNC_PROVIDER_READ_FAILED = "github app live read failed"
GITHUB_APP_LIVE_SYNC_REPOSITORY_NOT_INSTALLED = (
    "github repository is not part of the app installation"
)
GITHUB_APP_LIVE_SYNC_INVALID_REPOSITORY = "invalid github repository full name"
GITHUB_APP_LIVE_SYNC_INVALID_ISSUE_STATE = "invalid github issue state"
GITHUB_APP_LIVE_SYNC_INVALID_PULL_REQUEST_STATE = "invalid github pull request state"

_ISSUE_STATES = {"open", "closed"}
_ISSUE_ALLOWED_STATES = _ISSUE_STATES | {"all"}
_PR_STATES = {"open", "closed", "merged"}
_PR_ALLOWED_STATES = _PR_STATES | {"all"}


class GitHubAppLiveSyncError(ValueError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class GitHubAppLiveSyncConflictError(GitHubAppLiveSyncError):
    pass


class GitHubAppLiveSyncNotFoundError(GitHubAppLiveSyncError):
    pass


class GitHubAppLiveSyncProviderReadError(GitHubAppLiveSyncError):
    pass


@dataclass(frozen=True)
class GitHubAppLiveSyncInput:
    connection_id: UUID
    repositories: list[str]
    include_issues: bool = True
    include_pull_requests: bool = True
    issue_states: list[str] = field(default_factory=lambda: ["open", "closed"])
    pull_request_states: list[str] = field(
        default_factory=lambda: ["open", "closed", "merged"]
    )


async def sync_github_app_installation_repositories(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    input_payload: GitHubAppLiveSyncInput,
    requested_by: str = "operator_api_key",
) -> dict[str, Any]:
    repositories = _normalize_repositories(input_payload.repositories)
    issue_states = _normalize_issue_states(input_payload.issue_states)
    pull_request_states = _normalize_pull_request_states(
        input_payload.pull_request_states
    )
    connection = await _get_app_installation_connection_or_raise(
        session,
        workspace_id=workspace_id,
        connection_id=input_payload.connection_id,
    )
    installation_id = _installation_id(connection)
    try:
        installation_token = await github_app_token_service.mint_installation_access_token(
            installation_id=installation_id
        )
    except GitHubAppTokenError as exc:
        raise GitHubAppLiveSyncConflictError(
            GITHUB_APP_LIVE_SYNC_TOKEN_UNAVAILABLE
        ) from exc

    try:
        installation_repositories = (
            await github_repository_client.list_installation_repositories(
                access_token=installation_token.token,
            )
        )
    except GitHubRepositoryClientError as exc:
        raise GitHubAppLiveSyncProviderReadError(
            GITHUB_APP_LIVE_SYNC_PROVIDER_READ_FAILED
        ) from exc

    installed_by_full_name = _installation_repository_map(installation_repositories)
    missing_repositories = [
        repository
        for repository in repositories
        if repository.casefold() not in installed_by_full_name
    ]
    if missing_repositories:
        raise GitHubAppLiveSyncConflictError(
            GITHUB_APP_LIVE_SYNC_REPOSITORY_NOT_INSTALLED
        )

    observed_at = datetime.now(timezone.utc).isoformat()
    repository_records: list[dict[str, Any]] = []
    issue_records: list[dict[str, Any]] = []
    pull_request_records: list[dict[str, Any]] = []
    repository_summaries: list[dict[str, Any]] = []
    issue_read_state = _github_issue_read_state(issue_states)
    pull_request_read_state = _github_pull_request_read_state(pull_request_states)

    for repository_full_name in repositories:
        raw_repository = installed_by_full_name[repository_full_name.casefold()]
        repo_issues: list[dict[str, Any]] = []
        repo_pull_requests: list[dict[str, Any]] = []
        skipped_pull_requests = 0

        if input_payload.include_issues:
            try:
                raw_issues = await github_issue_client.list_issues(
                    access_token=installation_token.token,
                    repository_full_name=repository_full_name,
                    state=issue_read_state,
                )
            except GitHubIssueClientError as exc:
                raise GitHubAppLiveSyncProviderReadError(
                    GITHUB_APP_LIVE_SYNC_PROVIDER_READ_FAILED
                ) from exc
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
                if "all" not in issue_states and state not in issue_states:
                    continue
                repo_issues.append(issue)

        if input_payload.include_pull_requests:
            try:
                raw_pull_requests = await github_pull_request_client.list_pull_requests(
                    access_token=installation_token.token,
                    repository_full_name=repository_full_name,
                    state=pull_request_read_state,
                )
            except GitHubPullRequestClientError as exc:
                raise GitHubAppLiveSyncProviderReadError(
                    GITHUB_APP_LIVE_SYNC_PROVIDER_READ_FAILED
                ) from exc
            for raw_pull_request in raw_pull_requests:
                if not isinstance(raw_pull_request, Mapping):
                    continue
                pull_request = _pull_request_record_from_github_response(
                    raw_pull_request,
                    repository_full_name=repository_full_name,
                )
                state = pull_request.get("state")
                if state not in _PR_STATES:
                    continue
                if "all" not in pull_request_states and state not in pull_request_states:
                    continue
                repo_pull_requests.append(pull_request)

        issue_records.extend(repo_issues)
        pull_request_records.extend(repo_pull_requests)
        repository_records.append(
            _repository_record(
                raw_repository,
                repository_full_name=repository_full_name,
                observed_at=observed_at,
                issues=repo_issues,
                pull_requests=repo_pull_requests,
                installation_id=installation_id,
            )
        )
        repository_summaries.append(
            {
                "full_name": repository_full_name,
                "synced_issues": len(repo_issues),
                "synced_pull_requests": len(repo_pull_requests),
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
                    "pull_requests": pull_request_records,
                },
                "github_app_live_sync": {
                    "installation_id": installation_id,
                    "repositories": repositories,
                    "issue_states": issue_states,
                    "pull_request_states": pull_request_states,
                    "provider_sync_started": True,
                    "external_writes": False,
                    "installation_access_token_persisted": False,
                    "installation_token_expires_at": installation_token.expires_at,
                },
            },
            notes="GitHub App installation read sync",
            requested_by=requested_by,
        ),
    )
    normalization = await normalize_github_sync_job_local(
        session,
        workspace_id=workspace_id,
        sync_job_id=sync_job["id"],
        options=GitHubNormalizationOptions(
            include_repositories=True,
            include_issues=input_payload.include_issues,
            include_pull_requests=input_payload.include_pull_requests,
            persist_if_supported=True,
        ),
    )

    return {
        "workspace_id": workspace_id,
        "connection_id": connection.id,
        "installation_id": installation_id,
        "repositories": repository_summaries,
        "totals": _totals(repository_summaries),
        "sync_job": normalization["sync_job"],
        "counts": normalization["counts"],
        "capabilities": {
            "read_only_sync": True,
            "external_writes": False,
            "installation_access_token_persisted": False,
        },
        "is_live": True,
        "provider_sync_started": True,
        "local_normalization_performed": True,
        "external_write_performed": False,
        "persistence_mode": normalization["persistence_mode"],
        "warnings": _warnings(normalization["warnings"]),
    }


async def _get_app_installation_connection_or_raise(
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
        raise GitHubAppLiveSyncNotFoundError(
            GITHUB_APP_LIVE_SYNC_CONNECTION_NOT_FOUND
        )
    if connection.status != INTEGRATION_CONNECTION_STATUS_CONNECTED:
        raise GitHubAppLiveSyncConflictError(
            GITHUB_APP_LIVE_SYNC_CONNECTION_NOT_CONNECTED
        )
    if not isinstance(connection.provider_metadata, Mapping) or (
        connection.provider_metadata.get("connection_method")
        != GITHUB_APP_CONNECTION_METHOD
    ):
        raise GitHubAppLiveSyncConflictError(
            GITHUB_APP_LIVE_SYNC_CONNECTION_NOT_APP_INSTALLATION
        )
    return connection


def _installation_id(connection: IntegrationConnection) -> str:
    if not isinstance(connection.provider_metadata, Mapping):
        raise GitHubAppLiveSyncConflictError(
            GITHUB_APP_LIVE_SYNC_INSTALLATION_ID_MISSING
        )
    raw_installation_id = connection.provider_metadata.get("installation_id")
    if not isinstance(raw_installation_id, str) or not raw_installation_id.strip():
        raise GitHubAppLiveSyncConflictError(
            GITHUB_APP_LIVE_SYNC_INSTALLATION_ID_MISSING
        )
    return raw_installation_id.strip()[:100]


def _installation_repository_map(
    repositories: list[dict[str, Any]],
) -> dict[str, Mapping[str, Any]]:
    mapped: dict[str, Mapping[str, Any]] = {}
    for repository in repositories:
        full_name = _normalize_repository_full_name(repository.get("full_name"))
        if full_name:
            mapped[full_name.casefold()] = repository
    return mapped


def _normalize_repositories(repositories: list[str]) -> list[str]:
    normalized: list[str] = []
    for raw_repository in repositories:
        repository = _normalize_repository_full_name(raw_repository)
        if repository is None:
            raise GitHubAppLiveSyncError(GITHUB_APP_LIVE_SYNC_INVALID_REPOSITORY)
        if repository.casefold() not in {item.casefold() for item in normalized}:
            normalized.append(repository)
    if not normalized:
        raise GitHubAppLiveSyncError(GITHUB_APP_LIVE_SYNC_INVALID_REPOSITORY)
    return normalized


def _normalize_repository_full_name(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    raw_owner, separator, raw_name = value.strip().partition("/")
    if separator != "/":
        return None
    owner = _safe_repo_part(raw_owner)
    name = _safe_repo_part(raw_name)
    if owner is None or name is None:
        return None
    return f"{owner}/{name}"


def _safe_repo_part(value: str) -> str | None:
    part = value.strip()
    if (
        not part
        or part.startswith(".")
        or part.endswith(".")
        or ".." in part
        or any(character.isspace() for character in part)
    ):
        return None
    if not all(character.isalnum() or character in {".", "_", "-"} for character in part):
        return None
    return part[:100]


def _normalize_issue_states(states: list[str]) -> list[str]:
    normalized: list[str] = []
    for raw_state in states or ["open", "closed"]:
        state = raw_state.strip().casefold() if isinstance(raw_state, str) else ""
        if state not in _ISSUE_ALLOWED_STATES:
            raise GitHubAppLiveSyncError(GITHUB_APP_LIVE_SYNC_INVALID_ISSUE_STATE)
        if state == "all":
            return ["all"]
        if state not in normalized:
            normalized.append(state)
    return normalized or ["open", "closed"]


def _normalize_pull_request_states(states: list[str]) -> list[str]:
    normalized: list[str] = []
    for raw_state in states or ["open", "closed", "merged"]:
        state = raw_state.strip().casefold() if isinstance(raw_state, str) else ""
        if state not in _PR_ALLOWED_STATES:
            raise GitHubAppLiveSyncError(
                GITHUB_APP_LIVE_SYNC_INVALID_PULL_REQUEST_STATE
            )
        if state == "all":
            return ["all"]
        if state not in normalized:
            normalized.append(state)
    return normalized or ["open", "closed", "merged"]


def _github_issue_read_state(states: list[str]) -> str:
    if "all" in states or {"open", "closed"}.issubset(set(states)):
        return "all"
    return states[0]


def _github_pull_request_read_state(states: list[str]) -> str:
    selected = set(states)
    if "all" in selected:
        return "all"
    if "open" in selected and ({"closed", "merged"} & selected):
        return "all"
    if selected <= {"closed", "merged"}:
        return "closed"
    return "open"


def _repository_record(
    raw_repository: Mapping[str, Any],
    *,
    repository_full_name: str,
    observed_at: str,
    issues: list[dict[str, Any]],
    pull_requests: list[dict[str, Any]],
    installation_id: str,
) -> dict[str, Any]:
    source_url = _safe_url(raw_repository.get("html_url")) or (
        f"https://github.com/{repository_full_name}"
    )
    return {
        "id": _safe_text(raw_repository.get("id"), limit=255) or repository_full_name,
        "external_id": _safe_text(raw_repository.get("id"), limit=255)
        or repository_full_name,
        "name": _safe_text(raw_repository.get("name"), limit=255)
        or repository_full_name.rsplit("/", 1)[-1],
        "full_name": repository_full_name,
        "default_branch": _safe_text(raw_repository.get("default_branch"), limit=255),
        "visibility": _repository_visibility(raw_repository),
        "archived": bool(raw_repository.get("archived")),
        "source_url": source_url,
        "last_activity_at": _latest_repository_timestamp(
            raw_repository,
            issues=issues,
            pull_requests=pull_requests,
        )
        or observed_at,
        "source": "github_app_live_sync",
        "evidence_refs": [
            {
                "kind": "github_repository",
                "source": "github",
                "ref": repository_full_name,
                "url": source_url,
            }
        ],
        "metadata": {
            "source": "github_app_live_sync",
            "installation_id": installation_id,
            "issues_observed": len(issues),
            "pull_requests_observed": len(pull_requests),
        },
    }


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
            "source": "github_app_live_sync",
            "repository_full_name": repository_full_name,
            "number": number,
            "state": state,
        },
    }


def _pull_request_record_from_github_response(
    raw_pull_request: Mapping[str, Any],
    *,
    repository_full_name: str,
) -> dict[str, Any]:
    number = _safe_int(raw_pull_request.get("number"))
    source_url = _safe_url(raw_pull_request.get("html_url"))
    provider_id = _safe_text(raw_pull_request.get("id"), limit=255)
    external_id = (
        f"{repository_full_name}#pull/{number}"
        if number is not None
        else provider_id or f"{repository_full_name}#pull/unknown"
    )
    state = _pull_request_state(raw_pull_request)
    return {
        "id": external_id,
        "external_id": external_id,
        "number": number,
        "title": _safe_text(raw_pull_request.get("title"), limit=500)
        or f"GitHub PR {number or external_id}",
        "state": state,
        "html_url": source_url,
        "repository_full_name": repository_full_name,
        "created_at": _safe_text(raw_pull_request.get("created_at")),
        "updated_at": _safe_text(raw_pull_request.get("updated_at")),
        "merged_at": _safe_text(raw_pull_request.get("merged_at")),
        "evidence_refs": [
            {
                "kind": "github_pull_request",
                "source": "github",
                "ref": external_id,
                "url": source_url,
            }
        ],
        "metadata": {
            "source": "github_app_live_sync",
            "repository_full_name": repository_full_name,
            "number": number,
            "state": state,
            "provider_id": provider_id,
            "draft": bool(raw_pull_request.get("draft")),
        },
    }


def _latest_repository_timestamp(
    raw_repository: Mapping[str, Any],
    *,
    issues: list[dict[str, Any]],
    pull_requests: list[dict[str, Any]],
) -> str | None:
    candidates = [
        _safe_text(raw_repository.get("pushed_at")),
        _safe_text(raw_repository.get("updated_at")),
    ]
    candidates.extend(_safe_text(issue.get("updated_at")) for issue in issues)
    candidates.extend(_safe_text(pr.get("updated_at")) for pr in pull_requests)
    values = [value for value in candidates if value]
    return max(values) if values else None


def _totals(repository_summaries: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "repositories": len(repository_summaries),
        "issues": sum(item["synced_issues"] for item in repository_summaries),
        "pull_requests": sum(
            item["synced_pull_requests"] for item in repository_summaries
        ),
        "skipped_pull_requests": sum(
            item["skipped_pull_requests"] for item in repository_summaries
        ),
    }


def _warnings(normalization_warnings: list[str]) -> list[str]:
    return _dedupe_warnings(
        [
            "GitHub App live sync is read-only; no external writes were performed.",
            "GitHub App installation access token was minted just-in-time and was not persisted.",
            *normalization_warnings,
        ]
    )


def _repository_visibility(raw_repository: Mapping[str, Any]) -> str:
    raw_visibility = raw_repository.get("visibility")
    if isinstance(raw_visibility, str) and raw_visibility in {
        "public",
        "private",
        "internal",
    }:
        return raw_visibility
    if raw_repository.get("private") is True:
        return "private"
    if raw_repository.get("private") is False:
        return "public"
    return "unknown"


def _safe_issue_state(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    state = value.strip().casefold()
    return state if state in _ISSUE_STATES else None


def _pull_request_state(raw_pull_request: Mapping[str, Any]) -> str | None:
    raw_state = _safe_text(raw_pull_request.get("state"))
    if raw_state == "closed" and raw_pull_request.get("merged_at"):
        return "merged"
    return raw_state if raw_state in {"open", "closed"} else None


def _safe_int(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _safe_url(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if not (stripped.startswith("https://") or stripped.startswith("http://")):
        return None
    return stripped[:500]


def _safe_text(value: Any, *, limit: int = 1000) -> str | None:
    if not isinstance(value, str | int):
        return None
    stripped = str(value).strip()
    return stripped[:limit] if stripped else None


def _dedupe_warnings(warnings: list[str]) -> list[str]:
    deduped: list[str] = []
    for warning in warnings:
        if warning not in deduped:
            deduped.append(warning)
    return deduped
