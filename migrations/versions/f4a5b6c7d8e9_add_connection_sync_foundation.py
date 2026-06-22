"""add connection sync foundation

Revision ID: f4a5b6c7d8e9
Revises: f3a4b5c6d7e8
Create Date: 2026-06-22 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "f4a5b6c7d8e9"
down_revision: Union[str, Sequence[str], None] = "f3a4b5c6d7e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.create_table(
        "integration_connections",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column(
            "status",
            sa.String(length=40),
            nullable=False,
            server_default="connected",
        ),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("external_account_id", sa.String(length=255), nullable=True),
        sa.Column(
            "scopes",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
        sa.Column("encrypted_access_token", sa.Text(), nullable=True),
        sa.Column("encrypted_refresh_token", sa.Text(), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "metadata",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
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
        sa.CheckConstraint(
            "provider in ('github', 'jira', 'gmail', 'drive')",
            name="ck_integration_connections_provider",
        ),
        sa.CheckConstraint(
            "status in ('connected', 'error', 'revoked', 'disabled')",
            name="ck_integration_connections_status",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_integration_connections_workspace_id",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_integration_connections_workspace_id"),
        "integration_connections",
        ["workspace_id"],
    )
    op.create_index(
        op.f("ix_integration_connections_provider"),
        "integration_connections",
        ["provider"],
    )
    op.create_index(
        op.f("ix_integration_connections_status"),
        "integration_connections",
        ["status"],
    )
    op.create_index(
        op.f("ix_integration_connections_external_account_id"),
        "integration_connections",
        ["external_account_id"],
    )
    op.create_index(
        op.f("ix_integration_connections_last_sync_at"),
        "integration_connections",
        ["last_sync_at"],
    )
    op.create_index(
        "ix_integration_connections_workspace_provider",
        "integration_connections",
        ["workspace_id", "provider"],
    )
    op.create_index(
        "ix_integration_connections_provider_external_account_id",
        "integration_connections",
        ["provider", "external_account_id"],
    )

    op.create_table(
        "sync_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("connection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column(
            "status",
            sa.String(length=40),
            nullable=False,
            server_default="queued",
        ),
        sa.Column(
            "sync_type",
            sa.String(length=40),
            nullable=False,
            server_default="manual",
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cursor_before", sa.JSON(), nullable=True),
        sa.Column("cursor_after", sa.JSON(), nullable=True),
        sa.Column(
            "records_seen",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "records_created",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "records_updated",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("logs", sa.JSON(), nullable=True),
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
        sa.CheckConstraint(
            "provider in ('github', 'jira', 'gmail', 'drive')",
            name="ck_sync_jobs_provider",
        ),
        sa.CheckConstraint(
            "status in ('queued', 'running', 'succeeded', 'failed', 'partial')",
            name="ck_sync_jobs_status",
        ),
        sa.CheckConstraint(
            "sync_type in ('initial', 'incremental', 'manual')",
            name="ck_sync_jobs_sync_type",
        ),
        sa.ForeignKeyConstraint(
            ["connection_id"],
            ["integration_connections.id"],
            name="fk_sync_jobs_connection_id",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_sync_jobs_workspace_id",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_sync_jobs_workspace_id"), "sync_jobs", ["workspace_id"])
    op.create_index(op.f("ix_sync_jobs_connection_id"), "sync_jobs", ["connection_id"])
    op.create_index(op.f("ix_sync_jobs_provider"), "sync_jobs", ["provider"])
    op.create_index(op.f("ix_sync_jobs_status"), "sync_jobs", ["status"])
    op.create_index(op.f("ix_sync_jobs_sync_type"), "sync_jobs", ["sync_type"])
    op.create_index(op.f("ix_sync_jobs_started_at"), "sync_jobs", ["started_at"])
    op.create_index(op.f("ix_sync_jobs_created_at"), "sync_jobs", ["created_at"])
    op.create_index(
        "ix_sync_jobs_workspace_status",
        "sync_jobs",
        ["workspace_id", "status"],
    )
    op.create_index(
        "ix_sync_jobs_connection_started_at",
        "sync_jobs",
        ["connection_id", "started_at"],
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_table("sync_jobs")
    op.drop_table("integration_connections")
