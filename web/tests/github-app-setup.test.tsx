import assert from "node:assert/strict";
import test from "node:test";

import { renderToStaticMarkup } from "react-dom/server";

import {
  buildGitHubManifestFormSpec,
  GitHubAppSetupWizardView
} from "../components/GitHubAppSetupWizard";
import {
  beginGitHubAppInstallSetup,
  beginGitHubAppManifestSetup,
  buildWorkspaceGitHubAppSetupInstallPath,
  buildWorkspaceGitHubAppSetupManifestPath,
  buildWorkspaceGitHubAppSetupPath,
  buildWorkspaceGitHubAppSetupRepositoriesPath,
  buildWorkspaceGitHubAppSetupRepositoriesRefreshPath,
  buildWorkspaceGitHubAppSetupRestartPath,
  fetchGitHubAppSetupStatus,
  refreshGitHubAppSetupRepositories,
  restartGitHubAppSetup,
  selectGitHubAppRepositories
} from "../lib/api";
import { M } from "../lib/messages";
import type { GitHubAppSetupStatus } from "../lib/types";

const notStartedStatus: GitHubAppSetupStatus = {
  phase: "not_started",
  credential_source: "none",
  app_slug: null,
  app_name: null,
  installation_account: null,
  installation_settings_url: null,
  repository_count: 0,
  repositories: [],
  selected_repositories: [],
  expires_at: null,
  error_code: null,
  install_url: null,
  can_manage: true,
  can_restart: false,
  setup_owned_by_current_user: true,
  installation_verified: false,
  secrets_encrypted: false,
  installation_tokens_persisted: false,
  provider_writes_enabled: false
};

const repositorySelectionStatus: GitHubAppSetupStatus = {
  ...notStartedStatus,
  phase: "repository_selection",
  credential_source: "managed",
  app_slug: "founderos-local",
  app_name: "FounderOS Local",
  installation_account: "qtwin-io",
  installation_settings_url:
    "https://github.com/organizations/qtwin-io/settings/installations/123",
  repository_count: 10,
  repositories: Array.from({ length: 10 }, (_, index) => ({
    id: `repo-${index + 1}`,
    name: `repository-${index + 1}`,
    full_name: `qtwin-io/repository-${index + 1}`,
    private: true,
    visibility: "private",
    archived: false,
    default_branch: "main",
    source_url: `https://github.com/qtwin-io/repository-${index + 1}`,
    last_activity_at: null
  })),
  selected_repositories: ["qtwin-io/repository-1"],
  can_restart: true,
  installation_verified: true,
  secrets_encrypted: true
};

const connectedStatus: GitHubAppSetupStatus = {
  ...repositorySelectionStatus,
  phase: "connected",
  selected_repositories: [
    "qtwin-io/repository-1",
    "qtwin-io/repository-2"
  ]
};

function renderWizard(
  status: GitHubAppSetupStatus,
  overrides: Partial<Parameters<typeof GitHubAppSetupWizardView>[0]> = {}
): string {
  return renderToStaticMarkup(
    <GitHubAppSetupWizardView
      action={overrides.action ?? "idle"}
      actionError={overrides.actionError ?? null}
      canAdminister={overrides.canAdminister ?? true}
      loadState={overrides.loadState ?? "ready"}
      onInstall={overrides.onInstall ?? (() => undefined)}
      onOrganizationLoginChange={
        overrides.onOrganizationLoginChange ?? (() => undefined)
      }
      onOwnerTypeChange={overrides.onOwnerTypeChange ?? (() => undefined)}
      onRefreshRepositories={
        overrides.onRefreshRepositories ?? (() => undefined)
      }
      onRepositoryToggle={overrides.onRepositoryToggle ?? (() => undefined)}
      onRestart={overrides.onRestart ?? (() => undefined)}
      onRetry={overrides.onRetry ?? (() => undefined)}
      onSaveRepositories={overrides.onSaveRepositories ?? (() => undefined)}
      onStart={overrides.onStart ?? (() => undefined)}
      organizationLogin={overrides.organizationLogin ?? ""}
      ownerType={overrides.ownerType ?? "user"}
      selectedRepositories={
        overrides.selectedRepositories ?? new Set(status.selected_repositories)
      }
      status={overrides.status === undefined ? status : overrides.status}
    />
  );
}

test("builds workspace-scoped GitHub App setup paths", () => {
  assert.equal(
    buildWorkspaceGitHubAppSetupPath("workspace/123"),
    "/api/v1/workspaces/workspace%2F123/github/app-setup"
  );
  assert.equal(
    buildWorkspaceGitHubAppSetupManifestPath("workspace-123"),
    "/api/v1/workspaces/workspace-123/github/app-setup/manifest"
  );
  assert.equal(
    buildWorkspaceGitHubAppSetupInstallPath("workspace-123"),
    "/api/v1/workspaces/workspace-123/github/app-setup/install"
  );
  assert.equal(
    buildWorkspaceGitHubAppSetupRepositoriesPath("workspace-123"),
    "/api/v1/workspaces/workspace-123/github/app-setup/repositories"
  );
  assert.equal(
    buildWorkspaceGitHubAppSetupRepositoriesRefreshPath("workspace-123"),
    "/api/v1/workspaces/workspace-123/github/app-setup/repositories/refresh"
  );
  assert.equal(
    buildWorkspaceGitHubAppSetupRestartPath("workspace-123"),
    "/api/v1/workspaces/workspace-123/github/app-setup/restart"
  );
});

test("uses the exact setup API request contract", async () => {
  const originalFetch = globalThis.fetch;
  const seen: { body: string | null; method: string; url: string }[] = [];
  globalThis.fetch = (async (input, init) => {
    const url = String(input);
    seen.push({
      body: typeof init?.body === "string" ? init.body : null,
      method: init?.method ?? "GET",
      url
    });
    if (url.endsWith("/manifest")) {
      return Response.json({
        phase: "manifest_pending",
        action_url: "https://github.com/organizations/qtwin-io/settings/apps/new?state=opaque",
        manifest: "{\"name\":\"FounderOS\"}",
        expires_at: "2026-07-14T12:00:00Z"
      });
    }
    if (url.endsWith("/install")) {
      return Response.json({
        phase: "installation_pending",
        redirect_url: "https://github.com/apps/founderos/installations/new?state=opaque",
        expires_at: "2026-07-14T12:00:00Z"
      });
    }
    if (url.endsWith("/repositories/refresh")) {
      return Response.json(repositorySelectionStatus);
    }
    if (url.endsWith("/repositories")) {
      return Response.json({
        phase: "connected",
        connection_id: "connection-1",
        selected_repositories: ["qtwin-io/repository-1"],
        repository_count: 1
      });
    }
    if (url.endsWith("/restart")) {
      return Response.json({ phase: "not_started" });
    }
    return Response.json(notStartedStatus);
  }) as typeof fetch;

  try {
    await fetchGitHubAppSetupStatus("workspace-123");
    await beginGitHubAppManifestSetup("workspace-123", {
      app_origin: "http://127.0.0.1:3000",
      owner_type: "organization",
      organization_login: "qtwin-io"
    });
    await beginGitHubAppInstallSetup("workspace-123");
    await selectGitHubAppRepositories("workspace-123", {
      repositories: ["qtwin-io/repository-1"]
    });
    await refreshGitHubAppSetupRepositories("workspace-123");
    await restartGitHubAppSetup("workspace-123");
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.deepEqual(seen, [
    {
      body: null,
      method: "GET",
      url: "http://localhost/api/v1/workspaces/workspace-123/github/app-setup"
    },
    {
      body: JSON.stringify({
        app_origin: "http://127.0.0.1:3000",
        owner_type: "organization",
        organization_login: "qtwin-io"
      }),
      method: "POST",
      url: "http://localhost/api/v1/workspaces/workspace-123/github/app-setup/manifest"
    },
    {
      body: null,
      method: "POST",
      url: "http://localhost/api/v1/workspaces/workspace-123/github/app-setup/install"
    },
    {
      body: JSON.stringify({ repositories: ["qtwin-io/repository-1"] }),
      method: "POST",
      url: "http://localhost/api/v1/workspaces/workspace-123/github/app-setup/repositories"
    },
    {
      body: null,
      method: "POST",
      url: "http://localhost/api/v1/workspaces/workspace-123/github/app-setup/repositories/refresh"
    },
    {
      body: null,
      method: "POST",
      url: "http://localhost/api/v1/workspaces/workspace-123/github/app-setup/restart"
    }
  ]);
});

test("manifest launch form posts only the manifest to GitHub", () => {
  assert.deepEqual(
    buildGitHubManifestFormSpec(
      "https://github.com/settings/apps/new?state=opaque",
      "{\"name\":\"FounderOS\"}"
    ),
    {
      action: "https://github.com/settings/apps/new?state=opaque",
      fields: [{ name: "manifest", value: "{\"name\":\"FounderOS\"}" }],
      method: "POST"
    }
  );
  assert.equal(
    buildGitHubManifestFormSpec(
      "https://attacker.example/settings/apps/new?state=opaque",
      "{}"
    ),
    null
  );
  assert.equal(
    buildGitHubManifestFormSpec("https://github.com/settings/apps/new", "  "),
    null
  );
});

test("renders one clear self-service start action without env instructions", () => {
  const html = renderWizard(notStartedStatus);

  assert.ok(html.includes(M.githubAppSetup.title));
  assert.ok(html.includes(M.githubAppSetup.badge));
  assert.ok(html.includes(M.githubAppSetup.start));
  assert.ok(html.includes(M.githubAppSetup.ownerUser));
  assert.ok(html.includes(M.githubAppSetup.ownerOrganization));
  assert.match(html, /aria-current="step"/);
  assert.doesNotMatch(html, /FOUNDEROS_GITHUB/);
  assert.doesNotMatch(html, /env-пол/i);
  assert.doesNotMatch(html, /private key/i);
});

test("shows organization login only for organization ownership", () => {
  const personal = renderWizard(notStartedStatus);
  const organization = renderWizard(notStartedStatus, {
    organizationLogin: "qtwin-io",
    ownerType: "organization"
  });

  assert.doesNotMatch(personal, new RegExp(M.githubAppSetup.organizationPlaceholder));
  assert.ok(organization.includes(M.githubAppSetup.organizationLabel));
  assert.match(organization, /value="qtwin-io"/);
});

test("keeps setup actions owner-admin only", () => {
  const html = renderWizard(
    { ...notStartedStatus, can_manage: false },
    { canAdminister: false }
  );

  assert.ok(html.includes(M.githubAppSetup.adminOnly));
  assert.doesNotMatch(html, new RegExp(M.githubAppSetup.start));
  assert.doesNotMatch(html, new RegExp(M.githubAppSetup.ownerOrganization));
});

test("renders installation and verification as distinct understandable phases", () => {
  const install = renderWizard({
    ...notStartedStatus,
    phase: "installation_pending",
    credential_source: "managed",
    app_slug: "founderos-local",
    app_name: "FounderOS Local"
  });
  const verifying = renderWizard({
    ...notStartedStatus,
    phase: "oauth_exchanging",
    credential_source: "managed"
  });

  assert.ok(install.includes(M.githubAppSetup.installTitle));
  assert.ok(install.includes(M.githubAppSetup.install));
  assert.ok(verifying.includes(M.githubAppSetup.verifyTitle));
  assert.ok(verifying.includes(M.githubAppSetup.verifyDescription));
  assert.match(verifying, /role="status"/);
});

test("renders repository selection with eight choices before disclosure", () => {
  const html = renderWizard(repositorySelectionStatus);
  const beforeDisclosure = html.split("<details>")[0];

  assert.ok(html.includes(M.githubAppSetup.repositoriesTitle));
  assert.equal(
    (beforeDisclosure.match(/class="github-app-setup__repository"/g) ?? []).length,
    8
  );
  assert.ok(html.includes("Показать ещё: 2"));
  assert.match(html, /checked=""/);
  assert.ok(html.includes(M.githubAppSetup.saveRepositories));
  assert.ok(html.includes(`${M.githubAppSetup.saveRepositories} · 1`));
  assert.ok(html.includes(M.githubAppSetup.repositoriesDescription));
});

test("renders a compact connected receipt without a broken reinstall action", () => {
  const owner = renderWizard(connectedStatus);
  const viewer = renderWizard(
    { ...connectedStatus, can_manage: false },
    { canAdminister: false }
  );

  assert.ok(owner.includes(M.githubAppSetup.connectedTitle));
  assert.ok(owner.includes("FounderOS Local"));
  assert.ok(owner.includes("qtwin-io"));
  assert.doesNotMatch(owner, new RegExp(M.githubAppSetup.install));
  assert.ok(viewer.includes(M.githubAppSetup.connectedTitle));
  assert.doesNotMatch(viewer, new RegExp(M.githubAppSetup.install));
  assert.ok(owner.includes(M.githubAppSetup.openRepositoryAccess));
  assert.ok(owner.includes(M.githubAppSetup.refreshRepositorySelection));
  assert.doesNotMatch(viewer, new RegExp(M.githubAppSetup.openRepositoryAccess));
  assert.doesNotMatch(
    viewer,
    new RegExp(M.githubAppSetup.refreshRepositorySelection)
  );
  assert.match(owner, /aria-live="polite"/);
  assert.match(owner, /tabindex="-1"/);
  assert.match(
    owner,
    new RegExp(`aria-label="${M.githubAppSetup.connectedTitle}"`)
  );
});

test("offers an in-platform repository refresh when GitHub returns no repositories", () => {
  const html = renderWizard({
    ...repositorySelectionStatus,
    repository_count: 0,
    repositories: [],
    selected_repositories: []
  });

  assert.ok(html.includes(M.githubAppSetup.repositoriesEmptyTitle));
  assert.ok(html.includes(M.githubAppSetup.refreshRepositories));
  assert.ok(html.includes(M.githubAppSetup.openRepositoryAccess));
  assert.match(
    html,
    /https:\/\/github\.com\/organizations\/qtwin-io\/settings\/installations\/123/
  );
  assert.doesNotMatch(html, new RegExp(M.githubAppSetup.install));
});

test("maps provider failures to safe user copy without exposing error codes", () => {
  const html = renderWizard({
    ...notStartedStatus,
    phase: "failed",
    error_code: "installation_not_visible: raw-provider-detail",
    can_restart: true
  });

  assert.ok(html.includes(M.githubAppSetup.failedTitle));
  assert.ok(html.includes(M.githubAppSetup.errorInstallationMissing));
  assert.ok(html.includes(M.githubAppSetup.restart));
  assert.doesNotMatch(html, /raw-provider-detail/);
  assert.doesNotMatch(html, /aria-current="step"/);
});
