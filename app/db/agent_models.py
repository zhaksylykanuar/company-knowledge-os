from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AgentProposal(Base):
    """A graph change suggested by an agent, awaiting a human decision.

    Anything an agent infers below its confidence threshold lands here
    instead of being written to the graph silently. ``kind`` is the
    proposal type (e.g. ``entity_merge_proposal``); ``dedupe_key`` keeps
    re-runs from filing the same suggestion twice; ``source_snapshot``
    preserves what the agent saw when it proposed; ``reversible`` tells
    the UI whether an accepted proposal can be undone.
    """

    __tablename__ = "agent_proposals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    proposal_id: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    dedupe_key: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    agent: Mapped[str] = mapped_column(String(80), index=True)
    kind: Mapped[str] = mapped_column(String(80), index=True)
    title: Mapped[str] = mapped_column(String(500))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    source_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    evidence_refs: Mapped[list] = mapped_column(JSON, default=list)
    confidence: Mapped[float] = mapped_column(Float)
    confidence_factors: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    decided_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    applied_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reversible: Mapped[bool] = mapped_column(Boolean, default=True)
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


class DataAvailability(Base):
    """Formal data-readiness state behind every widget/series.

    The UI never draws a number without checking this row first:
    ``no_data`` / ``collecting`` / ``insufficient`` / ``ready`` / ``stale``.
    """

    __tablename__ = "data_availability"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    metric_key: Mapped[str] = mapped_column(String(120), index=True)
    scope: Mapped[str] = mapped_column(String(160), default="global", index=True)
    status: Mapped[str] = mapped_column(String(20), index=True)
    points_count: Mapped[int] = mapped_column(Integer, default=0)
    required_points: Mapped[int] = mapped_column(Integer, default=5)
    last_point_at: Mapped[str | None] = mapped_column(String(10), nullable=True)
    message: Mapped[str] = mapped_column(String(300), default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "metric_key", "scope", name="uq_data_availability_key_scope"
        ),
    )
