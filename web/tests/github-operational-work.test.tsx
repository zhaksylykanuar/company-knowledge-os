import assert from "node:assert/strict";
import test from "node:test";

import { renderToStaticMarkup } from "react-dom/server";

import {
  buildWorkspaceGitHubOperationalWorkPath,
  fetchGitHubOperationalWork
} from "../lib/api";
import { M } from "../lib/messages";
import type { GitHubOperationalWorkResponse } from "../lib/types";
import {
  formatSourceTimestamp,
  GitHubOperationalWorkPanelView
} from "../components/GitHubOperationalWorkPanel";

const sampleWork: GitHubOperationalWorkResponse = {
  issues: [
    {
      id: "issue-row-1",
      external_id: "qtwin-io/founderos-api#issue/42",
      number: 42,
      title: "Investigate failing sync",
      state: "open",
      source_url: "https://github.com/qtwin-io/founderos-api/issues/42",
      repository_full_name: "qtwin-io/founderos-api",
      repository_external_id: "qtwin-io/founderos-api",
      source_record_id: "source-record-issue-1",
      source_updated_at: "2026-06-24T08:30:00+00:00",
      metadata: {}
    }
  ],
  pull_requests: [
    {
      id: "pr-row-1",
      external_id: "qtwin-io/founderos-api#pull/7",
      number: 7,
      title: "Wire operational dashboard",
      state: "open",
      source_url: "https://github.com/qtwin-io/founderos-api/pull/7",
      repository_id: "repo-row-1",
      repository_full_name: "qtwin-io/founderos-api",
      repository_external_id: "qtwin-io/founderos-api",
      created_at_source: "2026-06-24T07:00:00+00:00",
      updated_at_source: "2026-06-24T09:00:00+00:00",
      merged_at_source: null,
      metadata: {}
    }
  ],
  counts: {
    issues: 1,
    pull_requests: 1
  },
  state: "open",
  source: "canonical_github_operational_work",
  is_live: false,
  warnings: []
};

const emptyWork: GitHubOperationalWorkResponse = {
  issues: [],
  pull_requests: [],
  counts: {
    issues: 0,
    pull_requests: 0
  },
  state: "open",
  source: "canonical_github_operational_work",
  is_live: false,
  warnings: []
};

function renderPanel(
  props: Partial<Parameters<typeof GitHubOperationalWorkPanelView>[0]> = {}
): string {
  return renderToStaticMarkup(
    <GitHubOperationalWorkPanelView
      data={props.data ?? sampleWork}
      error={props.error ?? null}
      onRetry={props.onRetry}
      onStateChange={props.onStateChange}
      selectedState={props.selectedState ?? "open"}
      status={props.status ?? "ready"}
    />
  );
}

test("builds the workspace operational work URL", () => {
  assert.equal(
    buildWorkspaceGitHubOperationalWorkPath("workspace-123", {
      limit: 25,
      state: "merged"
    }),
    "/api/v1/workspaces/workspace-123/github/operational-work?state=merged&limit=25"
  );
});

test("fetches and parses operational work payloads", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (input) => {
    assert.equal(
      String(input),
      "http://localhost/api/v1/workspaces/workspace-123/github/operational-work?state=open&limit=50"
    );
    return new Response(JSON.stringify(sampleWork), {
      headers: { "Content-Type": "application/json" },
      status: 200
    });
  }) as typeof fetch;

  try {
    const payload = await fetchGitHubOperationalWork(
      "workspace-123",
      { limit: 50, state: "open" },
      {}
    );
    assert.equal(payload.issues[0]?.title, "Investigate failing sync");
    assert.equal(payload.pull_requests[0]?.repository_full_name, "qtwin-io/founderos-api");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("renders loading state", () => {
  const html = renderPanel({ data: null, status: "loading" });
  assert.ok(html.includes(M.githubWork.loading));
  assert.match(html, /aria-busy="true"/);
  assert.match(html, /aria-live="polite"/);
  assert.match(html, /role="status"/);
});

test("renders a truthful zero-count sample for an empty filter", () => {
  const html = renderPanel({ data: emptyWork, status: "empty" });
  assert.match(html, /data-scope="loaded-sample"/);
  assert.ok(html.includes(M.githubWork.noIssuesForFilter));
  assert.ok(html.includes(M.githubWork.noPullRequestsForFilter));
  assert.doesNotMatch(html, new RegExp(M.githubWork.emptyTitle));
});

test("renders backend error state with retry affordance", () => {
  const html = renderPanel({
    data: null,
    error: "backend unavailable",
    onRetry: () => undefined,
    status: "error"
  });
  assert.ok(html.includes(M.githubWork.unavailableTitle));
  assert.match(html, /backend unavailable/);
  assert.ok(html.includes(M.common.retry));
  assert.match(html, /<details class="github-work-pulse__error-details">/);
});

test("renders issue and pull request records with repository identity", () => {
  const html = renderPanel();
  assert.match(html, /Investigate failing sync/);
  assert.match(html, /Wire operational dashboard/);
  assert.match(html, /qtwin-io\/founderos-api/);
  assert.match(html, /#42/);
  assert.match(html, /#7/);
  assert.match(html, /<ul class="work-list github-work-pulse__list">/);
  assert.match(
    html,
    new RegExp(`${M.githubWork.metaState}: ${M.githubWork.stateOpen}`)
  );
  assert.doesNotMatch(html, /source_events/);
  assert.doesNotMatch(html, /Placeholder/);
});

test("renders issue and PR counts as a loaded sample without total claims", () => {
  const html = renderPanel();
  assert.match(html, /class="github-work-pulse__snapshot"/);
  assert.match(html, /data-scope="loaded-sample"/);
  assert.ok(html.includes(M.githubWork.sampleNote));
  assert.equal((html.match(/<meter/g) ?? []).length, 2);
  assert.match(html, /max="2" value="1"/);
  assert.ok(html.includes("1 из 2 записей текущего фильтра."));
  assert.doesNotMatch(html, />Всего</);
});

test("renders open, closed, merged, and all filters", () => {
  const html = renderPanel({ selectedState: "merged" });
  assert.ok(html.includes(M.githubWork.stateOpen));
  assert.ok(html.includes(M.githubWork.stateClosed));
  assert.ok(html.includes(M.githubWork.stateMerged));
  assert.ok(html.includes(M.githubWork.stateAll));
  assert.match(html, /aria-pressed="true"/);
});

test("keeps long loaded lists compact behind a native disclosure", () => {
  const issues = Array.from({ length: 6 }, (_, index) => ({
    ...sampleWork.issues[0]!,
    id: `issue-row-${index + 1}`,
    number: index + 1,
    title: `Issue ${index + 1}`
  }));
  const html = renderPanel({
    data: {
      ...sampleWork,
      counts: { issues: issues.length, pull_requests: 1 },
      issues
    }
  });

  assert.match(html, /<details class="github-work-pulse__more">/);
  assert.match(
    html,
    new RegExp(`<summary>${M.githubWork.issuesTitle} \\+2</summary>`)
  );
});

test("keeps backend warnings available without crowding the pulse", () => {
  const html = renderPanel({
    data: {
      ...sampleWork,
      warnings: ["partial canonical sample"]
    }
  });

  assert.match(html, /<details class="github-work-pulse__warnings">/);
  assert.ok(html.includes(`${M.common.warnings} (1)`));
  assert.match(html, /partial canonical sample/);
});

test("formats source timestamps without inventing extra facts", () => {
  assert.equal(
    formatSourceTimestamp("2026-06-24T08:30:00+00:00"),
    "2026-06-24 08:30:00 UTC"
  );
  assert.equal(formatSourceTimestamp(null), M.githubWork.timestampUnknown);
});
