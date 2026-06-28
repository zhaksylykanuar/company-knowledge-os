"""reconcile ingested_events index/constraint drift

Revision ID: a8c9d0e1f2b3
Revises: f7b8c9d0e1a2
Create Date: 2026-06-28 00:00:01.000000

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "a8c9d0e1f2b3"
down_revision: Union[str, Sequence[str], None] = "f7b8c9d0e1a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Reconcile retained ingested_events drift with the ORM model.

    NO DATA IS CHANGED — this only reshapes indexes/constraints to match
    app/db/models.py ``IngestedEvent``, which already expresses
    ``idempotency_key`` uniqueness as a UNIQUE INDEX and indexes
    ``event_type`` / ``source_object_id`` / ``source_system`` individually. The
    live schema still carried the original unique CONSTRAINT plus a composite
    ``(source_system, source_object_id)`` index, leaving ``alembic check``
    perpetually red. ``idempotency_key`` is already unique in the data (via the
    constraint being dropped), so converting it to a unique index is safe.
    """

    # idempotency_key: replace UNIQUE CONSTRAINT + non-unique index with a
    # single UNIQUE INDEX (the model's shape).
    op.drop_constraint(
        "ingested_events_idempotency_key_key", "ingested_events", type_="unique"
    )
    op.drop_index("ix_ingested_events_idempotency_key", table_name="ingested_events")
    op.create_index(
        "ix_ingested_events_idempotency_key",
        "ingested_events",
        ["idempotency_key"],
        unique=True,
    )

    # Replace the composite source index with the model's single-column indexes.
    op.drop_index("ix_ingested_events_source", table_name="ingested_events")
    op.create_index(
        "ix_ingested_events_event_type",
        "ingested_events",
        ["event_type"],
        unique=False,
    )
    op.create_index(
        "ix_ingested_events_source_object_id",
        "ingested_events",
        ["source_object_id"],
        unique=False,
    )
    op.create_index(
        "ix_ingested_events_source_system",
        "ingested_events",
        ["source_system"],
        unique=False,
    )


def downgrade() -> None:
    """Restore the pre-reconciliation index/constraint shape."""

    op.drop_index("ix_ingested_events_source_system", table_name="ingested_events")
    op.drop_index("ix_ingested_events_source_object_id", table_name="ingested_events")
    op.drop_index("ix_ingested_events_event_type", table_name="ingested_events")
    op.create_index(
        "ix_ingested_events_source",
        "ingested_events",
        ["source_system", "source_object_id"],
        unique=False,
    )

    op.drop_index("ix_ingested_events_idempotency_key", table_name="ingested_events")
    op.create_index(
        "ix_ingested_events_idempotency_key",
        "ingested_events",
        ["idempotency_key"],
        unique=False,
    )
    op.create_unique_constraint(
        "ingested_events_idempotency_key_key",
        "ingested_events",
        ["idempotency_key"],
    )
