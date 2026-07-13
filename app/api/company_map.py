from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.api.workspace_auth import (
    WorkspaceAccess,
    require_workspace_access,
    require_workspace_role,
)
from app.api.workspace_company_brain import CompanyBrainSourceRefRead
from app.db.base import AsyncSessionLocal
from app.db.identity_models import MEMBERSHIP_ROLE_MEMBER
from app.services.company_map_read_service import build_workspace_company_map
from app.services.company_world_confirmation_service import (
    CompanyWorldCandidateNotFoundError,
    CompanyWorldEvidenceError,
    CompanyWorldResolutionConflictError,
    ResolveCompanyWorldCandidateCommand,
    resolve_company_world_candidate,
)

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
    person_id: UUID | None = None
    user_id: UUID
    name: str | None = None
    email: str
    status: str
    role: Literal["owner", "admin", "member", "viewer"]
    source_refs: list[CompanyBrainSourceRefRead] = Field(default_factory=list)


class CompanyMapExternalCandidateRead(BaseModel):
    key: str
    candidate_version: str
    email: str
    display_name: str | None = None
    organization_key: str | None = None
    last_interaction_at: datetime | None = None
    interaction_count: int = 0
    source_refs: list[CompanyBrainSourceRefRead] = Field(default_factory=list)
    needs_founder_confirm: Literal[True] = True


class CompanyMapOrganizationCandidateRead(BaseModel):
    key: str
    candidate_version: str
    domain: str
    name: str | None = None
    kind: Literal["external_candidate"] = "external_candidate"
    people_count: int = 0
    interaction_count: int = 0
    last_interaction_at: datetime | None = None
    source_refs: list[CompanyBrainSourceRefRead] = Field(default_factory=list)
    needs_founder_confirm: Literal[True] = True


class CompanyMapConfirmedExternalPersonRead(BaseModel):
    key: str
    person_id: UUID
    email: str
    display_name: str | None = None
    status: str
    organization_id: UUID | None = None
    organization_key: str | None = None
    organization_name: str | None = None
    relationship_type: str | None = None
    role_title: str | None = None
    interaction_count: int = 0
    last_interaction_at: datetime | None = None
    source_refs: list[CompanyBrainSourceRefRead] = Field(default_factory=list)


class CompanyMapConfirmedOrganizationRead(BaseModel):
    key: str
    organization_id: UUID
    domain: str | None = None
    name: str | None = None
    relationship_kind: str
    status: str
    people_count: int = 0
    interaction_count: int = 0
    last_interaction_at: datetime | None = None
    source_refs: list[CompanyBrainSourceRefRead] = Field(default_factory=list)


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
    confirmed_external_people: int = 0
    confirmed_organizations: int = 0
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
    confirmed_external: list[CompanyMapConfirmedExternalPersonRead] = Field(default_factory=list)
    external_candidates: list[CompanyMapExternalCandidateRead] = Field(default_factory=list)


class CompanyMapCapabilitiesRead(BaseModel):
    read_only: Literal[True] = True
    can_resolve: bool = False
    required_role: Literal["member"] = "member"
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
    confirmed_organizations: list[CompanyMapConfirmedOrganizationRead] = Field(default_factory=list)
    touchpoints: list[CompanyMapTouchpointRead] = Field(default_factory=list)
    capabilities: CompanyMapCapabilitiesRead
    warnings: list[str] = Field(default_factory=list)
    is_live: Literal[False] = False
    llm_used: Literal[False] = False


class CompanyWorldResolutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_type: Literal["external_person", "organization"]
    candidate_key: str = Field(min_length=1, max_length=500)
    candidate_version: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision: Literal["confirmed", "dismissed"]
    idempotency_key: str = Field(min_length=8, max_length=255)
    display_name: str | None = Field(default=None, max_length=255)
    organization_name: str | None = Field(default=None, max_length=255)
    relationship_type: (
        Literal[
            "contact",
            "employee",
            "decision_maker",
            "account_owner",
            "advisor",
            "other",
        ]
        | None
    ) = None
    organization_relationship_kind: (
        Literal[
            "unknown",
            "prospect",
            "customer",
            "partner",
            "vendor",
            "other",
        ]
        | None
    ) = None
    role_title: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def validate_founder_fields(self) -> "CompanyWorldResolutionRequest":
        founder_fields = (
            self.display_name,
            self.organization_name,
            self.relationship_type,
            self.organization_relationship_kind,
            self.role_title,
        )
        if self.decision == "dismissed" and any(value is not None for value in founder_fields):
            raise ValueError("dismissed candidates cannot include profile fields")
        if self.candidate_type == "organization" and (
            self.relationship_type is not None or self.role_title is not None
        ):
            raise ValueError("organization candidates cannot include affiliation fields")
        if self.candidate_type == "external_person" and (
            self.organization_name is not None or self.organization_relationship_kind is not None
        ):
            raise ValueError("external person candidates cannot confirm organization fields")
        if self.role_title is not None and self.relationship_type is None:
            raise ValueError("role_title requires relationship_type")
        return self


class CompanyWorldResolutionRead(BaseModel):
    id: UUID
    candidate_type: Literal["external_person", "organization"]
    candidate_key: str
    decision: Literal["confirmed", "dismissed"]
    created_at: datetime


class CompanyWorldResolutionCapabilitiesRead(BaseModel):
    provider_calls: Literal[False] = False
    external_write: Literal[False] = False
    llm_used: Literal[False] = False


class CompanyWorldResolutionResponse(BaseModel):
    resolution: CompanyWorldResolutionRead
    person_id: UUID | None = None
    organization_id: UUID | None = None
    affiliation_id: UUID | None = None
    interaction_count: int = 0
    replayed: bool = False
    capabilities: CompanyWorldResolutionCapabilitiesRead = Field(
        default_factory=CompanyWorldResolutionCapabilitiesRead
    )


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
            access_role=access.workspace_membership.membership.role,
        )
    return CompanyMapResponse.model_validate(payload)


@router.post("/resolutions", response_model=CompanyWorldResolutionResponse)
async def resolve_workspace_company_map_candidate(
    workspace_id: UUID,
    request: CompanyWorldResolutionRequest,
    access: WorkspaceAccess = Depends(require_workspace_role(MEMBERSHIP_ROLE_MEMBER)),
) -> CompanyWorldResolutionResponse:
    """Confirm or dismiss one evidence-backed Company World candidate."""

    command = ResolveCompanyWorldCandidateCommand(
        candidate_type=request.candidate_type,
        candidate_key=request.candidate_key,
        candidate_version=request.candidate_version,
        decision=request.decision,
        idempotency_key=request.idempotency_key,
        display_name=request.display_name,
        organization_name=request.organization_name,
        relationship_type=request.relationship_type,
        organization_relationship_kind=request.organization_relationship_kind,
        role_title=request.role_title,
    )
    async with AsyncSessionLocal() as session:
        try:
            receipt = await resolve_company_world_candidate(
                session=session,
                workspace_id=workspace_id,
                actor_user_id=access.workspace_membership.user.id,
                command=command,
            )
        except CompanyWorldCandidateNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="company world candidate not found",
            ) from exc
        except (CompanyWorldResolutionConflictError, CompanyWorldEvidenceError) as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc
        await session.commit()

    return CompanyWorldResolutionResponse(
        resolution=CompanyWorldResolutionRead(
            id=receipt.resolution.id,
            candidate_type=receipt.resolution.candidate_type,
            candidate_key=receipt.resolution.candidate_key,
            decision=receipt.resolution.decision,
            created_at=receipt.resolution.created_at,
        ),
        person_id=receipt.person_id,
        organization_id=receipt.organization_id,
        affiliation_id=receipt.affiliation_id,
        interaction_count=receipt.interaction_count,
        replayed=receipt.replayed,
    )
