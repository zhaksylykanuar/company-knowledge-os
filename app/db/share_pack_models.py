from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SharePack(Base):
    """A reviewable, evidence-backed update prepared for a specific audience.

    AI may generate the draft; only a human can approve, export or revoke
    it. The pack freezes a ``source_snapshot`` at generation time and a
    ``content_hash`` over its shareable content, so the thing that is
    exported is exactly the thing that was reviewed. ``approved_content_hash``
    records what was approved — export is refused if the live content_hash
    has drifted from it (stale-hash protection). ``redaction_manifest``
    states, per audience, what the pack hides, so investor/team packs can
    prove they do not leak. The audit trail lives in ``audit_logs`` keyed
    by ``pack_id`` (not on this row).
    """

    __tablename__ = "share_packs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pack_id: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    company_id: Mapped[str] = mapped_column(
        String(120), default="default", index=True
    )
    pack_type: Mapped[str] = mapped_column(String(80), index=True)
    audience: Mapped[str] = mapped_column(String(20), index=True)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)

    title: Mapped[str] = mapped_column(String(500), default="")
    generated_summary: Mapped[str] = mapped_column(Text, default="")
    sections: Mapped[list] = mapped_column(JSON, default=list)
    evidence_coverage: Mapped[str] = mapped_column(String(80), default="")
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    declared_vs_observed: Mapped[dict] = mapped_column(JSON, default=dict)
    redaction_manifest: Mapped[dict] = mapped_column(JSON, default=dict)

    included_entity_ids: Mapped[list] = mapped_column(JSON, default=list)
    included_finding_ids: Mapped[list] = mapped_column(JSON, default=list)
    # Raw source-event refs are only ever populated when the audience permits.
    included_source_event_ids: Mapped[list] = mapped_column(JSON, default=list)

    created_by: Mapped[str] = mapped_column(String(120), default="founder")
    approved_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    exported_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    content_hash: Mapped[str] = mapped_column(String(128), default="", index=True)
    # The hash that was approved; export requires content_hash to still match.
    approved_content_hash: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )
    source_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # The content frozen at approval time, so the UI can diff the current
    # draft against what was last approved.
    approved_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
