"""add transactional company memory streams

Revision ID: d9a0b1c2d3e4
Revises: d8f9a0b1c2d3
Create Date: 2026-07-27 00:00:00.000000

Identity sequences are allocated before transaction commit and therefore cannot
serve as a lossless acknowledgement cursor under concurrency. A transactional
per-workspace counter closes that gap.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "d9a0b1c2d3e4"
down_revision: Union[str, Sequence[str], None] = "d8f9a0b1c2d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "company_memory_event_streams",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "last_sequence",
            sa.BigInteger(),
            server_default="0",
            nullable=False,
        ),
        sa.CheckConstraint(
            "last_sequence >= 0",
            name="ck_company_memory_event_streams_last_sequence",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_company_memory_event_streams_workspace_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("workspace_id"),
    )
    op.add_column(
        "company_memory_events",
        sa.Column("workspace_sequence", sa.BigInteger(), nullable=True),
    )
    op.execute(
        """
        WITH ranked AS (
            SELECT
                sequence_id,
                row_number() OVER (
                    PARTITION BY workspace_id
                    ORDER BY sequence_id
                ) AS workspace_sequence
            FROM company_memory_events
        )
        UPDATE company_memory_events AS event
        SET workspace_sequence = ranked.workspace_sequence
        FROM ranked
        WHERE event.sequence_id = ranked.sequence_id
        """
    )
    op.execute(
        """
        INSERT INTO company_memory_event_streams (workspace_id, last_sequence)
        SELECT workspace_id, max(workspace_sequence)
        FROM company_memory_events
        GROUP BY workspace_id
        """
    )
    op.alter_column(
        "company_memory_events",
        "workspace_sequence",
        existing_type=sa.BigInteger(),
        nullable=False,
    )
    op.create_unique_constraint(
        "uq_company_memory_events_workspace_sequence",
        "company_memory_events",
        ["workspace_id", "workspace_sequence"],
    )
    op.drop_index(
        "ix_company_memory_events_workspace_sequence",
        table_name="company_memory_events",
    )
    op.create_index(
        "ix_company_memory_events_workspace_sequence",
        "company_memory_events",
        ["workspace_id", "workspace_sequence"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_company_memory_events_workspace_sequence",
        table_name="company_memory_events",
    )
    op.create_index(
        "ix_company_memory_events_workspace_sequence",
        "company_memory_events",
        ["workspace_id", "sequence_id"],
        unique=False,
    )
    op.drop_constraint(
        "uq_company_memory_events_workspace_sequence",
        "company_memory_events",
        type_="unique",
    )
    op.drop_column("company_memory_events", "workspace_sequence")
    op.drop_table("company_memory_event_streams")
