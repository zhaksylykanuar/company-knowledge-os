"""add knowledge scores

Revision ID: f33a4a9caaa5
Revises: e1f2a3b4c5d6
Create Date: 2026-04-27 01:05:27.865788

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f33a4a9caaa5"
down_revision: Union[str, Sequence[str], None] = "e1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "knowledge_scores",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("entity_id", sa.String(length=255), nullable=False),
        sa.Column("source_document_id", sa.String(length=255), nullable=True),
        sa.Column("chunk_id", sa.String(length=255), nullable=True),
        sa.Column("importance_score", sa.Float(), nullable=False),
        sa.Column("urgency_score", sa.Float(), nullable=False),
        sa.Column("risk_score", sa.Float(), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column("attention_score", sa.Float(), nullable=False),
        sa.Column("reasons", sa.JSON(), nullable=False),
        sa.Column("evidence_refs", sa.JSON(), nullable=False),
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
        sa.UniqueConstraint(
            "entity_type",
            "entity_id",
            name="uq_knowledge_scores_entity",
        ),
    )
    op.create_index(
        op.f("ix_knowledge_scores_chunk_id"),
        "knowledge_scores",
        ["chunk_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_knowledge_scores_entity_id"),
        "knowledge_scores",
        ["entity_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_knowledge_scores_entity_type"),
        "knowledge_scores",
        ["entity_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_knowledge_scores_source_document_id"),
        "knowledge_scores",
        ["source_document_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f("ix_knowledge_scores_source_document_id"),
        table_name="knowledge_scores",
    )
    op.drop_index(
        op.f("ix_knowledge_scores_entity_type"),
        table_name="knowledge_scores",
    )
    op.drop_index(
        op.f("ix_knowledge_scores_entity_id"),
        table_name="knowledge_scores",
    )
    op.drop_index(
        op.f("ix_knowledge_scores_chunk_id"),
        table_name="knowledge_scores",
    )
    op.drop_table("knowledge_scores")
