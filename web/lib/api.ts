import type {
  ActionProposal,
  ActionExecutionPreviewResponse,
  ActionExecutionResponse,
  ActionProposalAuditResponse,
  ActionProposalExecuteRequest,
  ActionProposalBulkRejectRequest,
  ActionProposalBulkRequest,
  ActionProposalBulkResponse,
  ActionProposalCreateRequest,
  ActionProposalDecisionResponse,
  ActionProposalDecisionRequest,
  ActionProposalListRequest,
  ActionProposalListResponse,
  ActionProposalMutationResponse,
  ActionProposalRejectRequest,
  ApiErrorPayload,
  ApiFetchOptions,
  BriefingActionProposalGenerationResponse,
  BriefingListResponse,
  CompanyMapResolutionReceipt,
  CompanyMapResolutionRequest,
  CompanyMapResponse,
  CompanyBrainResponse,
  FounderBriefingRequest,
  FounderBriefingResponse,
  GitHubAppInstallSetupResponse,
  GitHubAppLiveSyncRequest,
  GitHubAppLiveSyncResponse,
  GitHubAppManifestSetupRequest,
  GitHubAppManifestSetupResponse,
  GitHubAppRepositorySelectionRequest,
  GitHubAppRepositorySelectionResponse,
  GitHubAppSetupRestartResponse,
  GitHubAppSetupStatus,
  GitHubConnectionStatusResponse,
  GitHubOperationalWorkResponse,
  GitHubOperationalWorkState,
  GitHubRepositoryListResponse,
  NormalizedEntitiesResponse,
  DocumentCreateRequest,
  DocumentListRequest,
  DocumentListResponse,
  DocumentResponse,
  DocumentUpdateRequest,
  DocumentVersionsResponse,
  ConnectorCheckReceipt,
  ConnectorConfigurationApplyRequest,
  ConnectorControl,
  ConnectorControlCenterResponse,
  ConnectorProvider,
  ConnectorRegistryResponse,
  WorkspaceMemberProvisionRequest,
  WorkspaceMemberProvisionResponse,
  WorkspaceMembersResponse
} from "./types";
import {
  parseHeadquartersOnboardingDetailResponse,
  parseHeadquartersSnapshotResponse,
  type HeadquartersOnboardingDetailResponse,
  type HeadquartersSnapshotResponse
} from "./headquarters";
import {
  parseAssistantQueryResponse,
  type AssistantQueryRequest,
  type AssistantQueryResponse
} from "./assistant";

// Same-origin base: the browser calls the web origin, and next.config.mjs
// proxies /api/* to the backend, keeping the session cookie first-party.
function sameOriginBase(): string {
  return typeof window !== "undefined" ? window.location.origin : "http://localhost";
}

function buildUrl(path: string, baseUrl: string): URL {
  if (path.startsWith("http://") || path.startsWith("https://")) {
    return new URL(path);
  }
  return new URL(path, baseUrl.endsWith("/") ? baseUrl : `${baseUrl}/`);
}

async function readError(response: Response): Promise<string> {
  const fallback = `${response.status} ${response.statusText}`.trim();
  try {
    const payload = (await response.json()) as ApiErrorPayload;
    return payload.detail || payload.message || fallback;
  } catch {
    return fallback;
  }
}

export class ApiRequestError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiRequestError";
    this.status = status;
  }
}

export async function apiFetch<TResponse>(
  path: string,
  options: ApiFetchOptions = {}
): Promise<TResponse> {
  // Always same-origin so the proxy delivers the first-party session cookie.
  // The backend resolves the workspace from the session user — no owner_email
  // and no operator API key are sent from the browser.
  const url = buildUrl(path, sameOriginBase());

  const headers = new Headers(options.headers);
  headers.set("Accept", "application/json");
  if (options.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  // The operator API key is never sent from the browser; auth is the
  // first-party session cookie (credentials: include).
  const response = await fetch(url, {
    ...options,
    headers,
    credentials: "include"
  });

  if (!response.ok) {
    throw new ApiRequestError(await readError(response), response.status);
  }

  if (response.status === 204) {
    return undefined as TResponse;
  }

  return (await response.json()) as TResponse;
}

type GitHubOperationalWorkRequest = {
  state?: GitHubOperationalWorkState;
  limit?: number;
};

export function buildWorkspaceGitHubOperationalWorkPath(
  workspaceId: string,
  request: GitHubOperationalWorkRequest = {}
): string {
  const params = new URLSearchParams();
  params.set("state", request.state ?? "open");
  params.set("limit", String(request.limit ?? 100));
  return `/api/v1/workspaces/${encodeURIComponent(
    workspaceId
  )}/github/operational-work?${params.toString()}`;
}

export async function fetchGitHubOperationalWork(
  workspaceId: string,
  request: GitHubOperationalWorkRequest = {},
  options: ApiFetchOptions = {}
): Promise<GitHubOperationalWorkResponse> {
  return apiFetch<GitHubOperationalWorkResponse>(
    buildWorkspaceGitHubOperationalWorkPath(workspaceId, request),
    options
  );
}

export function buildWorkspaceCompanyBrainPath(workspaceId: string): string {
  return `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/company-brain`;
}

export function buildWorkspaceCompanyMapPath(workspaceId: string): string {
  return `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/company-map`;
}

export function buildWorkspaceHeadquartersPath(workspaceId: string): string {
  return `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/headquarters`;
}

export function buildWorkspaceHeadquartersOnboardingPath(
  workspaceId: string
): string {
  return `${buildWorkspaceHeadquartersPath(workspaceId)}/onboarding`;
}

export async function fetchHeadquarters(
  workspaceId: string,
  options: ApiFetchOptions = {}
): Promise<HeadquartersSnapshotResponse> {
  const payload = await apiFetch<unknown>(
    buildWorkspaceHeadquartersPath(workspaceId),
    options
  );
  return parseHeadquartersSnapshotResponse(payload);
}

export async function fetchHeadquartersOnboarding(
  workspaceId: string,
  options: ApiFetchOptions = {}
): Promise<HeadquartersOnboardingDetailResponse> {
  const payload = await apiFetch<unknown>(
    buildWorkspaceHeadquartersOnboardingPath(workspaceId),
    options
  );
  return parseHeadquartersOnboardingDetailResponse(payload);
}

export function buildWorkspaceAssistantQueryPath(workspaceId: string): string {
  return `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/assistant/query`;
}

export async function queryWorkspaceAssistant(
  workspaceId: string,
  request: AssistantQueryRequest,
  options: ApiFetchOptions = {}
): Promise<AssistantQueryResponse> {
  const payload = await apiFetch<unknown>(
    buildWorkspaceAssistantQueryPath(workspaceId),
    {
      ...options,
      body: JSON.stringify(request),
      method: "POST"
    }
  );
  return parseAssistantQueryResponse(payload);
}

export function buildWorkspaceCompanyMapResolutionsPath(workspaceId: string): string {
  return `${buildWorkspaceCompanyMapPath(workspaceId)}/resolutions`;
}

export async function fetchCompanyMap(
  workspaceId: string,
  options: ApiFetchOptions = {}
): Promise<CompanyMapResponse> {
  return apiFetch<CompanyMapResponse>(buildWorkspaceCompanyMapPath(workspaceId), options);
}

export async function resolveCompanyMapCandidate(
  workspaceId: string,
  request: CompanyMapResolutionRequest,
  options: ApiFetchOptions = {}
): Promise<CompanyMapResolutionReceipt> {
  return apiFetch<CompanyMapResolutionReceipt>(
    buildWorkspaceCompanyMapResolutionsPath(workspaceId),
    {
      ...options,
      body: JSON.stringify(request),
      method: "POST"
    }
  );
}

export function buildWorkspaceCompanyBrainEntitiesPath(workspaceId: string): string {
  return `${buildWorkspaceCompanyBrainPath(workspaceId)}/entities`;
}

export async function fetchCompanyBrain(
  workspaceId: string,
  options: ApiFetchOptions = {}
): Promise<CompanyBrainResponse> {
  return apiFetch<CompanyBrainResponse>(
    buildWorkspaceCompanyBrainPath(workspaceId),
    options
  );
}

export async function fetchCompanyBrainEntities(
  workspaceId: string,
  options: ApiFetchOptions = {}
): Promise<NormalizedEntitiesResponse> {
  return apiFetch<NormalizedEntitiesResponse>(
    buildWorkspaceCompanyBrainEntitiesPath(workspaceId),
    options
  );
}

export function buildWorkspaceMembersPath(workspaceId: string): string {
  return `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/members`;
}

export function buildWorkspaceConnectorsPath(workspaceId: string): string {
  return `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/connectors`;
}

export async function fetchWorkspaceConnectors(
  workspaceId: string,
  options: ApiFetchOptions = {}
): Promise<ConnectorRegistryResponse> {
  return apiFetch<ConnectorRegistryResponse>(
    buildWorkspaceConnectorsPath(workspaceId),
    options
  );
}

export function buildWorkspaceConnectorControlCenterPath(
  workspaceId: string
): string {
  return `${buildWorkspaceConnectorsPath(workspaceId)}/control-center`;
}

export function buildWorkspaceConnectorConfigurationPath(
  workspaceId: string,
  provider: ConnectorProvider
): string {
  return `${buildWorkspaceConnectorsPath(workspaceId)}/${encodeURIComponent(
    provider
  )}/configuration`;
}

export function buildWorkspaceConnectorCheckPath(
  workspaceId: string,
  provider: ConnectorProvider,
  capability: "read" | "write"
): string {
  return `${buildWorkspaceConnectorsPath(workspaceId)}/${encodeURIComponent(
    provider
  )}/checks/${capability}`;
}

export async function fetchConnectorControlCenter(
  workspaceId: string,
  options: ApiFetchOptions = {}
): Promise<ConnectorControlCenterResponse> {
  return apiFetch<ConnectorControlCenterResponse>(
    buildWorkspaceConnectorControlCenterPath(workspaceId),
    options
  );
}

export async function applyConnectorConfiguration(
  workspaceId: string,
  provider: ConnectorProvider,
  request: ConnectorConfigurationApplyRequest,
  options: ApiFetchOptions = {}
): Promise<ConnectorControl> {
  return apiFetch<ConnectorControl>(
    buildWorkspaceConnectorConfigurationPath(workspaceId, provider),
    {
      ...options,
      body: JSON.stringify(request),
      method: "POST"
    }
  );
}

export async function disconnectConnectorConfiguration(
  workspaceId: string,
  provider: ConnectorProvider,
  options: ApiFetchOptions = {}
): Promise<ConnectorControl> {
  return apiFetch<ConnectorControl>(
    buildWorkspaceConnectorConfigurationPath(workspaceId, provider),
    { ...options, method: "DELETE" }
  );
}

export async function checkConnectorReadAccess(
  workspaceId: string,
  provider: ConnectorProvider,
  options: ApiFetchOptions = {}
): Promise<ConnectorCheckReceipt> {
  return apiFetch<ConnectorCheckReceipt>(
    buildWorkspaceConnectorCheckPath(workspaceId, provider, "read"),
    { ...options, method: "POST" }
  );
}

export async function checkConnectorWriteReadiness(
  workspaceId: string,
  provider: ConnectorProvider,
  options: ApiFetchOptions = {}
): Promise<ConnectorCheckReceipt> {
  return apiFetch<ConnectorCheckReceipt>(
    buildWorkspaceConnectorCheckPath(workspaceId, provider, "write"),
    { ...options, method: "POST" }
  );
}

export async function fetchWorkspaceMembers(
  workspaceId: string,
  options: ApiFetchOptions = {}
): Promise<WorkspaceMembersResponse> {
  return apiFetch<WorkspaceMembersResponse>(
    buildWorkspaceMembersPath(workspaceId),
    options
  );
}

export async function provisionWorkspaceMember(
  workspaceId: string,
  request: WorkspaceMemberProvisionRequest,
  options: ApiFetchOptions = {}
): Promise<WorkspaceMemberProvisionResponse> {
  return apiFetch<WorkspaceMemberProvisionResponse>(
    buildWorkspaceMembersPath(workspaceId),
    {
      ...options,
      body: JSON.stringify({
        email: request.email,
        name: request.name || null,
        role: request.role
      }),
      method: "POST"
    }
  );
}


export function buildWorkspaceDocumentsPath(
  workspaceId: string,
  request: DocumentListRequest = {}
): string {
  const params = new URLSearchParams();
  params.set("limit", String(request.limit ?? 50));
  if (request.status) {
    params.set("status", request.status);
  }
  if (request.search) {
    params.set("search", request.search);
  }
  return `/api/v1/workspaces/${encodeURIComponent(
    workspaceId
  )}/documents?${params.toString()}`;
}

export function buildWorkspaceDocumentsCollectionPath(workspaceId: string): string {
  return `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/documents`;
}

export function buildWorkspaceDocumentPath(
  workspaceId: string,
  documentId: string
): string {
  return `/api/v1/workspaces/${encodeURIComponent(
    workspaceId
  )}/documents/${encodeURIComponent(documentId)}`;
}

export function buildWorkspaceDocumentVersionsPath(
  workspaceId: string,
  documentId: string
): string {
  return `${buildWorkspaceDocumentPath(workspaceId, documentId)}/versions`;
}

export async function fetchDocuments(
  workspaceId: string,
  request: DocumentListRequest = {},
  options: ApiFetchOptions = {}
): Promise<DocumentListResponse> {
  return apiFetch<DocumentListResponse>(
    buildWorkspaceDocumentsPath(workspaceId, request),
    options
  );
}

export async function fetchDocument(
  workspaceId: string,
  documentId: string,
  options: ApiFetchOptions = {}
): Promise<DocumentResponse> {
  return apiFetch<DocumentResponse>(
    buildWorkspaceDocumentPath(workspaceId, documentId),
    options
  );
}

export async function fetchDocumentVersions(
  workspaceId: string,
  documentId: string,
  options: ApiFetchOptions = {}
): Promise<DocumentVersionsResponse> {
  return apiFetch<DocumentVersionsResponse>(
    buildWorkspaceDocumentVersionsPath(workspaceId, documentId),
    options
  );
}

export async function createDocument(
  workspaceId: string,
  request: DocumentCreateRequest,
  options: ApiFetchOptions = {}
): Promise<DocumentResponse> {
  return apiFetch<DocumentResponse>(
    buildWorkspaceDocumentsCollectionPath(workspaceId),
    {
      ...options,
      body: JSON.stringify({
        title: request.title,
        body_markdown: request.body_markdown ?? "",
        tags: request.tags ?? [],
        status: request.status ?? "draft"
      }),
      method: "POST"
    }
  );
}

export async function updateDocument(
  workspaceId: string,
  documentId: string,
  request: DocumentUpdateRequest,
  options: ApiFetchOptions = {}
): Promise<DocumentResponse> {
  return apiFetch<DocumentResponse>(
    buildWorkspaceDocumentPath(workspaceId, documentId),
    {
      ...options,
      body: JSON.stringify(request),
      method: "PATCH"
    }
  );
}

export async function deleteDocument(
  workspaceId: string,
  documentId: string,
  options: ApiFetchOptions = {}
): Promise<void> {
  await apiFetch<void>(buildWorkspaceDocumentPath(workspaceId, documentId), {
    ...options,
    method: "DELETE"
  });
}

export function buildWorkspaceManualBriefingPath(workspaceId: string): string {
  return `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/briefings/manual`;
}

export async function generateManualFounderBriefing(
  workspaceId: string,
  request: FounderBriefingRequest = {},
  options: ApiFetchOptions = {}
): Promise<FounderBriefingResponse> {
  return apiFetch<FounderBriefingResponse>(
    buildWorkspaceManualBriefingPath(workspaceId),
    {
      ...options,
      body: JSON.stringify({
        focus: request.focus ?? ["github", "sync", "repositories"],
        include_github: request.include_github ?? true,
        include_connections: request.include_connections ?? true,
        include_sync_jobs: request.include_sync_jobs ?? true,
        include_repository_inventory: request.include_repository_inventory ?? true,
        limit: request.limit ?? 20
      }),
      method: "POST"
    }
  );
}

export function buildWorkspaceBriefingsPath(
  workspaceId: string,
  request: { limit?: number; offset?: number } = {}
): string {
  const params = new URLSearchParams();
  params.set("limit", String(request.limit ?? 20));
  params.set("offset", String(request.offset ?? 0));
  return `/api/v1/workspaces/${encodeURIComponent(
    workspaceId
  )}/briefings?${params.toString()}`;
}

export function buildWorkspaceBriefingPath(
  workspaceId: string,
  briefingId: string
): string {
  return `/api/v1/workspaces/${encodeURIComponent(
    workspaceId
  )}/briefings/${encodeURIComponent(briefingId)}`;
}

export function buildWorkspaceBriefingActionProposalsPath(
  workspaceId: string,
  briefingId: string
): string {
  return `${buildWorkspaceBriefingPath(workspaceId, briefingId)}/action-proposals`;
}

export async function listBriefings(
  workspaceId: string,
  request: { limit?: number; offset?: number } = {},
  options: ApiFetchOptions = {}
): Promise<BriefingListResponse> {
  return apiFetch<BriefingListResponse>(
    buildWorkspaceBriefingsPath(workspaceId, request),
    options
  );
}

export async function getBriefing(
  workspaceId: string,
  briefingId: string,
  options: ApiFetchOptions = {}
): Promise<FounderBriefingResponse> {
  return apiFetch<FounderBriefingResponse>(
    buildWorkspaceBriefingPath(workspaceId, briefingId),
    options
  );
}

export async function generateBriefingActionProposals(
  workspaceId: string,
  briefingId: string,
  options: ApiFetchOptions = {}
): Promise<BriefingActionProposalGenerationResponse> {
  return apiFetch<BriefingActionProposalGenerationResponse>(
    buildWorkspaceBriefingActionProposalsPath(workspaceId, briefingId),
    {
      ...options,
      method: "POST"
    }
  );
}

export function buildWorkspaceActionProposalsPath(
  workspaceId: string,
  request: ActionProposalListRequest = {}
): string {
  const params = new URLSearchParams();
  params.set("limit", String(request.limit ?? 50));
  if (request.status) {
    params.set("status", request.status);
  }
  if (request.target_provider) {
    params.set("target_provider", request.target_provider);
  }
  if (request.action_type) {
    params.set("action_type", request.action_type);
  }
  return `${buildWorkspaceActionProposalsCollectionPath(
    workspaceId
  )}?${params.toString()}`;
}

export function buildWorkspaceActionProposalsCollectionPath(workspaceId: string): string {
  return `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/actions/proposals`;
}

export function buildWorkspaceActionProposalPath(
  workspaceId: string,
  proposalId: string
): string {
  return `/api/v1/workspaces/${encodeURIComponent(
    workspaceId
  )}/actions/proposals/${encodeURIComponent(proposalId)}`;
}

export function buildWorkspaceActionProposalApprovePath(
  workspaceId: string,
  proposalId: string
): string {
  return `${buildWorkspaceActionProposalPath(workspaceId, proposalId)}/approve`;
}

export function buildWorkspaceActionProposalRejectPath(
  workspaceId: string,
  proposalId: string
): string {
  return `${buildWorkspaceActionProposalPath(workspaceId, proposalId)}/reject`;
}

export function buildWorkspaceActionProposalBulkApprovePath(
  workspaceId: string
): string {
  return `${buildWorkspaceActionProposalsCollectionPath(workspaceId)}/bulk-approve`;
}

export function buildWorkspaceActionProposalBulkRejectPath(workspaceId: string): string {
  return `${buildWorkspaceActionProposalsCollectionPath(workspaceId)}/bulk-reject`;
}

export function buildWorkspaceActionProposalExecutionPreviewPath(
  workspaceId: string,
  proposalId: string
): string {
  return `${buildWorkspaceActionProposalPath(
    workspaceId,
    proposalId
  )}/execution-preview`;
}

export function buildWorkspaceActionProposalAuditPath(
  workspaceId: string,
  proposalId: string
): string {
  return `${buildWorkspaceActionProposalPath(workspaceId, proposalId)}/audit`;
}

export function buildWorkspaceActionProposalExecutePath(
  workspaceId: string,
  proposalId: string
): string {
  return `${buildWorkspaceActionProposalPath(workspaceId, proposalId)}/execute`;
}

export async function fetchActionProposals(
  workspaceId: string,
  request: ActionProposalListRequest = {},
  options: ApiFetchOptions = {}
): Promise<ActionProposalListResponse> {
  return apiFetch<ActionProposalListResponse>(
    buildWorkspaceActionProposalsPath(workspaceId, request),
    options
  );
}

export async function fetchActionProposal(
  workspaceId: string,
  proposalId: string,
  options: ApiFetchOptions = {}
): Promise<ActionProposal> {
  return apiFetch<ActionProposal>(
    buildWorkspaceActionProposalPath(workspaceId, proposalId),
    options
  );
}

export async function createActionProposal(
  workspaceId: string,
  request: ActionProposalCreateRequest,
  options: ApiFetchOptions = {}
): Promise<ActionProposalMutationResponse> {
  return apiFetch<ActionProposalMutationResponse>(
    buildWorkspaceActionProposalsCollectionPath(workspaceId),
    {
      ...options,
      body: JSON.stringify({
        briefing_item_id: request.briefing_item_id ?? null,
        target_provider: request.target_provider,
        action_type: request.action_type,
        title: request.title,
        description: request.description ?? null,
        payload: request.payload ?? {},
        evidence_refs: request.evidence_refs ?? [],
        created_by: request.created_by ?? "user"
      }),
      method: "POST"
    }
  );
}

export async function approveActionProposal(
  workspaceId: string,
  proposalId: string,
  request: ActionProposalDecisionRequest,
  options: ApiFetchOptions = {}
): Promise<ActionProposalDecisionResponse> {
  return apiFetch<ActionProposalDecisionResponse>(
    buildWorkspaceActionProposalApprovePath(workspaceId, proposalId),
    {
      ...options,
      body: JSON.stringify({
        expected_snapshot_id: request.expected_snapshot_id ?? null,
        idempotency_key: request.idempotency_key,
        proposal_version: request.proposal_version
      }),
      method: "POST"
    }
  );
}

export async function rejectActionProposal(
  workspaceId: string,
  proposalId: string,
  request: ActionProposalRejectRequest,
  options: ApiFetchOptions = {}
): Promise<ActionProposalDecisionResponse> {
  return apiFetch<ActionProposalDecisionResponse>(
    buildWorkspaceActionProposalRejectPath(workspaceId, proposalId),
    {
      ...options,
      body: JSON.stringify({
        expected_snapshot_id: request.expected_snapshot_id ?? null,
        idempotency_key: request.idempotency_key,
        proposal_version: request.proposal_version,
        reason: request.reason ?? null
      }),
      method: "POST"
    }
  );
}

export async function bulkApproveActionProposals(
  workspaceId: string,
  request: ActionProposalBulkRequest,
  options: ApiFetchOptions = {}
): Promise<ActionProposalBulkResponse> {
  return apiFetch<ActionProposalBulkResponse>(
    buildWorkspaceActionProposalBulkApprovePath(workspaceId),
    {
      ...options,
      body: JSON.stringify({
        proposal_ids: request.proposal_ids
      }),
      method: "POST"
    }
  );
}

export async function bulkRejectActionProposals(
  workspaceId: string,
  request: ActionProposalBulkRejectRequest,
  options: ApiFetchOptions = {}
): Promise<ActionProposalBulkResponse> {
  return apiFetch<ActionProposalBulkResponse>(
    buildWorkspaceActionProposalBulkRejectPath(workspaceId),
    {
      ...options,
      body: JSON.stringify({
        proposal_ids: request.proposal_ids,
        reason: request.reason ?? null
      }),
      method: "POST"
    }
  );
}

export async function fetchActionExecutionPreview(
  workspaceId: string,
  proposalId: string,
  options: ApiFetchOptions = {}
): Promise<ActionExecutionPreviewResponse> {
  return apiFetch<ActionExecutionPreviewResponse>(
    buildWorkspaceActionProposalExecutionPreviewPath(workspaceId, proposalId),
    options
  );
}

export async function fetchActionProposalAudit(
  workspaceId: string,
  proposalId: string,
  options: ApiFetchOptions = {}
): Promise<ActionProposalAuditResponse> {
  return apiFetch<ActionProposalAuditResponse>(
    buildWorkspaceActionProposalAuditPath(workspaceId, proposalId),
    options
  );
}

export async function executeActionProposal(
  workspaceId: string,
  proposalId: string,
  request: ActionProposalExecuteRequest,
  options: ApiFetchOptions = {}
): Promise<ActionExecutionResponse> {
  return apiFetch<ActionExecutionResponse>(
    buildWorkspaceActionProposalExecutePath(workspaceId, proposalId),
    {
      ...options,
      body: JSON.stringify({
        connection_id: request.connection_id,
        confirm_external_write: request.confirm_external_write,
        idempotency_key: request.idempotency_key ?? null
      }),
      method: "POST"
    }
  );
}

export function buildWorkspaceGitHubConnectionStatusPath(workspaceId: string): string {
  return `/api/v1/workspaces/${encodeURIComponent(
    workspaceId
  )}/github/connection-status`;
}

export async function fetchGitHubConnectionStatus(
  workspaceId: string,
  options: ApiFetchOptions = {}
): Promise<GitHubConnectionStatusResponse> {
  return apiFetch<GitHubConnectionStatusResponse>(
    buildWorkspaceGitHubConnectionStatusPath(workspaceId),
    options
  );
}

export function buildWorkspaceGitHubAppSetupPath(workspaceId: string): string {
  return `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/github/app-setup`;
}

export function buildWorkspaceGitHubAppSetupManifestPath(
  workspaceId: string
): string {
  return `${buildWorkspaceGitHubAppSetupPath(workspaceId)}/manifest`;
}

export function buildWorkspaceGitHubAppSetupInstallPath(
  workspaceId: string
): string {
  return `${buildWorkspaceGitHubAppSetupPath(workspaceId)}/install`;
}

export function buildWorkspaceGitHubAppSetupRepositoriesPath(
  workspaceId: string
): string {
  return `${buildWorkspaceGitHubAppSetupPath(workspaceId)}/repositories`;
}

export function buildWorkspaceGitHubAppSetupRepositoriesRefreshPath(
  workspaceId: string
): string {
  return `${buildWorkspaceGitHubAppSetupRepositoriesPath(workspaceId)}/refresh`;
}

export function buildWorkspaceGitHubAppSetupRestartPath(
  workspaceId: string
): string {
  return `${buildWorkspaceGitHubAppSetupPath(workspaceId)}/restart`;
}

export async function fetchGitHubAppSetupStatus(
  workspaceId: string,
  options: ApiFetchOptions = {}
): Promise<GitHubAppSetupStatus> {
  return apiFetch<GitHubAppSetupStatus>(
    buildWorkspaceGitHubAppSetupPath(workspaceId),
    options
  );
}

export async function beginGitHubAppManifestSetup(
  workspaceId: string,
  request: GitHubAppManifestSetupRequest,
  options: ApiFetchOptions = {}
): Promise<GitHubAppManifestSetupResponse> {
  const body: GitHubAppManifestSetupRequest = {
    app_origin: request.app_origin,
    owner_type: request.owner_type
  };
  if (request.owner_type === "organization" && request.organization_login) {
    body.organization_login = request.organization_login;
  }
  return apiFetch<GitHubAppManifestSetupResponse>(
    buildWorkspaceGitHubAppSetupManifestPath(workspaceId),
    {
      ...options,
      body: JSON.stringify(body),
      method: "POST"
    }
  );
}

export async function beginGitHubAppInstallSetup(
  workspaceId: string,
  options: ApiFetchOptions = {}
): Promise<GitHubAppInstallSetupResponse> {
  return apiFetch<GitHubAppInstallSetupResponse>(
    buildWorkspaceGitHubAppSetupInstallPath(workspaceId),
    { ...options, method: "POST" }
  );
}

export async function selectGitHubAppRepositories(
  workspaceId: string,
  request: GitHubAppRepositorySelectionRequest,
  options: ApiFetchOptions = {}
): Promise<GitHubAppRepositorySelectionResponse> {
  return apiFetch<GitHubAppRepositorySelectionResponse>(
    buildWorkspaceGitHubAppSetupRepositoriesPath(workspaceId),
    {
      ...options,
      body: JSON.stringify({ repositories: request.repositories }),
      method: "POST"
    }
  );
}

export async function refreshGitHubAppSetupRepositories(
  workspaceId: string,
  options: ApiFetchOptions = {}
): Promise<GitHubAppSetupStatus> {
  return apiFetch<GitHubAppSetupStatus>(
    buildWorkspaceGitHubAppSetupRepositoriesRefreshPath(workspaceId),
    { ...options, method: "POST" }
  );
}

export async function restartGitHubAppSetup(
  workspaceId: string,
  options: ApiFetchOptions = {}
): Promise<GitHubAppSetupRestartResponse> {
  return apiFetch<GitHubAppSetupRestartResponse>(
    buildWorkspaceGitHubAppSetupRestartPath(workspaceId),
    { ...options, method: "POST" }
  );
}

export function buildWorkspaceGitHubRepositoriesPath(
  workspaceId: string,
  limit = 100
): string {
  const params = new URLSearchParams();
  params.set("limit", String(limit));
  return `/api/v1/workspaces/${encodeURIComponent(
    workspaceId
  )}/github/repositories?${params.toString()}`;
}

export async function fetchGitHubRepositories(
  workspaceId: string,
  options: ApiFetchOptions = {}
): Promise<GitHubRepositoryListResponse> {
  return apiFetch<GitHubRepositoryListResponse>(
    buildWorkspaceGitHubRepositoriesPath(workspaceId),
    options
  );
}

export function buildWorkspaceGitHubAppLiveSyncPath(workspaceId: string): string {
  return `/api/v1/workspaces/${encodeURIComponent(
    workspaceId
  )}/github/connections/app-installation/sync`;
}

export async function runGitHubAppLiveSync(
  workspaceId: string,
  request: GitHubAppLiveSyncRequest,
  options: ApiFetchOptions = {}
): Promise<GitHubAppLiveSyncResponse> {
  const body: Record<string, unknown> = {
    connection_id: request.connection_id,
    repositories: request.repositories,
    include_issues: request.include_issues ?? true,
    include_pull_requests: request.include_pull_requests ?? true
  };
  if (request.issue_states && request.issue_states.length > 0) {
    body.issue_states = request.issue_states;
  }
  if (request.pull_request_states && request.pull_request_states.length > 0) {
    body.pull_request_states = request.pull_request_states;
  }
  return apiFetch<GitHubAppLiveSyncResponse>(
    buildWorkspaceGitHubAppLiveSyncPath(workspaceId),
    {
      ...options,
      body: JSON.stringify(body),
      method: "POST"
    }
  );
}
