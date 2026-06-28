"use client";

import { useEffect, useState } from "react";

import {
  fetchGitHubConnectionStatus,
  runGitHubLocalSync
} from "../lib/api";
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
        setError(caught instanceof Error ? caught.message : "Request failed");
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
      setError(caught instanceof Error ? caught.message : "Request failed");
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
          <span className="eyebrow">GitHub</span>
          <h2 id="github-sync-title">Local sync controls</h2>
        </div>
        <span className="badge">No live provider</span>
      </div>

      {status === "loading" ? <LoadingState label="Loading GitHub connection state" /> : null}

      {status === "missing" ? (
        <EmptyState
          description="Your account has no workspace yet, so there is nothing to sync."
          title="No workspace available"
        />
      ) : null}

      {status === "error" && !connectionStatus ? (
        <>
          <ErrorState
            description={error ?? "The dashboard could not load GitHub sync state."}
            title="GitHub sync state unavailable"
          />
          <button className="button secondary" onClick={onRetry} type="button">
            Retry
          </button>
        </>
      ) : null}

      {connectionStatus ? (
        <>
          <section className="grid" aria-label="GitHub local sync status">
            <StatusCard
              description={connectionDescription(connectionStatus)}
              title="Connection record"
              value={connectionStatus.has_connection_record ? connectionStatus.status : "Missing"}
            />
            <StatusCard
              description="Live OAuth and provider execution are not enabled from this UI."
              title="Execution mode"
              value="Local only"
            />
            <StatusCard
              description={`Repository read source: ${connectionStatus.repository_read_source}.`}
              title="Repository source"
              value={connectionStatus.repository_read_available ? "Available" : "Unavailable"}
            />
          </section>

          {!connectionStatus.has_connection_record ? (
            <EmptyState
              description="Live OAuth is not enabled yet. This control can normalize local GitHub data after a backend GitHub connection record exists."
              title="GitHub connection record required"
            />
          ) : null}

          {connectionStatus.has_connection_record && connectionStatus.status !== "connected" ? (
            <EmptyState
              description={`The backend record is ${connectionStatus.status}. Local normalization requires a connected GitHub record.`}
              title="GitHub connection record is not ready"
            />
          ) : null}

          {connectionStatus.warnings.length > 0 ? (
            <ul className="meta-list" aria-label="GitHub sync warnings">
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
              {isSyncing ? "Running local sync" : "Run local GitHub sync"}
            </button>
            <button className="button secondary" onClick={onRetry} type="button">
              Refresh status
            </button>
          </div>

          {status === "error" ? (
            <ErrorState
              description={error ?? "The local GitHub sync request failed."}
              title="Local GitHub sync failed"
            />
          ) : null}

          {result ? (
            <section className="callout" aria-label="GitHub local sync result">
              <strong>{result.message}</strong>
              <p>
                {result.counts.repositories} repositories, {result.counts.issues} issues/tasks, and{" "}
                {result.counts.pull_requests} pull requests normalized. Status: {result.status}.
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
    return "No backend GitHub connection record exists for this workspace.";
  }
  if (status.display_name) {
    return status.display_name;
  }
  return "Backend GitHub connection record found.";
}
