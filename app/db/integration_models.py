from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


INTEGRATION_PROVIDER_GITHUB = "github"
INTEGRATION_PROVIDER_JIRA = "jira"
INTEGRATION_PROVIDER_GMAIL = "gmail"
INTEGRATION_PROVIDER_DRIVE = "drive"
AI_PROVIDER_OPENAI = "openai"
AI_REASONING_EFFORT_LOW = "low"
AI_REASONING_EFFORT_MEDIUM = "medium"
AI_REASONING_EFFORT_HIGH = "high"
AI_CHECK_STATUS_PASSED = "passed"
AI_CHECK_STATUS_FAILED = "failed"

INTEGRATION_CONNECTION_STATUS_CONNECTED = "connected"
INTEGRATION_CONNECTION_STATUS_ERROR = "error"
INTEGRATION_CONNECTION_STATUS_REVOKED = "revoked"
INTEGRATION_CONNECTION_STATUS_DISABLED = "disabled"

SYNC_JOB_STATUS_QUEUED = "queued"
SYNC_JOB_STATUS_RUNNING = "running"
SYNC_JOB_STATUS_SUCCEEDED = "succeeded"
SYNC_JOB_STATUS_FAILED = "failed"
SYNC_JOB_STATUS_PARTIAL = "partial"
SYNC_JOB_STATUS_CANCELLED = "cancelled"

SYNC_JOB_TYPE_INITIAL = "initial"
SYNC_JOB_TYPE_INCREMENTAL = "incremental"
SYNC_JOB_TYPE_MANUAL = "manual"

GITHUB_APP_CREDENTIAL_STATUS_ACTIVE = "active"
GITHUB_APP_CREDENTIAL_STATUS_ERROR = "error"
GITHUB_APP_CREDENTIAL_STATUS_REVOKED = "revoked"

GITHUB_APP_INSTALLATION_STATUS_ACTIVE = "active"
GITHUB_APP_INSTALLATION_STATUS_SUSPENDED = "suspended"
GITHUB_APP_INSTALLATION_STATUS_REVOKED = "revoked"

GITHUB_APP_SETUP_PHASE_MANIFEST_PENDING = "manifest_pending"
GITHUB_APP_SETUP_PHASE_MANIFEST_EXCHANGING = "manifest_exchanging"
GITHUB_APP_SETUP_PHASE_INSTALLATION_PENDING = "installation_pending"
GITHUB_APP_SETUP_PHASE_OAUTH_PENDING = "oauth_pending"
GITHUB_APP_SETUP_PHASE_OAUTH_EXCHANGING = "oauth_exchanging"
GITHUB_APP_SETUP_PHASE_REPOSITORY_SELECTION = "repository_selection"
GITHUB_APP_SETUP_PHASE_COMPLETED = "completed"
GITHUB_APP_SETUP_PHASE_FAILED = "failed"
GITHUB_APP_SETUP_PHASE_CANCELLED = "cancelled"


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


class WorkspaceAIConfiguration(Base):
    """Encrypted, workspace-owned configuration for the optional AI path."""

    __tablename__ = "workspace_ai_configurations"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            name="uq_workspace_ai_configurations_workspace_id",
        ),
        CheckConstraint(
            "provider = 'openai'",
            name="ck_workspace_ai_configurations_provider",
        ),
        CheckConstraint(
            "reasoning_effort in ('low', 'medium', 'high')",
            name="ck_workspace_ai_configurations_reasoning_effort",
        ),
        CheckConstraint(
            "max_output_tokens >= 400 and max_output_tokens <= 4000",
            name="ck_workspace_ai_configurations_output_budget",
        ),
        CheckConstraint(
            "configuration_version >= 1",
            name="ck_workspace_ai_configurations_version",
        ),
        CheckConstraint(
            "last_check_status is null or last_check_status in ('passed', 'failed')",
            name="ck_workspace_ai_configurations_check_status",
        ),
        CheckConstraint(
            "not enabled or "
            "(encrypted_api_key is not null and "
            "data_policy_acknowledged_at is not null)",
            name="ck_workspace_ai_configurations_enabled_ready",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "workspaces.id",
            name="fk_workspace_ai_configurations_workspace_id",
            ondelete="CASCADE",
        ),
        index=True,
    )
    provider: Mapped[str] = mapped_column(
        String(40),
        default=AI_PROVIDER_OPENAI,
        server_default=AI_PROVIDER_OPENAI,
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
    )
    model: Mapped[str] = mapped_column(String(80))
    reasoning_effort: Mapped[str] = mapped_column(
        String(20),
        default=AI_REASONING_EFFORT_MEDIUM,
        server_default=AI_REASONING_EFFORT_MEDIUM,
    )
    max_output_tokens: Mapped[int] = mapped_column(
        Integer,
        default=1_200,
        server_default="1200",
    )
    configuration_version: Mapped[int] = mapped_column(
        Integer,
        default=1,
        server_default="1",
    )
    encrypted_api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_policy_version: Mapped[str | None] = mapped_column(
        String(80),
        nullable=True,
    )
    data_policy_acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    data_policy_acknowledged_by_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "users.id",
            name="fk_workspace_ai_configurations_ack_user_id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    last_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_check_status: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )
    last_check_code: Mapped[str | None] = mapped_column(
        String(80),
        nullable=True,
    )
    last_check_model: Mapped[str | None] = mapped_column(
        String(80),
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


class SyncJob(Base):
    """Canonical sync job state for a provider connection.

    PostgreSQL is the durable queue and lifecycle source of truth. Provider
    credentials and payload bodies are never stored in lease fields or logs.
    """

    __tablename__ = "sync_jobs"
    __table_args__ = (
        CheckConstraint(
            "provider in ('github', 'jira', 'gmail', 'drive')",
            name="ck_sync_jobs_provider",
        ),
        CheckConstraint(
            "status in "
            "('queued', 'running', 'succeeded', 'failed', 'partial', 'cancelled')",
            name="ck_sync_jobs_status",
        ),
        CheckConstraint(
            "sync_type in ('initial', 'incremental', 'manual')",
            name="ck_sync_jobs_sync_type",
        ),
        Index("ix_sync_jobs_workspace_status", "workspace_id", "status"),
        Index("ix_sync_jobs_connection_started_at", "connection_id", "started_at"),
        Index(
            "ix_sync_jobs_claim",
            "provider",
            "status",
            "next_attempt_at",
            "lease_expires_at",
        ),
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
        index=True,
    )
    lease_owner: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    cancel_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class GitHubAppCredential(Base):
    """Encrypted workspace-owned GitHub App identity.

    Installation and user access tokens are deliberately absent. They are minted
    or exchanged just-in-time and discarded after the bounded provider call.
    """

    __tablename__ = "github_app_credentials"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            name="uq_github_app_credentials_workspace_id",
        ),
        UniqueConstraint("app_id", name="uq_github_app_credentials_app_id"),
        CheckConstraint(
            "status in ('active', 'error', 'revoked')",
            name="ck_github_app_credentials_status",
        ),
        CheckConstraint(
            "source in ('manifest', 'manual')",
            name="ck_github_app_credentials_source",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "workspaces.id",
            name="fk_github_app_credentials_workspace_id",
            ondelete="CASCADE",
        ),
        index=True,
    )
    app_id: Mapped[str] = mapped_column(String(100), index=True)
    app_slug: Mapped[str] = mapped_column(String(120))
    app_name: Mapped[str] = mapped_column(String(255))
    client_id: Mapped[str] = mapped_column(String(255))
    encrypted_private_key: Mapped[str] = mapped_column(Text)
    encrypted_client_secret: Mapped[str] = mapped_column(Text)
    encrypted_webhook_secret: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_login: Mapped[str | None] = mapped_column(String(255), nullable=True)
    owner_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    owner_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    permissions: Mapped[dict] = mapped_column(JSON, default=dict)
    html_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    callback_url: Mapped[str] = mapped_column(String(1000))
    source: Mapped[str] = mapped_column(String(40), default="manifest")
    status: Mapped[str] = mapped_column(
        String(20), default=GITHUB_APP_CREDENTIAL_STATUS_ACTIVE, index=True
    )
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "users.id",
            name="fk_github_app_credentials_created_by_user_id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )
    last_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class GitHubAppInstallation(Base):
    """Verified GitHub App installation facts, separate from flexible metadata."""

    __tablename__ = "github_app_installations"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            name="uq_github_app_installations_workspace_id",
        ),
        UniqueConstraint(
            "connection_id",
            name="uq_github_app_installations_connection_id",
        ),
        UniqueConstraint(
            "installation_id",
            name="uq_github_app_installations_installation_id",
        ),
        CheckConstraint(
            "status in ('active', 'suspended', 'revoked')",
            name="ck_github_app_installations_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "workspaces.id",
            name="fk_github_app_installations_workspace_id",
            ondelete="CASCADE",
        ),
        index=True,
    )
    credential_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "github_app_credentials.id",
            name="fk_github_app_installations_credential_id",
            ondelete="CASCADE",
        ),
        index=True,
    )
    connection_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "integration_connections.id",
            name="fk_github_app_installations_connection_id",
            ondelete="CASCADE",
        ),
        index=True,
    )
    installation_id: Mapped[str] = mapped_column(String(100), index=True)
    account_login: Mapped[str] = mapped_column(String(255))
    account_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    account_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    repository_selection: Mapped[str] = mapped_column(String(32))
    permissions: Mapped[dict] = mapped_column(JSON, default=dict)
    installation_settings_url: Mapped[str | None] = mapped_column(
        String(1000), nullable=True
    )
    verified_by_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "users.id",
            name="fk_github_app_installations_verified_by_user_id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    repository_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(
        String(20), default=GITHUB_APP_INSTALLATION_STATUS_ACTIVE, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class GitHubAppSetupSession(Base):
    """Single resumable, one-time GitHub App setup handshake per workspace."""

    __tablename__ = "github_app_setup_sessions"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            name="uq_github_app_setup_sessions_workspace_id",
        ),
        UniqueConstraint("state_hash", name="uq_github_app_setup_sessions_state_hash"),
        CheckConstraint(
            "phase in ("
            "'manifest_pending', 'manifest_exchanging', 'installation_pending', "
            "'oauth_pending', 'oauth_exchanging', 'repository_selection', "
            "'completed', 'failed', 'cancelled'"
            ")",
            name="ck_github_app_setup_sessions_phase",
        ),
        Index(
            "ix_github_app_setup_sessions_workspace_phase",
            "workspace_id",
            "phase",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "workspaces.id",
            name="fk_github_app_setup_sessions_workspace_id",
            ondelete="CASCADE",
        ),
        index=True,
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "users.id",
            name="fk_github_app_setup_sessions_created_by_user_id",
            ondelete="CASCADE",
        ),
        index=True,
    )
    credential_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "github_app_credentials.id",
            name="fk_github_app_setup_sessions_credential_id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )
    connection_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "integration_connections.id",
            name="fk_github_app_setup_sessions_connection_id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )
    phase: Mapped[str] = mapped_column(String(40), index=True)
    state_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    encrypted_pkce_verifier: Mapped[str | None] = mapped_column(Text, nullable=True)
    app_origin: Mapped[str] = mapped_column(String(1000))
    installation_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    installation_account_login: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    installation_account_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    repository_selection: Mapped[str | None] = mapped_column(String(32), nullable=True)
    repository_inventory: Mapped[list[dict]] = mapped_column(JSON, default=list)
    error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
