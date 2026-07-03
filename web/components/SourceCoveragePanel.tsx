"use client";

import { useEffect, useState } from "react";

import { fetchCompanyBrain } from "../lib/api";
import { M, T } from "../lib/messages";
import { useWorkspaceId } from "../lib/session";
import type { CompanyBrainResponse } from "../lib/types";
import { EmptyState } from "./EmptyState";
import { ErrorState } from "./ErrorState";
import { LoadingState } from "./LoadingState";
import { StatusCard } from "./StatusCard";

type PanelStatus = "loading" | "ready" | "empty" | "error" | "missing";

type SourceCoveragePanelProps = {
  refreshSignal?: number;
};

type SourceCoveragePanelViewProps = {
  data: CompanyBrainResponse | null;
  error: string | null;
  onRetry?: () => void;
  status: PanelStatus;
};

type CoverageItem = {
  description: string;
  id: string;
  label: string;
  status: string;
};

type EvidenceKindCount = {
  kind: string;
  count: number;
};

export function SourceCoveragePanel({ refreshSignal = 0 }: SourceCoveragePanelProps) {
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
        setStatus(hasSourceCoverage(payload) ? "ready" : "empty");
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
    <SourceCoveragePanelView
      data={data}
      error={error}
      onRetry={() => setReloadKey((current) => current + 1)}
      status={status}
    />
  );
}

export function SourceCoveragePanelView({
  data,
  error,
  onRetry,
  status
}: SourceCoveragePanelViewProps) {
  return (
    <section className="panel source-coverage" aria-labelledby="source-coverage-title">
      <div className="section-header">
        <div>
          <span className="eyebrow">{M.sourceCoverage.eyebrow}</span>
          <h2 id="source-coverage-title">{M.sourceCoverage.title}</h2>
        </div>
        <span className="badge">{M.sourceCoverage.badgeDeterministic}</span>
      </div>

      {status === "loading" ? <LoadingState label={M.sourceCoverage.loading} /> : null}

      {status === "missing" ? (
        <EmptyState
          description={M.sourceCoverage.noWorkspaceDescription}
          title={M.common.noWorkspaceTitle}
        />
      ) : null}

      {status === "error" ? (
        <>
          <ErrorState
            description={error ?? M.sourceCoverage.unavailableDescription}
            title={M.sourceCoverage.unavailableTitle}
          />
          <button className="button secondary" onClick={onRetry} type="button">
            {M.common.retry}
          </button>
        </>
      ) : null}

      {status === "empty" ? (
        <EmptyState
          description={M.sourceCoverage.emptyDescription}
          title={M.sourceCoverage.emptyTitle}
        />
      ) : null}

      {data && status === "ready" ? (
        <>
          <p className="muted">{M.sourceCoverage.intro}</p>
          <section className="grid" aria-label={M.sourceCoverage.summaryLabel}>
            <StatusCard
              description={M.sourceCoverage.repositoriesDescription}
              title={M.sourceCoverage.repositoriesTitle}
              value={String(data.summary.repositories)}
            />
            <StatusCard
              description={M.sourceCoverage.workDescription}
              title={M.sourceCoverage.workTitle}
              value={T.sourceCoverageWork(
                data.summary.open_issues,
                data.summary.open_pull_requests
              )}
            />
            <StatusCard
              description={M.sourceCoverage.evidenceDescription}
              title={M.sourceCoverage.evidenceTitle}
              value={String(data.evidence.length)}
            />
            <StatusCard
              description={M.sourceCoverage.modeDescription}
              title={M.sourceCoverage.modeTitle}
              value={data.is_live ? M.sourceCoverage.modeLive : M.sourceCoverage.modeLocal}
            />
          </section>
          <CoverageList items={coverageItems(data)} />
          <CoverageBreakdown data={data} />
          <CoverageNextSteps items={coverageNextSteps(data)} />
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

function CoverageList({ items }: { items: CoverageItem[] }) {
  return (
    <section className="work-section" aria-label={M.sourceCoverage.detailsLabel}>
      <h3>{M.sourceCoverage.detailsTitle}</h3>
      <div className="work-list">
        {items.map((item) => (
          <article className="work-item" key={item.id}>
            <div className="work-item-main">
              <span className="badge">{item.status}</span>
              <h4>{item.label}</h4>
            </div>
            <p className="muted">{item.description}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

function CoverageBreakdown({ data }: { data: CompanyBrainResponse }) {
  const reposWithRefs = repositoriesWithSourceRefs(data);
  const reposWithoutRefs = data.repositories.length - reposWithRefs;
  const evidenceKinds = evidenceKindCounts(data.evidence);

  return (
    <section className="work-section" aria-label={M.sourceCoverage.breakdownLabel}>
      <h3>{M.sourceCoverage.breakdownTitle}</h3>
      <section className="grid" aria-label={M.sourceCoverage.breakdownLabel}>
        <StatusCard
          description={M.sourceCoverage.closedWorkDescription}
          title={M.sourceCoverage.closedWorkTitle}
          value={T.sourceCoverageClosedWork(
            data.summary.closed_issues,
            data.summary.merged_pull_requests
          )}
        />
        <StatusCard
          description={M.sourceCoverage.recentDescription}
          title={M.sourceCoverage.recentTitle}
          value={String(data.work.recent.length)}
        />
      </section>
      {data.repositories.length > 0 ? (
        <ul className="meta-list" aria-label={M.sourceCoverage.repositoriesLabel}>
          <li>{T.sourceCoverageReposWithEvidence(reposWithRefs, data.repositories.length)}</li>
          {reposWithoutRefs > 0 ? (
            <li>{T.sourceCoverageReposWithoutEvidence(reposWithoutRefs)}</li>
          ) : null}
        </ul>
      ) : null}
      <h4>{M.sourceCoverage.evidenceKindsTitle}</h4>
      <p className="muted">{M.sourceCoverage.evidenceKindsDescription}</p>
      {evidenceKinds.length > 0 ? (
        <ul className="meta-list" aria-label={M.sourceCoverage.evidenceKindsTitle}>
          {evidenceKinds.map((entry) => (
            <li key={entry.kind}>
              {T.sourceCoverageEvidenceKind(entry.kind, entry.count)}
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted">{M.sourceCoverage.evidenceKindsEmpty}</p>
      )}
    </section>
  );
}

function CoverageNextSteps({ items }: { items: CoverageItem[] }) {
  return (
    <section className="work-section" aria-label={M.sourceCoverage.nextStepsLabel}>
      <h3>{M.sourceCoverage.nextStepsTitle}</h3>
      <div className="work-list">
        {items.map((item) => (
          <article className="work-item" key={item.id}>
            <div className="work-item-main">
              <span className="badge">{item.status}</span>
              <h4>{item.label}</h4>
            </div>
            <p className="muted">{item.description}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

function coverageNextSteps(data: CompanyBrainResponse): CoverageItem[] {
  const reposWithRefs = repositoriesWithSourceRefs(data);
  const reposWithoutRefs = data.repositories.length - reposWithRefs;
  const openWork = data.summary.open_issues + data.summary.open_pull_requests;

  return [
    {
      description:
        data.summary.repositories > 0
          ? T.sourceCoverageNextStepDataReady(data.summary.repositories)
          : M.sourceCoverage.nextStepDataMissingDescription,
      id: "next-data",
      label: M.sourceCoverage.nextStepDataLabel,
      status:
        data.summary.repositories > 0
          ? M.sourceCoverage.statusReady
          : M.sourceCoverage.statusNeedsData
    },
    {
      description:
        data.evidence.length === 0
          ? M.sourceCoverage.nextStepEvidenceMissingDescription
          : reposWithoutRefs > 0
            ? T.sourceCoverageNextStepEvidenceGaps(reposWithoutRefs)
            : M.sourceCoverage.nextStepEvidenceReadyDescription,
      id: "next-evidence",
      label: M.sourceCoverage.nextStepEvidenceLabel,
      status:
        data.evidence.length > 0 && reposWithoutRefs === 0
          ? M.sourceCoverage.statusReady
          : M.sourceCoverage.statusNeedsEvidence
    },
    {
      description:
        openWork > 0
          ? T.sourceCoverageNextStepOpenWork(openWork)
          : M.sourceCoverage.nextStepNoOpenWorkDescription,
      id: "next-work",
      label: M.sourceCoverage.nextStepWorkLabel,
      status: openWork > 0 ? M.sourceCoverage.statusReview : M.sourceCoverage.statusReady
    },
    {
      description: data.capabilities.live_provider_sync
        ? M.sourceCoverage.nextStepProviderEnabledDescription
        : M.sourceCoverage.nextStepProviderDeferredDescription,
      id: "next-provider",
      label: M.sourceCoverage.nextStepProviderLabel,
      status: data.capabilities.live_provider_sync
        ? M.sourceCoverage.statusBoundary
        : M.sourceCoverage.statusDeferred
    },
    {
      description: data.capabilities.llm_briefing
        ? M.sourceCoverage.nextStepAiEnabledDescription
        : M.sourceCoverage.nextStepAiOffDescription,
      id: "next-ai",
      label: M.sourceCoverage.nextStepAiLabel,
      status: data.capabilities.llm_briefing
        ? M.sourceCoverage.statusBoundary
        : M.sourceCoverage.statusOff
    }
  ];
}

function repositoriesWithSourceRefs(data: CompanyBrainResponse): number {
  return data.repositories.filter((repository) => repository.source_refs.length > 0).length;
}

function evidenceKindCounts(
  evidence: CompanyBrainResponse["evidence"]
): EvidenceKindCount[] {
  const counts = new Map<string, number>();
  for (const ref of evidence) {
    counts.set(ref.kind, (counts.get(ref.kind) ?? 0) + 1);
  }
  return Array.from(counts.entries())
    .map(([kind, count]) => ({ kind, count }))
    .sort((a, b) => (b.count - a.count) || a.kind.localeCompare(b.kind));
}

function coverageItems(data: CompanyBrainResponse): CoverageItem[] {
  return [
    {
      description:
        data.summary.repositories > 0
          ? T.sourceCoverageRepositoriesReady(data.summary.repositories)
          : M.sourceCoverage.repositoriesEmpty,
      id: "repositories",
      label: M.sourceCoverage.repositoriesLabel,
      status:
        data.summary.repositories > 0
          ? M.sourceCoverage.statusReady
          : M.sourceCoverage.statusEmpty
    },
    {
      description: data.capabilities.live_provider_sync
        ? M.sourceCoverage.liveProviderEnabledDescription
        : M.sourceCoverage.liveProviderDeferredDescription,
      id: "live-provider",
      label: M.sourceCoverage.liveProviderLabel,
      status: data.capabilities.live_provider_sync
        ? M.sourceCoverage.statusEnabled
        : M.sourceCoverage.statusDeferred
    },
    {
      description: data.capabilities.llm_briefing
        ? M.sourceCoverage.llmEnabledDescription
        : M.sourceCoverage.llmOffDescription,
      id: "llm",
      label: M.sourceCoverage.llmLabel,
      status: data.capabilities.llm_briefing
        ? M.sourceCoverage.statusEnabled
        : M.sourceCoverage.statusOff
    },
    {
      description:
        data.evidence.length > 0
          ? T.sourceCoverageEvidenceReady(data.evidence.length)
          : M.sourceCoverage.evidenceEmpty,
      id: "evidence",
      label: M.sourceCoverage.evidenceLabel,
      status:
        data.evidence.length > 0
          ? M.sourceCoverage.statusReady
          : M.sourceCoverage.statusNeedsEvidence
    }
  ];
}

function hasSourceCoverage(data: CompanyBrainResponse): boolean {
  return (
    data.summary.repositories +
      data.summary.open_issues +
      data.summary.open_pull_requests +
      data.summary.closed_issues +
      data.summary.merged_pull_requests +
      data.evidence.length >
    0
  );
}
