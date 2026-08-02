"""add account setup tokens

Revision ID: e9a0b1c2d3e4
Revises: e8f9a0b1c2d3
Create Date: 2026-07-05 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "e9a0b1c2d3e4"
down_revision: Union[str, Sequence[str], None] = "e8f9a0b1c2d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "account_setup_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("purpose", sa.String(length=40), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "purpose in ('team_invite')",
            name="ck_account_setup_tokens_purpose",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_account_setup_tokens_created_by_user_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_account_setup_tokens_user_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "token_hash",
            name="uq_account_setup_tokens_token_hash",
        ),
    )
    op.create_index(
        op.f("ix_account_setup_tokens_consumed_at"),
        "account_setup_tokens",
        ["consumed_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_account_setup_tokens_created_by_user_id"),
        "account_setup_tokens",
        ["created_by_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_account_setup_tokens_expires_at"),
        "account_setup_tokens",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_account_setup_tokens_purpose"),
        "account_setup_tokens",
        ["purpose"],
        unique=False,
    )
    op.create_index(
        op.f("ix_account_setup_tokens_token_hash"),
        "account_setup_tokens",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        op.f("ix_account_setup_tokens_user_id"),
        "account_setup_tokens",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_account_setup_tokens_user_id"), table_name="account_setup_tokens")
    op.drop_index(
        op.f("ix_account_setup_tokens_token_hash"),
        table_name="account_setup_tokens",
    )
    op.drop_index(
        op.f("ix_account_setup_tokens_purpose"),
        table_name="account_setup_tokens",
    )
    op.drop_index(
        op.f("ix_account_setup_tokens_expires_at"),
        table_name="account_setup_tokens",
    )
    op.drop_index(
        op.f("ix_account_setup_tokens_created_by_user_id"),
        table_name="account_setup_tokens",
    )
    op.drop_index(
        op.f("ix_account_setup_tokens_consumed_at"),
        table_name="account_setup_tokens",
    )
    op.drop_table("account_setup_tokens")
