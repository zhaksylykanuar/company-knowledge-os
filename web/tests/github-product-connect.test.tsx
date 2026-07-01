import assert from "node:assert/strict";
import test from "node:test";

import { renderToStaticMarkup } from "react-dom/server";

import {
  buildWorkspaceGitHubRepositoriesPath,
  fetchGitHubRepositories
} from "../lib/api";
import { M } from "../lib/messages";
import type {
  GitHubAppConfigStatus,
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
  repositories: [],
  count: 25,
  source: "local_snapshot",
  is_live: false,
  warnings: []
};

function renderPanel(
  props: Partial<Parameters<typeof GitHubProductConnectPanelView>[0]> = {}
): string {
  return renderToStaticMarkup(
    <GitHubProductConnectPanelView
      connectionStatus={props.connectionStatus ?? connectedAppStatus}
      error={props.error ?? null}
      onRetry={props.onRetry}
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

test("renders connected GitHub App foundation without write promises", () => {
  const html = renderPanel();

  assert.ok(html.includes(M.githubProductConnect.title));
  assert.ok(html.includes(M.githubProductConnect.appConnected));
  assert.ok(html.includes("25"));
  assert.ok(html.includes(M.githubProductConnect.tokenTitle));
  assert.ok(html.includes(M.githubProductConnect.writeTitle));
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
