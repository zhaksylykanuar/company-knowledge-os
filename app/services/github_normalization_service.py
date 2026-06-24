from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import app.services.github_repository_read_service as github_repository_read_service
from app.db.canonical_models import (
    SOURCE_RECORD_PROVIDER_GITHUB,
    Repository,
    SourceRecord,
)
from app.db.integration_models import (
    INTEGRATION_PROVIDER_GITHUB,
    SYNC_JOB_STATUS_PARTIAL,
    SYNC_JOB_STATUS_QUEUED,
    SYNC_JOB_STATUS_RUNNING,
    SYNC_JOB_STATUS_SUCCEEDED,
    SYNC_JOB_TYPE_MANUAL,
    SyncJob,
)

GITHUB_NORMALIZATION_PROJECTION_WARNING = (
    "GitHub data normalized through compatibility projection; persistent graph upsert is deferred."
)
GITHUB_NORMALIZATION_ISSUES_UNAVAILABLE_WARNING = (
    "GitHub issues were not available in local source; returned empty issues array."
)
GITHUB_NORMALIZATION_PULL_REQUESTS_UNAVAILABLE_WARNING = (
    "GitHub pull requests were not available in local source; returned empty pull_requests array."
)
GITHUB_NORMALIZATION_NO_LOCAL_REPOSITORIES_WARNING = (
    "No local GitHub repository inventory found for normalization."
)
GITHUB_NORMALIZATION_JOB_NOT_FOUND = "github sync job not found"
GITHUB_NORMALIZATION_JOB_NOT_GITHUB = "github manual sync job required"
GITHUB_NORMALIZATION_JOB_NOT_MANUAL = "github manual sync job required"
GITHUB_NORMALIZATION_JOB_NOT_QUEUED = "github sync job must be queued"
GITHUB_NORMALIZATION_PERSISTENCE_DEFERRED = (
    "persistent graph upsert is deferred for GitHub normalization"
)

PERSISTENCE_MODE_PROJECTION = "projection"
PERSISTENCE_MODE_CANONICAL = "canonical"
SOURCE_RECORD_TYPE_REPOSITORY = "repository"

GITHUB_NORMALIZATION_CANONICAL_WARNING = (
    "GitHub repository normalization persisted to canonical SourceRecord/Repository tables."
)


@dataclass(frozen=True)
class GitHubNormalizationOptions:
    include_repositories: bool = True
    include_issues: bool = True
    include_pull_requests: bool = True
    persist_if_supported: bool = False


class GitHubNormalizationError(ValueError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


@dataclass(frozen=True)
class CanonicalRepositoryPersistenceCounts:
    source_records_created: int = 0
    source_records_updated: int = 0
    repositories_created: int = 0
    repositories_updated: int = 0


async def normalize_github_sync_job_local(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    sync_job_id: UUID,
    options: GitHubNormalizationOptions,
) -> dict[str, Any]:
    sync_job = await _get_workspace_sync_job(
        session,
        workspace_id=workspace_id,
        sync_job_id=sync_job_id,
    )
    if sync_job is None:
        raise GitHubNormalizationError(GITHUB_NORMALIZATION_JOB_NOT_FOUND)
    _validate_sync_job(sync_job)

    started_at = datetime.now(timezone.utc)
    sync_job.status = SYNC_JOB_STATUS_RUNNING
    sync_job.started_at = started_at
    sync_job.error_message = None
    await session.flush()

    persistence_mode = (
        PERSISTENCE_MODE_CANONICAL
        if options.persist_if_supported
        else PERSISTENCE_MODE_PROJECTION
    )
    warnings = [
        GITHUB_NORMALIZATION_CANONICAL_WARNING
        if options.persist_if_supported
        else GITHUB_NORMALIZATION_PROJECTION_WARNING
    ]
    repositories: list[dict[str, Any]] = []
    if options.include_repositories:
        repository_result = await github_repository_read_service.list_workspace_github_repositories(
            session=session,
            workspace_id=workspace_id,
            filters=github_repository_read_service.GitHubRepositoryFilters(limit=100),
        )
        repositories = [
            build_normalized_repository(repository)
            for repository in repository_result.repositories
        ]
        warnings.extend(repository_result.warnings)
        if not repositories:
            warnings.append(GITHUB_NORMALIZATION_NO_LOCAL_REPOSITORIES_WARNING)

    issues: list[dict[str, Any]] = []
    pull_requests: list[dict[str, Any]] = []
    if options.include_issues:
        warnings.append(GITHUB_NORMALIZATION_ISSUES_UNAVAILABLE_WARNING)
    if options.include_pull_requests:
        warnings.append(GITHUB_NORMALIZATION_PULL_REQUESTS_UNAVAILABLE_WARNING)

    counts = {
        "repositories": len(repositories),
        "issues": len(issues),
        "pull_requests": len(pull_requests),
    }
    persistence_counts = CanonicalRepositoryPersistenceCounts()
    if options.persist_if_supported:
        persistence_counts = await _persist_canonical_repositories(
            session,
            sync_job=sync_job,
            repositories=repositories,
            observed_at=started_at,
        )
    missing_requested_data = (
        (options.include_repositories and not repositories)
        or (options.include_issues and not issues)
        or (options.include_pull_requests and not pull_requests)
    )
    sync_job.status = (
        SYNC_JOB_STATUS_PARTIAL if missing_requested_data else SYNC_JOB_STATUS_SUCCEEDED
    )
    sync_job.finished_at = datetime.now(timezone.utc)
    sync_job.records_seen = sum(counts.values())
    sync_job.records_created = persistence_counts.repositories_created
    sync_job.records_updated = persistence_counts.repositories_updated
    sync_job.cursor_after = {
        "local_normalization_performed": True,
        "provider_sync_started": False,
        "persistence_mode": persistence_mode,
        "counts": counts,
        "canonical_persistence": _persistence_counts_payload(persistence_counts),
    }
    sync_job.logs = _append_normalization_log(
        sync_job.logs,
        counts=counts,
        persistence_counts=persistence_counts,
        persistence_mode=persistence_mode,
        warnings=warnings,
        options=options,
    )
    await session.flush()
    await session.refresh(sync_job)

    return {
        "sync_job": {
            "id": sync_job.id,
            "status": sync_job.status,
            "records_seen": sync_job.records_seen,
            "records_created": sync_job.records_created,
            "records_updated": sync_job.records_updated,
            "started_at": sync_job.started_at,
            "finished_at": sync_job.finished_at,
        },
        "normalized": {
            "repositories": repositories,
            "issues": issues,
            "pull_requests": pull_requests,
        },
        "counts": counts,
        "is_live": False,
        "provider_sync_started": False,
        "local_normalization_performed": True,
        "persistence_mode": persistence_mode,
        "warnings": _dedupe_warnings(warnings),
    }


def build_normalized_repository(repo: Mapping[str, Any]) -> dict[str, Any]:
    full_name = _safe_text(repo.get("full_name")) or _safe_text(repo.get("name")) or "unknown"
    name = _safe_text(repo.get("name")) or full_name.rsplit("/", 1)[-1]
    return {
        "entity_type": "repository",
        "provider": INTEGRATION_PROVIDER_GITHUB,
        "external_id": _safe_text(repo.get("id")) or full_name or name,
        "name": name,
        "full_name": full_name,
        "default_branch": _safe_text(repo.get("default_branch")),
        "visibility": _safe_visibility(repo.get("visibility")),
        "archived": bool(repo.get("archived")),
        "source_url": _safe_url(repo.get("source_url")),
        "last_activity_at": _safe_text(repo.get("last_activity_at")),
        "source": _safe_source(repo.get("source")),
        "evidence_refs": _safe_evidence_refs(repo.get("evidence_refs")),
        "metadata": _safe_metadata(repo.get("metadata")),
    }


def build_normalized_issue(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "entity_type": "task",
        "provider": INTEGRATION_PROVIDER_GITHUB,
        "external_id": _safe_text(record.get("external_id")) or "unknown",
        "number": record.get("number") if isinstance(record.get("number"), int) else None,
        "title": _safe_text(record.get("title")),
        "state": _safe_text(record.get("state")),
        "source_url": _safe_url(record.get("source_url")),
        "repository_full_name": _safe_text(record.get("repository_full_name")),
        "created_at_source": _safe_text(record.get("created_at_source")),
        "updated_at_source": _safe_text(record.get("updated_at_source")),
        "evidence_refs": _safe_evidence_refs(record.get("evidence_refs")),
        "metadata": _safe_metadata(record.get("metadata")),
    }


def build_normalized_pull_request(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "entity_type": "pull_request",
        "provider": INTEGRATION_PROVIDER_GITHUB,
        "external_id": _safe_text(record.get("external_id")) or "unknown",
        "number": record.get("number") if isinstance(record.get("number"), int) else None,
        "title": _safe_text(record.get("title")),
        "state": _safe_text(record.get("state")),
        "source_url": _safe_url(record.get("source_url")),
        "repository_full_name": _safe_text(record.get("repository_full_name")),
        "created_at_source": _safe_text(record.get("created_at_source")),
        "updated_at_source": _safe_text(record.get("updated_at_source")),
        "merged_at_source": _safe_text(record.get("merged_at_source")),
        "evidence_refs": _safe_evidence_refs(record.get("evidence_refs")),
        "metadata": _safe_metadata(record.get("metadata")),
    }


async def _get_workspace_sync_job(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    sync_job_id: UUID,
) -> SyncJob | None:
    return await session.scalar(
        select(SyncJob)
        .where(SyncJob.workspace_id == workspace_id)
        .where(SyncJob.id == sync_job_id)
    )


def _validate_sync_job(sync_job: SyncJob) -> None:
    if sync_job.provider != INTEGRATION_PROVIDER_GITHUB:
        raise GitHubNormalizationError(GITHUB_NORMALIZATION_JOB_NOT_GITHUB)
    if sync_job.sync_type != SYNC_JOB_TYPE_MANUAL:
        raise GitHubNormalizationError(GITHUB_NORMALIZATION_JOB_NOT_MANUAL)
    if sync_job.status != SYNC_JOB_STATUS_QUEUED:
        raise GitHubNormalizationError(GITHUB_NORMALIZATION_JOB_NOT_QUEUED)


def _append_normalization_log(
    current_logs: list[dict[str, Any]] | None,
    *,
    counts: dict[str, int],
    persistence_counts: CanonicalRepositoryPersistenceCounts,
    persistence_mode: str,
    warnings: list[str],
    options: GitHubNormalizationOptions,
) -> list[dict[str, Any]]:
    logs = list(current_logs or [])
    logs.append(
        {
            "local_normalization": {
                "performed": True,
                "provider_sync_started": False,
                "persistence_mode": persistence_mode,
                "counts": counts,
                **_persistence_counts_payload(persistence_counts),
                "warnings": _dedupe_warnings(warnings),
                "include_repositories": options.include_repositories,
                "include_issues": options.include_issues,
                "include_pull_requests": options.include_pull_requests,
            }
        }
    )
    return logs


async def _persist_canonical_repositories(
    session: AsyncSession,
    *,
    sync_job: SyncJob,
    repositories: list[dict[str, Any]],
    observed_at: datetime,
) -> CanonicalRepositoryPersistenceCounts:
    source_records_created = 0
    source_records_updated = 0
    repositories_created = 0
    repositories_updated = 0

    for repo in repositories:
        external_id = _repository_external_id(repo)
        payload = _source_record_payload(repo)
        payload_hash = _stable_payload_hash(payload)
        source_updated_at = _parse_optional_datetime(repo.get("last_activity_at"))

        source_record = await session.scalar(
            select(SourceRecord)
            .where(SourceRecord.workspace_id == sync_job.workspace_id)
            .where(SourceRecord.provider == SOURCE_RECORD_PROVIDER_GITHUB)
            .where(SourceRecord.external_id == external_id)
        )
        if source_record is None:
            source_record = SourceRecord(
                workspace_id=sync_job.workspace_id,
                provider=SOURCE_RECORD_PROVIDER_GITHUB,
                external_id=external_id,
                record_type=SOURCE_RECORD_TYPE_REPOSITORY,
                payload=payload,
                payload_hash=payload_hash,
                observed_at=observed_at,
            )
            session.add(source_record)
            source_records_created += 1
        else:
            source_records_updated += 1

        source_record.connection_id = sync_job.connection_id
        source_record.record_type = SOURCE_RECORD_TYPE_REPOSITORY
        source_record.source_url = _safe_url(repo.get("source_url"))
        source_record.payload = payload
        source_record.payload_hash = payload_hash
        source_record.observed_at = observed_at
        source_record.source_updated_at = source_updated_at
        source_record.sync_job_id = sync_job.id
        source_record.is_deleted = False

        repository = await session.scalar(
            select(Repository)
            .where(Repository.workspace_id == sync_job.workspace_id)
            .where(Repository.external_id == external_id)
        )
        if repository is None:
            repository = Repository(
                workspace_id=sync_job.workspace_id,
                provider=SOURCE_RECORD_PROVIDER_GITHUB,
                external_id=external_id,
                name=_repository_name(repo),
                full_name=_repository_full_name(repo),
            )
            session.add(repository)
            repositories_created += 1
        else:
            repositories_updated += 1

        repository.provider = SOURCE_RECORD_PROVIDER_GITHUB
        repository.name = _repository_name(repo)
        repository.full_name = _repository_full_name(repo)
        repository.default_branch = _safe_text(repo.get("default_branch"))
        repository.visibility = _repository_visibility(repo.get("visibility"))
        repository.archived = bool(repo.get("archived"))
        repository.source_url = _safe_url(repo.get("source_url"))
        repository.last_activity_at = source_updated_at
        repository.repo_metadata = _repository_metadata(repo)

    return CanonicalRepositoryPersistenceCounts(
        source_records_created=source_records_created,
        source_records_updated=source_records_updated,
        repositories_created=repositories_created,
        repositories_updated=repositories_updated,
    )


def _persistence_counts_payload(
    counts: CanonicalRepositoryPersistenceCounts,
) -> dict[str, int]:
    return {
        "source_records_created": counts.source_records_created,
        "source_records_updated": counts.source_records_updated,
        "repositories_created": counts.repositories_created,
        "repositories_updated": counts.repositories_updated,
    }


def _source_record_payload(repo: Mapping[str, Any]) -> dict[str, Any]:
    return _sanitize_payload(
        {
            "record_type": SOURCE_RECORD_TYPE_REPOSITORY,
            "normalized_repository": dict(repo),
            "evidence_refs": repo.get("evidence_refs") or [],
        }
    )


def _repository_metadata(repo: Mapping[str, Any]) -> dict[str, Any]:
    return _sanitize_payload(
        {
            "source": repo.get("source"),
            "evidence_refs": repo.get("evidence_refs") or [],
            "metadata": repo.get("metadata") or {},
        }
    )


def _repository_external_id(repo: Mapping[str, Any]) -> str:
    return (
        _safe_text(repo.get("external_id"))
        or _safe_text(repo.get("full_name"))
        or _safe_text(repo.get("name"))
        or "unknown"
    )


def _repository_name(repo: Mapping[str, Any]) -> str:
    full_name = _repository_full_name(repo)
    return _safe_text(repo.get("name")) or full_name.rsplit("/", 1)[-1] or "unknown"


def _repository_full_name(repo: Mapping[str, Any]) -> str:
    return _safe_text(repo.get("full_name")) or _safe_text(repo.get("name")) or "unknown"


def _repository_visibility(value: Any) -> str | None:
    text = _safe_text(value)
    return text if text in {"public", "private", "internal"} else None


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
    return str(value)[:1000]


def _safe_text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _safe_visibility(value: Any) -> str:
    text = _safe_text(value)
    return text if text in {"public", "private", "internal", "unknown"} else "unknown"


def _safe_source(value: Any) -> str:
    text = _safe_text(value)
    if text in {"repo_audit", "repository_inventory", "source_control", "github_connector"}:
        return text
    return "unknown"


def _safe_url(value: Any) -> str | None:
    text = _safe_text(value)
    if text and "@" not in text:
        return text[:1000]
    return None


def _safe_evidence_refs(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    refs: list[dict[str, Any]] = []
    for item in value[:20]:
        if not isinstance(item, Mapping):
            continue
        ref = {
            "kind": _safe_text(item.get("kind")) or "source_event",
            "source": _safe_text(item.get("source")) or "unknown",
            "ref": _safe_text(item.get("ref")),
            "url": _safe_url(item.get("url")),
        }
        if ref["ref"]:
            refs.append(ref)
    return refs


def _safe_metadata(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    safe: dict[str, Any] = {}
    for key, raw in value.items():
        if not isinstance(key, str) or _metadata_key_is_sensitive(key):
            continue
        if isinstance(raw, str):
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


def _dedupe_warnings(warnings: list[str]) -> list[str]:
    deduped: list[str] = []
    for warning in warnings:
        if warning and warning not in deduped:
            deduped.append(warning)
    return deduped
