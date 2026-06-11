"""add status snapshots

Revision ID: a5f1c2d3e4b6
Revises: e5f6a7b8c9d0
Create Date: 2026-06-11 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "a5f1c2d3e4b6"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "status_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.String(length=120), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("entity_id", sa.String(length=255), nullable=False),
        sa.Column("status_color", sa.String(length=20), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column(
            "what_changed_json",
            sa.JSON(),
            server_default=sa.text("'[]'::json"),
            nullable=False,
        ),
        sa.Column(
            "current_work_json",
            sa.JSON(),
            server_default=sa.text("'[]'::json"),
            nullable=False,
        ),
        sa.Column(
            "blockers_json",
            sa.JSON(),
            server_default=sa.text("'[]'::json"),
            nullable=False,
        ),
        sa.Column(
            "risks_json",
            sa.JSON(),
            server_default=sa.text("'[]'::json"),
            nullable=False,
        ),
        sa.Column(
            "conflicts_json",
            sa.JSON(),
            server_default=sa.text("'[]'::json"),
            nullable=False,
        ),
        sa.Column(
            "recommendations_json",
            sa.JSON(),
            server_default=sa.text("'[]'::json"),
            nullable=False,
        ),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("confidence_reason", sa.Text(), nullable=False),
        sa.Column("last_meaningful_update_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "evidence_source_ids_json",
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_status_snapshots_organization_id", "status_snapshots", ["organization_id"])
    op.create_index("ix_status_snapshots_entity_type", "status_snapshots", ["entity_type"])
    op.create_index("ix_status_snapshots_entity_id", "status_snapshots", ["entity_id"])
    op.create_index("ix_status_snapshots_status_color", "status_snapshots", ["status_color"])
    op.create_index(
        "ix_status_snapshots_last_meaningful_update_at",
        "status_snapshots",
        ["last_meaningful_update_at"],
    )
    op.create_index("ix_status_snapshots_created_at", "status_snapshots", ["created_at"])
    op.create_index(
        "ix_status_snapshots_entity_created",
        "status_snapshots",
        ["organization_id", "entity_type", "entity_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_status_snapshots_entity_created", table_name="status_snapshots")
    op.drop_index("ix_status_snapshots_created_at", table_name="status_snapshots")
    op.drop_index(
        "ix_status_snapshots_last_meaningful_update_at",
        table_name="status_snapshots",
    )
    op.drop_index("ix_status_snapshots_status_color", table_name="status_snapshots")
    op.drop_index("ix_status_snapshots_entity_id", table_name="status_snapshots")
    op.drop_index("ix_status_snapshots_entity_type", table_name="status_snapshots")
    op.drop_index("ix_status_snapshots_organization_id", table_name="status_snapshots")
    op.drop_table("status_snapshots")
