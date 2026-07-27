"""Minimal persistence for FounderOS temporal-memory checkpoints.

The checkpoint deliberately stores only opaque fingerprints of the canonical
signals visible at acknowledgement time. Source bodies, evidence payloads and
rendered signal text stay in their existing source-of-truth tables.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    JSON,
    String,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base

# Register the composite FK target regardless of import order.
import app.db.identity_models  # noqa: E402,F401


COMPANY_MEMORY_CHECKPOINT_VERSION = "temporal-checkpoint.v1"


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
            "checkpoint_version = 'temporal-checkpoint.v1'",
            name="ck_company_memory_checkpoints_version",
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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
