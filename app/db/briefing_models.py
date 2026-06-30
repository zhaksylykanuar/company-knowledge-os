"""Persistent Founder Briefing models (§6 Briefing / BriefingItem).

Briefings Chunk 1 persists the deterministic Founder Briefing so the founder has
history to revisit. The generation logic in
``app.services.founder_briefing_service`` is unchanged and still LLM-free; this
module only stores its output.

A ``Briefing`` is one generated briefing (workspace-scoped); ``BriefingItem``
rows are its ordered items, mirroring the deterministic generator's item shape
(category / title / summary / severity / confidence / recommended_next_step /
evidence_refs / related_entities / warnings). The LLM-generated narrative is a
later chunk; ``generated_by`` records which generator produced the row.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

# Register FK-target tables (workspaces / users -> identity_models) in the shared
# metadata regardless of import order, so the string foreign keys below resolve.
import app.db.identity_models  # noqa: E402,F401

BRIEFING_GENERATED_BY_DETERMINISTIC_V0 = "deterministic_v0"


class Briefing(Base):
    """One persisted Founder Briefing (workspace-scoped, newest-first history)."""

    __tablename__ = "briefings"
    __table_args__ = (
        Index("ix_briefings_workspace_created_at", "workspace_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "workspaces.id",
            name="fk_briefings_workspace_id",
            ondelete="CASCADE",
        ),
        index=True,
    )
    # The acting founder/user when known; SET NULL on user delete keeps history.
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "users.id",
            name="fk_briefings_created_by_user_id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )
    generated_by: Mapped[str] = mapped_column(
        String(50), default=BRIEFING_GENERATED_BY_DETERMINISTIC_V0
    )
    title: Mapped[str] = mapped_column(String(255))
    summary: Mapped[str] = mapped_column(Text, default="")
    # "as of" timestamp of the generated content (the generator's generated_at);
    # created_at is when the row was saved.
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    signals: Mapped[dict] = mapped_column(JSON, default=dict)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    items: Mapped[list["BriefingItem"]] = relationship(
        "BriefingItem",
        back_populates="briefing",
        cascade="all, delete-orphan",
        order_by="BriefingItem.position",
    )


class BriefingItem(Base):
    """One ordered item inside a persisted briefing (mirrors generator shape)."""

    __tablename__ = "briefing_items"
    __table_args__ = (
        Index(
            "ix_briefing_items_briefing_position",
            "briefing_id",
            "position",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    briefing_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "briefings.id",
            name="fk_briefing_items_briefing_id",
            ondelete="CASCADE",
        ),
        index=True,
    )
    position: Mapped[int] = mapped_column(Integer, default=0)
    # The generator's stable string id (e.g. "github-connection"); kept as
    # item_key so it does not clash with the row primary key.
    item_key: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(String(255))
    summary: Mapped[str] = mapped_column(Text, default="")
    severity: Mapped[str] = mapped_column(String(20))
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    recommended_next_step: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_refs: Mapped[list] = mapped_column(JSON, default=list)
    related_entities: Mapped[list] = mapped_column(JSON, default=list)
    warnings: Mapped[list] = mapped_column(JSON, default=list)

    briefing: Mapped["Briefing"] = relationship("Briefing", back_populates="items")
