export type OperatorConfig = {
  apiBaseUrl: string;
  apiKey: string;
  ownerEmail: string;
  workspaceId: string;
};

export type ApiErrorPayload = {
  detail?: string;
  message?: string;
};

export type ApiFetchOptions = RequestInit & {
  apiBaseUrl?: string | null;
  apiKey?: string | null;
  includeOwnerEmail?: boolean;
  ownerEmail?: string | null;
};

export type GitHubOperationalWorkState = "open" | "closed" | "merged" | "all";

export type CompanyBrainSourceRef = {
  id: string;
  kind: string;
  source: string;
  label: string;
  url: string | null;
  record_type: string;
  record_id: string;
};

export type CompanyBrainSummary = {
  repositories: number;
  open_issues: number;
  open_pull_requests: number;
  closed_issues: number;
  merged_pull_requests: number;
};

export type CompanyBrainRepository = {
  id: string;
  provider: "github";
  external_id: string;
  name: string;
  full_name: string;
  visibility: string | null;
  archived: boolean;
  source_url: string | null;
  last_activity_at: string | null;
  source_refs: CompanyBrainSourceRef[];
};

export type CompanyBrainWorkItem = {
  id: string;
  type: "issue" | "pull_request";
  external_id: string | null;
  number: number | null;
  title: string;
  state: string | null;
  repository_full_name: string | null;
  repository_external_id: string | null;
  source_url: string | null;
  updated_at: string | null;
  source_refs: CompanyBrainSourceRef[];
};

export type CompanyBrainResponse = {
  workspace_id: string;
  mode: "github_first_canonical";
  source: "canonical_github_company_brain";
  summary: CompanyBrainSummary;
  repositories: CompanyBrainRepository[];
  work: {
    issues: CompanyBrainWorkItem[];
    pull_requests: CompanyBrainWorkItem[];
    recent: CompanyBrainWorkItem[];
  };
  evidence: CompanyBrainSourceRef[];
  capabilities: {
    live_github_oauth: boolean;
    live_provider_sync: boolean;
    local_sync: boolean;
    llm_briefing: boolean;
  };
  is_live: boolean;
  llm_used: boolean;
  warnings: string[];
};

export type FounderBriefingRequest = {
  focus?: string[];
  include_github?: boolean;
  include_connections?: boolean;
  include_sync_jobs?: boolean;
  include_repository_inventory?: boolean;
  limit?: number;
};

export type BriefingEvidenceRef = {
  kind: string;
  source: string;
  ref: string;
  url: string | null;
};

export type FounderBriefingItem = {
  id: string;
  category: string;
  title: string;
  summary: string;
  severity: string;
  confidence: number;
  evidence_refs: BriefingEvidenceRef[];
  related_entities: string[];
  recommended_next_step: string | null;
  warnings: string[];
};

export type FounderBriefingResponse = {
  briefing: {
    title: string;
    summary: string;
    generated_at: string;
    workspace_id: string;
    is_live: boolean;
    llm_used: boolean;
    persistence: "transient" | string;
    items: FounderBriefingItem[];
    signals: {
      github: {
        connection_status: string;
        repository_count: number;
        queued_sync_jobs: number;
        latest_sync_job_status: string | null;
      };
    };
    warnings: string[];
  };
};

export type ActionProposalStatus =
  | "approved"
  | "executed"
  | "failed"
  | "proposed"
  | "rejected";

export type ActionTargetProvider = "github" | "internal";

export type ActionProposalType = "create_github_issue" | "internal_todo";

export type ActionProposalEvidenceRef = BriefingEvidenceRef;

export type ActionProposalCreateRequest = {
  briefing_item_id?: string | null;
  target_provider: ActionTargetProvider;
  action_type: ActionProposalType;
  title: string;
  description?: string | null;
  payload?: Record<string, unknown>;
  evidence_refs?: ActionProposalEvidenceRef[];
  created_by?: "ai" | "system" | "user";
};

export type ActionProposal = {
  id: string;
  workspace_id: string;
  briefing_item_id: string | null;
  target_provider: ActionTargetProvider | string;
  action_type: ActionProposalType | string;
  title: string;
  description: string | null;
  payload: Record<string, unknown>;
  status: ActionProposalStatus | string;
  evidence_refs: ActionProposalEvidenceRef[];
  created_by: string;
  created_by_user_id: string | null;
  approved_by_user_id: string | null;
  approved_at: string | null;
  rejected_by_user_id: string | null;
  rejected_at: string | null;
  rejection_reason: string | null;
  created_at: string;
  updated_at: string;
  is_live: boolean;
  execution_started: boolean;
  warnings: string[];
};

export type ActionProposalListRequest = {
  status?: ActionProposalStatus | string;
  target_provider?: ActionTargetProvider | string;
  action_type?: ActionProposalType | string;
  limit?: number;
};

export type ActionProposalListResponse = {
  proposals: ActionProposal[];
  count: number;
  is_live: boolean;
  warnings: string[];
};

export type ActionProposalMutationResponse = {
  proposal: ActionProposal;
  is_live: boolean;
  execution_started: boolean;
  warnings: string[];
};

export type ActionProposalRejectRequest = {
  reason?: string | null;
};

export type ActionExecutionPreviewStatus =
  | "blocked"
  | "executed"
  | "failed"
  | "not_approved"
  | "preview_ready"
  | "unsupported";

export type ActionExecutionMode = "dry_run" | "external_disabled" | "external_write";

export type ActionExecutionCapabilities = {
  dry_run: boolean;
  local_approval: boolean;
  external_execution: boolean;
  live_provider_write: boolean;
  requires_confirmation: boolean;
};

export type GitHubIssueExecutionPreview = {
  provider: string;
  action: string;
  repository: string;
  title: string;
  body: string | null;
  labels: string[];
  assignees: string[];
  evidence_refs: ActionProposalEvidenceRef[];
};

export type ActionExecutionAuditEvent = {
  id: string;
  event: string;
  actor: string;
  created_at: string;
  message: string;
};

export type ActionExecutionPreviewResponse = {
  workspace_id: string;
  proposal_id: string;
  status: ActionExecutionPreviewStatus | string;
  mode: ActionExecutionMode | string;
  message: string;
  capabilities: ActionExecutionCapabilities;
  preview: GitHubIssueExecutionPreview | null;
  audit: ActionExecutionAuditEvent[];
  warnings: string[];
};

export type ActionProposalExecuteRequest = {
  connection_id: string;
  confirm_external_write: boolean;
  idempotency_key?: string | null;
};

export type ActionExecutionResponse = {
  proposal: {
    id: string;
    status: string;
  };
  execution: {
    id: string;
    status: string;
    external_id: string | null;
    provider_response: Record<string, unknown>;
    error_message: string | null;
    started_at: string;
    finished_at: string | null;
  };
  is_live: boolean;
  external_write_performed: boolean;
  provider: string;
  warnings: string[];
};

export type GitHubConnectionStatusResponse = {
  provider: string;
  status: string;
  connection_id: string | null;
  display_name: string | null;
  last_sync_at: string | null;
  last_error: string | null;
  has_connection_record: boolean;
  has_valid_token_record: boolean;
  repository_read_available: boolean;
  repository_read_source: string;
  is_live: boolean;
  warnings: string[];
};

export type GitHubLocalSyncRequest = {
  include_repositories?: boolean;
  include_issues?: boolean;
  include_pull_requests?: boolean;
};

export type GitHubLocalSyncResponse = {
  sync_job: {
    id: string;
    status: string;
    records_seen: number;
    records_created: number;
    records_updated: number;
    started_at: string | null;
    finished_at: string | null;
  };
  counts: {
    repositories: number;
    issues: number;
    pull_requests: number;
  };
  status: string;
  message: string;
  capability_mode: string;
  is_live: boolean;
  provider_sync_started: boolean;
  local_normalization_performed: boolean;
  persistence_mode: string;
  warnings: string[];
};

export type GitHubOperationalIssue = {
  id: string;
  external_id: string | null;
  number: number | null;
  title: string;
  state: string | null;
  source_url: string | null;
  repository_full_name: string | null;
  repository_external_id: string | null;
  source_record_id: string | null;
  source_updated_at: string | null;
  metadata: Record<string, unknown>;
};

export type GitHubOperationalPullRequest = {
  id: string;
  external_id: string;
  number: number;
  title: string;
  state: string;
  source_url: string | null;
  repository_id: string;
  repository_full_name: string | null;
  repository_external_id: string | null;
  created_at_source: string | null;
  updated_at_source: string | null;
  merged_at_source: string | null;
  metadata: Record<string, unknown>;
};

export type GitHubOperationalWorkResponse = {
  issues: GitHubOperationalIssue[];
  pull_requests: GitHubOperationalPullRequest[];
  counts: {
    issues: number;
    pull_requests: number;
  };
  state: GitHubOperationalWorkState;
  source: string;
  is_live: boolean;
  warnings: string[];
};
