"""Authoritative, content-free reconciliation for canonical source records."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.canonical_models import (
    SOURCE_RECORD_PROVIDER_GITHUB,
    SourceRecord,
)
from app.db.integration_models import INTEGRATION_PROVIDER_GITHUB, SyncJob
from app.db.memory_models import COMPANY_MEMORY_EVENT_SOURCE_RECORD_DISAPPEARED
from app.services.company_memory_event_service import (
    append_source_record_lifecycle_memory_event,
)


SOURCE_RECONCILIATION_VERSION = "source-reconciliation.v1"
SOURCE_RECONCILIATION_TOMBSTONE_REASON = (
    "missing_from_complete_github_repository_snapshot"
)
_SUPPORTED_RECORD_TYPES = frozenset({"issue", "pull_request"})
_NORMALIZED_PAYLOAD_KEYS = {
    "issue": "normalized_issue",
    "pull_request": "normalized_pull_request",
}


@dataclass(frozen=True)
class SourceReconciliationResult:
    record_type: str
    scopes_reconciled: int
    records_scanned: int
    records_tombstoned: int

    def as_payload(self) -> dict[str, Any]:
        return {
            "version": SOURCE_RECONCILIATION_VERSION,
            "record_type": self.record_type,
            "scopes_reconciled": self.scopes_reconciled,
            "records_scanned": self.records_scanned,
            "records_tombstoned": self.records_tombstoned,
        }


async def reconcile_authoritative_github_records(
    session: AsyncSession,
    *,
    sync_job: SyncJob,
    record_type: str,
    repository_full_names: Sequence[str],
    observed_records: Sequence[Mapping[str, Any]],
    snapshot_observed_at: datetime,
) -> SourceReconciliationResult:
    """Tombstone records absent from complete, server-attested repository scopes.

    Callers must only provide scopes obtained from a successful, fully paginated
    provider read. Partial imports and client-authored SyncJob metadata never
    enter this function.
    """

    _validate_inputs(
        sync_job=sync_job,
        record_type=record_type,
        snapshot_observed_at=snapshot_observed_at,
    )
    repositories = _normalized_repositories(repository_full_names)
    observed_by_repository = _observed_external_ids(
        observed_records,
        repositories=repositories,
    )
    normalized_key = _NORMALIZED_PAYLOAD_KEYS[record_type]
    snapshot_time = snapshot_observed_at.astimezone(timezone.utc)
    tombstoned_at = datetime.now(timezone.utc)
    records_scanned = 0
    tombstoned: list[SourceRecord] = []

    for repository_key, repository_full_name in repositories.items():
        repository_path = SourceRecord.payload[normalized_key][
            "repository_full_name"
        ].as_string()
        rows = list(
            (
                await session.execute(
                    select(SourceRecord)
                    .where(
                        SourceRecord.workspace_id == sync_job.workspace_id,
                        SourceRecord.provider == SOURCE_RECORD_PROVIDER_GITHUB,
                        SourceRecord.record_type == record_type,
                        SourceRecord.is_deleted.is_(False),
                        SourceRecord.observed_at <= snapshot_time,
                        func.lower(repository_path) == repository_key,
                    )
                    .order_by(SourceRecord.id.asc())
                    .with_for_update()
                )
            ).scalars()
        )
        records_scanned += len(rows)
        observed_external_ids = observed_by_repository.get(repository_key, set())
        for source_record in rows:
            if source_record.external_id in observed_external_ids:
                continue
            source_record.is_deleted = True
            source_record.tombstoned_at = tombstoned_at
            source_record.tombstone_observed_at = snapshot_time
            source_record.tombstone_sync_job_id = sync_job.id
            source_record.tombstone_reason = SOURCE_RECONCILIATION_TOMBSTONE_REASON
            tombstoned.append(source_record)

    if tombstoned:
        await session.flush()
        for source_record in tombstoned:
            await append_source_record_lifecycle_memory_event(
                session,
                source_record=source_record,
                sync_job_id=sync_job.id,
                event_type=COMPANY_MEMORY_EVENT_SOURCE_RECORD_DISAPPEARED,
                occurred_at=snapshot_time,
            )

    return SourceReconciliationResult(
        record_type=record_type,
        scopes_reconciled=len(repositories),
        records_scanned=records_scanned,
        records_tombstoned=len(tombstoned),
    )


def _validate_inputs(
    *,
    sync_job: SyncJob,
    record_type: str,
    snapshot_observed_at: datetime,
) -> None:
    if sync_job.provider != INTEGRATION_PROVIDER_GITHUB:
        raise ValueError("github sync job required for source reconciliation")
    if record_type not in _SUPPORTED_RECORD_TYPES:
        raise ValueError("unsupported source reconciliation record type")
    if snapshot_observed_at.tzinfo is None:
        raise ValueError("source reconciliation snapshot time must be timezone-aware")


def _normalized_repositories(
    repository_full_names: Sequence[str],
) -> dict[str, str]:
    repositories: dict[str, str] = {}
    for value in repository_full_names:
        if not isinstance(value, str):
            raise ValueError("source reconciliation repository scope is invalid")
        normalized = value.strip()
        if normalized.count("/") != 1:
            raise ValueError("source reconciliation repository scope is invalid")
        repositories.setdefault(normalized.casefold(), normalized)
    if not repositories:
        raise ValueError("source reconciliation requires a repository scope")
    return dict(sorted(repositories.items()))


def _observed_external_ids(
    observed_records: Sequence[Mapping[str, Any]],
    *,
    repositories: Mapping[str, str],
) -> dict[str, set[str]]:
    observed = {repository: set() for repository in repositories}
    for record in observed_records:
        repository_full_name = record.get("repository_full_name")
        external_id = record.get("external_id")
        if not isinstance(repository_full_name, str) or not isinstance(
            external_id, str
        ):
            continue
        repository_key = repository_full_name.strip().casefold()
        if repository_key in observed and external_id:
            observed[repository_key].add(external_id)
    return observed
