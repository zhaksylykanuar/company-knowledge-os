"""Internal Document model (§6.16 Document / MVP §1.5 "internal documents").

FounderOS MVP requires a first-class internal document module: the founder can
create/edit workspace-scoped documents, and those documents show up in Company
Brain and search. Unlike the read-only connector slices (Jira/Gmail/Drive) that
ingest external provider snapshots into ``SourceRecord``, an internal Document is
authored inside founderOS, so it is its own canonical, workspace-scoped table.

This module stores only user-authored content (title / markdown body / derived
plain text / tags / status). It performs no provider calls and no LLM work; the
plain-text projection is a deterministic strip of the markdown body used for
search and Company Brain context.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base

# Register FK-target tables (workspaces / users -> identity_models) in the shared
# metadata regardless of import order, so the string foreign keys below resolve.
import app.db.identity_models  # noqa: E402,F401

DOCUMENT_STATUS_DRAFT = "draft"
DOCUMENT_STATUS_PUBLISHED = "published"
DOCUMENT_STATUS_ARCHIVED = "archived"

DOCUMENT_STATUSES = (
    DOCUMENT_STATUS_DRAFT,
    DOCUMENT_STATUS_PUBLISHED,
    DOCUMENT_STATUS_ARCHIVED,
)


class Document(Base):
    """One workspace-scoped internal document (§6.16).

    ``body_markdown`` is the authored source; ``body_text`` is a deterministic
    plain-text projection used for search and Company Brain context. Both are
    required by the spec. ``status`` is constrained to draft/published/archived.
    """

    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(
            "status in ('draft', 'published', 'archived')",
            name="ck_documents_status",
        ),
        Index("ix_documents_workspace_status", "workspace_id", "status"),
        Index("ix_documents_workspace_updated_at", "workspace_id", "updated_at"),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "workspaces.id",
            name="fk_documents_workspace_id",
            ondelete="CASCADE",
        ),
        index=True,
    )
    title: Mapped[str] = mapped_column(String(500))
    body_markdown: Mapped[str] = mapped_column(Text, default="")
    body_text: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(
        String(20), default=DOCUMENT_STATUS_DRAFT, index=True
    )
    tags: Mapped[list] = mapped_column(JSON, default=list)
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "users.id",
            name="fk_documents_created_by_user_id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )
    updated_by_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "users.id",
            name="fk_documents_updated_by_user_id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DocumentVersion(Base):
    """Immutable snapshot of one document revision (§4.7 DocumentVersion).

    Versions are local-only audit/history records. Version 1 is created with the
    document; each successful update appends the next version number. The latest
    ``Document`` row stays the editable source of truth, while versions preserve
    prior/current authored markdown and deterministic plain-text projection.
    """

    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "version_number",
            name="uq_document_versions_document_version_number",
        ),
        Index(
            "ix_document_versions_workspace_document_created",
            "workspace_id",
            "document_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "workspaces.id",
            name="fk_document_versions_workspace_id",
            ondelete="CASCADE",
        ),
        index=True,
    )
    document_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "documents.id",
            name="fk_document_versions_document_id",
            ondelete="CASCADE",
        ),
        index=True,
    )
    version_number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(500))
    body_markdown: Mapped[str] = mapped_column(Text, default="")
    body_text: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20))
    tags: Mapped[list] = mapped_column(JSON, default=list)
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "users.id",
            name="fk_document_versions_created_by_user_id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
