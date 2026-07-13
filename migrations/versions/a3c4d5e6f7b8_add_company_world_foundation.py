"""add durable Company World profile foundation

Revision ID: a3c4d5e6f7b8
Revises: f2b3c4d5e6f7
Create Date: 2026-07-13 00:00:00.000000

Schema-only foundation for founder-confirmed people, organizations,
affiliations, sanitized interactions, and idempotent candidate resolutions.
This migration performs no backfill and never rewrites source records.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "a3c4d5e6f7b8"
down_revision: Union[str, Sequence[str], None] = "f2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COMPANY_WORLD_TABLES = (
    "company_world_resolutions",
    "interactions",
    "affiliations",
    "organizations",
    "people",
)
COMPANY_WORLD_LOCK_ORDER = (
    "affiliations",
    "company_world_resolutions",
    "interactions",
    "organizations",
    "people",
)


def upgrade() -> None:
    """Create the empty, workspace-isolated Company World tables."""

    # Composite FKs below include workspace_id so a row can never reference a
    # source record owned by another tenant.
    op.create_unique_constraint(
        "uq_source_records_workspace_id_id",
        "source_records",
        ["workspace_id", "id"],
    )

    op.create_table(
        "people",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("normalized_email", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("origin", sa.String(length=40), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="active",
            nullable=False,
        ),
        sa.Column("confirmed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "origin in ('membership', 'founder_confirmation')",
            name="ck_people_origin",
        ),
        sa.CheckConstraint(
            "status in ('active', 'archived')",
            name="ck_people_status",
        ),
        sa.CheckConstraint(
            "origin != 'membership' or user_id is not null",
            name="ck_people_membership_user",
        ),
        sa.CheckConstraint(
            "origin = 'membership' or "
            "(confirmed_by_user_id is not null and confirmed_at is not null)",
            name="ck_people_confirmation_provenance",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_people_workspace_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "user_id"],
            ["memberships.workspace_id", "memberships.user_id"],
            name="fk_people_workspace_user",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "confirmed_by_user_id"],
            ["memberships.workspace_id", "memberships.user_id"],
            name="fk_people_workspace_confirmed_by",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "id",
            name="uq_people_workspace_id_id",
        ),
    )
    op.create_index(
        "ix_people_workspace_status",
        "people",
        ["workspace_id", "status"],
    )
    op.create_index(
        "uq_people_workspace_user_id",
        "people",
        ["workspace_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("user_id IS NOT NULL"),
    )
    op.create_index(
        "uq_people_workspace_normalized_email",
        "people",
        ["workspace_id", "normalized_email"],
        unique=True,
    )

    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("canonical_key", sa.String(length=500), nullable=False),
        sa.Column("normalized_domain", sa.String(length=253), nullable=True),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column(
            "relationship_kind",
            sa.String(length=20),
            server_default="unknown",
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="active",
            nullable=False,
        ),
        sa.Column("confirmed_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
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
        sa.CheckConstraint(
            "relationship_kind in "
            "('unknown', 'prospect', 'customer', 'partner', 'vendor', 'other')",
            name="ck_organizations_relationship_kind",
        ),
        sa.CheckConstraint(
            "status in ('active', 'archived')",
            name="ck_organizations_status",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_organizations_workspace_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "confirmed_by_user_id"],
            ["memberships.workspace_id", "memberships.user_id"],
            name="fk_organizations_workspace_confirmed_by",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "id",
            name="uq_organizations_workspace_id_id",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "canonical_key",
            name="uq_organizations_workspace_canonical_key",
        ),
    )
    op.create_index(
        "ix_organizations_workspace_relationship_kind",
        "organizations",
        ["workspace_id", "relationship_kind"],
    )
    op.create_index(
        "ix_organizations_workspace_status",
        "organizations",
        ["workspace_id", "status"],
    )
    op.create_index(
        "uq_organizations_workspace_normalized_domain",
        "organizations",
        ["workspace_id", "normalized_domain"],
        unique=True,
        postgresql_where=sa.text("normalized_domain IS NOT NULL"),
    )

    op.create_table(
        "affiliations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("person_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("relationship_type", sa.String(length=30), nullable=False),
        sa.Column("role_title", sa.String(length=255), nullable=True),
        sa.Column("source_record_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("confirmed_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="active",
            nullable=False,
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
        sa.CheckConstraint(
            "relationship_type in "
            "('contact', 'employee', 'decision_maker', 'account_owner', "
            "'advisor', 'other')",
            name="ck_affiliations_relationship_type",
        ),
        sa.CheckConstraint(
            "status in ('active', 'archived')",
            name="ck_affiliations_status",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_affiliations_workspace_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "person_id"],
            ["people.workspace_id", "people.id"],
            name="fk_affiliations_workspace_person",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "organization_id"],
            ["organizations.workspace_id", "organizations.id"],
            name="fk_affiliations_workspace_organization",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "source_record_id"],
            ["source_records.workspace_id", "source_records.id"],
            name="fk_affiliations_workspace_source_record",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "confirmed_by_user_id"],
            ["memberships.workspace_id", "memberships.user_id"],
            name="fk_affiliations_workspace_confirmed_by",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "id",
            name="uq_affiliations_workspace_id_id",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "person_id",
            "organization_id",
            name="uq_affiliations_workspace_person_organization",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "id",
            "person_id",
            "organization_id",
            name="uq_affiliations_workspace_identity",
        ),
    )
    op.create_index(
        "ix_affiliations_workspace_status",
        "affiliations",
        ["workspace_id", "status"],
    )
    op.create_index("ix_affiliations_person_id", "affiliations", ["person_id"])
    op.create_index(
        "ix_affiliations_organization_id",
        "affiliations",
        ["organization_id"],
    )

    op.create_table(
        "interactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("person_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_record_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "channel",
            sa.String(length=20),
            server_default="email",
            nullable=False,
        ),
        sa.Column("direction", sa.String(length=20), nullable=False),
        sa.Column("subject", sa.String(length=500), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_url", sa.String(length=1000), nullable=True),
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
        sa.CheckConstraint(
            "channel in ('email')",
            name="ck_interactions_channel",
        ),
        sa.CheckConstraint(
            "direction in ('inbound', 'outbound', 'mixed', 'unknown')",
            name="ck_interactions_direction",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_interactions_workspace_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "person_id"],
            ["people.workspace_id", "people.id"],
            name="fk_interactions_workspace_person",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "organization_id"],
            ["organizations.workspace_id", "organizations.id"],
            name="fk_interactions_workspace_organization",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "source_record_id"],
            ["source_records.workspace_id", "source_records.id"],
            name="fk_interactions_workspace_source_record",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "id",
            name="uq_interactions_workspace_id_id",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "source_record_id",
            "person_id",
            name="uq_interactions_workspace_source_person",
        ),
    )
    op.create_index(
        "ix_interactions_workspace_occurred_at",
        "interactions",
        ["workspace_id", "occurred_at"],
    )
    op.create_index(
        "ix_interactions_person_occurred_at",
        "interactions",
        ["person_id", "occurred_at"],
    )
    op.create_index(
        "ix_interactions_organization_occurred_at",
        "interactions",
        ["organization_id", "occurred_at"],
    )

    op.create_table(
        "company_world_resolutions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_type", sa.String(length=30), nullable=False),
        sa.Column("candidate_key", sa.String(length=500), nullable=False),
        sa.Column("candidate_version", sa.String(length=64), nullable=False),
        sa.Column("decision", sa.String(length=20), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_record_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("result_person_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("result_organization_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("result_affiliation_id", postgresql.UUID(as_uuid=True), nullable=True),
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
        sa.CheckConstraint(
            "candidate_type in ('external_person', 'organization')",
            name="ck_company_world_resolutions_candidate_type",
        ),
        sa.CheckConstraint(
            "char_length(candidate_version) = 64",
            name="ck_company_world_resolutions_candidate_version",
        ),
        sa.CheckConstraint(
            "decision in ('confirmed', 'dismissed')",
            name="ck_company_world_resolutions_decision",
        ),
        sa.CheckConstraint(
            "(decision = 'dismissed' and result_person_id is null "
            "and result_organization_id is null and result_affiliation_id is null) "
            "or (decision = 'confirmed' and candidate_type = 'external_person' "
            "and result_person_id is not null "
            "and (result_affiliation_id is null or result_organization_id is not null)) "
            "or (decision = 'confirmed' and candidate_type = 'organization' "
            "and result_organization_id is not null and result_person_id is null "
            "and result_affiliation_id is null)",
            name="ck_company_world_resolutions_result_shape",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_company_world_resolutions_workspace_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "actor_user_id"],
            ["memberships.workspace_id", "memberships.user_id"],
            name="fk_company_world_resolutions_workspace_actor",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "source_record_id"],
            ["source_records.workspace_id", "source_records.id"],
            name="fk_company_world_resolutions_workspace_source_record",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "result_person_id"],
            ["people.workspace_id", "people.id"],
            name="fk_company_world_resolutions_workspace_result_person",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "result_organization_id"],
            ["organizations.workspace_id", "organizations.id"],
            name="fk_company_world_resolutions_workspace_result_organization",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            [
                "workspace_id",
                "result_affiliation_id",
                "result_person_id",
                "result_organization_id",
            ],
            [
                "affiliations.workspace_id",
                "affiliations.id",
                "affiliations.person_id",
                "affiliations.organization_id",
            ],
            name="fk_company_world_resolutions_result_affiliation_identity",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "id",
            name="uq_company_world_resolutions_workspace_id_id",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "idempotency_key",
            name="uq_company_world_resolutions_workspace_idempotency_key",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "candidate_type",
            "candidate_key",
            name="uq_company_world_resolutions_workspace_candidate",
        ),
    )
    op.create_index(
        "ix_company_world_resolutions_workspace_created_at",
        "company_world_resolutions",
        ["workspace_id", "created_at"],
    )


def downgrade() -> None:
    """Remove only an empty profile foundation; refuse destructive rollback."""

    bind = op.get_bind()
    for table_name in COMPANY_WORLD_LOCK_ORDER:
        bind.execute(sa.text(f'LOCK TABLE "{table_name}" IN ACCESS EXCLUSIVE MODE'))

    for table_name in COMPANY_WORLD_TABLES:
        has_rows = bind.execute(
            sa.text(f'SELECT EXISTS (SELECT 1 FROM "{table_name}" LIMIT 1)')
        ).scalar_one()
        if has_rows:
            raise RuntimeError(
                "refusing to downgrade non-empty Company World tables; "
                "export or explicitly clear durable profile data first"
            )

    for table_name in COMPANY_WORLD_TABLES:
        op.drop_table(table_name)
    op.drop_constraint(
        "uq_source_records_workspace_id_id",
        "source_records",
        type_="unique",
    )
