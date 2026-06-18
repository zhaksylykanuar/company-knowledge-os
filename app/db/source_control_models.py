from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, JSON, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SourceControlState(Base):
    """Local state for a source connector/control surface.

    This does not store connector credentials. It records only safe runtime
    state such as paused/resumed and the last local request.
    """

    __tablename__ = "source_control_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_type: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(40), default="disconnected", index=True)
    paused: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    last_action: Mapped[str | None] = mapped_column(String(40), nullable=True)
    last_action_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_action_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_request_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_success_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    input_watermark: Mapped[str | None] = mapped_column(String(255), nullable=True)
    latest_run_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    config_status: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SourceRunRequest(Base):
    """A safe request to test/sync/backfill/pause/resume a source.

    The row is the product action in the MVP: it is auditable and idempotent,
    and it intentionally does not call external providers.
    """

    __tablename__ = "source_run_requests"
    __table_args__ = (
        UniqueConstraint(
            "source_type",
            "action_type",
            "request_key",
            name="uq_source_run_requests_dedupe",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    source_type: Mapped[str] = mapped_column(String(80), index=True)
    action_type: Mapped[str] = mapped_column(String(40), index=True)
    status: Mapped[str] = mapped_column(String(40), default="requested", index=True)
    request_key: Mapped[str] = mapped_column(String(255), index=True)
    run_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    correlation_id: Mapped[str | None] = mapped_column(
        String(120), nullable=True, index=True
    )
    requested_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    input_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    result_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    error_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    external_side_effect: Mapped[bool] = mapped_column(Boolean, default=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    idempotency_key: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    source_state_before: Mapped[dict] = mapped_column(JSON, default=dict)
    source_state_after: Mapped[dict] = mapped_column(JSON, default=dict)
    audit_log_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
