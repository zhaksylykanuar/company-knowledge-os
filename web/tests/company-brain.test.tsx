import assert from "node:assert/strict";
import test from "node:test";

import { renderToStaticMarkup } from "react-dom/server";

import {
  buildWorkspaceCompanyBrainPath,
  fetchCompanyBrain
} from "../lib/api";
import type { CompanyBrainResponse } from "../lib/types";
import { CompanyBrainPanelView } from "../components/CompanyBrainPanel";

const sampleBrain: CompanyBrainResponse = {
  workspace_id: "workspace-123",
  mode: "github_first_canonical",
  source: "canonical_github_company_brain",
  summary: {
    repositories: 1,
    open_issues: 1,
    open_pull_requests: 1,
    closed_issues: 1,
    merged_pull_requests: 1
  },
  repositories: [
    {
      id: "repo-row-1",
      provider: "github",
      external_id: "qtwin-io/founderos-api",
      name: "founderos-api",
      full_name: "qtwin-io/founderos-api",
      visibility: "private",
      archived: false,
      source_url: "https://github.com/qtwin-io/founderos-api",
      last_activity_at: "2026-06-24T10:00:00+00:00",
      source_refs: [
        {
          id: "repo-source-1:0",
          kind: "repository_inventory_snapshot",
          source: "canonical_source_record",
          label: "repo-snapshot-1",
          url: "https://github.com/qtwin-io/founderos-api",
          record_type: "repository",
          record_id: "repo-source-1"
        }
      ]
    }
  ],
  work: {
    issues: [
      {
        id: "issue-row-1",
        type: "issue",
        external_id: "qtwin-io/founderos-api#issue/42",
        number: 42,
        title: "Investigate issue 42",
        state: "open",
        repository_full_name: "qtwin-io/founderos-api",
        repository_external_id: "qtwin-io/founderos-api",
        source_url: "https://github.com/qtwin-io/founderos-api/issues/42",
        updated_at: "2026-06-24T10:00:00+00:00",
        source_refs: [
          {
            id: "issue-source-1:0",
            kind: "github_issue",
            source: "github",
            label: "qtwin-io/founderos-api#issue/42",
            url: "https://github.com/qtwin-io/founderos-api/issues/42",
            record_type: "issue",
            record_id: "issue-source-1"
          }
        ]
      }
    ],
    pull_requests: [
      {
        id: "pr-row-1",
        type: "pull_request",
        external_id: "qtwin-io/founderos-api#pull/7",
        number: 7,
        title: "Ship PR 7",
        state: "open",
        repository_full_name: "qtwin-io/founderos-api",
        repository_external_id: "qtwin-io/founderos-api",
        source_url: "https://github.com/qtwin-io/founderos-api/pull/7",
        updated_at: "2026-06-24T10:00:00+00:00",
        source_refs: [
          {
            id: "pr-source-1:0",
            kind: "github_pull_request",
            source: "github",
            label: "qtwin-io/founderos-api#pull/7",
            url: "https://github.com/qtwin-io/founderos-api/pull/7",
            record_type: "pull_request",
            record_id: "pr-source-1"
          }
        ]
      }
    ],
    recent: [
      {
        id: "merged-pr-row-1",
        type: "pull_request",
        external_id: "qtwin-io/founderos-api#pull/8",
        number: 8,
        title: "Merge PR 8",
        state: "merged",
        repository_full_name: "qtwin-io/founderos-api",
        repository_external_id: "qtwin-io/founderos-api",
        source_url: "https://github.com/qtwin-io/founderos-api/pull/8",
        updated_at: "2026-06-24T10:00:00+00:00",
        source_refs: []
      }
    ]
  },
  evidence: [
    {
      id: "repo-source-1:0",
      kind: "repository_inventory_snapshot",
      source: "canonical_source_record",
      label: "repo-snapshot-1",
      url: "https://github.com/qtwin-io/founderos-api",
      record_type: "repository",
      record_id: "repo-source-1"
    },
    {
      id: "issue-source-1:0",
      kind: "github_issue",
      source: "github",
      label: "qtwin-io/founderos-api#issue/42",
      url: "https://github.com/qtwin-io/founderos-api/issues/42",
      record_type: "issue",
      record_id: "issue-source-1"
    }
  ],
  capabilities: {
    live_github_oauth: false,
    live_provider_sync: false,
    local_sync: true,
    llm_briefing: false
  },
  is_live: false,
  llm_used: false,
  warnings: []
};

const emptyBrain: CompanyBrainResponse = {
  ...sampleBrain,
  summary: {
    repositories: 0,
    open_issues: 0,
    open_pull_requests: 0,
    closed_issues: 0,
    merged_pull_requests: 0
  },
  repositories: [],
  work: {
    issues: [],
    pull_requests: [],
    recent: []
  },
  evidence: [],
  warnings: ["No canonical GitHub records have been synced for this workspace yet."]
};

function renderPanel(
  props: Partial<Parameters<typeof CompanyBrainPanelView>[0]> = {}
): string {
  return renderToStaticMarkup(
    <CompanyBrainPanelView
      data={props.data ?? sampleBrain}
      error={props.error ?? null}
      onRetry={props.onRetry}
      status={props.status ?? "ready"}
    />
  );
}

test("builds the workspace Company Brain URL", () => {
  assert.equal(
    buildWorkspaceCompanyBrainPath("workspace-123"),
    "/api/v1/workspaces/workspace-123/company-brain"
  );
});

test("fetches and parses Company Brain payloads", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (input) => {
    assert.equal(
      String(input),
      "http://localhost/api/v1/workspaces/workspace-123/company-brain"
    );
    return new Response(JSON.stringify(sampleBrain), {
      headers: { "Content-Type": "application/json" },
      status: 200
    });
  }) as typeof fetch;

  try {
    const payload = await fetchCompanyBrain("workspace-123", {
      includeOwnerEmail: false
    });
    assert.equal(payload.mode, "github_first_canonical");
    assert.equal(payload.summary.open_pull_requests, 1);
    assert.equal(payload.capabilities.live_provider_sync, false);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("renders loading state", () => {
  const html = renderPanel({ data: null, status: "loading" });
  assert.match(html, /Loading Company Brain/);
});

test("renders missing settings state", () => {
  const html = renderPanel({ data: null, status: "missing" });
  assert.match(html, /Workspace settings required/);
  assert.match(html, /workspace ID, owner email, and operator API key/);
});

test("renders empty state", () => {
  const html = renderPanel({ data: emptyBrain, status: "empty" });
  assert.match(html, /No Company Brain data yet/);
  assert.match(html, /No canonical GitHub records are synced yet/);
});

test("renders backend error state with retry", () => {
  const html = renderPanel({
    data: null,
    error: "backend unavailable",
    onRetry: () => undefined,
    status: "error"
  });
  assert.match(html, /Company Brain unavailable/);
  assert.match(html, /backend unavailable/);
  assert.match(html, /Retry/);
});

test("renders summary counts, repositories, issues, and PRs", () => {
  const html = renderPanel();
  assert.match(html, /Evidence-backed GitHub state/);
  assert.match(html, /Repositories/);
  assert.match(html, /Open issues/);
  assert.match(html, /Open PRs/);
  assert.match(html, /1 \/ 1/);
  assert.match(html, /qtwin-io\/founderos-api/);
  assert.match(html, /Investigate issue 42/);
  assert.match(html, /Ship PR 7/);
  assert.match(html, /Merge PR 8/);
});

test("renders evidence and source refs without fake company facts", () => {
  const html = renderPanel();
  assert.match(html, /Evidence \/ sources/);
  assert.match(html, /repo-snapshot-1/);
  assert.match(html, /qtwin-io\/founderos-api#issue\/42/);
  assert.match(html, /github_issue/);
  assert.match(html, /Canonical synced record; no separate source ref returned/);
  assert.doesNotMatch(html, /source_events/);
  assert.doesNotMatch(html, /AI knows/);
  assert.doesNotMatch(html, /strategic priority/);
});

test("renders deterministic capability boundary", () => {
  const html = renderPanel();
  assert.match(html, /Deterministic/);
  assert.match(html, /Live OAuth: not enabled/);
  assert.match(html, /Provider sync: not enabled/);
  assert.match(html, /AI briefing: not enabled/);
});
