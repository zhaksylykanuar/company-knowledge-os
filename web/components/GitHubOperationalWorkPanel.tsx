"use client";

import { useEffect, useState } from "react";

import { fetchGitHubOperationalWork } from "../lib/api";
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
  { value: "open", label: "Open" },
  { value: "all", label: "All" },
  { value: "closed", label: "Closed" },
  { value: "merged", label: "Merged" }
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
        setError(caught instanceof Error ? caught.message : "Request failed");
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
          <span className="eyebrow">GitHub</span>
          <h2 id="github-work-title">Operational work</h2>
        </div>
        <div className="segmented" aria-label="GitHub work state">
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

      {status === "loading" ? <LoadingState label="Loading GitHub work" /> : null}

      {status === "missing" ? (
        <EmptyState
          description="Your account has no workspace yet, so there is no GitHub work to show."
          title="No workspace available"
        />
      ) : null}

      {status === "error" ? (
        <>
          <ErrorState
            description={error ?? "The dashboard could not load GitHub work."}
            title="GitHub operational work unavailable"
          />
          <button className="button secondary" onClick={onRetry} type="button">
            Retry
          </button>
        </>
      ) : null}

      {status === "empty" ? (
        <EmptyState
          description="Run local GitHub normalization with canonical persistence to populate issues and pull requests."
          title="No GitHub operational work synced yet"
        />
      ) : null}

      {data && status !== "loading" && status !== "error" && status !== "missing" ? (
        <>
          <section className="grid" aria-label="GitHub operational work counts">
            <StatusCard
              description={`${stateLabel(selectedState)} GitHub issue/task records from the canonical backend path.`}
              title="Issues / tasks"
              value={String(data.counts.issues)}
            />
            <StatusCard
              description={`${stateLabel(selectedState)} pull requests linked to repositories where available.`}
              title="Pull requests"
              value={String(data.counts.pull_requests)}
            />
          </section>
          <div className="work-columns">
            <WorkSection
              emptyText="No issue/task records for this filter."
              items={data.issues}
              title="Issues / tasks"
              type="issue"
            />
            <WorkSection
              emptyText="No pull requests for this filter."
              items={data.pull_requests}
              title="Pull requests"
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
              <span className="badge">{type === "issue" ? "Issue" : "PR"}</span>
              <h4>{item.title}</h4>
            </div>
            <dl className="work-meta">
              <div>
                <dt>Repository</dt>
                <dd>{repositoryLabel(item)}</dd>
              </div>
              <div>
                <dt>State</dt>
                <dd>{item.state ?? "unknown"}</dd>
              </div>
              <div>
                <dt>Reference</dt>
                <dd>{referenceLabel(item)}</dd>
              </div>
              {timestampLabel(item) ? (
                <div>
                  <dt>Updated</dt>
                  <dd>
                    <time dateTime={timestampLabel(item) ?? undefined}>
                      {formatSourceTimestamp(timestampLabel(item))}
                    </time>
                  </dd>
                </div>
              ) : null}
            </dl>
            {item.source_url ? (
              <SourceLink url={item.source_url}>Open source</SourceLink>
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
    "Repository unavailable"
  );
}

function referenceLabel(
  item: GitHubOperationalIssue | GitHubOperationalPullRequest
): string {
  if (typeof item.number === "number") {
    return `#${item.number}`;
  }
  return item.external_id || "No external id";
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
    return "Unknown";
  }
  return value.replace("T", " ").replace("+00:00", " UTC").replace("Z", " UTC");
}

function stateLabel(state: GitHubOperationalWorkState): string {
  if (state === "all") {
    return "All";
  }
  return state.charAt(0).toUpperCase() + state.slice(1);
}
