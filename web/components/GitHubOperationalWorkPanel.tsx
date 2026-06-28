"use client";

import { useEffect, useState } from "react";

import { fetchGitHubOperationalWork } from "../lib/api";
import { M, T } from "../lib/messages";
import { useWorkspaceId } from "../lib/session";
import type {
  GitHubOperationalIssue,
  GitHubOperationalPullRequest,
  GitHubOperationalWorkResponse,
  GitHubOperationalWorkState
} from "../lib/types";
import { SourceLink } from "./SourceLink";
import { EmptyState } from "./EmptyState";
import { ErrorState } from "./ErrorState";
import { LoadingState } from "./LoadingState";
import { StatusCard } from "./StatusCard";

const stateOptions: { value: GitHubOperationalWorkState; label: string }[] = [
  { value: "open", label: M.githubWork.stateOpen },
  { value: "all", label: M.githubWork.stateAll },
  { value: "closed", label: M.githubWork.stateClosed },
  { value: "merged", label: M.githubWork.stateMerged }
];

type PanelStatus = "loading" | "ready" | "empty" | "error" | "missing";

type GitHubOperationalWorkPanelProps = {
  refreshSignal?: number;
};

type GitHubOperationalWorkPanelViewProps = {
  data: GitHubOperationalWorkResponse | null;
  error: string | null;
  onRetry?: () => void;
  onStateChange?: (state: GitHubOperationalWorkState) => void;
  selectedState: GitHubOperationalWorkState;
  status: PanelStatus;
};

export function GitHubOperationalWorkPanel({
  refreshSignal = 0
}: GitHubOperationalWorkPanelProps) {
  const workspaceId = useWorkspaceId();
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
      data={data}
      error={error}
      onRetry={() => setReloadKey((current) => current + 1)}
      onStateChange={setSelectedState}
      selectedState={selectedState}
      status={status}
    />
  );
}

export function GitHubOperationalWorkPanelView({
  data,
  error,
  onRetry,
  onStateChange,
  selectedState,
  status
}: GitHubOperationalWorkPanelViewProps) {
  return (
    <section className="panel operational-work" aria-labelledby="github-work-title">
      <div className="section-header">
        <div>
          <span className="eyebrow">{M.githubWork.eyebrow}</span>
          <h2 id="github-work-title">{M.githubWork.title}</h2>
        </div>
        <div className="segmented" aria-label={M.githubWork.stateLabel}>
          {stateOptions.map((option) => (
            <button
              aria-pressed={selectedState === option.value}
              className={
                selectedState === option.value ? "segment active" : "segment"
              }
              key={option.value}
              onClick={() => onStateChange?.(option.value)}
              type="button"
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      {status === "loading" ? <LoadingState label={M.githubWork.loading} /> : null}

      {status === "missing" ? (
        <EmptyState
          description={M.githubWork.noWorkspaceDescription}
          title={M.common.noWorkspaceTitle}
        />
      ) : null}

      {status === "error" ? (
        <>
          <ErrorState
            description={error ?? M.githubWork.unavailableDescription}
            title={M.githubWork.unavailableTitle}
          />
          <button className="button secondary" onClick={onRetry} type="button">
            {M.common.retry}
          </button>
        </>
      ) : null}

      {status === "empty" ? (
        <EmptyState
          description={M.githubWork.emptyDescription}
          title={M.githubWork.emptyTitle}
        />
      ) : null}

      {data && status !== "loading" && status !== "error" && status !== "missing" ? (
        <>
          <section className="grid" aria-label={M.githubWork.title}>
            <StatusCard
              description={T.workIssuesDescription(stateLabel(selectedState))}
              title={M.githubWork.issuesTitle}
              value={String(data.counts.issues)}
            />
            <StatusCard
              description={T.workPullRequestsDescription(stateLabel(selectedState))}
              title={M.githubWork.pullRequestsTitle}
              value={String(data.counts.pull_requests)}
            />
          </section>
          <div className="work-columns">
            <WorkSection
              emptyText={M.githubWork.noIssuesForFilter}
              items={data.issues}
              title={M.githubWork.issuesTitle}
              type="issue"
            />
            <WorkSection
              emptyText={M.githubWork.noPullRequestsForFilter}
              items={data.pull_requests}
              title={M.githubWork.pullRequestsTitle}
              type="pull_request"
            />
          </div>
        </>
      ) : null}
    </section>
  );
}

type WorkSectionProps =
  | {
      emptyText: string;
      items: GitHubOperationalIssue[];
      title: string;
      type: "issue";
    }
  | {
      emptyText: string;
      items: GitHubOperationalPullRequest[];
      title: string;
      type: "pull_request";
    };

function WorkSection({ emptyText, items, title, type }: WorkSectionProps) {
  return (
    <section className="work-section" aria-label={title}>
      <h3>{title}</h3>
      {items.length === 0 ? <p className="muted">{emptyText}</p> : null}
      <div className="work-list">
        {items.map((item) => (
          <article className="work-item" key={item.id}>
            <div className="work-item-main">
              <span className="badge">{type === "issue" ? M.githubWork.badgeIssue : M.githubWork.badgePr}</span>
              <h4>{item.title}</h4>
            </div>
            <dl className="work-meta">
              <div>
                <dt>{M.githubWork.metaRepository}</dt>
                <dd>{repositoryLabel(item)}</dd>
              </div>
              <div>
                <dt>{M.githubWork.metaState}</dt>
                <dd>{item.state ?? M.common.unknown}</dd>
              </div>
              <div>
                <dt>{M.githubWork.metaReference}</dt>
                <dd>{referenceLabel(item)}</dd>
              </div>
              {timestampLabel(item) ? (
                <div>
                  <dt>{M.githubWork.metaUpdated}</dt>
                  <dd>
                    <time dateTime={timestampLabel(item) ?? undefined}>
                      {formatSourceTimestamp(timestampLabel(item))}
                    </time>
                  </dd>
                </div>
              ) : null}
            </dl>
            {item.source_url ? (
              <SourceLink url={item.source_url}>{M.common.openSource}</SourceLink>
            ) : null}
          </article>
        ))}
      </div>
    </section>
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

export function formatSourceTimestamp(value: string | null): string {
  if (!value) {
    return M.githubWork.timestampUnknown;
  }
  return value.replace("T", " ").replace("+00:00", " UTC").replace("Z", " UTC");
}

function stateLabel(state: GitHubOperationalWorkState): string {
  const labels: Record<GitHubOperationalWorkState, string> = {
    open: M.githubWork.stateOpen,
    closed: M.githubWork.stateClosed,
    merged: M.githubWork.stateMerged,
    all: M.githubWork.stateAll
  };
  return labels[state];
}
