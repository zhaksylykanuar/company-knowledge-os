"use client";

import { useEffect, useState } from "react";

import { PageHeader } from "../../components/PageHeader";
import { StatusCard } from "../../components/StatusCard";
import { fetchWorkspaceConnectors } from "../../lib/api";
import { M } from "../../lib/messages";
import { useWorkspaceId } from "../../lib/session";
import type { Connector, ConnectorRegistryResponse } from "../../lib/types";

type PanelStatus = "error" | "loading" | "missing" | "ready";

type ConnectorsPanelViewProps = {
  data: ConnectorRegistryResponse | null;
  error: string | null;
  onRetry?: () => void;
  status: PanelStatus;
};

export default function ConnectorsPage() {
  const workspaceId = useWorkspaceId();
  const [data, setData] = useState<ConnectorRegistryResponse | null>(null);
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
    fetchWorkspaceConnectors(workspaceId)
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
  }, [workspaceId, reloadKey]);

  return (
    <>
      <PageHeader
        eyebrow={M.connectors.eyebrow}
        title={M.connectors.title}
        description={M.connectors.description}
      />
      <ConnectorsPanelView
        data={data}
        error={error}
        onRetry={() => setReloadKey((current) => current + 1)}
        status={status}
      />
    </>
  );
}

export function ConnectorsPanelView({
  data,
  error,
  onRetry,
  status
}: ConnectorsPanelViewProps) {
  return (
    <section className="panel connectors" aria-labelledby="connectors-title">
      <div className="section-header">
        <div>
          <span className="eyebrow">{M.connectors.eyebrow}</span>
          <h2 id="connectors-title">{M.connectors.title}</h2>
        </div>
        <span className="badge">{M.connectors.badgeReadOnly}</span>
      </div>

      {status === "loading" ? <p className="state loading">{M.connectors.loading}</p> : null}

      {status === "missing" ? (
        <p className="muted">{M.connectors.noWorkspaceDescription}</p>
      ) : null}

      {status === "error" ? (
        <section className="state error">
          <strong>{M.connectors.unavailableTitle}</strong>
          <p>{error ?? M.connectors.unavailableDescription}</p>
          {onRetry ? (
            <button className="button secondary" onClick={onRetry} type="button">
              {M.common.retry}
            </button>
          ) : null}
        </section>
      ) : null}

      {data && status === "ready" ? (
        <>
          <section className="grid" aria-label={M.connectors.summaryLabel}>
            <StatusCard
              description={M.connectors.totalDescription}
              title={M.connectors.totalTitle}
              value={String(data.summary.total)}
            />
            <StatusCard
              description={M.connectors.availableDescription}
              title={M.connectors.availableTitle}
              value={String(data.summary.available)}
            />
            <StatusCard
              description={M.connectors.plannedDescription}
              title={M.connectors.plannedTitle}
              value={String(data.summary.planned)}
            />
            <StatusCard
              description={M.connectors.connectedDescription}
              title={M.connectors.connectedTitle}
              value={String(data.summary.connected)}
            />
          </section>

          <div className="work-list" aria-label={M.connectors.listLabel}>
            {data.connectors.map((connector) => (
              <ConnectorCard connector={connector} key={connector.provider} />
            ))}
          </div>

          <p className="muted">{M.connectors.boundaryNote}</p>
        </>
      ) : null}
    </section>
  );
}

function ConnectorCard({ connector }: { connector: Connector }) {
  const statusLabel =
    connector.status === "available"
      ? M.connectors.statusAvailable
      : M.connectors.statusPlanned;
  return (
    <article className="work-item">
      <div className="work-item-main">
        <span className="badge">{statusLabel}</span>
        <h3>{connector.name}</h3>
      </div>
      <p className="muted">{connector.summary}</p>
      <dl className="work-meta">
        <div>
          <dt>{M.connectors.connectionsLabel}</dt>
          <dd>{connector.connection_count}</dd>
        </div>
        <div>
          <dt>{M.connectors.connectedLabel}</dt>
          <dd>{connector.connected_count}</dd>
        </div>
      </dl>
      {connector.status === "available" && connector.manage_path ? (
        <a className="button secondary" href={connector.manage_path}>
          {M.connectors.manageLink}
        </a>
      ) : (
        <p className="muted">{M.connectors.plannedHint}</p>
      )}
    </article>
  );
}
