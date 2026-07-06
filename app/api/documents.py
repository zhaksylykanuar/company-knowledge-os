from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from app.api.workspace_auth import (
    WorkspaceAccess,
    require_workspace_access,
    require_workspace_role,
)
from app.db.base import AsyncSessionLocal
from app.db.identity_models import MEMBERSHIP_ROLE_MEMBER
from app.services.document_service import (
    DOCUMENT_NOT_FOUND,
    DocumentCreateInput,
    DocumentError,
    DocumentListFilters,
    DocumentNotFoundError,
    DocumentUpdateInput,
    create_document,
    delete_document,
    get_document,
    list_documents,
    serialize_document,
    update_document,
)

router = APIRouter(
    prefix="/api/v1/workspaces/{workspace_id}/documents",
    tags=["documents"],
)


class DocumentBoundaryRead(BaseModel):
    provider_calls: bool = False
    external_writes: bool = False
    llm: bool = False
    reads_secrets: bool = False


class DocumentSummaryRead(BaseModel):
    id: UUID
    workspace_id: UUID
    title: str
    status: str
    tags: list[str] = Field(default_factory=list)
    excerpt: str = ""
    created_by_user_id: UUID | None = None
    updated_by_user_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class DocumentRead(DocumentSummaryRead):
    body_markdown: str = ""
    body_text: str = ""


class DocumentListResponse(BaseModel):
    workspace_id: UUID
    documents: list[DocumentSummaryRead] = Field(default_factory=list)
    count: int
    boundary: DocumentBoundaryRead = Field(default_factory=DocumentBoundaryRead)


class DocumentResponse(BaseModel):
    document: DocumentRead
    boundary: DocumentBoundaryRead = Field(default_factory=DocumentBoundaryRead)


class DocumentCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=500)
    body_markdown: str = Field(default="", max_length=100_000)
    tags: list[str] = Field(default_factory=list, max_length=25)
    status: str = Field(default="draft", max_length=20)


class DocumentUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str | None = Field(default=None, max_length=500)
    body_markdown: str | None = Field(default=None, max_length=100_000)
    tags: list[str] | None = Field(default=None, max_length=25)
    status: str | None = Field(default=None, max_length=20)


@router.get("", response_model=DocumentListResponse)
async def list_documents_route(
    status_filter: str | None = Query(default=None, alias="status", max_length=20),
    search: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=200),
    access: WorkspaceAccess = Depends(require_workspace_access),
) -> DocumentListResponse:
    workspace_id = access.workspace_membership.workspace.id
    async with AsyncSessionLocal() as session:
        try:
            documents = await list_documents(
                session,
                workspace_id=workspace_id,
                filters=DocumentListFilters(
                    status=status_filter,
                    search=search,
                    limit=limit,
                ),
            )
        except DocumentError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=exc.detail,
            ) from exc
        data = [
            serialize_document(document, include_body=False) for document in documents
        ]
    return DocumentListResponse.model_validate(
        {
            "workspace_id": workspace_id,
            "documents": data,
            "count": len(data),
            "boundary": DocumentBoundaryRead().model_dump(),
        }
    )


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def create_document_route(
    payload: DocumentCreateRequest,
    access: WorkspaceAccess = Depends(require_workspace_role(MEMBERSHIP_ROLE_MEMBER)),
) -> DocumentResponse:
    workspace_id = access.workspace_membership.workspace.id
    async with AsyncSessionLocal() as session:
        try:
            document = await create_document(
                session,
                workspace_id=workspace_id,
                created_by_user_id=access.workspace_membership.user.id,
                payload=DocumentCreateInput(
                    title=payload.title,
                    body_markdown=payload.body_markdown,
                    tags=payload.tags,
                    status=payload.status,
                ),
            )
            data = serialize_document(document)
            await session.commit()
        except DocumentError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=exc.detail,
            ) from exc
    return DocumentResponse.model_validate(
        {"document": data, "boundary": DocumentBoundaryRead().model_dump()}
    )


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document_route(
    document_id: UUID,
    access: WorkspaceAccess = Depends(require_workspace_access),
) -> DocumentResponse:
    workspace_id = access.workspace_membership.workspace.id
    async with AsyncSessionLocal() as session:
        document = await get_document(
            session,
            workspace_id=workspace_id,
            document_id=document_id,
        )
        if document is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=DOCUMENT_NOT_FOUND,
            )
        data = serialize_document(document)
    return DocumentResponse.model_validate(
        {"document": data, "boundary": DocumentBoundaryRead().model_dump()}
    )


@router.patch("/{document_id}", response_model=DocumentResponse)
async def update_document_route(
    document_id: UUID,
    payload: DocumentUpdateRequest,
    access: WorkspaceAccess = Depends(require_workspace_role(MEMBERSHIP_ROLE_MEMBER)),
) -> DocumentResponse:
    workspace_id = access.workspace_membership.workspace.id
    async with AsyncSessionLocal() as session:
        try:
            document = await update_document(
                session,
                workspace_id=workspace_id,
                document_id=document_id,
                updated_by_user_id=access.workspace_membership.user.id,
                payload=DocumentUpdateInput(
                    title=payload.title,
                    body_markdown=payload.body_markdown,
                    tags=payload.tags,
                    status=payload.status,
                ),
            )
            data = serialize_document(document)
            await session.commit()
        except DocumentNotFoundError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=exc.detail,
            ) from exc
        except DocumentError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=exc.detail,
            ) from exc
    return DocumentResponse.model_validate(
        {"document": data, "boundary": DocumentBoundaryRead().model_dump()}
    )


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document_route(
    document_id: UUID,
    access: WorkspaceAccess = Depends(require_workspace_role(MEMBERSHIP_ROLE_MEMBER)),
) -> None:
    workspace_id = access.workspace_membership.workspace.id
    async with AsyncSessionLocal() as session:
        try:
            await delete_document(
                session,
                workspace_id=workspace_id,
                document_id=document_id,
            )
            await session.commit()
        except DocumentNotFoundError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=exc.detail,
            ) from exc
