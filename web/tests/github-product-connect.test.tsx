import assert from "node:assert/strict";
import test from "node:test";

import { renderToStaticMarkup } from "react-dom/server";

import {
  buildWorkspaceGitHubAppLiveSyncPath,
  buildWorkspaceGitHubRepositoriesPath,
  fetchGitHubRepositories,
  runGitHubAppLiveSync
} from "../lib/api";
import { M } from "../lib/messages";
import type {
  GitHubAppConfigStatus,
  GitHubAppLiveSyncResponse,
  GitHubConnectionStatusResponse,
  GitHubRepositoryListResponse
} from "../lib/types";
import { GitHubProductConnectPanelView } from "../components/GitHubProductConnectPanel";

const appConfigured: GitHubAppConfigStatus = {
  configured: true,
  app_id_configured: true,
  app_slug: "founderos",
  private_key_configured: true,
  private_key_source: "path",
  webhook_secret_configured: true,
  setup_url: "https://github.com/apps/founderos/installations/new",
  callback_url: null,
  missing_env: [],
  installation_tokens_persisted: false,
  provider_writes_enabled: false
};

const appMissing: GitHubAppConfigStatus = {
  ...appConfigured,
  configured: false,
  app_id_configured: false,
  app_slug: null,
  private_key_configured: false,
  private_key_source: null,
  webhook_secret_configured: false,
  setup_url: null,
  missing_env: [
    "FOUNDEROS_GITHUB_APP_ID",
    "FOUNDEROS_GITHUB_APP_PRIVATE_KEY or FOUNDEROS_GITHUB_APP_PRIVATE_KEY_PATH"
  ]
};

const connectedAppStatus: GitHubConnectionStatusResponse = {
  provider: "github",
  status: "connected",
  connection_method: "github_app_installation",
  connection_id: "connection-1",
  display_name: "GitHub App: qtwin-io",
  last_sync_at: null,
  last_error: null,
  has_connection_record: true,
  has_valid_token_record: false,
  repository_read_available: true,
  repository_read_source: "local_bridge",
  is_live: false,
  app: appConfigured,
  warnings: [
    "GitHub App installation uses just-in-time installation tokens; no installation access token is persisted."
  ]
};

const missingAppStatus: GitHubConnectionStatusResponse = {
  ...connectedAppStatus,
  status: "local_bridge_only",
  connection_method: null,
  connection_id: null,
  display_name: null,
  has_connection_record: false,
  app: appMissing,
  warnings: []
};

const repositories: GitHubRepositoryListResponse = {
  repositories: [
    {
      id: "repo-1",
      name: "company-knowledge-os",
      full_name: "qtwin-io/company-knowledge-os",
      default_branch: "main",
      visibility: "private",
      archived: false,
      source_url: "https://github.com/qtwin-io/company-knowledge-os",
      last_activity_at: null,
      source: "local_snapshot",
      evidence_refs: [],
      metadata: {}
    },
    {
      id: "repo-2",
      name: "another-repo",
      full_name: "qtwin-io/another-repo",
      default_branch: "main",
      visibility: "private",
      archived: false,
      source_url: "https://github.com/qtwin-io/another-repo",
      last_activity_at: "2026-07-01T10:00:00Z",
      source: "local_snapshot",
      evidence_refs: [],
      metadata: {}
    }
  ],
  count: 25,
  source: "local_snapshot",
  is_live: false,
  warnings: []
};

const liveSyncResult: GitHubAppLiveSyncResponse = {
  workspace_id: "workspace-123",
  connection_id: "connection-1",
  installation_id: "98765",
  repositories: [
    {
      full_name: "qtwin-io/company-knowledge-os",
      synced_issues: 1,
      synced_pull_requests: 1,
      skipped_pull_requests: 0
    }
  ],
  totals: {
    repositories: 1,
    issues: 1,
    pull_requests: 1,
    skipped_pull_requests: 0
  },
  sync_job: {
    id: "sync-job-1",
    status: "succeeded",
    records_seen: 3,
    records_created: 3,
    records_updated: 0,
    started_at: "2026-07-01T10:00:00Z",
    finished_at: "2026-07-01T10:00:01Z"
  },
  counts: {
    repositories: 1,
    issues: 1,
    pull_requests: 1
  },
  capabilities: {
    read_only_sync: true,
    external_writes: false,
    installation_access_token_persisted: false
  },
  is_live: true,
  provider_sync_started: true,
  local_normalization_performed: true,
  external_write_performed: false,
  persistence_mode: "canonical",
  warnings: [
    "GitHub App installation access token was minted just-in-time and was not persisted."
  ]
};

function renderPanel(
  props: Partial<Parameters<typeof GitHubProductConnectPanelView>[0]> = {}
): string {
  return renderToStaticMarkup(
    <GitHubProductConnectPanelView
      connectionStatus={props.connectionStatus ?? connectedAppStatus}
      error={props.error ?? null}
      onRetry={props.onRetry}
      onRunRepositorySync={props.onRunRepositorySync}
      repositorySync={props.repositorySync ?? {}}
      repositories={props.repositories ?? repositories}
      state={props.state ?? "ready"}
    />
  );
}

test("builds GitHub repository list URL", () => {
  assert.equal(
    buildWorkspaceGitHubRepositoriesPath("workspace-123"),
    "/api/v1/workspaces/workspace-123/github/repositories?limit=100"
  );
  assert.equal(
    buildWorkspaceGitHubAppLiveSyncPath("workspace-123"),
    "/api/v1/workspaces/workspace-123/github/connections/app-installation/sync"
  );
});

test("fetches GitHub repository list", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (input) => {
    assert.equal(
      String(input),
      "http://localhost/api/v1/workspaces/workspace-123/github/repositories?limit=100"
    );
    return new Response(JSON.stringify(repositories), {
      headers: { "Content-Type": "application/json" },
      status: 200
    });
  }) as typeof fetch;

  try {
    const payload = await fetchGitHubRepositories("workspace-123", {});
    assert.equal(payload.count, 25);
    assert.equal(payload.is_live, false);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("posts GitHub App live sync request with explicit repository", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (input, init) => {
    assert.equal(
      String(input),
      "http://localhost/api/v1/workspaces/workspace-123/github/connections/app-installation/sync"
    );
    assert.equal(init?.method, "POST");
    assert.equal(
      init?.body,
      JSON.stringify({
        connection_id: "connection-1",
        repositories: ["qtwin-io/company-knowledge-os"],
        include_issues: true,
        include_pull_requests: true
      })
    );
    return new Response(JSON.stringify(liveSyncResult), {
      headers: { "Content-Type": "application/json" },
      status: 200
    });
  }) as typeof fetch;

  try {
    const payload = await runGitHubAppLiveSync("workspace-123", {
      connection_id: "connection-1",
      repositories: ["qtwin-io/company-knowledge-os"]
    });
    assert.equal(payload.external_write_performed, false);
    assert.equal(payload.capabilities.installation_access_token_persisted, false);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("renders connected GitHub App foundation without write promises", () => {
  const html = renderPanel();

  assert.ok(html.includes(M.githubProductConnect.title));
  assert.ok(html.includes(M.githubProductConnect.appConnected));
  assert.ok(html.includes("25"));
  assert.ok(html.includes(M.githubProductConnect.tokenTitle));
  assert.ok(html.includes(M.githubProductConnect.writeTitle));
  assert.ok(html.includes(M.githubProductConnect.liveSyncTitle));
  assert.ok(html.includes(M.githubProductConnect.liveSyncRun));
  assert.ok(html.includes("qtwin-io/company-knowledge-os"));
  assert.ok(html.includes("qtwin-io/another-repo"));
  assert.equal(
    (html.match(new RegExp(M.githubProductConnect.liveSyncRun, "g")) ?? []).length,
    2
  );
  assert.doesNotMatch(html, /operator API key/);
  assert.doesNotMatch(html, /provider token/i);
  assert.doesNotMatch(html, /write enabled/i);
});

test("renders missing GitHub App env contract", () => {
  const html = renderPanel({
    connectionStatus: missingAppStatus,
    repositories: { ...repositories, count: 0 }
  });

  assert.ok(html.includes(M.githubProductConnect.appNotConfigured));
  assert.ok(html.includes(M.githubProductConnect.missingEnvTitle));
  assert.ok(html.includes("FOUNDEROS_GITHUB_APP_ID"));
});

test("renders invalid repository and missing app sync states", () => {
  const invalid = renderPanel({
    repositories: {
      ...repositories,
      repositories: [
        {
          ...repositories.repositories[0],
          full_name: "bad repo"
        }
      ]
    }
  });
  assert.ok(invalid.includes(M.githubProductConnect.liveSyncRepositoryInvalid));

  const missingApp = renderPanel({
    connectionStatus: missingAppStatus
  });
  assert.ok(missingApp.includes(M.githubProductConnect.liveSyncRequiresApp));
});

test("renders live sync success and error states without write claim", () => {
  const success = renderPanel({
    repositorySync: {
      "qtwin-io/company-knowledge-os": {
        error: null,
        result: liveSyncResult,
        state: "success"
      }
    }
  });
  assert.ok(success.includes(M.githubProductConnect.liveSyncResultTitle));
  assert.ok(success.includes(M.githubProductConnect.liveSyncNoWrites));
  assert.ok(success.includes("репозиториев — 1, задач — 1, пулреквестов — 1"));

  const error = renderPanel({
    repositorySync: {
      "qtwin-io/company-knowledge-os": {
        error: "github repository is not part of the app installation",
        result: null,
        state: "error"
      }
    }
  });
  assert.ok(error.includes(M.githubProductConnect.liveSyncFailedTitle));
  assert.match(error, /not part of the app installation/);
});

test("renders no-workspace and error states", () => {
  const missing = renderPanel({
    connectionStatus: null,
    repositories: null,
    state: "missing"
  });
  assert.ok(missing.includes(M.common.noWorkspaceTitle));

  const error = renderPanel({
    connectionStatus: null,
    error: "backend unavailable",
    onRetry: () => undefined,
    repositories: null,
    state: "error"
  });
  assert.ok(error.includes(M.githubProductConnect.unavailableTitle));
  assert.match(error, /backend unavailable/);
});
