"use client";

import { useEffect, useState } from "react";

import {
  fetchGitHubConnectionStatus,
  syncSelectedRepositoryIssues,
  syncSelectedRepositoryPullRequests
} from "../lib/api";
import { useWorkspaceId } from "../lib/session";
import type {
  GitHubConnectionStatusResponse,
  GitHubSelectedIssueSyncResponse,
  GitHubSelectedPullRequestSyncResponse
} from "../lib/types";
import { EmptyState } from "./EmptyState";
import { ErrorState } from "./ErrorState";
import { LoadingState } from "./LoadingState";

export const DEFAULT_SELECTED_REPOSITORY = "qtwin-io/founderos-smoke";

type ConnectionLoadStatus = "loading" | "ready" | "error" | "missing";

export type SelectedSyncAction = "issues" | "pull_requests" | "both";

export type SelectedSyncErrorKind = "allowlist" | "permission" | "generic";

export type SelectedSyncError = {
  kind: SelectedSyncErrorKind;
  message: string;
};

type SelectedRepositorySyncControlsProps = {
  onSyncComplete?: () => void;
};

type SelectedRepositorySyncControlsViewProps = {
  status: ConnectionLoadStatus;
  connectionStatus: GitHubConnectionStatusResponse | null;
  connectionError: string | null;
  repositoryInput: string;
  onRepositoryInputChange?: (value: string) => void;
  repositoryError: string | null;
  pendingAction: SelectedSyncAction | null;
  syncError: SelectedSyncError | null;
  issuesResult: GitHubSelectedIssueSyncResponse | null;
  pullRequestsResult: GitHubSelectedPullRequestSyncResponse | null;
  onRunIssues?: () => void;
  onRunPullRequests?: () => void;
  onRunBoth?: () => void;
  onRetryConnection?: () => void;
};

export function isValidRepositoryFullName(value: string): boolean {
  const trimmed = value.trim();
  if (!trimmed || /\s/.test(trimmed)) {
    return false;
  }
  const parts = trimmed.split("/");
  if (parts.length !== 2) {
    return false;
  }
  return parts[0].length > 0 && parts[1].length > 0;
}

export function repositoryValidationMessage(value: string): string {
  if (!value.trim()) {
    return "Enter a repository full name as owner/repo.";
  }
  return "Repository must be in owner/repo format with no spaces.";
}

export function classifySelectedSyncError(message: string): SelectedSyncError {
  const normalized = message.toLowerCase();
  if (
    normalized.includes("not allowed for selected") ||
    normalized.includes("allowed repositories are not configured")
  ) {
    return {
      kind: "allowlist",
      message: "Repository is not allowlisted for selected sync."
    };
  }
  if (normalized.includes("insufficient workspace role")) {
    return {
      kind: "permission",
      message:
        "Your workspace role cannot run selected repository sync. An admin role is required."
    };
  }
  return {
    kind: "generic",
    message: message || "The selected repository sync request failed."
  };
}

export function SelectedRepositorySyncControls({
  onSyncComplete
}: SelectedRepositorySyncControlsProps) {
  const workspaceId = useWorkspaceId();
  const [connectionStatus, setConnectionStatus] =
    useState<GitHubConnectionStatusResponse | null>(null);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const [status, setStatus] = useState<ConnectionLoadStatus>("loading");
  const [reloadKey, setReloadKey] = useState(0);

  const [repositoryInput, setRepositoryInput] = useState(
    DEFAULT_SELECTED_REPOSITORY
  );
  const [repositoryError, setRepositoryError] = useState<string | null>(null);
  const [pendingAction, setPendingAction] = useState<SelectedSyncAction | null>(
    null
  );
  const [syncError, setSyncError] = useState<SelectedSyncError | null>(null);
  const [issuesResult, setIssuesResult] =
    useState<GitHubSelectedIssueSyncResponse | null>(null);
  const [pullRequestsResult, setPullRequestsResult] =
    useState<GitHubSelectedPullRequestSyncResponse | null>(null);

  useEffect(() => {
    if (!workspaceId) {
      setConnectionStatus(null);
      setConnectionError(null);
      setStatus("missing");
      return;
    }

    let cancelled = false;
    setStatus("loading");
    setConnectionError(null);
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
        setConnectionError(
          caught instanceof Error ? caught.message : "Request failed"
        );
        setStatus("error");
      });

    return () => {
      cancelled = true;
    };
  }, [workspaceId, reloadKey]);

  async function runSelectedSync(action: SelectedSyncAction): Promise<void> {
    if (!workspaceId) {
      setStatus("missing");
      return;
    }
    const repository = repositoryInput.trim();
    if (!isValidRepositoryFullName(repository)) {
      setRepositoryError(repositoryValidationMessage(repository));
      return;
    }
    setRepositoryError(null);

    const connectionId = connectionStatus?.connection_id;
    if (!connectionStatus?.has_connection_record || !connectionId) {
      return;
    }

    setSyncError(null);
    if (action === "issues" || action === "both") {
      setIssuesResult(null);
    }
    if (action === "pull_requests" || action === "both") {
      setPullRequestsResult(null);
    }
    setPendingAction(action);

    try {
      if (action === "issues" || action === "both") {
        const issues = await syncSelectedRepositoryIssues(workspaceId, {
          connection_id: connectionId,
          repositories: [repository]
        });
        setIssuesResult(issues);
        onSyncComplete?.();
      }
      if (action === "pull_requests" || action === "both") {
        const pullRequests = await syncSelectedRepositoryPullRequests(
          workspaceId,
          {
            connection_id: connectionId,
            repositories: [repository]
          }
        );
        setPullRequestsResult(pullRequests);
        onSyncComplete?.();
      }
    } catch (caught: unknown) {
      const message =
        caught instanceof Error ? caught.message : "Request failed";
      setSyncError(classifySelectedSyncError(message));
    } finally {
      setPendingAction(null);
    }
  }

  return (
    <SelectedRepositorySyncControlsView
      connectionError={connectionError}
      connectionStatus={connectionStatus}
      issuesResult={issuesResult}
      onRepositoryInputChange={(value) => {
        setRepositoryError(null);
        setRepositoryInput(value);
      }}
      onRetryConnection={() => setReloadKey((current) => current + 1)}
      onRunBoth={() => void runSelectedSync("both")}
      onRunIssues={() => void runSelectedSync("issues")}
      onRunPullRequests={() => void runSelectedSync("pull_requests")}
      pendingAction={pendingAction}
      pullRequestsResult={pullRequestsResult}
      repositoryError={repositoryError}
      repositoryInput={repositoryInput}
      status={status}
      syncError={syncError}
    />
  );
}

export function SelectedRepositorySyncControlsView({
  status,
  connectionStatus,
  connectionError,
  repositoryInput,
  onRepositoryInputChange,
  repositoryError,
  pendingAction,
  syncError,
  issuesResult,
  pullRequestsResult,
  onRunIssues,
  onRunPullRequests,
  onRunBoth,
  onRetryConnection
}: SelectedRepositorySyncControlsViewProps) {
  const hasConnection = Boolean(
    connectionStatus?.has_connection_record && connectionStatus.connection_id
  );
  const isBusy = pendingAction !== null;
  const canSync = hasConnection && !isBusy;

  return (
    <section
      className="panel selected-repository-sync"
      aria-labelledby="selected-repository-sync-title"
    >
      <div className="section-header">
        <div>
          <span className="eyebrow">GitHub</span>
          <h2 id="selected-repository-sync-title">Selected repository sync</h2>
        </div>
        <span className="badge">Read-only</span>
      </div>

      <p className="muted">
        Read-only selected repository sync. No GitHub writes are performed.
        Issues and pull requests are fetched from selected allowlisted
        repositories. This does not create, close, merge, or comment on GitHub
        items.
      </p>

      {status === "loading" ? (
        <LoadingState label="Loading GitHub connection state" />
      ) : null}

      {status === "missing" ? (
        <EmptyState
          description="Your account has no workspace yet, so there is nothing to sync."
          title="No workspace available"
        />
      ) : null}

      {status === "error" ? (
        <>
          <ErrorState
            description={
              connectionError ??
              "The dashboard could not load GitHub connection state."
            }
            title="Selected repository sync unavailable"
          />
          <button
            className="button secondary"
            onClick={onRetryConnection}
            type="button"
          >
            Retry
          </button>
        </>
      ) : null}

      {status === "ready" && !hasConnection ? (
        <EmptyState
          description="A GitHub connection must be configured for this workspace before selected repository sync. Configure the GitHub connection, then retry."
          title="GitHub connection required"
        />
      ) : null}

      {status === "ready" && hasConnection ? (
        <>
          <div className="field">
            <label htmlFor="selected-repository-input">
              Repository (owner/repo)
            </label>
            <input
              autoComplete="off"
              id="selected-repository-input"
              onChange={(event) =>
                onRepositoryInputChange?.(event.target.value)
              }
              placeholder="owner/repo"
              spellCheck={false}
              type="text"
              value={repositoryInput}
            />
            <p className="muted">
              Selected repositories must be allowed by backend config. This UI
              syncs one explicit repository at a time and never syncs all
              organization repositories.
            </p>
            {repositoryError ? (
              <p className="error-text" role="alert">
                {repositoryError}
              </p>
            ) : null}
          </div>

          <div className="actions-row">
            <button
              className="button"
              disabled={!canSync}
              onClick={onRunIssues}
              type="button"
            >
              {pendingAction === "issues" ? "Syncing issues" : "Run issue sync"}
            </button>
            <button
              className="button"
              disabled={!canSync}
              onClick={onRunPullRequests}
              type="button"
            >
              {pendingAction === "pull_requests"
                ? "Syncing pull requests"
                : "Run PR sync"}
            </button>
            <button
              className="button secondary"
              disabled={!canSync}
              onClick={onRunBoth}
              type="button"
            >
              {pendingAction === "both"
                ? "Syncing issues and pull requests"
                : "Run issue + PR sync"}
            </button>
          </div>

          {syncError ? (
            <ErrorState
              description={syncError.message}
              title={selectedSyncErrorTitle(syncError.kind)}
            />
          ) : null}

          {issuesResult ? (
            <IssueSyncSummary result={issuesResult} />
          ) : null}

          {pullRequestsResult ? (
            <PullRequestSyncSummary result={pullRequestsResult} />
          ) : null}
        </>
      ) : null}
    </section>
  );
}

function selectedSyncErrorTitle(kind: SelectedSyncErrorKind): string {
  if (kind === "allowlist") {
    return "Repository not allowlisted";
  }
  if (kind === "permission") {
    return "Insufficient workspace role";
  }
  return "Selected repository sync failed";
}

function IssueSyncSummary({
  result
}: {
  result: GitHubSelectedIssueSyncResponse;
}) {
  const { totals } = result;
  return (
    <section className="callout" aria-label="Selected issue sync summary">
      <strong>Issue sync summary</strong>
      {totals.issues === 0 ? (
        <p>No issue records were synced for the selected repository.</p>
      ) : (
        <p>
          {totals.repositories} repositories synced, {totals.issues} issues (
          {totals.open_issues} open / {totals.closed_issues} closed).
        </p>
      )}
      {totals.skipped_pull_requests > 0 ? (
        <p>
          {totals.skipped_pull_requests} PR-shaped issue records skipped.
        </p>
      ) : null}
      <RepositorySummaryList
        items={result.repositories.map((repository) => ({
          full_name: repository.full_name,
          detail: `${repository.synced_issues} issues (${repository.open_issues} open / ${repository.closed_issues} closed)`
        }))}
      />
      <p className="success-text">No GitHub writes were performed.</p>
      <SyncWarnings warnings={result.warnings} />
    </section>
  );
}

function PullRequestSyncSummary({
  result
}: {
  result: GitHubSelectedPullRequestSyncResponse;
}) {
  const { totals } = result;
  return (
    <section className="callout" aria-label="Selected pull request sync summary">
      <strong>Pull request sync summary</strong>
      {totals.pull_requests === 0 ? (
        <p>No pull request records were synced for the selected repository.</p>
      ) : (
        <p>
          {totals.repositories} repositories synced, {totals.pull_requests} pull
          requests ({totals.open_pull_requests} open /{" "}
          {totals.closed_pull_requests} closed / {totals.merged_pull_requests}{" "}
          merged).
        </p>
      )}
      <RepositorySummaryList
        items={result.repositories.map((repository) => ({
          full_name: repository.full_name,
          detail: `${repository.synced_pull_requests} PRs (${repository.open_pull_requests} open / ${repository.closed_pull_requests} closed / ${repository.merged_pull_requests} merged)`
        }))}
      />
      <p className="success-text">No GitHub writes were performed.</p>
      <SyncWarnings warnings={result.warnings} />
    </section>
  );
}

function RepositorySummaryList({
  items
}: {
  items: { full_name: string; detail: string }[];
}) {
  if (items.length === 0) {
    return null;
  }
  return (
    <ul className="meta-list">
      {items.map((item) => (
        <li key={item.full_name}>
          <strong>{item.full_name}</strong>: {item.detail}
        </li>
      ))}
    </ul>
  );
}

function SyncWarnings({ warnings }: { warnings: string[] }) {
  if (warnings.length === 0) {
    return null;
  }
  return (
    <ul className="meta-list" aria-label="Selected sync warnings">
      {warnings.map((warning) => (
        <li key={warning}>{warning}</li>
      ))}
    </ul>
  );
}
