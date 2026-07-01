"use client";

import { useEffect, useState } from "react";

import {
  fetchGitHubConnectionStatus,
  fetchGitHubRepositories
} from "../lib/api";
import { M, T } from "../lib/messages";
import { useWorkspaceId } from "../lib/session";
import type {
  GitHubConnectionStatusResponse,
  GitHubRepositoryListResponse
} from "../lib/types";
import { EmptyState } from "./EmptyState";
import { ErrorState } from "./ErrorState";
import { LoadingState } from "./LoadingState";
import { SourceLink } from "./SourceLink";
import { StatusCard } from "./StatusCard";

type ProductConnectState = "loading" | "ready" | "error" | "missing";

type GitHubProductConnectPanelViewProps = {
  connectionStatus: GitHubConnectionStatusResponse | null;
  error: string | null;
  onRetry?: () => void;
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

  return (
    <GitHubProductConnectPanelView
      connectionStatus={connectionStatus}
      error={error}
      onRetry={() => setReloadKey((current) => current + 1)}
      repositories={repositories}
      state={state}
    />
  );
}

export function GitHubProductConnectPanelView({
  connectionStatus,
  error,
  onRetry,
  repositories,
  state
}: GitHubProductConnectPanelViewProps) {
  const appStatus = connectionStatus?.app ?? null;
  const appConnectionReady =
    connectionStatus?.connection_method === "github_app_installation" &&
    connectionStatus.has_connection_record;

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
