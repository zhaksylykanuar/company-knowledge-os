export type ApiErrorPayload = {
  detail?: string;
  message?: string;
};

// Auth is the first-party session cookie; no operator key / owner email / base
// URL is carried in request options anymore.
export type ApiFetchOptions = RequestInit;

export type WorkspaceMemberRole = "admin" | "member" | "owner" | "viewer";

export type WorkspaceMemberUser = {
  id: string;
  email: string;
  name: string | null;
  status: string;
};

export type WorkspaceMemberMembership = {
  id: string;
  workspace_id: string;
  user_id: string;
  role: WorkspaceMemberRole;
};

export type WorkspaceMember = {
  user: WorkspaceMemberUser;
  membership: WorkspaceMemberMembership;
};

export type WorkspaceMembersResponse = {
  members: WorkspaceMember[];
};

export type WorkspaceMemberProvisionRequest = {
  email: string;
  name?: string | null;
  role: Exclude<WorkspaceMemberRole, "owner">;
};

export type WorkspaceMemberProvisionResponse = {
  member: WorkspaceMember;
  external_invite_sent: boolean;
  provider_write_performed: boolean;
  login_credential_set: boolean;
  setup_link_generated: boolean;
  setup_url_path: string | null;
  setup_token_expires_at: string | null;
  warnings: string[];
};

export type ConnectorStatus = "available" | "planned";

export type Connector = {
  provider: string;
  name: string;
  status: ConnectorStatus;
  read_only: boolean;
  manage_path: string | null;
  summary: string;
  connection_count: number;
  connected_count: number;
  has_connection: boolean;
};

export type ConnectorRegistrySummary = {
  total: number;
  available: number;
  planned: number;
  connected: number;
};

export type ConnectorRegistryBoundary = {
  provider_calls: boolean;
  external_writes: boolean;
  llm: boolean;
  reads_secrets: boolean;
};

export type ConnectorRegistryResponse = {
  workspace_id: string;
  connectors: Connector[];
  summary: ConnectorRegistrySummary;
  boundary: ConnectorRegistryBoundary;
};


export type JiraEvidenceRef = {
  kind: string;
  source: string;
  ref: string;
  url: string | null;
};

export type JiraConnectorBoundary = {
  provider_calls: boolean;
  sync_started: boolean;
  external_writes: boolean;
  llm: boolean;
  reads_secrets: boolean;
};

export type JiraIssue = {
  task_id: string | null;
  source_record_id: string | null;
  key: string;
  title: string;
  status: string | null;
  status_category: string | null;
  priority: string | null;
  due_date: string | null;
  source_url: string | null;
  updated_at: string | null;
  project_key: string | null;
  issue_type: string | null;
  evidence_refs: JiraEvidenceRef[];
};

export type JiraIssueListCounts = {
  total: number;
  not_done: number;
  done: number;
};

export type JiraIssueListResponse = {
  workspace_id: string;
  issues: JiraIssue[];
  counts: JiraIssueListCounts;
  boundary: JiraConnectorBoundary;
  warnings: string[];
};

export type JiraIssueImportRequest = {
  issues: Record<string, unknown>[];
  connectionId?: string | null;
};

export type JiraIssueImportCounts = {
  received: number;
  imported: number;
  failed: number;
  source_records_created: number;
  source_records_updated: number;
  tasks_created: number;
  tasks_updated: number;
};

export type JiraIssueImportFailure = {
  index: number;
  reason: string;
};

export type JiraIssueImportResponse = {
  workspace_id: string;
  counts: JiraIssueImportCounts;
  issues: JiraIssue[];
  failures: JiraIssueImportFailure[];
  boundary: JiraConnectorBoundary;
  warnings: string[];
};

export type GmailEvidenceRef = {
  kind: string;
  source: string;
  ref: string;
  url: string | null;
};

export type GmailConnectorBoundary = {
  provider_calls: boolean;
  sync_started: boolean;
  external_writes: boolean;
  llm: boolean;
  reads_secrets: boolean;
};

export type GmailMessage = {
  source_record_id: string | null;
  message_id: string;
  thread_id: string | null;
  subject: string;
  snippet: string | null;
  from_address: string | null;
  to_addresses: string[];
  labels: string[];
  unread: boolean;
  received_at: string | null;
  source_url: string | null;
  evidence_refs: GmailEvidenceRef[];
};

export type GmailMessageListCounts = {
  total: number;
  unread: number;
  read: number;
};

export type GmailMessageListResponse = {
  workspace_id: string;
  messages: GmailMessage[];
  counts: GmailMessageListCounts;
  boundary: GmailConnectorBoundary;
  warnings: string[];
};

export type GmailMessageImportRequest = {
  messages: Record<string, unknown>[];
  connectionId?: string | null;
};

export type GmailMessageImportCounts = {
  received: number;
  imported: number;
  failed: number;
  source_records_created: number;
  source_records_updated: number;
};

export type GmailMessageImportFailure = {
  index: number;
  reason: string;
};

export type GmailMessageImportResponse = {
  workspace_id: string;
  counts: GmailMessageImportCounts;
  messages: GmailMessage[];
  failures: GmailMessageImportFailure[];
  boundary: GmailConnectorBoundary;
  warnings: string[];
};

export type DriveEvidenceRef = {
  kind: string;
  source: string;
  ref: string;
  url: string | null;
};

export type DriveConnectorBoundary = {
  provider_calls: boolean;
  sync_started: boolean;
  external_writes: boolean;
  llm: boolean;
  reads_secrets: boolean;
};

export type DriveFile = {
  source_record_id: string | null;
  file_id: string;
  name: string;
  mime_type: string | null;
  owners: string[];
  drive_id: string | null;
  folder_path: string | null;
  shared: boolean;
  size_bytes: number | null;
  modified_at: string | null;
  source_url: string | null;
  evidence_refs: DriveEvidenceRef[];
};

export type DriveFileListCounts = {
  total: number;
  shared: number;
  not_shared: number;
};

export type DriveFileListResponse = {
  workspace_id: string;
  files: DriveFile[];
  counts: DriveFileListCounts;
  boundary: DriveConnectorBoundary;
  warnings: string[];
};

export type DriveFileImportRequest = {
  files: Record<string, unknown>[];
  connectionId?: string | null;
};

export type DriveFileImportCounts = {
  received: number;
  imported: number;
  failed: number;
  source_records_created: number;
  source_records_updated: number;
};

export type DriveFileImportFailure = {
  index: number;
  reason: string;
};

export type DriveFileImportResponse = {
  workspace_id: string;
  counts: DriveFileImportCounts;
  files: DriveFile[];
  failures: DriveFileImportFailure[];
  boundary: DriveConnectorBoundary;
  warnings: string[];
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

export type CompanyMapCompany = {
  key: string;
  workspace_id: string;
  name: string;
  slug: string;
  status: string;
  source_refs: CompanyBrainSourceRef[];
};

export type CompanyMapInternalPerson = {
  key: string;
  person_id: string | null;
  user_id: string;
  name: string | null;
  email: string;
  status: string;
  role: WorkspaceMemberRole;
  source_refs: CompanyBrainSourceRef[];
};

export type CompanyMapExternalCandidate = {
  key: string;
  candidate_version: string;
  email: string;
  display_name: string | null;
  organization_key: string | null;
  last_interaction_at: string | null;
  interaction_count: number;
  source_refs: CompanyBrainSourceRef[];
  needs_founder_confirm: true;
};

export type CompanyMapOrganizationCandidate = {
  key: string;
  candidate_version: string;
  domain: string;
  name: string | null;
  kind: "external_candidate";
  people_count: number;
  interaction_count: number;
  last_interaction_at: string | null;
  source_refs: CompanyBrainSourceRef[];
  needs_founder_confirm: true;
};

export type CompanyMapConfirmedExternalPerson = {
  key: string;
  person_id: string;
  email: string;
  display_name: string | null;
  status: string;
  organization_id: string | null;
  organization_key: string | null;
  organization_name: string | null;
  relationship_type: CompanyMapRelationshipType | null;
  role_title: string | null;
  interaction_count: number;
  last_interaction_at: string | null;
  source_refs: CompanyBrainSourceRef[];
};

export type CompanyMapConfirmedOrganization = {
  key: string;
  organization_id: string;
  domain: string | null;
  name: string | null;
  relationship_kind: CompanyMapOrganizationRelationshipKind;
  status: string;
  people_count: number;
  interaction_count: number;
  last_interaction_at: string | null;
  source_refs: CompanyBrainSourceRef[];
};

export type CompanyMapResolutionCandidateType =
  | "external_person"
  | "organization";

export type CompanyMapResolutionDecision = "confirmed" | "dismissed";

export type CompanyMapRelationshipType =
  | "contact"
  | "employee"
  | "decision_maker"
  | "account_owner"
  | "advisor"
  | "other";

export type CompanyMapOrganizationRelationshipKind =
  | "unknown"
  | "prospect"
  | "customer"
  | "partner"
  | "vendor"
  | "other";

type CompanyMapResolutionRequestBase = {
  candidate_key: string;
  candidate_version: string;
  idempotency_key: string;
};

type CompanyMapDismissedResolutionRequest = CompanyMapResolutionRequestBase & {
  candidate_type: CompanyMapResolutionCandidateType;
  decision: "dismissed";
};

type CompanyMapConfirmedExternalPersonResolutionRequest =
  CompanyMapResolutionRequestBase & {
    candidate_type: "external_person";
    decision: "confirmed";
    display_name?: string;
  } & (
    | {
        relationship_type?: never;
        role_title?: never;
      }
    | {
        relationship_type: CompanyMapRelationshipType;
        role_title?: string;
      }
  );

type CompanyMapConfirmedOrganizationResolutionRequest =
  CompanyMapResolutionRequestBase & {
    candidate_type: "organization";
    decision: "confirmed";
    organization_name?: string;
    organization_relationship_kind?: CompanyMapOrganizationRelationshipKind;
  };

export type CompanyMapResolutionRequest =
  | CompanyMapDismissedResolutionRequest
  | CompanyMapConfirmedExternalPersonResolutionRequest
  | CompanyMapConfirmedOrganizationResolutionRequest;

export type CompanyMapResolutionReceipt = {
  resolution: {
    id: string;
    candidate_type: CompanyMapResolutionCandidateType;
    candidate_key: string;
    decision: CompanyMapResolutionDecision;
    created_at: string;
  };
  person_id?: string | null;
  organization_id?: string | null;
  affiliation_id?: string | null;
  interaction_count: number;
  replayed: boolean;
  capabilities: {
    provider_calls: false;
    external_write: false;
    llm_used: false;
  };
};

export type CompanyMapTouchpointDirection =
  | "inbound"
  | "outbound"
  | "mixed"
  | "unknown";

export type CompanyMapTouchpoint = {
  key: string;
  channel: "email";
  source_record_id: string;
  subject: string;
  direction: CompanyMapTouchpointDirection;
  occurred_at: string | null;
  person_keys: string[];
  organization_keys: string[];
  source_url: string | null;
  source_refs: CompanyBrainSourceRef[];
};

export type CompanyMapResponse = {
  workspace_id: string;
  mode: "evidence_backed_projection";
  source: "workspace_and_company_brain_projection";
  company: CompanyMapCompany;
  summary: {
    internal_people: number;
    confirmed_external_people: number;
    confirmed_organizations: number;
    external_contacts_in_window: number;
    organizations_in_window: number;
    touchpoints_in_window: number;
  };
  window: {
    gmail_messages_available: number;
    gmail_messages_considered: number;
    message_limit: number;
    truncated: boolean;
    order: "newest_first";
  };
  people: {
    internal: CompanyMapInternalPerson[];
    confirmed_external: CompanyMapConfirmedExternalPerson[];
    external_candidates: CompanyMapExternalCandidate[];
  };
  organizations: CompanyMapOrganizationCandidate[];
  confirmed_organizations: CompanyMapConfirmedOrganization[];
  touchpoints: CompanyMapTouchpoint[];
  capabilities: {
    read_only: true;
    can_resolve: boolean;
    required_role: "member";
    provider_calls: false;
    llm_used: false;
  };
  warnings: string[];
  is_live: false;
  llm_used: false;
};

export type CompanyBrainSummary = {
  repositories: number;
  open_issues: number;
  open_pull_requests: number;
  closed_issues: number;
  merged_pull_requests: number;
};

export type CompanyBrainSourceRecordProviderCount = {
  provider: string;
  count: number;
};

export type CompanyBrainSourceRecordTypeCount = {
  record_type: string;
  count: number;
};

export type CompanyBrainSourceRecordCoverage = {
  total: number;
  by_provider: CompanyBrainSourceRecordProviderCount[];
  by_record_type: CompanyBrainSourceRecordTypeCount[];
};

export type NormalizedEntityType =
  | "repository"
  | "issue"
  | "pull_request"
  | "email_message"
  | "drive_file"
  | "document";

export type NormalizedEntity = {
  entity_type: NormalizedEntityType | string;
  key: string;
  external_id: string;
  title: string;
  source_provider: string;
  status: string | null;
  source_url: string | null;
  updated_at: string | null;
  reference_id: string | null;
  source_refs: CompanyBrainSourceRef[];
};

export type NormalizedEntityTypeCount = {
  entity_type: string;
  count: number;
};

export type NormalizedEntityProviderCount = {
  source_provider: string;
  count: number;
};

export type NormalizedEntitiesSummary = {
  total: number;
  by_entity_type: NormalizedEntityTypeCount[];
  by_source_provider: NormalizedEntityProviderCount[];
};

export type NormalizedEntitiesResponse = {
  workspace_id: string;
  mode: "github_first_canonical";
  source: "canonical_company_brain_entities";
  summary: NormalizedEntitiesSummary;
  entities: NormalizedEntity[];
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
  source_provider?: string | null;
  external_id: string | null;
  number: number | null;
  title: string;
  state: string | null;
  repository_full_name: string | null;
  repository_external_id: string | null;
  project_key?: string | null;
  source_url: string | null;
  updated_at: string | null;
  source_refs: CompanyBrainSourceRef[];
};

export type CompanyBrainMessage = {
  source_record_id: string;
  message_id: string;
  thread_id: string | null;
  subject: string;
  snippet: string | null;
  from_address: string | null;
  to_addresses: string[];
  labels: string[];
  unread: boolean;
  received_at: string | null;
  source_url: string | null;
  source_refs: CompanyBrainSourceRef[];
};

export type CompanyBrainDriveFile = {
  source_record_id: string;
  file_id: string;
  name: string;
  mime_type: string | null;
  owners: string[];
  drive_id: string | null;
  folder_path: string | null;
  shared: boolean;
  size_bytes: number | null;
  modified_at: string | null;
  source_url: string | null;
  source_refs: CompanyBrainSourceRef[];
};

export type CompanyBrainResponse = {
  workspace_id: string;
  mode: "github_first_canonical";
  source: "canonical_github_company_brain";
  summary: CompanyBrainSummary;
  source_records?: CompanyBrainSourceRecordCoverage;
  repositories: CompanyBrainRepository[];
  work: {
    issues: CompanyBrainWorkItem[];
    pull_requests: CompanyBrainWorkItem[];
    recent: CompanyBrainWorkItem[];
  };
  communications?: {
    messages: CompanyBrainMessage[];
  };
  documents?: {
    files: CompanyBrainDriveFile[];
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

export type BriefingCoverageSignals = {
  canonical_repositories: number;
  open_issues: number;
  open_pull_requests: number;
  evidence_refs: number;
  is_live: boolean;
  llm_used: boolean;
  live_provider_sync: boolean;
  local_sync: boolean;
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
      coverage: BriefingCoverageSignals;
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
    coverage: BriefingCoverageSignals;
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
  created_by?: "user";
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
  proposal_version: string;
  is_live: boolean;
  execution_started: boolean;
  warnings: string[];
};

export type BriefingActionProposalSkippedItem = {
  item_key: string;
  title: string;
  reason: string;
};

export type BriefingActionProposalGenerationResponse = {
  proposals: ActionProposal[];
  skipped: BriefingActionProposalSkippedItem[];
  created_count: number;
  skipped_count: number;
  is_live: boolean;
  execution_started: boolean;
  warnings: string[];
};

export type DocumentStatus = "draft" | "published" | "archived";

export type DocumentBoundary = {
  provider_calls: boolean;
  external_writes: boolean;
  llm: boolean;
  reads_secrets: boolean;
};

export type DocumentSummary = {
  id: string;
  workspace_id: string;
  title: string;
  status: DocumentStatus | string;
  tags: string[];
  excerpt: string;
  created_by_user_id: string | null;
  updated_by_user_id: string | null;
  created_at: string;
  updated_at: string;
};

export type DocumentDetail = DocumentSummary & {
  body_markdown: string;
  body_text: string;
};

export type DocumentVersion = {
  id: string;
  workspace_id: string;
  document_id: string;
  version_number: number;
  title: string;
  body_markdown: string;
  body_text: string;
  status: DocumentStatus | string;
  tags: string[];
  created_by_user_id: string | null;
  created_at: string;
  excerpt: string;
};

export type DocumentListResponse = {
  workspace_id: string;
  documents: DocumentSummary[];
  count: number;
  boundary: DocumentBoundary;
};

export type DocumentResponse = {
  document: DocumentDetail;
  boundary: DocumentBoundary;
};

export type DocumentVersionsResponse = {
  workspace_id: string;
  document_id: string;
  versions: DocumentVersion[];
  count: number;
  boundary: DocumentBoundary;
};

export type DocumentCreateRequest = {
  title: string;
  body_markdown?: string;
  tags?: string[];
  status?: DocumentStatus | string;
};

export type DocumentUpdateRequest = {
  title?: string;
  body_markdown?: string;
  tags?: string[];
  status?: DocumentStatus | string;
};

export type DocumentListRequest = {
  status?: DocumentStatus | string;
  search?: string;
  limit?: number;
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

export type ActionProposalDecisionResponse = ActionProposalMutationResponse & {
  decision_receipt: LocalActionDecisionReceipt;
  is_live: false;
  execution_started: false;
};

export type ActionProposalBulkRequest = {
  proposal_ids: string[];
};

export type ActionProposalBulkRejectRequest = ActionProposalBulkRequest & {
  reason?: string | null;
};

export type ActionProposalBulkFailure = {
  proposal_id: string;
  status_code: number;
  detail: string;
};

export type ActionProposalBulkResponse = {
  proposals: ActionProposal[];
  failures: ActionProposalBulkFailure[];
  succeeded_count: number;
  failed_count: number;
  is_live: boolean;
  execution_started: boolean;
  warnings: string[];
};

export type RepoAuditImportFindingRequest = {
  repository_full_name: string;
  title?: string | null;
  summary?: string;
  severity?: string | null;
  risks?: string[];
  evidence_refs?: string[];
  recommended_next_step?: string | null;
  area_candidate?: string | null;
};

export type RepoAuditImportRequest = {
  findings: RepoAuditImportFindingRequest[];
};

export type RepoAuditImportFailure = {
  index: number;
  repository_full_name: string | null;
  status_code: number;
  detail: string;
};

export type RepoAuditImportResponse = {
  proposals: ActionProposal[];
  failures: RepoAuditImportFailure[];
  succeeded_count: number;
  failed_count: number;
  is_live: boolean;
  execution_started: boolean;
  warnings: string[];
};

export type RepoAuditImportPreviewFinding = {
  key: number;
  finding: RepoAuditImportFindingRequest;
  valid: boolean;
  issues: string[];
};

export type RepoAuditImportPreview = {
  parseError: string | null;
  findings: RepoAuditImportPreviewFinding[];
};

export type ActionProposalDecisionRequest = {
  idempotency_key: string;
  proposal_version: string;
  expected_snapshot_id?: string | null;
};

export type ActionProposalRejectRequest = ActionProposalDecisionRequest & {
  reason?: string | null;
};

export type LocalActionDecisionReceipt = {
  receipt_id: string;
  proposal_id: string;
  decision: "approved" | "rejected";
  recorded_at: string;
  replayed: boolean;
  external_write_performed: false;
  proposal_version: string;
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
  credential_source: GitHubAppCredentialSource;
  app_id_configured: boolean;
  app_slug: string | null;
  app_name: string | null;
  private_key_configured: boolean;
  private_key_source: string | null;
  webhook_secret_configured: boolean;
  setup_url: string | null;
  callback_url: string | null;
  missing_env: string[];
  installation_tokens_persisted: boolean;
  provider_writes_enabled: boolean;
};

export type GitHubAppSetupPhase =
  | "not_started"
  | "manifest_pending"
  | "manifest_exchanging"
  | "installation_pending"
  | "oauth_pending"
  | "oauth_exchanging"
  | "repository_selection"
  | "connected"
  | "failed"
  | "cancelled";

export type GitHubAppCredentialSource = "managed" | "environment" | "none";

export type GitHubAppSetupRepositoryRead = {
  id: string;
  name: string;
  full_name: string;
  private: boolean;
  visibility: string;
  archived: boolean;
  default_branch: string | null;
  source_url: string | null;
  last_activity_at: string | null;
};

export type GitHubAppSetupStatus = {
  phase: GitHubAppSetupPhase;
  credential_source: GitHubAppCredentialSource;
  app_slug: string | null;
  app_name: string | null;
  installation_account: string | null;
  installation_settings_url: string | null;
  repository_count: number;
  repositories: GitHubAppSetupRepositoryRead[];
  selected_repositories: string[];
  expires_at: string | null;
  error_code: string | null;
  install_url: string | null;
  can_manage: boolean;
  can_restart: boolean;
  setup_owned_by_current_user: boolean;
  installation_verified: boolean;
  secrets_encrypted: boolean;
  installation_tokens_persisted: boolean;
  provider_writes_enabled: boolean;
};

export type GitHubAppManifestSetupRequest = {
  owner_type: "user" | "organization";
  organization_login?: string;
  app_origin: string;
};

export type GitHubAppManifestSetupResponse = {
  phase: GitHubAppSetupPhase;
  action_url: string;
  manifest: string;
  expires_at: string;
};

export type GitHubAppInstallSetupResponse = {
  phase: GitHubAppSetupPhase;
  redirect_url: string;
  expires_at: string;
};

export type GitHubAppRepositorySelectionRequest = {
  repositories: string[];
};

export type GitHubAppRepositorySelectionResponse = {
  phase: GitHubAppSetupPhase;
  connection_id: string;
  selected_repositories: string[];
  repository_count: number;
};

export type GitHubAppSetupRestartResponse = {
  phase: GitHubAppSetupPhase;
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
  installation_verified: boolean;
  live_read_available: boolean;
  selected_repositories: string[];
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

// --- Repository Audit (deterministic, read-only over local discovery snapshot) ---

export type RepoAuditSourceSnapshot = {
  available: boolean;
  status: string;
  path: string | null;
  snapshot_id: string | null;
  snapshot_age_seconds: number | null;
  freshness_status?: string;
  freshness_label_ru?: string;
  repo_count?: number;
  message_ru?: string;
};

export type RepoAuditSummaryCard = {
  key: string;
  label_ru: string;
  value: number | string;
  detail_ru: string;
};

export type RepoAuditRepoFact = {
  name: string;
  full_name: string;
  org: string | null;
  description_status: string;
  archived: boolean;
  fork: boolean;
  private: boolean;
  visibility: string;
  default_branch: string | null;
  pushed_at: string | null;
  days_since_last_push: number | null;
  activity_bucket: string;
  primary_language: string | null;
  stack_candidate: string;
  ci_detected: boolean;
  tests_detected: boolean;
  license_status: string;
  readme_status: string;
  owner_candidate_status: string;
  area_candidate: string | null;
  area_confidence: number | null;
  needs_founder_confirm: boolean;
  risks: string[];
  unknowns: string[];
  evidence_refs: string[];
};

export type RepoAuditGuardrails = {
  preview_only: boolean;
  computed: boolean;
  db_written: boolean;
  network_calls: boolean;
  external_writes: boolean;
  github_writes: boolean;
  jira_writes: boolean;
  obsidian_written: boolean;
};

export type RepoAuditResponse = {
  status: string;
  preview_only: boolean;
  computed: boolean;
  db_written: boolean;
  network_calls: boolean;
  generated_at: string | null;
  source_snapshot: RepoAuditSourceSnapshot;
  repo_count: number;
  catalog_count: number;
  repo_facts: RepoAuditRepoFact[];
  summary_cards: RepoAuditSummaryCard[];
  risk_summary: Record<string, number>;
  area_candidate_counts: Record<string, number>;
  guardrails: RepoAuditGuardrails;
};
