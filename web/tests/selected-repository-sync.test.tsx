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
import { M } from "../lib/messages";
import type {
  GitHubAppConfigStatus,
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

const configuredApp: GitHubAppConfigStatus = {
  configured: true,
  app_id_configured: true,
  app_slug: "founderos",
  private_key_configured: true,
  private_key_source: "path",
  webhook_secret_configured: false,
  setup_url: "https://github.com/apps/founderos/installations/new",
  callback_url: null,
  missing_env: [],
  installation_tokens_persisted: false,
  provider_writes_enabled: false
};

const connectedStatus: GitHubConnectionStatusResponse = {
  provider: "github",
  status: "connected",
  connection_method: "manual_provider_token",
  connection_id: "connection-1",
  display_name: "GitHub manual connection",
  last_sync_at: null,
  last_error: null,
  has_connection_record: true,
  has_valid_token_record: true,
  repository_read_available: true,
  repository_read_source: "integration_connection",
  is_live: false,
  app: configuredApp,
  warnings: []
};

const missingConnectionStatus: GitHubConnectionStatusResponse = {
  ...connectedStatus,
  status: "local_bridge_only",
  connection_method: null,
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
    M.selectedSync.errorAllowlist
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
  assert.ok(html.includes(M.selectedSync.intro));
  assert.doesNotMatch(html, /Sync organization/);
  assert.doesNotMatch(html, /Write enabled/);
  assert.doesNotMatch(html, /Connected to all repos/);
});

test("renders no-workspace state without any operator-key gate", () => {
  const html = renderControls({ status: "missing", connectionStatus: null });
  assert.ok(html.includes(M.common.noWorkspaceTitle));
  assert.doesNotMatch(html, /operator API key/);
  assert.doesNotMatch(html, /owner email/);
});

test("renders missing connection state when no connection record exists", () => {
  const html = renderControls({
    status: "ready",
    connectionStatus: missingConnectionStatus
  });
  assert.ok(html.includes(M.selectedSync.connectionRequiredTitle));
  assert.ok(html.includes(M.selectedSync.connectionRequiredDescription));
  assert.doesNotMatch(html, /Run issue sync/);
});

test("renders connection load error with retry", () => {
  const html = renderControls({
    status: "error",
    connectionStatus: null,
    connectionError: "backend unavailable",
    onRetryConnection: () => undefined
  });
  assert.ok(html.includes(M.selectedSync.unavailableTitle));
  assert.match(html, /backend unavailable/);
  assert.ok(html.includes(M.common.retry));
});

test("renders repository input, controls, and validation error", () => {
  const html = renderControls({
    repositoryError: M.selectedSync.validationFormat
  });
  assert.ok(html.includes(M.selectedSync.repoLabel));
  assert.ok(html.includes(M.selectedSync.runIssues));
  assert.ok(html.includes(M.selectedSync.runPr));
  assert.ok(html.includes(M.selectedSync.runBoth));
  assert.ok(html.includes(M.selectedSync.repoNote));
  assert.ok(html.includes(M.selectedSync.validationFormat));
});

test("renders loading state for each in-flight action", () => {
  const issues = renderControls({ pendingAction: "issues" });
  assert.ok(issues.includes(M.selectedSync.syncingIssues));
  assert.match(issues, /disabled/);

  const prs = renderControls({ pendingAction: "pull_requests" });
  assert.ok(prs.includes(M.selectedSync.syncingPr));

  const both = renderControls({ pendingAction: "both" });
  assert.ok(both.includes(M.selectedSync.syncingBoth));
});

test("renders issue sync summary including skipped PR-shaped records", () => {
  const html = renderControls({ issuesResult });
  assert.ok(html.includes(M.selectedSync.issueSummaryTitle));
  assert.match(html, /репозиториев — 1, задач — 2 \(открытых 1 \/ закрытых 1\)/);
  assert.match(html, /Пропущено записей задач в виде PR: 1/);
  assert.match(html, /qtwin-io\/founderos-smoke/);
  assert.ok(html.includes(M.selectedSync.noWrites));
  assert.match(html, /one historical issue identifier was de-duplicated/);
});

test("renders PR sync summary with open/closed/merged counts", () => {
  const html = renderControls({ pullRequestsResult });
  assert.ok(html.includes(M.selectedSync.prSummaryTitle));
  assert.match(
    html,
    /репозиториев — 1, пулреквестов — 3 \(открытых 1 \/ закрытых 1 \/ слитых 1\)/
  );
  assert.ok(html.includes(M.selectedSync.noWrites));
});

test("renders both summaries together when issue + PR sync ran", () => {
  const html = renderControls({ issuesResult, pullRequestsResult });
  assert.ok(html.includes(M.selectedSync.issueSummaryTitle));
  assert.ok(html.includes(M.selectedSync.prSummaryTitle));
});

test("renders empty summary when no records were synced", () => {
  const html = renderControls({ issuesResult: emptyIssuesResult });
  assert.ok(html.includes(M.selectedSync.noIssuesSynced));
  assert.doesNotMatch(html, /PR-shaped issue records skipped/);
});

test("renders allowlist backend error clearly", () => {
  const html = renderControls({
    syncError: {
      kind: "allowlist",
      message: M.selectedSync.errorAllowlist
    }
  });
  assert.ok(html.includes(M.selectedSync.errorTitleAllowlist));
  assert.ok(html.includes(M.selectedSync.errorAllowlist));
});

test("renders permission and generic backend errors", () => {
  const permission = renderControls({
    syncError: {
      kind: "permission",
      message: M.selectedSync.errorPermission
    }
  });
  assert.ok(permission.includes(M.selectedSync.errorTitlePermission));
  assert.ok(permission.includes(M.selectedSync.errorPermission));

  const generic = renderControls({
    syncError: { kind: "generic", message: "The request failed." }
  });
  assert.ok(generic.includes(M.selectedSync.errorTitleGeneric));
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
