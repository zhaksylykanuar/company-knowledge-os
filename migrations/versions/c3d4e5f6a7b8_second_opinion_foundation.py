"""second opinion foundation: identity layer, findings, availability

Revision ID: c3d4e5f6a7b8
Revises: b7c8d9e0f1a2
Create Date: 2026-06-12 14:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "b7c8d9e0f1a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "entities",
        sa.Column("canonical_entity_id", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "entities",
        sa.Column(
            "merge_status",
            sa.String(length=20),
            nullable=False,
            server_default="none",
        ),
    )
    op.add_column(
        "entities", sa.Column("merge_confidence", sa.Float(), nullable=True)
    )
    op.create_index(
        op.f("ix_entities_canonical_entity_id"),
        "entities",
        ["canonical_entity_id"],
    )

    op.add_column(
        "entity_links", sa.Column("confidence_factors", sa.JSON(), nullable=True)
    )

    op.create_table(
        "entity_source_accounts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("entity_id", sa.String(length=120), nullable=False),
        sa.Column("source_system", sa.String(length=50), nullable=False),
        sa.Column("account_id", sa.String(length=255), nullable=False),
        sa.Column("account_url", sa.String(length=500), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_system", "account_id"),
    )
    op.create_index(
        op.f("ix_entity_source_accounts_entity_id"),
        "entity_source_accounts",
        ["entity_id"],
    )
    op.create_index(
        op.f("ix_entity_source_accounts_source_system"),
        "entity_source_accounts",
        ["source_system"],
    )

    op.add_column(
        "agent_proposals",
        sa.Column("dedupe_key", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "agent_proposals", sa.Column("source_snapshot", sa.JSON(), nullable=True)
    )
    op.add_column(
        "agent_proposals",
        sa.Column("confidence_factors", sa.JSON(), nullable=True),
    )
    op.add_column(
        "agent_proposals",
        sa.Column("decision_reason", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "agent_proposals",
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "agent_proposals",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "agent_proposals",
        sa.Column(
            "reversible",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.create_index(
        op.f("ix_agent_proposals_dedupe_key"), "agent_proposals", ["dedupe_key"]
    )

    op.create_table(
        "second_opinion_findings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("finding_key", sa.String(length=255), nullable=False),
        sa.Column("company_id", sa.String(length=120), nullable=False),
        sa.Column("entity_id", sa.String(length=120), nullable=True),
        sa.Column("finding_type", sa.String(length=60), nullable=False),
        sa.Column("declared_state", sa.Text(), nullable=False),
        sa.Column("observed_state", sa.Text(), nullable=False),
        sa.Column("summary", sa.String(length=500), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("confidence_factors", sa.JSON(), nullable=True),
        sa.Column("evidence_refs", sa.JSON(), nullable=False),
        sa.Column("source_refs", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("visibility_scope", sa.String(length=20), nullable=False),
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
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_second_opinion_findings_finding_key"),
        "second_opinion_findings",
        ["finding_key"],
        unique=True,
    )
    for column in ("company_id", "entity_id", "finding_type", "severity", "status",
                   "created_at"):
        op.create_index(
            op.f(f"ix_second_opinion_findings_{column}"),
            "second_opinion_findings",
            [column],
        )

    op.create_table(
        "data_availability",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("metric_key", sa.String(length=120), nullable=False),
        sa.Column("scope", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("points_count", sa.Integer(), nullable=False),
        sa.Column("required_points", sa.Integer(), nullable=False),
        sa.Column("last_point_at", sa.String(length=10), nullable=True),
        sa.Column("message", sa.String(length=300), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("metric_key", "scope", name="uq_data_availability_key_scope"),
    )
    op.create_index(
        op.f("ix_data_availability_metric_key"), "data_availability", ["metric_key"]
    )
    op.create_index(
        op.f("ix_data_availability_scope"), "data_availability", ["scope"]
    )
    op.create_index(
        op.f("ix_data_availability_status"), "data_availability", ["status"]
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("data_availability")
    op.drop_table("second_opinion_findings")
    op.drop_index(op.f("ix_agent_proposals_dedupe_key"), table_name="agent_proposals")
    for column in (
        "reversible",
        "expires_at",
        "applied_at",
        "decision_reason",
        "confidence_factors",
        "source_snapshot",
        "dedupe_key",
    ):
        op.drop_column("agent_proposals", column)
    op.drop_table("entity_source_accounts")
    op.drop_column("entity_links", "confidence_factors")
    op.drop_index(op.f("ix_entities_canonical_entity_id"), table_name="entities")
    op.drop_column("entities", "merge_confidence")
    op.drop_column("entities", "merge_status")
    op.drop_column("entities", "canonical_entity_id")
