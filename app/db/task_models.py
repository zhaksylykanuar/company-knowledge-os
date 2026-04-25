from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agent_run_id: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    runner_name: Mapped[str] = mapped_column(String(120), index=True)
    source_document_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    chunk_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(40), default="completed")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ExtractedTask(Base):
    __tablename__ = "extracted_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(50), default="open")
    item_type: Mapped[str] = mapped_column(String(50), default="task")
    owner: Mapped[str | None] = mapped_column(String(255), nullable=True)
    due_date: Mapped[str | None] = mapped_column(String(80), nullable=True)
    confidence: Mapped[float] = mapped_column(Float)
    source_event_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    source_document_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    chunk_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    evidence_refs: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ExtractedDecision(Base):
    __tablename__ = "extracted_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(500))
    decision: Mapped[str] = mapped_column(String(1000))
    owner: Mapped[str | None] = mapped_column(String(255), nullable=True)
    confidence: Mapped[float] = mapped_column(Float)
    source_event_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    source_document_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    chunk_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    evidence_refs: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ExtractedRisk(Base):
    __tablename__ = "extracted_risks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(500))
    severity: Mapped[str] = mapped_column(String(80), default="medium")
    confidence: Mapped[float] = mapped_column(Float)
    source_event_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    source_document_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    chunk_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    evidence_refs: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
