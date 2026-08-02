"""Durable Repository Intelligence persistence models (RI-006).

PostgreSQL stores only strict run metadata, evidence-backed facts, directional
relationships, findings, contradictions, and lifecycle state. Repository
checkout contents and unbounded analyzer artifacts never enter these tables.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base

# Register all FK targets in the shared metadata regardless of import order.
import app.db.canonical_models  # noqa: E402,F401
import app.db.identity_models  # noqa: E402,F401


REPOSITORY_ANALYSIS_JOB_STATUS_QUEUED = "queued"
REPOSITORY_ANALYSIS_JOB_STATUS_RUNNING = "running"
REPOSITORY_ANALYSIS_JOB_STATUS_SUCCEEDED = "succeeded"
REPOSITORY_ANALYSIS_JOB_STATUS_FAILED = "failed"
REPOSITORY_ANALYSIS_JOB_STATUS_PARTIAL = "partial"
REPOSITORY_ANALYSIS_JOB_STATUS_CANCELLED = "cancelled"

REPOSITORY_AUDIT_RUN_STATUS_SUCCEEDED = "succeeded"
REPOSITORY_AUDIT_RUN_STATUS_PARTIAL = "partial"
REPOSITORY_AUDIT_RUN_STATUS_FAILED = "failed"
REPOSITORY_AUDIT_RUN_STATUS_CANCELLED = "cancelled"

REPOSITORY_COVERAGE_STATUS_COMPLETE = "complete"
REPOSITORY_COVERAGE_STATUS_PARTIAL = "partial"

REPOSITORY_CLAIM_STATUS_OBSERVED = "observed"
REPOSITORY_CLAIM_STATUS_INFERRED = "inferred"
REPOSITORY_CLAIM_STATUS_INSUFFICIENT_EVIDENCE = "insufficient_evidence"

REPOSITORY_LIFECYCLE_STATUS_CURRENT = "current"
REPOSITORY_LIFECYCLE_STATUS_STALE = "stale"

REPOSITORY_HUMAN_RESOLUTION_PENDING = "pending"
REPOSITORY_HUMAN_RESOLUTION_CONFIRMED = "confirmed"
REPOSITORY_HUMAN_RESOLUTION_REJECTED = "rejected"

REPOSITORY_FINDING_STATUS_NEW = "new"
REPOSITORY_FINDING_STATUS_OPEN = "open"
REPOSITORY_FINDING_STATUS_RESOLVED = "resolved"
REPOSITORY_FINDING_STATUS_REGRESSED = "regressed"
REPOSITORY_FINDING_STATUS_ACCEPTED_RISK = "accepted_risk"
REPOSITORY_FINDING_STATUS_FALSE_POSITIVE = "false_positive"
REPOSITORY_FINDING_STATUS_INSUFFICIENT_EVIDENCE = "insufficient_evidence"

REPOSITORY_CONTRADICTION_STATUS_CURRENT = "current"
REPOSITORY_CONTRADICTION_STATUS_RESOLVED = "resolved"

REPOSITORY_EVIDENCE_ROLE_SUPPORTING = "supporting"
REPOSITORY_EVIDENCE_ROLE_CONTRADICTING = "contradicting"

REPOSITORY_RETENTION_POLICY_WORKSPACE_CANONICAL = "workspace_canonical"


class RepositoryAnalysisJob(Base):
    """One durable, retryable analysis request for one repository."""

    __tablename__ = "repository_analysis_jobs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "repository_id"],
            ["repositories.workspace_id", "repositories.id"],
            name="fk_repository_analysis_jobs_workspace_repository",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "workspace_id",
            "id",
            name="uq_repository_analysis_jobs_workspace_id_id",
        ),
        UniqueConstraint(
            "workspace_id",
            "repository_id",
            "id",
            name="uq_repository_analysis_jobs_workspace_repository_id",
        ),
        UniqueConstraint(
            "workspace_id",
            "idempotency_key",
            name="uq_repository_analysis_jobs_workspace_idempotency_key",
        ),
        CheckConstraint(
            "status in "
            "('queued','running','succeeded','failed','partial','cancelled')",
            name="ck_repository_analysis_jobs_status",
        ),
        CheckConstraint(
            "audit_level in ('L0','L1','L2')",
            name="ck_repository_analysis_jobs_audit_level",
        ),
        CheckConstraint(
            "target_status in ('exact','unavailable')",
            name="ck_repository_analysis_jobs_target_status",
        ),
        CheckConstraint(
            "("
            "target_status = 'exact' "
            "and commit_sha is not null "
            "and metadata_snapshot_id is null"
            ") or ("
            "target_status = 'unavailable' "
            "and commit_sha is null "
            "and metadata_snapshot_id is not null"
            ")",
            name="ck_repository_analysis_jobs_target_shape",
        ),
        CheckConstraint(
            "audit_level = 'L0' or target_status = 'exact'",
            name="ck_repository_analysis_jobs_exact_deep_target",
        ),
        CheckConstraint(
            "commit_sha is null or commit_sha ~ '^[0-9a-f]{40}$'",
            name="ck_repository_analysis_jobs_commit_sha",
        ),
        CheckConstraint(
            "policy_hash ~ '^[0-9a-f]{64}$' and "
            "request_hash ~ '^[0-9a-f]{64}$'",
            name="ck_repository_analysis_jobs_hashes",
        ),
        CheckConstraint(
            "attempt_count >= 0 and max_attempts >= 1 "
            "and attempt_count <= max_attempts",
            name="ck_repository_analysis_jobs_attempts",
        ),
        CheckConstraint(
            "(lease_owner is null and lease_expires_at is null) or "
            "(lease_owner is not null and lease_expires_at is not null)",
            name="ck_repository_analysis_jobs_lease_shape",
        ),
        CheckConstraint(
            "completed_at is null or status in "
            "('succeeded','failed','partial','cancelled')",
            name="ck_repository_analysis_jobs_completed_status",
        ),
        Index(
            "ix_repository_analysis_jobs_claim",
            "workspace_id",
            "status",
            "next_attempt_at",
            "lease_expires_at",
        ),
        Index(
            "ix_repository_analysis_jobs_repository_created",
            "workspace_id",
            "repository_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "workspaces.id",
            name="fk_repository_analysis_jobs_workspace_id",
            ondelete="CASCADE",
        ),
    )
    repository_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    requested_by_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "users.id",
            name="fk_repository_analysis_jobs_requested_by_user_id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    idempotency_key: Mapped[str] = mapped_column(String(128))
    request_hash: Mapped[str] = mapped_column(String(64))
    target_status: Mapped[str] = mapped_column(String(20))
    commit_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)
    metadata_snapshot_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    audit_level: Mapped[str] = mapped_column(String(2))
    profile: Mapped[str] = mapped_column(String(80))
    policy_hash: Mapped[str] = mapped_column(String(64))
    engine_version: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(
        String(20),
        default=REPOSITORY_ANALYSIS_JOB_STATUS_QUEUED,
        server_default=REPOSITORY_ANALYSIS_JOB_STATUS_QUEUED,
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
    )
    max_attempts: Mapped[int] = mapped_column(
        Integer,
        default=3,
        server_default="3",
    )
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    lease_owner: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    cancel_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class RepositoryAuditRun(Base):
    """Immutable header and sanitized artifact manifest for one analyzer result."""

    __tablename__ = "repository_audit_runs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "repository_id"],
            ["repositories.workspace_id", "repositories.id"],
            name="fk_repository_audit_runs_workspace_repository",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "repository_id", "job_id"],
            [
                "repository_analysis_jobs.workspace_id",
                "repository_analysis_jobs.repository_id",
                "repository_analysis_jobs.id",
            ],
            name="fk_repository_audit_runs_workspace_repository_job",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "source_record_id"],
            ["source_records.workspace_id", "source_records.id"],
            name="fk_repository_audit_runs_workspace_source_record",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "workspace_id",
            "id",
            name="uq_repository_audit_runs_workspace_id_id",
        ),
        UniqueConstraint(
            "workspace_id",
            "repository_id",
            "id",
            name="uq_repository_audit_runs_workspace_repository_id",
        ),
        UniqueConstraint(
            "workspace_id",
            "job_id",
            name="uq_repository_audit_runs_workspace_job_id",
        ),
        UniqueConstraint(
            "workspace_id",
            "source_record_id",
            name="uq_repository_audit_runs_workspace_source_record_id",
        ),
        CheckConstraint(
            "status in ('succeeded','partial','failed','cancelled')",
            name="ck_repository_audit_runs_status",
        ),
        CheckConstraint(
            "coverage_status in ('complete','partial')",
            name="ck_repository_audit_runs_coverage_status",
        ),
        CheckConstraint(
            "(status = 'succeeded' and coverage_status = 'complete') or "
            "(status <> 'succeeded' and coverage_status = 'partial')",
            name="ck_repository_audit_runs_status_coverage",
        ),
        CheckConstraint(
            "not reconciliation_applied or "
            "(status = 'succeeded' and coverage_status = 'complete')",
            name="ck_repository_audit_runs_reconciliation",
        ),
        CheckConstraint(
            "audit_level in ('L0','L1','L2')",
            name="ck_repository_audit_runs_audit_level",
        ),
        CheckConstraint(
            "target_status in ('exact','unavailable')",
            name="ck_repository_audit_runs_target_status",
        ),
        CheckConstraint(
            "("
            "target_status = 'exact' "
            "and commit_sha is not null "
            "and metadata_snapshot_id is null"
            ") or ("
            "target_status = 'unavailable' "
            "and commit_sha is null "
            "and metadata_snapshot_id is not null"
            ")",
            name="ck_repository_audit_runs_target_shape",
        ),
        CheckConstraint(
            "audit_level = 'L0' or target_status = 'exact'",
            name="ck_repository_audit_runs_exact_deep_target",
        ),
        CheckConstraint(
            "commit_sha is null or commit_sha ~ '^[0-9a-f]{40}$'",
            name="ck_repository_audit_runs_commit_sha",
        ),
        CheckConstraint(
            "policy_hash ~ '^[0-9a-f]{64}$'",
            name="ck_repository_audit_runs_policy_hash",
        ),
        CheckConstraint(
            "result_hash ~ '^[0-9a-f]{64}$' and "
            "run_key ~ '^[0-9a-f]{64}$' and "
            "artifact_manifest_hash ~ '^[0-9a-f]{64}$'",
            name="ck_repository_audit_runs_hashes",
        ),
        CheckConstraint(
            "completed_at >= started_at",
            name="ck_repository_audit_runs_time_order",
        ),
        CheckConstraint(
            "retention_policy = 'workspace_canonical'",
            name="ck_repository_audit_runs_retention_policy",
        ),
        Index(
            "ix_repository_audit_runs_repository_completed",
            "workspace_id",
            "repository_id",
            "completed_at",
        ),
        Index(
            "ix_repository_audit_runs_run_key",
            "workspace_id",
            "run_key",
        ),
        Index(
            "ix_repository_audit_runs_artifact_expiry",
            "workspace_id",
            "artifact_expires_at",
            postgresql_where=text("artifact_purged_at IS NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "workspaces.id",
            name="fk_repository_audit_runs_workspace_id",
            ondelete="CASCADE",
        ),
    )
    repository_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    job_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    source_record_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    run_key: Mapped[str] = mapped_column(String(64))
    result_hash: Mapped[str] = mapped_column(String(64))
    target_status: Mapped[str] = mapped_column(String(20))
    commit_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)
    metadata_snapshot_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    audit_level: Mapped[str] = mapped_column(String(2))
    profile: Mapped[str] = mapped_column(String(80))
    policy_hash: Mapped[str] = mapped_column(String(64))
    engine_version: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(20))
    coverage_status: Mapped[str] = mapped_column(String(20))
    coverage: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    reconciliation_applied: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
    )
    limitations: Mapped[list[str]] = mapped_column(JSON, default=list)
    artifact_manifest: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON,
        default=list,
    )
    artifact_manifest_hash: Mapped[str] = mapped_column(String(64))
    artifact_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True)
    )
    artifact_purged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    retention_policy: Mapped[str] = mapped_column(
        String(40),
        default=REPOSITORY_RETENTION_POLICY_WORKSPACE_CANONICAL,
        server_default=REPOSITORY_RETENTION_POLICY_WORKSPACE_CANONICAL,
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )


class RepositoryFact(Base):
    """One reconciled evidence-backed repository claim or explicit unknown."""

    __tablename__ = "repository_facts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "repository_id"],
            ["repositories.workspace_id", "repositories.id"],
            name="fk_repository_facts_workspace_repository",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "repository_id", "first_seen_run_id"],
            [
                "repository_audit_runs.workspace_id",
                "repository_audit_runs.repository_id",
                "repository_audit_runs.id",
            ],
            name="fk_repository_facts_workspace_repository_first_run",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "repository_id", "last_seen_run_id"],
            [
                "repository_audit_runs.workspace_id",
                "repository_audit_runs.repository_id",
                "repository_audit_runs.id",
            ],
            name="fk_repository_facts_workspace_repository_last_run",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "workspace_id",
            "id",
            name="uq_repository_facts_workspace_id_id",
        ),
        UniqueConstraint(
            "workspace_id",
            "repository_id",
            "id",
            name="uq_repository_facts_workspace_repository_id",
        ),
        UniqueConstraint(
            "workspace_id",
            "repository_id",
            "fingerprint",
            name="uq_repository_facts_workspace_repository_fingerprint",
        ),
        CheckConstraint(
            "claim_status in ('observed','inferred','insufficient_evidence')",
            name="ck_repository_facts_claim_status",
        ),
        CheckConstraint(
            "lifecycle_status in ('current','stale')",
            name="ck_repository_facts_lifecycle_status",
        ),
        CheckConstraint(
            "confidence >= 0 and confidence <= 1",
            name="ck_repository_facts_confidence",
        ),
        CheckConstraint(
            "human_resolution_status in ('pending','confirmed','rejected')",
            name="ck_repository_facts_human_resolution_status",
        ),
        CheckConstraint(
            "("
            "human_resolution_status = 'pending' "
            "and resolved_by_user_id is null "
            "and resolved_at is null"
            ") or ("
            "human_resolution_status in ('confirmed','rejected') "
            "and resolved_by_user_id is not null "
            "and resolved_at is not null"
            ")",
            name="ck_repository_facts_human_resolution_provenance",
        ),
        Index(
            "ix_repository_facts_workspace_lifecycle",
            "workspace_id",
            "lifecycle_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "workspaces.id",
            name="fk_repository_facts_workspace_id",
            ondelete="CASCADE",
        ),
    )
    repository_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    fingerprint: Mapped[str] = mapped_column(String(64))
    claim_id: Mapped[str] = mapped_column(String(128))
    fact_type: Mapped[str] = mapped_column(String(80))
    value: Mapped[dict[str, Any]] = mapped_column(JSON)
    claim_status: Mapped[str] = mapped_column(String(30))
    confidence: Mapped[float] = mapped_column(Float)
    lifecycle_status: Mapped[str] = mapped_column(
        String(20),
        default=REPOSITORY_LIFECYCLE_STATUS_CURRENT,
        server_default=REPOSITORY_LIFECYCLE_STATUS_CURRENT,
    )
    first_seen_run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    last_seen_run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    stale_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    human_resolution_status: Mapped[str] = mapped_column(
        String(20),
        default=REPOSITORY_HUMAN_RESOLUTION_PENDING,
        server_default=REPOSITORY_HUMAN_RESOLUTION_PENDING,
    )
    resolved_by_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "users.id",
            name="fk_repository_facts_resolved_by_user_id",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class RepositoryRelationshipRecord(Base):
    """One reconciled directional repository relationship candidate."""

    __tablename__ = "repository_relationships"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "from_repository_id"],
            ["repositories.workspace_id", "repositories.id"],
            name="fk_repository_relationships_workspace_from_repository",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "to_repository_id"],
            ["repositories.workspace_id", "repositories.id"],
            name="fk_repository_relationships_workspace_to_repository",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "from_repository_id", "first_seen_run_id"],
            [
                "repository_audit_runs.workspace_id",
                "repository_audit_runs.repository_id",
                "repository_audit_runs.id",
            ],
            name="fk_repository_relationships_workspace_source_first_run",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "from_repository_id", "last_seen_run_id"],
            [
                "repository_audit_runs.workspace_id",
                "repository_audit_runs.repository_id",
                "repository_audit_runs.id",
            ],
            name="fk_repository_relationships_workspace_source_last_run",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "workspace_id",
            "id",
            name="uq_repository_relationships_workspace_id_id",
        ),
        UniqueConstraint(
            "workspace_id",
            "from_repository_id",
            "id",
            name="uq_repository_relationships_workspace_source_id",
        ),
        UniqueConstraint(
            "workspace_id",
            "from_repository_id",
            "fingerprint",
            name="uq_repository_relationships_workspace_from_fingerprint",
        ),
        CheckConstraint(
            "relationship_type in ("
            "'calls_api_of','imports_package_from','consumes_event_from',"
            "'deployed_by','uses_image_from','generates_client_for','tests',"
            "'documents','replaces','forked_from','duplicate_candidate_of',"
            "'operationally_coupled_with','shares_schema_with',"
            "'shares_database_with','owns_migrations_for'"
            ")",
            name="ck_repository_relationships_type",
        ),
        CheckConstraint(
            "claim_status in ('observed','inferred')",
            name="ck_repository_relationships_claim_status",
        ),
        CheckConstraint(
            "lifecycle_status in ('current','stale')",
            name="ck_repository_relationships_lifecycle_status",
        ),
        CheckConstraint(
            "confidence >= 0 and confidence <= 1",
            name="ck_repository_relationships_confidence",
        ),
        CheckConstraint(
            "resolution_status in ('canonical','candidate')",
            name="ck_repository_relationships_resolution_status",
        ),
        CheckConstraint(
            "("
            "resolution_status = 'canonical' and to_repository_id is not null"
            ") or ("
            "resolution_status = 'candidate' and to_repository_id is null"
            ")",
            name="ck_repository_relationships_resolution_shape",
        ),
        CheckConstraint(
            "to_repository_id is null or "
            "from_repository_id <> to_repository_id",
            name="ck_repository_relationships_no_self_edge",
        ),
        CheckConstraint(
            "human_resolution_status in ('pending','confirmed','rejected')",
            name="ck_repository_relationships_human_resolution_status",
        ),
        CheckConstraint(
            "("
            "human_resolution_status = 'pending' "
            "and resolved_by_user_id is null "
            "and resolved_at is null"
            ") or ("
            "human_resolution_status in ('confirmed','rejected') "
            "and resolved_by_user_id is not null "
            "and resolved_at is not null"
            ")",
            name="ck_repository_relationships_human_resolution_provenance",
        ),
        Index(
            "ix_repository_relationships_workspace_lifecycle",
            "workspace_id",
            "lifecycle_status",
        ),
        Index(
            "ix_repository_relationships_workspace_target",
            "workspace_id",
            "to_repository_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "workspaces.id",
            name="fk_repository_relationships_workspace_id",
            ondelete="CASCADE",
        ),
    )
    from_repository_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    to_repository_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    fingerprint: Mapped[str] = mapped_column(String(64))
    relationship_type: Mapped[str] = mapped_column(String(80))
    target_provider: Mapped[str] = mapped_column(String(40))
    target_external_id: Mapped[str] = mapped_column(String(255))
    target_full_name: Mapped[str] = mapped_column(String(500))
    resolution_status: Mapped[str] = mapped_column(String(20))
    summary: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    claim_status: Mapped[str] = mapped_column(String(20))
    confidence: Mapped[float] = mapped_column(Float)
    lifecycle_status: Mapped[str] = mapped_column(
        String(20),
        default=REPOSITORY_LIFECYCLE_STATUS_CURRENT,
        server_default=REPOSITORY_LIFECYCLE_STATUS_CURRENT,
    )
    first_seen_run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    last_seen_run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    stale_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    human_resolution_status: Mapped[str] = mapped_column(
        String(20),
        default=REPOSITORY_HUMAN_RESOLUTION_PENDING,
        server_default=REPOSITORY_HUMAN_RESOLUTION_PENDING,
    )
    resolved_by_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "users.id",
            name="fk_repository_relationships_resolved_by_user_id",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class RepositoryAuditFinding(Base):
    """One durable audit finding with fix/regression and human-decision state."""

    __tablename__ = "repository_audit_findings"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "repository_id"],
            ["repositories.workspace_id", "repositories.id"],
            name="fk_repository_audit_findings_workspace_repository",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "repository_id", "first_seen_run_id"],
            [
                "repository_audit_runs.workspace_id",
                "repository_audit_runs.repository_id",
                "repository_audit_runs.id",
            ],
            name="fk_repository_audit_findings_workspace_repository_first_run",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "repository_id", "last_seen_run_id"],
            [
                "repository_audit_runs.workspace_id",
                "repository_audit_runs.repository_id",
                "repository_audit_runs.id",
            ],
            name="fk_repository_audit_findings_workspace_repository_last_run",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "workspace_id",
            "id",
            name="uq_repository_audit_findings_workspace_id_id",
        ),
        UniqueConstraint(
            "workspace_id",
            "repository_id",
            "id",
            name="uq_repository_audit_findings_workspace_repository_id",
        ),
        UniqueConstraint(
            "workspace_id",
            "repository_id",
            "fingerprint",
            name="uq_repository_audit_findings_workspace_repository_fingerprint",
        ),
        CheckConstraint(
            "severity in ('info','low','medium','high','critical')",
            name="ck_repository_audit_findings_severity",
        ),
        CheckConstraint(
            "status in ("
            "'new','open','resolved','regressed','accepted_risk',"
            "'false_positive','insufficient_evidence'"
            ")",
            name="ck_repository_audit_findings_status",
        ),
        CheckConstraint(
            "confidence >= 0 and confidence <= 1",
            name="ck_repository_audit_findings_confidence",
        ),
        CheckConstraint(
            "("
            "status in ('accepted_risk','false_positive') "
            "and decided_by_user_id is not null "
            "and decided_at is not null"
            ") or ("
            "status not in ('accepted_risk','false_positive')"
            ")",
            name="ck_repository_audit_findings_human_decision",
        ),
        Index(
            "ix_repository_audit_findings_workspace_status",
            "workspace_id",
            "status",
        ),
        Index(
            "ix_repository_audit_findings_workspace_severity",
            "workspace_id",
            "severity",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "workspaces.id",
            name="fk_repository_audit_findings_workspace_id",
            ondelete="CASCADE",
        ),
    )
    repository_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    fingerprint: Mapped[str] = mapped_column(String(64))
    finding_id: Mapped[str] = mapped_column(String(128))
    rule_id: Mapped[str] = mapped_column(String(128))
    category: Mapped[str] = mapped_column(String(80))
    severity: Mapped[str] = mapped_column(String(20))
    confidence: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(
        String(30),
        default=REPOSITORY_FINDING_STATUS_NEW,
        server_default=REPOSITORY_FINDING_STATUS_NEW,
    )
    title: Mapped[str] = mapped_column(String(500))
    summary: Mapped[str] = mapped_column(Text)
    recommended_next_step: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
    )
    first_seen_run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    last_seen_run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    decided_by_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "users.id",
            name="fk_repository_audit_findings_decided_by_user_id",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class RepositoryContradiction(Base):
    """One preserved contradiction between two evidence-backed repository facts."""

    __tablename__ = "repository_contradictions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "repository_id"],
            ["repositories.workspace_id", "repositories.id"],
            name="fk_repository_contradictions_workspace_repository",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "repository_id", "left_fact_id"],
            [
                "repository_facts.workspace_id",
                "repository_facts.repository_id",
                "repository_facts.id",
            ],
            name="fk_repository_contradictions_workspace_repository_left_fact",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "repository_id", "right_fact_id"],
            [
                "repository_facts.workspace_id",
                "repository_facts.repository_id",
                "repository_facts.id",
            ],
            name="fk_repository_contradictions_workspace_repository_right_fact",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "repository_id", "first_seen_run_id"],
            [
                "repository_audit_runs.workspace_id",
                "repository_audit_runs.repository_id",
                "repository_audit_runs.id",
            ],
            name="fk_repository_contradictions_workspace_repository_first_run",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "repository_id", "last_seen_run_id"],
            [
                "repository_audit_runs.workspace_id",
                "repository_audit_runs.repository_id",
                "repository_audit_runs.id",
            ],
            name="fk_repository_contradictions_workspace_repository_last_run",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "workspace_id",
            "id",
            name="uq_repository_contradictions_workspace_id_id",
        ),
        UniqueConstraint(
            "workspace_id",
            "repository_id",
            "id",
            name="uq_repository_contradictions_workspace_repository_id",
        ),
        UniqueConstraint(
            "workspace_id",
            "repository_id",
            "fingerprint",
            name="uq_repository_contradictions_workspace_repository_fingerprint",
        ),
        CheckConstraint(
            "left_fact_id <> right_fact_id",
            name="ck_repository_contradictions_distinct_facts",
        ),
        CheckConstraint(
            "status in ('current','resolved')",
            name="ck_repository_contradictions_status",
        ),
        CheckConstraint(
            "confidence >= 0 and confidence <= 1",
            name="ck_repository_contradictions_confidence",
        ),
        Index(
            "ix_repository_contradictions_workspace_status",
            "workspace_id",
            "status",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "workspaces.id",
            name="fk_repository_contradictions_workspace_id",
            ondelete="CASCADE",
        ),
    )
    repository_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    fingerprint: Mapped[str] = mapped_column(String(64))
    contradiction_id: Mapped[str] = mapped_column(String(128))
    left_fact_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    right_fact_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    status: Mapped[str] = mapped_column(
        String(20),
        default=REPOSITORY_CONTRADICTION_STATUS_CURRENT,
        server_default=REPOSITORY_CONTRADICTION_STATUS_CURRENT,
    )
    confidence: Mapped[float] = mapped_column(Float)
    summary: Mapped[str] = mapped_column(String(1000))
    first_seen_run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    last_seen_run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class RepositoryEvidenceLink(Base):
    """Workspace-safe link from one RI entity to canonical ``EvidenceRef``."""

    __tablename__ = "repository_evidence_links"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "evidence_ref_id"],
            ["evidence_refs.workspace_id", "evidence_refs.id"],
            name="fk_repository_evidence_links_workspace_evidence",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "fact_id"],
            ["repository_facts.workspace_id", "repository_facts.id"],
            name="fk_repository_evidence_links_workspace_fact",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "relationship_id"],
            [
                "repository_relationships.workspace_id",
                "repository_relationships.id",
            ],
            name="fk_repository_evidence_links_workspace_relationship",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "finding_id"],
            [
                "repository_audit_findings.workspace_id",
                "repository_audit_findings.id",
            ],
            name="fk_repository_evidence_links_workspace_finding",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "contradiction_id"],
            [
                "repository_contradictions.workspace_id",
                "repository_contradictions.id",
            ],
            name="fk_repository_evidence_links_workspace_contradiction",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "evidence_role in ('supporting','contradicting')",
            name="ck_repository_evidence_links_role",
        ),
        CheckConstraint(
            "num_nonnulls(fact_id,relationship_id,finding_id,contradiction_id) = 1",
            name="ck_repository_evidence_links_one_parent",
        ),
        Index(
            "uq_repository_evidence_links_fact",
            "workspace_id",
            "fact_id",
            "evidence_ref_id",
            "evidence_role",
            unique=True,
            postgresql_where=text("fact_id IS NOT NULL"),
        ),
        Index(
            "uq_repository_evidence_links_relationship",
            "workspace_id",
            "relationship_id",
            "evidence_ref_id",
            "evidence_role",
            unique=True,
            postgresql_where=text("relationship_id IS NOT NULL"),
        ),
        Index(
            "uq_repository_evidence_links_finding",
            "workspace_id",
            "finding_id",
            "evidence_ref_id",
            "evidence_role",
            unique=True,
            postgresql_where=text("finding_id IS NOT NULL"),
        ),
        Index(
            "uq_repository_evidence_links_contradiction",
            "workspace_id",
            "contradiction_id",
            "evidence_ref_id",
            "evidence_role",
            unique=True,
            postgresql_where=text("contradiction_id IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "workspaces.id",
            name="fk_repository_evidence_links_workspace_id",
            ondelete="CASCADE",
        ),
    )
    evidence_ref_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    evidence_role: Mapped[str] = mapped_column(String(20))
    fact_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    relationship_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    finding_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    contradiction_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
