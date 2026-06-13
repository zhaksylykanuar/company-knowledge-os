from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FounderDeclaration(Base):
    """A declared state (weekly focus, hypotheses) agents check reality
    against. One row per declaration key."""

    __tablename__ = "founder_declarations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    declaration_key: Mapped[str] = mapped_column(String(80), unique=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    declared_by: Mapped[str] = mapped_column(String(120), default="founder")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
