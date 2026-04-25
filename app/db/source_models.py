from datetime import datetime

from sqlalchemy import DateTime, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class SourceDocument(Base):
    __tablename__ = "source_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_document_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    source_system: Mapped[str] = mapped_column(String(50), index=True)
    source_object_id: Mapped[str] = mapped_column(String(255), index=True)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    raw_object_ref: Mapped[str] = mapped_column(String(1000))
    content_hash: Mapped[str] = mapped_column(String(128), index=True)
    modified_at: Mapped[str | None] = mapped_column(String(80), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (UniqueConstraint("source_system", "source_object_id", "content_hash"),)


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_document_id: Mapped[str] = mapped_column(String(255), index=True)
    chunk_id: Mapped[str] = mapped_column(String(255), index=True)
    source_system: Mapped[str] = mapped_column(String(50), index=True)
    source_object_id: Mapped[str] = mapped_column(String(255), index=True)
    raw_object_ref: Mapped[str] = mapped_column(String(1000))
    text: Mapped[str] = mapped_column(Text)
    start_char: Mapped[int] = mapped_column(Integer)
    end_char: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(128), index=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("source_document_id", "chunk_id"),)
