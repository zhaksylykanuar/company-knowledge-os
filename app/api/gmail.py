from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from app.api.workspace_auth import (
    WorkspaceAccess,
    require_workspace_access,
    require_workspace_role,
)
from app.db.base import AsyncSessionLocal
from app.db.identity_models import MEMBERSHIP_ROLE_ADMIN
from app.services.gmail_connector_service import (
    GmailConnectorError,
    import_gmail_messages_local,
    list_workspace_gmail_messages,
)

router = APIRouter(
    prefix="/api/v1/workspaces/{workspace_id}/gmail",
    tags=["gmail"],
)


class GmailEvidenceRefRead(BaseModel):
    kind: str
    source: str
    ref: str
    url: str | None = None


class GmailConnectorBoundaryRead(BaseModel):
    provider_calls: bool
    sync_started: bool
    external_writes: bool
    llm: bool
    reads_secrets: bool


class GmailMessageRead(BaseModel):
    source_record_id: UUID | None = None
    message_id: str
    thread_id: str | None = None
    subject: str
    snippet: str | None = None
    from_address: str | None = None
    to_addresses: list[str] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)
    unread: bool = False
    received_at: datetime | None = None
    source_url: str | None = None
    evidence_refs: list[GmailEvidenceRefRead] = Field(default_factory=list)


class GmailMessageListCounts(BaseModel):
    total: int
    unread: int
    read: int


class GmailMessageListResponse(BaseModel):
    workspace_id: str
    messages: list[GmailMessageRead] = Field(default_factory=list)
    counts: GmailMessageListCounts
    boundary: GmailConnectorBoundaryRead
    warnings: list[str] = Field(default_factory=list)


class GmailMessageImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    messages: list[dict[str, Any]] = Field(min_length=1, max_length=100)
    connection_id: UUID | None = None


class GmailMessageImportCounts(BaseModel):
    received: int
    imported: int
    failed: int
    source_records_created: int
    source_records_updated: int


class GmailMessageImportFailure(BaseModel):
    index: int
    reason: str


class GmailMessageImportResponse(BaseModel):
    workspace_id: str
    counts: GmailMessageImportCounts
    messages: list[GmailMessageRead] = Field(default_factory=list)
    failures: list[GmailMessageImportFailure] = Field(default_factory=list)
    boundary: GmailConnectorBoundaryRead
    warnings: list[str] = Field(default_factory=list)


@router.get("/messages", response_model=GmailMessageListResponse)
async def list_gmail_messages(
    limit: int = Query(default=100, ge=1, le=200),
    access: WorkspaceAccess = Depends(require_workspace_access),
) -> GmailMessageListResponse:
    async with AsyncSessionLocal() as session:
        payload = await list_workspace_gmail_messages(
            session,
            workspace_id=access.workspace_membership.workspace.id,
            limit=limit,
        )
    return GmailMessageListResponse.model_validate(payload)


@router.post(
    "/messages/import",
    response_model=GmailMessageImportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def import_gmail_messages(
    payload: GmailMessageImportRequest,
    access: WorkspaceAccess = Depends(require_workspace_role(MEMBERSHIP_ROLE_ADMIN)),
) -> GmailMessageImportResponse:
    async with AsyncSessionLocal() as session:
        try:
            result = await import_gmail_messages_local(
                session,
                workspace_id=access.workspace_membership.workspace.id,
                raw_messages=payload.messages,
                connection_id=payload.connection_id,
            )
            await session.commit()
        except GmailConnectorError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=exc.detail,
            ) from exc
    return GmailMessageImportResponse.model_validate(
        result.as_payload(workspace_id=access.workspace_membership.workspace.id)
    )
