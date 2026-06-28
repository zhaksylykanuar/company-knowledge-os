import assert from "node:assert/strict";
import test from "node:test";

import { renderToStaticMarkup } from "react-dom/server";

import {
  buildWorkspaceGitHubConnectionStatusPath,
  buildWorkspaceGitHubLocalSyncPath,
  fetchGitHubConnectionStatus,
  runGitHubLocalSync
} from "../lib/api";
import type {
  GitHubConnectionStatusResponse,
  GitHubLocalSyncResponse
} from "../lib/types";
import { GitHubSyncControlsView } from "../components/GitHubSyncControls";

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
  provider: "github",
  status: "local_bridge_only",
  connection_id: null,
  display_name: null,
  last_sync_at: null,
  last_error: null,
  has_connection_record: false,
  has_valid_token_record: false,
  repository_read_available: true,
  repository_read_source: "local_bridge",
  is_live: false,
  warnings: [
    "no GitHub IntegrationConnection exists; repository read uses local bridge only"
  ]
};

const syncResult: GitHubLocalSyncResponse = {
  sync_job: {
    id: "sync-job-1",
    status: "partial",
    records_seen: 1,
    records_created: 1,
    records_updated: 0,
    started_at: "2026-06-24T10:00:00+00:00",
    finished_at: "2026-06-24T10:00:01+00:00"
  },
  counts: {
    repositories: 1,
    issues: 0,
    pull_requests: 0
  },
  status: "partial",
  message: "Local GitHub data normalized into canonical backend state.",
  capability_mode: "local_normalization",
  is_live: false,
  provider_sync_started: false,
  local_normalization_performed: true,
  persistence_mode: "canonical",
  warnings: ["local GitHub issues were not available"]
};

function renderControls(
  props: Partial<Parameters<typeof GitHubSyncControlsView>[0]> = {}
): string {
  return renderToStaticMarkup(
    <GitHubSyncControlsView
      connectionStatus={props.connectionStatus ?? connectedStatus}
      error={props.error ?? null}
      onRetry={props.onRetry}
      onSync={props.onSync}
      result={props.result ?? null}
      status={props.status ?? "ready"}
    />
  );
}

test("builds GitHub connection status and local sync URLs", () => {
  assert.equal(
    buildWorkspaceGitHubConnectionStatusPath("workspace-123"),
    "/api/v1/workspaces/workspace-123/github/connection-status"
  );
  assert.equal(
    buildWorkspaceGitHubLocalSyncPath("workspace-123"),
    "/api/v1/workspaces/workspace-123/github/local-sync"
  );
});

test("fetches and parses GitHub connection status", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (input) => {
    assert.equal(
      String(input),
      "http://localhost/api/v1/workspaces/workspace-123/github/connection-status"
    );
    return new Response(JSON.stringify(connectedStatus), {
      headers: { "Content-Type": "application/json" },
      status: 200
    });
  }) as typeof fetch;

  try {
    const payload = await fetchGitHubConnectionStatus("workspace-123", {
      includeOwnerEmail: false
    });
    assert.equal(payload.status, "connected");
    assert.equal(payload.is_live, false);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("posts local sync request without live provider data", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (input, init) => {
    assert.equal(
      String(input),
      "http://localhost/api/v1/workspaces/workspace-123/github/local-sync"
    );
    assert.equal(init?.method, "POST");
    assert.equal(
      init?.body,
      JSON.stringify({
        include_repositories: true,
        include_issues: true,
        include_pull_requests: true
      })
    );
    return new Response(JSON.stringify(syncResult), {
      headers: { "Content-Type": "application/json" },
      status: 200
    });
  }) as typeof fetch;

  try {
    const payload = await runGitHubLocalSync("workspace-123", {}, {
      includeOwnerEmail: false
    });
    assert.equal(payload.capability_mode, "local_normalization");
    assert.equal(payload.provider_sync_started, false);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("renders missing settings state", () => {
  const html = renderControls({
    connectionStatus: null,
    status: "missing"
  });
  assert.match(html, /Workspace settings required/);
  assert.match(html, /workspace ID, owner email, and operator API key/);
});

test("renders unsupported state when no connection record exists", () => {
  const html = renderControls({
    connectionStatus: missingConnectionStatus
  });
  assert.match(html, /GitHub connection record required/);
  assert.match(html, /Live OAuth is not enabled yet/);
  assert.match(html, /No live provider/);
  assert.doesNotMatch(html, /Connected to GitHub/);
  assert.doesNotMatch(html, /source_events/);
});

test("renders connected local sync action without promising OAuth", () => {
  const html = renderControls();
  assert.match(html, /Local sync controls/);
  assert.match(html, /Run local GitHub sync/);
  assert.match(html, /Local only/);
  assert.match(html, /Live OAuth and provider execution are not enabled/);
  assert.doesNotMatch(html, /Connected to GitHub/);
});

test("renders pending local sync state", () => {
  const html = renderControls({ status: "syncing" });
  assert.match(html, /Running local sync/);
  assert.match(html, /disabled/);
});

test("renders successful sync result and warnings", () => {
  const html = renderControls({
    result: syncResult,
    status: "success"
  });
  assert.match(html, /Local GitHub data normalized into canonical backend state/);
  assert.match(html, /1 repositories, 0 issues\/tasks, and 0 pull requests/);
  assert.match(html, /local GitHub issues were not available/);
});

test("renders local sync backend error with retry", () => {
  const html = renderControls({
    error: "github connected connection record required for local sync",
    onRetry: () => undefined,
    status: "error"
  });
  assert.match(html, /Local GitHub sync failed/);
  assert.match(html, /github connected connection record required/);
  assert.match(html, /Refresh status/);
});
