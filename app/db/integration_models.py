from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


INTEGRATION_PROVIDER_GITHUB = "github"
INTEGRATION_PROVIDER_JIRA = "jira"
INTEGRATION_PROVIDER_GMAIL = "gmail"
INTEGRATION_PROVIDER_DRIVE = "drive"

INTEGRATION_CONNECTION_STATUS_CONNECTED = "connected"
INTEGRATION_CONNECTION_STATUS_ERROR = "error"
INTEGRATION_CONNECTION_STATUS_REVOKED = "revoked"
INTEGRATION_CONNECTION_STATUS_DISABLED = "disabled"

SYNC_JOB_STATUS_QUEUED = "queued"
SYNC_JOB_STATUS_RUNNING = "running"
SYNC_JOB_STATUS_SUCCEEDED = "succeeded"
SYNC_JOB_STATUS_FAILED = "failed"
SYNC_JOB_STATUS_PARTIAL = "partial"

SYNC_JOB_TYPE_INITIAL = "initial"
SYNC_JOB_TYPE_INCREMENTAL = "incremental"
SYNC_JOB_TYPE_MANUAL = "manual"


class IntegrationConnection(Base):
    """Canonical workspace connection to an external provider.

    `external_account_id` is nullable for staged MVP setup, so this model avoids a
    nullable unique constraint and relies on explicit provider/account checks in
    future connector workflows.
    """

    __tablename__ = "integration_connections"
    __table_args__ = (
        CheckConstraint(
            "provider in ('github', 'jira', 'gmail', 'drive')",
            name="ck_integration_connections_provider",
        ),
        CheckConstraint(
            "status in ('connected', 'error', 'revoked', 'disabled')",
            name="ck_integration_connections_status",
        ),
        Index("ix_integration_connections_workspace_provider", "workspace_id", "provider"),
        Index(
            "ix_integration_connections_provider_external_account_id",
            "provider",
            "external_account_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces.id", name="fk_integration_connections_workspace_id"),
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(40), index=True)
    status: Mapped[str] = mapped_column(
        String(40), default=INTEGRATION_CONNECTION_STATUS_CONNECTED, index=True
    )
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_account_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    scopes: Mapped[list[str]] = mapped_column(JSON, default=list)
    encrypted_access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    encrypted_refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    provider_metadata: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    last_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SyncJob(Base):
    """Canonical sync job state for a provider connection.

    This row records sync lifecycle and counters only; it does not enqueue or run
    provider work.
    """

    __tablename__ = "sync_jobs"
    __table_args__ = (
        CheckConstraint(
            "provider in ('github', 'jira', 'gmail', 'drive')",
            name="ck_sync_jobs_provider",
        ),
        CheckConstraint(
            "status in ('queued', 'running', 'succeeded', 'failed', 'partial')",
            name="ck_sync_jobs_status",
        ),
        CheckConstraint(
            "sync_type in ('initial', 'incremental', 'manual')",
            name="ck_sync_jobs_sync_type",
        ),
        Index("ix_sync_jobs_workspace_status", "workspace_id", "status"),
        Index("ix_sync_jobs_connection_started_at", "connection_id", "started_at"),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces.id", name="fk_sync_jobs_workspace_id"),
        index=True,
    )
    connection_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("integration_connections.id", name="fk_sync_jobs_connection_id"),
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(40), index=True)
    status: Mapped[str] = mapped_column(
        String(40), default=SYNC_JOB_STATUS_QUEUED, index=True
    )
    sync_type: Mapped[str] = mapped_column(
        String(40), default=SYNC_JOB_TYPE_MANUAL, index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cursor_before: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    cursor_after: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    records_seen: Mapped[int] = mapped_column(Integer, default=0)
    records_created: Mapped[int] = mapped_column(Integer, default=0)
    records_updated: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    logs: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
