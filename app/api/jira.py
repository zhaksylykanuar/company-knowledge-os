from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from app.api.workspace_auth import WorkspaceAccess, require_workspace_access, require_workspace_role
from app.db.base import AsyncSessionLocal
from app.db.identity_models import MEMBERSHIP_ROLE_ADMIN
from app.services.jira_connector_service import (
    JiraConnectorError,
    import_jira_issues_local,
    list_workspace_jira_issues,
)

router = APIRouter(
    prefix="/api/v1/workspaces/{workspace_id}/jira",
    tags=["jira"],
)


class JiraEvidenceRefRead(BaseModel):
    kind: str
    source: str
    ref: str
    url: str | None = None


class JiraConnectorBoundaryRead(BaseModel):
    provider_calls: bool
    sync_started: bool
    external_writes: bool
    llm: bool
    reads_secrets: bool


class JiraIssueRead(BaseModel):
    task_id: UUID | None = None
    source_record_id: UUID | None = None
    key: str
    title: str
    status: str | None = None
    status_category: str | None = None
    priority: str | None = None
    due_date: date | None = None
    source_url: str | None = None
    updated_at: datetime | None = None
    project_key: str | None = None
    issue_type: str | None = None
    evidence_refs: list[JiraEvidenceRefRead] = Field(default_factory=list)


class JiraIssueListCounts(BaseModel):
    total: int
    not_done: int
    done: int


class JiraIssueListResponse(BaseModel):
    workspace_id: str
    issues: list[JiraIssueRead] = Field(default_factory=list)
    counts: JiraIssueListCounts
    boundary: JiraConnectorBoundaryRead
    warnings: list[str] = Field(default_factory=list)


class JiraIssueImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    issues: list[dict[str, Any]] = Field(min_length=1, max_length=100)
    connection_id: UUID | None = None


class JiraIssueImportCounts(BaseModel):
    received: int
    imported: int
    failed: int
    source_records_created: int
    source_records_updated: int
    tasks_created: int
    tasks_updated: int


class JiraIssueImportFailure(BaseModel):
    index: int
    reason: str


class JiraIssueImportResponse(BaseModel):
    workspace_id: str
    counts: JiraIssueImportCounts
    issues: list[JiraIssueRead] = Field(default_factory=list)
    failures: list[JiraIssueImportFailure] = Field(default_factory=list)
    boundary: JiraConnectorBoundaryRead
    warnings: list[str] = Field(default_factory=list)


@router.get("/issues", response_model=JiraIssueListResponse)
async def list_jira_issues(
    limit: int = Query(default=100, ge=1, le=200),
    access: WorkspaceAccess = Depends(require_workspace_access),
) -> JiraIssueListResponse:
    async with AsyncSessionLocal() as session:
        payload = await list_workspace_jira_issues(
            session,
            workspace_id=access.workspace_membership.workspace.id,
            limit=limit,
        )
    return JiraIssueListResponse.model_validate(payload)


@router.post(
    "/issues/import",
    response_model=JiraIssueImportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def import_jira_issues(
    payload: JiraIssueImportRequest,
    access: WorkspaceAccess = Depends(require_workspace_role(MEMBERSHIP_ROLE_ADMIN)),
) -> JiraIssueImportResponse:
    async with AsyncSessionLocal() as session:
        try:
            result = await import_jira_issues_local(
                session,
                workspace_id=access.workspace_membership.workspace.id,
                raw_issues=payload.issues,
                connection_id=payload.connection_id,
            )
            await session.commit()
        except JiraConnectorError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=exc.detail,
            ) from exc
    return JiraIssueImportResponse.model_validate(
        result.as_payload(workspace_id=access.workspace_membership.workspace.id)
    )
