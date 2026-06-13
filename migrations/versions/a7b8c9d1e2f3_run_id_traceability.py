"""run id traceability on findings and proposals

Revision ID: a7b8c9d1e2f3
Revises: f6a7b8c9d1e2
Create Date: 2026-06-13 11:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a7b8c9d1e2f3"
down_revision: Union[str, Sequence[str], None] = "f6a7b8c9d1e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "second_opinion_findings",
        sa.Column("last_run_id", sa.String(length=120), nullable=True),
    )
    op.create_index(
        op.f("ix_second_opinion_findings_last_run_id"),
        "second_opinion_findings",
        ["last_run_id"],
    )
    op.add_column(
        "agent_proposals",
        sa.Column("run_id", sa.String(length=120), nullable=True),
    )
    op.create_index(
        op.f("ix_agent_proposals_run_id"), "agent_proposals", ["run_id"]
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_agent_proposals_run_id"), table_name="agent_proposals")
    op.drop_column("agent_proposals", "run_id")
    op.drop_index(
        op.f("ix_second_opinion_findings_last_run_id"),
        table_name="second_opinion_findings",
    )
    op.drop_column("second_opinion_findings", "last_run_id")
