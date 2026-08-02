from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ActionProposalCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    briefing_item_id: UUID | None = None
    target_provider: str = Field(max_length=40)
    action_type: str = Field(max_length=80)
    title: str = Field(min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=5000)
    payload: dict[str, Any] = Field(default_factory=dict)
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list, max_length=50)
    # Public callers can create only user-originated proposals. System/AI
    # provenance is reserved for reviewed internal services and must never be
    # caller-upgradable.
    created_by: Literal["user"] = "user"


class ActionProposalDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    idempotency_key: str = Field(min_length=8, max_length=255)
    proposal_version: str = Field(pattern=r"^ap1_[0-9a-f]{64}$")
    expected_snapshot_id: str | None = Field(
        default=None,
        pattern=r"^hqs1_[0-9a-f]{64}$",
    )


class ActionProposalApproveRequest(ActionProposalDecisionRequest):
    pass


class ActionProposalRejectRequest(ActionProposalDecisionRequest):
    reason: str | None = Field(default=None, max_length=1000)


class ActionProposalBulkDecisionItem(ActionProposalDecisionRequest):
    proposal_id: UUID


class ActionProposalBulkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decisions: list[ActionProposalBulkDecisionItem] = Field(
        min_length=1,
        max_length=100,
    )

    @model_validator(mode="after")
    def reject_duplicate_proposals(self) -> Self:
        proposal_ids = [item.proposal_id for item in self.decisions]
        if len(set(proposal_ids)) != len(proposal_ids):
            raise ValueError("bulk decisions must contain unique proposal_ids")
        return self


class ActionProposalBulkRejectRequest(ActionProposalBulkRequest):
    reason: str | None = Field(default=None, max_length=1000)


class RepoAuditImportFinding(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    repository_full_name: str = Field(default="", max_length=160)
    title: str | None = Field(default=None, max_length=500)
    summary: str = Field(default="External audit finding.", max_length=2000)
    severity: str | None = Field(default=None, max_length=40)
    risks: list[str] = Field(default_factory=list, max_length=20)
    evidence_refs: list[str] = Field(default_factory=list, max_length=50)
    recommended_next_step: str | None = Field(default=None, max_length=1000)
    area_candidate: str | None = Field(default=None, max_length=80)


class RepoAuditImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    findings: list[RepoAuditImportFinding] = Field(min_length=1, max_length=50)


class ActionProposalExecuteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    connection_id: UUID
    confirm_external_write: bool = False
    idempotency_key: str = Field(min_length=8, max_length=255)


class ActionProposalExecutionResultSyncRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connection_id: UUID | None = None


class ActionProposalRead(BaseModel):
    id: UUID
    workspace_id: UUID
    briefing_item_id: UUID | None = None
    target_provider: str
    action_type: str
    title: str
    description: str | None = None
    payload: dict[str, Any]
    status: str
    evidence_refs: list[dict[str, Any]]
    created_by: str
    created_by_user_id: UUID | None = None
    approved_by_user_id: UUID | None = None
    approved_at: datetime | None = None
    rejected_by_user_id: UUID | None = None
    rejected_at: datetime | None = None
    rejection_reason: str | None = None
    created_at: datetime
    updated_at: datetime
    proposal_version: str
    is_live: bool
    execution_started: bool
    warnings: list[str] = Field(default_factory=list)


class ActionProposalListResponse(BaseModel):
    proposals: list[ActionProposalRead]
    count: int
    is_live: bool
    warnings: list[str] = Field(default_factory=list)


class ActionProposalMutationResponse(BaseModel):
    proposal: ActionProposalRead
    is_live: bool
    execution_started: bool
    warnings: list[str] = Field(default_factory=list)


class ActionProposalDecisionReceiptRead(BaseModel):
    receipt_id: UUID
    proposal_id: UUID
    decision: Literal["approved", "rejected"]
    recorded_at: datetime
    replayed: bool
    external_write_performed: Literal[False]
    proposal_version: str


class ActionProposalDecisionResponse(BaseModel):
    proposal: ActionProposalRead
    decision_receipt: ActionProposalDecisionReceiptRead
    is_live: Literal[False]
    execution_started: Literal[False]
    warnings: list[str] = Field(default_factory=list)


class ActionProposalBulkFailureRead(BaseModel):
    proposal_id: UUID
    status_code: int
    detail: str


class ActionProposalBulkResponse(BaseModel):
    proposals: list[ActionProposalRead]
    decision_receipts: list[ActionProposalDecisionReceiptRead]
    failures: list[ActionProposalBulkFailureRead]
    succeeded_count: int
    failed_count: int
    is_live: bool
    execution_started: bool
    warnings: list[str] = Field(default_factory=list)


class RepoAuditImportFailureRead(BaseModel):
    index: int
    repository_full_name: str | None = None
    status_code: int
    detail: str


class RepoAuditImportResponse(BaseModel):
    proposals: list[ActionProposalRead]
    failures: list[RepoAuditImportFailureRead]
    succeeded_count: int
    failed_count: int
    is_live: bool
    execution_started: bool
    warnings: list[str] = Field(default_factory=list)


class ExecutedActionProposalRead(BaseModel):
    id: UUID
    status: str


class ActionExecutionRead(BaseModel):
    id: UUID
    status: str
    workspace_id: UUID
    requested_by_user_id: UUID | None = None
    connection_id: UUID | None = None
    client_idempotency_key: str
    request_hash: str
    external_id: str | None = None
    provider_response: dict[str, Any]
    error_message: str | None = None
    claimed_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    reconciled_at: datetime | None = None


class ActionExecutionReceiptRead(BaseModel):
    provider: str | None = None
    action: str | None = None
    status: str | None = None
    external_execution_enabled: bool = False
    confirmation_received: bool = False
    external_result_id: str | None = None
    external_result_url: str | None = None
    external_write_performed: bool = False
    provider_result: str = "none"
    error_code: str | None = None
    error_message: str | None = None
    idempotency_key: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ActionExecutionResponse(BaseModel):
    proposal: ExecutedActionProposalRead
    execution: ActionExecutionRead
    receipt: ActionExecutionReceiptRead
    is_live: bool
    external_write_performed: bool
    provider: str
    warnings: list[str] = Field(default_factory=list)


class ActionExecutionCapabilitiesRead(BaseModel):
    dry_run: bool
    local_approval: bool
    external_execution: bool
    live_provider_write: bool
    requires_confirmation: bool


class GitHubIssueExecutionPreviewRead(BaseModel):
    provider: str
    action: str
    repository: str
    title: str
    body: str | None = None
    labels: list[str] = Field(default_factory=list)
    assignees: list[str] = Field(default_factory=list)
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)


class ActionExecutionAuditEventRead(BaseModel):
    id: UUID
    event_type: str
    event: str
    actor: str
    status: str
    created_at: datetime
    message: str
    event_metadata: dict[str, Any] = Field(default_factory=dict)
    provider: str | None = None
    action: str | None = None
    external_execution_enabled: bool = False
    confirmation_received: bool = False
    external_result_id: str | None = None
    external_result_url: str | None = None
    error_code: str | None = None
    error_message: str | None = None


class ActionExecutionPreviewResponse(BaseModel):
    workspace_id: UUID
    proposal_id: UUID
    status: str
    mode: str
    message: str
    capabilities: ActionExecutionCapabilitiesRead
    preview: GitHubIssueExecutionPreviewRead | None = None
    audit: list[ActionExecutionAuditEventRead] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ActionExecutionAuditResponse(BaseModel):
    workspace_id: UUID
    proposal_id: UUID
    events: list[ActionExecutionAuditEventRead]
    receipt: ActionExecutionReceiptRead


class ActionExecutionResultSyncIssueRead(BaseModel):
    number: int | None = None
    state: str | None = None
    title: str | None = None


class ActionExecutionResultSyncJobRead(BaseModel):
    id: UUID
    status: str
    records_seen: int
    records_created: int
    records_updated: int


class ActionExecutionResultCanonicalRead(BaseModel):
    task_id: UUID | None = None
    source_record_id: UUID | None = None
    external_id: str | None = None
    evidence_refs_count: int = 0


class ActionExecutionResultSyncResponse(BaseModel):
    workspace_id: UUID
    proposal_id: UUID
    synced: bool
    status: str
    provider: str
    action: str
    repository: str
    issue: ActionExecutionResultSyncIssueRead
    sync_job: ActionExecutionResultSyncJobRead | None = None
    canonical: ActionExecutionResultCanonicalRead
    counts: dict[str, int] = Field(default_factory=dict)
    audit: list[ActionExecutionAuditEventRead] = Field(default_factory=list)
    retry_after: datetime | None = None
    warnings: list[str] = Field(default_factory=list)
