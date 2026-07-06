"use client";

import { useEffect, useState } from "react";

import { fetchCompanyBrainEntities } from "../lib/api";
import { M } from "../lib/messages";
import { useWorkspaceId } from "../lib/session";
import type { CompanyBrainSourceRef, NormalizedEntitiesResponse, NormalizedEntity } from "../lib/types";
import { EmptyState } from "./EmptyState";
import { ErrorState } from "./ErrorState";
import { LoadingState } from "./LoadingState";
import { SourceLink } from "./SourceLink";
import { StatusCard } from "./StatusCard";

type PanelStatus = "loading" | "ready" | "empty" | "error" | "missing";

type NormalizedEntitiesPanelProps = {
  refreshSignal?: number;
};

type NormalizedEntitiesPanelViewProps = {
  data: NormalizedEntitiesResponse | null;
  error: string | null;
  onRetry?: () => void;
  status: PanelStatus;
};

export function NormalizedEntitiesPanel({ refreshSignal = 0 }: NormalizedEntitiesPanelProps) {
  const workspaceId = useWorkspaceId();
  const [data, setData] = useState<NormalizedEntitiesResponse | null>(null);
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
    fetchCompanyBrainEntities(workspaceId)
      .then((payload) => {
        if (cancelled) {
          return;
        }
        setData(payload);
        setStatus(payload.entities.length > 0 ? "ready" : "empty");
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
    <NormalizedEntitiesPanelView
      data={data}
      error={error}
      onRetry={() => setReloadKey((current) => current + 1)}
      status={status}
    />
  );
}

export function NormalizedEntitiesPanelView({
  data,
  error,
  onRetry,
  status
}: NormalizedEntitiesPanelViewProps) {
  return (
    <section className="panel normalized-entities" aria-labelledby="normalized-entities-title">
      <div className="section-header">
        <div>
          <span className="eyebrow">{M.companyBrainEntities.eyebrow}</span>
          <h2 id="normalized-entities-title">{M.companyBrainEntities.title}</h2>
        </div>
        <span className="badge">{M.companyBrainEntities.badgeProjection}</span>
      </div>

      {status === "loading" ? <LoadingState label={M.companyBrainEntities.loading} /> : null}

      {status === "missing" ? (
        <EmptyState
          description={M.companyBrainEntities.noWorkspaceDescription}
          title={M.common.noWorkspaceTitle}
        />
      ) : null}

      {status === "error" ? (
        <>
          <ErrorState
            description={error ?? M.companyBrainEntities.unavailableDescription}
            title={M.companyBrainEntities.unavailableTitle}
          />
          <button className="button secondary" onClick={onRetry} type="button">
            {M.common.retry}
          </button>
        </>
      ) : null}

      {status === "empty" ? (
        <EmptyState
          description={M.companyBrainEntities.emptyDescription}
          title={M.companyBrainEntities.emptyTitle}
        />
      ) : null}

      {data && status === "ready" ? (
        <>
          <p className="muted">{M.companyBrainEntities.intro}</p>
          <section className="grid" aria-label={M.companyBrainEntities.summaryLabel}>
            <StatusCard
              description={M.companyBrainEntities.totalDescription}
              title={M.companyBrainEntities.totalTitle}
              value={String(data.summary.total)}
            />
            <StatusCard
              description={M.companyBrainEntities.typesDescription}
              title={M.companyBrainEntities.typesTitle}
              value={String(data.summary.by_entity_type.length)}
            />
            <StatusCard
              description={M.companyBrainEntities.providersDescription}
              title={M.companyBrainEntities.providersTitle}
              value={String(data.summary.by_source_provider.length)}
            />
            <StatusCard
              description={M.companyBrainEntities.evidenceDescription}
              title={M.companyBrainEntities.evidenceTitle}
              value={String(data.evidence.length)}
            />
          </section>
          <BreakdownSection data={data} />
          <EntitiesList entities={data.entities} />
          <EntityEvidence evidence={data.evidence} />
          <p className="muted">{M.companyBrainEntities.boundaryNote}</p>
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

function BreakdownSection({ data }: { data: NormalizedEntitiesResponse }) {
  return (
    <section className="work-columns">
      <section className="work-section" aria-label={M.companyBrainEntities.typeBreakdownTitle}>
        <h3>{M.companyBrainEntities.typeBreakdownTitle}</h3>
        <ul className="meta-list">
          {data.summary.by_entity_type.map((row) => (
            <li key={row.entity_type}>{row.entity_type}: {row.count}</li>
          ))}
        </ul>
      </section>
      <section className="work-section" aria-label={M.companyBrainEntities.providerBreakdownTitle}>
        <h3>{M.companyBrainEntities.providerBreakdownTitle}</h3>
        <ul className="meta-list">
          {data.summary.by_source_provider.map((row) => (
            <li key={row.source_provider}>{row.source_provider}: {row.count}</li>
          ))}
        </ul>
      </section>
    </section>
  );
}

function EntitiesList({ entities }: { entities: NormalizedEntity[] }) {
  return (
    <section className="work-section" aria-label={M.companyBrainEntities.listLabel}>
      <h3>{M.companyBrainEntities.listLabel}</h3>
      <div className="work-list">
        {entities.map((entity) => (
          <article className="work-item" key={entity.key}>
            <div className="work-item-main">
              <span className="badge">{entity.entity_type}</span>
              <h4>{entity.title}</h4>
            </div>
            <dl className="work-meta">
              <div>
                <dt>{M.companyBrainEntities.metaProvider}</dt>
                <dd>{entity.source_provider}</dd>
              </div>
              <div>
                <dt>{M.companyBrainEntities.metaStatus}</dt>
                <dd>{entity.status ?? M.common.none}</dd>
              </div>
              <div>
                <dt>{M.companyBrainEntities.metaReference}</dt>
                <dd>{entity.external_id}</dd>
              </div>
              <div>
                <dt>{M.companyBrainEntities.metaUpdated}</dt>
                <dd>{entity.updated_at ?? M.common.unknown}</dd>
              </div>
            </dl>
            <SourceRefList refs={entity.source_refs} />
            {entity.source_url ? (
              <SourceLink url={entity.source_url}>{M.common.openSource}</SourceLink>
            ) : null}
          </article>
        ))}
      </div>
    </section>
  );
}

function EntityEvidence({ evidence }: { evidence: CompanyBrainSourceRef[] }) {
  return (
    <section className="work-section" aria-label={M.companyBrainEntities.evidenceTitle}>
      <h3>{M.companyBrainEntities.evidenceTitle}</h3>
      {evidence.length === 0 ? <p className="muted">{M.companyBrainEntities.noEvidence}</p> : null}
      <SourceRefList refs={evidence} />
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
