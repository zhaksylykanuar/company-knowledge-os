from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class SourceEvent(Base):
    __tablename__ = "source_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    source_event_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    source_event_key: Mapped[str] = mapped_column(String(500), unique=True, index=True)

    ingested_event_id: Mapped[str] = mapped_column(
        String(120),
        ForeignKey("ingested_events.event_id", name="fk_source_events_ingested_event_id"),
        index=True,
    )

    event_type: Mapped[str] = mapped_column(String(120), index=True)
    source_system: Mapped[str] = mapped_column(String(50), index=True)
    source_object_type: Mapped[str] = mapped_column(String(120), index=True)
    source_object_id: Mapped[str] = mapped_column(String(255), index=True)

    source_event_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    actor_external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    raw_object_ref: Mapped[str] = mapped_column(String(1000))
    evidence_refs: Mapped[list[dict]] = mapped_column(JSON, default=list)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)

    schema_version: Mapped[str] = mapped_column(String(40), default="1.0")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        UniqueConstraint(
            "source_system",
            "source_object_type",
            "source_object_id",
            "event_type",
            "source_event_key",
            name="uq_source_events_external_event",
        ),
    )


class NormalizedActivityItemRecord(Base):
    __tablename__ = "normalized_activity_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    activity_item_id: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    source_event_id: Mapped[str | None] = mapped_column(
        String(255),
        ForeignKey("source_events.source_event_id", name="fk_normalized_activity_source_event_id"),
        nullable=True,
        index=True,
    )
    source: Mapped[str] = mapped_column(String(50), index=True)
    source_object_id: Mapped[str] = mapped_column(String(255), index=True)
    activity_type: Mapped[str] = mapped_column(String(120), index=True)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    actor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    activity_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    project: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    safe_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    related_people: Mapped[list[str]] = mapped_column(JSON, default=list)
    related_jira_keys: Mapped[list[str]] = mapped_column(JSON, default=list)
    related_prs: Mapped[list[str]] = mapped_column(JSON, default=list)
    related_files: Mapped[list[str]] = mapped_column(JSON, default=list)
    evidence_refs: Mapped[list[dict]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,
    )

    __table_args__ = (
        Index(
            "ix_normalized_activity_items_source_object_created",
            "source",
            "source_object_id",
            "activity_created_at",
        ),
        Index(
            "ix_normalized_activity_items_source_event_created",
            "source_event_id",
            "activity_created_at",
        ),
    )
