"use client";

import { useEffect, useState } from "react";

import {
  fetchGitHubConnectionStatus,
  runGitHubLocalSync
} from "../lib/api";
import { M, T } from "../lib/messages";
import { useWorkspaceId } from "../lib/session";
import type {
  GitHubConnectionStatusResponse,
  GitHubLocalSyncResponse
} from "../lib/types";
import { EmptyState } from "./EmptyState";
import { ErrorState } from "./ErrorState";
import { LoadingState } from "./LoadingState";
import { StatusCard } from "./StatusCard";

type SyncControlStatus = "loading" | "ready" | "syncing" | "success" | "error" | "missing";

type GitHubSyncControlsProps = {
  onSyncComplete?: () => void;
};

type GitHubSyncControlsViewProps = {
  connectionStatus: GitHubConnectionStatusResponse | null;
  error: string | null;
  onRetry?: () => void;
  onSync?: () => void;
  result: GitHubLocalSyncResponse | null;
  status: SyncControlStatus;
};

export function GitHubSyncControls({ onSyncComplete }: GitHubSyncControlsProps) {
  const workspaceId = useWorkspaceId();
  const [connectionStatus, setConnectionStatus] =
    useState<GitHubConnectionStatusResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [result, setResult] = useState<GitHubLocalSyncResponse | null>(null);
  const [status, setStatus] = useState<SyncControlStatus>("loading");

  useEffect(() => {
    if (!workspaceId) {
      setConnectionStatus(null);
      setError(null);
      setStatus("missing");
      return;
    }

    let cancelled = false;
    setStatus("loading");
    setError(null);
    fetchGitHubConnectionStatus(workspaceId)
      .then((payload) => {
        if (cancelled) {
          return;
        }
        setConnectionStatus(payload);
        setStatus("ready");
      })
      .catch((caught: unknown) => {
        if (cancelled) {
          return;
        }
        setConnectionStatus(null);
        setError(caught instanceof Error ? caught.message : M.common.requestFailed);
        setStatus("error");
      });

    return () => {
      cancelled = true;
    };
  }, [workspaceId, reloadKey]);

  async function syncLocalGitHubData() {
    if (!workspaceId) {
      setStatus("missing");
      return;
    }
    setError(null);
    setStatus("syncing");
    try {
      const payload = await runGitHubLocalSync(workspaceId);
      setResult(payload);
      setStatus("success");
      onSyncComplete?.();
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : M.common.requestFailed);
      setStatus("error");
    }
  }

  return (
    <GitHubSyncControlsView
      connectionStatus={connectionStatus}
      error={error}
      onRetry={() => setReloadKey((current) => current + 1)}
      onSync={syncLocalGitHubData}
      result={result}
      status={status}
    />
  );
}

export function GitHubSyncControlsView({
  connectionStatus,
  error,
  onRetry,
  onSync,
  result,
  status
}: GitHubSyncControlsViewProps) {
  const canSync = connectionStatus?.has_connection_record && connectionStatus.status === "connected";
  const isSyncing = status === "syncing";

  return (
    <section className="panel github-sync-controls" aria-labelledby="github-sync-title">
      <div className="section-header">
        <div>
          <span className="eyebrow">{M.githubSync.eyebrow}</span>
          <h2 id="github-sync-title">{M.githubSync.title}</h2>
        </div>
        <span className="badge">{M.githubSync.badgeNoLiveProvider}</span>
      </div>

      {status === "loading" ? <LoadingState label={M.githubSync.loading} /> : null}

      {status === "missing" ? (
        <EmptyState
          description={M.githubSync.noWorkspaceDescription}
          title={M.common.noWorkspaceTitle}
        />
      ) : null}

      {status === "error" && !connectionStatus ? (
        <>
          <ErrorState
            description={error ?? M.githubSync.stateUnavailableDescription}
            title={M.githubSync.stateUnavailableTitle}
          />
          <button className="button secondary" onClick={onRetry} type="button">
            {M.common.retry}
          </button>
        </>
      ) : null}

      {connectionStatus ? (
        <>
          <section className="grid" aria-label={M.githubSync.title}>
            <StatusCard
              description={connectionDescription(connectionStatus)}
              title={M.githubSync.connectionRecordTitle}
              value={connectionStatus.has_connection_record ? connectionStatus.status : M.githubSync.connectionRecordMissing}
            />
            <StatusCard
              description={M.githubSync.executionModeDescription}
              title={M.githubSync.executionModeTitle}
              value={M.githubSync.executionModeValue}
            />
            <StatusCard
              description={T.repoReadSource(connectionStatus.repository_read_source)}
              title={M.githubSync.repoSourceTitle}
              value={connectionStatus.repository_read_available ? M.githubSync.repoSourceAvailable : M.githubSync.repoSourceUnavailable}
            />
          </section>

          {!connectionStatus.has_connection_record ? (
            <EmptyState
              description={M.githubSync.connectionRequiredDescription}
              title={M.githubSync.connectionRequiredTitle}
            />
          ) : null}

          {connectionStatus.has_connection_record && connectionStatus.status !== "connected" ? (
            <EmptyState
              description={T.connectionNotReady(connectionStatus.status)}
              title={M.githubSync.connectionNotReadyTitle}
            />
          ) : null}

          {connectionStatus.warnings.length > 0 ? (
            <ul className="meta-list" aria-label={M.githubSync.title}>
              {connectionStatus.warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          ) : null}

          <div className="actions-row">
            <button
              className="button"
              disabled={!canSync || isSyncing}
              onClick={onSync}
              type="button"
            >
              {isSyncing ? M.githubSync.runningSync : M.githubSync.runSync}
            </button>
            <button className="button secondary" onClick={onRetry} type="button">
              {M.common.refreshStatus}
            </button>
          </div>

          {status === "error" ? (
            <ErrorState
              description={error ?? M.githubSync.syncFailedDescription}
              title={M.githubSync.syncFailedTitle}
            />
          ) : null}

          {result ? (
            <section className="callout" aria-label={M.githubSync.title}>
              <strong>{result.message}</strong>
              <p>
                {T.syncResultCounts(
                  result.counts.repositories,
                  result.counts.issues,
                  result.counts.pull_requests,
                  result.status
                )}
              </p>
              {result.warnings.length > 0 ? (
                <ul className="meta-list">
                  {result.warnings.map((warning) => (
                    <li key={warning}>{warning}</li>
                  ))}
                </ul>
              ) : null}
            </section>
          ) : null}
        </>
      ) : null}
    </section>
  );
}

function connectionDescription(status: GitHubConnectionStatusResponse): string {
  if (!status.has_connection_record) {
    return M.githubSync.noConnectionRecord;
  }
  if (status.display_name) {
    return status.display_name;
  }
  return M.githubSync.connectionRecordFound;
}
