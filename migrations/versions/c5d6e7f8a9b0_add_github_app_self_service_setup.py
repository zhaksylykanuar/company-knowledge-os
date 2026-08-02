"""add GitHub App self-service setup

Revision ID: c5d6e7f8a9b0
Revises: b4d5e6f7a8c9
Create Date: 2026-07-14 00:00:00.000000

Workspace-owned GitHub App credentials are encrypted before persistence. Setup
sessions keep only hashed one-time state and an encrypted PKCE verifier; OAuth
user tokens and installation access tokens are never stored.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c5d6e7f8a9b0"
down_revision: Union[str, Sequence[str], None] = "b4d5e6f7a8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "github_app_credentials",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("app_id", sa.String(length=100), nullable=False),
        sa.Column("app_slug", sa.String(length=120), nullable=False),
        sa.Column("app_name", sa.String(length=255), nullable=False),
        sa.Column("client_id", sa.String(length=255), nullable=False),
        sa.Column("encrypted_private_key", sa.Text(), nullable=False),
        sa.Column("encrypted_client_secret", sa.Text(), nullable=False),
        sa.Column("encrypted_webhook_secret", sa.Text(), nullable=True),
        sa.Column("owner_login", sa.String(length=255), nullable=True),
        sa.Column("owner_id", sa.String(length=100), nullable=True),
        sa.Column("owner_type", sa.String(length=40), nullable=True),
        sa.Column(
            "permissions",
            sa.JSON(),
            server_default=sa.text("'{}'::json"),
            nullable=False,
        ),
        sa.Column("html_url", sa.String(length=1000), nullable=True),
        sa.Column("callback_url", sa.String(length=1000), nullable=False),
        sa.Column(
            "source",
            sa.String(length=40),
            server_default="manifest",
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="active",
            nullable=False,
        ),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=500), nullable=True),
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
            "source in ('manifest', 'manual')",
            name="ck_github_app_credentials_source",
        ),
        sa.CheckConstraint(
            "status in ('active', 'error', 'revoked')",
            name="ck_github_app_credentials_status",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_github_app_credentials_created_by_user_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_github_app_credentials_workspace_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("app_id", name="uq_github_app_credentials_app_id"),
        sa.UniqueConstraint(
            "workspace_id",
            name="uq_github_app_credentials_workspace_id",
        ),
    )
    op.create_index(
        op.f("ix_github_app_credentials_app_id"),
        "github_app_credentials",
        ["app_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_github_app_credentials_created_by_user_id"),
        "github_app_credentials",
        ["created_by_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_github_app_credentials_status"),
        "github_app_credentials",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_github_app_credentials_workspace_id"),
        "github_app_credentials",
        ["workspace_id"],
        unique=False,
    )

    op.create_table(
        "github_app_installations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("credential_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("connection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("installation_id", sa.String(length=100), nullable=False),
        sa.Column("account_login", sa.String(length=255), nullable=False),
        sa.Column("account_id", sa.String(length=100), nullable=True),
        sa.Column("account_type", sa.String(length=40), nullable=True),
        sa.Column("repository_selection", sa.String(length=32), nullable=False),
        sa.Column(
            "permissions",
            sa.JSON(),
            server_default=sa.text("'{}'::json"),
            nullable=False,
        ),
        sa.Column("installation_settings_url", sa.String(length=1000), nullable=True),
        sa.Column("verified_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "repository_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="active",
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
        sa.CheckConstraint(
            "status in ('active', 'suspended', 'revoked')",
            name="ck_github_app_installations_status",
        ),
        sa.ForeignKeyConstraint(
            ["connection_id"],
            ["integration_connections.id"],
            name="fk_github_app_installations_connection_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["credential_id"],
            ["github_app_credentials.id"],
            name="fk_github_app_installations_credential_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["verified_by_user_id"],
            ["users.id"],
            name="fk_github_app_installations_verified_by_user_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_github_app_installations_workspace_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "connection_id",
            name="uq_github_app_installations_connection_id",
        ),
        sa.UniqueConstraint(
            "installation_id",
            name="uq_github_app_installations_installation_id",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            name="uq_github_app_installations_workspace_id",
        ),
    )
    op.create_index(
        op.f("ix_github_app_installations_connection_id"),
        "github_app_installations",
        ["connection_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_github_app_installations_credential_id"),
        "github_app_installations",
        ["credential_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_github_app_installations_installation_id"),
        "github_app_installations",
        ["installation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_github_app_installations_status"),
        "github_app_installations",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_github_app_installations_verified_by_user_id"),
        "github_app_installations",
        ["verified_by_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_github_app_installations_workspace_id"),
        "github_app_installations",
        ["workspace_id"],
        unique=False,
    )

    op.create_table(
        "github_app_setup_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("credential_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("connection_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("phase", sa.String(length=40), nullable=False),
        sa.Column("state_hash", sa.String(length=64), nullable=True),
        sa.Column("encrypted_pkce_verifier", sa.Text(), nullable=True),
        sa.Column("app_origin", sa.String(length=1000), nullable=False),
        sa.Column("installation_id", sa.String(length=100), nullable=True),
        sa.Column("installation_account_login", sa.String(length=255), nullable=True),
        sa.Column("installation_account_id", sa.String(length=100), nullable=True),
        sa.Column("repository_selection", sa.String(length=32), nullable=True),
        sa.Column(
            "repository_inventory",
            sa.JSON(),
            server_default=sa.text("'[]'::json"),
            nullable=False,
        ),
        sa.Column("error_code", sa.String(length=120), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
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
            "phase in ("
            "'manifest_pending', 'manifest_exchanging', 'installation_pending', "
            "'oauth_pending', 'oauth_exchanging', 'repository_selection', "
            "'completed', 'failed', 'cancelled'"
            ")",
            name="ck_github_app_setup_sessions_phase",
        ),
        sa.ForeignKeyConstraint(
            ["connection_id"],
            ["integration_connections.id"],
            name="fk_github_app_setup_sessions_connection_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_github_app_setup_sessions_created_by_user_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["credential_id"],
            ["github_app_credentials.id"],
            name="fk_github_app_setup_sessions_credential_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_github_app_setup_sessions_workspace_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "state_hash",
            name="uq_github_app_setup_sessions_state_hash",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            name="uq_github_app_setup_sessions_workspace_id",
        ),
    )
    op.create_index(
        op.f("ix_github_app_setup_sessions_connection_id"),
        "github_app_setup_sessions",
        ["connection_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_github_app_setup_sessions_created_by_user_id"),
        "github_app_setup_sessions",
        ["created_by_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_github_app_setup_sessions_credential_id"),
        "github_app_setup_sessions",
        ["credential_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_github_app_setup_sessions_expires_at"),
        "github_app_setup_sessions",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_github_app_setup_sessions_phase"),
        "github_app_setup_sessions",
        ["phase"],
        unique=False,
    )
    op.create_index(
        op.f("ix_github_app_setup_sessions_state_hash"),
        "github_app_setup_sessions",
        ["state_hash"],
        unique=False,
    )
    op.create_index(
        op.f("ix_github_app_setup_sessions_workspace_id"),
        "github_app_setup_sessions",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        "ix_github_app_setup_sessions_workspace_phase",
        "github_app_setup_sessions",
        ["workspace_id", "phase"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_github_app_setup_sessions_workspace_phase",
        table_name="github_app_setup_sessions",
    )
    op.drop_index(
        op.f("ix_github_app_setup_sessions_workspace_id"),
        table_name="github_app_setup_sessions",
    )
    op.drop_index(
        op.f("ix_github_app_setup_sessions_state_hash"),
        table_name="github_app_setup_sessions",
    )
    op.drop_index(
        op.f("ix_github_app_setup_sessions_phase"),
        table_name="github_app_setup_sessions",
    )
    op.drop_index(
        op.f("ix_github_app_setup_sessions_expires_at"),
        table_name="github_app_setup_sessions",
    )
    op.drop_index(
        op.f("ix_github_app_setup_sessions_credential_id"),
        table_name="github_app_setup_sessions",
    )
    op.drop_index(
        op.f("ix_github_app_setup_sessions_created_by_user_id"),
        table_name="github_app_setup_sessions",
    )
    op.drop_index(
        op.f("ix_github_app_setup_sessions_connection_id"),
        table_name="github_app_setup_sessions",
    )
    op.drop_table("github_app_setup_sessions")

    op.drop_index(
        op.f("ix_github_app_installations_workspace_id"),
        table_name="github_app_installations",
    )
    op.drop_index(
        op.f("ix_github_app_installations_verified_by_user_id"),
        table_name="github_app_installations",
    )
    op.drop_index(
        op.f("ix_github_app_installations_status"),
        table_name="github_app_installations",
    )
    op.drop_index(
        op.f("ix_github_app_installations_installation_id"),
        table_name="github_app_installations",
    )
    op.drop_index(
        op.f("ix_github_app_installations_credential_id"),
        table_name="github_app_installations",
    )
    op.drop_index(
        op.f("ix_github_app_installations_connection_id"),
        table_name="github_app_installations",
    )
    op.drop_table("github_app_installations")

    op.drop_index(
        op.f("ix_github_app_credentials_workspace_id"),
        table_name="github_app_credentials",
    )
    op.drop_index(
        op.f("ix_github_app_credentials_status"),
        table_name="github_app_credentials",
    )
    op.drop_index(
        op.f("ix_github_app_credentials_created_by_user_id"),
        table_name="github_app_credentials",
    )
    op.drop_index(
        op.f("ix_github_app_credentials_app_id"),
        table_name="github_app_credentials",
    )
    op.drop_table("github_app_credentials")
