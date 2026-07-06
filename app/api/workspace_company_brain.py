from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.workspace_auth import WorkspaceAccess, require_workspace_access
from app.db.base import AsyncSessionLocal
from app.services.company_brain_github_read_service import (
    build_workspace_company_brain,
)

router = APIRouter(
    prefix="/api/v1/workspaces/{workspace_id}/company-brain",
    tags=["company-brain"],
)


class CompanyBrainSourceRefRead(BaseModel):
    id: str
    kind: str
    source: str
    label: str
    url: str | None = None
    record_type: str
    record_id: UUID


class CompanyBrainSummaryRead(BaseModel):
    repositories: int
    open_issues: int
    open_pull_requests: int
    closed_issues: int
    merged_pull_requests: int


class CompanyBrainSourceRecordProviderCountRead(BaseModel):
    provider: str
    count: int


class CompanyBrainSourceRecordTypeCountRead(BaseModel):
    record_type: str
    count: int


class CompanyBrainSourceRecordCoverageRead(BaseModel):
    total: int = 0
    by_provider: list[CompanyBrainSourceRecordProviderCountRead] = Field(
        default_factory=list
    )
    by_record_type: list[CompanyBrainSourceRecordTypeCountRead] = Field(
        default_factory=list
    )


class CompanyBrainRepositoryRead(BaseModel):
    id: UUID
    provider: Literal["github"]
    external_id: str
    name: str
    full_name: str
    visibility: str | None = None
    archived: bool
    source_url: str | None = None
    last_activity_at: datetime | None = None
    source_refs: list[CompanyBrainSourceRefRead] = Field(default_factory=list)


class CompanyBrainWorkItemRead(BaseModel):
    id: UUID
    type: Literal["issue", "pull_request"]
    source_provider: str | None = None
    external_id: str | None = None
    number: int | None = None
    title: str
    state: str | None = None
    repository_full_name: str | None = None
    repository_external_id: str | None = None
    project_key: str | None = None
    source_url: str | None = None
    updated_at: datetime | None = None
    source_refs: list[CompanyBrainSourceRefRead] = Field(default_factory=list)


class CompanyBrainWorkRead(BaseModel):
    issues: list[CompanyBrainWorkItemRead] = Field(default_factory=list)
    pull_requests: list[CompanyBrainWorkItemRead] = Field(default_factory=list)
    recent: list[CompanyBrainWorkItemRead] = Field(default_factory=list)


class CompanyBrainMessageRead(BaseModel):
    source_record_id: UUID
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
    source_refs: list[CompanyBrainSourceRefRead] = Field(default_factory=list)


class CompanyBrainCommunicationsRead(BaseModel):
    messages: list[CompanyBrainMessageRead] = Field(default_factory=list)


class CompanyBrainDriveFileRead(BaseModel):
    source_record_id: UUID
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
    source_refs: list[CompanyBrainSourceRefRead] = Field(default_factory=list)


class CompanyBrainDocumentsRead(BaseModel):
    files: list[CompanyBrainDriveFileRead] = Field(default_factory=list)


class CompanyBrainCapabilitiesRead(BaseModel):
    live_github_oauth: bool
    live_provider_sync: bool
    local_sync: bool
    llm_briefing: bool


class CompanyBrainResponse(BaseModel):
    workspace_id: UUID
    mode: Literal["github_first_canonical"]
    source: Literal["canonical_github_company_brain"]
    summary: CompanyBrainSummaryRead
    source_records: CompanyBrainSourceRecordCoverageRead = Field(
        default_factory=CompanyBrainSourceRecordCoverageRead
    )
    repositories: list[CompanyBrainRepositoryRead] = Field(default_factory=list)
    work: CompanyBrainWorkRead
    communications: CompanyBrainCommunicationsRead = Field(
        default_factory=CompanyBrainCommunicationsRead
    )
    documents: CompanyBrainDocumentsRead = Field(default_factory=CompanyBrainDocumentsRead)
    evidence: list[CompanyBrainSourceRefRead] = Field(default_factory=list)
    capabilities: CompanyBrainCapabilitiesRead
    is_live: bool
    llm_used: bool
    warnings: list[str] = Field(default_factory=list)


@router.get("", response_model=CompanyBrainResponse)
async def get_workspace_company_brain(
    workspace_id: UUID,
    access: WorkspaceAccess = Depends(require_workspace_access),
) -> CompanyBrainResponse:
    _ = access
    async with AsyncSessionLocal() as session:
        payload = await build_workspace_company_brain(
            session=session,
            workspace_id=workspace_id,
        )
    return CompanyBrainResponse.model_validate(payload)
