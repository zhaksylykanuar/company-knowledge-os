import assert from "node:assert/strict";
import test from "node:test";

import { renderToStaticMarkup } from "react-dom/server";

import RepositoryIntelligencePage from "../app/company-brain/repositories/page";
import {
  filterRepositoryPortfolio,
  RelationshipGraph,
  RepositoryIntelligencePageClient,
  RepositoryIntelligenceView
} from "../components/RepositoryIntelligencePageClient";
import {
  buildRepositoryIntelligenceDetailPath,
  buildRepositoryIntelligenceGraphPath,
  buildRepositoryIntelligenceHistoryPath,
  buildRepositoryIntelligencePortfolioPath,
  fetchRepositoryIntelligenceDetail,
  fetchRepositoryIntelligenceGraph,
  fetchRepositoryIntelligenceHistory,
  fetchRepositoryIntelligencePortfolio,
  normalizeRepositoryIntelligenceRepositoryId,
  type RepositoryDetailResponse,
  type RepositoryGraphResponse,
  type RepositoryHistoryResponse,
  type RepositoryPortfolioResponse
} from "../lib/repository-intelligence";

const WORKSPACE_ID = "11111111-1111-4111-8111-111111111111";
const REPOSITORY_ID = "22222222-2222-4222-8222-222222222222";
const TARGET_ID = "33333333-3333-4333-8333-333333333333";

const capabilities = {
  provider_calls: false,
  repository_reads: false,
  target_execution: false,
  external_writes: false,
  llm_used: false,
  human_resolution_writes: false
} as const;

const portfolio: RepositoryPortfolioResponse = {
  workspace_id: WORKSPACE_ID,
  mode: "repository_intelligence_read_only",
  source: "ri_006_persistence",
  summary: {
    repositories: 2,
    analyzed_repositories: 1,
    repositories_with_open_findings: 1,
    repositories_with_stale_intelligence: 1,
    current_relationships: 1,
    blocking_unknowns: 1,
    pending_confirmations: 2
  },
  repositories: [
    {
      id: REPOSITORY_ID,
      provider: "github",
      external_id: "source-1",
      name: "orders-service",
      full_name: "synthetic-company/orders-service",
      default_branch: "main",
      visibility: "private",
      archived: false,
      source_url: "https://github.com/synthetic-company/orders-service",
      last_activity_at: "2026-08-03T10:00:00Z",
      purpose_summary: "Synthetic backend service for orders.",
      operational_summary: "Provides an order API.",
      repository_type: "backend_service",
      purpose_status: "observed",
      purpose_confidence: 0.96,
      product_candidates: ["Commerce"],
      owner_candidates: ["Platform Team"],
      has_confirmed_owner: false,
      latest_audit: {
        id: "44444444-4444-4444-8444-444444444444",
        audit_level: "L1",
        target_status: "exact",
        commit_sha: "1".repeat(40),
        metadata_snapshot_id: null,
        profile: "backend_service",
        engine_version: "ri-test-1",
        status: "succeeded",
        coverage_status: "complete",
        reconciliation_applied: true,
        completed_at: "2026-08-03T10:00:00Z",
        artifact_status: "retained"
      },
      open_findings: {
        critical: 0,
        high: 0,
        medium: 1,
        low: 0,
        info: 0
      },
      open_findings_total: 1,
      outbound_relationship_count: 1,
      inbound_relationship_count: 0,
      unknown_count: 1,
      pending_confirmation_count: 2,
      has_stale_intelligence: false
    },
    {
      id: TARGET_ID,
      provider: "github",
      external_id: "target-1",
      name: "catalog-service",
      full_name: "synthetic-company/catalog-service",
      default_branch: "main",
      visibility: "internal",
      archived: true,
      source_url: null,
      last_activity_at: null,
      purpose_summary: null,
      operational_summary: null,
      repository_type: "unknown",
      purpose_status: "unavailable",
      purpose_confidence: 0,
      product_candidates: [],
      owner_candidates: [],
      has_confirmed_owner: false,
      latest_audit: null,
      open_findings: {
        critical: 0,
        high: 0,
        medium: 0,
        low: 0,
        info: 0
      },
      open_findings_total: 0,
      outbound_relationship_count: 0,
      inbound_relationship_count: 1,
      unknown_count: 0,
      pending_confirmation_count: 0,
      has_stale_intelligence: true
    }
  ],
  limits: { repositories: 100 },
  truncated: false,
  capabilities,
  warnings: []
};

const evidence = {
  id: "55555555-5555-4555-8555-555555555555",
  role: "supporting" as const,
  kind: "repository_manifest",
  source: "github",
  ref: "synthetic-company/orders-service@sha:pyproject.toml",
  record_id: "66666666-6666-4666-8666-666666666666",
  url: "https://github.com/synthetic-company/orders-service/blob/sha/pyproject.toml",
  confidence: 1
};

const detail: RepositoryDetailResponse = {
  workspace_id: WORKSPACE_ID,
  mode: "repository_intelligence_read_only",
  source: "ri_006_persistence",
  repository: {
    ...portfolio.repositories[0]
  },
  purpose: {
    id: "77777777-7777-4777-8777-777777777777",
    fact_type: "purpose",
    claim_id: "purpose.primary",
    value: {
      summary: "Synthetic backend service for orders.",
      operational_summary: "Provides an order API.",
      repository_type: "backend_service"
    },
    claim_status: "observed",
    confidence: 0.96,
    lifecycle_status: "current",
    human_resolution_status: "pending",
    first_seen_at: "2026-08-03T10:00:00Z",
    last_seen_at: "2026-08-03T10:00:00Z",
    stale_at: null,
    evidence: [evidence]
  },
  latest_audit: portfolio.repositories[0]?.latest_audit ?? null,
  facts: [
    {
      id: "88888888-8888-4888-8888-888888888888",
      fact_type: "responsibility",
      claim_id: "responsibility.orders",
      value: {
        claim_type: "owns",
        summary: "Owns the synthetic order API.",
        details: ["Creates synthetic orders."]
      },
      claim_status: "observed",
      confidence: 0.93,
      lifecycle_status: "current",
      human_resolution_status: "pending",
      first_seen_at: "2026-08-03T10:00:00Z",
      last_seen_at: "2026-08-03T10:00:00Z",
      stale_at: null,
      evidence: [evidence]
    }
  ],
  relationships: [
    {
      id: "99999999-9999-4999-8999-999999999999",
      direction: "outbound",
      from_repository: {
        id: REPOSITORY_ID,
        full_name: "synthetic-company/orders-service"
      },
      to_repository: {
        id: TARGET_ID,
        full_name: "synthetic-company/catalog-service"
      },
      target_full_name: "synthetic-company/catalog-service",
      relationship_type: "calls_api_of",
      resolution_status: "canonical",
      summary: "Calls the catalog service.",
      claim_status: "inferred",
      confidence: 0.82,
      lifecycle_status: "current",
      human_resolution_status: "pending",
      first_seen_at: "2026-08-03T10:00:00Z",
      last_seen_at: "2026-08-03T10:00:00Z",
      stale_at: null,
      evidence: [evidence]
    }
  ],
  findings: [
    {
      id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
      finding_id: "finding.typecheck",
      rule_id: "ri.ci.typecheck",
      category: "quality",
      severity: "medium",
      confidence: 0.88,
      status: "new",
      title: "CI omits type checking",
      summary: "The workflow has no type-check step.",
      recommended_next_step: "Add a type-check command.",
      first_seen_at: "2026-08-03T10:00:00Z",
      last_seen_at: "2026-08-03T10:00:00Z",
      resolved_at: null,
      evidence: [evidence]
    }
  ],
  contradictions: [],
  cross_source: {
    summary: {
      sources_considered: 3,
      comparisons: 3,
      agreements: 1,
      contradictions: 1,
      insufficient_evidence: 1,
      rejected_claim_sets: 1
    },
    comparisons: [
      {
        id: "c".repeat(64),
        status: "agreement",
        summary:
          "Source claim agrees with RI: purpose.primary.repository_type=backend_service.",
        source: {
          source_type: "task",
          provider: "github",
          record_id: "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
          ref: "issue-1",
          url: "https://github.com/synthetic-company/orders-service/issues/1",
          observed_at: "2026-08-03T10:00:00Z"
        },
        source_claim: {
          fact_type: "purpose",
          claim_id: "purpose.primary",
          field: "repository_type",
          expected_value: "backend_service",
          summary: "The GitHub issue describes a backend service.",
          confidence: 0.9
        },
        repository_fact: {
          id: "77777777-7777-4777-8777-777777777777",
          fact_type: "purpose",
          claim_id: "purpose.primary",
          field: "repository_type",
          actual_value: "backend_service",
          claim_status: "observed",
          confidence: 0.96,
          human_resolution_status: "pending"
        },
        source_evidence: [
          {
            ...evidence,
            id: "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
            kind: "github_issue",
            record_id: "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
          }
        ],
        repository_evidence: [evidence]
      },
      {
        id: "d".repeat(64),
        status: "contradiction",
        summary:
          "Source claim asserts purpose.primary.repository_type=frontend_application, while RI records backend_service.",
        source: {
          source_type: "task",
          provider: "jira",
          record_id: "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
          ref: "FOS-42",
          url: "https://jira.example/browse/FOS-42",
          observed_at: "2026-08-03T10:00:00Z"
        },
        source_claim: {
          fact_type: "purpose",
          claim_id: "purpose.primary",
          field: "repository_type",
          expected_value: "frontend_application",
          summary: "Jira describes this as a frontend application.",
          confidence: 0.8
        },
        repository_fact: {
          id: "77777777-7777-4777-8777-777777777777",
          fact_type: "purpose",
          claim_id: "purpose.primary",
          field: "repository_type",
          actual_value: "backend_service",
          claim_status: "observed",
          confidence: 0.96,
          human_resolution_status: "pending"
        },
        source_evidence: [
          {
            ...evidence,
            id: "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
            kind: "jira_issue",
            source: "jira",
            record_id: "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
            url: "https://jira.example/browse/FOS-42"
          }
        ],
        repository_evidence: [evidence]
      },
      {
        id: "e".repeat(64),
        status: "insufficient_evidence",
        summary:
          "No current RI fact exactly matches dependency_consumed:dependency.cache.claim_type.",
        source: {
          source_type: "document",
          provider: "internal",
          record_id: "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
          ref: "Architecture note",
          url: null,
          observed_at: "2026-08-03T10:00:00Z"
        },
        source_claim: {
          fact_type: "dependency_consumed",
          claim_id: "dependency.cache",
          field: "claim_type",
          expected_value: "redis",
          summary: "The architecture note declares a Redis dependency.",
          confidence: 0.7
        },
        repository_fact: null,
        source_evidence: [
          {
            ...evidence,
            id: "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
            kind: "document",
            source: "internal",
            record_id: "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
            url: null
          }
        ],
        repository_evidence: []
      }
    ],
    rejected_claim_sets: [
      {
        source: {
          source_type: "document",
          provider: "internal",
          record_id: "ffffffff-ffff-4fff-8fff-ffffffffffff",
          ref: "Malformed claim note",
          url: null,
          observed_at: "2026-08-03T10:00:00Z"
        },
        error_code: "claim_set_invalid_json"
      }
    ],
    truncated: {
      sources: false,
      comparisons: false,
      rejected_claim_sets: false
    },
    contract: {
      claim_set_schema: "repository_cross_source_claim_set.v1",
      claim_schema: "repository_cross_source_claim.v1",
      exact_repository_identity_required: true,
      free_text_inference: false,
      fuzzy_matching: false,
      persistence_write: false
    }
  },
  unknowns: [
    {
      id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
      fact_type: "unknown",
      claim_id: "unknown.owner",
      value: { question: "Who owns this service?" },
      claim_status: "insufficient_evidence",
      confidence: 0,
      lifecycle_status: "current",
      human_resolution_status: "pending",
      first_seen_at: "2026-08-03T10:00:00Z",
      last_seen_at: "2026-08-03T10:00:00Z",
      stale_at: null,
      evidence: []
    }
  ],
  confirmation_queue: [
    {
      kind: "relationship",
      id: "99999999-9999-4999-8999-999999999999",
      label: "Calls the catalog service.",
      claim_status: "inferred",
      human_resolution_status: "pending",
      evidence: [evidence]
    }
  ],
  limitations: ["Static synthetic analysis only."],
  truncated: {
    facts: false,
    relationships: false,
    findings: false,
    contradictions: false,
    confirmation_queue: false
  },
  capabilities
};

const history: RepositoryHistoryResponse = {
  workspace_id: WORKSPACE_ID,
  mode: "repository_intelligence_read_only",
  source: "ri_006_persistence",
  repository: detail.repository,
  runs: [
    {
      id: "44444444-4444-4444-8444-444444444444",
      audit_level: "L1",
      target_status: "exact",
      commit_sha: "1".repeat(40),
      metadata_snapshot_id: null,
      profile: "backend_service",
      policy_hash: "a".repeat(64),
      engine_version: "ri-test-1",
      status: "succeeded",
      coverage_status: "complete",
      completed_checks: ["manifest", "relationship"],
      failed_checks: [],
      skipped_checks: [],
      limitations: ["Static synthetic analysis only."],
      reconciliation_applied: true,
      artifact_count: 1,
      artifact_status: "retained",
      started_at: "2026-08-03T09:59:40Z",
      completed_at: "2026-08-03T10:00:00Z"
    }
  ],
  limit: 20,
  truncated: false,
  capabilities
};

const graph: RepositoryGraphResponse = {
  workspace_id: WORKSPACE_ID,
  mode: "repository_intelligence_read_only",
  source: "ri_006_persistence",
  nodes: portfolio.repositories.map((repository) => ({
    id: repository.id,
    full_name: repository.full_name,
    repository_type: repository.repository_type,
    archived: repository.archived,
    open_findings_total: repository.open_findings_total,
    has_stale_intelligence: repository.has_stale_intelligence,
    latest_audit_at: repository.latest_audit?.completed_at ?? null
  })),
  edges: [
    {
      id: "99999999-9999-4999-8999-999999999999",
      from_repository_id: REPOSITORY_ID,
      from_repository_full_name: "synthetic-company/orders-service",
      to_repository_id: TARGET_ID,
      target_full_name: "synthetic-company/catalog-service",
      relationship_type: "calls_api_of",
      resolution_status: "canonical",
      claim_status: "inferred",
      human_resolution_status: "pending",
      confidence: 0.82,
      summary: "Calls the catalog service."
    }
  ],
  summary: {
    nodes: 2,
    edges: 1,
    observed_edges: 0,
    inferred_edges: 1,
    candidate_edges: 0
  },
  truncated: {
    nodes: false,
    edges: false
  },
  capabilities
};

test("builds the bounded Repository Intelligence API paths", () => {
  assert.equal(
    buildRepositoryIntelligencePortfolioPath(WORKSPACE_ID),
    `/api/v1/workspaces/${WORKSPACE_ID}/repository-intelligence?limit=100`
  );
  assert.equal(
    buildRepositoryIntelligenceDetailPath(WORKSPACE_ID, REPOSITORY_ID),
    `/api/v1/workspaces/${WORKSPACE_ID}/repository-intelligence/repositories/${REPOSITORY_ID}`
  );
  assert.equal(
    buildRepositoryIntelligenceHistoryPath(WORKSPACE_ID, REPOSITORY_ID),
    `/api/v1/workspaces/${WORKSPACE_ID}/repository-intelligence/repositories/${REPOSITORY_ID}/history?limit=20`
  );
  assert.equal(
    buildRepositoryIntelligenceGraphPath(WORKSPACE_ID),
    `/api/v1/workspaces/${WORKSPACE_ID}/repository-intelligence/graph?repository_limit=200&edge_limit=500`
  );
});

test("fetches portfolio, detail, history, and graph through same-origin GETs", async () => {
  const originalFetch = globalThis.fetch;
  const responses = new Map<string, unknown>([
    [
      `http://localhost${buildRepositoryIntelligencePortfolioPath(WORKSPACE_ID)}`,
      portfolio
    ],
    [
      `http://localhost${buildRepositoryIntelligenceDetailPath(
        WORKSPACE_ID,
        REPOSITORY_ID
      )}`,
      detail
    ],
    [
      `http://localhost${buildRepositoryIntelligenceHistoryPath(
        WORKSPACE_ID,
        REPOSITORY_ID
      )}`,
      history
    ],
    [
      `http://localhost${buildRepositoryIntelligenceGraphPath(WORKSPACE_ID)}`,
      graph
    ]
  ]);
  globalThis.fetch = (async (input, init) => {
    assert.equal(init?.method, undefined);
    const payload = responses.get(String(input));
    assert.ok(payload, `unexpected request ${String(input)}`);
    return new Response(JSON.stringify(payload), {
      headers: { "Content-Type": "application/json" },
      status: 200
    });
  }) as typeof fetch;

  try {
    assert.equal(
      (await fetchRepositoryIntelligencePortfolio(WORKSPACE_ID)).summary
        .repositories,
      2
    );
    assert.equal(
      (
        await fetchRepositoryIntelligenceDetail(
          WORKSPACE_ID,
          REPOSITORY_ID
        )
      ).findings[0]?.severity,
      "medium"
    );
    assert.equal(
      (
        await fetchRepositoryIntelligenceHistory(
          WORKSPACE_ID,
          REPOSITORY_ID
        )
      ).runs[0]?.artifact_count,
      1
    );
    assert.equal(
      (await fetchRepositoryIntelligenceGraph(WORKSPACE_ID)).summary
        .inferred_edges,
      1
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("filters the loaded portfolio without provider calls", () => {
  assert.deepEqual(
    filterRepositoryPortfolio(portfolio.repositories, {
      query: "order",
      repositoryType: "backend_service",
      product: "Commerce",
      owner: "unresolved",
      lifecycle: "active",
      severity: "medium",
      staleness: "fresh"
    }).map((repository) => repository.id),
    [REPOSITORY_ID]
  );
  assert.deepEqual(
    filterRepositoryPortfolio(portfolio.repositories, {
      query: "",
      repositoryType: "all",
      product: "all",
      owner: "all",
      lifecycle: "archived",
      severity: "all",
      staleness: "stale"
    }).map((repository) => repository.id),
    [TARGET_ID]
  );
});

test("renders portfolio, progressive detail, evidence states, and boundaries", () => {
  const html = renderToStaticMarkup(
    <RepositoryIntelligenceView
      detail={detail}
      detailError={null}
      detailStatus="ready"
      error={null}
      graph={graph}
      history={history}
      onSelectRepository={() => undefined}
      portfolio={portfolio}
      selectedRepositoryId={REPOSITORY_ID}
      status="ready"
    />
  );

  assert.match(html, /Карта репозиториев/);
  assert.match(html, /synthetic-company\/orders-service/);
  assert.match(html, /Synthetic backend service for orders/);
  assert.match(html, /Обязанности · 1/);
  assert.match(html, /Направленные связи · 1/);
  assert.match(html, /Риски и operability · 1/);
  assert.match(html, /Неизвестные и очередь подтверждения · 2/);
  assert.match(html, /Между источниками · 3/);
  assert.match(html, /agreement/);
  assert.match(html, /contradiction/);
  assert.match(html, /insufficient_evidence/);
  assert.match(html, /FOS-42/);
  assert.match(html, /claim_set_invalid_json/);
  assert.match(html, /История аудита · 1/);
  assert.match(html, /inferred/);
  assert.match(html, /Evidence: Owns the synthetic order API/);
  assert.match(html, /Raw source bodies/);
  assert.doesNotMatch(html, /private source body/);
  assert.doesNotMatch(html, /artifact_manifest/);
});

test("renders graph distinctions and empty/error states accessibly", () => {
  const graphHtml = renderToStaticMarkup(<RelationshipGraph graph={graph} />);
  assert.match(graphHtml, /synthetic-company\/orders-service/);
  assert.match(graphHtml, /synthetic-company\/catalog-service/);
  assert.match(graphHtml, /calls_api_of/);
  assert.match(graphHtml, /inferred · confidence 82%/);
  assert.match(graphHtml, /observed/);
  assert.match(graphHtml, /human confirmed/);
  assert.match(graphHtml, /unresolved candidate/);

  const readyHtml = renderToStaticMarkup(
    <RepositoryIntelligenceView
      detail={detail}
      detailError={null}
      detailStatus="ready"
      error={null}
      graph={graph}
      history={history}
      onSelectRepository={() => undefined}
      portfolio={portfolio}
      selectedRepositoryId={REPOSITORY_ID}
      status="ready"
    />
  );
  assert.match(readyHtml, /role="tablist"/);
  assert.match(readyHtml, /aria-selected="true"/);
  assert.match(readyHtml, /Направленные связи/);

  const emptyHtml = renderToStaticMarkup(
    <RepositoryIntelligenceView
      detail={null}
      detailError={null}
      detailStatus="idle"
      error={null}
      graph={null}
      history={null}
      onSelectRepository={() => undefined}
      portfolio={{ ...portfolio, repositories: [] }}
      selectedRepositoryId={null}
      status="empty"
    />
  );
  assert.match(emptyHtml, /Репозитории пока не подготовлены/);

  const errorHtml = renderToStaticMarkup(
    <RepositoryIntelligenceView
      detail={null}
      detailError={null}
      detailStatus="idle"
      error="backend unavailable"
      graph={null}
      history={null}
      onRetry={() => undefined}
      onSelectRepository={() => undefined}
      portfolio={null}
      selectedRepositoryId={null}
      status="error"
    />
  );
  assert.match(errorHtml, /backend unavailable/);
  assert.match(errorHtml, /Повторить/);
});

test("repository route preserves only a valid UUID selector", async () => {
  const selected = await RepositoryIntelligencePage({
    searchParams: Promise.resolve({ repository: REPOSITORY_ID })
  });
  const invalid = await RepositoryIntelligencePage({
    searchParams: Promise.resolve({ repository: "not-a-uuid\u0000" })
  });
  assert.equal(selected.type, RepositoryIntelligencePageClient);
  assert.equal(selected.props.initialRepositoryId, REPOSITORY_ID);
  assert.equal(invalid.props.initialRepositoryId, null);
  assert.equal(
    normalizeRepositoryIntelligenceRepositoryId(REPOSITORY_ID.toUpperCase()),
    REPOSITORY_ID
  );
  assert.equal(
    normalizeRepositoryIntelligenceRepositoryId("javascript:alert(1)"),
    null
  );
});
