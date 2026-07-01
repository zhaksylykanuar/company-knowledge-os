export type ApiErrorPayload = {
  detail?: string;
  message?: string;
};

// Auth is the first-party session cookie; no operator key / owner email / base
// URL is carried in request options anymore.
export type ApiFetchOptions = RequestInit;

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

export type BriefingGitHubSignals = {
  connection_status: string;
  repository_count: number;
  queued_sync_jobs: number;
  latest_sync_job_status: string | null;
};

export type FounderBriefingResponse = {
  briefing: {
    id: string;
    workspace_id: string;
    created_at: string;
    generated_at: string;
    generated_by: string;
    title: string;
    summary: string;
    is_live: boolean;
    llm_used: boolean;
    persistence: string;
    items: FounderBriefingItem[];
    signals: {
      github: BriefingGitHubSignals;
    };
    warnings: string[];
  };
};

export type BriefingSummary = {
  id: string;
  created_at: string;
  generated_at: string;
  generated_by: string;
  title: string;
  summary: string;
  item_count: number;
  signals: {
    github: BriefingGitHubSignals;
  };
};

export type BriefingListResponse = {
  briefings: BriefingSummary[];
  count: number;
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
  event_type: string;
  event: string;
  actor: string;
  status: string;
  created_at: string;
  message: string;
  event_metadata: Record<string, unknown>;
  provider: string | null;
  action: string | null;
  external_execution_enabled: boolean;
  confirmation_received: boolean;
  external_result_id: string | null;
  external_result_url: string | null;
  error_code: string | null;
  error_message: string | null;
};

export type ActionExecutionReceipt = {
  provider: string | null;
  action: string | null;
  status: string | null;
  external_execution_enabled: boolean;
  confirmation_received: boolean;
  external_result_id: string | null;
  external_result_url: string | null;
  external_write_performed: boolean;
  provider_result: string;
  error_code: string | null;
  error_message: string | null;
  idempotency_key: string | null;
  created_at: string | null;
  updated_at: string | null;
};

export type ActionProposalAuditResponse = {
  workspace_id: string;
  proposal_id: string;
  events: ActionExecutionAuditEvent[];
  receipt: ActionExecutionReceipt;
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
  receipt: ActionExecutionReceipt;
  is_live: boolean;
  external_write_performed: boolean;
  provider: string;
  warnings: string[];
};

export type GitHubAppConfigStatus = {
  configured: boolean;
  app_id_configured: boolean;
  app_slug: string | null;
  private_key_configured: boolean;
  private_key_source: string | null;
  webhook_secret_configured: boolean;
  setup_url: string | null;
  callback_url: string | null;
  missing_env: string[];
  installation_tokens_persisted: boolean;
  provider_writes_enabled: boolean;
};

export type GitHubConnectionStatusResponse = {
  provider: string;
  status: string;
  connection_method: string | null;
  connection_id: string | null;
  display_name: string | null;
  last_sync_at: string | null;
  last_error: string | null;
  has_connection_record: boolean;
  has_valid_token_record: boolean;
  repository_read_available: boolean;
  repository_read_source: string;
  is_live: boolean;
  app: GitHubAppConfigStatus;
  warnings: string[];
};

export type GitHubRepositoryRead = {
  id: string;
  name: string;
  full_name: string;
  default_branch: string | null;
  visibility: string;
  archived: boolean;
  source_url: string | null;
  last_activity_at: string | null;
  source: string;
  evidence_refs: BriefingEvidenceRef[];
  metadata: Record<string, unknown>;
};

export type GitHubRepositoryListResponse = {
  repositories: GitHubRepositoryRead[];
  count: number;
  source: string;
  is_live: boolean;
  warnings: string[];
};

export type GitHubAppLiveSyncRequest = {
  connection_id: string;
  repositories: string[];
  include_issues?: boolean;
  include_pull_requests?: boolean;
  issue_states?: ("open" | "closed" | "all")[];
  pull_request_states?: ("open" | "closed" | "merged" | "all")[];
};

export type GitHubAppLiveSyncResponse = {
  workspace_id: string;
  connection_id: string;
  installation_id: string;
  repositories: {
    full_name: string;
    synced_issues: number;
    synced_pull_requests: number;
    skipped_pull_requests: number;
  }[];
  totals: {
    repositories: number;
    issues: number;
    pull_requests: number;
    skipped_pull_requests: number;
  };
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
  capabilities: {
    read_only_sync: boolean;
    external_writes: boolean;
    installation_access_token_persisted: boolean;
  };
  is_live: boolean;
  provider_sync_started: boolean;
  local_normalization_performed: boolean;
  external_write_performed: boolean;
  persistence_mode: string;
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

export type GitHubSelectedIssueSyncState = "open" | "closed" | "all";

export type GitHubSelectedPullRequestSyncState =
  | "open"
  | "closed"
  | "merged"
  | "all";

export type GitHubSelectedIssueSyncRequest = {
  connection_id: string;
  repositories: string[];
  states?: GitHubSelectedIssueSyncState[];
};

export type GitHubSelectedPullRequestSyncRequest = {
  connection_id: string;
  repositories: string[];
  states?: GitHubSelectedPullRequestSyncState[];
};

export type GitHubSelectedSyncCapabilities = {
  read_only_sync: boolean;
  external_writes: boolean;
};

export type GitHubSelectedSyncJob = {
  id: string;
  status: string;
  records_seen: number;
  records_created: number;
  records_updated: number;
  started_at: string | null;
  finished_at: string | null;
};

export type GitHubSelectedSyncCounts = {
  repositories: number;
  issues: number;
  pull_requests: number;
};

export type GitHubSelectedIssueSyncRepositorySummary = {
  full_name: string;
  synced_issues: number;
  open_issues: number;
  closed_issues: number;
  skipped_pull_requests: number;
};

export type GitHubSelectedIssueSyncTotals = {
  repositories: number;
  issues: number;
  open_issues: number;
  closed_issues: number;
  skipped_pull_requests: number;
};

export type GitHubSelectedIssueSyncResponse = {
  workspace_id: string;
  repositories: GitHubSelectedIssueSyncRepositorySummary[];
  totals: GitHubSelectedIssueSyncTotals;
  sync_job: GitHubSelectedSyncJob;
  counts: GitHubSelectedSyncCounts;
  capabilities: GitHubSelectedSyncCapabilities;
  is_live: boolean;
  provider_sync_started: boolean;
  external_write_performed: boolean;
  warnings: string[];
};

export type GitHubSelectedPullRequestSyncRepositorySummary = {
  full_name: string;
  synced_pull_requests: number;
  open_pull_requests: number;
  closed_pull_requests: number;
  merged_pull_requests: number;
};

export type GitHubSelectedPullRequestSyncTotals = {
  repositories: number;
  pull_requests: number;
  open_pull_requests: number;
  closed_pull_requests: number;
  merged_pull_requests: number;
};

export type GitHubSelectedPullRequestSyncResponse = {
  workspace_id: string;
  repositories: GitHubSelectedPullRequestSyncRepositorySummary[];
  totals: GitHubSelectedPullRequestSyncTotals;
  sync_job: GitHubSelectedSyncJob;
  counts: GitHubSelectedSyncCounts;
  capabilities: GitHubSelectedSyncCapabilities;
  is_live: boolean;
  provider_sync_started: boolean;
  external_write_performed: boolean;
  warnings: string[];
};

export type GitHubSelectedRepositorySyncResult = {
  issues: GitHubSelectedIssueSyncResponse | null;
  pull_requests: GitHubSelectedPullRequestSyncResponse | null;
};
