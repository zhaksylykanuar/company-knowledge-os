"""add normalized activity items

Revision ID: d9e0f1a2b3c4
Revises: c8d9e0f1a2b3
Create Date: 2026-05-19 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "d9e0f1a2b3c4"
down_revision = "c8d9e0f1a2b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "normalized_activity_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("activity_item_id", sa.String(length=120), nullable=False),
        sa.Column("source_event_id", sa.String(length=255), nullable=True),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("source_object_id", sa.String(length=255), nullable=False),
        sa.Column("activity_type", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("actor", sa.String(length=255), nullable=True),
        sa.Column("activity_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("project", sa.String(length=255), nullable=True),
        sa.Column("safe_summary", sa.Text(), nullable=True),
        sa.Column(
            "related_people",
            sa.JSON(),
            server_default=sa.text("'[]'::json"),
            nullable=False,
        ),
        sa.Column(
            "related_jira_keys",
            sa.JSON(),
            server_default=sa.text("'[]'::json"),
            nullable=False,
        ),
        sa.Column(
            "related_prs",
            sa.JSON(),
            server_default=sa.text("'[]'::json"),
            nullable=False,
        ),
        sa.Column(
            "related_files",
            sa.JSON(),
            server_default=sa.text("'[]'::json"),
            nullable=False,
        ),
        sa.Column(
            "evidence_refs",
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
            ["source_event_id"],
            ["source_events.source_event_id"],
            name="fk_normalized_activity_source_event_id",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_normalized_activity_items_activity_item_id"),
        "normalized_activity_items",
        ["activity_item_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_normalized_activity_items_source_event_id"),
        "normalized_activity_items",
        ["source_event_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_normalized_activity_items_source"),
        "normalized_activity_items",
        ["source"],
        unique=False,
    )
    op.create_index(
        op.f("ix_normalized_activity_items_source_object_id"),
        "normalized_activity_items",
        ["source_object_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_normalized_activity_items_activity_type"),
        "normalized_activity_items",
        ["activity_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_normalized_activity_items_activity_created_at"),
        "normalized_activity_items",
        ["activity_created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_normalized_activity_items_project"),
        "normalized_activity_items",
        ["project"],
        unique=False,
    )
    op.create_index(
        op.f("ix_normalized_activity_items_created_at"),
        "normalized_activity_items",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_normalized_activity_items_source_object_created",
        "normalized_activity_items",
        ["source", "source_object_id", "activity_created_at"],
        unique=False,
    )
    op.create_index(
        "ix_normalized_activity_items_source_event_created",
        "normalized_activity_items",
        ["source_event_id", "activity_created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_normalized_activity_items_source_event_created",
        table_name="normalized_activity_items",
    )
    op.drop_index(
        "ix_normalized_activity_items_source_object_created",
        table_name="normalized_activity_items",
    )
    op.drop_index(
        op.f("ix_normalized_activity_items_created_at"),
        table_name="normalized_activity_items",
    )
    op.drop_index(
        op.f("ix_normalized_activity_items_project"),
        table_name="normalized_activity_items",
    )
    op.drop_index(
        op.f("ix_normalized_activity_items_activity_created_at"),
        table_name="normalized_activity_items",
    )
    op.drop_index(
        op.f("ix_normalized_activity_items_activity_type"),
        table_name="normalized_activity_items",
    )
    op.drop_index(
        op.f("ix_normalized_activity_items_source_object_id"),
        table_name="normalized_activity_items",
    )
    op.drop_index(
        op.f("ix_normalized_activity_items_source"),
        table_name="normalized_activity_items",
    )
    op.drop_index(
        op.f("ix_normalized_activity_items_source_event_id"),
        table_name="normalized_activity_items",
    )
    op.drop_index(
        op.f("ix_normalized_activity_items_activity_item_id"),
        table_name="normalized_activity_items",
    )
    op.drop_table("normalized_activity_items")
