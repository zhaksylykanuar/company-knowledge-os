"""dedupe and enforce canonical task uniqueness

Revision ID: f7b8c9d0e1a2
Revises: a2b3c4d5e6f7
Create Date: 2026-06-28 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f7b8c9d0e1a2"
down_revision: Union[str, Sequence[str], None] = "a2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TASK_IDENTITY_INDEX = "uq_tasks_workspace_provider_external_id"


def upgrade() -> None:
    """Enforce canonical Task identity (workspace_id, source_provider, external_id).

    Step 1 deterministically de-duplicates any rows that share the identity,
    keeping the most-recently-updated row (then newest created_at, then highest
    id) and deleting the losers, so the unique index can be created even on data
    that already contains duplicates. Tasks with NULL external_id (manual /
    internal tasks) are never selected for de-dupe. Nothing FK-references
    tasks.id (evidence_refs link to source_records), so deleting losers needs no
    row re-pointing.

    Step 2 creates a PARTIAL unique index scoped to ``external_id IS NOT NULL``
    so manual/internal tasks are never blocked.

    IRREVERSIBLE: the Step 1 DELETE permanently removes duplicate rows;
    downgrade() only drops the index and cannot restore deleted rows.
    """

    # Step 1 — deterministic de-dupe (provider-keyed rows only; NULLs untouched).
    op.execute(
        sa.text(
            """
            DELETE FROM tasks t
            USING (
                SELECT id,
                       row_number() OVER (
                           PARTITION BY workspace_id, source_provider, external_id
                           ORDER BY updated_at DESC NULLS LAST,
                                    created_at DESC NULLS LAST,
                                    id DESC
                       ) AS rn
                FROM tasks
                WHERE external_id IS NOT NULL
            ) ranked
            WHERE t.id = ranked.id
              AND ranked.rn > 1
            """
        )
    )

    # Step 2 — partial unique index backing the canonical identity.
    op.create_index(
        TASK_IDENTITY_INDEX,
        "tasks",
        ["workspace_id", "source_provider", "external_id"],
        unique=True,
        postgresql_where=sa.text("external_id IS NOT NULL"),
    )


def downgrade() -> None:
    """Drop the canonical-identity unique index.

    NOTE: the de-dupe performed in upgrade() deleted duplicate task rows and is
    NOT reversible. This downgrade only removes the unique index; it cannot
    restore previously-deleted duplicates.
    """

    op.drop_index(TASK_IDENTITY_INDEX, table_name="tasks")
