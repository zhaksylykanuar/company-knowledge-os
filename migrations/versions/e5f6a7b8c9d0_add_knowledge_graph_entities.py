"""add knowledge graph entities

Revision ID: e5f6a7b8c9d0
Revises: d9e0f1a2b3c4
Create Date: 2026-06-12 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "e5f6a7b8c9d0"
down_revision = "d9e0f1a2b3c4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "entities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("entity_id", sa.String(length=120), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("canonical_name", sa.String(length=255), nullable=False),
        sa.Column(
            "attrs",
            sa.JSON(),
            server_default=sa.text("'{}'::json"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("entity_id"),
    )
    op.create_index("ix_entities_entity_type", "entities", ["entity_type"])

    op.create_table(
        "entity_aliases",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("entity_id", sa.String(length=120), nullable=False),
        sa.Column("alias", sa.String(length=255), nullable=False),
        sa.Column("normalized_alias", sa.String(length=255), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column(
            "confirmed_by_user",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("entity_id", "normalized_alias"),
    )
    op.create_index(
        "ix_entity_aliases_normalized_alias",
        "entity_aliases",
        ["normalized_alias"],
    )

    op.create_table(
        "entity_links",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("link_id", sa.String(length=120), nullable=False),
        sa.Column("from_entity_id", sa.String(length=120), nullable=False),
        sa.Column("to_entity_id", sa.String(length=120), nullable=False),
        sa.Column("relation", sa.String(length=60), nullable=False),
        sa.Column(
            "evidence_refs",
            sa.JSON(),
            server_default=sa.text("'[]'::json"),
            nullable=False,
        ),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("link_id"),
    )
    op.create_index(
        "ix_entity_links_from_entity_id", "entity_links", ["from_entity_id"]
    )
    op.create_index("ix_entity_links_to_entity_id", "entity_links", ["to_entity_id"])
    op.create_index("ix_entity_links_relation", "entity_links", ["relation"])


def downgrade() -> None:
    op.drop_table("entity_links")
    op.drop_table("entity_aliases")
    op.drop_table("entities")
