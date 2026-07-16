from __future__ import annotations

from datetime import datetime
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.api.workspace_auth import WorkspaceAccess, require_workspace_access
from app.services.headquarters_read_service import (
    HEADQUARTERS_CONTRACT_VERSION,
    HEADQUARTERS_ONBOARDING_CONTRACT_VERSION,
    HEADQUARTERS_ONBOARDING_READINESS_VERSION,
    HEADQUARTERS_RANKING_VERSION,
    HeadquartersAccessChangedError,
    read_workspace_headquarters,
    sanitize_headquarters_evidence_url,
)

router = APIRouter(
    prefix="/api/v1/workspaces/{workspace_id}/headquarters",
    tags=["headquarters"],
)


class StrictReadModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HeadquartersActionRead(StrictReadModel):
    kind: str
    label: str
    target: str | None = None
    enabled: bool
    disabled_reason: str | None = None

    @field_validator("target")
    @classmethod
    def validate_safe_target(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return _validate_internal_target(value)

    @model_validator(mode="after")
    def validate_disabled_reason(self) -> HeadquartersActionRead:
        if self.enabled and self.disabled_reason is not None:
            raise ValueError("enabled action cannot have disabled_reason")
        if not self.enabled and not self.disabled_reason:
            raise ValueError("disabled action requires disabled_reason")
        return self


class HeadquartersEvidenceRefRead(StrictReadModel):
    id: str
    kind: str
    source_key: str
    label: str
    target: str | None = None
    provenance: Literal[
        "briefing_item",
        "canonical_evidence_ref",
        "canonical_source_record",
        "canonical_repository",
        "integration_connection",
        "company_world_projection",
        "headquarters_aggregate",
    ]
    trust: Literal["verified", "aggregate"]
    reference_type: Literal[
        "briefing_item",
        "evidence_ref",
        "source_record",
        "repository",
        "integration_connection",
        "sync_job",
        "company_world_candidate",
        "headquarters_snapshot",
    ]
    reference_id: str
    workspace_scoped: Literal[True]

    @field_validator("target")
    @classmethod
    def validate_safe_target(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if value.startswith("/"):
            return _validate_internal_target(value)
        return _validate_external_evidence_target(value)


class HeadquartersFactProvenanceRead(StrictReadModel):
    owner: list[HeadquartersEvidenceRefRead] = Field(default_factory=list)
    customer: list[HeadquartersEvidenceRefRead] = Field(default_factory=list)
    due: list[HeadquartersEvidenceRefRead] = Field(default_factory=list)
    impact: list[HeadquartersEvidenceRefRead] = Field(default_factory=list)
    severity: list[HeadquartersEvidenceRefRead] = Field(default_factory=list)
    confidence: list[HeadquartersEvidenceRefRead] = Field(default_factory=list)


class HeadquartersMissionRead(StrictReadModel):
    id: str
    kind: Literal[
        "review_proposal",
        "source_attention",
        "review_world",
        "connect_source",
        "create_briefing",
    ]
    reference_type: Literal["proposal", "source", "world", "setup"]
    reference_id: str
    title: str
    summary: str
    why_now: str
    status: str
    severity: Literal["critical", "high", "medium", "low", "info", "unknown"]
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    confidence_precision: Literal["exact", "unavailable"]
    due_at: datetime | None = None
    impact: str | None = None
    next_step: str
    owner_person_ids: list[UUID] = Field(default_factory=list)
    organization_id: UUID | None = None
    primary_person_id: UUID | None = None
    source_keys: list[str] = Field(default_factory=list)
    evidence_refs: list[HeadquartersEvidenceRefRead] = Field(default_factory=list)
    proposal_id: UUID | None = None
    proposal_version: str | None = None
    evidence_state: Literal["verified", "aggregate"]
    trust_class: Literal["verified_canonical", "aggregate"]
    ranking_reason: Literal[
        "verified_proposal",
        "configured_source_attention",
        "evidence_backed_relationship",
        "source_setup_gap",
        "briefing_setup_gap",
    ]
    fact_provenance: HeadquartersFactProvenanceRead
    action: HeadquartersActionRead
    correlation_reason: str | None = None
    correlation_rule_version: str | None = None

    @model_validator(mode="after")
    def validate_confidence_precision(self) -> HeadquartersMissionRead:
        if self.confidence is None and self.confidence_precision != "unavailable":
            raise ValueError("missing confidence must be unavailable")
        if self.confidence is not None and self.confidence_precision != "exact":
            raise ValueError("present confidence must be exact")
        return self


class HeadquartersPulseMetricRead(StrictReadModel):
    key: Literal[
        "waiting_decisions",
        "sources_attention",
        "pending_relationships",
    ]
    label: str
    value: int | None = Field(default=None, ge=0)
    precision: Literal["exact", "at_least", "unavailable"]
    empty_state: str
    target: str
    action: HeadquartersActionRead

    @field_validator("target")
    @classmethod
    def validate_safe_target(cls, value: str) -> str:
        return _validate_internal_target(value)

    @model_validator(mode="after")
    def validate_precision_value(self) -> HeadquartersPulseMetricRead:
        if self.precision == "unavailable" and self.value is not None:
            raise ValueError("unavailable metric cannot have a value")
        if self.precision != "unavailable" and self.value is None:
            raise ValueError("available metric requires a value")
        return self


class HeadquartersSourceHealthRead(StrictReadModel):
    key: Literal["github", "jira", "gmail", "drive"]
    name: str
    configuration: Literal["disconnected", "configured"]
    read: Literal["idle", "running", "succeeded", "failed"]
    data: Literal["empty", "available", "partial"]
    freshness: Literal["fresh", "stale", "unknown"]
    primary_state: Literal["failed", "partial", "stale", "no_data", "healthy", "setup"]
    attention_reason: str | None = None
    scopes: list[str] = Field(default_factory=list)
    last_success_at: datetime | None = None
    last_attempt_at: datetime | None = None
    last_data_observed_at: datetime | None = None
    fresh_until: datetime | None = None
    freshness_policy_version: Literal["source-health.v1"]
    connection_count: int = Field(ge=0)
    connection_count_precision: Literal["exact"]
    record_count: int = Field(ge=0)
    record_count_precision: Literal["exact"]
    blocker: str | None = None
    safe_debug_id: str | None = None
    next_action: HeadquartersActionRead


class HeadquartersSourcesRead(StrictReadModel):
    healthy: int = Field(ge=0)
    total: int = Field(ge=0)
    configured_count: int = Field(ge=0)
    data_ready_count: int = Field(ge=0)
    attention_count: int = Field(ge=0)
    count_precision: Literal["exact"]
    items: list[HeadquartersSourceHealthRead] = Field(default_factory=list)


class HeadquartersChangeItemRead(StrictReadModel):
    id: str
    kind: Literal["proposal", "source", "relationship"]
    title: str
    summary: str
    occurred_at: datetime | None = None
    source_keys: list[str] = Field(default_factory=list)
    evidence_refs: list[HeadquartersEvidenceRefRead] = Field(default_factory=list)
    target: str

    @field_validator("target")
    @classmethod
    def validate_safe_target(cls, value: str) -> str:
        return _validate_internal_target(value)


class HeadquartersChangesRead(StrictReadModel):
    items: list[HeadquartersChangeItemRead] = Field(default_factory=list, max_length=3)
    basis: Literal["current_snapshot"]
    cursor: None = None
    since_checkpoint: Literal[False]


class HeadquartersCapabilitySetRead(StrictReadModel):
    can_manage_team: bool
    can_manage_source: bool
    can_import_source: bool
    can_start_source_read: bool
    can_generate_briefing: bool
    can_create_proposal: bool
    can_review_proposal: bool
    can_execute_external: bool
    can_resolve_world: bool
    can_acknowledge_changes: bool


class HeadquartersOnboardingEvidenceFactRead(StrictReadModel):
    key: str
    label: str
    state: Literal["complete", "pending", "unknown"]
    value: int | None = Field(default=None, ge=0)
    precision: Literal["exact", "unavailable"]

    @model_validator(mode="after")
    def validate_precision(self) -> HeadquartersOnboardingEvidenceFactRead:
        if self.precision == "unavailable":
            if self.value is not None or self.state != "unknown":
                raise ValueError("unavailable onboarding evidence must be unknown")
        elif self.value is None or self.state == "unknown":
            raise ValueError("exact onboarding evidence requires a known value and state")
        return self


class HeadquartersOnboardingStepRead(StrictReadModel):
    key: Literal[
        "company",
        "source",
        "canonical_data",
        "context",
        "headquarters",
    ]
    state: Literal["complete", "pending", "unknown"]
    requirement: Literal["required", "recommended"]
    label: str
    benefit: str
    evidence: list[HeadquartersOnboardingEvidenceFactRead] = Field(min_length=1)
    action: HeadquartersActionRead

    @model_validator(mode="after")
    def validate_state_from_evidence(self) -> HeadquartersOnboardingStepRead:
        evidence_states = {fact.state for fact in self.evidence}
        expected_state = (
            "complete"
            if "complete" in evidence_states
            else "unknown"
            if "unknown" in evidence_states
            else "pending"
        )
        if self.state != expected_state:
            raise ValueError("onboarding step state must match its evidence")
        return self


class HeadquartersOnboardingRead(StrictReadModel):
    contract_version: Literal[HEADQUARTERS_ONBOARDING_CONTRACT_VERSION]
    readiness_version: Literal[HEADQUARTERS_ONBOARDING_READINESS_VERSION]
    ready: bool
    completed_count: int = Field(ge=0)
    total_count: Literal[5]
    completed_required: int = Field(ge=0)
    required_total: Literal[3]
    current_step_key: (
        Literal[
            "company",
            "source",
            "canonical_data",
            "context",
            "headquarters",
        ]
        | None
    ) = None
    steps: list[HeadquartersOnboardingStepRead] = Field(min_length=5, max_length=5)
    next_action: HeadquartersActionRead | None = None

    @model_validator(mode="after")
    def validate_readiness(self) -> HeadquartersOnboardingRead:
        expected_keys = [
            "company",
            "source",
            "canonical_data",
            "context",
            "headquarters",
        ]
        expected_requirements = {
            "company": "required",
            "source": "recommended",
            "canonical_data": "required",
            "context": "recommended",
            "headquarters": "required",
        }
        if [step.key for step in self.steps] != expected_keys:
            raise ValueError("onboarding must contain the five v1 steps in order")
        if any(step.requirement != expected_requirements[step.key] for step in self.steps):
            raise ValueError("onboarding requirements must match readiness v1")

        required_steps = [step for step in self.steps if step.requirement == "required"]
        completed_count = sum(step.state == "complete" for step in self.steps)
        completed_required = sum(step.state == "complete" for step in required_steps)
        if self.completed_count != completed_count:
            raise ValueError("completed_count must match onboarding steps")
        if self.completed_required != completed_required:
            raise ValueError("completed_required must match required onboarding steps")
        if self.ready != (completed_required == self.required_total):
            raise ValueError("ready must match required onboarding steps")

        current_step = next(
            (step for step in required_steps if step.state != "complete"),
            None,
        )
        expected_current_key = current_step.key if current_step is not None else None
        if self.current_step_key != expected_current_key:
            raise ValueError("current_step_key must be the first incomplete required step")
        if current_step is None:
            if self.next_action is not None:
                raise ValueError("ready onboarding cannot have next_action")
        elif self.next_action != current_step.action:
            raise ValueError("next_action must match the current required step")
        return self


class HeadquartersCoverageRead(StrictReadModel):
    key: Literal["identity", "sources", "decisions", "company_world"]
    status: Literal["complete", "partial", "unavailable"]
    watermark: str
    warning: str | None = None

    @model_validator(mode="after")
    def validate_warning(self) -> HeadquartersCoverageRead:
        if self.status == "complete" and self.warning is not None:
            raise ValueError("complete coverage cannot have a warning")
        if self.status != "complete" and not self.warning:
            raise ValueError("non-complete coverage requires a warning")
        return self


class HeadquartersSnapshotMetaRead(StrictReadModel):
    id: str
    as_of: datetime
    partial: bool
    warnings: list[str] = Field(default_factory=list)
    coverage: list[HeadquartersCoverageRead] = Field(default_factory=list)


class HeadquartersWorkspaceRead(StrictReadModel):
    id: UUID
    name: str
    role: Literal["owner", "admin", "member", "viewer"]


class HeadquartersBoundaryRead(StrictReadModel):
    provider_calls: Literal[False]
    external_writes: Literal[False]
    llm: Literal[False]
    reads_secrets: Literal[False]
    transaction: Literal["repeatable_read_read_only"]


class HeadquartersSnapshotResponse(StrictReadModel):
    contract_version: Literal[HEADQUARTERS_CONTRACT_VERSION]
    ranking_version: Literal[HEADQUARTERS_RANKING_VERSION]
    snapshot: HeadquartersSnapshotMetaRead
    workspace: HeadquartersWorkspaceRead
    onboarding: HeadquartersOnboardingRead
    sources: HeadquartersSourcesRead
    priority: HeadquartersMissionRead | None = None
    pulse: list[HeadquartersPulseMetricRead] = Field(min_length=3, max_length=3)
    queue: list[HeadquartersMissionRead] = Field(default_factory=list, max_length=2)
    changes: HeadquartersChangesRead
    capabilities: HeadquartersCapabilitySetRead
    boundary: HeadquartersBoundaryRead

    @model_validator(mode="after")
    def validate_snapshot_invariants(self) -> HeadquartersSnapshotResponse:
        expected_pulse = [
            "waiting_decisions",
            "sources_attention",
            "pending_relationships",
        ]
        expected_coverage = ["identity", "sources", "decisions", "company_world"]
        if [metric.key for metric in self.pulse] != expected_pulse:
            raise ValueError("pulse must contain the three v1 metrics in order")
        if [item.key for item in self.snapshot.coverage] != expected_coverage:
            raise ValueError("coverage must contain the four v1 sections in order")
        if self.priority and any(item.id == self.priority.id for item in self.queue):
            raise ValueError("priority cannot be duplicated in queue")
        if self.snapshot.partial != any(
            item.status != "complete" for item in self.snapshot.coverage
        ):
            raise ValueError("snapshot.partial must match coverage")
        return self


class HeadquartersOnboardingResponse(StrictReadModel):
    contract_version: Literal[HEADQUARTERS_CONTRACT_VERSION]
    snapshot: HeadquartersSnapshotMetaRead
    workspace: HeadquartersWorkspaceRead
    onboarding: HeadquartersOnboardingRead
    capabilities: HeadquartersCapabilitySetRead
    boundary: HeadquartersBoundaryRead


def _validate_internal_target(value: str) -> str:
    if (
        not value.startswith("/")
        or value.startswith("//")
        or "\\" in value
        or any(
            character.isspace() or ord(character) < 32 or ord(character) == 127
            for character in value
        )
    ):
        raise ValueError("action target must be a safe internal path")
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or not parsed.path.startswith("/"):
        raise ValueError("action target must be a safe internal path")
    return value


def _validate_external_evidence_target(value: str) -> str:
    if sanitize_headquarters_evidence_url(value) != value:
        raise ValueError("evidence target must be a safe internal path or web URL")
    return value


@router.get("", response_model=HeadquartersSnapshotResponse)
async def get_workspace_headquarters(
    workspace_id: UUID,
    response: Response,
    access: WorkspaceAccess = Depends(require_workspace_access),
) -> HeadquartersSnapshotResponse:
    try:
        payload = await read_workspace_headquarters(
            workspace_id=workspace_id,
            user_id=access.workspace_membership.user.id,
        )
    except HeadquartersAccessChangedError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="workspace not found",
            headers={"Cache-Control": "private, no-store"},
        ) from exc

    result = HeadquartersSnapshotResponse.model_validate(payload)
    response.headers["ETag"] = f'"{result.snapshot.id}"'
    response.headers["Cache-Control"] = "private, no-store"
    return result


@router.get("/onboarding", response_model=HeadquartersOnboardingResponse)
async def get_workspace_headquarters_onboarding(
    workspace_id: UUID,
    response: Response,
    access: WorkspaceAccess = Depends(require_workspace_access),
) -> HeadquartersOnboardingResponse:
    try:
        payload = await read_workspace_headquarters(
            workspace_id=workspace_id,
            user_id=access.workspace_membership.user.id,
        )
    except HeadquartersAccessChangedError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="workspace not found",
            headers={"Cache-Control": "private, no-store"},
        ) from exc

    snapshot = HeadquartersSnapshotResponse.model_validate(payload)
    result = HeadquartersOnboardingResponse.model_validate(
        {
            "contract_version": snapshot.contract_version,
            "snapshot": snapshot.snapshot,
            "workspace": snapshot.workspace,
            "onboarding": snapshot.onboarding,
            "capabilities": snapshot.capabilities,
            "boundary": snapshot.boundary,
        }
    )
    response.headers["ETag"] = f'"{result.snapshot.id}"'
    response.headers["Cache-Control"] = "private, no-store"
    return result
