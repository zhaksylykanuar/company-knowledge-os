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

const visibleWorkItems = 4;

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
    <section
      aria-busy={status === "loading"}
      aria-labelledby="github-work-title"
      className="panel operational-work github-work-pulse"
    >
      <div className="section-header github-work-pulse__header">
        <div>
          <span className="eyebrow">{M.githubWork.eyebrow}</span>
          <h2 id="github-work-title">{M.githubWork.title}</h2>
        </div>
        <div
          aria-label={M.githubWork.stateLabel}
          className="segmented github-work-pulse__filters"
          role="group"
        >
          {stateOptions.map((option) => (
            <button
              aria-pressed={selectedState === option.value}
              className={
                selectedState === option.value
                  ? "segment active github-work-pulse__filter"
                  : "segment github-work-pulse__filter"
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

      {status === "loading" ? (
        <div
          aria-live="polite"
          className="github-work-pulse__state"
          role="status"
        >
          <LoadingState label={M.githubWork.loading} />
        </div>
      ) : null}

      {status === "missing" ? (
        <div className="github-work-pulse__state">
          <EmptyState
            description={M.githubWork.noWorkspaceDescription}
            title={M.common.noWorkspaceTitle}
          />
        </div>
      ) : null}

      {status === "error" ? (
        <div className="github-work-pulse__state">
          <ErrorState
            description={M.githubWork.unavailableDescription}
            title={M.githubWork.unavailableTitle}
          />
          <button className="button secondary" onClick={onRetry} type="button">
            {M.common.retry}
          </button>
          {error ? (
            <details className="github-work-pulse__error-details">
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
        <div className="github-work-pulse__results" id="github-work-results">
          <p className="muted github-work-pulse__sample-note">
            {M.githubWork.sampleNote}
          </p>
          <section
            aria-label={M.githubWork.title}
            aria-live="polite"
            className="github-work-pulse__snapshot"
            data-scope="loaded-sample"
            role="status"
          >
            <PulseMetric
              count={data.counts.issues}
              description={T.workIssuesDescription(stateLabel(selectedState))}
              kind="issue"
              sampleSize={data.counts.issues + data.counts.pull_requests}
              title={M.githubWork.issuesTitle}
            />
            <PulseMetric
              count={data.counts.pull_requests}
              description={T.workPullRequestsDescription(stateLabel(selectedState))}
              kind="pull-request"
              sampleSize={data.counts.issues + data.counts.pull_requests}
              title={M.githubWork.pullRequestsTitle}
            />
          </section>
          {data.warnings.length > 0 ? (
            <details className="github-work-pulse__warnings">
              <summary>
                {M.common.warnings} ({data.warnings.length})
              </summary>
              <ul className="github-work-pulse__warning-list">
                {data.warnings.map((warning, index) => (
                  <li key={`${index}-${warning}`}>{warning}</li>
                ))}
              </ul>
            </details>
          ) : null}
          <div className="work-columns github-work-pulse__columns">
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
        </div>
      ) : null}
    </section>
  );
}

type PulseMetricProps = {
  count: number;
  description: string;
  kind: "issue" | "pull-request";
  sampleSize: number;
  title: string;
};

function PulseMetric({
  count,
  description,
  kind,
  sampleSize,
  title
}: PulseMetricProps) {
  const composition = T.githubWorkMetricComposition(count, sampleSize);
  const metricDescription = `${description} ${composition}`;
  return (
    <article
      aria-label={metricDescription}
      className={`github-work-pulse__metric github-work-pulse__metric--${kind}`}
    >
      <span className="github-work-pulse__metric-title">{title}</span>
      <strong className="github-work-pulse__metric-value">{count}</strong>
      <meter
        aria-label={metricDescription}
        className="github-work-pulse__meter"
        max={Math.max(sampleSize, 1)}
        value={count}
      >
        {count}
      </meter>
      <span className="github-work-pulse__metric-caption">{composition}</span>
    </article>
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
  const firstItems = items.slice(0, visibleWorkItems);
  const remainingItems = items.slice(visibleWorkItems);
  const typeClass = type === "issue" ? "issue" : "pull-request";

  return (
    <section
      aria-label={title}
      className={`work-section github-work-pulse__section github-work-pulse__section--${typeClass}`}
    >
      <div className="github-work-pulse__section-header">
        <h3>{title}</h3>
        <span className="badge github-work-pulse__section-count">{items.length}</span>
      </div>
      {items.length === 0 ? (
        <p className="muted github-work-pulse__empty" role="status">
          {emptyText}
        </p>
      ) : (
        <>
          <WorkList items={firstItems} type={type} />
          {remainingItems.length > 0 ? (
            <details className="github-work-pulse__more">
              <summary>
                {title} +{remainingItems.length}
              </summary>
              <WorkList items={remainingItems} type={type} />
            </details>
          ) : null}
        </>
      )}
    </section>
  );
}

type WorkListProps = {
  items: (GitHubOperationalIssue | GitHubOperationalPullRequest)[];
  type: "issue" | "pull_request";
};

function WorkList({ items, type }: WorkListProps) {
  return (
    <ul className="work-list github-work-pulse__list">
      {items.map((item) => (
        <li className="github-work-pulse__list-item" key={item.id}>
          <article className="work-item github-work-pulse__item">
            <div className="work-item-main github-work-pulse__item-main">
              <div className="github-work-pulse__item-badges">
                <span className="badge">
                  {type === "issue"
                    ? M.githubWork.badgeIssue
                    : M.githubWork.badgePr}{" "}
                  {referenceLabel(item)}
                </span>
                <span
                  aria-label={`${M.githubWork.metaState}: ${workItemStateLabel(item.state)}`}
                  className="badge github-work-pulse__item-state"
                >
                  {workItemStateLabel(item.state)}
                </span>
              </div>
              <h4>{item.title}</h4>
            </div>
            <dl className="work-meta github-work-pulse__item-meta">
              <div>
                <dt>{M.githubWork.metaRepository}</dt>
                <dd>{repositoryLabel(item)}</dd>
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
        </li>
      ))}
    </ul>
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

function stateLabel(state: GitHubOperationalWorkState): string {
  const labels: Record<GitHubOperationalWorkState, string> = {
    open: M.githubWork.stateOpen,
    closed: M.githubWork.stateClosed,
    merged: M.githubWork.stateMerged,
    all: M.githubWork.stateAll
  };
  return labels[state];
}
