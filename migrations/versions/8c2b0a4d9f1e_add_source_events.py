"""add source events

Revision ID: 8c2b0a4d9f1e
Revises: f33a4a9caaa5
Create Date: 2026-04-27 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "8c2b0a4d9f1e"
down_revision = "f33a4a9caaa5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "source_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_event_id", sa.String(length=255), nullable=False),
        sa.Column("source_event_key", sa.String(length=500), nullable=False),
        sa.Column("ingested_event_id", sa.String(length=120), nullable=False),
        sa.Column("event_type", sa.String(length=120), nullable=False),
        sa.Column("source_system", sa.String(length=50), nullable=False),
        sa.Column("source_object_type", sa.String(length=120), nullable=False),
        sa.Column("source_object_id", sa.String(length=255), nullable=False),
        sa.Column("source_event_ts", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actor_external_id", sa.String(length=255), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("source_url", sa.String(length=1000), nullable=True),
        sa.Column("raw_object_ref", sa.String(length=1000), nullable=False),
        sa.Column("evidence_refs", sa.JSON(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("schema_version", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["ingested_event_id"],
            ["ingested_events.event_id"],
            name="fk_source_events_ingested_event_id",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_system",
            "source_object_type",
            "source_object_id",
            "event_type",
            "source_event_key",
            name="uq_source_events_external_event",
        ),
    )

    op.create_index(op.f("ix_source_events_source_event_id"), "source_events", ["source_event_id"], unique=True)
    op.create_index(op.f("ix_source_events_source_event_key"), "source_events", ["source_event_key"], unique=True)
    op.create_index(op.f("ix_source_events_ingested_event_id"), "source_events", ["ingested_event_id"], unique=False)
    op.create_index(op.f("ix_source_events_event_type"), "source_events", ["event_type"], unique=False)
    op.create_index(op.f("ix_source_events_source_system"), "source_events", ["source_system"], unique=False)
    op.create_index(op.f("ix_source_events_source_object_type"), "source_events", ["source_object_type"], unique=False)
    op.create_index(op.f("ix_source_events_source_object_id"), "source_events", ["source_object_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_source_events_source_object_id"), table_name="source_events")
    op.drop_index(op.f("ix_source_events_source_object_type"), table_name="source_events")
    op.drop_index(op.f("ix_source_events_source_system"), table_name="source_events")
    op.drop_index(op.f("ix_source_events_event_type"), table_name="source_events")
    op.drop_index(op.f("ix_source_events_ingested_event_id"), table_name="source_events")
    op.drop_index(op.f("ix_source_events_source_event_key"), table_name="source_events")
    op.drop_index(op.f("ix_source_events_source_event_id"), table_name="source_events")
    op.drop_table("source_events")
