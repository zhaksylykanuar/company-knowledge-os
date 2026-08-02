"""Durable RI-006 jobs, runs, reconciliation, evidence, and retention.

The service persists only strict Repository Intelligence contracts and
sanitized artifact descriptors. It never reads a repository, executes target
code, calls a provider, writes an external artifact, or invokes an LLM.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import re
from typing import Annotated, Any, Literal, Self
from uuid import UUID, uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationInfo,
    field_validator,
    model_validator,
)
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.canonical_models import (
    SOURCE_RECORD_PROVIDER_INTERNAL,
    EvidenceRef,
    Repository,
    SourceRecord,
)
from app.db.identity_models import (
    MEMBERSHIP_ROLE_ADMIN,
    MEMBERSHIP_ROLE_OWNER,
    Membership,
)
from app.db.repository_intelligence_models import (
    REPOSITORY_ANALYSIS_JOB_STATUS_CANCELLED,
    REPOSITORY_ANALYSIS_JOB_STATUS_FAILED,
    REPOSITORY_ANALYSIS_JOB_STATUS_PARTIAL,
    REPOSITORY_ANALYSIS_JOB_STATUS_QUEUED,
    REPOSITORY_ANALYSIS_JOB_STATUS_RUNNING,
    REPOSITORY_ANALYSIS_JOB_STATUS_SUCCEEDED,
    REPOSITORY_AUDIT_RUN_STATUS_PARTIAL,
    REPOSITORY_AUDIT_RUN_STATUS_SUCCEEDED,
    REPOSITORY_CONTRADICTION_STATUS_CURRENT,
    REPOSITORY_CONTRADICTION_STATUS_RESOLVED,
    REPOSITORY_COVERAGE_STATUS_COMPLETE,
    REPOSITORY_COVERAGE_STATUS_PARTIAL,
    REPOSITORY_EVIDENCE_ROLE_CONTRADICTING,
    REPOSITORY_EVIDENCE_ROLE_SUPPORTING,
    REPOSITORY_FINDING_STATUS_ACCEPTED_RISK,
    REPOSITORY_FINDING_STATUS_FALSE_POSITIVE,
    REPOSITORY_FINDING_STATUS_NEW,
    REPOSITORY_FINDING_STATUS_REGRESSED,
    REPOSITORY_FINDING_STATUS_RESOLVED,
    REPOSITORY_LIFECYCLE_STATUS_CURRENT,
    REPOSITORY_LIFECYCLE_STATUS_STALE,
    RepositoryAnalysisJob,
    RepositoryAuditFinding,
    RepositoryAuditRun,
    RepositoryContradiction,
    RepositoryEvidenceLink,
    RepositoryFact,
    RepositoryRelationshipRecord,
)
from app.services.repository_intelligence.contracts import (
    AnalysisTargetV1,
    EvidenceRefV1,
    RepositoryClaimV1,
    RepositoryContradictionV1,
    RepositoryFindingV1,
    RepositoryIntelligenceV1,
    RepositoryRelationshipV1,
)
from app.services.repository_intelligence.taxonomy import (
    AnalyzerClaimStatus,
    AuditLevel,
    FindingLifecycleStatus,
)


REPOSITORY_INTELLIGENCE_RUN_RECORD_TYPE = "repository_intelligence_run"
REPOSITORY_INTELLIGENCE_RUN_MANIFEST_VERSION = (
    "repository_intelligence_run_manifest.v1"
)
REPOSITORY_ARTIFACT_RETENTION_DAYS = 30
REPOSITORY_RUN_PAYLOAD_MAX_BYTES = 64 * 1024
REPOSITORY_ARTIFACT_MANIFEST_MAX_BYTES = 32 * 1024
REPOSITORY_ARTIFACT_MAX_BYTES = 64 * 1024 * 1024
REPOSITORY_ANALYSIS_LEASE_SECONDS = 300
REPOSITORY_ANALYSIS_RETRY_DELAY_SECONDS = 60
_SAFE_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SAFE_WORKER_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")
_SAFE_ERROR_CODE = re.compile(r"^[a-z][a-z0-9_.-]{0,79}$")
_SAFE_STORAGE_REF = re.compile(
    r"^repository-intelligence/[A-Za-z0-9][A-Za-z0-9._/-]{0,459}$"
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")

_ALLOWED_COVERAGE_CHECKS = frozenset(
    {
        "canonical_metadata",
        "manifest",
        "entrypoint",
        "dependency",
        "interface",
        "deployment",
        "test_ci",
        "documentation",
        "migration",
        "relationship",
        "isolated_execution",
    }
)
_REQUIRED_COVERAGE: dict[AuditLevel, frozenset[str]] = {
    AuditLevel.L0: frozenset({"canonical_metadata"}),
    AuditLevel.L1: frozenset(
        {
            "manifest",
            "entrypoint",
            "dependency",
            "interface",
            "deployment",
            "test_ci",
            "documentation",
            "migration",
            "relationship",
        }
    ),
    AuditLevel.L2: frozenset(
        {
            "manifest",
            "entrypoint",
            "dependency",
            "interface",
            "deployment",
            "test_ci",
            "documentation",
            "migration",
            "relationship",
            "isolated_execution",
        }
    ),
}


class RepositoryIntelligencePersistenceError(RuntimeError):
    """Sanitized RI-006 persistence failure."""


class RepositoryIntelligenceConflictError(RepositoryIntelligencePersistenceError):
    """An idempotency key or run identity was reused with different input."""


class RepositoryIntelligenceStateError(RepositoryIntelligencePersistenceError):
    """A requested lifecycle transition is invalid."""


class RepositoryIntelligenceEvidenceError(RepositoryIntelligencePersistenceError):
    """Evidence could not be resolved inside the trusted workspace."""


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


StrictCheck = Annotated[
    str,
    StringConstraints(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_.-]*$"),
]


class RepositoryCoverageV1(_StrictModel):
    completed_checks: list[StrictCheck] = Field(default_factory=list, max_length=20)
    failed_checks: list[StrictCheck] = Field(default_factory=list, max_length=20)
    skipped_checks: list[StrictCheck] = Field(default_factory=list, max_length=20)

    @field_validator("completed_checks", "failed_checks", "skipped_checks")
    @classmethod
    def validate_checks(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("coverage checks must be unique")
        if any(value not in _ALLOWED_COVERAGE_CHECKS for value in values):
            raise ValueError("coverage contains an unsupported check")
        return sorted(values)

    @model_validator(mode="after")
    def validate_disjoint_sets(self) -> Self:
        completed = set(self.completed_checks)
        failed = set(self.failed_checks)
        skipped = set(self.skipped_checks)
        if completed & failed or completed & skipped or failed & skipped:
            raise ValueError("coverage check sets must be disjoint")
        return self

    def is_complete_for(self, audit_level: AuditLevel) -> bool:
        required = _REQUIRED_COVERAGE[audit_level]
        completed = set(self.completed_checks)
        return (
            required.issubset(completed)
            and not self.failed_checks
            and not required.intersection(self.skipped_checks)
        )


class RepositoryArtifactManifestItemV1(_StrictModel):
    artifact_type: Literal[
        "collector_result",
        "relationship_result",
        "scanner_result",
        "report",
    ]
    storage_ref: Annotated[str, StringConstraints(min_length=1, max_length=500)]
    content_hash: Annotated[
        str,
        StringConstraints(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$"),
    ]
    size_bytes: int = Field(ge=0, le=REPOSITORY_ARTIFACT_MAX_BYTES)

    @field_validator("storage_ref")
    @classmethod
    def validate_storage_ref(cls, value: str) -> str:
        if (
            _SAFE_STORAGE_REF.fullmatch(value) is None
            or ".." in value.split("/")
            or "\\" in value
        ):
            raise ValueError("artifact storage_ref must be an opaque RI raw-storage ref")
        return value


class RepositoryAnalysisRequestV1(_StrictModel):
    workspace_id: UUID
    repository_id: UUID
    idempotency_key: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    audit_level: AuditLevel
    analysis_target: AnalysisTargetV1
    profile: Annotated[
        str,
        StringConstraints(
            min_length=1,
            max_length=80,
            pattern=r"^[a-z][a-z0-9_.-]{0,79}$",
        ),
    ]
    policy_hash: Annotated[
        str,
        StringConstraints(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$"),
    ]
    engine_version: Annotated[str, StringConstraints(min_length=1, max_length=80)]
    max_attempts: int = Field(default=3, ge=1, le=10)

    @field_validator("idempotency_key", "engine_version")
    @classmethod
    def validate_safe_text(cls, value: str, info: ValidationInfo) -> str:
        if value != value.strip() or any(
            ord(character) < 32 or ord(character) == 127
            for character in value
        ):
            raise ValueError("analysis request text is unsafe")
        if info.field_name == "idempotency_key" and _SAFE_KEY.fullmatch(value) is None:
            raise ValueError("analysis idempotency key is invalid")
        return value

    @model_validator(mode="after")
    def validate_target_level(self) -> Self:
        if (
            self.audit_level in {AuditLevel.L1, AuditLevel.L2}
            and self.analysis_target.target_status.value != "exact"
        ):
            raise ValueError("L1 and L2 requests require an exact target")
        return self


class RepositoryArtifactDeletionReceipt(_StrictModel):
    workspace_id: UUID
    run_id: UUID
    storage_refs: list[
        Annotated[str, StringConstraints(min_length=1, max_length=500)]
    ] = Field(default_factory=list, max_length=50)
    expires_at: datetime


class RepositoryIntelligenceDeletionResult(_StrictModel):
    jobs_deleted: int
    runs_deleted: int
    facts_deleted: int
    relationships_deleted: int
    findings_deleted: int
    contradictions_deleted: int
    evidence_links_deleted: int
    evidence_refs_deleted: int
    source_records_deleted: int


async def enqueue_repository_analysis_job(
    session: AsyncSession,
    *,
    request: RepositoryAnalysisRequestV1,
    requested_by_user_id: UUID,
) -> RepositoryAnalysisJob:
    """Create or replay one workspace-scoped analysis job idempotently."""

    await _require_admin_membership(
        session,
        workspace_id=request.workspace_id,
        user_id=requested_by_user_id,
    )
    await _require_repository(
        session,
        workspace_id=request.workspace_id,
        repository_id=request.repository_id,
    )
    request_hash = _sha256_json(
        request.model_dump(mode="json", exclude={"idempotency_key"})
    )
    existing = await session.scalar(
        select(RepositoryAnalysisJob)
        .where(
            RepositoryAnalysisJob.workspace_id == request.workspace_id,
            RepositoryAnalysisJob.idempotency_key == request.idempotency_key,
        )
        .with_for_update()
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise RepositoryIntelligenceConflictError(
                "analysis idempotency key was reused with different input"
            )
        return existing

    job = RepositoryAnalysisJob(
        workspace_id=request.workspace_id,
        repository_id=request.repository_id,
        requested_by_user_id=requested_by_user_id,
        idempotency_key=request.idempotency_key,
        request_hash=request_hash,
        target_status=request.analysis_target.target_status.value,
        commit_sha=request.analysis_target.commit_sha,
        metadata_snapshot_id=request.analysis_target.metadata_snapshot_id,
        audit_level=request.audit_level.value,
        profile=request.profile,
        policy_hash=request.policy_hash,
        engine_version=request.engine_version,
        max_attempts=request.max_attempts,
    )
    session.add(job)
    await session.flush()
    return job


async def claim_repository_analysis_job(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    job_id: UUID,
    worker_id: str,
    now: datetime | None = None,
    lease_seconds: int = REPOSITORY_ANALYSIS_LEASE_SECONDS,
) -> RepositoryAnalysisJob | None:
    """Claim one queued or stale-leased job without exposing repository data."""

    if _SAFE_WORKER_ID.fullmatch(worker_id) is None:
        raise RepositoryIntelligenceStateError("analysis worker identity is invalid")
    if lease_seconds <= 0 or lease_seconds > 3600:
        raise RepositoryIntelligenceStateError("analysis lease duration is invalid")
    current_time = _aware_utc(now)
    job = await session.scalar(
        select(RepositoryAnalysisJob)
        .where(
            RepositoryAnalysisJob.workspace_id == workspace_id,
            RepositoryAnalysisJob.id == job_id,
        )
        .with_for_update()
    )
    if job is None:
        return None
    if job.status in {
        REPOSITORY_ANALYSIS_JOB_STATUS_SUCCEEDED,
        REPOSITORY_ANALYSIS_JOB_STATUS_FAILED,
        REPOSITORY_ANALYSIS_JOB_STATUS_PARTIAL,
        REPOSITORY_ANALYSIS_JOB_STATUS_CANCELLED,
    }:
        return None
    if job.cancel_requested_at is not None:
        _finish_cancelled_job(job, current_time)
        await session.flush()
        return None
    if job.next_attempt_at > current_time:
        return None
    if (
        job.lease_expires_at is not None
        and job.lease_expires_at > current_time
    ):
        return None
    if job.attempt_count >= job.max_attempts:
        job.status = REPOSITORY_ANALYSIS_JOB_STATUS_FAILED
        job.completed_at = current_time
        job.error_code = "attempts_exhausted"
        job.lease_owner = None
        job.lease_expires_at = None
        await session.flush()
        return None

    job.status = REPOSITORY_ANALYSIS_JOB_STATUS_RUNNING
    job.attempt_count += 1
    job.started_at = job.started_at or current_time
    job.lease_owner = worker_id
    job.lease_expires_at = current_time + timedelta(seconds=lease_seconds)
    job.error_code = None
    await session.flush()
    return job


async def fail_repository_analysis_job(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    job_id: UUID,
    worker_id: str,
    error_code: str,
    retryable: bool,
    now: datetime | None = None,
    retry_delay_seconds: int = REPOSITORY_ANALYSIS_RETRY_DELAY_SECONDS,
) -> RepositoryAnalysisJob:
    """Record a sanitized failure and either retry or finish the job."""

    if _SAFE_ERROR_CODE.fullmatch(error_code) is None:
        raise RepositoryIntelligenceStateError("analysis error code is invalid")
    if _SAFE_WORKER_ID.fullmatch(worker_id) is None:
        raise RepositoryIntelligenceStateError("analysis worker identity is invalid")
    if retry_delay_seconds < 0 or retry_delay_seconds > 86_400:
        raise RepositoryIntelligenceStateError("analysis retry delay is invalid")
    current_time = _aware_utc(now)
    job = await _locked_job(
        session,
        workspace_id=workspace_id,
        job_id=job_id,
    )
    if job.status != REPOSITORY_ANALYSIS_JOB_STATUS_RUNNING:
        raise RepositoryIntelligenceStateError(
            "only a running analysis job can record worker failure"
        )
    if job.lease_owner != worker_id:
        raise RepositoryIntelligenceStateError(
            "analysis worker does not own the active lease"
        )
    job.error_code = error_code
    job.lease_owner = None
    job.lease_expires_at = None
    if retryable and job.attempt_count < job.max_attempts:
        job.status = REPOSITORY_ANALYSIS_JOB_STATUS_QUEUED
        job.next_attempt_at = current_time + timedelta(
            seconds=retry_delay_seconds
        )
    else:
        job.status = REPOSITORY_ANALYSIS_JOB_STATUS_FAILED
        job.completed_at = current_time
    await session.flush()
    return job


async def request_repository_analysis_cancellation(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    job_id: UUID,
    requested_by_user_id: UUID,
    now: datetime | None = None,
) -> RepositoryAnalysisJob:
    current_time = _aware_utc(now)
    await _require_admin_membership(
        session,
        workspace_id=workspace_id,
        user_id=requested_by_user_id,
    )
    job = await _locked_job(
        session,
        workspace_id=workspace_id,
        job_id=job_id,
    )
    if job.status in {
        REPOSITORY_ANALYSIS_JOB_STATUS_SUCCEEDED,
        REPOSITORY_ANALYSIS_JOB_STATUS_FAILED,
        REPOSITORY_ANALYSIS_JOB_STATUS_PARTIAL,
        REPOSITORY_ANALYSIS_JOB_STATUS_CANCELLED,
    }:
        return job
    job.cancel_requested_at = current_time
    if job.status == REPOSITORY_ANALYSIS_JOB_STATUS_QUEUED:
        _finish_cancelled_job(job, current_time)
    await session.flush()
    return job


async def persist_repository_intelligence_result(
    session: AsyncSession,
    *,
    job_id: UUID,
    worker_id: str,
    payload: RepositoryIntelligenceV1,
    coverage: RepositoryCoverageV1,
    artifact_manifest: Sequence[RepositoryArtifactManifestItemV1] = (),
    started_at: datetime,
    completed_at: datetime,
) -> RepositoryAuditRun:
    """Persist one strict result and reconcile only complete trusted coverage."""

    started = _aware_utc(started_at)
    completed = _aware_utc(completed_at)
    if _SAFE_WORKER_ID.fullmatch(worker_id) is None:
        raise RepositoryIntelligenceStateError("analysis worker identity is invalid")
    if completed < started:
        raise RepositoryIntelligenceStateError(
            "analysis completion cannot precede its start"
        )
    job = await _locked_job(
        session,
        workspace_id=payload.workspace_id,
        job_id=job_id,
    )
    _validate_job_payload(job=job, payload=payload)
    if job.cancel_requested_at is not None:
        _finish_cancelled_job(job, completed)
        await session.flush()
        raise RepositoryIntelligenceStateError(
            "cancelled analysis result cannot be persisted"
        )
    manifest_items = list(artifact_manifest)
    manifest_payload = [
        item.model_dump(mode="json") for item in manifest_items
    ]
    manifest_encoded = _strict_json(manifest_payload)
    if len(manifest_encoded) > REPOSITORY_ARTIFACT_MANIFEST_MAX_BYTES:
        raise RepositoryIntelligenceStateError(
            "artifact manifest exceeds the configured byte bound"
        )
    result_hash = _sha256_json(payload.model_dump(mode="json"))
    run_key = _run_key(payload)
    existing = await session.scalar(
        select(RepositoryAuditRun)
        .where(
            RepositoryAuditRun.workspace_id == payload.workspace_id,
            RepositoryAuditRun.job_id == job.id,
        )
        .with_for_update()
    )
    if existing is not None:
        expected_complete = coverage.is_complete_for(payload.audit_level)
        expected_status = (
            REPOSITORY_AUDIT_RUN_STATUS_SUCCEEDED
            if expected_complete
            else REPOSITORY_AUDIT_RUN_STATUS_PARTIAL
        )
        if (
            existing.result_hash != result_hash
            or existing.coverage != coverage.model_dump(mode="json")
            or existing.artifact_manifest_hash
            != sha256(manifest_encoded).hexdigest()
            or existing.status != expected_status
        ):
            raise RepositoryIntelligenceConflictError(
                "analysis run identity produced a different result"
            )
        _finish_job_from_run(job, existing)
        await session.flush()
        return existing
    if job.status != REPOSITORY_ANALYSIS_JOB_STATUS_RUNNING:
        raise RepositoryIntelligenceStateError(
            "new analysis result requires a running job"
        )
    if job.lease_owner != worker_id:
        raise RepositoryIntelligenceStateError(
            "analysis worker does not own the active lease"
        )

    complete = coverage.is_complete_for(payload.audit_level)
    run_status = (
        REPOSITORY_AUDIT_RUN_STATUS_SUCCEEDED
        if complete
        else REPOSITORY_AUDIT_RUN_STATUS_PARTIAL
    )
    coverage_status = (
        REPOSITORY_COVERAGE_STATUS_COMPLETE
        if complete
        else REPOSITORY_COVERAGE_STATUS_PARTIAL
    )
    run_id = uuid4()
    source_record_id = uuid4()
    artifact_manifest_hash = sha256(manifest_encoded).hexdigest()
    run_manifest = _run_source_manifest(
        run_id=run_id,
        payload=payload,
        run_key=run_key,
        result_hash=result_hash,
        status=run_status,
        coverage_status=coverage_status,
        coverage=coverage,
        artifact_manifest_hash=artifact_manifest_hash,
        artifact_count=len(manifest_items),
    )
    source_payload_hash = _sha256_json(run_manifest)
    source_record = SourceRecord(
        id=source_record_id,
        workspace_id=payload.workspace_id,
        provider=SOURCE_RECORD_PROVIDER_INTERNAL,
        external_id=f"repository-intelligence-run:{run_id}",
        record_type=REPOSITORY_INTELLIGENCE_RUN_RECORD_TYPE,
        payload=run_manifest,
        payload_hash=source_payload_hash,
        observed_at=completed,
        source_updated_at=completed,
    )
    session.add(source_record)
    run = RepositoryAuditRun(
        id=run_id,
        workspace_id=payload.workspace_id,
        repository_id=payload.repository_id,
        job_id=job.id,
        source_record_id=source_record_id,
        run_key=run_key,
        result_hash=result_hash,
        target_status=payload.analysis_target.target_status.value,
        commit_sha=payload.analysis_target.commit_sha,
        metadata_snapshot_id=payload.analysis_target.metadata_snapshot_id,
        audit_level=payload.audit_level.value,
        profile=payload.profile,
        policy_hash=payload.policy_hash,
        engine_version=payload.engine_version,
        status=run_status,
        coverage_status=coverage_status,
        coverage=coverage.model_dump(mode="json"),
        limitations=list(payload.result.limitations),
        artifact_manifest=manifest_payload,
        artifact_manifest_hash=artifact_manifest_hash,
        artifact_expires_at=completed
        + timedelta(days=REPOSITORY_ARTIFACT_RETENTION_DAYS),
        started_at=started,
        completed_at=completed,
    )
    session.add(run)
    await session.flush()

    claim_rows = await _upsert_facts(
        session,
        run=run,
        source_record=source_record,
        payload=payload,
    )
    await _upsert_relationships(
        session,
        run=run,
        source_record=source_record,
        relationships=payload.result.relationship_candidates,
    )
    await _upsert_findings(
        session,
        run=run,
        source_record=source_record,
        findings=payload.result.findings,
    )
    await _upsert_contradictions(
        session,
        run=run,
        source_record=source_record,
        contradictions=payload.result.contradictions,
        fact_by_claim_id=claim_rows,
    )
    if complete:
        await _reconcile_absent_records(session, run=run)
        run.reconciliation_applied = True

    _finish_job_from_run(job, run)
    await session.flush()
    return run


async def list_expired_repository_artifacts(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    now: datetime | None = None,
) -> list[RepositoryArtifactDeletionReceipt]:
    current_time = _aware_utc(now)
    runs = list(
        (
            await session.execute(
                select(RepositoryAuditRun)
                .where(
                    RepositoryAuditRun.workspace_id == workspace_id,
                    RepositoryAuditRun.artifact_purged_at.is_(None),
                    RepositoryAuditRun.artifact_expires_at <= current_time,
                )
                .order_by(RepositoryAuditRun.id.asc())
            )
        ).scalars()
    )
    return [
        RepositoryArtifactDeletionReceipt(
            workspace_id=workspace_id,
            run_id=run.id,
            storage_refs=[
                str(item["storage_ref"])
                for item in run.artifact_manifest
                if isinstance(item, dict)
                and isinstance(item.get("storage_ref"), str)
            ],
            expires_at=run.artifact_expires_at,
        )
        for run in runs
    ]


async def confirm_repository_artifacts_deleted(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    run_id: UUID,
    now: datetime | None = None,
) -> RepositoryAuditRun:
    """Clear artifact refs only after an external raw-storage deletion succeeds."""

    current_time = _aware_utc(now)
    run = await session.scalar(
        select(RepositoryAuditRun)
        .where(
            RepositoryAuditRun.workspace_id == workspace_id,
            RepositoryAuditRun.id == run_id,
        )
        .with_for_update()
    )
    if run is None:
        raise RepositoryIntelligenceStateError("repository audit run was not found")
    if run.artifact_expires_at > current_time:
        raise RepositoryIntelligenceStateError(
            "repository artifacts are not past retention"
        )
    run.artifact_manifest = []
    run.artifact_manifest_hash = sha256(b"[]").hexdigest()
    run.artifact_purged_at = current_time
    await session.flush()
    return run


async def delete_repository_intelligence_records(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    repository_id: UUID,
    requested_by_user_id: UUID,
) -> RepositoryIntelligenceDeletionResult:
    """Delete the exact RI boundary for one repository in dependency order."""

    await _require_admin_membership(
        session,
        workspace_id=workspace_id,
        user_id=requested_by_user_id,
    )
    run_ids = list(
        (
            await session.execute(
                select(RepositoryAuditRun.id).where(
                    RepositoryAuditRun.workspace_id == workspace_id,
                    RepositoryAuditRun.repository_id == repository_id,
                )
            )
        ).scalars()
    )
    source_record_ids = list(
        (
            await session.execute(
                select(RepositoryAuditRun.source_record_id).where(
                    RepositoryAuditRun.workspace_id == workspace_id,
                    RepositoryAuditRun.repository_id == repository_id,
                )
            )
        ).scalars()
    )
    parent_ids = await _repository_parent_ids(
        session,
        workspace_id=workspace_id,
        repository_id=repository_id,
    )
    evidence_links_deleted = await _delete_evidence_links_for_parents(
        session,
        workspace_id=workspace_id,
        parent_ids=parent_ids,
    )
    contradictions_deleted = await _delete_count(
        session,
        delete(RepositoryContradiction).where(
            RepositoryContradiction.workspace_id == workspace_id,
            RepositoryContradiction.repository_id == repository_id,
        ),
    )
    findings_deleted = await _delete_count(
        session,
        delete(RepositoryAuditFinding).where(
            RepositoryAuditFinding.workspace_id == workspace_id,
            RepositoryAuditFinding.repository_id == repository_id,
        ),
    )
    relationships_deleted = await _delete_count(
        session,
        delete(RepositoryRelationshipRecord).where(
            RepositoryRelationshipRecord.workspace_id == workspace_id,
            RepositoryRelationshipRecord.from_repository_id == repository_id,
        ),
    )
    facts_deleted = await _delete_count(
        session,
        delete(RepositoryFact).where(
            RepositoryFact.workspace_id == workspace_id,
            RepositoryFact.repository_id == repository_id,
        ),
    )
    runs_deleted = await _delete_count(
        session,
        delete(RepositoryAuditRun).where(
            RepositoryAuditRun.workspace_id == workspace_id,
            RepositoryAuditRun.repository_id == repository_id,
        ),
    )
    jobs_deleted = await _delete_count(
        session,
        delete(RepositoryAnalysisJob).where(
            RepositoryAnalysisJob.workspace_id == workspace_id,
            RepositoryAnalysisJob.repository_id == repository_id,
        ),
    )
    evidence_refs_deleted = 0
    source_records_deleted = 0
    if source_record_ids:
        evidence_refs_deleted = await _delete_count(
            session,
            delete(EvidenceRef).where(
                EvidenceRef.workspace_id == workspace_id,
                EvidenceRef.source_record_id.in_(source_record_ids),
            ),
        )
        source_records_deleted = await _delete_count(
            session,
            delete(SourceRecord).where(
                SourceRecord.workspace_id == workspace_id,
                SourceRecord.id.in_(source_record_ids),
                SourceRecord.record_type
                == REPOSITORY_INTELLIGENCE_RUN_RECORD_TYPE,
            ),
        )
    if run_ids and runs_deleted != len(run_ids):
        raise RepositoryIntelligenceStateError(
            "repository intelligence deletion did not remove the exact run set"
        )
    return RepositoryIntelligenceDeletionResult(
        jobs_deleted=jobs_deleted,
        runs_deleted=runs_deleted,
        facts_deleted=facts_deleted,
        relationships_deleted=relationships_deleted,
        findings_deleted=findings_deleted,
        contradictions_deleted=contradictions_deleted,
        evidence_links_deleted=evidence_links_deleted,
        evidence_refs_deleted=evidence_refs_deleted,
        source_records_deleted=source_records_deleted,
    )


async def _upsert_facts(
    session: AsyncSession,
    *,
    run: RepositoryAuditRun,
    source_record: SourceRecord,
    payload: RepositoryIntelligenceV1,
) -> dict[str, RepositoryFact]:
    material: list[
        tuple[
            str,
            str,
            dict[str, Any],
            str,
            float,
            list[EvidenceRefV1],
            list[EvidenceRefV1],
        ]
    ] = []
    purpose = payload.result.purpose
    material.append(
        (
            purpose.claim_id,
            "purpose",
            {
                "summary": purpose.summary,
                "operational_summary": purpose.operational_summary,
                "repository_type": purpose.repository_type.value,
            },
            purpose.status.value,
            purpose.confidence,
            purpose.evidence_refs,
            purpose.contradicting_evidence_refs,
        )
    )
    sections: tuple[tuple[str, Sequence[RepositoryClaimV1]], ...] = (
        ("responsibility", payload.result.responsibilities),
        ("interface_provided", payload.result.interfaces_provided),
        ("dependency_consumed", payload.result.dependencies_consumed),
        ("deployment_unit", payload.result.deployment_units),
        ("owner_candidate", payload.result.ownership_candidates),
    )
    for fact_type, claims in sections:
        for claim in claims:
            material.append(
                (
                    claim.claim_id,
                    fact_type,
                    {
                        "claim_type": claim.claim_type,
                        "summary": claim.summary,
                        "details": claim.details,
                    },
                    claim.status.value,
                    claim.confidence,
                    claim.evidence_refs,
                    claim.contradicting_evidence_refs,
                )
            )
    for unknown in payload.result.unknowns:
        material.append(
            (
                unknown.unknown_id,
                "unknown",
                {"question": unknown.question},
                unknown.status.value,
                0.0,
                unknown.evidence_refs,
                [],
            )
        )

    fact_by_claim_id: dict[str, RepositoryFact] = {}
    for (
        claim_id,
        fact_type,
        value,
        claim_status,
        confidence,
        evidence_refs,
        contradicting_evidence_refs,
    ) in material:
        fingerprint = _fingerprint(
            "fact",
            str(run.repository_id),
            fact_type,
            claim_id,
        )
        row = await session.scalar(
            select(RepositoryFact)
            .where(
                RepositoryFact.workspace_id == run.workspace_id,
                RepositoryFact.repository_id == run.repository_id,
                RepositoryFact.fingerprint == fingerprint,
            )
            .with_for_update()
        )
        if row is None:
            row = RepositoryFact(
                workspace_id=run.workspace_id,
                repository_id=run.repository_id,
                fingerprint=fingerprint,
                claim_id=claim_id,
                fact_type=fact_type,
                value=value,
                claim_status=claim_status,
                confidence=confidence,
                first_seen_run_id=run.id,
                last_seen_run_id=run.id,
            )
            session.add(row)
            await session.flush()
        else:
            row.value = value
            row.claim_status = claim_status
            row.confidence = confidence
            row.lifecycle_status = REPOSITORY_LIFECYCLE_STATUS_CURRENT
            row.last_seen_run_id = run.id
            row.stale_at = None
        await _replace_evidence_links(
            session,
            workspace_id=run.workspace_id,
            source_record=source_record,
            parent_type="fact",
            parent_id=row.id,
            supporting=evidence_refs,
            contradicting=contradicting_evidence_refs,
        )
        fact_by_claim_id[claim_id] = row
    return fact_by_claim_id


async def _upsert_relationships(
    session: AsyncSession,
    *,
    run: RepositoryAuditRun,
    source_record: SourceRecord,
    relationships: Sequence[RepositoryRelationshipV1],
) -> None:
    for relationship in relationships:
        if relationship.status == AnalyzerClaimStatus.INSUFFICIENT_EVIDENCE:
            raise RepositoryIntelligenceEvidenceError(
                "insufficient evidence cannot create a repository relationship"
            )
        if relationship.from_repository.repository_id != run.repository_id:
            raise RepositoryIntelligenceStateError(
                "relationship source must match the persisted repository"
            )
        fingerprint = _fingerprint(
            "relationship",
            *relationship.normalized_identity(),
        )
        row = await session.scalar(
            select(RepositoryRelationshipRecord)
            .where(
                RepositoryRelationshipRecord.workspace_id == run.workspace_id,
                RepositoryRelationshipRecord.from_repository_id
                == run.repository_id,
                RepositoryRelationshipRecord.fingerprint == fingerprint,
            )
            .with_for_update()
        )
        target = relationship.to_repository
        if row is None:
            row = RepositoryRelationshipRecord(
                workspace_id=run.workspace_id,
                from_repository_id=run.repository_id,
                to_repository_id=target.repository_id,
                fingerprint=fingerprint,
                relationship_type=relationship.relationship_type.value,
                target_provider=target.provider.value,
                target_external_id=target.external_id,
                target_full_name=target.full_name,
                resolution_status=target.resolution_status.value,
                summary=relationship.summary,
                claim_status=relationship.status.value,
                confidence=relationship.confidence,
                first_seen_run_id=run.id,
                last_seen_run_id=run.id,
            )
            session.add(row)
            await session.flush()
        else:
            row.to_repository_id = target.repository_id
            row.target_provider = target.provider.value
            row.target_external_id = target.external_id
            row.target_full_name = target.full_name
            row.resolution_status = target.resolution_status.value
            row.summary = relationship.summary
            row.claim_status = relationship.status.value
            row.confidence = relationship.confidence
            row.lifecycle_status = REPOSITORY_LIFECYCLE_STATUS_CURRENT
            row.last_seen_run_id = run.id
            row.stale_at = None
        await _replace_evidence_links(
            session,
            workspace_id=run.workspace_id,
            source_record=source_record,
            parent_type="relationship",
            parent_id=row.id,
            supporting=relationship.evidence_refs,
            contradicting=relationship.contradicting_evidence_refs,
        )


async def _upsert_findings(
    session: AsyncSession,
    *,
    run: RepositoryAuditRun,
    source_record: SourceRecord,
    findings: Sequence[RepositoryFindingV1],
) -> None:
    for finding in findings:
        fingerprint = _fingerprint(
            "finding",
            str(run.repository_id),
            finding.rule_id,
            finding.category,
            finding.finding_id,
        )
        row = await session.scalar(
            select(RepositoryAuditFinding)
            .where(
                RepositoryAuditFinding.workspace_id == run.workspace_id,
                RepositoryAuditFinding.repository_id == run.repository_id,
                RepositoryAuditFinding.fingerprint == fingerprint,
            )
            .with_for_update()
        )
        incoming_status = (
            finding.lifecycle_status.value
            if finding.lifecycle_status
            == FindingLifecycleStatus.INSUFFICIENT_EVIDENCE
            else REPOSITORY_FINDING_STATUS_NEW
        )
        if row is None:
            row = RepositoryAuditFinding(
                workspace_id=run.workspace_id,
                repository_id=run.repository_id,
                fingerprint=fingerprint,
                finding_id=finding.finding_id,
                rule_id=finding.rule_id,
                category=finding.category,
                severity=finding.severity.value,
                confidence=finding.confidence,
                status=incoming_status,
                title=finding.title,
                summary=finding.summary,
                recommended_next_step=finding.recommended_next_step,
                first_seen_run_id=run.id,
                last_seen_run_id=run.id,
            )
            session.add(row)
            await session.flush()
        else:
            row.severity = finding.severity.value
            row.confidence = finding.confidence
            row.title = finding.title
            row.summary = finding.summary
            row.recommended_next_step = finding.recommended_next_step
            row.last_seen_run_id = run.id
            if row.status == REPOSITORY_FINDING_STATUS_RESOLVED:
                row.status = REPOSITORY_FINDING_STATUS_REGRESSED
                row.resolved_at = None
            elif row.status not in {
                REPOSITORY_FINDING_STATUS_ACCEPTED_RISK,
                REPOSITORY_FINDING_STATUS_FALSE_POSITIVE,
            }:
                row.status = incoming_status
        await _replace_evidence_links(
            session,
            workspace_id=run.workspace_id,
            source_record=source_record,
            parent_type="finding",
            parent_id=row.id,
            supporting=finding.evidence_refs,
            contradicting=finding.contradicting_evidence_refs,
        )


async def _upsert_contradictions(
    session: AsyncSession,
    *,
    run: RepositoryAuditRun,
    source_record: SourceRecord,
    contradictions: Sequence[RepositoryContradictionV1],
    fact_by_claim_id: dict[str, RepositoryFact],
) -> None:
    for contradiction in contradictions:
        left = fact_by_claim_id.get(contradiction.left_claim_id)
        right = fact_by_claim_id.get(contradiction.right_claim_id)
        if left is None or right is None:
            raise RepositoryIntelligenceStateError(
                "contradiction references a missing persisted fact"
            )
        fingerprint = _fingerprint(
            "contradiction",
            str(run.repository_id),
            *contradiction.normalized_pair(),
        )
        row = await session.scalar(
            select(RepositoryContradiction)
            .where(
                RepositoryContradiction.workspace_id == run.workspace_id,
                RepositoryContradiction.repository_id == run.repository_id,
                RepositoryContradiction.fingerprint == fingerprint,
            )
            .with_for_update()
        )
        if row is None:
            row = RepositoryContradiction(
                workspace_id=run.workspace_id,
                repository_id=run.repository_id,
                fingerprint=fingerprint,
                contradiction_id=contradiction.contradiction_id,
                left_fact_id=left.id,
                right_fact_id=right.id,
                confidence=contradiction.confidence,
                summary=contradiction.summary,
                first_seen_run_id=run.id,
                last_seen_run_id=run.id,
            )
            session.add(row)
            await session.flush()
        else:
            row.left_fact_id = left.id
            row.right_fact_id = right.id
            row.status = REPOSITORY_CONTRADICTION_STATUS_CURRENT
            row.confidence = contradiction.confidence
            row.summary = contradiction.summary
            row.last_seen_run_id = run.id
            row.resolved_at = None
        await _replace_evidence_links(
            session,
            workspace_id=run.workspace_id,
            source_record=source_record,
            parent_type="contradiction",
            parent_id=row.id,
            supporting=contradiction.evidence_refs,
            contradicting=[],
        )


async def _reconcile_absent_records(
    session: AsyncSession,
    *,
    run: RepositoryAuditRun,
) -> None:
    current_time = run.completed_at
    prior_runs = (
        select(RepositoryAuditRun.id)
        .where(
            RepositoryAuditRun.workspace_id == run.workspace_id,
            RepositoryAuditRun.repository_id == run.repository_id,
            RepositoryAuditRun.profile == run.profile,
            RepositoryAuditRun.audit_level == run.audit_level,
            RepositoryAuditRun.policy_hash == run.policy_hash,
            RepositoryAuditRun.engine_version == run.engine_version,
            RepositoryAuditRun.id != run.id,
        )
    )
    facts = list(
        (
            await session.execute(
                select(RepositoryFact)
                .where(
                    RepositoryFact.workspace_id == run.workspace_id,
                    RepositoryFact.repository_id == run.repository_id,
                    RepositoryFact.lifecycle_status
                    == REPOSITORY_LIFECYCLE_STATUS_CURRENT,
                    RepositoryFact.last_seen_run_id.in_(prior_runs),
                )
                .with_for_update()
            )
        ).scalars()
    )
    for fact in facts:
        fact.lifecycle_status = REPOSITORY_LIFECYCLE_STATUS_STALE
        fact.stale_at = current_time

    relationships = list(
        (
            await session.execute(
                select(RepositoryRelationshipRecord)
                .where(
                    RepositoryRelationshipRecord.workspace_id
                    == run.workspace_id,
                    RepositoryRelationshipRecord.from_repository_id
                    == run.repository_id,
                    RepositoryRelationshipRecord.lifecycle_status
                    == REPOSITORY_LIFECYCLE_STATUS_CURRENT,
                    RepositoryRelationshipRecord.last_seen_run_id.in_(prior_runs),
                )
                .with_for_update()
            )
        ).scalars()
    )
    for relationship in relationships:
        relationship.lifecycle_status = REPOSITORY_LIFECYCLE_STATUS_STALE
        relationship.stale_at = current_time

    findings = list(
        (
            await session.execute(
                select(RepositoryAuditFinding)
                .where(
                    RepositoryAuditFinding.workspace_id == run.workspace_id,
                    RepositoryAuditFinding.repository_id == run.repository_id,
                    RepositoryAuditFinding.last_seen_run_id.in_(prior_runs),
                    RepositoryAuditFinding.status.not_in(
                        {
                            REPOSITORY_FINDING_STATUS_RESOLVED,
                            REPOSITORY_FINDING_STATUS_ACCEPTED_RISK,
                            REPOSITORY_FINDING_STATUS_FALSE_POSITIVE,
                        }
                    ),
                )
                .with_for_update()
            )
        ).scalars()
    )
    for finding in findings:
        finding.status = REPOSITORY_FINDING_STATUS_RESOLVED
        finding.resolved_at = current_time

    contradictions = list(
        (
            await session.execute(
                select(RepositoryContradiction)
                .where(
                    RepositoryContradiction.workspace_id == run.workspace_id,
                    RepositoryContradiction.repository_id == run.repository_id,
                    RepositoryContradiction.status
                    == REPOSITORY_CONTRADICTION_STATUS_CURRENT,
                    RepositoryContradiction.last_seen_run_id.in_(prior_runs),
                )
                .with_for_update()
            )
        ).scalars()
    )
    for contradiction in contradictions:
        contradiction.status = REPOSITORY_CONTRADICTION_STATUS_RESOLVED
        contradiction.resolved_at = current_time


async def _replace_evidence_links(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    source_record: SourceRecord,
    parent_type: Literal["fact", "relationship", "finding", "contradiction"],
    parent_id: UUID,
    supporting: Sequence[EvidenceRefV1],
    contradicting: Sequence[EvidenceRefV1],
) -> None:
    parent_column = getattr(RepositoryEvidenceLink, f"{parent_type}_id")
    await session.execute(
        delete(RepositoryEvidenceLink).where(
            RepositoryEvidenceLink.workspace_id == workspace_id,
            parent_column == parent_id,
        )
    )
    for role, evidence_refs in (
        (REPOSITORY_EVIDENCE_ROLE_SUPPORTING, supporting),
        (REPOSITORY_EVIDENCE_ROLE_CONTRADICTING, contradicting),
    ):
        for evidence in evidence_refs:
            row = await _resolve_evidence(
                session,
                workspace_id=workspace_id,
                run_source_record=source_record,
                evidence=evidence,
            )
            link_values: dict[str, Any] = {
                "workspace_id": workspace_id,
                "evidence_ref_id": row.id,
                "evidence_role": role,
                f"{parent_type}_id": parent_id,
            }
            session.add(RepositoryEvidenceLink(**link_values))
    await session.flush()


async def _resolve_evidence(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    run_source_record: SourceRecord,
    evidence: EvidenceRefV1,
) -> EvidenceRef:
    if evidence.evidence_ref_id is not None:
        existing = await session.scalar(
            select(EvidenceRef).where(
                EvidenceRef.workspace_id == workspace_id,
                EvidenceRef.id == evidence.evidence_ref_id,
            )
        )
        if existing is None:
            raise RepositoryIntelligenceEvidenceError(
                "evidence_ref_id is unavailable in the trusted workspace"
            )
        return existing

    source_record_id = evidence.source_record_id or run_source_record.id
    source_record = await session.scalar(
        select(SourceRecord).where(
            SourceRecord.workspace_id == workspace_id,
            SourceRecord.id == source_record_id,
        )
    )
    if source_record is None:
        raise RepositoryIntelligenceEvidenceError(
            "evidence source record is unavailable in the trusted workspace"
        )
    material = evidence.model_dump(mode="json", exclude_none=True)
    evidence_key = _sha256_json(
        {
            "source_record_id": source_record_id,
            "evidence": material,
        }
    )
    existing = await session.scalar(
        select(EvidenceRef)
        .where(
            EvidenceRef.workspace_id == workspace_id,
            EvidenceRef.evidence_key == evidence_key,
        )
        .with_for_update()
    )
    if existing is not None:
        return existing
    selector = _evidence_selector(evidence)
    row = EvidenceRef(
        workspace_id=workspace_id,
        source_record_id=source_record_id,
        evidence_key=evidence_key,
        evidence_kind=evidence.kind.value,
        evidence_source=evidence.source.value,
        selector=selector,
        field_path=selector,
        source_url=evidence.url,
        confidence=1.0,
    )
    session.add(row)
    await session.flush()
    return row


def _evidence_selector(evidence: EvidenceRefV1) -> str:
    for value in (
        evidence.ref,
        evidence.id,
        str(evidence.record_id) if evidence.record_id is not None else None,
        str(evidence.source_record_id)
        if evidence.source_record_id is not None
        else None,
    ):
        if value is not None:
            return value[:500]
    raise RepositoryIntelligenceEvidenceError(
        "evidence is missing a durable selector"
    )


def _run_source_manifest(
    *,
    run_id: UUID,
    payload: RepositoryIntelligenceV1,
    run_key: str,
    result_hash: str,
    status: str,
    coverage_status: str,
    coverage: RepositoryCoverageV1,
    artifact_manifest_hash: str,
    artifact_count: int,
) -> dict[str, Any]:
    material = {
        "schema_version": REPOSITORY_INTELLIGENCE_RUN_MANIFEST_VERSION,
        "run_id": str(run_id),
        "repository_id": str(payload.repository_id),
        "run_key": run_key,
        "result_hash": result_hash,
        "audit_level": payload.audit_level.value,
        "profile": payload.profile,
        "policy_hash": payload.policy_hash,
        "engine_version": payload.engine_version,
        "analysis_target": payload.analysis_target.model_dump(mode="json"),
        "status": status,
        "coverage_status": coverage_status,
        "coverage": coverage.model_dump(mode="json"),
        "artifact_manifest_hash": artifact_manifest_hash,
        "artifact_count": artifact_count,
        "retention": {
            "checkout": "deleted_on_exit",
            "artifact_days": REPOSITORY_ARTIFACT_RETENTION_DAYS,
            "canonical_records": "workspace_or_repository_deletion",
        },
    }
    if len(_strict_json(material)) > REPOSITORY_RUN_PAYLOAD_MAX_BYTES:
        raise RepositoryIntelligenceStateError(
            "repository run manifest exceeds the configured byte bound"
        )
    return material


def _validate_job_payload(
    *,
    job: RepositoryAnalysisJob,
    payload: RepositoryIntelligenceV1,
) -> None:
    expected = {
        "workspace_id": job.workspace_id,
        "repository_id": job.repository_id,
        "target_status": job.target_status,
        "commit_sha": job.commit_sha,
        "metadata_snapshot_id": job.metadata_snapshot_id,
        "audit_level": job.audit_level,
        "profile": job.profile,
        "policy_hash": job.policy_hash,
        "engine_version": job.engine_version,
    }
    actual = {
        "workspace_id": payload.workspace_id,
        "repository_id": payload.repository_id,
        "target_status": payload.analysis_target.target_status.value,
        "commit_sha": payload.analysis_target.commit_sha,
        "metadata_snapshot_id": payload.analysis_target.metadata_snapshot_id,
        "audit_level": payload.audit_level.value,
        "profile": payload.profile,
        "policy_hash": payload.policy_hash,
        "engine_version": payload.engine_version,
    }
    if expected != actual:
        raise RepositoryIntelligenceConflictError(
            "analysis result does not match its trusted job request"
        )


def _finish_job_from_run(
    job: RepositoryAnalysisJob,
    run: RepositoryAuditRun,
) -> None:
    job.status = (
        REPOSITORY_ANALYSIS_JOB_STATUS_SUCCEEDED
        if run.status == REPOSITORY_AUDIT_RUN_STATUS_SUCCEEDED
        else REPOSITORY_ANALYSIS_JOB_STATUS_PARTIAL
    )
    job.completed_at = run.completed_at
    job.lease_owner = None
    job.lease_expires_at = None
    job.error_code = None


def _finish_cancelled_job(
    job: RepositoryAnalysisJob,
    completed_at: datetime,
) -> None:
    job.status = REPOSITORY_ANALYSIS_JOB_STATUS_CANCELLED
    job.completed_at = completed_at
    job.lease_owner = None
    job.lease_expires_at = None
    job.error_code = None


async def _locked_job(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    job_id: UUID,
) -> RepositoryAnalysisJob:
    job = await session.scalar(
        select(RepositoryAnalysisJob)
        .where(
            RepositoryAnalysisJob.workspace_id == workspace_id,
            RepositoryAnalysisJob.id == job_id,
        )
        .with_for_update()
    )
    if job is None:
        raise RepositoryIntelligenceStateError("repository analysis job was not found")
    return job


async def _require_repository(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    repository_id: UUID,
) -> Repository:
    repository = await session.scalar(
        select(Repository).where(
            Repository.workspace_id == workspace_id,
            Repository.id == repository_id,
        )
    )
    if repository is None:
        raise RepositoryIntelligenceStateError(
            "repository is unavailable in the trusted workspace"
        )
    return repository


async def _require_admin_membership(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    user_id: UUID,
) -> Membership:
    membership = await session.scalar(
        select(Membership).where(
            Membership.workspace_id == workspace_id,
            Membership.user_id == user_id,
        )
    )
    if membership is None or membership.role not in {
        MEMBERSHIP_ROLE_OWNER,
        MEMBERSHIP_ROLE_ADMIN,
    }:
        raise RepositoryIntelligenceStateError(
            "repository intelligence mutation requires workspace owner or admin"
        )
    return membership


def _run_key(payload: RepositoryIntelligenceV1) -> str:
    return _sha256_json(
        {
            "workspace_id": payload.workspace_id,
            "repository_id": payload.repository_id,
            "analysis_target": payload.analysis_target.model_dump(mode="json"),
            "audit_level": payload.audit_level.value,
            "profile": payload.profile,
            "policy_hash": payload.policy_hash,
            "engine_version": payload.engine_version,
        }
    )


def _fingerprint(prefix: str, *parts: str) -> str:
    return sha256(
        _strict_json({"prefix": prefix, "parts": parts})
    ).hexdigest()


def _sha256_json(value: Any) -> str:
    return sha256(_strict_json(value)).hexdigest()


def _strict_json(value: Any) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        default=str,
    ).encode("utf-8")


def _aware_utc(value: datetime | None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise RepositoryIntelligenceStateError(
            "repository intelligence timestamp must be timezone-aware"
        )
    return current.astimezone(timezone.utc)


async def _repository_parent_ids(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    repository_id: UUID,
) -> dict[str, list[UUID]]:
    return {
        "fact": list(
            (
                await session.execute(
                    select(RepositoryFact.id).where(
                        RepositoryFact.workspace_id == workspace_id,
                        RepositoryFact.repository_id == repository_id,
                    )
                )
            ).scalars()
        ),
        "relationship": list(
            (
                await session.execute(
                    select(RepositoryRelationshipRecord.id).where(
                        RepositoryRelationshipRecord.workspace_id
                        == workspace_id,
                        RepositoryRelationshipRecord.from_repository_id
                        == repository_id,
                    )
                )
            ).scalars()
        ),
        "finding": list(
            (
                await session.execute(
                    select(RepositoryAuditFinding.id).where(
                        RepositoryAuditFinding.workspace_id == workspace_id,
                        RepositoryAuditFinding.repository_id == repository_id,
                    )
                )
            ).scalars()
        ),
        "contradiction": list(
            (
                await session.execute(
                    select(RepositoryContradiction.id).where(
                        RepositoryContradiction.workspace_id == workspace_id,
                        RepositoryContradiction.repository_id == repository_id,
                    )
                )
            ).scalars()
        ),
    }


async def _delete_evidence_links_for_parents(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    parent_ids: dict[str, list[UUID]],
) -> int:
    total = 0
    for parent_type, ids in parent_ids.items():
        if not ids:
            continue
        parent_column = getattr(RepositoryEvidenceLink, f"{parent_type}_id")
        total += await _delete_count(
            session,
            delete(RepositoryEvidenceLink).where(
                RepositoryEvidenceLink.workspace_id == workspace_id,
                parent_column.in_(ids),
            ),
        )
    return total


async def _delete_count(session: AsyncSession, statement: Any) -> int:
    result = await session.execute(statement)
    return int(getattr(result, "rowcount", 0) or 0)
