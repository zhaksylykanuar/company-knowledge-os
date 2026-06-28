"use client";

import { useEffect, useState } from "react";

import { fetchCompanyBrain } from "../lib/api";
import { useWorkspaceId } from "../lib/session";
import type {
  CompanyBrainRepository,
  CompanyBrainResponse,
  CompanyBrainSourceRef,
  CompanyBrainWorkItem
} from "../lib/types";
import { EmptyState } from "./EmptyState";
import { ErrorState } from "./ErrorState";
import { LoadingState } from "./LoadingState";
import { SourceLink } from "./SourceLink";
import { StatusCard } from "./StatusCard";

type PanelStatus = "loading" | "ready" | "empty" | "error" | "missing";

type CompanyBrainPanelProps = {
  refreshSignal?: number;
};

type CompanyBrainPanelViewProps = {
  data: CompanyBrainResponse | null;
  error: string | null;
  onRetry?: () => void;
  status: PanelStatus;
};

export function CompanyBrainPanel({ refreshSignal = 0 }: CompanyBrainPanelProps) {
  const workspaceId = useWorkspaceId();
  const [data, setData] = useState<CompanyBrainResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [status, setStatus] = useState<PanelStatus>("loading");

  useEffect(() => {
    if (!workspaceId) {
      setData(null);
      setError(null);
      setStatus("missing");
      return;
    }

    let cancelled = false;
    setStatus("loading");
    setError(null);
    fetchCompanyBrain(workspaceId)
      .then((payload) => {
        if (cancelled) {
          return;
        }
        setData(payload);
        setStatus(hasCompanyBrainData(payload) ? "ready" : "empty");
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
  }, [workspaceId, refreshSignal, reloadKey]);

  return (
    <CompanyBrainPanelView
      data={data}
      error={error}
      onRetry={() => setReloadKey((current) => current + 1)}
      status={status}
    />
  );
}

export function CompanyBrainPanelView({
  data,
  error,
  onRetry,
  status
}: CompanyBrainPanelViewProps) {
  return (
    <section className="panel company-brain" aria-labelledby="company-brain-title">
      <div className="section-header">
        <div>
          <span className="eyebrow">Company Brain</span>
          <h2 id="company-brain-title">Evidence-backed GitHub state</h2>
        </div>
        <span className="badge">Deterministic</span>
      </div>

      {status === "loading" ? <LoadingState label="Loading Company Brain" /> : null}

      {status === "missing" ? (
        <EmptyState
          description="Your account has no workspace yet, so there is no Company Brain to show."
          title="No workspace available"
        />
      ) : null}

      {status === "error" ? (
        <>
          <ErrorState
            description={error ?? "The dashboard could not load Company Brain state."}
            title="Company Brain unavailable"
          />
          <button className="button secondary" onClick={onRetry} type="button">
            Retry
          </button>
        </>
      ) : null}

      {status === "empty" ? (
        <EmptyState
          description="No canonical GitHub records are synced yet. Run local GitHub sync, then return here for the evidence-backed state."
          title="No Company Brain data yet"
        />
      ) : null}

      {data && status === "ready" ? (
        <>
          <p className="muted">
            Company Brain is based on synced canonical GitHub records. Live OAuth,
            provider sync, and AI briefing are not enabled in this view.
          </p>
          <section className="grid" aria-label="Company Brain summary">
            <StatusCard
              description="Canonical GitHub repositories known to this workspace."
              title="Repositories"
              value={String(data.summary.repositories)}
            />
            <StatusCard
              description="Open GitHub issue/task records from canonical tasks."
              title="Open issues"
              value={String(data.summary.open_issues)}
            />
            <StatusCard
              description="Open pull requests linked to canonical repositories."
              title="Open PRs"
              value={String(data.summary.open_pull_requests)}
            />
            <StatusCard
              description="Closed issues and merged pull requests."
              title="Closed / merged"
              value={`${data.summary.closed_issues} / ${data.summary.merged_pull_requests}`}
            />
          </section>
          <section className="work-columns">
            <RepositorySection repositories={data.repositories} />
            <BrainWorkSection
              emptyText="No open issue/task records in Company Brain."
              items={data.work.issues}
              title="Open issues / tasks"
            />
            <BrainWorkSection
              emptyText="No open pull requests in Company Brain."
              items={data.work.pull_requests}
              title="Open pull requests"
            />
            <BrainWorkSection
              emptyText="No recent GitHub work has been synced yet."
              items={data.work.recent}
              title="Recent GitHub work"
            />
          </section>
          <EvidenceSection evidence={data.evidence} />
          <CapabilityNote data={data} />
          {data.warnings.length > 0 ? (
            <ul className="meta-list" aria-label="Company Brain warnings">
              {data.warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          ) : null}
        </>
      ) : null}
    </section>
  );
}

function RepositorySection({
  repositories
}: {
  repositories: CompanyBrainRepository[];
}) {
  return (
    <section className="work-section" aria-label="Company Brain repositories">
      <h3>Repositories</h3>
      {repositories.length === 0 ? (
        <p className="muted">No canonical repositories synced yet.</p>
      ) : null}
      <div className="work-list">
        {repositories.map((repository) => (
          <article className="work-item" key={repository.id}>
            <div className="work-item-main">
              <span className="badge">Repository</span>
              <h4>{repository.full_name}</h4>
            </div>
            <dl className="work-meta">
              <div>
                <dt>Visibility</dt>
                <dd>{repository.visibility ?? "unknown"}</dd>
              </div>
              <div>
                <dt>Archived</dt>
                <dd>{repository.archived ? "yes" : "no"}</dd>
              </div>
            </dl>
            <SourceRefList refs={repository.source_refs} />
            {repository.source_url ? (
              <SourceLink url={repository.source_url}>Open source</SourceLink>
            ) : null}
          </article>
        ))}
      </div>
    </section>
  );
}

function BrainWorkSection({
  emptyText,
  items,
  title
}: {
  emptyText: string;
  items: CompanyBrainWorkItem[];
  title: string;
}) {
  return (
    <section className="work-section" aria-label={title}>
      <h3>{title}</h3>
      {items.length === 0 ? <p className="muted">{emptyText}</p> : null}
      <div className="work-list">
        {items.map((item) => (
          <article className="work-item" key={`${item.type}-${item.id}`}>
            <div className="work-item-main">
              <span className="badge">{item.type === "issue" ? "Issue" : "PR"}</span>
              <h4>{item.title}</h4>
            </div>
            <dl className="work-meta">
              <div>
                <dt>Repository</dt>
                <dd>{item.repository_full_name ?? "Unknown repository"}</dd>
              </div>
              <div>
                <dt>State</dt>
                <dd>{item.state ?? "unknown"}</dd>
              </div>
              <div>
                <dt>Reference</dt>
                <dd>{item.number ? `#${item.number}` : item.external_id ?? "unknown"}</dd>
              </div>
            </dl>
            <SourceRefList refs={item.source_refs} />
            {item.source_url ? (
              <SourceLink url={item.source_url}>Open source</SourceLink>
            ) : null}
          </article>
        ))}
      </div>
    </section>
  );
}

function EvidenceSection({ evidence }: { evidence: CompanyBrainSourceRef[] }) {
  return (
    <section className="work-section" aria-label="Company Brain evidence">
      <h3>Evidence / sources</h3>
      {evidence.length === 0 ? (
        <p className="muted">No source refs were returned for the current records.</p>
      ) : null}
      <SourceRefList refs={evidence} />
    </section>
  );
}

function CapabilityNote({ data }: { data: CompanyBrainResponse }) {
  return (
    <section className="callout" aria-label="Company Brain capabilities">
      <strong>Current capability mode</strong>
      <p>
        Local sync: {data.capabilities.local_sync ? "available" : "unavailable"}.
        Live OAuth: {data.capabilities.live_github_oauth ? "enabled" : "not enabled"}.
        Provider sync: {data.capabilities.live_provider_sync ? "enabled" : "not enabled"}.
        AI briefing: {data.capabilities.llm_briefing ? "enabled" : "not enabled"}.
      </p>
    </section>
  );
}

function SourceRefList({ refs }: { refs: CompanyBrainSourceRef[] }) {
  if (refs.length === 0) {
    return (
      <p className="muted">
        Canonical synced record; no separate source ref returned.
      </p>
    );
  }
  return (
    <ul className="source-ref-list">
      {refs.map((ref) => (
        <li key={ref.id}>
          <SourceLink url={ref.url}>{ref.label}</SourceLink>
          <span className="muted"> {ref.kind}</span>
        </li>
      ))}
    </ul>
  );
}

function hasCompanyBrainData(data: CompanyBrainResponse): boolean {
  return (
    data.summary.repositories +
      data.summary.open_issues +
      data.summary.open_pull_requests +
      data.summary.closed_issues +
      data.summary.merged_pull_requests >
    0
  );
}
