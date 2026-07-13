"""Durable, workspace-owned Company World profile foundation.

The tables in this module persist only founder-confirmed company profiles,
their source-backed interactions, and terminal human resolution receipts.
Candidate discovery remains a read-only Company World projection until a
member explicitly resolves a server-revalidated candidate.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base

# Register all string-FK targets even when this module is imported directly by
# a model or migration metadata test.
import app.db.canonical_models  # noqa: E402,F401
import app.db.identity_models  # noqa: E402,F401


PERSON_ORIGIN_MEMBERSHIP = "membership"
PERSON_ORIGIN_FOUNDER_CONFIRMATION = "founder_confirmation"
PROFILE_STATUS_ACTIVE = "active"
PROFILE_STATUS_ARCHIVED = "archived"

ORGANIZATION_RELATIONSHIP_UNKNOWN = "unknown"
ORGANIZATION_RELATIONSHIP_PROSPECT = "prospect"
ORGANIZATION_RELATIONSHIP_CUSTOMER = "customer"
ORGANIZATION_RELATIONSHIP_PARTNER = "partner"
ORGANIZATION_RELATIONSHIP_VENDOR = "vendor"
ORGANIZATION_RELATIONSHIP_OTHER = "other"

AFFILIATION_RELATIONSHIP_CONTACT = "contact"
AFFILIATION_RELATIONSHIP_EMPLOYEE = "employee"
AFFILIATION_RELATIONSHIP_DECISION_MAKER = "decision_maker"
AFFILIATION_RELATIONSHIP_ACCOUNT_OWNER = "account_owner"
AFFILIATION_RELATIONSHIP_ADVISOR = "advisor"
AFFILIATION_RELATIONSHIP_OTHER = "other"

INTERACTION_CHANNEL_EMAIL = "email"
INTERACTION_DIRECTION_INBOUND = "inbound"
INTERACTION_DIRECTION_OUTBOUND = "outbound"
INTERACTION_DIRECTION_MIXED = "mixed"
INTERACTION_DIRECTION_UNKNOWN = "unknown"

RESOLUTION_CANDIDATE_EXTERNAL_PERSON = "external_person"
RESOLUTION_CANDIDATE_ORGANIZATION = "organization"
RESOLUTION_DECISION_CONFIRMED = "confirmed"
RESOLUTION_DECISION_DISMISSED = "dismissed"


class Person(Base):
    """One durable internal or founder-confirmed external person profile."""

    __tablename__ = "people"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "id",
            name="uq_people_workspace_id_id",
        ),
        CheckConstraint(
            "origin in ('membership', 'founder_confirmation')",
            name="ck_people_origin",
        ),
        CheckConstraint(
            "status in ('active', 'archived')",
            name="ck_people_status",
        ),
        CheckConstraint(
            "origin != 'membership' or user_id is not null",
            name="ck_people_membership_user",
        ),
        CheckConstraint(
            "origin = 'membership' or "
            "(confirmed_by_user_id is not null and confirmed_at is not null)",
            name="ck_people_confirmation_provenance",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "user_id"],
            ["memberships.workspace_id", "memberships.user_id"],
            name="fk_people_workspace_user",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "confirmed_by_user_id"],
            ["memberships.workspace_id", "memberships.user_id"],
            name="fk_people_workspace_confirmed_by",
            ondelete="RESTRICT",
        ),
        Index("ix_people_workspace_status", "workspace_id", "status"),
        Index(
            "uq_people_workspace_user_id",
            "workspace_id",
            "user_id",
            unique=True,
            postgresql_where=text("user_id IS NOT NULL"),
        ),
        Index(
            "uq_people_workspace_normalized_email",
            "workspace_id",
            "normalized_email",
            unique=True,
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "workspaces.id",
            name="fk_people_workspace_id",
            ondelete="CASCADE",
        ),
    )
    user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    normalized_email: Mapped[str] = mapped_column(String(320))
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    origin: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(
        String(20), default=PROFILE_STATUS_ACTIVE, server_default=PROFILE_STATUS_ACTIVE
    )
    confirmed_by_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Organization(Base):
    """One durable company or other organization inside a workspace."""

    __tablename__ = "organizations"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "id",
            name="uq_organizations_workspace_id_id",
        ),
        UniqueConstraint(
            "workspace_id",
            "canonical_key",
            name="uq_organizations_workspace_canonical_key",
        ),
        CheckConstraint(
            "relationship_kind in "
            "('unknown', 'prospect', 'customer', 'partner', 'vendor', 'other')",
            name="ck_organizations_relationship_kind",
        ),
        CheckConstraint(
            "status in ('active', 'archived')",
            name="ck_organizations_status",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "confirmed_by_user_id"],
            ["memberships.workspace_id", "memberships.user_id"],
            name="fk_organizations_workspace_confirmed_by",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_organizations_workspace_relationship_kind",
            "workspace_id",
            "relationship_kind",
        ),
        Index("ix_organizations_workspace_status", "workspace_id", "status"),
        Index(
            "uq_organizations_workspace_normalized_domain",
            "workspace_id",
            "normalized_domain",
            unique=True,
            postgresql_where=text("normalized_domain IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "workspaces.id",
            name="fk_organizations_workspace_id",
            ondelete="CASCADE",
        ),
    )
    canonical_key: Mapped[str] = mapped_column(String(500))
    normalized_domain: Mapped[str | None] = mapped_column(String(253), nullable=True)
    display_name: Mapped[str] = mapped_column(String(255))
    relationship_kind: Mapped[str] = mapped_column(
        String(20),
        default=ORGANIZATION_RELATIONSHIP_UNKNOWN,
        server_default=ORGANIZATION_RELATIONSHIP_UNKNOWN,
    )
    status: Mapped[str] = mapped_column(
        String(20), default=PROFILE_STATUS_ACTIVE, server_default=PROFILE_STATUS_ACTIVE
    )
    confirmed_by_user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Affiliation(Base):
    """A confirmed person-to-organization relationship."""

    __tablename__ = "affiliations"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "id",
            name="uq_affiliations_workspace_id_id",
        ),
        UniqueConstraint(
            "workspace_id",
            "person_id",
            "organization_id",
            name="uq_affiliations_workspace_person_organization",
        ),
        UniqueConstraint(
            "workspace_id",
            "id",
            "person_id",
            "organization_id",
            name="uq_affiliations_workspace_identity",
        ),
        CheckConstraint(
            "relationship_type in "
            "('contact', 'employee', 'decision_maker', 'account_owner', "
            "'advisor', 'other')",
            name="ck_affiliations_relationship_type",
        ),
        CheckConstraint(
            "status in ('active', 'archived')",
            name="ck_affiliations_status",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "person_id"],
            ["people.workspace_id", "people.id"],
            name="fk_affiliations_workspace_person",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "organization_id"],
            ["organizations.workspace_id", "organizations.id"],
            name="fk_affiliations_workspace_organization",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "source_record_id"],
            ["source_records.workspace_id", "source_records.id"],
            name="fk_affiliations_workspace_source_record",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "confirmed_by_user_id"],
            ["memberships.workspace_id", "memberships.user_id"],
            name="fk_affiliations_workspace_confirmed_by",
            ondelete="RESTRICT",
        ),
        Index("ix_affiliations_workspace_status", "workspace_id", "status"),
        Index("ix_affiliations_person_id", "person_id"),
        Index("ix_affiliations_organization_id", "organization_id"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "workspaces.id",
            name="fk_affiliations_workspace_id",
            ondelete="CASCADE",
        ),
    )
    person_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    organization_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    relationship_type: Mapped[str] = mapped_column(String(30))
    role_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_record_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    confirmed_by_user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(
        String(20), default=PROFILE_STATUS_ACTIVE, server_default=PROFILE_STATUS_ACTIVE
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Interaction(Base):
    """One sanitized email touchpoint involving one durable person."""

    __tablename__ = "interactions"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "id",
            name="uq_interactions_workspace_id_id",
        ),
        UniqueConstraint(
            "workspace_id",
            "source_record_id",
            "person_id",
            name="uq_interactions_workspace_source_person",
        ),
        CheckConstraint(
            "channel in ('email')",
            name="ck_interactions_channel",
        ),
        CheckConstraint(
            "direction in ('inbound', 'outbound', 'mixed', 'unknown')",
            name="ck_interactions_direction",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "person_id"],
            ["people.workspace_id", "people.id"],
            name="fk_interactions_workspace_person",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "organization_id"],
            ["organizations.workspace_id", "organizations.id"],
            name="fk_interactions_workspace_organization",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "source_record_id"],
            ["source_records.workspace_id", "source_records.id"],
            name="fk_interactions_workspace_source_record",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_interactions_workspace_occurred_at",
            "workspace_id",
            "occurred_at",
        ),
        Index("ix_interactions_person_occurred_at", "person_id", "occurred_at"),
        Index(
            "ix_interactions_organization_occurred_at",
            "organization_id",
            "occurred_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "workspaces.id",
            name="fk_interactions_workspace_id",
            ondelete="CASCADE",
        ),
    )
    person_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    organization_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    source_record_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    channel: Mapped[str] = mapped_column(
        String(20),
        default=INTERACTION_CHANNEL_EMAIL,
        server_default=INTERACTION_CHANNEL_EMAIL,
    )
    direction: Mapped[str] = mapped_column(String(20))
    subject: Mapped[str | None] = mapped_column(String(500), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CompanyWorldResolution(Base):
    """Idempotent founder decision for one projected Company World candidate."""

    __tablename__ = "company_world_resolutions"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "id",
            name="uq_company_world_resolutions_workspace_id_id",
        ),
        UniqueConstraint(
            "workspace_id",
            "idempotency_key",
            name="uq_company_world_resolutions_workspace_idempotency_key",
        ),
        UniqueConstraint(
            "workspace_id",
            "candidate_type",
            "candidate_key",
            name="uq_company_world_resolutions_workspace_candidate",
        ),
        CheckConstraint(
            "candidate_type in ('external_person', 'organization')",
            name="ck_company_world_resolutions_candidate_type",
        ),
        CheckConstraint(
            "char_length(candidate_version) = 64",
            name="ck_company_world_resolutions_candidate_version",
        ),
        CheckConstraint(
            "decision in ('confirmed', 'dismissed')",
            name="ck_company_world_resolutions_decision",
        ),
        CheckConstraint(
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
        ForeignKeyConstraint(
            ["workspace_id", "actor_user_id"],
            ["memberships.workspace_id", "memberships.user_id"],
            name="fk_company_world_resolutions_workspace_actor",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "source_record_id"],
            ["source_records.workspace_id", "source_records.id"],
            name="fk_company_world_resolutions_workspace_source_record",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "result_person_id"],
            ["people.workspace_id", "people.id"],
            name="fk_company_world_resolutions_workspace_result_person",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "result_organization_id"],
            ["organizations.workspace_id", "organizations.id"],
            name="fk_company_world_resolutions_workspace_result_organization",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
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
        Index(
            "ix_company_world_resolutions_workspace_created_at",
            "workspace_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "workspaces.id",
            name="fk_company_world_resolutions_workspace_id",
            ondelete="CASCADE",
        ),
    )
    candidate_type: Mapped[str] = mapped_column(String(30))
    candidate_key: Mapped[str] = mapped_column(String(500))
    candidate_version: Mapped[str] = mapped_column(String(64))
    decision: Mapped[str] = mapped_column(String(20))
    idempotency_key: Mapped[str] = mapped_column(String(255))
    request_hash: Mapped[str] = mapped_column(String(64))
    actor_user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    source_record_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    result_person_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    result_organization_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    result_affiliation_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
