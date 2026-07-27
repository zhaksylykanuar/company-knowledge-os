"""add company memory event ledger

Revision ID: d7e8f9a0b1c2
Revises: d6e7f8a9b0c1
Create Date: 2026-07-27 00:00:00.000000

The ledger stores lifecycle metadata and canonical identifiers only. Raw source
bodies, provider payloads and rendered UI text remain in their source tables.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "d7e8f9a0b1c2"
down_revision: Union[str, Sequence[str], None] = "d6e7f8a9b0c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "company_memory_checkpoints",
        sa.Column(
            "last_event_sequence",
            sa.BigInteger(),
            server_default="0",
            nullable=False,
        ),
    )
    op.drop_constraint(
        "ck_company_memory_checkpoints_version",
        "company_memory_checkpoints",
        type_="check",
    )
    op.execute(
        "UPDATE company_memory_checkpoints "
        "SET checkpoint_version = 'temporal-checkpoint.v2'"
    )
    op.create_check_constraint(
        "ck_company_memory_checkpoints_version",
        "company_memory_checkpoints",
        "checkpoint_version = 'temporal-checkpoint.v2'",
    )
    op.create_check_constraint(
        "ck_company_memory_checkpoints_last_event_sequence",
        "company_memory_checkpoints",
        "last_event_sequence >= 0",
    )

    op.create_table(
        "company_memory_events",
        sa.Column(
            "sequence_id",
            sa.BigInteger(),
            sa.Identity(),
            nullable=False,
        ),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "event_version",
            sa.String(length=40),
            server_default="company-memory-event.v1",
            nullable=False,
        ),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("lifecycle_state", sa.String(length=20), nullable=False),
        sa.Column("subject_type", sa.String(length=40), nullable=False),
        sa.Column("subject_key", sa.String(length=120), nullable=False),
        sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_key", sa.String(length=40), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "primary_source_record_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "evidence_refs",
            sa.JSON(),
            server_default=sa.text("'[]'::json"),
            nullable=False,
        ),
        sa.Column("payload_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=120), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "observed_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "event_version = 'company-memory-event.v1'",
            name="ck_company_memory_events_version",
        ),
        sa.CheckConstraint(
            "event_type in ("
            "'action_proposal_created', "
            "'action_proposal_approved', "
            "'action_proposal_rejected', "
            "'company_world_confirmed', "
            "'company_world_dismissed'"
            ")",
            name="ck_company_memory_events_type",
        ),
        sa.CheckConstraint(
            "lifecycle_state in ('created', 'resolved')",
            name="ck_company_memory_events_lifecycle_state",
        ),
        sa.CheckConstraint(
            "subject_type in ("
            "'action_proposal', "
            "'external_person_candidate', "
            "'organization_candidate'"
            ")",
            name="ck_company_memory_events_subject_type",
        ),
        sa.CheckConstraint(
            "source_key in ('github', 'jira', 'gmail', 'drive', 'internal')",
            name="ck_company_memory_events_source_key",
        ),
        sa.CheckConstraint(
            "char_length(payload_fingerprint) = 64",
            name="ck_company_memory_events_payload_fingerprint",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_company_memory_events_workspace_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name="fk_company_memory_events_actor_user_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["primary_source_record_id"],
            ["source_records.id"],
            name="fk_company_memory_events_primary_source_record_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("sequence_id"),
        sa.UniqueConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "idempotency_key",
            name="uq_company_memory_events_workspace_idempotency_key",
        ),
    )
    op.create_index(
        "ix_company_memory_events_workspace_sequence",
        "company_memory_events",
        ["workspace_id", "sequence_id"],
        unique=False,
    )
    op.create_index(
        "ix_company_memory_events_workspace_subject",
        "company_memory_events",
        ["workspace_id", "subject_type", "subject_key"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_company_memory_events_workspace_subject",
        table_name="company_memory_events",
    )
    op.drop_index(
        "ix_company_memory_events_workspace_sequence",
        table_name="company_memory_events",
    )
    op.drop_table("company_memory_events")

    op.drop_constraint(
        "ck_company_memory_checkpoints_last_event_sequence",
        "company_memory_checkpoints",
        type_="check",
    )
    op.drop_constraint(
        "ck_company_memory_checkpoints_version",
        "company_memory_checkpoints",
        type_="check",
    )
    op.execute(
        "UPDATE company_memory_checkpoints "
        "SET checkpoint_version = 'temporal-checkpoint.v1'"
    )
    op.create_check_constraint(
        "ck_company_memory_checkpoints_version",
        "company_memory_checkpoints",
        "checkpoint_version = 'temporal-checkpoint.v1'",
    )
    op.drop_column("company_memory_checkpoints", "last_event_sequence")
