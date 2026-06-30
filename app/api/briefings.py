from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.workspace_auth import WorkspaceAccess, require_workspace_access
from app.db.base import AsyncSessionLocal
from app.services.briefing_persistence_service import (
    count_briefings,
    get_briefing,
    list_briefings,
    persist_briefing,
    serialize_briefing,
    serialize_briefing_summary,
)
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


class PersistedBriefingRead(BaseModel):
    """A saved briefing with its items (the generated content, now durable)."""

    id: UUID
    workspace_id: UUID
    created_at: datetime
    generated_at: datetime
    generated_by: str
    title: str
    summary: str
    is_live: bool
    llm_used: bool
    persistence: str
    items: list[FounderBriefingItemRead] = Field(default_factory=list)
    signals: FounderBriefingSignalsRead
    warnings: list[str] = Field(default_factory=list)


class PersistedBriefingResponse(BaseModel):
    briefing: PersistedBriefingRead


class BriefingSummaryRead(BaseModel):
    """One entry in the briefing history list (no items)."""

    id: UUID
    created_at: datetime
    generated_at: datetime
    generated_by: str
    title: str
    summary: str
    item_count: int
    signals: FounderBriefingSignalsRead


class BriefingListResponse(BaseModel):
    briefings: list[BriefingSummaryRead] = Field(default_factory=list)
    count: int


@router.post("/manual", response_model=PersistedBriefingResponse)
async def generate_manual_founder_briefing_route(
    workspace_id: UUID,
    payload: FounderBriefingRequest,
    access: WorkspaceAccess = Depends(require_workspace_access),
) -> PersistedBriefingResponse:
    """Run the deterministic generator, SAVE the briefing + items, return it.

    Generation is unchanged (deterministic, no LLM); this endpoint persists the
    output and returns the durable briefing including its ``id`` so it shows up
    in history.
    """

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
        briefing = await persist_briefing(
            session,
            workspace_id=workspace_id,
            created_by_user_id=access.workspace_membership.user.id,
            generated=result["briefing"],
        )
        data = serialize_briefing(briefing)
        await session.commit()
    return PersistedBriefingResponse.model_validate({"briefing": data})


@router.get("", response_model=BriefingListResponse)
async def list_briefings_route(
    workspace_id: UUID,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    access: WorkspaceAccess = Depends(require_workspace_access),
) -> BriefingListResponse:
    """List the workspace's saved briefings, newest first."""

    _ = access
    async with AsyncSessionLocal() as session:
        briefings = await list_briefings(
            session,
            workspace_id=workspace_id,
            limit=limit,
            offset=offset,
        )
        count = await count_briefings(session, workspace_id=workspace_id)
        data = [serialize_briefing_summary(briefing) for briefing in briefings]
    return BriefingListResponse.model_validate({"briefings": data, "count": count})


@router.get("/{briefing_id}", response_model=PersistedBriefingResponse)
async def get_briefing_route(
    workspace_id: UUID,
    briefing_id: UUID,
    access: WorkspaceAccess = Depends(require_workspace_access),
) -> PersistedBriefingResponse:
    """Read one saved briefing (with items), scoped to the workspace."""

    _ = access
    async with AsyncSessionLocal() as session:
        briefing = await get_briefing(
            session,
            workspace_id=workspace_id,
            briefing_id=briefing_id,
        )
        if briefing is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="briefing not found",
            )
        data = serialize_briefing(briefing)
    return PersistedBriefingResponse.model_validate({"briefing": data})
