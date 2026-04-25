from datetime import datetime

from sqlalchemy import DateTime, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class GmailThread(Base):
    __tablename__ = "gmail_threads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    thread_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    history_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    raw_object_ref: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GmailMessage(Base):
    __tablename__ = "gmail_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    message_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    thread_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    history_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    snippet: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    label_ids: Mapped[list] = mapped_column(JSON, default=list)
    raw_object_ref: Mapped[str] = mapped_column(String(1000))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GmailAttachment(Base):
    __tablename__ = "gmail_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    message_id: Mapped[str] = mapped_column(String(255), index=True)
    attachment_id: Mapped[str] = mapped_column(String(255), index=True)
    filename: Mapped[str | None] = mapped_column(String(500), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_object_ref: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("message_id", "attachment_id"),)
