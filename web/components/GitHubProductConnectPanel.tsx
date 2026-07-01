"use client";

import { useEffect, useState } from "react";

import {
  fetchGitHubConnectionStatus,
  fetchGitHubRepositories,
  runGitHubAppLiveSync
} from "../lib/api";
import { M, T } from "../lib/messages";
import { useWorkspaceId } from "../lib/session";
import type {
  GitHubAppLiveSyncResponse,
  GitHubConnectionStatusResponse,
  GitHubRepositoryListResponse
} from "../lib/types";
import { EmptyState } from "./EmptyState";
import { ErrorState } from "./ErrorState";
import { LoadingState } from "./LoadingState";
import { SourceLink } from "./SourceLink";
import { StatusCard } from "./StatusCard";

type ProductConnectState = "loading" | "ready" | "error" | "missing";
type LiveSyncState = "idle" | "syncing" | "success" | "error";
type RepositorySyncStatus = {
  error: string | null;
  result: GitHubAppLiveSyncResponse | null;
  state: LiveSyncState;
};

type GitHubProductConnectPanelViewProps = {
  connectionStatus: GitHubConnectionStatusResponse | null;
  error: string | null;
  onRetry?: () => void;
  onRunRepositorySync?: (repositoryFullName: string) => void;
  repositorySync: Record<string, RepositorySyncStatus>;
  repositories: GitHubRepositoryListResponse | null;
  state: ProductConnectState;
};

export function GitHubProductConnectPanel() {
  const workspaceId = useWorkspaceId();
  const [connectionStatus, setConnectionStatus] =
    useState<GitHubConnectionStatusResponse | null>(null);
  const [repositories, setRepositories] =
    useState<GitHubRepositoryListResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [repositorySync, setRepositorySync] = useState<
    Record<string, RepositorySyncStatus>
  >({});
  const [state, setState] = useState<ProductConnectState>("loading");

  useEffect(() => {
    if (!workspaceId) {
      setConnectionStatus(null);
      setRepositories(null);
      setError(null);
      setState("missing");
      return;
    }

    let cancelled = false;
    setError(null);
    setState("loading");
    Promise.all([
      fetchGitHubConnectionStatus(workspaceId),
      fetchGitHubRepositories(workspaceId)
    ])
      .then(([status, repositoryList]) => {
        if (cancelled) {
          return;
        }
        setConnectionStatus(status);
        setRepositories(repositoryList);
        setState("ready");
      })
      .catch((caught: unknown) => {
        if (cancelled) {
          return;
        }
        setConnectionStatus(null);
        setRepositories(null);
        setError(caught instanceof Error ? caught.message : M.common.requestFailed);
        setState("error");
      });

    return () => {
      cancelled = true;
    };
  }, [workspaceId, reloadKey]);

  async function syncRepository(repositoryFullName: string) {
    const repository = repositoryFullName.trim();
    if (!workspaceId || !connectionStatus?.connection_id || !repository) {
      return;
    }
    setRepositorySync((current) => ({
      ...current,
      [repository]: { error: null, result: null, state: "syncing" }
    }));
    try {
      const payload = await runGitHubAppLiveSync(workspaceId, {
        connection_id: connectionStatus.connection_id,
        repositories: [repository],
        include_issues: true,
        include_pull_requests: true
      });
      setRepositorySync((current) => ({
        ...current,
        [repository]: { error: null, result: payload, state: "success" }
      }));
      setReloadKey((current) => current + 1);
    } catch (caught: unknown) {
      setRepositorySync((current) => ({
        ...current,
        [repository]: {
          error: caught instanceof Error ? caught.message : M.common.requestFailed,
          result: null,
          state: "error"
        }
      }));
    }
  }

  return (
    <GitHubProductConnectPanelView
      connectionStatus={connectionStatus}
      error={error}
      onRetry={() => setReloadKey((current) => current + 1)}
      onRunRepositorySync={syncRepository}
      repositorySync={repositorySync}
      repositories={repositories}
      state={state}
    />
  );
}

export function GitHubProductConnectPanelView({
  connectionStatus,
  error,
  onRetry,
  onRunRepositorySync,
  repositorySync,
  repositories,
  state
}: GitHubProductConnectPanelViewProps) {
  const appStatus = connectionStatus?.app ?? null;
  const appConnectionReady =
    connectionStatus?.connection_method === "github_app_installation" &&
    connectionStatus.has_connection_record;
  const repositoryItems = repositories?.repositories ?? [];

  return (
    <section
      aria-labelledby="github-product-connect-title"
      className="panel github-product-connect"
    >
      <div className="section-header">
        <div>
          <span className="eyebrow">{M.githubProductConnect.eyebrow}</span>
          <h2 id="github-product-connect-title">
            {M.githubProductConnect.title}
          </h2>
        </div>
        <span className="badge">{M.githubProductConnect.badgeReadOnly}</span>
      </div>

      <p className="muted">{M.githubProductConnect.description}</p>

      {state === "loading" ? (
        <LoadingState label={M.githubProductConnect.loading} />
      ) : null}

      {state === "missing" ? (
        <EmptyState
          description={M.githubProductConnect.noWorkspaceDescription}
          title={M.common.noWorkspaceTitle}
        />
      ) : null}

      {state === "error" ? (
        <>
          <ErrorState
            description={error ?? M.githubProductConnect.unavailableDescription}
            title={M.githubProductConnect.unavailableTitle}
          />
          <button className="button secondary" onClick={onRetry} type="button">
            {M.common.retry}
          </button>
        </>
      ) : null}

      {state === "ready" && connectionStatus && appStatus ? (
        <>
          <section className="grid" aria-label={M.githubProductConnect.title}>
            <StatusCard
              description={githubAppDescription(connectionStatus)}
              title={M.githubProductConnect.appTitle}
              value={
                appConnectionReady
                  ? M.githubProductConnect.appConnected
                  : appStatus.configured
                    ? M.githubProductConnect.appConfigured
                    : M.githubProductConnect.appNotConfigured
              }
            />
            <StatusCard
              description={T.githubRepositorySurfaceDescription(
                repositories?.source ?? M.common.unknown
              )}
              title={M.githubProductConnect.repositoriesTitle}
              value={String(repositories?.count ?? 0)}
            />
            <StatusCard
              description={M.githubProductConnect.tokenDescription}
              title={M.githubProductConnect.tokenTitle}
              value={
                appStatus.installation_tokens_persisted
                  ? M.common.yes
                  : M.common.no
              }
            />
            <StatusCard
              description={M.githubProductConnect.writeDescription}
              title={M.githubProductConnect.writeTitle}
              value={
                appStatus.provider_writes_enabled ? M.common.enabled : M.common.notEnabled
              }
            />
          </section>

          {!appStatus.configured && appStatus.missing_env.length > 0 ? (
            <section className="callout">
              <strong>{M.githubProductConnect.missingEnvTitle}</strong>
              <ul className="meta-list">
                {appStatus.missing_env.map((name) => (
                  <li key={name}>{name}</li>
                ))}
              </ul>
            </section>
          ) : null}

          {appStatus.setup_url ? (
            <p className="actions-row">
              <SourceLink className="button secondary" url={appStatus.setup_url}>
                {M.githubProductConnect.openSetup}
              </SourceLink>
            </p>
          ) : null}

          <section className="callout">
            <strong>{M.githubProductConnect.liveSyncTitle}</strong>
            <p>{M.githubProductConnect.liveSyncDescription}</p>
            <p className="muted">
              {M.githubProductConnect.liveSyncRepositoryNote}
            </p>
            {!appConnectionReady ? (
              <p className="muted">{M.githubProductConnect.liveSyncRequiresApp}</p>
            ) : null}

            {repositoryItems.length === 0 ? (
              <EmptyState
                description={M.githubProductConnect.repositoryListEmptyDescription}
                title={M.githubProductConnect.repositoryListEmptyTitle}
              />
            ) : (
              <section
                aria-label={M.githubProductConnect.repositoryListTitle}
                className="stack"
              >
                <strong>{M.githubProductConnect.repositoryListTitle}</strong>
                {repositoryItems.map((repository) => {
                  const sync = repositorySync[repository.full_name] ?? {
                    error: null,
                    result: null,
                    state: "idle" as LiveSyncState
                  };
                  const repositoryValid = isRepositoryFullName(repository.full_name);
                  const canSyncRepository =
                    appConnectionReady &&
                    repositoryValid &&
                    sync.state !== "syncing";
                  return (
                    <article className="card" key={repository.full_name}>
                      <div className="section-header">
                        <div>
                          <h3>{repository.full_name}</h3>
                          <p className="muted">
                            {T.githubRepositoryMeta(
                              repository.visibility,
                              repository.archived,
                              repository.source
                            )}
                          </p>
                          {repository.last_activity_at ? (
                            <p className="muted">
                              {T.githubRepositoryLastActivity(
                                repository.last_activity_at
                              )}
                            </p>
                          ) : null}
                        </div>
                        <button
                          className="button"
                          disabled={!canSyncRepository}
                          onClick={() => onRunRepositorySync?.(repository.full_name)}
                          type="button"
                        >
                          {sync.state === "syncing"
                            ? M.githubProductConnect.liveSyncRunning
                            : M.githubProductConnect.liveSyncRun}
                        </button>
                      </div>

                      {repository.source_url ? (
                        <p>
                          <SourceLink url={repository.source_url}>
                            {M.common.openSource}
                          </SourceLink>
                        </p>
                      ) : null}

                      {!repositoryValid ? (
                        <p className="error-text">
                          {M.githubProductConnect.liveSyncRepositoryInvalid}
                        </p>
                      ) : null}

                      {sync.state === "error" ? (
                        <ErrorState
                          description={
                            sync.error ??
                            M.githubProductConnect.liveSyncFailedDescription
                          }
                          title={M.githubProductConnect.liveSyncFailedTitle}
                        />
                      ) : null}

                      {sync.result ? (
                        <section className="callout">
                          <strong>{M.githubProductConnect.liveSyncResultTitle}</strong>
                          <p>
                            {T.githubAppLiveSyncResult(
                              sync.result.totals.repositories,
                              sync.result.totals.issues,
                              sync.result.totals.pull_requests,
                              sync.result.sync_job.status
                            )}
                          </p>
                          <p className="success-text">
                            {M.githubProductConnect.liveSyncNoWrites}
                          </p>
                          {sync.result.warnings.length > 0 ? (
                            <ul className="meta-list" aria-label={M.common.warnings}>
                              {sync.result.warnings.map((warning) => (
                                <li key={warning}>{warning}</li>
                              ))}
                            </ul>
                          ) : null}
                        </section>
                      ) : null}
                    </article>
                  );
                })}
              </section>
            )}
          </section>

          {[...connectionStatus.warnings, ...(repositories?.warnings ?? [])].length > 0 ? (
            <ul className="meta-list" aria-label={M.common.warnings}>
              {[...connectionStatus.warnings, ...(repositories?.warnings ?? [])].map(
                (warning) => (
                  <li key={warning}>{warning}</li>
                )
              )}
            </ul>
          ) : null}
        </>
      ) : null}
    </section>
  );
}

function githubAppDescription(status: GitHubConnectionStatusResponse): string {
  if (status.connection_method === "github_app_installation") {
    return status.display_name ?? M.githubProductConnect.appInstallationDescription;
  }
  if (status.app.configured) {
    return M.githubProductConnect.appReadyDescription;
  }
  return M.githubProductConnect.appMissingDescription;
}

function isRepositoryFullName(value: string): boolean {
  return /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(value);
}
