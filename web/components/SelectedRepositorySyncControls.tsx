"use client";

import { useEffect, useState } from "react";

import {
  fetchGitHubConnectionStatus,
  syncSelectedRepositoryIssues,
  syncSelectedRepositoryPullRequests
} from "../lib/api";
import { M, T } from "../lib/messages";
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
    return M.selectedSync.validationEmpty;
  }
  return M.selectedSync.validationFormat;
}

export function classifySelectedSyncError(message: string): SelectedSyncError {
  const normalized = message.toLowerCase();
  if (
    normalized.includes("not allowed for selected") ||
    normalized.includes("allowed repositories are not configured")
  ) {
    return {
      kind: "allowlist",
      message: M.selectedSync.errorAllowlist
    };
  }
  if (normalized.includes("insufficient workspace role")) {
    return {
      kind: "permission",
      message: M.selectedSync.errorPermission
    };
  }
  return {
    kind: "generic",
    message: message || M.selectedSync.errorGeneric
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
          caught instanceof Error ? caught.message : M.common.requestFailed
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
        caught instanceof Error ? caught.message : M.common.requestFailed;
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
          <span className="eyebrow">{M.selectedSync.eyebrow}</span>
          <h2 id="selected-repository-sync-title">{M.selectedSync.title}</h2>
        </div>
        <span className="badge">{M.selectedSync.badgeReadOnly}</span>
      </div>

      <p className="muted">{M.selectedSync.intro}</p>

      {status === "loading" ? (
        <LoadingState label={M.selectedSync.loading} />
      ) : null}

      {status === "missing" ? (
        <EmptyState
          description={M.selectedSync.noWorkspaceDescription}
          title={M.common.noWorkspaceTitle}
        />
      ) : null}

      {status === "error" ? (
        <>
          <ErrorState
            description={connectionError ?? M.selectedSync.unavailableDescription}
            title={M.selectedSync.unavailableTitle}
          />
          <button
            className="button secondary"
            onClick={onRetryConnection}
            type="button"
          >
            {M.common.retry}
          </button>
        </>
      ) : null}

      {status === "ready" && !hasConnection ? (
        <EmptyState
          description={M.selectedSync.connectionRequiredDescription}
          title={M.selectedSync.connectionRequiredTitle}
        />
      ) : null}

      {status === "ready" && hasConnection ? (
        <>
          <div className="field">
            <label htmlFor="selected-repository-input">
              {M.selectedSync.repoLabel}
            </label>
            <input
              autoComplete="off"
              id="selected-repository-input"
              onChange={(event) =>
                onRepositoryInputChange?.(event.target.value)
              }
              placeholder={M.selectedSync.repoPlaceholder}
              spellCheck={false}
              type="text"
              value={repositoryInput}
            />
            <p className="muted">{M.selectedSync.repoNote}</p>
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
              {pendingAction === "issues" ? M.selectedSync.syncingIssues : M.selectedSync.runIssues}
            </button>
            <button
              className="button"
              disabled={!canSync}
              onClick={onRunPullRequests}
              type="button"
            >
              {pendingAction === "pull_requests"
                ? M.selectedSync.syncingPr
                : M.selectedSync.runPr}
            </button>
            <button
              className="button secondary"
              disabled={!canSync}
              onClick={onRunBoth}
              type="button"
            >
              {pendingAction === "both"
                ? M.selectedSync.syncingBoth
                : M.selectedSync.runBoth}
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
    return M.selectedSync.errorTitleAllowlist;
  }
  if (kind === "permission") {
    return M.selectedSync.errorTitlePermission;
  }
  return M.selectedSync.errorTitleGeneric;
}

function IssueSyncSummary({
  result
}: {
  result: GitHubSelectedIssueSyncResponse;
}) {
  const { totals } = result;
  return (
    <section className="callout" aria-label={M.selectedSync.issueSummaryTitle}>
      <strong>{M.selectedSync.issueSummaryTitle}</strong>
      {totals.issues === 0 ? (
        <p>{M.selectedSync.noIssuesSynced}</p>
      ) : (
        <p>
          {T.selectedIssueSummary(
            totals.repositories,
            totals.issues,
            totals.open_issues,
            totals.closed_issues
          )}
        </p>
      )}
      {totals.skipped_pull_requests > 0 ? (
        <p>{T.skippedPrs(totals.skipped_pull_requests)}</p>
      ) : null}
      <RepositorySummaryList
        items={result.repositories.map((repository) => ({
          full_name: repository.full_name,
          detail: T.selectedIssueRepoDetail(
            repository.synced_issues,
            repository.open_issues,
            repository.closed_issues
          )
        }))}
      />
      <p className="success-text">{M.selectedSync.noWrites}</p>
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
    <section className="callout" aria-label={M.selectedSync.prSummaryTitle}>
      <strong>{M.selectedSync.prSummaryTitle}</strong>
      {totals.pull_requests === 0 ? (
        <p>{M.selectedSync.noPrsSynced}</p>
      ) : (
        <p>
          {T.selectedPrSummary(
            totals.repositories,
            totals.pull_requests,
            totals.open_pull_requests,
            totals.closed_pull_requests,
            totals.merged_pull_requests
          )}
        </p>
      )}
      <RepositorySummaryList
        items={result.repositories.map((repository) => ({
          full_name: repository.full_name,
          detail: T.selectedPrRepoDetail(
            repository.synced_pull_requests,
            repository.open_pull_requests,
            repository.closed_pull_requests,
            repository.merged_pull_requests
          )
        }))}
      />
      <p className="success-text">{M.selectedSync.noWrites}</p>
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
    <ul className="meta-list" aria-label={M.common.warnings}>
      {warnings.map((warning) => (
        <li key={warning}>{warning}</li>
      ))}
    </ul>
  );
}
