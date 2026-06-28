"use client";

import { useEffect, useState } from "react";

import { fetchCompanyBrain } from "../lib/api";
import { M, T } from "../lib/messages";
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
        setError(caught instanceof Error ? caught.message : M.common.requestFailed);
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
          <span className="eyebrow">{M.companyBrain.eyebrow}</span>
          <h2 id="company-brain-title">{M.companyBrain.title}</h2>
        </div>
        <span className="badge">{M.companyBrain.badgeDeterministic}</span>
      </div>

      {status === "loading" ? <LoadingState label={M.companyBrain.loading} /> : null}

      {status === "missing" ? (
        <EmptyState
          description={M.companyBrain.noWorkspaceDescription}
          title={M.common.noWorkspaceTitle}
        />
      ) : null}

      {status === "error" ? (
        <>
          <ErrorState
            description={error ?? M.companyBrain.unavailableDescription}
            title={M.companyBrain.unavailableTitle}
          />
          <button className="button secondary" onClick={onRetry} type="button">
            {M.common.retry}
          </button>
        </>
      ) : null}

      {status === "empty" ? (
        <EmptyState
          description={M.companyBrain.emptyDescription}
          title={M.companyBrain.emptyTitle}
        />
      ) : null}

      {data && status === "ready" ? (
        <>
          <p className="muted">{M.companyBrain.intro}</p>
          <section className="grid" aria-label={M.companyBrain.summaryLabel}>
            <StatusCard
              description={M.companyBrain.reposDescription}
              title={M.companyBrain.reposTitle}
              value={String(data.summary.repositories)}
            />
            <StatusCard
              description={M.companyBrain.openIssuesDescription}
              title={M.companyBrain.openIssuesTitle}
              value={String(data.summary.open_issues)}
            />
            <StatusCard
              description={M.companyBrain.openPrsDescription}
              title={M.companyBrain.openPrsTitle}
              value={String(data.summary.open_pull_requests)}
            />
            <StatusCard
              description={M.companyBrain.closedDescription}
              title={M.companyBrain.closedTitle}
              value={`${data.summary.closed_issues} / ${data.summary.merged_pull_requests}`}
            />
          </section>
          <section className="work-columns">
            <RepositorySection repositories={data.repositories} />
            <BrainWorkSection
              emptyText={M.companyBrain.noOpenIssues}
              items={data.work.issues}
              title={M.companyBrain.openIssuesSection}
            />
            <BrainWorkSection
              emptyText={M.companyBrain.noOpenPrs}
              items={data.work.pull_requests}
              title={M.companyBrain.openPrsSection}
            />
            <BrainWorkSection
              emptyText={M.companyBrain.noRecent}
              items={data.work.recent}
              title={M.companyBrain.recentSection}
            />
          </section>
          <EvidenceSection evidence={data.evidence} />
          <CapabilityNote data={data} />
          {data.warnings.length > 0 ? (
            <ul className="meta-list" aria-label={M.common.warnings}>
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
    <section className="work-section" aria-label={M.companyBrain.reposSection}>
      <h3>{M.companyBrain.reposSection}</h3>
      {repositories.length === 0 ? (
        <p className="muted">{M.companyBrain.noRepos}</p>
      ) : null}
      <div className="work-list">
        {repositories.map((repository) => (
          <article className="work-item" key={repository.id}>
            <div className="work-item-main">
              <span className="badge">{M.companyBrain.repoBadge}</span>
              <h4>{repository.full_name}</h4>
            </div>
            <dl className="work-meta">
              <div>
                <dt>{M.companyBrain.metaVisibility}</dt>
                <dd>{repository.visibility ?? M.common.unknown}</dd>
              </div>
              <div>
                <dt>{M.companyBrain.archived}</dt>
                <dd>{repository.archived ? M.common.yes : M.common.no}</dd>
              </div>
            </dl>
            <SourceRefList refs={repository.source_refs} />
            {repository.source_url ? (
              <SourceLink url={repository.source_url}>{M.common.openSource}</SourceLink>
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
              <span className="badge">{item.type === "issue" ? M.companyBrain.badgeIssue : M.companyBrain.badgePr}</span>
              <h4>{item.title}</h4>
            </div>
            <dl className="work-meta">
              <div>
                <dt>{M.companyBrain.metaRepository}</dt>
                <dd>{item.repository_full_name ?? M.companyBrain.unknownRepository}</dd>
              </div>
              <div>
                <dt>{M.companyBrain.metaState}</dt>
                <dd>{item.state ?? M.common.unknown}</dd>
              </div>
              <div>
                <dt>{M.companyBrain.metaReference}</dt>
                <dd>{item.number ? `#${item.number}` : item.external_id ?? M.common.unknown}</dd>
              </div>
            </dl>
            <SourceRefList refs={item.source_refs} />
            {item.source_url ? (
              <SourceLink url={item.source_url}>{M.common.openSource}</SourceLink>
            ) : null}
          </article>
        ))}
      </div>
    </section>
  );
}

function EvidenceSection({ evidence }: { evidence: CompanyBrainSourceRef[] }) {
  return (
    <section className="work-section" aria-label={M.companyBrain.evidenceSection}>
      <h3>{M.companyBrain.evidenceSection}</h3>
      {evidence.length === 0 ? (
        <p className="muted">{M.companyBrain.noEvidence}</p>
      ) : null}
      <SourceRefList refs={evidence} />
    </section>
  );
}

function CapabilityNote({ data }: { data: CompanyBrainResponse }) {
  return (
    <section className="callout" aria-label={M.companyBrain.capabilityTitle}>
      <strong>{M.companyBrain.capabilityTitle}</strong>
      <p>
        {T.brainCapability(
          data.capabilities.local_sync,
          data.capabilities.live_github_oauth,
          data.capabilities.live_provider_sync,
          data.capabilities.llm_briefing
        )}
      </p>
    </section>
  );
}

function SourceRefList({ refs }: { refs: CompanyBrainSourceRef[] }) {
  if (refs.length === 0) {
    return <p className="muted">{M.companyBrain.noSourceRef}</p>;
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
