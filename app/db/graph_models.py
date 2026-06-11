from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class EntityRecord(Base):
    __tablename__ = "entities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_id: Mapped[str] = mapped_column(String(120), unique=True)
    entity_type: Mapped[str] = mapped_column(String(50), index=True)
    canonical_name: Mapped[str] = mapped_column(String(255))
    attrs: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class EntityAliasRecord(Base):
    __tablename__ = "entity_aliases"
    __table_args__ = (UniqueConstraint("entity_id", "normalized_alias"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_id: Mapped[str] = mapped_column(String(120))
    alias: Mapped[str] = mapped_column(String(255))
    normalized_alias: Mapped[str] = mapped_column(String(255), index=True)
    source: Mapped[str] = mapped_column(String(50))
    confidence: Mapped[float] = mapped_column(Float)
    confirmed_by_user: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class EntityLinkRecord(Base):
    __tablename__ = "entity_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    link_id: Mapped[str] = mapped_column(String(120), unique=True)
    from_entity_id: Mapped[str] = mapped_column(String(120), index=True)
    to_entity_id: Mapped[str] = mapped_column(String(120), index=True)
    relation: Mapped[str] = mapped_column(String(60), index=True)
    evidence_refs: Mapped[list[dict]] = mapped_column(JSON, default=list)
    confidence: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
