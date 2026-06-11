from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class StatusSnapshotRecord(Base):
    __tablename__ = "status_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(120), index=True)
    entity_type: Mapped[str] = mapped_column(String(50), index=True)
    entity_id: Mapped[str] = mapped_column(String(255), index=True)
    status_color: Mapped[str] = mapped_column(String(20), index=True)
    summary: Mapped[str] = mapped_column(Text)
    what_changed_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    current_work_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    blockers_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    risks_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    conflicts_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    recommendations_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    confidence: Mapped[float] = mapped_column(Float)
    confidence_reason: Mapped[str] = mapped_column(Text)
    last_meaningful_update_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    evidence_source_ids_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,
    )

    __table_args__ = (
        Index(
            "ix_status_snapshots_entity_created",
            "organization_id",
            "entity_type",
            "entity_id",
            "created_at",
        ),
    )
