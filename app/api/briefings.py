from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.workspace_auth import WorkspaceAccess, require_workspace_access
from app.db.base import AsyncSessionLocal
from app.services.founder_briefing_service import (
    FounderBriefingOptions,
    generate_manual_founder_briefing,
)

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/briefings", tags=["briefings"])


class FounderBriefingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    focus: list[str] = Field(
        default_factory=lambda: ["github", "sync", "repositories"],
        max_length=20,
    )
    include_github: bool = True
    include_connections: bool = True
    include_sync_jobs: bool = True
    include_repository_inventory: bool = True
    limit: int = Field(default=20, ge=1, le=50)

    @field_validator("focus")
    @classmethod
    def validate_focus(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        for raw in value:
            focus = raw.strip().casefold()
            if not focus:
                continue
            normalized.append(focus[:80])
        return normalized


class BriefingEvidenceRef(BaseModel):
    kind: str
    source: str
    ref: str
    url: str | None = None


class FounderBriefingItemRead(BaseModel):
    id: str
    category: str
    title: str
    summary: str
    severity: str
    confidence: float
    evidence_refs: list[BriefingEvidenceRef] = Field(default_factory=list)
    related_entities: list[str] = Field(default_factory=list)
    recommended_next_step: str | None = None
    warnings: list[str] = Field(default_factory=list)


class FounderBriefingGitHubSignalsRead(BaseModel):
    connection_status: str
    repository_count: int
    queued_sync_jobs: int
    latest_sync_job_status: str | None = None


class FounderBriefingSignalsRead(BaseModel):
    github: FounderBriefingGitHubSignalsRead


class FounderBriefingRead(BaseModel):
    title: str
    summary: str
    generated_at: datetime
    workspace_id: UUID
    is_live: bool
    llm_used: bool
    persistence: str
    items: list[FounderBriefingItemRead]
    signals: FounderBriefingSignalsRead
    warnings: list[str] = Field(default_factory=list)


class FounderBriefingResponse(BaseModel):
    briefing: FounderBriefingRead


@router.post("/manual", response_model=FounderBriefingResponse)
async def generate_manual_founder_briefing_route(
    workspace_id: UUID,
    payload: FounderBriefingRequest,
    access: WorkspaceAccess = Depends(require_workspace_access),
) -> FounderBriefingResponse:
    _ = access
    async with AsyncSessionLocal() as session:
        result = await generate_manual_founder_briefing(
            session,
            workspace_id=workspace_id,
            options=FounderBriefingOptions(
                focus=payload.focus,
                include_github=payload.include_github,
                include_connections=payload.include_connections,
                include_sync_jobs=payload.include_sync_jobs,
                include_repository_inventory=payload.include_repository_inventory,
                limit=payload.limit,
            ),
        )
    return FounderBriefingResponse.model_validate(result)
