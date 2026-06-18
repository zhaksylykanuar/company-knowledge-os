"""add source run lifecycle

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-06-13 23:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e2f3a4b5c6d7"
down_revision: Union[str, Sequence[str], None] = "d1e2f3a4b5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.add_column(
        "source_control_states",
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "source_control_states",
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "source_control_states",
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "source_control_states",
        sa.Column("input_watermark", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "source_control_states",
        sa.Column("latest_run_id", sa.String(length=120), nullable=True),
    )

    op.add_column(
        "source_run_requests",
        sa.Column("run_id", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "source_run_requests",
        sa.Column("correlation_id", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "source_run_requests",
        sa.Column("approved_by", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "source_run_requests",
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "source_run_requests",
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "source_run_requests",
        sa.Column(
            "error_summary",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
    )
    op.add_column(
        "source_run_requests",
        sa.Column(
            "external_side_effect",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "source_run_requests",
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "source_run_requests",
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "source_run_requests",
        sa.Column(
            "source_state_before",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
    )
    op.add_column(
        "source_run_requests",
        sa.Column(
            "source_state_after",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
    )
    op.create_index(
        op.f("ix_source_run_requests_run_id"),
        "source_run_requests",
        ["run_id"],
    )
    op.create_index(
        op.f("ix_source_run_requests_correlation_id"),
        "source_run_requests",
        ["correlation_id"],
    )
    op.create_index(
        op.f("ix_source_run_requests_idempotency_key"),
        "source_run_requests",
        ["idempotency_key"],
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index(
        op.f("ix_source_run_requests_idempotency_key"),
        table_name="source_run_requests",
    )
    op.drop_index(
        op.f("ix_source_run_requests_correlation_id"),
        table_name="source_run_requests",
    )
    op.drop_index(
        op.f("ix_source_run_requests_run_id"),
        table_name="source_run_requests",
    )
    for column in (
        "source_state_after",
        "source_state_before",
        "idempotency_key",
        "retry_count",
        "external_side_effect",
        "error_summary",
        "finished_at",
        "started_at",
        "approved_by",
        "correlation_id",
        "run_id",
    ):
        op.drop_column("source_run_requests", column)
    for column in (
        "latest_run_id",
        "input_watermark",
        "last_error_at",
        "last_success_at",
        "last_sync_at",
    ):
        op.drop_column("source_control_states", column)
