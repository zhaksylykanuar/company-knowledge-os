import assert from "node:assert/strict";
import test from "node:test";

import { renderToStaticMarkup } from "react-dom/server";

import {
  buildWorkspaceGitHubSyncJobPath,
  buildWorkspaceGitHubAppLiveSyncPath,
  buildWorkspaceGitHubRepositoriesPath,
  cancelGitHubSyncJob,
  fetchGitHubRepositories,
  runGitHubAppLiveSync,
  waitForGitHubSyncJob
} from "../lib/api";
import { M, T } from "../lib/messages";
import type {
  GitHubAppConfigStatus,
  GitHubAppLiveSyncResponse,
  GitHubConnectionStatusResponse,
  GitHubRepositoryListResponse,
  GitHubSyncJobRead
} from "../lib/types";
import {
  classifyGitHubSyncState,
  GitHubProductConnectPanelView,
  mergeGitHubSyncJobResult,
  shouldRefreshGitHubDataAfterSync,
  summarizeGitHubRealReadReadiness
} from "../components/GitHubProductConnectPanel";

const appConfigured: GitHubAppConfigStatus = {
  configured: true,
  credential_source: "managed",
  app_id_configured: true,
  app_slug: "founderos",
  app_name: "FounderOS",
  private_key_configured: true,
  private_key_source: "encrypted_database",
  webhook_secret_configured: true,
  setup_url: "https://github.com/apps/founderos/installations/new",
  callback_url: null,
  missing_requirements: [],
  installation_tokens_persisted: false,
  provider_writes_enabled: false
};

const appMissing: GitHubAppConfigStatus = {
  ...appConfigured,
  configured: false,
  credential_source: "none",
  app_id_configured: false,
  app_slug: null,
  app_name: null,
  private_key_configured: false,
  private_key_source: null,
  webhook_secret_configured: false,
  setup_url: null,
  missing_requirements: ["github_app_product_setup"]
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
  installation_verified: true,
  live_read_available: true,
  selected_repositories: ["qtwin-io/company-knowledge-os"],
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
  installation_verified: false,
  live_read_available: false,
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
    finished_at: "2026-07-01T10:00:01Z",
    attempt_count: 1,
    max_attempts: 3,
    next_attempt_at: "2026-07-01T10:00:00Z",
    cancel_requested_at: null,
    progress: {
      phase: "succeeded",
      completed_repositories: ["qtwin-io/company-knowledge-os"],
      total_repositories: 1,
      repositories: [
        {
          full_name: "qtwin-io/company-knowledge-os",
          synced_issues: 1,
          synced_pull_requests: 1,
          skipped_pull_requests: 0
        }
      ],
      counts: {
        repositories: 1,
        issues: 1,
        pull_requests: 1,
        skipped_pull_requests: 0
      }
    }
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

const queuedSyncJob: GitHubSyncJobRead = {
  id: "sync-job-1",
  workspace_id: "workspace-123",
  connection_id: "connection-1",
  provider: "github",
  status: "queued",
  sync_type: "manual",
  started_at: null,
  finished_at: null,
  records_seen: 0,
  records_created: 0,
  records_updated: 0,
  error_message: null,
  attempt_count: 0,
  max_attempts: 3,
  next_attempt_at: "2026-07-01T10:00:00Z",
  cancel_requested_at: null,
  progress: {
    phase: "queued",
    completed_repositories: [],
    total_repositories: 1,
    repositories: [],
    counts: {
      repositories: 0,
      issues: 0,
      pull_requests: 0,
      skipped_pull_requests: 0
    }
  },
  created_at: "2026-07-01T10:00:00Z",
  updated_at: "2026-07-01T10:00:00Z",
  is_live: false,
  execution_started: false,
  warnings: []
};

function renderPanel(
  props: Partial<Parameters<typeof GitHubProductConnectPanelView>[0]> = {}
): string {
  return renderToStaticMarkup(
    <GitHubProductConnectPanelView
      canAdminister={props.canAdminister}
      connectionStatus={props.connectionStatus ?? connectedAppStatus}
      error={props.error ?? null}
      onCancelRepositorySync={props.onCancelRepositorySync}
      onCloseSetup={props.onCloseSetup}
      onOpenSetup={props.onOpenSetup}
      onRepositorySelect={props.onRepositorySelect ?? (() => undefined)}
      onRetry={props.onRetry}
      onRunRepositorySync={props.onRunRepositorySync ?? (() => undefined)}
      repositorySync={props.repositorySync ?? {}}
      repositories={props.repositories ?? repositories}
      selectedRepository={props.selectedRepository}
      selfServiceSetupEnabled={props.selfServiceSetupEnabled}
      setupOpen={props.setupOpen}
      setupWizard={props.setupWizard}
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
  assert.equal(
    buildWorkspaceGitHubSyncJobPath("workspace-123", "sync-job-1"),
    "/api/v1/workspaces/workspace-123/github/sync-jobs/sync-job-1"
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

test("polls a queued GitHub sync job until it reaches a terminal state", async () => {
  const originalFetch = globalThis.fetch;
  const statuses = ["running", "succeeded"];
  const updates: string[] = [];
  globalThis.fetch = (async (input) => {
    assert.equal(
      String(input),
      "http://localhost/api/v1/workspaces/workspace-123/github/sync-jobs/sync-job-1"
    );
    const status = statuses.shift();
    assert.ok(status);
    return new Response(
      JSON.stringify({
        ...queuedSyncJob,
        status,
        attempt_count: 1,
        execution_started: true,
        is_live: true,
        finished_at:
          status === "succeeded" ? "2026-07-01T10:00:01Z" : null
      }),
      { headers: { "Content-Type": "application/json" }, status: 200 }
    );
  }) as typeof fetch;

  try {
    const result = await waitForGitHubSyncJob(
      "workspace-123",
      "sync-job-1",
      {
        intervalMs: 0,
        maxPolls: 2,
        onUpdate: (syncJob) => updates.push(syncJob.status)
      }
    );
    assert.equal(result.status, "succeeded");
    assert.deepEqual(updates, ["running", "succeeded"]);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("cancels a GitHub sync job through its workspace-scoped endpoint", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (input, init) => {
    assert.equal(
      String(input),
      "http://localhost/api/v1/workspaces/workspace-123/github/sync-jobs/sync-job-1/cancel"
    );
    assert.equal(init?.method, "POST");
    return new Response(
      JSON.stringify({
        ...queuedSyncJob,
        status: "cancelled",
        cancel_requested_at: "2026-07-01T10:00:01Z",
        finished_at: "2026-07-01T10:00:01Z"
      }),
      { headers: { "Content-Type": "application/json" }, status: 200 }
    );
  }) as typeof fetch;

  try {
    const result = await cancelGitHubSyncJob(
      "workspace-123",
      "sync-job-1"
    );
    assert.equal(result.status, "cancelled");
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

test("renders one connected workspace with one repository selector and update action", () => {
  const html = renderPanel();

  assert.ok(html.includes(M.githubProductConnect.connectedBadge));
  assert.ok(html.includes(M.githubProductConnect.repositoryControlTitle));
  assert.ok(html.includes("qtwin-io/company-knowledge-os"));
  assert.doesNotMatch(html, /qtwin-io\/another-repo/);
  assert.equal(
    (html.match(new RegExp(M.githubProductConnect.updateData, "g")) ?? []).length,
    1
  );
  assert.match(html, /<select/);
  assert.match(html, /<details class="github-source__safety">/);
  assert.ok(html.includes(M.githubProductConnect.tokenTitle));
  assert.ok(html.includes(M.githubProductConnect.writeTitle));
  assert.doesNotMatch(html, new RegExp(M.githubProductConnect.metricsTitle));
  assert.doesNotMatch(html, new RegExp(M.githubProductConnect.flowLabel));
  assert.doesNotMatch(html, new RegExp(M.githubProductConnect.title));
});

test("summarizes GitHub App real-read readiness from loaded local state", () => {
  assert.deepEqual(
    summarizeGitHubRealReadReadiness(connectedAppStatus, repositories),
    {
      appConfigured: true,
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
    "github_app_not_configured",
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

test("keeps setup behind one explicit action", () => {
  const closed = renderPanel({
    connectionStatus: missingAppStatus,
    repositories: { ...repositories, count: 0, repositories: [] },
    selfServiceSetupEnabled: true,
    setupWizard: <div>SELF_SERVICE_GITHUB_SETUP</div>
  });
  assert.ok(closed.includes(M.githubProductConnect.connectTitle));
  assert.ok(closed.includes(M.githubProductConnect.connectAction));
  assert.doesNotMatch(closed, /SELF_SERVICE_GITHUB_SETUP/);
  assert.doesNotMatch(closed, /FOUNDEROS_GITHUB_APP_ID/);

  const open = renderPanel({
    connectionStatus: missingAppStatus,
    repositories: { ...repositories, count: 0, repositories: [] },
    selfServiceSetupEnabled: true,
    setupOpen: true,
    setupWizard: <div>SELF_SERVICE_GITHUB_SETUP</div>
  });
  assert.ok(open.includes("SELF_SERVICE_GITHUB_SETUP"));
  assert.ok(open.includes(M.githubProductConnect.closeSetupAction));
});

test("shows a continue action for an existing installation instead of creating another", () => {
  const html = renderPanel({
    connectionStatus: {
      ...connectedAppStatus,
      status: "disabled",
      installation_verified: true,
      live_read_available: false,
      app: { ...appConfigured, credential_source: "managed" }
    },
    selfServiceSetupEnabled: true
  });

  assert.ok(html.includes(M.githubProductConnect.connectionAttentionTitle));
  assert.ok(html.includes(M.githubProductConnect.continueSetupAction));
  assert.doesNotMatch(html, new RegExp(M.githubProductConnect.updateData));
});

test("keeps connected data visible but removes mutation controls for viewers", () => {
  const html = renderPanel({ canAdminister: false });

  assert.ok(html.includes("qtwin-io/company-knowledge-os"));
  assert.doesNotMatch(html, new RegExp(M.githubProductConnect.updateData));
  assert.doesNotMatch(html, new RegExp(M.githubProductConnect.manageConnection));
});

test("managed setup shows only the saved repository subset", () => {
  const html = renderPanel({
    connectionStatus: {
      ...connectedAppStatus,
      app: {
        ...appConfigured,
        credential_source: "managed"
      },
      selected_repositories: ["qtwin-io/company-knowledge-os"]
    }
  });

  assert.ok(html.includes("qtwin-io/company-knowledge-os"));
  assert.doesNotMatch(html, /qtwin-io\/another-repo/);
});

test("renders invalid repository and blocks update when GitHub is not ready", () => {
  const invalid = renderPanel({
    connectionStatus: {
      ...connectedAppStatus,
      selected_repositories: ["bad repo"]
    },
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
  assert.ok(missingApp.includes(M.githubProductConnect.connectTitle));
  assert.doesNotMatch(missingApp, new RegExp(M.githubProductConnect.updateData));
});

test("missing product setup never exposes deployment variable names", () => {
  const html = renderPanel({
    connectionStatus: missingAppStatus,
    repositories: { ...repositories, count: 0, repositories: [] },
    selfServiceSetupEnabled: false
  });

  assert.doesNotMatch(html, /FOUNDEROS_GITHUB_APP/);
  assert.match(html, /<details class="github-source__safety">/);
});

test("connected empty state offers repository access management", () => {
  const html = renderPanel({
    repositories: {
      ...repositories,
      count: 0,
      repositories: []
    }
  });

  assert.ok(html.includes(M.githubProductConnect.repositoryListEmptyTitle));
  assert.ok(html.includes(M.githubProductConnect.manageRepositoryAccess));
  assert.doesNotMatch(html, new RegExp(M.githubProductConnect.updateData));
});

test("uses a global sync lock for the selector and update action", () => {
  const html = renderPanel({
    repositorySync: {
      "qtwin-io/another-repo": {
        error: null,
        result: null,
        state: "syncing"
      }
    }
  });

  assert.ok(html.includes(M.githubProductConnect.updatingData));
  assert.match(html, /<select disabled=""/);
  assert.match(html, /<button class="button github-source__primary" disabled=""/);
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
  assert.match(error, /<details class="github-source__error-details">/);
});

test("classifies resolved sync jobs without treating HTTP success as job success", () => {
  assert.equal(classifyGitHubSyncState("succeeded"), "success");
  assert.equal(classifyGitHubSyncState("running"), "pending");
  assert.equal(classifyGitHubSyncState("queued"), "pending");
  assert.equal(classifyGitHubSyncState("failed"), "error");
  assert.equal(classifyGitHubSyncState("cancelled"), "error");
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
  assert.ok(running.includes(M.githubProductConnect.updatingData));
  assert.match(running, /<select disabled=""/);
  assert.match(running, /github-sync-receipt--pending/);
  assert.doesNotMatch(
    running,
    new RegExp(`class="eyebrow">${M.githubProductConnect.receiptEyebrow}<`)
  );

  const cancellable = renderPanel({
    onCancelRepositorySync: () => undefined,
    repositorySync: {
      "qtwin-io/company-knowledge-os": {
        error: null,
        result: {
          ...liveSyncResult,
          sync_job: { ...liveSyncResult.sync_job, status: "queued" }
        },
        state: "pending"
      }
    }
  });
  assert.ok(cancellable.includes(M.githubProductConnect.liveSyncCancel));

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

test("merges durable worker progress into the live sync receipt", () => {
  const result = mergeGitHubSyncJobResult(liveSyncResult, {
    ...queuedSyncJob,
    status: "running",
    attempt_count: 2,
    execution_started: true,
    is_live: true,
    records_seen: 5,
    records_created: 2,
    records_updated: 3,
    progress: {
      phase: "running",
      completed_repositories: ["qtwin-io/company-knowledge-os"],
      total_repositories: 2,
      repositories: [
        {
          full_name: "qtwin-io/company-knowledge-os",
          synced_issues: 2,
          synced_pull_requests: 2,
          skipped_pull_requests: 1
        }
      ],
      counts: {
        repositories: 1,
        issues: 2,
        pull_requests: 2,
        skipped_pull_requests: 1
      }
    }
  });

  assert.equal(result.sync_job.status, "running");
  assert.equal(result.sync_job.attempt_count, 2);
  assert.equal(result.totals.repositories, 1);
  assert.equal(result.totals.issues, 2);
  assert.equal(result.totals.pull_requests, 2);
  assert.equal(result.totals.skipped_pull_requests, 1);
  assert.equal(result.provider_sync_started, true);
  assert.equal(result.persistence_mode, "running");
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
