from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.workspace_auth import WorkspaceAccess, require_workspace_access
from app.api.workspace_company_brain import CompanyBrainSourceRefRead
from app.db.base import AsyncSessionLocal
from app.services.company_map_read_service import build_workspace_company_map

router = APIRouter(
    prefix="/api/v1/workspaces/{workspace_id}/company-map",
    tags=["company-map"],
)


class CompanyMapCompanyRead(BaseModel):
    key: str
    workspace_id: UUID
    name: str
    slug: str
    status: str
    source_refs: list[CompanyBrainSourceRefRead] = Field(default_factory=list)


class CompanyMapInternalPersonRead(BaseModel):
    key: str
    user_id: UUID
    name: str | None = None
    email: str
    status: str
    role: Literal["owner", "admin", "member", "viewer"]
    source_refs: list[CompanyBrainSourceRefRead] = Field(default_factory=list)


class CompanyMapExternalCandidateRead(BaseModel):
    key: str
    email: str
    display_name: str | None = None
    organization_key: str | None = None
    last_interaction_at: datetime | None = None
    interaction_count: int = 0
    source_refs: list[CompanyBrainSourceRefRead] = Field(default_factory=list)
    needs_founder_confirm: Literal[True] = True


class CompanyMapOrganizationCandidateRead(BaseModel):
    key: str
    domain: str
    name: str | None = None
    kind: Literal["external_candidate"] = "external_candidate"
    people_count: int = 0
    interaction_count: int = 0
    last_interaction_at: datetime | None = None
    source_refs: list[CompanyBrainSourceRefRead] = Field(default_factory=list)
    needs_founder_confirm: Literal[True] = True


class CompanyMapTouchpointRead(BaseModel):
    key: str
    channel: Literal["email"]
    source_record_id: UUID
    subject: str
    direction: Literal["inbound", "outbound", "mixed", "unknown"]
    occurred_at: datetime | None = None
    person_keys: list[str] = Field(default_factory=list)
    organization_keys: list[str] = Field(default_factory=list)
    source_url: str | None = None
    source_refs: list[CompanyBrainSourceRefRead] = Field(default_factory=list)


class CompanyMapSummaryRead(BaseModel):
    internal_people: int = 0
    external_contacts_in_window: int = 0
    organizations_in_window: int = 0
    touchpoints_in_window: int = 0


class CompanyMapWindowRead(BaseModel):
    gmail_messages_available: int = 0
    gmail_messages_considered: int = 0
    message_limit: int = 100
    truncated: bool = False
    order: Literal["newest_first"] = "newest_first"


class CompanyMapPeopleRead(BaseModel):
    internal: list[CompanyMapInternalPersonRead] = Field(default_factory=list)
    external_candidates: list[CompanyMapExternalCandidateRead] = Field(default_factory=list)


class CompanyMapCapabilitiesRead(BaseModel):
    read_only: Literal[True] = True
    provider_calls: Literal[False] = False
    llm_used: Literal[False] = False


class CompanyMapResponse(BaseModel):
    workspace_id: UUID
    mode: Literal["evidence_backed_projection"]
    source: Literal["workspace_and_company_brain_projection"]
    company: CompanyMapCompanyRead
    summary: CompanyMapSummaryRead
    window: CompanyMapWindowRead
    people: CompanyMapPeopleRead
    organizations: list[CompanyMapOrganizationCandidateRead] = Field(default_factory=list)
    touchpoints: list[CompanyMapTouchpointRead] = Field(default_factory=list)
    capabilities: CompanyMapCapabilitiesRead
    warnings: list[str] = Field(default_factory=list)
    is_live: Literal[False] = False
    llm_used: Literal[False] = False


@router.get("", response_model=CompanyMapResponse)
async def get_workspace_company_map(
    workspace_id: UUID,
    access: WorkspaceAccess = Depends(require_workspace_access),
) -> CompanyMapResponse:
    """Return the deterministic company-world projection for one workspace."""

    _ = access
    async with AsyncSessionLocal() as session:
        payload = await build_workspace_company_map(
            session=session,
            workspace_id=workspace_id,
        )
    return CompanyMapResponse.model_validate(payload)
