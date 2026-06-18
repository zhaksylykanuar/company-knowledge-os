"""add source control requests

Revision ID: d1e2f3a4b5c6
Revises: c9d2e3f4a5b6
Create Date: 2026-06-13 22:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, Sequence[str], None] = "c9d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.create_table(
        "source_control_states",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_type", sa.String(length=80), nullable=False),
        sa.Column(
            "status",
            sa.String(length=40),
            nullable=False,
            server_default="disconnected",
        ),
        sa.Column("paused", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("last_action", sa.String(length=40), nullable=True),
        sa.Column("last_action_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_action_by", sa.String(length=120), nullable=True),
        sa.Column("last_request_key", sa.String(length=255), nullable=True),
        sa.Column(
            "config_status",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
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
    )
    op.create_index(
        op.f("ix_source_control_states_source_type"),
        "source_control_states",
        ["source_type"],
        unique=True,
    )
    op.create_index(
        op.f("ix_source_control_states_status"),
        "source_control_states",
        ["status"],
    )
    op.create_index(
        op.f("ix_source_control_states_paused"),
        "source_control_states",
        ["paused"],
    )

    op.create_table(
        "source_run_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.String(length=120), nullable=False),
        sa.Column("source_type", sa.String(length=80), nullable=False),
        sa.Column("action_type", sa.String(length=40), nullable=False),
        sa.Column(
            "status",
            sa.String(length=40),
            nullable=False,
            server_default="requested",
        ),
        sa.Column("request_key", sa.String(length=255), nullable=False),
        sa.Column("requested_by", sa.String(length=120), nullable=True),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "input_snapshot",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
        sa.Column(
            "result_summary",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
        sa.Column("audit_log_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_type",
            "action_type",
            "request_key",
            name="uq_source_run_requests_dedupe",
        ),
    )
    op.create_index(
        op.f("ix_source_run_requests_request_id"),
        "source_run_requests",
        ["request_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_source_run_requests_source_type"),
        "source_run_requests",
        ["source_type"],
    )
    op.create_index(
        op.f("ix_source_run_requests_action_type"),
        "source_run_requests",
        ["action_type"],
    )
    op.create_index(
        op.f("ix_source_run_requests_status"),
        "source_run_requests",
        ["status"],
    )
    op.create_index(
        op.f("ix_source_run_requests_request_key"),
        "source_run_requests",
        ["request_key"],
    )
    op.create_index(
        op.f("ix_source_run_requests_requested_at"),
        "source_run_requests",
        ["requested_at"],
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_table("source_run_requests")
    op.drop_table("source_control_states")
