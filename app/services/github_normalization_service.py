from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any
from uuid import UUID

from sqlalchemy import func, literal_column, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

import app.services.github_repository_read_service as github_repository_read_service
from app.db.canonical_models import (
    PULL_REQUEST_STATE_CLOSED,
    PULL_REQUEST_STATE_MERGED,
    PULL_REQUEST_STATE_OPEN,
    SOURCE_RECORD_PROVIDER_GITHUB,
    TASK_PROVIDER_GITHUB,
    PullRequest,
    Repository,
    SourceRecord,
    Task,
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
SOURCE_RECORD_TYPE_ISSUE = "issue"
SOURCE_RECORD_TYPE_PULL_REQUEST = "pull_request"

GITHUB_NORMALIZATION_CANONICAL_WARNING = (
    "GitHub normalization persisted supported records to canonical tables."
)

_SAFE_REPO_PART_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


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


@dataclass
class CanonicalGitHubPersistenceCounts:
    source_records_created: int = 0
    source_records_updated: int = 0
    repositories_created: int = 0
    repositories_updated: int = 0
    tasks_created: int = 0
    tasks_updated: int = 0
    pull_requests_created: int = 0
    pull_requests_updated: int = 0

    @property
    def records_created(self) -> int:
        return self.repositories_created + self.tasks_created + self.pull_requests_created

    @property
    def records_updated(self) -> int:
        return self.repositories_updated + self.tasks_updated + self.pull_requests_updated


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
    local_records = _local_github_records(sync_job)
    repositories: list[dict[str, Any]] = []
    if options.include_repositories:
        local_repositories = local_records["repositories"]
        if local_repositories:
            repositories = [
                build_normalized_repository(repository)
                for repository in local_repositories
            ]
        else:
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
        issues = [
            build_normalized_issue(record)
            for record in local_records["issues"]
            if _is_issue_record(record)
        ]
        if not issues:
            warnings.append(GITHUB_NORMALIZATION_ISSUES_UNAVAILABLE_WARNING)
    if options.include_pull_requests:
        pull_requests = [
            build_normalized_pull_request(record)
            for record in local_records["pull_requests"]
        ]
        if not pull_requests:
            warnings.append(GITHUB_NORMALIZATION_PULL_REQUESTS_UNAVAILABLE_WARNING)

    counts = {
        "repositories": len(repositories),
        "issues": len(issues),
        "pull_requests": len(pull_requests),
    }
    persistence_counts = CanonicalGitHubPersistenceCounts()
    if options.persist_if_supported:
        persistence_counts = await _persist_canonical_github_records(
            session,
            sync_job=sync_job,
            repositories=repositories,
            issues=issues,
            pull_requests=pull_requests,
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
    sync_job.records_created = persistence_counts.records_created
    sync_job.records_updated = persistence_counts.records_updated
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
    repository_full_name = _record_repository_full_name(record)
    number = _safe_int(record.get("number"))
    source_url = _work_item_source_url(record)
    external_id = _work_item_external_id(
        record,
        repository_full_name=repository_full_name,
        kind="issue",
        number=number,
        source_url=source_url,
    )
    metadata = _work_item_metadata(
        record,
        kind="issue",
        repository_full_name=repository_full_name,
        number=number,
    )
    return {
        "entity_type": "task",
        "provider": INTEGRATION_PROVIDER_GITHUB,
        "external_id": external_id,
        "number": number,
        "title": _safe_title(record.get("title"), f"GitHub issue {number or external_id}"),
        "state": _issue_state(record.get("state")),
        "source_url": source_url,
        "repository_full_name": repository_full_name,
        "created_at_source": _source_datetime_text(record, "created"),
        "updated_at_source": _source_datetime_text(record, "updated"),
        "evidence_refs": _work_item_evidence_refs(
            record,
            kind="github_issue",
            external_id=external_id,
            source_url=source_url,
        ),
        "metadata": metadata,
    }


def build_normalized_pull_request(record: Mapping[str, Any]) -> dict[str, Any]:
    repository_full_name = _record_repository_full_name(record)
    number = _safe_int(record.get("number"))
    source_url = _work_item_source_url(record)
    external_id = _work_item_external_id(
        record,
        repository_full_name=repository_full_name,
        kind="pull",
        number=number,
        source_url=source_url,
    )
    state = _pull_request_state(record)
    metadata = _work_item_metadata(
        record,
        kind="pull_request",
        repository_full_name=repository_full_name,
        number=number,
    )
    return {
        "entity_type": "pull_request",
        "provider": INTEGRATION_PROVIDER_GITHUB,
        "external_id": external_id,
        "number": number,
        "title": _safe_title(record.get("title"), f"GitHub PR {number or external_id}"),
        "state": state,
        "source_url": source_url,
        "repository_full_name": repository_full_name,
        "created_at_source": _source_datetime_text(record, "created"),
        "updated_at_source": _source_datetime_text(record, "updated"),
        "merged_at_source": _source_datetime_text(record, "merged"),
        "evidence_refs": _work_item_evidence_refs(
            record,
            kind="github_pull_request",
            external_id=external_id,
            source_url=source_url,
        ),
        "metadata": metadata,
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
    persistence_counts: CanonicalGitHubPersistenceCounts,
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


async def _persist_canonical_github_records(
    session: AsyncSession,
    *,
    sync_job: SyncJob,
    repositories: list[dict[str, Any]],
    issues: list[dict[str, Any]],
    pull_requests: list[dict[str, Any]],
    observed_at: datetime,
) -> CanonicalGitHubPersistenceCounts:
    counts = CanonicalGitHubPersistenceCounts()

    for repo in repositories:
        external_id = _repository_external_id(repo)
        source_record, created = await _upsert_source_record(
            session,
            sync_job=sync_job,
            external_id=external_id,
            record_type=SOURCE_RECORD_TYPE_REPOSITORY,
            payload=_source_record_payload(
                record_type=SOURCE_RECORD_TYPE_REPOSITORY,
                normalized_key="normalized_repository",
                record=repo,
            ),
            source_url=_safe_url(repo.get("source_url")),
            source_updated_at=_parse_optional_datetime(repo.get("last_activity_at")),
            observed_at=observed_at,
        )
        _ = source_record
        if created:
            counts.source_records_created += 1
        else:
            counts.source_records_updated += 1
        _, repository_created = await _upsert_repository(
            session,
            sync_job=sync_job,
            repo=repo,
            external_id=external_id,
        )
        if repository_created:
            counts.repositories_created += 1
        else:
            counts.repositories_updated += 1

    for issue in issues:
        external_id = _work_item_external_id_from_normalized(issue)
        source_updated_at = _parse_optional_datetime(issue.get("updated_at_source"))
        source_record, created = await _upsert_source_record(
            session,
            sync_job=sync_job,
            external_id=external_id,
            record_type=SOURCE_RECORD_TYPE_ISSUE,
            payload=_source_record_payload(
                record_type=SOURCE_RECORD_TYPE_ISSUE,
                normalized_key="normalized_issue",
                record=issue,
            ),
            source_url=_safe_url(issue.get("source_url")),
            source_updated_at=source_updated_at,
            observed_at=observed_at,
        )
        if created:
            counts.source_records_created += 1
        else:
            counts.source_records_updated += 1
        task_created = await _upsert_github_issue_task(
            session,
            sync_job=sync_job,
            issue=issue,
            source_record=source_record,
            source_updated_at=source_updated_at,
        )
        if task_created:
            counts.tasks_created += 1
        else:
            counts.tasks_updated += 1

    for pull_request in pull_requests:
        repository, repository_created = await _ensure_repository_for_work_item(
            session,
            sync_job=sync_job,
            record=pull_request,
        )
        if repository_created:
            counts.repositories_created += 1
        external_id = _work_item_external_id_from_normalized(pull_request)
        source_updated_at = _parse_optional_datetime(pull_request.get("updated_at_source"))
        source_record, created = await _upsert_source_record(
            session,
            sync_job=sync_job,
            external_id=external_id,
            record_type=SOURCE_RECORD_TYPE_PULL_REQUEST,
            payload=_source_record_payload(
                record_type=SOURCE_RECORD_TYPE_PULL_REQUEST,
                normalized_key="normalized_pull_request",
                record=pull_request,
            ),
            source_url=_safe_url(pull_request.get("source_url")),
            source_updated_at=source_updated_at,
            observed_at=observed_at,
        )
        if created:
            counts.source_records_created += 1
        else:
            counts.source_records_updated += 1
        pull_request_created = await _upsert_pull_request(
            session,
            sync_job=sync_job,
            pull_request=pull_request,
            repository=repository,
        )
        if pull_request_created:
            counts.pull_requests_created += 1
        else:
            counts.pull_requests_updated += 1

    return counts


def _persistence_counts_payload(
    counts: CanonicalGitHubPersistenceCounts,
) -> dict[str, int]:
    return {
        "source_records_created": counts.source_records_created,
        "source_records_updated": counts.source_records_updated,
        "repositories_created": counts.repositories_created,
        "repositories_updated": counts.repositories_updated,
        "tasks_created": counts.tasks_created,
        "tasks_updated": counts.tasks_updated,
        "pull_requests_created": counts.pull_requests_created,
        "pull_requests_updated": counts.pull_requests_updated,
    }


async def _upsert_source_record(
    session: AsyncSession,
    *,
    sync_job: SyncJob,
    external_id: str,
    record_type: str,
    payload: dict[str, Any],
    source_url: str | None,
    source_updated_at: datetime | None,
    observed_at: datetime,
) -> tuple[SourceRecord, bool]:
    payload_hash = _stable_payload_hash(payload)

    # Idempotent, concurrency-safe upsert on the canonical SourceRecord identity
    # (workspace_id, provider, external_id), backed by the existing unique
    # constraint uq_source_records_workspace_provider_external_id. Two concurrent
    # syncs for the same object converge to one row with no IntegrityError. The
    # row is read back so callers keep receiving a real ORM SourceRecord, and
    # RETURNING (xmax = 0) preserves the created/updated counters.
    mutable = {
        SourceRecord.connection_id: sync_job.connection_id,
        SourceRecord.record_type: record_type,
        SourceRecord.source_url: source_url,
        SourceRecord.payload: payload,
        SourceRecord.payload_hash: payload_hash,
        SourceRecord.observed_at: observed_at,
        SourceRecord.source_updated_at: source_updated_at,
        SourceRecord.sync_job_id: sync_job.id,
        SourceRecord.is_deleted: False,
    }
    statement = (
        pg_insert(SourceRecord)
        .values(
            {
                SourceRecord.workspace_id: sync_job.workspace_id,
                SourceRecord.provider: SOURCE_RECORD_PROVIDER_GITHUB,
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
    source_record = await session.get(
        SourceRecord, row[0], populate_existing=True
    )
    return source_record, bool(row[1])


async def _upsert_repository(
    session: AsyncSession,
    *,
    sync_job: SyncJob,
    repo: Mapping[str, Any],
    external_id: str,
) -> tuple[Repository, bool]:
    full_name = _repository_full_name(repo)

    mutable = {
        Repository.provider: SOURCE_RECORD_PROVIDER_GITHUB,
        Repository.external_id: external_id,
        Repository.name: _repository_name(repo),
        Repository.full_name: full_name,
        Repository.default_branch: _safe_text(repo.get("default_branch")),
        Repository.visibility: _repository_visibility(repo.get("visibility")),
        Repository.archived: bool(repo.get("archived")),
        Repository.source_url: _safe_url(repo.get("source_url")),
        Repository.last_activity_at: _parse_optional_datetime(repo.get("last_activity_at")),
        Repository.repo_metadata: _repository_metadata(repo),
        Repository.updated_at: func.now(),
    }

    # Cross-path dedup (load-bearing): the main sync keys external_id on the
    # GitHub numeric id (build_normalized_repository) while the work-item path
    # initially keys it on full_name. The database now has guards for both
    # identities:
    #   * uq_repositories_workspace_external_id
    #   * uq_repositories_workspace_provider_full_name
    #
    # ``ON CONFLICT DO NOTHING`` deliberately has no explicit target, so either
    # unique guard can catch a concurrent insert. If a conflict happened, read
    # the canonical row by either identity and update in place. This avoids an
    # IntegrityError when live polling/webhook paths race across identities.
    statement = (
        pg_insert(Repository)
        .values({Repository.workspace_id: sync_job.workspace_id, **mutable})
        .on_conflict_do_nothing()
        .returning(Repository.id)
    )
    inserted = (await session.execute(statement)).first()
    if inserted is not None:
        repository = await session.get(
            Repository, inserted[0], populate_existing=True
        )
        return repository, True

    existing = await session.scalar(
        select(Repository)
        .where(Repository.workspace_id == sync_job.workspace_id)
        .where(Repository.provider == SOURCE_RECORD_PROVIDER_GITHUB)
        .where(
            or_(
                Repository.external_id == external_id,
                Repository.full_name == full_name,
            )
        )
        .order_by(
            (Repository.full_name == full_name).desc(),
            (Repository.external_id == external_id).desc(),
            Repository.updated_at.desc().nulls_last(),
            Repository.created_at.desc().nulls_last(),
            Repository.id.desc(),
        )
    )
    if existing is None:
        raise GitHubNormalizationError(
            "repository upsert conflict could not be resolved"
        )

    update_values = dict(mutable)
    if external_id == full_name:
        # Work-item-created repository records use full_name as a temporary
        # external_id on insert. Once a later main sync has learned the stable
        # GitHub id, any concurrent/subsequent work-item update must not
        # downgrade it back to full_name. Removing this field for every
        # work-item update also avoids a stale pre-upgrade read racing after the
        # stable-id update.
        update_values.pop(Repository.external_id, None)

    await session.execute(
        update(Repository).where(Repository.id == existing.id).values(update_values)
    )
    repository = await session.get(Repository, existing.id, populate_existing=True)
    return repository, False


async def _ensure_repository_for_work_item(
    session: AsyncSession,
    *,
    sync_job: SyncJob,
    record: Mapping[str, Any],
) -> tuple[Repository, bool]:
    repository_full_name = _safe_text(record.get("repository_full_name")) or "unknown"
    repository = await session.scalar(
        select(Repository)
        .where(Repository.workspace_id == sync_job.workspace_id)
        .where(Repository.full_name == repository_full_name)
    )
    if repository is not None:
        return repository, False

    repo = {
        "external_id": repository_full_name,
        "name": repository_full_name.rsplit("/", 1)[-1],
        "full_name": repository_full_name,
        "visibility": "private",
        "source_url": _repository_url_from_full_name(repository_full_name),
        "metadata": {
            "source": "github_normalization_work_item",
            "created_from_work_item": True,
        },
    }
    return await _upsert_repository(
        session,
        sync_job=sync_job,
        repo=repo,
        external_id=repository_full_name,
    )


async def _upsert_github_issue_task(
    session: AsyncSession,
    *,
    sync_job: SyncJob,
    issue: Mapping[str, Any],
    source_record: SourceRecord,
    source_updated_at: datetime | None,
) -> bool:
    external_id = _work_item_external_id_from_normalized(issue)

    # Idempotent, concurrency-safe upsert keyed on the canonical Task identity
    # (workspace_id, source_provider, external_id), backed by the partial unique
    # index uq_tasks_workspace_provider_external_id. INSERT ... ON CONFLICT DO
    # UPDATE means two concurrent syncs for the same issue converge to exactly
    # one row with no IntegrityError. RETURNING (xmax = 0) is true for an insert
    # and false for an update, preserving the created/updated count semantics.
    mutable = {
        Task.source_record_id: source_record.id,
        Task.title: _safe_title(issue.get("title"), f"GitHub issue {external_id}"),
        Task.description: _safe_text(issue.get("description")),
        Task.status: _issue_state(issue.get("state")),
        Task.source_url: _safe_url(issue.get("source_url")),
        Task.source_updated_at: source_updated_at,
        Task.task_metadata: _task_metadata(issue),
    }
    statement = (
        pg_insert(Task)
        .values(
            {
                Task.workspace_id: sync_job.workspace_id,
                Task.source_provider: TASK_PROVIDER_GITHUB,
                Task.external_id: external_id,
                **mutable,
            }
        )
        .on_conflict_do_update(
            index_elements=["workspace_id", "source_provider", "external_id"],
            index_where=Task.external_id.isnot(None),
            # updated_at is a "last synced" marker (see Task.updated_at): bumped
            # on every sync by design. User-facing recency uses source_updated_at,
            # so no consumer needs content-change semantics here.
            set_={**mutable, Task.updated_at: func.now()},
        )
        .returning(literal_column("(xmax = 0)"))
    )
    result = await session.execute(statement)
    return bool(result.scalar_one())


async def _upsert_pull_request(
    session: AsyncSession,
    *,
    sync_job: SyncJob,
    pull_request: Mapping[str, Any],
    repository: Repository,
) -> bool:
    external_id = _work_item_external_id_from_normalized(pull_request)

    # Idempotent, concurrency-safe upsert on the canonical PullRequest identity
    # (workspace_id, external_id), backed by the existing unique constraint
    # uq_pull_requests_workspace_external_id. Two concurrent syncs for the same
    # PR converge to one row with no IntegrityError; RETURNING (xmax = 0)
    # preserves the created/updated counters.
    mutable = {
        PullRequest.repository_id: repository.id,
        PullRequest.number: int(pull_request.get("number") or 0),
        PullRequest.title: _safe_title(pull_request.get("title"), f"GitHub PR {external_id}"),
        PullRequest.state: _pull_request_state(pull_request),
        PullRequest.source_url: _safe_url(pull_request.get("source_url")),
        PullRequest.created_at_source: _parse_optional_datetime(
            pull_request.get("created_at_source")
        ),
        PullRequest.updated_at_source: _parse_optional_datetime(
            pull_request.get("updated_at_source")
        ),
        PullRequest.merged_at_source: _parse_optional_datetime(
            pull_request.get("merged_at_source")
        ),
        PullRequest.pr_metadata: _pull_request_metadata(pull_request),
    }
    statement = (
        pg_insert(PullRequest)
        .values(
            {
                PullRequest.workspace_id: sync_job.workspace_id,
                PullRequest.external_id: external_id,
                **mutable,
            }
        )
        .on_conflict_do_update(
            constraint="uq_pull_requests_workspace_external_id",
            set_=mutable,
        )
        .returning(literal_column("(xmax = 0)"))
    )
    result = await session.execute(statement)
    return bool(result.scalar_one())


def _source_record_payload(
    *,
    record_type: str,
    normalized_key: str,
    record: Mapping[str, Any],
) -> dict[str, Any]:
    return _sanitize_payload(
        {
            "record_type": record_type,
            normalized_key: dict(record),
            "evidence_refs": record.get("evidence_refs") or [],
        }
    )


def _local_github_records(sync_job: SyncJob) -> dict[str, list[Mapping[str, Any]]]:
    cursor = sync_job.cursor_before if isinstance(sync_job.cursor_before, Mapping) else {}
    local = cursor.get("local_github") if isinstance(cursor.get("local_github"), Mapping) else {}
    github = cursor.get("github") if isinstance(cursor.get("github"), Mapping) else {}
    candidates = (local, github, cursor)
    return {
        "repositories": _first_record_list(
            candidates,
            "repositories",
            "github_repositories",
        ),
        "issues": _first_record_list(candidates, "issues", "github_issues"),
        "pull_requests": _first_record_list(
            candidates,
            "pull_requests",
            "prs",
            "github_pull_requests",
        ),
    }


def _first_record_list(
    candidates: tuple[Mapping[str, Any], ...],
    *keys: str,
) -> list[Mapping[str, Any]]:
    for candidate in candidates:
        for key in keys:
            value = candidate.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, Mapping)]
    return []


def _is_issue_record(record: Mapping[str, Any]) -> bool:
    if record.get("pull_request") is not None:
        return False
    entity_type = _safe_text(record.get("entity_type"))
    if entity_type == "pull_request":
        return False
    return True


def _record_repository_full_name(record: Mapping[str, Any]) -> str | None:
    repository = record.get("repository")
    candidates: list[Any] = [
        record.get("repository_full_name"),
        record.get("full_name"),
        record.get("repository_name"),
        record.get("source_url"),
        record.get("html_url"),
        record.get("web_url"),
        record.get("url"),
    ]
    if isinstance(repository, Mapping):
        candidates.extend(
            [
                repository.get("full_name"),
                repository.get("name_with_owner"),
                repository.get("html_url"),
                repository.get("url"),
            ]
        )
    for candidate in candidates:
        full_name = _safe_full_name(candidate) or _github_full_name_from_url(candidate)
        if full_name:
            return full_name
    return None


def _work_item_source_url(record: Mapping[str, Any]) -> str | None:
    for key in ("source_url", "html_url", "web_url", "url"):
        url = _safe_url(record.get(key))
        if url:
            return url
    return None


def _work_item_external_id(
    record: Mapping[str, Any],
    *,
    repository_full_name: str | None,
    kind: str,
    number: int | None,
    source_url: str | None,
) -> str:
    explicit = _safe_text(record.get("external_id"), limit=255) or _safe_text(
        record.get("id"),
        limit=255,
    )
    if explicit and explicit != "unknown":
        return explicit
    if repository_full_name and number is not None:
        return f"{repository_full_name}#{kind}/{number}"[:255]
    return (source_url or f"unknown-github-{kind}")[:255]


def _work_item_external_id_from_normalized(record: Mapping[str, Any]) -> str:
    return _safe_text(record.get("external_id"), limit=255) or "unknown"


def _work_item_metadata(
    record: Mapping[str, Any],
    *,
    kind: str,
    repository_full_name: str | None,
    number: int | None,
) -> dict[str, Any]:
    metadata = _safe_metadata(record.get("metadata"))
    metadata.update(
        {
            "github_object_type": kind,
            "repository_full_name": repository_full_name,
            "repository_external_id": repository_full_name,
            "number": number,
        }
    )
    return _sanitize_payload(metadata)


def _task_metadata(issue: Mapping[str, Any]) -> dict[str, Any]:
    metadata = _safe_metadata(issue.get("metadata"))
    metadata.update(
        {
            "github_object_type": "issue",
            "repository_full_name": _safe_text(issue.get("repository_full_name")),
            "repository_external_id": _safe_text(issue.get("repository_full_name")),
            "number": issue.get("number") if isinstance(issue.get("number"), int) else None,
            "evidence_refs": issue.get("evidence_refs") or [],
        }
    )
    return _sanitize_payload(metadata)


def _pull_request_metadata(pull_request: Mapping[str, Any]) -> dict[str, Any]:
    metadata = _safe_metadata(pull_request.get("metadata"))
    metadata.update(
        {
            "github_object_type": "pull_request",
            "repository_full_name": _safe_text(pull_request.get("repository_full_name")),
            "repository_external_id": _safe_text(pull_request.get("repository_full_name")),
            "number": (
                pull_request.get("number")
                if isinstance(pull_request.get("number"), int)
                else None
            ),
            "evidence_refs": pull_request.get("evidence_refs") or [],
        }
    )
    return _sanitize_payload(metadata)


def _work_item_evidence_refs(
    record: Mapping[str, Any],
    *,
    kind: str,
    external_id: str,
    source_url: str | None,
) -> list[dict[str, Any]]:
    refs = _safe_evidence_refs(record.get("evidence_refs"))
    if refs:
        return refs
    return [
        {
            "kind": kind,
            "source": SOURCE_RECORD_PROVIDER_GITHUB,
            "ref": external_id,
            "url": source_url,
        }
    ]


def _source_datetime_text(record: Mapping[str, Any], prefix: str) -> str | None:
    for key in (f"{prefix}_at_source", f"{prefix}_at", f"{prefix}At"):
        text = _safe_text(record.get(key))
        if text:
            return text
    return None


def _issue_state(value: Any) -> str | None:
    text = _safe_text(value)
    if text is None:
        return None
    normalized = text.casefold()
    if normalized in {"open", "closed"}:
        return normalized
    return None


def _pull_request_state(record: Mapping[str, Any]) -> str:
    if _safe_text(record.get("merged_at_source")) or _safe_text(record.get("merged_at")):
        return PULL_REQUEST_STATE_MERGED
    if record.get("merged") is True:
        return PULL_REQUEST_STATE_MERGED
    text = _safe_text(record.get("state"))
    if text is None:
        return PULL_REQUEST_STATE_OPEN
    normalized = text.casefold()
    if normalized in {
        PULL_REQUEST_STATE_OPEN,
        PULL_REQUEST_STATE_CLOSED,
        PULL_REQUEST_STATE_MERGED,
    }:
        return normalized
    return PULL_REQUEST_STATE_OPEN


def _safe_int(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _safe_full_name(value: Any) -> str | None:
    text = _safe_text(value)
    if not text:
        return None
    parts = text.removesuffix(".git").split("/")
    if len(parts) != 2:
        return None
    owner = _safe_repo_part(parts[0])
    repo = _safe_repo_part(parts[1])
    if owner and repo:
        return f"{owner}/{repo}"
    return None


def _github_full_name_from_url(value: Any) -> str | None:
    text = _safe_text(value)
    if not text or "github.com" not in text:
        return None
    marker = "github.com/"
    if marker not in text:
        return None
    path = text.split(marker, 1)[1].split("?", 1)[0].split("#", 1)[0]
    parts = path.strip("/").split("/")
    if len(parts) < 2:
        return None
    owner = _safe_repo_part(parts[0])
    repo = _safe_repo_part(parts[1])
    if owner and repo:
        return f"{owner}/{repo}"
    return None


def _repository_url_from_full_name(full_name: str) -> str | None:
    safe = _safe_full_name(full_name)
    return f"https://github.com/{safe}" if safe else None


def _safe_repo_part(value: Any) -> str | None:
    text = _safe_text(value)
    if not text:
        return None
    text = text.removesuffix(".git")
    if "/" in text or not _SAFE_REPO_PART_RE.match(text):
        return None
    return text


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
        _safe_text(repo.get("external_id"), limit=255)
        or _safe_text(repo.get("full_name"), limit=255)
        or _safe_text(repo.get("name"), limit=255)
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


def _safe_text(value: Any, *, limit: int = 1000) -> str | None:
    return value.strip()[:limit] if isinstance(value, str) and value.strip() else None


def _safe_title(value: Any, fallback: str) -> str:
    return (_safe_text(value, limit=500) or fallback)[:500]


def _safe_visibility(value: Any) -> str:
    text = _safe_text(value)
    return text if text in {"public", "private", "internal", "unknown"} else "unknown"


def _safe_source(value: Any) -> str:
    text = _safe_text(value)
    if text in {
        "repo_audit",
        "repository_inventory",
        "source_control",
        "github_connector",
        "selected_repository_issue_sync",
        "selected_repository_pr_sync",
    }:
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
