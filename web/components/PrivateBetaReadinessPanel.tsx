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

type PanelStatus = "error" | "loading" | "missing" | "ready";

type PrivateBetaReadinessPanelProps = {
  refreshSignal?: number;
};

type PrivateBetaReadinessPanelViewProps = {
  data: CompanyBrainResponse | null;
  error: string | null;
  onRetry?: () => void;
  status: PanelStatus;
};

type ReadinessItem = {
  description: string;
  id: string;
  label: string;
  status: string;
};

export function PrivateBetaReadinessPanel({
  refreshSignal = 0
}: PrivateBetaReadinessPanelProps) {
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
        setStatus("ready");
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
    <PrivateBetaReadinessPanelView
      data={data}
      error={error}
      onRetry={() => setReloadKey((current) => current + 1)}
      status={status}
    />
  );
}

export function PrivateBetaReadinessPanelView({
  data,
  error,
  onRetry,
  status
}: PrivateBetaReadinessPanelViewProps) {
  const summary = readinessSummary(data);

  return (
    <section
      className="panel private-beta-readiness"
      aria-labelledby="private-beta-readiness-title"
    >
      <div className="section-header">
        <div>
          <span className="eyebrow">{M.privateBetaReadiness.eyebrow}</span>
          <h2 id="private-beta-readiness-title">{M.privateBetaReadiness.title}</h2>
        </div>
        <span className="badge">{M.privateBetaReadiness.badgeManual}</span>
      </div>

      {status === "loading" ? (
        <LoadingState label={M.privateBetaReadiness.loading} />
      ) : null}

      {status === "missing" ? (
        <EmptyState
          description={M.privateBetaReadiness.noWorkspaceDescription}
          title={M.common.noWorkspaceTitle}
        />
      ) : null}

      {status === "error" ? (
        <>
          <ErrorState
            description={error ?? M.privateBetaReadiness.unavailableDescription}
            title={M.privateBetaReadiness.unavailableTitle}
          />
          <button className="button secondary" onClick={onRetry} type="button">
            {M.common.retry}
          </button>
        </>
      ) : null}

      {status === "ready" ? (
        <>
          <p className="muted">{M.privateBetaReadiness.intro}</p>
          <section className="grid" aria-label={M.privateBetaReadiness.summaryLabel}>
            <StatusCard
              description={M.privateBetaReadiness.dataDescription}
              title={M.privateBetaReadiness.dataTitle}
              value={summary.dataReady ? M.common.yes : M.common.no}
            />
            <StatusCard
              description={M.privateBetaReadiness.externalWritesDescription}
              title={M.privateBetaReadiness.externalWritesTitle}
              value={M.privateBetaReadiness.externalWritesValue}
            />
            <StatusCard
              description={M.privateBetaReadiness.deployDescription}
              title={M.privateBetaReadiness.deployTitle}
              value={M.privateBetaReadiness.deployValue}
            />
            <StatusCard
              description={M.privateBetaReadiness.aiDescription}
              title={M.privateBetaReadiness.aiTitle}
              value={M.privateBetaReadiness.aiValue}
            />
          </section>
          <ReadinessList items={readinessItems(data, summary)} />
          {data?.warnings.length ? (
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

function ReadinessList({ items }: { items: ReadinessItem[] }) {
  return (
    <section className="work-section" aria-label={M.privateBetaReadiness.detailsLabel}>
      <h3>{M.privateBetaReadiness.detailsTitle}</h3>
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

function readinessSummary(data: CompanyBrainResponse | null) {
  const repositories = data?.summary.repositories ?? 0;
  const evidenceRefs = data?.evidence.length ?? 0;
  const openWork =
    (data?.summary.open_issues ?? 0) + (data?.summary.open_pull_requests ?? 0);
  return {
    dataReady: repositories > 0 && evidenceRefs > 0,
    evidenceRefs,
    openWork,
    repositories
  };
}

function readinessItems(
  data: CompanyBrainResponse | null,
  summary: ReturnType<typeof readinessSummary>
): ReadinessItem[] {
  const liveProviderSync = data?.capabilities.live_provider_sync ?? false;
  const llmBriefing = data?.capabilities.llm_briefing ?? false;

  return [
    {
      description: summary.dataReady
        ? T.privateBetaReadinessDataReady(
            summary.repositories,
            summary.evidenceRefs,
            summary.openWork
          )
        : M.privateBetaReadiness.dataNeedsEvidenceDescription,
      id: "canonical-data",
      label: M.privateBetaReadiness.dataLabel,
      status: summary.dataReady
        ? M.privateBetaReadiness.statusReady
        : M.privateBetaReadiness.statusNeedsData
    },
    {
      description: M.privateBetaReadiness.sessionDescription,
      id: "session-auth",
      label: M.privateBetaReadiness.sessionLabel,
      status: M.privateBetaReadiness.statusReady
    },
    {
      description: M.privateBetaReadiness.manualDeployDescription,
      id: "manual-deploy",
      label: M.privateBetaReadiness.manualDeployLabel,
      status: M.privateBetaReadiness.statusManual
    },
    {
      description: liveProviderSync
        ? M.privateBetaReadiness.providerReadAvailableDescription
        : M.privateBetaReadiness.providerReadDeferredDescription,
      id: "provider-read",
      label: M.privateBetaReadiness.providerReadLabel,
      status: liveProviderSync
        ? M.privateBetaReadiness.statusAvailable
        : M.privateBetaReadiness.statusDeferred
    },
    {
      description: M.privateBetaReadiness.externalWritesOffDescription,
      id: "external-writes",
      label: M.privateBetaReadiness.externalWritesLabel,
      status: M.privateBetaReadiness.statusOff
    },
    {
      description: llmBriefing
        ? M.privateBetaReadiness.llmAvailableDescription
        : M.privateBetaReadiness.llmOffDescription,
      id: "llm",
      label: M.privateBetaReadiness.llmLabel,
      status: llmBriefing
        ? M.privateBetaReadiness.statusAvailable
        : M.privateBetaReadiness.statusOff
    }
  ];
}
