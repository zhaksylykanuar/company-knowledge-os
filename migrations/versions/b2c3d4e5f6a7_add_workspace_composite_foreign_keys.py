"""enforce workspace isolation with composite foreign keys

Revision ID: b2c3d4e5f6a7
Revises: a1c2d3e4f5b6
Create Date: 2026-07-29 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "a1c2d3e4f5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _assert_no_cross_workspace_references() -> None:
    violations = op.get_bind().execute(
        sa.text(
            """
            SELECT count(*)
            FROM (
                SELECT evidence.id
                FROM evidence_refs AS evidence
                JOIN source_records AS source
                  ON source.id = evidence.source_record_id
                WHERE source.workspace_id <> evidence.workspace_id

                UNION ALL

                SELECT pull_request.id
                FROM pull_requests AS pull_request
                JOIN repositories AS repository
                  ON repository.id = pull_request.repository_id
                WHERE repository.workspace_id <> pull_request.workspace_id

                UNION ALL

                SELECT pull_request.id
                FROM pull_requests AS pull_request
                JOIN source_records AS source
                  ON source.id = pull_request.source_record_id
                WHERE source.workspace_id <> pull_request.workspace_id

                UNION ALL

                SELECT task.id
                FROM tasks AS task
                JOIN source_records AS source
                  ON source.id = task.source_record_id
                WHERE source.workspace_id <> task.workspace_id

                UNION ALL

                SELECT version.id
                FROM document_versions AS version
                JOIN documents AS document
                  ON document.id = version.document_id
                WHERE document.workspace_id <> version.workspace_id
            ) AS cross_workspace_references
            """
        )
    ).scalar_one()
    if violations:
        raise RuntimeError(
            "workspace isolation migration blocked: "
            f"{violations} cross-workspace reference(s) require manual repair"
        )


def upgrade() -> None:
    _assert_no_cross_workspace_references()

    op.create_unique_constraint(
        "uq_repositories_workspace_id_id",
        "repositories",
        ["workspace_id", "id"],
    )
    op.create_unique_constraint(
        "uq_documents_workspace_id_id",
        "documents",
        ["workspace_id", "id"],
    )

    op.drop_constraint(
        "fk_evidence_refs_source_record_id",
        "evidence_refs",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_pull_requests_repository_id",
        "pull_requests",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_pull_requests_source_record_id",
        "pull_requests",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_tasks_source_record_id",
        "tasks",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_document_versions_document_id",
        "document_versions",
        type_="foreignkey",
    )

    op.create_foreign_key(
        "fk_evidence_refs_workspace_source_record",
        "evidence_refs",
        "source_records",
        ["workspace_id", "source_record_id"],
        ["workspace_id", "id"],
    )
    op.create_foreign_key(
        "fk_pull_requests_workspace_repository",
        "pull_requests",
        "repositories",
        ["workspace_id", "repository_id"],
        ["workspace_id", "id"],
    )
    op.create_foreign_key(
        "fk_pull_requests_workspace_source_record",
        "pull_requests",
        "source_records",
        ["workspace_id", "source_record_id"],
        ["workspace_id", "id"],
    )
    op.create_foreign_key(
        "fk_tasks_workspace_source_record",
        "tasks",
        "source_records",
        ["workspace_id", "source_record_id"],
        ["workspace_id", "id"],
    )
    op.create_foreign_key(
        "fk_document_versions_workspace_document",
        "document_versions",
        "documents",
        ["workspace_id", "document_id"],
        ["workspace_id", "id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_document_versions_workspace_document",
        "document_versions",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_tasks_workspace_source_record",
        "tasks",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_pull_requests_workspace_source_record",
        "pull_requests",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_pull_requests_workspace_repository",
        "pull_requests",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_evidence_refs_workspace_source_record",
        "evidence_refs",
        type_="foreignkey",
    )

    op.create_foreign_key(
        "fk_document_versions_document_id",
        "document_versions",
        "documents",
        ["document_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_tasks_source_record_id",
        "tasks",
        "source_records",
        ["source_record_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_pull_requests_source_record_id",
        "pull_requests",
        "source_records",
        ["source_record_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_pull_requests_repository_id",
        "pull_requests",
        "repositories",
        ["repository_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_evidence_refs_source_record_id",
        "evidence_refs",
        "source_records",
        ["source_record_id"],
        ["id"],
    )

    op.drop_constraint(
        "uq_documents_workspace_id_id",
        "documents",
        type_="unique",
    )
    op.drop_constraint(
        "uq_repositories_workspace_id_id",
        "repositories",
        type_="unique",
    )
