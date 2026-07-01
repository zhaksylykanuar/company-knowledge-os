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

type GitHubProductConnectPanelViewProps = {
  connectionStatus: GitHubConnectionStatusResponse | null;
  error: string | null;
  liveSyncError: string | null;
  liveSyncResult: GitHubAppLiveSyncResponse | null;
  liveSyncState: LiveSyncState;
  onRetry?: () => void;
  onRepositoryChange?: (value: string) => void;
  onRunLiveSync?: () => void;
  repositories: GitHubRepositoryListResponse | null;
  repositoryInput: string;
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
  const [repositoryInput, setRepositoryInput] = useState("");
  const [liveSyncError, setLiveSyncError] = useState<string | null>(null);
  const [liveSyncResult, setLiveSyncResult] =
    useState<GitHubAppLiveSyncResponse | null>(null);
  const [liveSyncState, setLiveSyncState] = useState<LiveSyncState>("idle");
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
        setRepositoryInput((current) => {
          if (current.trim()) {
            return current;
          }
          return repositoryList.repositories[0]?.full_name ?? "";
        });
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

  async function syncExplicitRepository() {
    const repository = repositoryInput.trim();
    if (!workspaceId || !connectionStatus?.connection_id || !repository) {
      return;
    }
    setLiveSyncError(null);
    setLiveSyncResult(null);
    setLiveSyncState("syncing");
    try {
      const payload = await runGitHubAppLiveSync(workspaceId, {
        connection_id: connectionStatus.connection_id,
        repositories: [repository],
        include_issues: true,
        include_pull_requests: true
      });
      setLiveSyncResult(payload);
      setLiveSyncState("success");
      setReloadKey((current) => current + 1);
    } catch (caught: unknown) {
      setLiveSyncError(caught instanceof Error ? caught.message : M.common.requestFailed);
      setLiveSyncState("error");
    }
  }

  return (
    <GitHubProductConnectPanelView
      connectionStatus={connectionStatus}
      error={error}
      liveSyncError={liveSyncError}
      liveSyncResult={liveSyncResult}
      liveSyncState={liveSyncState}
      onRetry={() => setReloadKey((current) => current + 1)}
      onRepositoryChange={setRepositoryInput}
      onRunLiveSync={syncExplicitRepository}
      repositories={repositories}
      repositoryInput={repositoryInput}
      state={state}
    />
  );
}

export function GitHubProductConnectPanelView({
  connectionStatus,
  error,
  liveSyncError,
  liveSyncResult,
  liveSyncState,
  onRetry,
  onRepositoryChange,
  onRunLiveSync,
  repositories,
  repositoryInput,
  state
}: GitHubProductConnectPanelViewProps) {
  const appStatus = connectionStatus?.app ?? null;
  const appConnectionReady =
    connectionStatus?.connection_method === "github_app_installation" &&
    connectionStatus.has_connection_record;
  const normalizedRepository = repositoryInput.trim();
  const repositoryLooksValid = isRepositoryFullName(normalizedRepository);
  const canRunLiveSync =
    appConnectionReady && repositoryLooksValid && liveSyncState !== "syncing";

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
            <label htmlFor="github-app-live-sync-repository">
              {M.githubProductConnect.liveSyncRepositoryLabel}
            </label>
            <input
              aria-describedby="github-app-live-sync-repository-note"
              disabled={!appConnectionReady || liveSyncState === "syncing"}
              id="github-app-live-sync-repository"
              onChange={(event) => onRepositoryChange?.(event.target.value)}
              placeholder={M.githubProductConnect.liveSyncRepositoryPlaceholder}
              type="text"
              value={repositoryInput}
            />
            <p className="muted" id="github-app-live-sync-repository-note">
              {M.githubProductConnect.liveSyncRepositoryNote}
            </p>
            {normalizedRepository && !repositoryLooksValid ? (
              <p className="error-text">{M.githubProductConnect.liveSyncRepositoryInvalid}</p>
            ) : null}
            {!appConnectionReady ? (
              <p className="muted">{M.githubProductConnect.liveSyncRequiresApp}</p>
            ) : null}
            <div className="actions-row">
              <button
                className="button"
                disabled={!canRunLiveSync}
                onClick={onRunLiveSync}
                type="button"
              >
                {liveSyncState === "syncing"
                  ? M.githubProductConnect.liveSyncRunning
                  : M.githubProductConnect.liveSyncRun}
              </button>
            </div>
          </section>

          {liveSyncState === "error" ? (
            <ErrorState
              description={liveSyncError ?? M.githubProductConnect.liveSyncFailedDescription}
              title={M.githubProductConnect.liveSyncFailedTitle}
            />
          ) : null}

          {liveSyncResult ? (
            <section className="callout">
              <strong>{M.githubProductConnect.liveSyncResultTitle}</strong>
              <p>
                {T.githubAppLiveSyncResult(
                  liveSyncResult.totals.repositories,
                  liveSyncResult.totals.issues,
                  liveSyncResult.totals.pull_requests,
                  liveSyncResult.sync_job.status
                )}
              </p>
              <p className="success-text">{M.githubProductConnect.liveSyncNoWrites}</p>
              {liveSyncResult.warnings.length > 0 ? (
                <ul className="meta-list" aria-label={M.common.warnings}>
                  {liveSyncResult.warnings.map((warning) => (
                    <li key={warning}>{warning}</li>
                  ))}
                </ul>
              ) : null}
            </section>
          ) : null}

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
