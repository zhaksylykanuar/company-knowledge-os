"""share packs

Revision ID: c9d2e3f4a5b6
Revises: b8c9d1e2f3a4
Create Date: 2026-06-13 19:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c9d2e3f4a5b6"
down_revision: Union[str, Sequence[str], None] = "b8c9d1e2f3a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "share_packs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("pack_id", sa.String(length=120), nullable=False),
        sa.Column(
            "company_id",
            sa.String(length=120),
            nullable=False,
            server_default="default",
        ),
        sa.Column("pack_type", sa.String(length=80), nullable=False),
        sa.Column("audience", sa.String(length=20), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("title", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("generated_summary", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "sections", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")
        ),
        sa.Column(
            "evidence_coverage",
            sa.String(length=80),
            nullable=False,
            server_default="",
        ),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column(
            "declared_vs_observed",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
        sa.Column(
            "redaction_manifest",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
        sa.Column(
            "included_entity_ids",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
        sa.Column(
            "included_finding_ids",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
        sa.Column(
            "included_source_event_ids",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
        sa.Column(
            "created_by",
            sa.String(length=120),
            nullable=False,
            server_default="founder",
        ),
        sa.Column("approved_by", sa.String(length=120), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("exported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "content_hash", sa.String(length=128), nullable=False, server_default=""
        ),
        sa.Column("approved_content_hash", sa.String(length=128), nullable=True),
        sa.Column("source_snapshot", sa.JSON(), nullable=True),
        sa.Column("approved_snapshot", sa.JSON(), nullable=True),
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
    )
    op.create_index(
        op.f("ix_share_packs_pack_id"), "share_packs", ["pack_id"], unique=True
    )
    op.create_index(
        op.f("ix_share_packs_company_id"), "share_packs", ["company_id"]
    )
    op.create_index(op.f("ix_share_packs_pack_type"), "share_packs", ["pack_type"])
    op.create_index(op.f("ix_share_packs_audience"), "share_packs", ["audience"])
    op.create_index(op.f("ix_share_packs_status"), "share_packs", ["status"])
    op.create_index(
        op.f("ix_share_packs_content_hash"), "share_packs", ["content_hash"]
    )
    op.create_index(
        op.f("ix_share_packs_created_at"), "share_packs", ["created_at"]
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("share_packs")
