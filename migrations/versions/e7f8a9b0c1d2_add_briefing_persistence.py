"""add briefing persistence (briefings + briefing_items)

Persists the deterministic Founder Briefing so the founder has history to
revisit. Generation logic is unchanged and still LLM-free; these tables only
store its output. Briefings Chunk 1.

Revision ID: e7f8a9b0c1d2
Revises: c0e1f2a3b4d5
Create Date: 2026-06-29 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "e7f8a9b0c1d2"
down_revision: Union[str, Sequence[str], None] = "c0e1f2a3b4d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the briefings + briefing_items persistence tables."""

    op.create_table(
        "briefings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
        sa.Column(
            "generated_by",
            sa.String(length=50),
            server_default="deterministic_v0",
            nullable=False,
        ),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), server_default="", nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "signals",
            sa.JSON(),
            server_default=sa.text("'{}'::json"),
            nullable=False,
        ),
        sa.Column(
            "warnings",
            sa.JSON(),
            server_default=sa.text("'[]'::json"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_briefings_workspace_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_briefings_created_by_user_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_briefings_workspace_id"), "briefings", ["workspace_id"]
    )
    op.create_index(
        op.f("ix_briefings_created_by_user_id"),
        "briefings",
        ["created_by_user_id"],
    )
    op.create_index(
        "ix_briefings_workspace_created_at",
        "briefings",
        ["workspace_id", "created_at"],
    )

    op.create_table(
        "briefing_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("briefing_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        sa.Column("item_key", sa.String(length=120), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), server_default="", nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column(
            "confidence", sa.Float(), server_default="0", nullable=False
        ),
        sa.Column("recommended_next_step", sa.Text(), nullable=True),
        sa.Column(
            "evidence_refs",
            sa.JSON(),
            server_default=sa.text("'[]'::json"),
            nullable=False,
        ),
        sa.Column(
            "related_entities",
            sa.JSON(),
            server_default=sa.text("'[]'::json"),
            nullable=False,
        ),
        sa.Column(
            "warnings",
            sa.JSON(),
            server_default=sa.text("'[]'::json"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["briefing_id"],
            ["briefings.id"],
            name="fk_briefing_items_briefing_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_briefing_items_briefing_id"),
        "briefing_items",
        ["briefing_id"],
    )
    op.create_index(
        "ix_briefing_items_briefing_position",
        "briefing_items",
        ["briefing_id", "position"],
    )


def downgrade() -> None:
    """Drop the briefing persistence tables."""

    op.drop_index(
        "ix_briefing_items_briefing_position", table_name="briefing_items"
    )
    op.drop_index(
        op.f("ix_briefing_items_briefing_id"), table_name="briefing_items"
    )
    op.drop_table("briefing_items")
    op.drop_index(
        "ix_briefings_workspace_created_at", table_name="briefings"
    )
    op.drop_index(
        op.f("ix_briefings_created_by_user_id"), table_name="briefings"
    )
    op.drop_index(op.f("ix_briefings_workspace_id"), table_name="briefings")
    op.drop_table("briefings")
