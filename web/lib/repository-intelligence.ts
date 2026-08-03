import { apiFetch } from "./api";
import type { ApiFetchOptions } from "./types";

export type RepositoryIntelligenceCapabilities = {
  provider_calls: false;
  repository_reads: false;
  target_execution: false;
  external_writes: false;
  llm_used: false;
  human_resolution_writes: false;
};

export type RepositoryIntelligenceIdentity = {
  id: string;
  provider: "github";
  external_id: string;
  name: string;
  full_name: string;
  default_branch: string | null;
  visibility: string | null;
  archived: boolean;
  source_url: string | null;
  last_activity_at: string | null;
};

export type RepositoryLatestAudit = {
  id: string;
  audit_level: "L0" | "L1" | "L2";
  target_status: "exact" | "unavailable";
  commit_sha: string | null;
  metadata_snapshot_id: string | null;
  profile: string;
  engine_version: string;
  status: "succeeded" | "partial" | "failed" | "cancelled";
  coverage_status: "complete" | "partial";
  reconciliation_applied: boolean;
  completed_at: string;
  artifact_status: "retained" | "purged";
};

export type RepositoryOpenFindings = {
  critical: number;
  high: number;
  medium: number;
  low: number;
  info: number;
};

export type RepositoryPortfolioItem = RepositoryIntelligenceIdentity & {
  purpose_summary: string | null;
  operational_summary: string | null;
  repository_type: string;
  purpose_status: string;
  purpose_confidence: number;
  product_candidates: string[];
  owner_candidates: string[];
  has_confirmed_owner: boolean;
  latest_audit: RepositoryLatestAudit | null;
  open_findings: RepositoryOpenFindings;
  open_findings_total: number;
  outbound_relationship_count: number;
  inbound_relationship_count: number;
  unknown_count: number;
  pending_confirmation_count: number;
  has_stale_intelligence: boolean;
};

export type RepositoryPortfolioResponse = {
  workspace_id: string;
  mode: "repository_intelligence_read_only";
  source: "ri_006_persistence";
  summary: {
    repositories: number;
    analyzed_repositories: number;
    repositories_with_open_findings: number;
    repositories_with_stale_intelligence: number;
    current_relationships: number;
    blocking_unknowns: number;
    pending_confirmations: number;
  };
  repositories: RepositoryPortfolioItem[];
  limits: {
    repositories: number;
  };
  truncated: boolean;
  capabilities: RepositoryIntelligenceCapabilities;
  warnings: string[];
};

export type RepositoryEvidence = {
  id: string;
  role: "supporting" | "contradicting";
  kind: string;
  source: string;
  ref: string | null;
  record_id: string;
  url: string | null;
  confidence: number;
};

export type RepositoryFact = {
  id: string;
  fact_type: string;
  claim_id: string;
  value: Record<string, unknown>;
  claim_status: string;
  confidence: number;
  lifecycle_status: "current" | "stale";
  human_resolution_status: "pending" | "confirmed" | "rejected";
  first_seen_at: string | null;
  last_seen_at: string | null;
  stale_at: string | null;
  evidence: RepositoryEvidence[];
};

export type RepositoryRelationship = {
  id: string;
  direction: "outbound" | "inbound";
  from_repository: {
    id: string;
    full_name: string;
  };
  to_repository: {
    id: string;
    full_name: string;
  } | null;
  target_full_name: string;
  relationship_type: string;
  resolution_status: "canonical" | "candidate";
  summary: string | null;
  claim_status: "observed" | "inferred";
  confidence: number;
  lifecycle_status: "current" | "stale";
  human_resolution_status: "pending" | "confirmed" | "rejected";
  first_seen_at: string | null;
  last_seen_at: string | null;
  stale_at: string | null;
  evidence: RepositoryEvidence[];
};

export type RepositoryFinding = {
  id: string;
  finding_id: string;
  rule_id: string;
  category: string;
  severity: "info" | "low" | "medium" | "high" | "critical";
  confidence: number;
  status: string;
  title: string;
  summary: string;
  recommended_next_step: string | null;
  first_seen_at: string | null;
  last_seen_at: string | null;
  resolved_at: string | null;
  evidence: RepositoryEvidence[];
};

export type RepositoryContradictionFact = {
  id: string;
  fact_type: string;
  claim_id: string;
  value: Record<string, unknown>;
  claim_status: string;
};

export type RepositoryContradiction = {
  id: string;
  contradiction_id: string;
  status: "current" | "resolved";
  confidence: number;
  summary: string;
  left_fact: RepositoryContradictionFact | null;
  right_fact: RepositoryContradictionFact | null;
  first_seen_at: string | null;
  last_seen_at: string | null;
  resolved_at: string | null;
  evidence: RepositoryEvidence[];
};

export type RepositoryConfirmation = {
  kind: "fact" | "relationship";
  id: string;
  label: string;
  claim_status: string;
  human_resolution_status: "pending" | "confirmed" | "rejected";
  evidence: RepositoryEvidence[];
};

export type RepositoryDetailResponse = {
  workspace_id: string;
  mode: "repository_intelligence_read_only";
  source: "ri_006_persistence";
  repository: RepositoryIntelligenceIdentity;
  purpose: RepositoryFact | null;
  latest_audit: RepositoryLatestAudit | null;
  facts: RepositoryFact[];
  relationships: RepositoryRelationship[];
  findings: RepositoryFinding[];
  contradictions: RepositoryContradiction[];
  unknowns: RepositoryFact[];
  confirmation_queue: RepositoryConfirmation[];
  limitations: string[];
  truncated: {
    facts: boolean;
    relationships: boolean;
    findings: boolean;
    contradictions: boolean;
    confirmation_queue: boolean;
  };
  capabilities: RepositoryIntelligenceCapabilities;
};

export type RepositoryHistoryRun = {
  id: string;
  audit_level: "L0" | "L1" | "L2";
  target_status: "exact" | "unavailable";
  commit_sha: string | null;
  metadata_snapshot_id: string | null;
  profile: string;
  policy_hash: string;
  engine_version: string;
  status: "succeeded" | "partial" | "failed" | "cancelled";
  coverage_status: "complete" | "partial";
  completed_checks: string[];
  failed_checks: string[];
  skipped_checks: string[];
  limitations: string[];
  reconciliation_applied: boolean;
  artifact_count: number;
  artifact_status: "retained" | "purged";
  started_at: string;
  completed_at: string;
};

export type RepositoryHistoryResponse = {
  workspace_id: string;
  mode: "repository_intelligence_read_only";
  source: "ri_006_persistence";
  repository: RepositoryIntelligenceIdentity;
  runs: RepositoryHistoryRun[];
  limit: number;
  truncated: boolean;
  capabilities: RepositoryIntelligenceCapabilities;
};

export type RepositoryGraphNode = {
  id: string;
  full_name: string;
  repository_type: string;
  archived: boolean;
  open_findings_total: number;
  has_stale_intelligence: boolean;
  latest_audit_at: string | null;
};

export type RepositoryGraphEdge = {
  id: string;
  from_repository_id: string;
  from_repository_full_name: string;
  to_repository_id: string | null;
  target_full_name: string;
  relationship_type: string;
  resolution_status: "canonical" | "candidate";
  claim_status: "observed" | "inferred";
  human_resolution_status: "pending" | "confirmed" | "rejected";
  confidence: number;
  summary: string | null;
};

export type RepositoryGraphResponse = {
  workspace_id: string;
  mode: "repository_intelligence_read_only";
  source: "ri_006_persistence";
  nodes: RepositoryGraphNode[];
  edges: RepositoryGraphEdge[];
  summary: {
    nodes: number;
    edges: number;
    observed_edges: number;
    inferred_edges: number;
    candidate_edges: number;
  };
  truncated: {
    nodes: boolean;
    edges: boolean;
  };
  capabilities: RepositoryIntelligenceCapabilities;
};

export function buildRepositoryIntelligencePortfolioPath(
  workspaceId: string,
  limit = 100
): string {
  return `/api/v1/workspaces/${encodeURIComponent(
    workspaceId
  )}/repository-intelligence?limit=${encodeURIComponent(String(limit))}`;
}

export function buildRepositoryIntelligenceGraphPath(
  workspaceId: string,
  repositoryLimit = 200,
  edgeLimit = 500
): string {
  const params = new URLSearchParams({
    repository_limit: String(repositoryLimit),
    edge_limit: String(edgeLimit)
  });
  return `/api/v1/workspaces/${encodeURIComponent(
    workspaceId
  )}/repository-intelligence/graph?${params.toString()}`;
}

export function buildRepositoryIntelligenceDetailPath(
  workspaceId: string,
  repositoryId: string
): string {
  return `/api/v1/workspaces/${encodeURIComponent(
    workspaceId
  )}/repository-intelligence/repositories/${encodeURIComponent(repositoryId)}`;
}

export function buildRepositoryIntelligenceHistoryPath(
  workspaceId: string,
  repositoryId: string,
  limit = 20
): string {
  return `${buildRepositoryIntelligenceDetailPath(
    workspaceId,
    repositoryId
  )}/history?limit=${encodeURIComponent(String(limit))}`;
}

export async function fetchRepositoryIntelligencePortfolio(
  workspaceId: string,
  options: ApiFetchOptions = {}
): Promise<RepositoryPortfolioResponse> {
  return apiFetch<RepositoryPortfolioResponse>(
    buildRepositoryIntelligencePortfolioPath(workspaceId),
    options
  );
}

export async function fetchRepositoryIntelligenceGraph(
  workspaceId: string,
  options: ApiFetchOptions = {}
): Promise<RepositoryGraphResponse> {
  return apiFetch<RepositoryGraphResponse>(
    buildRepositoryIntelligenceGraphPath(workspaceId),
    options
  );
}

export async function fetchRepositoryIntelligenceDetail(
  workspaceId: string,
  repositoryId: string,
  options: ApiFetchOptions = {}
): Promise<RepositoryDetailResponse> {
  return apiFetch<RepositoryDetailResponse>(
    buildRepositoryIntelligenceDetailPath(workspaceId, repositoryId),
    options
  );
}

export async function fetchRepositoryIntelligenceHistory(
  workspaceId: string,
  repositoryId: string,
  options: ApiFetchOptions = {}
): Promise<RepositoryHistoryResponse> {
  return apiFetch<RepositoryHistoryResponse>(
    buildRepositoryIntelligenceHistoryPath(workspaceId, repositoryId),
    options
  );
}

export function normalizeRepositoryIntelligenceRepositoryId(
  value: string | null | undefined
): string | null {
  if (typeof value !== "string") {
    return null;
  }
  const normalized = value.trim().toLowerCase();
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(
    normalized
  )
    ? normalized
    : null;
}
