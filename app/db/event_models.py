from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
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
