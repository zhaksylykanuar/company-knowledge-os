from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class AttentionTriageResultRecord(Base):
    __tablename__ = "attention_triage_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    triage_result_id: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    source: Mapped[str] = mapped_column(String(50), index=True)
    source_object_id: Mapped[str] = mapped_column(String(255), index=True)
    activity_item_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    attention_class: Mapped[str] = mapped_column(String(60), index=True)
    priority: Mapped[str] = mapped_column(String(20), index=True)
    show_in_digest: Mapped[bool] = mapped_column(Boolean, index=True)
    confidence: Mapped[float] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(Text)
    recommended_action: Mapped[str] = mapped_column(Text)
    owner: Mapped[str | None] = mapped_column(String(255), nullable=True)
    deadline: Mapped[str | None] = mapped_column(String(120), nullable=True)
    evidence_refs: Mapped[list[dict]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,
    )

    __table_args__ = (
        Index(
            "ix_attention_triage_results_object_created",
            "source_object_id",
            "created_at",
        ),
        Index(
            "ix_attention_triage_results_source_object_created",
            "source",
            "source_object_id",
            "created_at",
        ),
    )


class AttentionTriageFeedbackRecord(Base):
    __tablename__ = "attention_triage_feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    feedback_id: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    source: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    source_object_id: Mapped[str] = mapped_column(String(255), index=True)
    triage_result_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    user_action: Mapped[str] = mapped_column(String(60), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,
    )

    __table_args__ = (
        Index(
            "ix_attention_triage_feedback_object_created",
            "source_object_id",
            "created_at",
        ),
        Index(
            "ix_attention_triage_feedback_source_object_created",
            "source",
            "source_object_id",
            "created_at",
        ),
    )
