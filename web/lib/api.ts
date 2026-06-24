import {
  getConfiguredApiBaseUrl,
  readOperatorConfig,
  resolveApiBaseUrl
} from "./config";
import type {
  ActionExecutionPreviewResponse,
  ActionExecutionResponse,
  ActionProposalExecuteRequest,
  ActionProposalCreateRequest,
  ActionProposalListRequest,
  ActionProposalListResponse,
  ActionProposalMutationResponse,
  ActionProposalRejectRequest,
  ApiErrorPayload,
  ApiFetchOptions,
  CompanyBrainResponse,
  FounderBriefingRequest,
  FounderBriefingResponse,
  GitHubConnectionStatusResponse,
  GitHubLocalSyncRequest,
  GitHubLocalSyncResponse,
  GitHubOperationalWorkResponse,
  GitHubOperationalWorkState
} from "./types";

const API_KEY_HEADER = "X-FounderOS-API-Key";

function buildUrl(path: string, baseUrl: string): URL {
  if (path.startsWith("http://") || path.startsWith("https://")) {
    return new URL(path);
  }
  return new URL(path, baseUrl.endsWith("/") ? baseUrl : `${baseUrl}/`);
}

function appendOwnerEmail(url: URL, ownerEmail: string | null | undefined): void {
  if (!ownerEmail || url.searchParams.has("owner_email")) {
    return;
  }
  url.searchParams.set("owner_email", ownerEmail);
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

export async function apiFetch<TResponse>(
  path: string,
  options: ApiFetchOptions = {}
): Promise<TResponse> {
  const localConfig = readOperatorConfig();
  const baseUrl = options.apiBaseUrl || resolveApiBaseUrl(localConfig);
  const url = buildUrl(path, baseUrl || getConfiguredApiBaseUrl());
  if (options.includeOwnerEmail !== false) {
    appendOwnerEmail(url, options.ownerEmail ?? localConfig.ownerEmail);
  }

  const headers = new Headers(options.headers);
  headers.set("Accept", "application/json");
  if (options.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const apiKey = options.apiKey ?? localConfig.apiKey;
  if (apiKey) {
    headers.set(API_KEY_HEADER, apiKey);
  }

  const response = await fetch(url, {
    ...options,
    headers
  });

  if (!response.ok) {
    throw new Error(await readError(response));
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

export async function fetchCompanyBrain(
  workspaceId: string,
  options: ApiFetchOptions = {}
): Promise<CompanyBrainResponse> {
  return apiFetch<CompanyBrainResponse>(
    buildWorkspaceCompanyBrainPath(workspaceId),
    options
  );
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

export function buildWorkspaceActionProposalExecutionPreviewPath(
  workspaceId: string,
  proposalId: string
): string {
  return `${buildWorkspaceActionProposalPath(
    workspaceId,
    proposalId
  )}/execution-preview`;
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
  options: ApiFetchOptions = {}
): Promise<ActionProposalMutationResponse> {
  return apiFetch<ActionProposalMutationResponse>(
    buildWorkspaceActionProposalApprovePath(workspaceId, proposalId),
    {
      ...options,
      method: "POST"
    }
  );
}

export async function rejectActionProposal(
  workspaceId: string,
  proposalId: string,
  request: ActionProposalRejectRequest = {},
  options: ApiFetchOptions = {}
): Promise<ActionProposalMutationResponse> {
  return apiFetch<ActionProposalMutationResponse>(
    buildWorkspaceActionProposalRejectPath(workspaceId, proposalId),
    {
      ...options,
      body: JSON.stringify({
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

export function buildWorkspaceGitHubLocalSyncPath(workspaceId: string): string {
  return `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/github/local-sync`;
}

export async function runGitHubLocalSync(
  workspaceId: string,
  request: GitHubLocalSyncRequest = {},
  options: ApiFetchOptions = {}
): Promise<GitHubLocalSyncResponse> {
  return apiFetch<GitHubLocalSyncResponse>(
    buildWorkspaceGitHubLocalSyncPath(workspaceId),
    {
      ...options,
      body: JSON.stringify({
        include_repositories: request.include_repositories ?? true,
        include_issues: request.include_issues ?? true,
        include_pull_requests: request.include_pull_requests ?? true
      }),
      method: "POST"
    }
  );
}

export { API_KEY_HEADER };
