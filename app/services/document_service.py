"""Internal Document service (§6.16 / §7.11 / MVP §1.5 "internal documents").

Deterministic, local-only CRUD + search for workspace-scoped internal documents.
No provider calls, no external writes, no LLM: ``body_text`` is a deterministic
plain-text projection of the authored markdown used for search and Company Brain
context. The founder authors these documents inside founderOS, so unlike the
read-only connector slices they are stored in their own canonical table.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.document_models import (
    DOCUMENT_STATUS_DRAFT,
    DOCUMENT_STATUSES,
    Document,
    DocumentVersion,
)

DOCUMENT_NOT_FOUND = "document not found"
DOCUMENT_TITLE_MAX = 500
DOCUMENT_BODY_MAX = 100_000
DOCUMENT_TAG_MAX = 40
DOCUMENT_TAGS_MAX = 25
DOCUMENT_BOUNDARY_NOTE = (
    "Internal documents are local founderOS content; authoring and search perform "
    "no provider call, no external write, and no LLM."
)

_MARKDOWN_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_MARKDOWN_CODE_FENCE_RE = re.compile(r"```[^\n]*\n?")
_MARKDOWN_INLINE_MARKS_RE = re.compile(r"[*_`~>#]+")
_WHITESPACE_RE = re.compile(r"[ \t]+")
_BLANKLINES_RE = re.compile(r"\n{3,}")


class DocumentError(ValueError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class DocumentNotFoundError(DocumentError):
    pass


@dataclass(frozen=True)
class DocumentCreateInput:
    title: str
    body_markdown: str = ""
    tags: list[str] = field(default_factory=list)
    status: str = DOCUMENT_STATUS_DRAFT


@dataclass(frozen=True)
class DocumentUpdateInput:
    """Partial update; unset fields (``None``) are left unchanged."""

    title: str | None = None
    body_markdown: str | None = None
    tags: list[str] | None = None
    status: str | None = None


@dataclass(frozen=True)
class DocumentListFilters:
    status: str | None = None
    search: str | None = None
    limit: int = 50


def markdown_to_text(body_markdown: str) -> str:
    """Deterministically strip markdown to a plain-text projection for search.

    This is intentionally simple and offline: it removes images, unwraps link
    text, drops code fences and common inline marks, and collapses whitespace.
    It never calls a renderer, network, or LLM.
    """

    if not body_markdown:
        return ""
    text = _MARKDOWN_IMAGE_RE.sub("", body_markdown)
    text = _MARKDOWN_LINK_RE.sub(r"\1", text)
    text = _MARKDOWN_CODE_FENCE_RE.sub("", text)
    text = _MARKDOWN_INLINE_MARKS_RE.sub("", text)
    text = _WHITESPACE_RE.sub(" ", text)
    text = _BLANKLINES_RE.sub("\n\n", text)
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(lines).strip()


def _normalized_title(value: str | None) -> str:
    title = (value or "").strip()
    if not title:
        raise DocumentError("title is required")
    return title[:DOCUMENT_TITLE_MAX]


def _normalized_body(value: str | None) -> str:
    body = value or ""
    if len(body) > DOCUMENT_BODY_MAX:
        raise DocumentError("body_markdown exceeds the maximum size")
    return body


def _normalized_status(value: str | None) -> str:
    status = (value or DOCUMENT_STATUS_DRAFT).strip().casefold()
    if status not in DOCUMENT_STATUSES:
        raise DocumentError("unknown document status")
    return status


def _normalized_tags(value: list[str] | None) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise DocumentError("tags must be a list")
    tags: list[str] = []
    for raw in value:
        if not isinstance(raw, str):
            raise DocumentError("tags must be strings")
        tag = raw.strip()[:DOCUMENT_TAG_MAX]
        if tag and tag not in tags:
            tags.append(tag)
        if len(tags) >= DOCUMENT_TAGS_MAX:
            break
    return tags


async def create_document(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    created_by_user_id: UUID | None,
    payload: DocumentCreateInput,
) -> Document:
    title = _normalized_title(payload.title)
    body_markdown = _normalized_body(payload.body_markdown)
    document = Document(
        workspace_id=workspace_id,
        title=title,
        body_markdown=body_markdown,
        body_text=markdown_to_text(body_markdown),
        status=_normalized_status(payload.status),
        tags=_normalized_tags(payload.tags),
        created_by_user_id=created_by_user_id,
        updated_by_user_id=created_by_user_id,
    )
    session.add(document)
    await session.flush()
    await _append_document_version(
        session,
        document=document,
        created_by_user_id=created_by_user_id,
    )
    await session.refresh(document)
    return document


async def update_document(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    document_id: UUID,
    updated_by_user_id: UUID | None,
    payload: DocumentUpdateInput,
) -> Document:
    document = await _get_document_or_raise(
        session,
        workspace_id=workspace_id,
        document_id=document_id,
    )
    changed = False
    if payload.title is not None:
        title = _normalized_title(payload.title)
        if title != document.title:
            document.title = title
            changed = True
    if payload.body_markdown is not None:
        body_markdown = _normalized_body(payload.body_markdown)
        if body_markdown != document.body_markdown:
            document.body_markdown = body_markdown
            document.body_text = markdown_to_text(body_markdown)
            changed = True
    if payload.tags is not None:
        tags = _normalized_tags(payload.tags)
        if tags != list(document.tags or []):
            document.tags = tags
            changed = True
    if payload.status is not None:
        status = _normalized_status(payload.status)
        if status != document.status:
            document.status = status
            changed = True
    if not changed:
        return document
    document.updated_by_user_id = updated_by_user_id
    await session.flush()
    await _append_document_version(
        session,
        document=document,
        created_by_user_id=updated_by_user_id,
    )
    await session.refresh(document)
    return document


async def get_document(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    document_id: UUID,
) -> Document | None:
    return await session.scalar(
        select(Document)
        .where(Document.workspace_id == workspace_id)
        .where(Document.id == document_id)
    )


async def list_documents(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    filters: DocumentListFilters,
) -> list[Document]:
    statement = (
        select(Document)
        .where(Document.workspace_id == workspace_id)
        .order_by(Document.updated_at.desc(), Document.id.desc())
        .limit(max(1, min(filters.limit, 200)))
    )
    if filters.status:
        statement = statement.where(Document.status == _normalized_status(filters.status))
    search = (filters.search or "").strip()
    if search:
        like = f"%{search.casefold()}%"
        statement = statement.where(
            or_(
                func.lower(Document.title).like(like),
                func.lower(Document.body_text).like(like),
            )
        )
    return list((await session.execute(statement)).scalars())


async def delete_document(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    document_id: UUID,
) -> None:
    document = await _get_document_or_raise(
        session,
        workspace_id=workspace_id,
        document_id=document_id,
    )
    await session.delete(document)
    await session.flush()


async def list_document_versions(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    document_id: UUID,
    limit: int = 50,
) -> list[DocumentVersion]:
    document = await get_document(
        session,
        workspace_id=workspace_id,
        document_id=document_id,
    )
    if document is None:
        raise DocumentNotFoundError(DOCUMENT_NOT_FOUND)
    return list(
        (
            await session.execute(
                select(DocumentVersion)
                .where(DocumentVersion.workspace_id == workspace_id)
                .where(DocumentVersion.document_id == document_id)
                .order_by(DocumentVersion.version_number.desc())
                .limit(max(1, min(limit, 100)))
            )
        ).scalars()
    )


def serialize_document(document: Document, *, include_body: bool = True) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": document.id,
        "workspace_id": document.workspace_id,
        "title": document.title,
        "status": document.status,
        "tags": list(document.tags or []),
        "created_by_user_id": document.created_by_user_id,
        "updated_by_user_id": document.updated_by_user_id,
        "created_at": document.created_at,
        "updated_at": document.updated_at,
        "excerpt": _excerpt(document.body_text),
    }
    if include_body:
        payload["body_markdown"] = document.body_markdown
        payload["body_text"] = document.body_text
    return payload


def serialize_document_version(version: DocumentVersion) -> dict[str, Any]:
    return {
        "id": version.id,
        "workspace_id": version.workspace_id,
        "document_id": version.document_id,
        "version_number": version.version_number,
        "title": version.title,
        "body_markdown": version.body_markdown,
        "body_text": version.body_text,
        "status": version.status,
        "tags": list(version.tags or []),
        "created_by_user_id": version.created_by_user_id,
        "created_at": version.created_at,
        "excerpt": _excerpt(version.body_text),
    }


def _excerpt(body_text: str, *, limit: int = 240) -> str:
    text = (body_text or "").strip().replace("\n", " ")
    if len(text) <= limit:
        return text
    return f"{text[: limit - 1]}…"


async def _append_document_version(
    session: AsyncSession,
    *,
    document: Document,
    created_by_user_id: UUID | None,
) -> DocumentVersion:
    latest_version = int(
        await session.scalar(
            select(func.max(DocumentVersion.version_number)).where(
                DocumentVersion.document_id == document.id
            )
        )
        or 0
    )
    version = DocumentVersion(
        workspace_id=document.workspace_id,
        document_id=document.id,
        version_number=latest_version + 1,
        title=document.title,
        body_markdown=document.body_markdown,
        body_text=document.body_text,
        status=document.status,
        tags=list(document.tags or []),
        created_by_user_id=created_by_user_id,
    )
    session.add(version)
    await session.flush()
    return version


async def _get_document_or_raise(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    document_id: UUID,
) -> Document:
    document = await get_document(
        session,
        workspace_id=workspace_id,
        document_id=document_id,
    )
    if document is None:
        raise DocumentNotFoundError(DOCUMENT_NOT_FOUND)
    return document
