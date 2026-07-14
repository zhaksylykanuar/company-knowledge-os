import assert from "node:assert/strict";
import test from "node:test";

import { renderToStaticMarkup } from "react-dom/server";

import {
  buildWorkspaceGitHubAppLiveSyncPath,
  buildWorkspaceGitHubRepositoriesPath,
  fetchGitHubRepositories,
  runGitHubAppLiveSync
} from "../lib/api";
import { M, T } from "../lib/messages";
import type {
  GitHubAppConfigStatus,
  GitHubAppLiveSyncResponse,
  GitHubConnectionStatusResponse,
  GitHubRepositoryListResponse
} from "../lib/types";
import {
  classifyGitHubSyncState,
  GitHubProductConnectPanelView,
  shouldRefreshGitHubDataAfterSync,
  summarizeGitHubRealReadReadiness
} from "../components/GitHubProductConnectPanel";

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

const disconnectedAppStatus: GitHubConnectionStatusResponse = {
  ...connectedAppStatus,
  status: "error",
  last_error: "installation suspended",
  warnings: ["GitHub connection status is error; live provider readiness is not implied"]
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
      evidence_refs: [
        {
          kind: "repository_inventory_snapshot",
          source: "github",
          ref: "qtwin-io/company-knowledge-os",
          url: "https://github.com/qtwin-io/company-knowledge-os"
        }
      ],
      metadata: {}
    },
    {
      id: "repo-2",
      name: "another-repo",
      full_name: "qtwin-io/another-repo",
      default_branch: "main",
      visibility: "private",
      archived: true,
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
      canAdminister={props.canAdminister}
      connectionStatus={props.connectionStatus ?? connectedAppStatus}
      error={props.error ?? null}
      onRepositoryFocusChange={props.onRepositoryFocusChange}
      onRepositorySelect={props.onRepositorySelect ?? (() => undefined)}
      onRetry={props.onRetry}
      onRunRepositorySync={props.onRunRepositorySync ?? (() => undefined)}
      repositoryFocus={props.repositoryFocus}
      repositorySync={props.repositorySync ?? {}}
      repositories={props.repositories ?? repositories}
      selectedRepository={props.selectedRepository}
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

test("renders a mission-first GitHub command center with one sync action", () => {
  const html = renderPanel();

  assert.ok(html.includes(M.githubProductConnect.title));
  assert.ok(html.includes(M.githubProductConnect.missionReadyCurrent));
  assert.ok(html.includes(M.githubProductConnect.missionReadyOutcome));
  assert.ok(html.includes(M.githubProductConnect.flowConnectionTitle));
  assert.ok(html.includes(M.githubProductConnect.flowRepositoryTitle));
  assert.ok(html.includes(M.githubProductConnect.flowFounderOSTitle));
  assert.ok(html.includes(M.githubProductConnect.metricsTitle));
  assert.ok(html.includes(T.githubLoadedRepositorySample(2, 25)));
  assert.match(html, /github-command-metric-value">2</);
  assert.ok(html.includes(M.githubProductConnect.repositoryWorkbenchTitle));
  assert.ok(html.includes("qtwin-io/company-knowledge-os"));
  assert.ok(html.includes("qtwin-io/another-repo"));
  assert.equal(
    (html.match(new RegExp(M.githubProductConnect.liveSyncRun, "g")) ?? []).length,
    1
  );

  // Readiness and provider mechanics stay available, but only in disclosure.
  assert.match(html, /<details class="github-command-technical">/);
  assert.ok(html.includes(M.githubProductConnect.realReadReadinessTitle));
  assert.ok(html.includes(M.githubProductConnect.realReadReady));
  assert.ok(
    html.includes(T.githubRealReadNextStep(true, true, true, true, true))
  );
  assert.ok(html.includes(M.githubProductConnect.tokenTitle));
  assert.ok(html.includes(M.githubProductConnect.writeTitle));
  assert.doesNotMatch(html, /operator API key/);
  assert.doesNotMatch(html, /provider token/i);
  assert.doesNotMatch(html, /write enabled/i);
});

test("keeps GitHub repository facts but removes setup and sync controls in read-only mode", () => {
  const html = renderPanel({ canAdminister: false });

  assert.ok(html.includes("qtwin-io/company-knowledge-os"));
  assert.ok(html.includes(M.common.sourceAdminOnlyNote));
  assert.doesNotMatch(html, new RegExp(M.githubProductConnect.openSetup));
  assert.doesNotMatch(html, new RegExp(M.githubProductConnect.liveSyncRun));
  assert.ok(html.includes(M.githubProductConnect.missionViewerCurrent));
  assert.ok(html.includes(M.githubProductConnect.missionViewerOutcome));
  assert.doesNotMatch(html, new RegExp(M.githubProductConnect.missionReadyOutcome));
});

test("summarizes GitHub App real-read readiness from loaded local state", () => {
  assert.deepEqual(
    summarizeGitHubRealReadReadiness(connectedAppStatus, repositories),
    {
      appEnvConfigured: true,
      blockers: [],
      hasAppInstallationConnection: true,
      installationConnected: true,
      localRepositoryCount: 25,
      localRepositorySurfaceAvailable: true,
      nextStep: T.githubRealReadNextStep(true, true, true, true, true),
      ready: true
    }
  );

  const blocked = summarizeGitHubRealReadReadiness(missingAppStatus, {
    ...repositories,
    count: 0,
    repositories: []
  });
  assert.equal(blocked.ready, false);
  assert.deepEqual(blocked.blockers, [
    "github_app_env_incomplete",
    "github_app_installation_connection_missing",
    "local_repository_surface_empty"
  ]);
  assert.equal(blocked.nextStep, T.githubRealReadNextStep(false, false, false, false, false));

  const disconnected = summarizeGitHubRealReadReadiness(
    disconnectedAppStatus,
    repositories
  );
  assert.equal(disconnected.ready, false);
  assert.deepEqual(disconnected.blockers, [
    "github_app_installation_connection_not_connected"
  ]);
  assert.equal(disconnected.nextStep, T.githubRealReadNextStep(true, true, false, true, false));
});

test("renders blocked GitHub App real-read readiness without provider calls", () => {
  const html = renderPanel({
    connectionStatus: missingAppStatus,
    repositories: { ...repositories, count: 0, repositories: [] }
  });

  assert.ok(html.includes(M.githubProductConnect.realReadReadinessTitle));
  assert.ok(html.includes(M.githubProductConnect.realReadBlocked));
  assert.ok(html.includes(M.githubProductConnect.realReadBlockersTitle));
  assert.ok(html.includes(M.githubProductConnect.realReadBlockerEnv));
  assert.ok(html.includes(M.githubProductConnect.realReadBlockerConnectionMissing));
  assert.ok(html.includes(M.githubProductConnect.realReadBlockerReposEmpty));
  assert.ok(html.includes(T.githubRealReadNextStep(false, false, false, false, false)));
  assert.ok(html.includes(M.githubProductConnect.realReadBoundary));
  assert.doesNotMatch(html, /provider read started/i);
  assert.doesNotMatch(html, /external write performed/i);
  assert.doesNotMatch(html, /installation access token/i);
});

test("filters the loaded repository surface locally without provider calls", () => {
  const archivedHtml = renderPanel({
    repositoryFocus: "archived"
  });
  assert.ok(archivedHtml.includes(M.githubProductConnect.repositoryFocusArchived));
  assert.ok(archivedHtml.includes("qtwin-io/another-repo"));
  assert.doesNotMatch(archivedHtml, /qtwin-io\/company-knowledge-os/);
  assert.equal(
    (archivedHtml.match(new RegExp(M.githubProductConnect.liveSyncRun, "g")) ?? [])
      .length,
    1
  );
  assert.match(
    archivedHtml,
    new RegExp(
      `aria-pressed="true"[^>]*>${M.githubProductConnect.repositoryFocusArchived}`
    )
  );

  const evidenceHtml = renderPanel({
    repositoryFocus: "with_evidence"
  });
  assert.ok(evidenceHtml.includes(M.githubProductConnect.repositoryFocusWithEvidence));
  assert.ok(evidenceHtml.includes("qtwin-io/company-knowledge-os"));
  assert.doesNotMatch(evidenceHtml, /qtwin-io\/another-repo/);
  assert.doesNotMatch(evidenceHtml, /provider read запущен/i);
  assert.doesNotMatch(evidenceHtml, /bulk sync started/i);
  assert.doesNotMatch(evidenceHtml, /external write performed/i);
});

test("renders missing GitHub App env contract", () => {
  const html = renderPanel({
    connectionStatus: missingAppStatus,
    repositories: { ...repositories, count: 0 }
  });

  assert.ok(html.includes(M.githubProductConnect.connectionMetricAttention));
  assert.ok(html.includes(M.githubProductConnect.missingEnvTitle));
  assert.ok(html.includes("FOUNDEROS_GITHUB_APP_ID"));
  assert.ok(html.includes(M.githubProductConnect.refreshConnection));
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
  assert.ok(missingApp.includes(M.githubProductConnect.missionConnectionCurrent));
  assert.doesNotMatch(
    missingApp,
    new RegExp(M.githubProductConnect.liveSyncRun)
  );
});

test("does not offer sync for a non-connected installation record", () => {
  const html = renderPanel({ connectionStatus: disconnectedAppStatus });

  assert.ok(
    html.includes(M.githubProductConnect.missionConnectionAttentionCurrent)
  );
  assert.doesNotMatch(html, new RegExp(M.githubProductConnect.liveSyncRun));
  assert.ok(html.includes(M.githubProductConnect.refreshConnection));
  assert.ok(html.includes(M.githubProductConnect.connectionAttentionActionHint));
  assert.doesNotMatch(html, new RegExp(M.githubProductConnect.openSetup));
});

test("keeps a stale connected installation blocked when GitHub App env is incomplete", () => {
  const html = renderPanel({
    connectionStatus: {
      ...connectedAppStatus,
      app: appMissing
    }
  });

  assert.ok(html.includes(M.githubProductConnect.connectionMetricAttention));
  assert.doesNotMatch(html, new RegExp(M.githubProductConnect.liveSyncRun));
  assert.ok(html.includes(M.githubProductConnect.realReadBlockerEnv));
});

test("never sends an existing installation into a new-install setup URL", () => {
  const html = renderPanel({
    repositories: {
      ...repositories,
      count: 0,
      repositories: []
    }
  });

  assert.ok(html.includes(M.githubProductConnect.missionEmptyCurrent));
  assert.ok(html.includes(M.githubProductConnect.refreshConnection));
  assert.doesNotMatch(html, new RegExp(M.githubProductConnect.openSetup));
  assert.doesNotMatch(
    html,
    new RegExp(M.githubProductConnect.openSetupSettings)
  );
});

test("uses a global sync lock for the chooser and primary action", () => {
  const html = renderPanel({
    repositorySync: {
      "qtwin-io/another-repo": {
        error: null,
        result: null,
        state: "syncing"
      }
    }
  });

  assert.ok(html.includes(M.githubProductConnect.liveSyncRunning));
  assert.match(
    html,
    /class="github-repository-choice-main" disabled=""/
  );
  assert.doesNotMatch(html, new RegExp(M.githubProductConnect.liveSyncRun));
});

test("keeps at most eight repository choices before the disclosure", () => {
  const manyRepositories: GitHubRepositoryListResponse = {
    ...repositories,
    count: 10,
    repositories: Array.from({ length: 10 }, (_, index) => ({
      ...repositories.repositories[0],
      id: `repo-${index + 1}`,
      name: `repo-${index + 1}`,
      full_name: `qtwin-io/repo-${index + 1}`,
      source_url: `https://github.com/qtwin-io/repo-${index + 1}`
    }))
  };
  const html = renderPanel({ repositories: manyRepositories });
  const beforeDisclosure = html.split(
    '<details class="github-repository-more">'
  )[0];

  assert.equal(
    (
      beforeDisclosure.match(
        /<article class="github-repository-choice(?: |")/g
      ) ?? []
    ).length,
    8
  );
  assert.ok(html.includes(T.githubShowMoreRepositories(2)));
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
  assert.match(success, /aria-live="polite"/);
  assert.match(success, /role="status"/);

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
  assert.match(error, /<details class="github-command-error-details">/);
});

test("classifies resolved sync jobs without treating HTTP success as job success", () => {
  assert.equal(classifyGitHubSyncState("succeeded"), "success");
  assert.equal(classifyGitHubSyncState("running"), "pending");
  assert.equal(classifyGitHubSyncState("queued"), "pending");
  assert.equal(classifyGitHubSyncState("failed"), "error");
  assert.equal(classifyGitHubSyncState("partial"), "partial");
  assert.equal(shouldRefreshGitHubDataAfterSync("succeeded"), true);
  assert.equal(shouldRefreshGitHubDataAfterSync("partial"), true);
  assert.equal(shouldRefreshGitHubDataAfterSync("running"), false);
  assert.equal(shouldRefreshGitHubDataAfterSync("failed"), false);

  const running = renderPanel({
    repositorySync: {
      "qtwin-io/company-knowledge-os": {
        error: null,
        result: {
          ...liveSyncResult,
          sync_job: { ...liveSyncResult.sync_job, status: "running" }
        },
        state: "pending"
      }
    }
  });
  assert.ok(running.includes(M.githubProductConnect.liveSyncPendingTitle));
  assert.ok(running.includes(M.githubProductConnect.liveSyncPendingDescription));
  assert.ok(running.includes(M.githubProductConnect.liveSyncRun));
  assert.doesNotMatch(running, new RegExp(M.githubProductConnect.liveSyncRunning));
  assert.match(running, /github-sync-receipt--pending/);
  assert.doesNotMatch(
    running,
    new RegExp(`class="eyebrow">${M.githubProductConnect.receiptEyebrow}<`)
  );

  const partial = renderPanel({
    repositorySync: {
      "qtwin-io/company-knowledge-os": {
        error: null,
        result: {
          ...liveSyncResult,
          sync_job: { ...liveSyncResult.sync_job, status: "partial" }
        },
        state: "partial"
      }
    }
  });
  assert.ok(partial.includes(M.githubProductConnect.liveSyncPartialTitle));
  assert.ok(partial.includes(M.githubProductConnect.liveSyncPartialDescription));
  assert.ok(partial.includes(M.githubProductConnect.missionPartialCurrent));
  assert.match(partial, /github-sync-receipt--partial/);
  assert.doesNotMatch(
    partial,
    new RegExp(M.githubProductConnect.liveSyncResultFailedTitle)
  );

  const failed = renderPanel({
    repositorySync: {
      "qtwin-io/company-knowledge-os": {
        error: null,
        result: {
          ...liveSyncResult,
          sync_job: { ...liveSyncResult.sync_job, status: "failed" }
        },
        state: "error"
      }
    }
  });
  assert.ok(failed.includes(M.githubProductConnect.liveSyncResultFailedTitle));
  assert.ok(failed.includes(M.githubProductConnect.receiptErrorEyebrow));
  assert.match(failed, /github-sync-receipt--error/);
  assert.doesNotMatch(
    failed,
    new RegExp(`class="eyebrow">${M.githubProductConnect.receiptEyebrow}<`)
  );
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
