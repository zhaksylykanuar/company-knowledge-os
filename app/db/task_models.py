from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class ExtractedTask(Base):
    __tablename__ = "extracted_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    title: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(50), default="open")

    confidence: Mapped[float] = mapped_column(Float)

    source_event_id: Mapped[str] = mapped_column(String(120), index=True)

    evidence_refs: Mapped[list] = mapped_column(JSON)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )