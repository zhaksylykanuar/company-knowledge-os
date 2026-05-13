from datetime import datetime

from sqlalchemy import DateTime, Integer, JSON, String, Text, UniqueConstraint
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


class EmailThreadState(Base):
    __tablename__ = "email_thread_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(50), default="gmail", index=True)
    thread_key: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    provider_thread_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    subject_normalized: Mapped[str | None] = mapped_column(String(500), nullable=True, index=True)
    subject_display: Mapped[str | None] = mapped_column(String(500), nullable=True)
    participants_json: Mapped[list] = mapped_column(JSON, default=list)
    first_message_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_message_from: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_message_direction: Mapped[str] = mapped_column(String(40), default="unknown", index=True)
    last_message_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    thread_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(60), default="informational", index=True)
    days_without_reply: Mapped[int | None] = mapped_column(Integer, nullable=True)
    messages_count: Mapped[int] = mapped_column(Integer, default=0)
    evidence_refs: Mapped[list[dict]] = mapped_column(JSON, default=list)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
