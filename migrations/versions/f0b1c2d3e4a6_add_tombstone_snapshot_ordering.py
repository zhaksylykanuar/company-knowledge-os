"""add tombstone snapshot ordering

Revision ID: f0b1c2d3e4a6
Revises: e0b1c2d3e4f5
Create Date: 2026-07-27 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f0b1c2d3e4a6"
down_revision: Union[str, Sequence[str], None] = "e0b1c2d3e4f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "source_records",
        sa.Column(
            "tombstone_observed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.execute(
        """
        UPDATE source_records
        SET tombstone_observed_at = COALESCE(observed_at, tombstoned_at)
        WHERE is_deleted = true
        """
    )
    op.drop_constraint(
        "ck_source_records_tombstone_provenance",
        "source_records",
        type_="check",
    )
    op.create_check_constraint(
        "ck_source_records_tombstone_provenance",
        "source_records",
        "("
        "is_deleted = false "
        "and tombstoned_at is null "
        "and tombstone_observed_at is null "
        "and tombstone_sync_job_id is null "
        "and tombstone_reason is null"
        ") or ("
        "is_deleted = true "
        "and tombstoned_at is not null "
        "and tombstone_observed_at is not null "
        "and tombstone_reason is not null"
        ")",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_source_records_tombstone_provenance",
        "source_records",
        type_="check",
    )
    op.create_check_constraint(
        "ck_source_records_tombstone_provenance",
        "source_records",
        "("
        "is_deleted = false "
        "and tombstoned_at is null "
        "and tombstone_sync_job_id is null "
        "and tombstone_reason is null"
        ") or ("
        "is_deleted = true "
        "and tombstoned_at is not null "
        "and tombstone_reason is not null"
        ")",
    )
    op.drop_column("source_records", "tombstone_observed_at")
