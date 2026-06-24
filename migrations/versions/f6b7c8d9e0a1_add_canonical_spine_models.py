"""add canonical spine models (source_records, evidence_refs, repositories, pull_requests, tasks)

Revision ID: f6b7c8d9e0a1
Revises: f5a6b7c8d9e0
Create Date: 2026-06-24 00:00:00.000000

Adds the spine-critical subset of the master-playbook §6 canonical models to the
GitHub MVP lineage (DEC-028). NormalizedEntity and other §6 models are deferred.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "f6b7c8d9e0a1"
down_revision: Union[str, Sequence[str], None] = "f5a6b7c8d9e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.create_table(
        "source_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("connection_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("record_type", sa.String(length=120), nullable=False),
        sa.Column("source_url", sa.String(length=1000), nullable=True),
        sa.Column(
            "payload",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
        sa.Column("payload_hash", sa.String(length=128), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sync_job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "provider in ('github', 'jira', 'gmail', 'drive', 'internal')",
            name="ck_source_records_provider",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_source_records_workspace_id",
        ),
        sa.ForeignKeyConstraint(
            ["connection_id"],
            ["integration_connections.id"],
            name="fk_source_records_connection_id",
        ),
        sa.ForeignKeyConstraint(
            ["sync_job_id"],
            ["sync_jobs.id"],
            name="fk_source_records_sync_job_id",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "provider",
            "external_id",
            name="uq_source_records_workspace_provider_external_id",
        ),
    )
    op.create_index(
        op.f("ix_source_records_workspace_id"), "source_records", ["workspace_id"]
    )
    op.create_index(op.f("ix_source_records_provider"), "source_records", ["provider"])
    op.create_index(
        op.f("ix_source_records_connection_id"), "source_records", ["connection_id"]
    )
    op.create_index(
        op.f("ix_source_records_sync_job_id"), "source_records", ["sync_job_id"]
    )
    op.create_index(
        "ix_source_records_workspace_record_type",
        "source_records",
        ["workspace_id", "record_type"],
    )
    op.create_index(
        "ix_source_records_payload_hash", "source_records", ["payload_hash"]
    )
    op.create_index(
        "ix_source_records_source_updated_at", "source_records", ["source_updated_at"]
    )

    op.create_table(
        "repositories",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "provider",
            sa.String(length=40),
            nullable=False,
            server_default="github",
        ),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=500), nullable=False),
        sa.Column("default_branch", sa.String(length=255), nullable=True),
        sa.Column("visibility", sa.String(length=20), nullable=True),
        sa.Column(
            "archived",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("source_url", sa.String(length=1000), nullable=True),
        sa.Column(
            "metadata",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint("provider in ('github')", name="ck_repositories_provider"),
        sa.CheckConstraint(
            "visibility in ('public', 'private', 'internal')",
            name="ck_repositories_visibility",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_repositories_workspace_id",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "external_id",
            name="uq_repositories_workspace_external_id",
        ),
    )
    op.create_index(
        op.f("ix_repositories_workspace_id"), "repositories", ["workspace_id"]
    )

    op.create_table(
        "pull_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("repository_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("author_person_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_url", sa.String(length=1000), nullable=True),
        sa.Column("created_at_source", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at_source", sa.DateTime(timezone=True), nullable=True),
        sa.Column("merged_at_source", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "metadata",
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
        sa.CheckConstraint(
            "state in ('open', 'closed', 'merged')",
            name="ck_pull_requests_state",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_pull_requests_workspace_id",
        ),
        sa.ForeignKeyConstraint(
            ["repository_id"],
            ["repositories.id"],
            name="fk_pull_requests_repository_id",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "external_id",
            name="uq_pull_requests_workspace_external_id",
        ),
    )
    op.create_index(
        op.f("ix_pull_requests_workspace_id"), "pull_requests", ["workspace_id"]
    )
    op.create_index(op.f("ix_pull_requests_state"), "pull_requests", ["state"])
    op.create_index(
        "ix_pull_requests_repository_id", "pull_requests", ["repository_id"]
    )

    op.create_table(
        "tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_provider", sa.String(length=40), nullable=False),
        sa.Column("source_record_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("external_id", sa.String(length=255), nullable=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=120), nullable=True),
        sa.Column("priority", sa.String(length=40), nullable=True),
        sa.Column("assignee_person_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("source_url", sa.String(length=1000), nullable=True),
        sa.Column(
            "metadata",
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
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "source_provider in ('github', 'jira', 'internal')",
            name="ck_tasks_source_provider",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_tasks_workspace_id",
        ),
        sa.ForeignKeyConstraint(
            ["source_record_id"],
            ["source_records.id"],
            name="fk_tasks_source_record_id",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_tasks_workspace_id"), "tasks", ["workspace_id"])
    op.create_index(
        op.f("ix_tasks_source_record_id"), "tasks", ["source_record_id"]
    )
    op.create_index("ix_tasks_workspace_status", "tasks", ["workspace_id", "status"])
    op.create_index(
        "ix_tasks_workspace_assignee", "tasks", ["workspace_id", "assignee_person_id"]
    )
    op.create_index(
        "ix_tasks_provider_external_id", "tasks", ["source_provider", "external_id"]
    )

    op.create_table(
        "evidence_refs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_record_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("quote", sa.Text(), nullable=True),
        sa.Column("field_path", sa.String(length=500), nullable=True),
        sa.Column("source_url", sa.String(length=1000), nullable=True),
        sa.Column(
            "confidence",
            sa.Float(),
            nullable=False,
            server_default=sa.text("1.0"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_evidence_refs_workspace_id",
        ),
        sa.ForeignKeyConstraint(
            ["source_record_id"],
            ["source_records.id"],
            name="fk_evidence_refs_source_record_id",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_evidence_refs_workspace_id", "evidence_refs", ["workspace_id"]
    )
    op.create_index(
        "ix_evidence_refs_source_record_id", "evidence_refs", ["source_record_id"]
    )
    op.create_index("ix_evidence_refs_entity_id", "evidence_refs", ["entity_id"])


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_table("evidence_refs")
    op.drop_table("tasks")
    op.drop_table("pull_requests")
    op.drop_table("repositories")
    op.drop_table("source_records")
