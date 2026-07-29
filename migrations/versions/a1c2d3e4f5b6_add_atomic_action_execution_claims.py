"""add atomic action execution claims

Revision ID: a1c2d3e4f5b6
Revises: f0b1c2d3e4a6
Create Date: 2026-07-29 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "a1c2d3e4f5b6"
down_revision: Union[str, Sequence[str], None] = "f0b1c2d3e4a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "action_executions",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "action_executions",
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "action_executions",
        sa.Column("connection_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "action_executions",
        sa.Column("client_idempotency_key", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "action_executions",
        sa.Column("request_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "action_executions",
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "action_executions",
        sa.Column("reconciled_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.execute(
        """
        UPDATE action_executions AS execution
        SET workspace_id = proposal.workspace_id,
            client_idempotency_key = 'legacy-' || execution.id::text,
            request_hash = md5(execution.id::text) || md5('legacy:' || execution.id::text),
            claimed_at = COALESCE(execution.started_at, execution.created_at)
        FROM action_proposals AS proposal
        WHERE proposal.id = execution.action_proposal_id
        """
    )

    op.alter_column("action_executions", "workspace_id", nullable=False)
    op.alter_column("action_executions", "client_idempotency_key", nullable=False)
    op.alter_column("action_executions", "request_hash", nullable=False)
    op.alter_column("action_executions", "claimed_at", nullable=False)

    op.drop_constraint(
        "ck_action_executions_status",
        "action_executions",
        type_="check",
    )
    op.create_check_constraint(
        "ck_action_executions_status",
        "action_executions",
        "status in ('claimed', 'running', 'succeeded', 'failed', 'uncertain')",
    )
    op.execute(
        """
        UPDATE action_executions
        SET status = 'uncertain'
        WHERE status = 'running'
        """
    )
    op.create_foreign_key(
        "fk_action_executions_workspace_id",
        "action_executions",
        "workspaces",
        ["workspace_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_action_executions_requested_by_user_id",
        "action_executions",
        "users",
        ["requested_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_action_executions_connection_id",
        "action_executions",
        "integration_connections",
        ["connection_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_action_executions_workspace_id"),
        "action_executions",
        ["workspace_id"],
    )
    op.create_index(
        op.f("ix_action_executions_requested_by_user_id"),
        "action_executions",
        ["requested_by_user_id"],
    )
    op.create_index(
        op.f("ix_action_executions_connection_id"),
        "action_executions",
        ["connection_id"],
    )
    op.create_index(
        "uq_action_executions_workspace_client_idempotency_key",
        "action_executions",
        ["workspace_id", "client_idempotency_key"],
        unique=True,
    )
    op.create_index(
        "uq_action_executions_one_active_or_success_per_proposal",
        "action_executions",
        ["action_proposal_id"],
        unique=True,
        postgresql_where=sa.text(
            "status in ('claimed', 'running', 'succeeded', 'uncertain')"
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_action_executions_one_active_or_success_per_proposal",
        table_name="action_executions",
    )
    op.drop_index(
        "uq_action_executions_workspace_client_idempotency_key",
        table_name="action_executions",
    )
    op.drop_index(
        op.f("ix_action_executions_connection_id"),
        table_name="action_executions",
    )
    op.drop_index(
        op.f("ix_action_executions_requested_by_user_id"),
        table_name="action_executions",
    )
    op.drop_index(
        op.f("ix_action_executions_workspace_id"),
        table_name="action_executions",
    )
    op.drop_constraint(
        "fk_action_executions_connection_id",
        "action_executions",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_action_executions_requested_by_user_id",
        "action_executions",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_action_executions_workspace_id",
        "action_executions",
        type_="foreignkey",
    )
    op.execute(
        """
        UPDATE action_executions
        SET status = 'failed'
        WHERE status IN ('claimed', 'uncertain')
        """
    )
    op.drop_constraint(
        "ck_action_executions_status",
        "action_executions",
        type_="check",
    )
    op.create_check_constraint(
        "ck_action_executions_status",
        "action_executions",
        "status in ('running', 'succeeded', 'failed')",
    )
    op.drop_column("action_executions", "reconciled_at")
    op.drop_column("action_executions", "claimed_at")
    op.drop_column("action_executions", "request_hash")
    op.drop_column("action_executions", "client_idempotency_key")
    op.drop_column("action_executions", "connection_id")
    op.drop_column("action_executions", "requested_by_user_id")
    op.drop_column("action_executions", "workspace_id")
