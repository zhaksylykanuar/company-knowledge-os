"""full run id lineage across source/normalized/graph

Revision ID: b8c9d1e2f3a4
Revises: a7b8c9d1e2f3
Create Date: 2026-06-13 12:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b8c9d1e2f3a4"
down_revision: Union[str, Sequence[str], None] = "a7b8c9d1e2f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "source_events",
        sa.Column("created_by_run_id", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "normalized_activity_items",
        sa.Column("run_id", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "entities",
        sa.Column("created_by_run_id", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "entities",
        sa.Column("updated_by_run_id", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "entity_links",
        sa.Column("created_by_run_id", sa.String(length=120), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("entity_links", "created_by_run_id")
    op.drop_column("entities", "updated_by_run_id")
    op.drop_column("entities", "created_by_run_id")
    op.drop_column("normalized_activity_items", "run_id")
    op.drop_column("source_events", "created_by_run_id")
