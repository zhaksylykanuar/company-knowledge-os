"""add durable sync job leases and cancellation

Revision ID: c4d5e6f7a8b9
Revises: b2c3d4e5f6a7
Create Date: 2026-07-29 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c4d5e6f7a8b9"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("ck_sync_jobs_status", "sync_jobs", type_="check")
    op.create_check_constraint(
        "ck_sync_jobs_status",
        "sync_jobs",
        "status in "
        "('queued', 'running', 'succeeded', 'failed', 'partial', 'cancelled')",
    )
    op.add_column(
        "sync_jobs",
        sa.Column(
            "attempt_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.add_column(
        "sync_jobs",
        sa.Column(
            "max_attempts",
            sa.Integer(),
            server_default="3",
            nullable=False,
        ),
    )
    op.add_column(
        "sync_jobs",
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.add_column(
        "sync_jobs",
        sa.Column("lease_owner", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "sync_jobs",
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "sync_jobs",
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_sync_jobs_next_attempt_at",
        "sync_jobs",
        ["next_attempt_at"],
    )
    op.create_index(
        "ix_sync_jobs_lease_expires_at",
        "sync_jobs",
        ["lease_expires_at"],
    )
    op.create_index(
        "ix_sync_jobs_claim",
        "sync_jobs",
        ["provider", "status", "next_attempt_at", "lease_expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_sync_jobs_claim", table_name="sync_jobs")
    op.drop_index("ix_sync_jobs_lease_expires_at", table_name="sync_jobs")
    op.drop_index("ix_sync_jobs_next_attempt_at", table_name="sync_jobs")
    op.drop_column("sync_jobs", "cancel_requested_at")
    op.drop_column("sync_jobs", "lease_expires_at")
    op.drop_column("sync_jobs", "lease_owner")
    op.drop_column("sync_jobs", "next_attempt_at")
    op.drop_column("sync_jobs", "max_attempts")
    op.drop_column("sync_jobs", "attempt_count")
    op.drop_constraint("ck_sync_jobs_status", "sync_jobs", type_="check")
    op.create_check_constraint(
        "ck_sync_jobs_status",
        "sync_jobs",
        "status in ('queued', 'running', 'succeeded', 'failed', 'partial')",
    )
