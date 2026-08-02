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
from app.services.drive_connector_service import (
    DriveConnectorError,
    import_drive_files_local,
    list_workspace_drive_files,
)

router = APIRouter(
    prefix="/api/v1/workspaces/{workspace_id}/drive",
    tags=["drive"],
)


class DriveEvidenceRefRead(BaseModel):
    kind: str
    source: str
    ref: str
    url: str | None = None


class DriveConnectorBoundaryRead(BaseModel):
    provider_calls: bool
    sync_started: bool
    external_writes: bool
    llm: bool
    reads_secrets: bool


class DriveFileRead(BaseModel):
    source_record_id: UUID | None = None
    file_id: str
    name: str
    mime_type: str | None = None
    owners: list[str] = Field(default_factory=list)
    drive_id: str | None = None
    folder_path: str | None = None
    shared: bool = False
    size_bytes: int | None = None
    modified_at: datetime | None = None
    source_url: str | None = None
    evidence_refs: list[DriveEvidenceRefRead] = Field(default_factory=list)


class DriveFileListCounts(BaseModel):
    total: int
    shared: int
    not_shared: int


class DriveFileListResponse(BaseModel):
    workspace_id: str
    files: list[DriveFileRead] = Field(default_factory=list)
    counts: DriveFileListCounts
    boundary: DriveConnectorBoundaryRead
    warnings: list[str] = Field(default_factory=list)


class DriveFileImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    files: list[dict[str, Any]] = Field(min_length=1, max_length=100)
    connection_id: UUID | None = None


class DriveFileImportCounts(BaseModel):
    received: int
    imported: int
    failed: int
    source_records_created: int
    source_records_updated: int


class DriveFileImportFailure(BaseModel):
    index: int
    reason: str


class DriveFileImportResponse(BaseModel):
    workspace_id: str
    counts: DriveFileImportCounts
    files: list[DriveFileRead] = Field(default_factory=list)
    failures: list[DriveFileImportFailure] = Field(default_factory=list)
    boundary: DriveConnectorBoundaryRead
    warnings: list[str] = Field(default_factory=list)


@router.get("/files", response_model=DriveFileListResponse)
async def list_drive_files(
    limit: int = Query(default=100, ge=1, le=200),
    access: WorkspaceAccess = Depends(require_workspace_access),
) -> DriveFileListResponse:
    async with AsyncSessionLocal() as session:
        payload = await list_workspace_drive_files(
            session,
            workspace_id=access.workspace_membership.workspace.id,
            limit=limit,
        )
    return DriveFileListResponse.model_validate(payload)


@router.post(
    "/files/import",
    response_model=DriveFileImportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def import_drive_files(
    payload: DriveFileImportRequest,
    access: WorkspaceAccess = Depends(require_workspace_role(MEMBERSHIP_ROLE_ADMIN)),
) -> DriveFileImportResponse:
    async with AsyncSessionLocal() as session:
        try:
            result = await import_drive_files_local(
                session,
                workspace_id=access.workspace_membership.workspace.id,
                raw_files=payload.files,
                connection_id=payload.connection_id,
            )
            await session.commit()
        except DriveConnectorError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=exc.detail,
            ) from exc
    return DriveFileImportResponse.model_validate(
        result.as_payload(workspace_id=access.workspace_membership.workspace.id)
    )
