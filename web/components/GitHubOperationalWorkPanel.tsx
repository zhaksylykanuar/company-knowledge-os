"use client";

import { useEffect, useState } from "react";

import { fetchGitHubOperationalWork } from "../lib/api";
import { M } from "../lib/messages";
import { useWorkspaceId } from "../lib/session";
import type {
  GitHubOperationalIssue,
  GitHubOperationalPullRequest,
  GitHubOperationalWorkResponse,
  GitHubOperationalWorkState
} from "../lib/types";
import { EmptyState } from "./EmptyState";
import { ErrorState } from "./ErrorState";
import { LoadingState } from "./LoadingState";
import { SourceLink } from "./SourceLink";

const VISIBLE_WORK_ITEMS = 8;

const stateOptions: { value: GitHubOperationalWorkState; label: string }[] = [
  { value: "open", label: M.githubWork.stateOpen },
  { value: "all", label: M.githubWork.stateAll },
  { value: "closed", label: M.githubWork.stateClosed },
  { value: "merged", label: M.githubWork.stateMerged }
];

type PanelStatus = "loading" | "ready" | "empty" | "error" | "missing";
type WorkKind = "issues" | "pull_requests";

type GitHubOperationalWorkPanelProps = {
  refreshSignal?: number;
  repositoryFullName?: string | null;
};

type GitHubOperationalWorkPanelViewProps = {
  activeKind?: WorkKind;
  data: GitHubOperationalWorkResponse | null;
  error: string | null;
  onKindChange?: (kind: WorkKind) => void;
  onRetry?: () => void;
  onStateChange?: (state: GitHubOperationalWorkState) => void;
  repositoryFullName?: string | null;
  selectedState: GitHubOperationalWorkState;
  status: PanelStatus;
};

export function GitHubOperationalWorkPanel({
  refreshSignal = 0,
  repositoryFullName = null
}: GitHubOperationalWorkPanelProps) {
  const workspaceId = useWorkspaceId();
  const [activeKind, setActiveKind] = useState<WorkKind>("issues");
  const [data, setData] = useState<GitHubOperationalWorkResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [selectedState, setSelectedState] =
    useState<GitHubOperationalWorkState>("open");
  const [status, setStatus] = useState<PanelStatus>("loading");

  useEffect(() => {
    if (!workspaceId) {
      setStatus("missing");
      setData(null);
      setError(null);
      return;
    }

    let cancelled = false;
    setStatus("loading");
    setError(null);
    fetchGitHubOperationalWork(workspaceId, {
      limit: 100,
      state: selectedState
    })
      .then((payload) => {
        if (cancelled) {
          return;
        }
        setData(payload);
        setStatus(
          payload.issues.length === 0 && payload.pull_requests.length === 0
            ? "empty"
            : "ready"
        );
      })
      .catch((caught: unknown) => {
        if (cancelled) {
          return;
        }
        setData(null);
        setError(caught instanceof Error ? caught.message : M.common.requestFailed);
        setStatus("error");
      });

    return () => {
      cancelled = true;
    };
  }, [workspaceId, refreshSignal, reloadKey, selectedState]);

  return (
    <GitHubOperationalWorkPanelView
      activeKind={activeKind}
      data={data}
      error={error}
      onKindChange={setActiveKind}
      onRetry={() => setReloadKey((current) => current + 1)}
      onStateChange={setSelectedState}
      repositoryFullName={repositoryFullName}
      selectedState={selectedState}
      status={status}
    />
  );
}

export function GitHubOperationalWorkPanelView({
  activeKind = "issues",
  data,
  error,
  onKindChange,
  onRetry,
  onStateChange,
  repositoryFullName = null,
  selectedState,
  status
}: GitHubOperationalWorkPanelViewProps) {
  const issues = data
    ? filterRepositoryItems(data.issues, repositoryFullName)
    : [];
  const pullRequests = data
    ? filterRepositoryItems(data.pull_requests, repositoryFullName)
    : [];
  const activeItems = activeKind === "issues" ? issues : pullRequests;
  const activeTitle =
    activeKind === "issues"
      ? M.githubWork.issuesTitle
      : M.githubWork.pullRequestsTitle;
  const activeEmptyText =
    activeKind === "issues"
      ? M.githubWork.noIssuesForFilter
      : M.githubWork.noPullRequestsForFilter;

  return (
    <section
      aria-busy={status === "loading"}
      aria-labelledby="github-work-title"
      className="panel github-work"
    >
      <div className="github-work__header">
        <div>
          <span className="eyebrow">{M.githubWork.eyebrow}</span>
          <h2 id="github-work-title">{M.githubWork.title}</h2>
          <p>
            {repositoryFullName
              ? `${M.githubWork.repositoryPrefix} ${repositoryFullName}`
              : M.githubWork.description}
          </p>
        </div>
        <label className="github-work__state-filter">
          <span>{M.githubWork.stateLabel}</span>
          <select
            onChange={(event) =>
              onStateChange?.(event.target.value as GitHubOperationalWorkState)
            }
            value={selectedState}
          >
            {stateOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      {status === "loading" ? (
        <div aria-live="polite" className="github-work__state" role="status">
          <LoadingState label={M.githubWork.loading} />
        </div>
      ) : null}

      {status === "missing" ? (
        <div className="github-work__state">
          <EmptyState
            description={M.githubWork.noWorkspaceDescription}
            title={M.common.noWorkspaceTitle}
          />
        </div>
      ) : null}

      {status === "error" ? (
        <div className="github-work__state">
          <ErrorState
            description={M.githubWork.unavailableDescription}
            title={M.githubWork.unavailableTitle}
          />
          <button className="button secondary" onClick={onRetry} type="button">
            {M.common.retry}
          </button>
          {error ? (
            <details className="github-work__error-details">
              <summary>{M.githubWork.errorDetails}</summary>
              <p>{error}</p>
            </details>
          ) : null}
        </div>
      ) : null}

      {status === "empty" && !data ? (
        <EmptyState
          description={M.githubWork.emptyDescription}
          title={M.githubWork.emptyTitle}
        />
      ) : null}

      {data && status !== "loading" && status !== "error" && status !== "missing" ? (
        <div className="github-work__results" id="github-work-results">
          <div
            aria-label={M.githubWork.kindLabel}
            className="github-work__tabs"
            role="tablist"
          >
            <button
              aria-controls="github-work-tab-panel"
              aria-selected={activeKind === "issues"}
              className={activeKind === "issues" ? "active" : ""}
              onClick={() => onKindChange?.("issues")}
              role="tab"
              type="button"
            >
              <span>{M.githubWork.issuesTitle}</span>
              <strong>{issues.length}</strong>
            </button>
            <button
              aria-controls="github-work-tab-panel"
              aria-selected={activeKind === "pull_requests"}
              className={activeKind === "pull_requests" ? "active" : ""}
              onClick={() => onKindChange?.("pull_requests")}
              role="tab"
              type="button"
            >
              <span>{M.githubWork.pullRequestsTitle}</span>
              <strong>{pullRequests.length}</strong>
            </button>
          </div>

          <div
            aria-label={activeTitle}
            className="github-work__tab-panel"
            data-scope="loaded-sample"
            id="github-work-tab-panel"
            role="tabpanel"
          >
            {activeItems.length === 0 ? (
              <div className="github-work__empty">
                <span aria-hidden="true">✓</span>
                <div>
                  <strong>{M.githubWork.nothingFoundTitle}</strong>
                  <p>{activeEmptyText}</p>
                </div>
              </div>
            ) : (
              <WorkList items={activeItems} type={activeKind} />
            )}
          </div>

          {data.warnings.length > 0 ? (
            <details className="github-work__warnings">
              <summary>
                {M.common.warnings} ({data.warnings.length})
              </summary>
              <ul>
                {data.warnings.map((warning, index) => (
                  <li key={`${index}-${warning}`}>{warning}</li>
                ))}
              </ul>
            </details>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

type WorkListProps = {
  items: (GitHubOperationalIssue | GitHubOperationalPullRequest)[];
  type: WorkKind;
};

function WorkList({ items, type }: WorkListProps) {
  const visibleItems = items.slice(0, VISIBLE_WORK_ITEMS);
  const remainingItems = items.slice(VISIBLE_WORK_ITEMS);
  return (
    <>
      <ul className="github-work__list">
        {visibleItems.map((item) => (
          <WorkListItem item={item} key={item.id} type={type} />
        ))}
      </ul>
      {remainingItems.length > 0 ? (
        <details className="github-work__more">
          <summary>
            {M.githubWork.showMore} · {remainingItems.length}
          </summary>
          <ul className="github-work__list">
            {remainingItems.map((item) => (
              <WorkListItem item={item} key={item.id} type={type} />
            ))}
          </ul>
        </details>
      ) : null}
    </>
  );
}

function WorkListItem({
  item,
  type
}: {
  item: GitHubOperationalIssue | GitHubOperationalPullRequest;
  type: WorkKind;
}) {
  const timestamp = timestampLabel(item);
  return (
    <li className="github-work__item">
      <div className="github-work__item-icon" aria-hidden="true">
        {type === "issues" ? "○" : "↗"}
      </div>
      <div className="github-work__item-copy">
        <div className="github-work__item-heading">
          <h3>{item.title}</h3>
          <span className="github-work__item-state">
            {workItemStateLabel(item.state)}
          </span>
        </div>
        <p>
          <span>{referenceLabel(item)}</span>
          <span>{repositoryLabel(item)}</span>
          {timestamp ? (
            <time dateTime={timestamp}>{formatSourceTimestamp(timestamp)}</time>
          ) : null}
        </p>
      </div>
      {item.source_url ? (
        <SourceLink className="github-work__item-link" url={item.source_url}>
          {M.githubWork.openInGitHub}
        </SourceLink>
      ) : null}
    </li>
  );
}

function filterRepositoryItems<
  T extends GitHubOperationalIssue | GitHubOperationalPullRequest
>(items: T[], repositoryFullName: string | null): T[] {
  if (!repositoryFullName) {
    return items;
  }
  return items.filter(
    (item) =>
      item.repository_full_name?.toLowerCase() ===
        repositoryFullName.toLowerCase() ||
      item.repository_external_id?.toLowerCase() ===
        repositoryFullName.toLowerCase()
  );
}

function repositoryLabel(
  item: GitHubOperationalIssue | GitHubOperationalPullRequest
): string {
  return (
    item.repository_full_name ||
    item.repository_external_id ||
    M.githubWork.repositoryUnavailable
  );
}

function referenceLabel(
  item: GitHubOperationalIssue | GitHubOperationalPullRequest
): string {
  if (typeof item.number === "number") {
    return `#${item.number}`;
  }
  return item.external_id || M.githubWork.noExternalId;
}

function timestampLabel(
  item: GitHubOperationalIssue | GitHubOperationalPullRequest
): string | null {
  if ("source_updated_at" in item) {
    return item.source_updated_at;
  }
  return item.updated_at_source || item.merged_at_source || item.created_at_source;
}

function workItemStateLabel(value: string | null): string {
  if (value === "open") {
    return M.githubWork.stateOpen;
  }
  if (value === "closed") {
    return M.githubWork.stateClosed;
  }
  if (value === "merged") {
    return M.githubWork.stateMerged;
  }
  return M.common.unknown;
}

export function formatSourceTimestamp(value: string | null): string {
  if (!value) {
    return M.githubWork.timestampUnknown;
  }
  return value.replace("T", " ").replace("+00:00", " UTC").replace("Z", " UTC");
}
