import assert from "node:assert/strict";
import test from "node:test";

import { renderToStaticMarkup } from "react-dom/server";

import {
  buildWorkspaceGitHubSelectedIssueSyncPath,
  buildWorkspaceGitHubSelectedPullRequestSyncPath,
  syncSelectedRepositoryIssues,
  syncSelectedRepositoryPullRequests,
  syncSelectedRepositoryGitHubWork
} from "../lib/api";
import type {
  GitHubConnectionStatusResponse,
  GitHubSelectedIssueSyncResponse,
  GitHubSelectedPullRequestSyncResponse
} from "../lib/types";
import {
  classifySelectedSyncError,
  DEFAULT_SELECTED_REPOSITORY,
  isValidRepositoryFullName,
  SelectedRepositorySyncControlsView
} from "../components/SelectedRepositorySyncControls";

const connectedStatus: GitHubConnectionStatusResponse = {
  provider: "github",
  status: "connected",
  connection_id: "connection-1",
  display_name: "GitHub manual connection",
  last_sync_at: null,
  last_error: null,
  has_connection_record: true,
  has_valid_token_record: true,
  repository_read_available: true,
  repository_read_source: "integration_connection",
  is_live: false,
  warnings: []
};

const missingConnectionStatus: GitHubConnectionStatusResponse = {
  ...connectedStatus,
  status: "local_bridge_only",
  connection_id: null,
  has_connection_record: false,
  has_valid_token_record: false,
  repository_read_source: "local_bridge"
};

const issuesResult: GitHubSelectedIssueSyncResponse = {
  workspace_id: "workspace-123",
  repositories: [
    {
      full_name: "qtwin-io/founderos-smoke",
      synced_issues: 2,
      open_issues: 1,
      closed_issues: 1,
      skipped_pull_requests: 1
    }
  ],
  totals: {
    repositories: 1,
    issues: 2,
    open_issues: 1,
    closed_issues: 1,
    skipped_pull_requests: 1
  },
  sync_job: {
    id: "sync-job-issue-1",
    status: "succeeded",
    records_seen: 2,
    records_created: 2,
    records_updated: 0,
    started_at: "2026-06-26T10:00:00+00:00",
    finished_at: "2026-06-26T10:00:01+00:00"
  },
  counts: {
    repositories: 1,
    issues: 2,
    pull_requests: 0
  },
  capabilities: {
    read_only_sync: true,
    external_writes: false
  },
  is_live: true,
  provider_sync_started: true,
  external_write_performed: false,
  warnings: ["one historical issue identifier was de-duplicated"]
};

const emptyIssuesResult: GitHubSelectedIssueSyncResponse = {
  ...issuesResult,
  repositories: [
    {
      full_name: "qtwin-io/founderos-smoke",
      synced_issues: 0,
      open_issues: 0,
      closed_issues: 0,
      skipped_pull_requests: 0
    }
  ],
  totals: {
    repositories: 1,
    issues: 0,
    open_issues: 0,
    closed_issues: 0,
    skipped_pull_requests: 0
  },
  warnings: []
};

const pullRequestsResult: GitHubSelectedPullRequestSyncResponse = {
  workspace_id: "workspace-123",
  repositories: [
    {
      full_name: "qtwin-io/founderos-smoke",
      synced_pull_requests: 3,
      open_pull_requests: 1,
      closed_pull_requests: 1,
      merged_pull_requests: 1
    }
  ],
  totals: {
    repositories: 1,
    pull_requests: 3,
    open_pull_requests: 1,
    closed_pull_requests: 1,
    merged_pull_requests: 1
  },
  sync_job: {
    id: "sync-job-pr-1",
    status: "succeeded",
    records_seen: 3,
    records_created: 3,
    records_updated: 0,
    started_at: "2026-06-26T10:01:00+00:00",
    finished_at: "2026-06-26T10:01:01+00:00"
  },
  counts: {
    repositories: 1,
    issues: 0,
    pull_requests: 3
  },
  capabilities: {
    read_only_sync: true,
    external_writes: false
  },
  is_live: true,
  provider_sync_started: true,
  external_write_performed: false,
  warnings: []
};

function renderControls(
  props: Partial<Parameters<typeof SelectedRepositorySyncControlsView>[0]> = {}
): string {
  return renderToStaticMarkup(
    <SelectedRepositorySyncControlsView
      connectionError={props.connectionError ?? null}
      connectionStatus={
        props.connectionStatus === undefined
          ? connectedStatus
          : props.connectionStatus
      }
      issuesResult={props.issuesResult ?? null}
      onRepositoryInputChange={props.onRepositoryInputChange}
      onRetryConnection={props.onRetryConnection}
      onRunBoth={props.onRunBoth}
      onRunIssues={props.onRunIssues}
      onRunPullRequests={props.onRunPullRequests}
      pendingAction={props.pendingAction ?? null}
      pullRequestsResult={props.pullRequestsResult ?? null}
      repositoryError={props.repositoryError ?? null}
      repositoryInput={props.repositoryInput ?? DEFAULT_SELECTED_REPOSITORY}
      status={props.status ?? "ready"}
      syncError={props.syncError ?? null}
    />
  );
}

test("builds selected issue and PR sync URLs", () => {
  assert.equal(
    buildWorkspaceGitHubSelectedIssueSyncPath("workspace-123"),
    "/api/v1/workspaces/workspace-123/github/repositories/issues/sync"
  );
  assert.equal(
    buildWorkspaceGitHubSelectedPullRequestSyncPath("workspace-123"),
    "/api/v1/workspaces/workspace-123/github/repositories/pull-requests/sync"
  );
});

test("API client builds the selected issue sync request", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (input, init) => {
    assert.equal(
      String(input),
      "http://localhost/api/v1/workspaces/workspace-123/github/repositories/issues/sync"
    );
    assert.equal(init?.method, "POST");
    assert.equal(
      init?.body,
      JSON.stringify({
        connection_id: "connection-1",
        repositories: ["qtwin-io/founderos-smoke"]
      })
    );
    return new Response(JSON.stringify(issuesResult), {
      headers: { "Content-Type": "application/json" },
      status: 200
    });
  }) as typeof fetch;

  try {
    const payload = await syncSelectedRepositoryIssues(
      "workspace-123",
      {
        connection_id: "connection-1",
        repositories: ["qtwin-io/founderos-smoke"]
      },
      {}
    );
    assert.equal(payload.totals.issues, 2);
    assert.equal(payload.capabilities.external_writes, false);
    assert.equal(payload.external_write_performed, false);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("API client builds the selected PR sync request with explicit states", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (input, init) => {
    assert.equal(
      String(input),
      "http://localhost/api/v1/workspaces/workspace-123/github/repositories/pull-requests/sync"
    );
    assert.equal(init?.method, "POST");
    assert.equal(
      init?.body,
      JSON.stringify({
        connection_id: "connection-1",
        repositories: ["qtwin-io/founderos-smoke"],
        states: ["open", "closed", "merged"]
      })
    );
    return new Response(JSON.stringify(pullRequestsResult), {
      headers: { "Content-Type": "application/json" },
      status: 200
    });
  }) as typeof fetch;

  try {
    const payload = await syncSelectedRepositoryPullRequests(
      "workspace-123",
      {
        connection_id: "connection-1",
        repositories: ["qtwin-io/founderos-smoke"],
        states: ["open", "closed", "merged"]
      },
      {}
    );
    assert.equal(payload.totals.merged_pull_requests, 1);
    assert.equal(payload.external_write_performed, false);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("validates repository full names client-side", () => {
  assert.equal(isValidRepositoryFullName("qtwin-io/founderos-smoke"), true);
  assert.equal(isValidRepositoryFullName(""), false);
  assert.equal(isValidRepositoryFullName("no-slash"), false);
  assert.equal(isValidRepositoryFullName("too/many/slashes"), false);
  assert.equal(isValidRepositoryFullName("owner /repo"), false);
  assert.equal(isValidRepositoryFullName("owner/"), false);
  assert.equal(isValidRepositoryFullName("/repo"), false);
});

test("classifies backend allowlist, permission, and generic errors", () => {
  assert.equal(
    classifySelectedSyncError(
      "github repository is not allowed for selected issue sync"
    ).kind,
    "allowlist"
  );
  assert.equal(
    classifySelectedSyncError(
      "github repository is not allowed for selected pull request sync"
    ).message,
    "Repository is not allowlisted for selected sync."
  );
  assert.equal(
    classifySelectedSyncError(
      "github selected issue sync allowed repositories are not configured"
    ).kind,
    "allowlist"
  );
  assert.equal(
    classifySelectedSyncError("insufficient workspace role").kind,
    "permission"
  );
  assert.equal(
    classifySelectedSyncError("502 Bad Gateway").kind,
    "generic"
  );
});

test("always states the read-only / no external write boundary", () => {
  const html = renderControls({ status: "missing", connectionStatus: null });
  assert.match(html, /Read-only selected repository sync/);
  assert.match(html, /No GitHub writes are performed/);
  assert.match(
    html,
    /Issues and pull requests are fetched from selected allowlisted repositories/
  );
  assert.match(
    html,
    /does not create, close, merge, or comment on GitHub items/
  );
  assert.doesNotMatch(html, /Sync organization/);
  assert.doesNotMatch(html, /Write enabled/);
  assert.doesNotMatch(html, /Connected to all repos/);
});

test("renders no-workspace state without any operator-key gate", () => {
  const html = renderControls({ status: "missing", connectionStatus: null });
  assert.match(html, /No workspace available/);
  assert.doesNotMatch(html, /operator API key/);
  assert.doesNotMatch(html, /owner email/);
});

test("renders missing connection state when no connection record exists", () => {
  const html = renderControls({
    status: "ready",
    connectionStatus: missingConnectionStatus
  });
  assert.match(html, /GitHub connection required/);
  assert.match(html, /GitHub connection must be configured/);
  assert.doesNotMatch(html, /Run issue sync/);
});

test("renders connection load error with retry", () => {
  const html = renderControls({
    status: "error",
    connectionStatus: null,
    connectionError: "backend unavailable",
    onRetryConnection: () => undefined
  });
  assert.match(html, /Selected repository sync unavailable/);
  assert.match(html, /backend unavailable/);
  assert.match(html, /Retry/);
});

test("renders repository input, controls, and validation error", () => {
  const html = renderControls({
    repositoryError: "Repository must be in owner/repo format with no spaces."
  });
  assert.match(html, /Repository \(owner\/repo\)/);
  assert.match(html, /Run issue sync/);
  assert.match(html, /Run PR sync/);
  assert.match(html, /Run issue \+ PR sync/);
  assert.match(html, /Selected repositories must be allowed by backend config/);
  assert.match(html, /owner\/repo format with no spaces/);
});

test("renders loading state for each in-flight action", () => {
  const issues = renderControls({ pendingAction: "issues" });
  assert.match(issues, /Syncing issues/);
  assert.match(issues, /disabled/);

  const prs = renderControls({ pendingAction: "pull_requests" });
  assert.match(prs, /Syncing pull requests/);

  const both = renderControls({ pendingAction: "both" });
  assert.match(both, /Syncing issues and pull requests/);
});

test("renders issue sync summary including skipped PR-shaped records", () => {
  const html = renderControls({ issuesResult });
  assert.match(html, /Issue sync summary/);
  assert.match(html, /1 repositories synced, 2 issues \(1 open \/ 1 closed\)/);
  assert.match(html, /1 PR-shaped issue records skipped/);
  assert.match(html, /qtwin-io\/founderos-smoke/);
  assert.match(html, /No GitHub writes were performed/);
  assert.match(html, /one historical issue identifier was de-duplicated/);
});

test("renders PR sync summary with open/closed/merged counts", () => {
  const html = renderControls({ pullRequestsResult });
  assert.match(html, /Pull request sync summary/);
  assert.match(
    html,
    /1 repositories synced, 3 pull requests \(1 open \/ 1 closed \/ 1 merged\)/
  );
  assert.match(html, /No GitHub writes were performed/);
});

test("renders both summaries together when issue + PR sync ran", () => {
  const html = renderControls({ issuesResult, pullRequestsResult });
  assert.match(html, /Issue sync summary/);
  assert.match(html, /Pull request sync summary/);
});

test("renders empty summary when no records were synced", () => {
  const html = renderControls({ issuesResult: emptyIssuesResult });
  assert.match(html, /No issue records were synced for the selected repository/);
  assert.doesNotMatch(html, /PR-shaped issue records skipped/);
});

test("renders allowlist backend error clearly", () => {
  const html = renderControls({
    syncError: {
      kind: "allowlist",
      message: "Repository is not allowlisted for selected sync."
    }
  });
  assert.match(html, /Repository not allowlisted/);
  assert.match(html, /Repository is not allowlisted for selected sync/);
});

test("renders permission and generic backend errors", () => {
  const permission = renderControls({
    syncError: {
      kind: "permission",
      message:
        "Your workspace role cannot run selected repository sync. An admin role is required."
    }
  });
  assert.match(permission, /Insufficient workspace role/);
  assert.match(permission, /admin role is required/);

  const generic = renderControls({
    syncError: { kind: "generic", message: "The request failed." }
  });
  assert.match(generic, /Selected repository sync failed/);
  assert.match(generic, /The request failed/);
});

test("does not render raw JSON, private IDs, or secrets", () => {
  const html = renderControls({
    issuesResult,
    pullRequestsResult,
    connectionStatus: connectedStatus
  });
  assert.doesNotMatch(html, /connection_id/);
  assert.doesNotMatch(html, /connection-1/);
  assert.doesNotMatch(html, /workspace_id/);
  assert.doesNotMatch(html, /sync_job/);
  assert.doesNotMatch(html, /sync-job-issue-1/);
  assert.doesNotMatch(html, /"totals"/);
  assert.doesNotMatch(html, /X-FounderOS-API-Key/);
});

test("exposes the smoke repository as the default selection", () => {
  assert.equal(DEFAULT_SELECTED_REPOSITORY, "qtwin-io/founderos-smoke");
});

test("combined helper issues both selected sync requests and returns both results", async () => {
  const originalFetch = globalThis.fetch;
  const calls: string[] = [];
  globalThis.fetch = (async (input) => {
    const url = String(input);
    calls.push(url);
    if (url.endsWith("/repositories/issues/sync")) {
      return new Response(JSON.stringify(issuesResult), {
        headers: { "Content-Type": "application/json" },
        status: 200
      });
    }
    return new Response(JSON.stringify(pullRequestsResult), {
      headers: { "Content-Type": "application/json" },
      status: 200
    });
  }) as typeof fetch;

  try {
    const result = await syncSelectedRepositoryGitHubWork(
      "workspace-123",
      {
        connection_id: "connection-1",
        repositories: ["qtwin-io/founderos-smoke"]
      },
      {}
    );
    assert.equal(calls.length, 2);
    assert.ok(calls[0].endsWith("/repositories/issues/sync"));
    assert.ok(calls[1].endsWith("/repositories/pull-requests/sync"));
    assert.equal(result.issues?.totals.issues, 2);
    assert.equal(result.pull_requests?.totals.pull_requests, 3);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
