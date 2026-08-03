"""Workspace-scoped Repository Intelligence read APIs (RI-007)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from app.api.workspace_auth import WorkspaceAccess, require_workspace_access
from app.db.base import AsyncSessionLocal
from app.services.repository_intelligence.read_service import (
    DEFAULT_HISTORY_LIMIT,
    DEFAULT_PORTFOLIO_LIMIT,
    MAX_GRAPH_EDGES,
    MAX_HISTORY_LIMIT,
    MAX_PORTFOLIO_LIMIT,
    build_repository_intelligence_detail,
    build_repository_intelligence_graph,
    build_repository_intelligence_history,
    build_repository_intelligence_portfolio,
)


router = APIRouter(
    prefix="/api/v1/workspaces/{workspace_id}/repository-intelligence",
    tags=["repository-intelligence"],
)


class _ReadModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RepositoryIntelligenceCapabilitiesRead(_ReadModel):
    provider_calls: Literal[False]
    repository_reads: Literal[False]
    target_execution: Literal[False]
    external_writes: Literal[False]
    llm_used: Literal[False]
    human_resolution_writes: Literal[False]


class RepositoryIdentityRead(_ReadModel):
    id: UUID
    provider: Literal["github"]
    external_id: str
    name: str
    full_name: str
    default_branch: str | None = None
    visibility: str | None = None
    archived: bool
    source_url: str | None = None
    last_activity_at: datetime | None = None


class RepositoryLatestAuditRead(_ReadModel):
    id: UUID
    audit_level: Literal["L0", "L1", "L2"]
    target_status: Literal["exact", "unavailable"]
    commit_sha: str | None = None
    metadata_snapshot_id: str | None = None
    profile: str
    engine_version: str
    status: Literal["succeeded", "partial", "failed", "cancelled"]
    coverage_status: Literal["complete", "partial"]
    reconciliation_applied: bool
    completed_at: datetime
    artifact_status: Literal["retained", "purged"]


class RepositoryOpenFindingsRead(_ReadModel):
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    info: int = 0


class RepositoryPortfolioItemRead(RepositoryIdentityRead):
    purpose_summary: str | None = None
    operational_summary: str | None = None
    repository_type: str
    purpose_status: str
    purpose_confidence: float
    product_candidates: list[str] = Field(default_factory=list)
    owner_candidates: list[str] = Field(default_factory=list)
    has_confirmed_owner: bool
    latest_audit: RepositoryLatestAuditRead | None = None
    open_findings: RepositoryOpenFindingsRead
    open_findings_total: int
    outbound_relationship_count: int
    inbound_relationship_count: int
    unknown_count: int
    pending_confirmation_count: int
    has_stale_intelligence: bool


class RepositoryPortfolioSummaryRead(_ReadModel):
    repositories: int
    analyzed_repositories: int
    repositories_with_open_findings: int
    repositories_with_stale_intelligence: int
    current_relationships: int
    blocking_unknowns: int
    pending_confirmations: int


class RepositoryPortfolioLimitsRead(_ReadModel):
    repositories: int


class RepositoryPortfolioResponse(_ReadModel):
    workspace_id: UUID
    mode: Literal["repository_intelligence_read_only"] = (
        "repository_intelligence_read_only"
    )
    source: Literal["ri_006_persistence"] = "ri_006_persistence"
    summary: RepositoryPortfolioSummaryRead
    repositories: list[RepositoryPortfolioItemRead] = Field(default_factory=list)
    limits: RepositoryPortfolioLimitsRead
    truncated: bool
    capabilities: RepositoryIntelligenceCapabilitiesRead
    warnings: list[str] = Field(default_factory=list)


class RepositoryEvidenceRead(_ReadModel):
    id: UUID
    role: Literal["supporting", "contradicting"]
    kind: str
    source: str
    ref: str | None = None
    record_id: UUID
    url: str | None = None
    confidence: float


class RepositoryFactRead(_ReadModel):
    id: UUID
    fact_type: str
    claim_id: str
    value: dict[str, Any]
    claim_status: str
    confidence: float
    lifecycle_status: Literal["current", "stale"]
    human_resolution_status: Literal["pending", "confirmed", "rejected"]
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    stale_at: datetime | None = None
    evidence: list[RepositoryEvidenceRead] = Field(default_factory=list)


class RepositoryGraphReferenceRead(_ReadModel):
    id: UUID
    full_name: str


class RepositoryRelationshipRead(_ReadModel):
    id: UUID
    direction: Literal["outbound", "inbound"]
    from_repository: RepositoryGraphReferenceRead
    to_repository: RepositoryGraphReferenceRead | None = None
    target_full_name: str
    relationship_type: str
    resolution_status: Literal["canonical", "candidate"]
    summary: str | None = None
    claim_status: Literal["observed", "inferred"]
    confidence: float
    lifecycle_status: Literal["current", "stale"]
    human_resolution_status: Literal["pending", "confirmed", "rejected"]
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    stale_at: datetime | None = None
    evidence: list[RepositoryEvidenceRead] = Field(default_factory=list)


class RepositoryFindingRead(_ReadModel):
    id: UUID
    finding_id: str
    rule_id: str
    category: str
    severity: Literal["info", "low", "medium", "high", "critical"]
    confidence: float
    status: str
    title: str
    summary: str
    recommended_next_step: str | None = None
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    resolved_at: datetime | None = None
    evidence: list[RepositoryEvidenceRead] = Field(default_factory=list)


class RepositoryContradictionFactRead(_ReadModel):
    id: UUID
    fact_type: str
    claim_id: str
    value: dict[str, Any]
    claim_status: str


class RepositoryContradictionRead(_ReadModel):
    id: UUID
    contradiction_id: str
    status: Literal["current", "resolved"]
    confidence: float
    summary: str
    left_fact: RepositoryContradictionFactRead | None = None
    right_fact: RepositoryContradictionFactRead | None = None
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    resolved_at: datetime | None = None
    evidence: list[RepositoryEvidenceRead] = Field(default_factory=list)


class RepositoryConfirmationRead(_ReadModel):
    kind: Literal["fact", "relationship"]
    id: UUID
    label: str
    claim_status: str
    human_resolution_status: Literal["pending", "confirmed", "rejected"]
    evidence: list[RepositoryEvidenceRead] = Field(default_factory=list)


class RepositoryDetailTruncatedRead(_ReadModel):
    facts: bool
    relationships: bool
    findings: bool
    contradictions: bool
    confirmation_queue: bool


class RepositoryDetailResponse(_ReadModel):
    workspace_id: UUID
    mode: Literal["repository_intelligence_read_only"] = (
        "repository_intelligence_read_only"
    )
    source: Literal["ri_006_persistence"] = "ri_006_persistence"
    repository: RepositoryIdentityRead
    purpose: RepositoryFactRead | None = None
    latest_audit: RepositoryLatestAuditRead | None = None
    facts: list[RepositoryFactRead] = Field(default_factory=list)
    relationships: list[RepositoryRelationshipRead] = Field(default_factory=list)
    findings: list[RepositoryFindingRead] = Field(default_factory=list)
    contradictions: list[RepositoryContradictionRead] = Field(default_factory=list)
    unknowns: list[RepositoryFactRead] = Field(default_factory=list)
    confirmation_queue: list[RepositoryConfirmationRead] = Field(
        default_factory=list
    )
    limitations: list[str] = Field(default_factory=list)
    truncated: RepositoryDetailTruncatedRead
    capabilities: RepositoryIntelligenceCapabilitiesRead


class RepositoryHistoryRunRead(_ReadModel):
    id: UUID
    audit_level: Literal["L0", "L1", "L2"]
    target_status: Literal["exact", "unavailable"]
    commit_sha: str | None = None
    metadata_snapshot_id: str | None = None
    profile: str
    policy_hash: str
    engine_version: str
    status: Literal["succeeded", "partial", "failed", "cancelled"]
    coverage_status: Literal["complete", "partial"]
    completed_checks: list[str] = Field(default_factory=list)
    failed_checks: list[str] = Field(default_factory=list)
    skipped_checks: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    reconciliation_applied: bool
    artifact_count: int
    artifact_status: Literal["retained", "purged"]
    started_at: datetime
    completed_at: datetime


class RepositoryHistoryResponse(_ReadModel):
    workspace_id: UUID
    mode: Literal["repository_intelligence_read_only"] = (
        "repository_intelligence_read_only"
    )
    source: Literal["ri_006_persistence"] = "ri_006_persistence"
    repository: RepositoryIdentityRead
    runs: list[RepositoryHistoryRunRead] = Field(default_factory=list)
    limit: int
    truncated: bool
    capabilities: RepositoryIntelligenceCapabilitiesRead


class RepositoryGraphNodeRead(_ReadModel):
    id: UUID
    full_name: str
    repository_type: str
    archived: bool
    open_findings_total: int
    has_stale_intelligence: bool
    latest_audit_at: datetime | None = None


class RepositoryGraphEdgeRead(_ReadModel):
    id: UUID
    from_repository_id: UUID
    from_repository_full_name: str
    to_repository_id: UUID | None = None
    target_full_name: str
    relationship_type: str
    resolution_status: Literal["canonical", "candidate"]
    claim_status: Literal["observed", "inferred"]
    human_resolution_status: Literal["pending", "confirmed", "rejected"]
    confidence: float
    summary: str | None = None


class RepositoryGraphSummaryRead(_ReadModel):
    nodes: int
    edges: int
    observed_edges: int
    inferred_edges: int
    candidate_edges: int


class RepositoryGraphTruncatedRead(_ReadModel):
    nodes: bool
    edges: bool


class RepositoryGraphResponse(_ReadModel):
    workspace_id: UUID
    mode: Literal["repository_intelligence_read_only"] = (
        "repository_intelligence_read_only"
    )
    source: Literal["ri_006_persistence"] = "ri_006_persistence"
    nodes: list[RepositoryGraphNodeRead] = Field(default_factory=list)
    edges: list[RepositoryGraphEdgeRead] = Field(default_factory=list)
    summary: RepositoryGraphSummaryRead
    truncated: RepositoryGraphTruncatedRead
    capabilities: RepositoryIntelligenceCapabilitiesRead


@router.get("", response_model=RepositoryPortfolioResponse)
async def get_repository_intelligence_portfolio(
    workspace_id: UUID,
    limit: int = Query(
        default=DEFAULT_PORTFOLIO_LIMIT,
        ge=1,
        le=MAX_PORTFOLIO_LIMIT,
    ),
    access: WorkspaceAccess = Depends(require_workspace_access),
) -> RepositoryPortfolioResponse:
    """Read the bounded Repository Intelligence portfolio for one workspace."""

    _ = access
    async with AsyncSessionLocal() as session:
        payload = await build_repository_intelligence_portfolio(
            session=session,
            workspace_id=workspace_id,
            limit=limit,
        )
    return RepositoryPortfolioResponse.model_validate(payload)


@router.get("/graph", response_model=RepositoryGraphResponse)
async def get_repository_intelligence_graph(
    workspace_id: UUID,
    repository_limit: int = Query(
        default=MAX_PORTFOLIO_LIMIT,
        ge=1,
        le=MAX_PORTFOLIO_LIMIT,
    ),
    edge_limit: int = Query(
        default=MAX_GRAPH_EDGES,
        ge=1,
        le=MAX_GRAPH_EDGES,
    ),
    access: WorkspaceAccess = Depends(require_workspace_access),
) -> RepositoryGraphResponse:
    """Read the bounded current directional repository graph."""

    _ = access
    async with AsyncSessionLocal() as session:
        payload = await build_repository_intelligence_graph(
            session=session,
            workspace_id=workspace_id,
            repository_limit=repository_limit,
            edge_limit=edge_limit,
        )
    return RepositoryGraphResponse.model_validate(payload)


@router.get(
    "/repositories/{repository_id}",
    response_model=RepositoryDetailResponse,
)
async def get_repository_intelligence_detail(
    workspace_id: UUID,
    repository_id: UUID,
    access: WorkspaceAccess = Depends(require_workspace_access),
) -> RepositoryDetailResponse:
    """Read facts, edges, findings, unknowns, and sanitized evidence."""

    _ = access
    async with AsyncSessionLocal() as session:
        payload = await build_repository_intelligence_detail(
            session=session,
            workspace_id=workspace_id,
            repository_id=repository_id,
        )
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="repository intelligence not found",
        )
    return RepositoryDetailResponse.model_validate(payload)


@router.get(
    "/repositories/{repository_id}/history",
    response_model=RepositoryHistoryResponse,
)
async def get_repository_intelligence_history(
    workspace_id: UUID,
    repository_id: UUID,
    limit: int = Query(
        default=DEFAULT_HISTORY_LIMIT,
        ge=1,
        le=MAX_HISTORY_LIMIT,
    ),
    access: WorkspaceAccess = Depends(require_workspace_access),
) -> RepositoryHistoryResponse:
    """Read bounded immutable audit history without artifact paths or bodies."""

    _ = access
    async with AsyncSessionLocal() as session:
        payload = await build_repository_intelligence_history(
            session=session,
            workspace_id=workspace_id,
            repository_id=repository_id,
            limit=limit,
        )
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="repository intelligence not found",
        )
    return RepositoryHistoryResponse.model_validate(payload)
