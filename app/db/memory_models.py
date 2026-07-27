"""Minimal persistence for FounderOS temporal memory.

The append-only ledger stores lifecycle metadata and canonical identifiers only.
The membership checkpoint combines an opaque fingerprint snapshot with a
monotonic ledger cursor. Source bodies, evidence payloads and rendered signal
text stay in their existing source-of-truth tables.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    JSON,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base

# Register the composite FK target regardless of import order.
import app.db.canonical_models  # noqa: E402,F401
import app.db.identity_models  # noqa: E402,F401


COMPANY_MEMORY_CHECKPOINT_VERSION = "temporal-checkpoint.v2"
COMPANY_MEMORY_EVENT_VERSION = "company-memory-event.v1"

COMPANY_MEMORY_EVENT_ACTION_PROPOSAL_CREATED = "action_proposal_created"
COMPANY_MEMORY_EVENT_ACTION_PROPOSAL_APPROVED = "action_proposal_approved"
COMPANY_MEMORY_EVENT_ACTION_PROPOSAL_REJECTED = "action_proposal_rejected"
COMPANY_MEMORY_EVENT_COMPANY_WORLD_CONFIRMED = "company_world_confirmed"
COMPANY_MEMORY_EVENT_COMPANY_WORLD_DISMISSED = "company_world_dismissed"
COMPANY_MEMORY_EVENT_SOURCE_RECORD_DISAPPEARED = "source_record_disappeared"
COMPANY_MEMORY_EVENT_SOURCE_RECORD_RESTORED = "source_record_restored"

COMPANY_MEMORY_LIFECYCLE_CREATED = "created"
COMPANY_MEMORY_LIFECYCLE_RESOLVED = "resolved"


class CompanyMemoryEvent(Base):
    """One immutable lifecycle fact backed by canonical identifiers.

    The row is intentionally unsuitable for provider payloads or rendered
    summaries. UI copy is resolved from the canonical subject at read time.
    """

    __tablename__ = "company_memory_events"
    __table_args__ = (
        CheckConstraint(
            "event_version = 'company-memory-event.v1'",
            name="ck_company_memory_events_version",
        ),
        CheckConstraint(
            "event_type in ("
            "'action_proposal_created', "
            "'action_proposal_approved', "
            "'action_proposal_rejected', "
            "'company_world_confirmed', "
            "'company_world_dismissed', "
            "'source_record_disappeared', "
            "'source_record_restored'"
            ")",
            name="ck_company_memory_events_type",
        ),
        CheckConstraint(
            "lifecycle_state in ('created', 'resolved')",
            name="ck_company_memory_events_lifecycle_state",
        ),
        CheckConstraint(
            "subject_type in ("
            "'action_proposal', "
            "'external_person_candidate', "
            "'organization_candidate', "
            "'source_record'"
            ")",
            name="ck_company_memory_events_subject_type",
        ),
        CheckConstraint(
            "source_key in ('github', 'jira', 'gmail', 'drive', 'internal')",
            name="ck_company_memory_events_source_key",
        ),
        CheckConstraint(
            "confidence >= 0 and confidence <= 1",
            name="ck_company_memory_events_confidence",
        ),
        CheckConstraint(
            "access_scope = 'workspace'",
            name="ck_company_memory_events_access_scope",
        ),
        CheckConstraint(
            "sensitivity = 'internal'",
            name="ck_company_memory_events_sensitivity",
        ),
        CheckConstraint(
            "retention_policy = 'workspace_canonical'",
            name="ck_company_memory_events_retention_policy",
        ),
        CheckConstraint(
            "char_length(payload_fingerprint) = 64",
            name="ck_company_memory_events_payload_fingerprint",
        ),
        UniqueConstraint(
            "workspace_id",
            "idempotency_key",
            name="uq_company_memory_events_workspace_idempotency_key",
        ),
        UniqueConstraint(
            "workspace_id",
            "workspace_sequence",
            name="uq_company_memory_events_workspace_sequence",
        ),
        Index(
            "ix_company_memory_events_workspace_sequence",
            "workspace_id",
            "workspace_sequence",
        ),
        Index(
            "ix_company_memory_events_workspace_subject",
            "workspace_id",
            "subject_type",
            "subject_key",
        ),
    )

    sequence_id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(),
        primary_key=True,
    )
    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        default=uuid4,
        unique=True,
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "workspaces.id",
            name="fk_company_memory_events_workspace_id",
            ondelete="CASCADE",
        ),
    )
    workspace_sequence: Mapped[int] = mapped_column(BigInteger)
    event_version: Mapped[str] = mapped_column(
        String(40),
        default=COMPANY_MEMORY_EVENT_VERSION,
        server_default=COMPANY_MEMORY_EVENT_VERSION,
    )
    event_type: Mapped[str] = mapped_column(String(80))
    lifecycle_state: Mapped[str] = mapped_column(String(20))
    subject_type: Mapped[str] = mapped_column(String(40))
    subject_key: Mapped[str] = mapped_column(String(120))
    subject_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    source_key: Mapped[str] = mapped_column(String(40))
    confidence: Mapped[float] = mapped_column(Float, default=1.0, server_default="1")
    access_scope: Mapped[str] = mapped_column(
        String(20),
        default="workspace",
        server_default="workspace",
    )
    sensitivity: Mapped[str] = mapped_column(
        String(20),
        default="internal",
        server_default="internal",
    )
    retention_policy: Mapped[str] = mapped_column(
        String(40),
        default="workspace_canonical",
        server_default="workspace_canonical",
    )
    actor_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "users.id",
            name="fk_company_memory_events_actor_user_id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    primary_source_record_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "source_records.id",
            name="fk_company_memory_events_primary_source_record_id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    evidence_refs: Mapped[list[dict[str, str]]] = mapped_column(JSON, default=list)
    payload_fingerprint: Mapped[str] = mapped_column(String(64))
    idempotency_key: Mapped[str] = mapped_column(String(120))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )


class CompanyMemoryEventStream(Base):
    """Transactional per-workspace cursor allocator for lifecycle events."""

    __tablename__ = "company_memory_event_streams"
    __table_args__ = (
        CheckConstraint(
            "last_sequence >= 0",
            name="ck_company_memory_event_streams_last_sequence",
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "workspaces.id",
            name="fk_company_memory_event_streams_workspace_id",
            ondelete="CASCADE",
        ),
        primary_key=True,
    )
    last_sequence: Mapped[int] = mapped_column(
        BigInteger,
        default=0,
        server_default="0",
    )


class CompanyMemoryCheckpoint(Base):
    """One membership-scoped acknowledgement point for temporal comparison."""

    __tablename__ = "company_memory_checkpoints"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "user_id"],
            ["memberships.workspace_id", "memberships.user_id"],
            name="fk_company_memory_checkpoints_membership",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "checkpoint_version = 'temporal-checkpoint.v2'",
            name="ck_company_memory_checkpoints_version",
        ),
        CheckConstraint(
            "last_event_sequence >= 0",
            name="ck_company_memory_checkpoints_last_event_sequence",
        ),
        Index(
            "ix_company_memory_checkpoints_workspace_updated_at",
            "workspace_id",
            "updated_at",
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
    )
    checkpoint_version: Mapped[str] = mapped_column(
        String(40),
        default=COMPANY_MEMORY_CHECKPOINT_VERSION,
        server_default=COMPANY_MEMORY_CHECKPOINT_VERSION,
    )
    source_snapshot_id: Mapped[str] = mapped_column(String(80))
    observed_through_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    event_fingerprints: Mapped[list[str]] = mapped_column(JSON, default=list)
    last_event_sequence: Mapped[int] = mapped_column(
        BigInteger,
        default=0,
        server_default="0",
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
