"""enforce repository full-name identity

Adds a DB-level guard for GitHub repository cross-path identity. Some sync paths
first see a repository by full_name (owner/repo), while full repository sync can
later see the same repository by GitHub numeric id. The existing
(workspace_id, external_id) uniqueness is not enough to protect concurrent live
sync paths from inserting two rows for the same workspace/provider/full_name.

Revision ID: e8f9a0b1c2d3
Revises: e7f8a9b0c1d2
Create Date: 2026-06-30 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e8f9a0b1c2d3"
down_revision: Union[str, Sequence[str], None] = "e7f8a9b0c1d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


REPOSITORY_FULL_NAME_IDENTITY = "uq_repositories_workspace_provider_full_name"


def upgrade() -> None:
    """Enforce workspace/provider/full_name identity for repositories.

    Step 1 deterministically de-duplicates any existing rows sharing
    (workspace_id, provider, full_name). The keeper prefers a stable provider id
    over a temporary full_name external_id, then the most recently updated row,
    then newest created_at/id. Pull requests are re-pointed to the keeper before
    loser rows are deleted.

    Step 2 adds the unique constraint used by the race-safe repository upsert.

    IRREVERSIBLE: the duplicate-row delete cannot be reversed by downgrade().
    """

    op.execute(
        sa.text(
            """
            WITH ranked AS (
                SELECT id,
                       first_value(id) OVER (
                           PARTITION BY workspace_id, provider, full_name
                           ORDER BY CASE WHEN external_id <> full_name THEN 0 ELSE 1 END,
                                    updated_at DESC NULLS LAST,
                                    created_at DESC NULLS LAST,
                                    id DESC
                       ) AS keeper_id,
                       row_number() OVER (
                           PARTITION BY workspace_id, provider, full_name
                           ORDER BY CASE WHEN external_id <> full_name THEN 0 ELSE 1 END,
                                    updated_at DESC NULLS LAST,
                                    created_at DESC NULLS LAST,
                                    id DESC
                       ) AS rn
                FROM repositories
            )
            UPDATE pull_requests pr
            SET repository_id = ranked.keeper_id
            FROM ranked
            WHERE pr.repository_id = ranked.id
              AND ranked.rn > 1
            """
        )
    )
    op.execute(
        sa.text(
            """
            WITH ranked AS (
                SELECT id,
                       row_number() OVER (
                           PARTITION BY workspace_id, provider, full_name
                           ORDER BY CASE WHEN external_id <> full_name THEN 0 ELSE 1 END,
                                    updated_at DESC NULLS LAST,
                                    created_at DESC NULLS LAST,
                                    id DESC
                       ) AS rn
                FROM repositories
            )
            DELETE FROM repositories r
            USING ranked
            WHERE r.id = ranked.id
              AND ranked.rn > 1
            """
        )
    )

    op.create_unique_constraint(
        REPOSITORY_FULL_NAME_IDENTITY,
        "repositories",
        ["workspace_id", "provider", "full_name"],
    )


def downgrade() -> None:
    """Drop the repository full-name identity constraint.

    NOTE: the de-dupe performed in upgrade() deleted duplicate repository rows
    and is NOT reversible. This downgrade only removes the unique constraint.
    """

    op.drop_constraint(
        REPOSITORY_FULL_NAME_IDENTITY,
        "repositories",
        type_="unique",
    )
