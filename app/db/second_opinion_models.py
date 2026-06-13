from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SecondOpinionFinding(Base):
    """One declared-vs-observed conflict — the central feed of the product.

    ``finding_key`` dedupes re-scans; ``visibility_scope`` controls which
    view (founder / team / investor) may see the finding.
    """

    __tablename__ = "second_opinion_findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    finding_key: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    company_id: Mapped[str] = mapped_column(String(120), default="default", index=True)
    entity_id: Mapped[str | None] = mapped_column(
        String(120), nullable=True, index=True
    )
    finding_type: Mapped[str] = mapped_column(String(60), index=True)
    declared_state: Mapped[str] = mapped_column(Text)
    observed_state: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(String(500))
    severity: Mapped[str] = mapped_column(String(20), index=True)
    confidence: Mapped[float] = mapped_column(Float)
    confidence_factors: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    evidence_refs: Mapped[list] = mapped_column(JSON, default=list)
    source_refs: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    visibility_scope: Mapped[str] = mapped_column(String(20), default="founder")
    last_update_reason: Mapped[str | None] = mapped_column(
        String(40), nullable=True
    )
    last_run_id: Mapped[str | None] = mapped_column(
        String(120), nullable=True, index=True
    )
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    snoozed_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
