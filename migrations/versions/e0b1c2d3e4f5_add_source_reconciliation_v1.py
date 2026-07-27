"""add authoritative source reconciliation v1

Revision ID: e0b1c2d3e4f5
Revises: d9a0b1c2d3e4
Create Date: 2026-07-27 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "e0b1c2d3e4f5"
down_revision: Union[str, Sequence[str], None] = "d9a0b1c2d3e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "source_records",
        sa.Column("tombstoned_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "source_records",
        sa.Column(
            "tombstone_sync_job_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.add_column(
        "source_records",
        sa.Column("tombstone_reason", sa.String(length=120), nullable=True),
    )
    op.create_foreign_key(
        "fk_source_records_tombstone_sync_job_id",
        "source_records",
        "sync_jobs",
        ["tombstone_sync_job_id"],
        ["id"],
    )
    op.create_index(
        "ix_source_records_tombstone_sync_job_id",
        "source_records",
        ["tombstone_sync_job_id"],
        unique=False,
    )
    op.create_index(
        "ix_source_records_workspace_provider_deleted",
        "source_records",
        ["workspace_id", "provider", "is_deleted"],
        unique=False,
    )
    op.execute(
        """
        UPDATE source_records
        SET
            tombstoned_at = COALESCE(observed_at, created_at),
            tombstone_sync_job_id = sync_job_id,
            tombstone_reason = 'legacy_without_provenance'
        WHERE is_deleted = true
        """
    )
    op.create_check_constraint(
        "ck_source_records_tombstone_provenance",
        "source_records",
        "("
        "is_deleted = false "
        "and tombstoned_at is null "
        "and tombstone_sync_job_id is null "
        "and tombstone_reason is null"
        ") or ("
        "is_deleted = true "
        "and tombstoned_at is not null "
        "and tombstone_reason is not null"
        ")",
    )

    op.add_column(
        "pull_requests",
        sa.Column(
            "source_record_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_pull_requests_source_record_id",
        "pull_requests",
        "source_records",
        ["source_record_id"],
        ["id"],
    )
    op.create_index(
        "ix_pull_requests_source_record_id",
        "pull_requests",
        ["source_record_id"],
        unique=False,
    )
    op.execute(
        """
        UPDATE pull_requests AS pull_request
        SET source_record_id = source_record.id
        FROM source_records AS source_record
        WHERE
            source_record.workspace_id = pull_request.workspace_id
            AND source_record.provider = 'github'
            AND source_record.record_type = 'pull_request'
            AND source_record.external_id = pull_request.external_id
        """
    )

    op.drop_constraint(
        "ck_company_memory_events_type",
        "company_memory_events",
        type_="check",
    )
    op.create_check_constraint(
        "ck_company_memory_events_type",
        "company_memory_events",
        "event_type in ("
        "'action_proposal_created', "
        "'action_proposal_approved', "
        "'action_proposal_rejected', "
        "'company_world_confirmed', "
        "'company_world_dismissed', "
        "'source_record_disappeared', "
        "'source_record_restored'"
        ")",
    )
    op.drop_constraint(
        "ck_company_memory_events_subject_type",
        "company_memory_events",
        type_="check",
    )
    op.create_check_constraint(
        "ck_company_memory_events_subject_type",
        "company_memory_events",
        "subject_type in ("
        "'action_proposal', "
        "'external_person_candidate', "
        "'organization_candidate', "
        "'source_record'"
        ")",
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM company_memory_events
        WHERE event_type IN (
            'source_record_disappeared',
            'source_record_restored'
        )
        """
    )
    op.drop_constraint(
        "ck_company_memory_events_subject_type",
        "company_memory_events",
        type_="check",
    )
    op.create_check_constraint(
        "ck_company_memory_events_subject_type",
        "company_memory_events",
        "subject_type in ("
        "'action_proposal', "
        "'external_person_candidate', "
        "'organization_candidate'"
        ")",
    )
    op.drop_constraint(
        "ck_company_memory_events_type",
        "company_memory_events",
        type_="check",
    )
    op.create_check_constraint(
        "ck_company_memory_events_type",
        "company_memory_events",
        "event_type in ("
        "'action_proposal_created', "
        "'action_proposal_approved', "
        "'action_proposal_rejected', "
        "'company_world_confirmed', "
        "'company_world_dismissed'"
        ")",
    )

    op.drop_index(
        "ix_pull_requests_source_record_id",
        table_name="pull_requests",
    )
    op.drop_constraint(
        "fk_pull_requests_source_record_id",
        "pull_requests",
        type_="foreignkey",
    )
    op.drop_column("pull_requests", "source_record_id")

    op.drop_constraint(
        "ck_source_records_tombstone_provenance",
        "source_records",
        type_="check",
    )
    op.drop_index(
        "ix_source_records_workspace_provider_deleted",
        table_name="source_records",
    )
    op.drop_index(
        "ix_source_records_tombstone_sync_job_id",
        table_name="source_records",
    )
    op.drop_constraint(
        "fk_source_records_tombstone_sync_job_id",
        "source_records",
        type_="foreignkey",
    )
    op.drop_column("source_records", "tombstone_reason")
    op.drop_column("source_records", "tombstone_sync_job_id")
    op.drop_column("source_records", "tombstoned_at")
