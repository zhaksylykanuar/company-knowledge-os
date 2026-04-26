from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class KnowledgeScore(Base):
    __tablename__ = "knowledge_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    entity_type: Mapped[str] = mapped_column(String(50), index=True)
    entity_id: Mapped[str] = mapped_column(String(255), index=True)

    source_document_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    chunk_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    importance_score: Mapped[float] = mapped_column(Float, default=0.0)
    urgency_score: Mapped[float] = mapped_column(Float, default=0.0)
    risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0)
    attention_score: Mapped[float] = mapped_column(Float, default=0.0)

    reasons: Mapped[list] = mapped_column(JSON, default=list)
    evidence_refs: Mapped[list] = mapped_column(JSON, default=list)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        UniqueConstraint("entity_type", "entity_id", name="uq_knowledge_scores_entity"),
    )
