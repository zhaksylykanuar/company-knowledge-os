from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, JSON, String, Text, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


ACTION_TARGET_PROVIDER_GITHUB = "github"
ACTION_TARGET_PROVIDER_INTERNAL = "internal"

ACTION_TYPE_CREATE_GITHUB_ISSUE = "create_github_issue"
ACTION_TYPE_INTERNAL_TODO = "internal_todo"

ACTION_PROPOSAL_STATUS_PROPOSED = "proposed"
ACTION_PROPOSAL_STATUS_APPROVED = "approved"
ACTION_PROPOSAL_STATUS_REJECTED = "rejected"
ACTION_PROPOSAL_STATUS_EXECUTED = "executed"
ACTION_PROPOSAL_STATUS_FAILED = "failed"

ACTION_CREATED_BY_USER = "user"
ACTION_CREATED_BY_SYSTEM = "system"
ACTION_CREATED_BY_AI = "ai"

ACTION_EXECUTION_STATUS_CLAIMED = "claimed"
ACTION_EXECUTION_STATUS_RUNNING = "running"
ACTION_EXECUTION_STATUS_SUCCEEDED = "succeeded"
ACTION_EXECUTION_STATUS_FAILED = "failed"
ACTION_EXECUTION_STATUS_UNCERTAIN = "uncertain"

ACTION_EXECUTION_EVENT_STATUS_RECORDED = "recorded"
ACTION_EXECUTION_EVENT_STATUS_BLOCKED = "blocked"
ACTION_EXECUTION_EVENT_STATUS_UNSUPPORTED = "unsupported"

ACTION_EXECUTION_EVENT_PROPOSAL_APPROVED = "action_proposal_approved_locally"
ACTION_EXECUTION_EVENT_PROPOSAL_REJECTED = "action_proposal_rejected_locally"
ACTION_EXECUTION_EVENT_PREVIEW_GENERATED = "execution_preview_generated"
ACTION_EXECUTION_EVENT_PREVIEW_BLOCKED = "execution_preview_blocked"
ACTION_EXECUTION_EVENT_UNSUPPORTED = "execution_unsupported"
ACTION_EXECUTION_EVENT_CONFIRMATION_MISSING = "execution_confirmation_missing"
ACTION_EXECUTION_EVENT_CONFIRMATION_RECEIVED_BUT_DISABLED = (
    "execution_confirmation_received_but_disabled"
)
ACTION_EXECUTION_EVENT_CONFIRMATION_RECEIVED = "execution_confirmation_received"
ACTION_EXECUTION_EVENT_CLAIMED = "execution_claimed"
ACTION_EXECUTION_EVENT_STARTED = "execution_started"
ACTION_EXECUTION_EVENT_SUCCEEDED = "execution_succeeded"
ACTION_EXECUTION_EVENT_FAILED = "execution_failed"
ACTION_EXECUTION_EVENT_OUTCOME_UNCERTAIN = "execution_outcome_uncertain"
ACTION_EXECUTION_EVENT_OUTCOME_RECONCILED = "execution_outcome_reconciled"
ACTION_EXECUTION_EVENT_RECONCILIATION_PENDING = "execution_reconciliation_pending"
ACTION_EXECUTION_EVENT_WRITE_NOT_OBSERVED = "execution_write_not_observed"
ACTION_EXECUTION_EVENT_BLOCKED = "execution_blocked"
ACTION_EXECUTION_EVENT_REPOSITORY_NOT_ALLOWED = "execution_repository_not_allowed"
ACTION_EXECUTION_EVENT_DUPLICATE_RETURNED_EXISTING_RECEIPT = (
    "execution_duplicate_returned_existing_receipt"
)
ACTION_EXECUTION_EVENT_RESULT_SYNC_STARTED = "execution_result_sync_started"
ACTION_EXECUTION_EVENT_RESULT_SYNCED = "execution_result_synced"
ACTION_EXECUTION_EVENT_RESULT_SYNC_FAILED = "execution_result_sync_failed"


class ActionProposal(Base):
    """Canonical local proposal for a future human-approved action.

    The proposal can be approved or rejected in FOS-ACT-01, but approval does
    not execute provider work and does not create an ActionExecution row.
    """

    __tablename__ = "action_proposals"
    __table_args__ = (
        CheckConstraint(
            "target_provider in ('github', 'internal')",
            name="ck_action_proposals_target_provider",
        ),
        CheckConstraint(
            "action_type in ('create_github_issue', 'internal_todo')",
            name="ck_action_proposals_action_type",
        ),
        CheckConstraint(
            "status in ('proposed', 'approved', 'rejected', 'executed', 'failed')",
            name="ck_action_proposals_status",
        ),
        CheckConstraint(
            "created_by in ('user', 'system', 'ai')",
            name="ck_action_proposals_created_by",
        ),
        Index("ix_action_proposals_workspace_status", "workspace_id", "status"),
        Index(
            "ix_action_proposals_provider_action_type",
            "target_provider",
            "action_type",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces.id", name="fk_action_proposals_workspace_id"),
        index=True,
    )
    briefing_item_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True, index=True
    )
    target_provider: Mapped[str] = mapped_column(String(40), index=True)
    action_type: Mapped[str] = mapped_column(String(80), index=True)
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(
        String(40), default=ACTION_PROPOSAL_STATUS_PROPOSED, index=True
    )
    evidence_refs: Mapped[list] = mapped_column(JSON, default=list)
    created_by: Mapped[str] = mapped_column(
        String(20), default=ACTION_CREATED_BY_USER, index=True
    )
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", name="fk_action_proposals_created_by_user_id"),
        nullable=True,
        index=True,
    )
    approved_by_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", name="fk_action_proposals_approved_by_user_id"),
        nullable=True,
        index=True,
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rejected_by_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", name="fk_action_proposals_rejected_by_user_id"),
        nullable=True,
        index=True,
    )
    rejected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ActionExecution(Base):
    """Durable claim and provider receipt for one approved external action."""

    __tablename__ = "action_executions"
    __table_args__ = (
        CheckConstraint(
            "status in ('claimed', 'running', 'succeeded', 'failed', 'uncertain')",
            name="ck_action_executions_status",
        ),
        Index(
            "ix_action_executions_proposal_status",
            "action_proposal_id",
            "status",
        ),
        Index(
            "uq_action_executions_workspace_client_idempotency_key",
            "workspace_id",
            "client_idempotency_key",
            unique=True,
        ),
        Index(
            "uq_action_executions_one_active_or_success_per_proposal",
            "action_proposal_id",
            unique=True,
            postgresql_where=text(
                "status in ('claimed', 'running', 'succeeded', 'uncertain')"
            ),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    action_proposal_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "action_proposals.id",
            name="fk_action_executions_action_proposal_id",
        ),
        index=True,
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces.id", name="fk_action_executions_workspace_id"),
        index=True,
    )
    requested_by_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "users.id",
            name="fk_action_executions_requested_by_user_id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )
    connection_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "integration_connections.id",
            name="fk_action_executions_connection_id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )
    client_idempotency_key: Mapped[str] = mapped_column(String(255))
    request_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(
        String(40), default=ACTION_EXECUTION_STATUS_CLAIMED, index=True
    )
    provider_response: Mapped[dict] = mapped_column(JSON, default=dict)
    external_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    claimed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reconciled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ActionExecutionEvent(Base):
    """Append-only local audit events for action review and execution readiness.

    These records are intentionally separate from ActionExecution rows: local
    review decisions, preview, and blocked attempts must be auditable without
    implying a provider write.
    """

    __tablename__ = "action_execution_events"
    __table_args__ = (
        CheckConstraint(
            "status in ('recorded', 'blocked', 'unsupported')",
            name="ck_action_execution_events_status",
        ),
        Index(
            "ix_action_execution_events_workspace_proposal_created",
            "workspace_id",
            "action_proposal_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces.id", name="fk_action_execution_events_workspace_id"),
        index=True,
    )
    action_proposal_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "action_proposals.id",
            name="fk_action_execution_events_action_proposal_id",
        ),
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    actor: Mapped[str] = mapped_column(String(80), default="system", index=True)
    status: Mapped[str] = mapped_column(
        String(40), default=ACTION_EXECUTION_EVENT_STATUS_RECORDED, index=True
    )
    message: Mapped[str] = mapped_column(String(500))
    event_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    idempotency_key: Mapped[str] = mapped_column(String(500), unique=True, index=True)
    provider: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    action: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    external_execution_enabled: Mapped[bool] = mapped_column(default=False)
    confirmation_received: Mapped[bool] = mapped_column(default=False)
    external_result_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    external_result_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
