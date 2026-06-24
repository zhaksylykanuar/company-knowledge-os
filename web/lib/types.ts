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
