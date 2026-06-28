"""Canonical §6 data layer for the GitHub-first MVP spine.

This module is the canonical lineage per DEC-028. It adds the spine-critical
subset of the master-playbook §6 models alongside the existing
``integration_models`` / ``action_models`` foundation. The older knowledge-graph
lineage (``entities``/``source_events``/...) is frozen legacy and is not used or
written by the spine.

Scope of this subset (CHUNK 1 / FOS-002): SourceRecord (§6.7), EvidenceRef
(§6.8), Repository (§6.12), PullRequest (§6.13), Task (§6.11). NormalizedEntity
(§6.9) and other §6 models are deferred (see DEC-028). Person is not built
(post-MVP); ``*_person_id`` / ``project_id`` columns are nullable uuids with no
FK yet so they stay forward-compatible.
"""

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
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

# Register FK-target tables in the shared metadata whenever this module is
# imported, so the string foreign keys below resolve regardless of import order
# (workspaces -> identity_models; integration_connections / sync_jobs ->
# integration_models).
import app.db.identity_models  # noqa: E402,F401
import app.db.integration_models  # noqa: E402,F401

# SourceRecord providers (§6.7): external providers + internal founderOS objects.
SOURCE_RECORD_PROVIDER_GITHUB = "github"
SOURCE_RECORD_PROVIDER_JIRA = "jira"
SOURCE_RECORD_PROVIDER_GMAIL = "gmail"
SOURCE_RECORD_PROVIDER_DRIVE = "drive"
SOURCE_RECORD_PROVIDER_INTERNAL = "internal"

REPOSITORY_VISIBILITY_PUBLIC = "public"
REPOSITORY_VISIBILITY_PRIVATE = "private"
REPOSITORY_VISIBILITY_INTERNAL = "internal"

PULL_REQUEST_STATE_OPEN = "open"
PULL_REQUEST_STATE_CLOSED = "closed"
PULL_REQUEST_STATE_MERGED = "merged"

TASK_PROVIDER_GITHUB = "github"
TASK_PROVIDER_JIRA = "jira"
TASK_PROVIDER_INTERNAL = "internal"


class SourceRecord(Base):
    """Raw, append/update-by-observation snapshot of one external object (§6.7).

    One row per external object (upserted by observation), holding the full
    payload and its hash. This is the evidence base; tokens are never stored in
    ``payload``.
    """

    __tablename__ = "source_records"
    __table_args__ = (
        CheckConstraint(
            "provider in ('github', 'jira', 'gmail', 'drive', 'internal')",
            name="ck_source_records_provider",
        ),
        UniqueConstraint(
            "workspace_id",
            "provider",
            "external_id",
            name="uq_source_records_workspace_provider_external_id",
        ),
        Index("ix_source_records_workspace_record_type", "workspace_id", "record_type"),
        Index("ix_source_records_payload_hash", "payload_hash"),
        Index("ix_source_records_source_updated_at", "source_updated_at"),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces.id", name="fk_source_records_workspace_id"),
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(40), index=True)
    connection_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("integration_connections.id", name="fk_source_records_connection_id"),
        nullable=True,
        index=True,
    )
    external_id: Mapped[str] = mapped_column(String(255))
    record_type: Mapped[str] = mapped_column(String(120))
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    payload_hash: Mapped[str] = mapped_column(String(128))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sync_job_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("sync_jobs.id", name="fk_source_records_sync_job_id"),
        nullable=True,
        index=True,
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class EvidenceRef(Base):
    """Evidence linking a claim to a source record (§6.8).

    ``entity_id`` is a nullable uuid with no FK because NormalizedEntity is
    deferred (DEC-028); it can become a FK when that table is added.
    """

    __tablename__ = "evidence_refs"
    __table_args__ = (
        Index("ix_evidence_refs_workspace_id", "workspace_id"),
        Index("ix_evidence_refs_source_record_id", "source_record_id"),
        Index("ix_evidence_refs_entity_id", "entity_id"),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces.id", name="fk_evidence_refs_workspace_id"),
    )
    source_record_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("source_records.id", name="fk_evidence_refs_source_record_id"),
    )
    entity_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    field_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Repository(Base):
    """Normalized GitHub repository (§6.12)."""

    __tablename__ = "repositories"
    __table_args__ = (
        CheckConstraint(
            "provider in ('github')",
            name="ck_repositories_provider",
        ),
        CheckConstraint(
            "visibility in ('public', 'private', 'internal')",
            name="ck_repositories_visibility",
        ),
        UniqueConstraint(
            "workspace_id",
            "external_id",
            name="uq_repositories_workspace_external_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces.id", name="fk_repositories_workspace_id"),
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(40), default=SOURCE_RECORD_PROVIDER_GITHUB)
    external_id: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(500))
    default_branch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    visibility: Mapped[str | None] = mapped_column(String(20), nullable=True)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    repo_metadata: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    last_activity_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PullRequest(Base):
    """Normalized GitHub pull request (§6.13).

    ``author_person_id`` is a nullable uuid with no FK (Person deferred, DEC-028).
    """

    __tablename__ = "pull_requests"
    __table_args__ = (
        CheckConstraint(
            "state in ('open', 'closed', 'merged')",
            name="ck_pull_requests_state",
        ),
        UniqueConstraint(
            "workspace_id",
            "external_id",
            name="uq_pull_requests_workspace_external_id",
        ),
        Index("ix_pull_requests_repository_id", "repository_id"),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces.id", name="fk_pull_requests_workspace_id"),
        index=True,
    )
    repository_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("repositories.id", name="fk_pull_requests_repository_id"),
    )
    external_id: Mapped[str] = mapped_column(String(255))
    number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(500))
    state: Mapped[str] = mapped_column(String(20), index=True)
    author_person_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at_source: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at_source: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    merged_at_source: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    pr_metadata: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Task(Base):
    """Normalized task from GitHub/Jira/internal (§6.11).

    ``project_id`` and ``assignee_person_id`` are nullable uuids with no FK
    (Project and Person deferred, DEC-028).
    """

    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint(
            "source_provider in ('github', 'jira', 'internal')",
            name="ck_tasks_source_provider",
        ),
        Index("ix_tasks_workspace_status", "workspace_id", "status"),
        Index("ix_tasks_workspace_assignee", "workspace_id", "assignee_person_id"),
        Index("ix_tasks_provider_external_id", "source_provider", "external_id"),
        # Canonical Task identity. PARTIAL so manually-created / non-provider
        # tasks (external_id IS NULL) are never constrained or de-duplicated;
        # only provider-keyed rows must be unique. Backs the idempotent
        # ON CONFLICT upsert in github_normalization_service.
        Index(
            "uq_tasks_workspace_provider_external_id",
            "workspace_id",
            "source_provider",
            "external_id",
            unique=True,
            postgresql_where=text("external_id IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces.id", name="fk_tasks_workspace_id"),
        index=True,
    )
    source_provider: Mapped[str] = mapped_column(String(40))
    source_record_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("source_records.id", name="fk_tasks_source_record_id"),
        nullable=True,
        index=True,
    )
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    project_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str | None] = mapped_column(String(120), nullable=True)
    priority: Mapped[str | None] = mapped_column(String(40), nullable=True)
    assignee_person_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    task_metadata: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # "Last synced" marker: bumped every time a sync writes this row, NOT a
    # content-change marker. User-facing recency comes from source_updated_at
    # (the upstream GitHub activity time); updated_at is only a secondary
    # ORDER BY tiebreak in the operational read model.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    source_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
