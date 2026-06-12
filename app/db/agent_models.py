from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AgentProposal(Base):
    """A graph change suggested by an agent, awaiting a human decision.

    Anything an agent infers below its confidence threshold lands here
    instead of being written to the graph silently.
    """

    __tablename__ = "agent_proposals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    proposal_id: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    agent: Mapped[str] = mapped_column(String(80), index=True)
    kind: Mapped[str] = mapped_column(String(80), index=True)
    title: Mapped[str] = mapped_column(String(500))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    evidence_refs: Mapped[list] = mapped_column(JSON, default=list)
    confidence: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    decided_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class MetricSnapshot(Base):
    """One captured point of a named time series, one row per day per scope."""

    __tablename__ = "metric_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    metric_key: Mapped[str] = mapped_column(String(120), index=True)
    scope: Mapped[str] = mapped_column(String(160), default="global", index=True)
    captured_on: Mapped[str] = mapped_column(String(10), index=True)
    value: Mapped[float] = mapped_column(Float)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "metric_key",
            "scope",
            "captured_on",
            name="uq_metric_snapshots_key_scope_day",
        ),
    )
