"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { MissionStrip } from "../../components/MissionStrip";
import { PageHeader } from "../../components/PageHeader";
import { fetchWorkspaceConnectors } from "../../lib/api";
import { M } from "../../lib/messages";
import { useSession } from "../../lib/session";
import type { Connector, ConnectorRegistryResponse } from "../../lib/types";

type PanelStatus = "error" | "loading" | "missing" | "ready";

type ConnectorsPanelViewProps = {
  canManageSources?: boolean;
  data: ConnectorRegistryResponse | null;
  error: string | null;
  onRetry?: () => void;
  status: PanelStatus;
};

export default function ConnectorsPage() {
  const session = useSession();
  const workspaceId = session?.workspaceId ?? null;
  const workspaceRole =
    session?.workspaces.find((workspace) => workspace.id === workspaceId)?.role ?? null;
  const canManageSources = workspaceRole === "owner" || workspaceRole === "admin";
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
      <Link className="onboarding-return" href="/onboarding#source">
        <span aria-hidden="true">←</span>
        Открыть шаг настройки первых данных
      </Link>
      <PageHeader
        eyebrow={M.connectors.eyebrow}
        title={M.connectors.title}
        description="Выберите, откуда FounderOS будет брать факты о компании. Начните с одного источника — остальные можно добавить позже."
      />
      <ConnectorsPanelView
        canManageSources={canManageSources}
        data={data}
        error={error}
        onRetry={() => setReloadKey((current) => current + 1)}
        status={status}
      />
    </>
  );
}

export function ConnectorsPanelView({
  canManageSources = true,
  data,
  error,
  onRetry,
  status
}: ConnectorsPanelViewProps) {
  const recommended = data ? recommendedConnector(data.connectors) : null;

  return (
    <section className="panel connectors" aria-labelledby="connectors-title">
      <div className="section-header">
        <div>
          <span className="eyebrow">Карта источников</span>
          <h2 id="connectors-title">Ваши источники</h2>
        </div>
        {data && status === "ready" ? (
          <span className="badge source-count-badge">
            {data.summary.connected} из {data.summary.total} подключено
          </span>
        ) : null}
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
          <MissionStrip
            action={recommendedAction(recommended, canManageSources)}
            current={sourceMissionCurrent(data)}
            outcome={recommendedOutcome(recommended, canManageSources)}
            details={
              <>
                <p>
                  {M.connectors.boundaryNote} Без вашего явного действия FounderOS
                  ничего не отправит во внешний сервис.
                </p>
                {!canManageSources ? (
                  <p>
                    Настройку подключения выполняет владелец или администратор компании.
                  </p>
                ) : null}
              </>
            }
          />

          <div className="source-state-legend" aria-label="Состояния источников">
            <span>
              <i aria-hidden="true" className="source-state-dot source-state-dot--connected" />
              Подключён
            </span>
            <span>
              <i aria-hidden="true" className="source-state-dot source-state-dot--attention" />
              Нужно проверить
            </span>
            <span>
              <i aria-hidden="true" className="source-state-dot source-state-dot--available" />
              Можно подключить
            </span>
            <span>
              <i aria-hidden="true" className="source-state-dot source-state-dot--later" />
              Позже
            </span>
          </div>

          <div className="source-card-grid" aria-label={M.connectors.listLabel}>
            {data.connectors.map((connector) => (
              <ConnectorCard
                canManageSources={canManageSources}
                connector={connector}
                key={connector.provider}
              />
            ))}
          </div>
        </>
      ) : null}
    </section>
  );
}

function ConnectorCard({
  canManageSources,
  connector
}: {
  canManageSources: boolean;
  connector: Connector;
}) {
  const state = connectorState(connector);
  const statusLabel = connectorStateLabel(state);
  return (
    <article className={`work-item connector-card connector-card--${state}`}>
      <div className="connector-card-header">
        <span className={`connector-provider-mark connector-provider-mark--${connector.provider}`} aria-hidden="true">
          {connector.name.slice(0, 1)}
        </span>
        <div>
          <h3>{connector.name}</h3>
          <span className={`connector-state connector-state--${state}`}>
            {statusLabel}
          </span>
        </div>
      </div>
      <p className="connector-outcome">{connectorOutcome(connector)}</p>
      {state === "connected" ? (
        <p className="connector-card-fact">
          Активных подключений: <strong>{connector.connected_count}</strong>
        </p>
      ) : null}
      {connector.status === "available" && connector.manage_path ? (
        <a className={state === "connected" ? "button secondary" : "button"} href={connector.manage_path}>
          {connectorActionLabel(state, canManageSources)}
        </a>
      ) : (
        <p className="connector-later-note">Этот источник появится позже.</p>
      )}
    </article>
  );
}

type ConnectorVisualState = "attention" | "available" | "connected" | "later";

function connectorState(connector: Connector): ConnectorVisualState {
  if (connector.connected_count > 0) {
    return "connected";
  }
  if (connector.has_connection) {
    return "attention";
  }
  return connector.status === "available" ? "available" : "later";
}

function connectorStateLabel(state: ConnectorVisualState): string {
  if (state === "connected") {
    return "Подключён";
  }
  if (state === "attention") {
    return "Нужно проверить";
  }
  return state === "available" ? "Можно подключить" : "Позже";
}

function recommendedConnector(connectors: Connector[]): Connector | null {
  const attention = connectors.find(
    (connector) => connectorState(connector) === "attention"
  );
  if (attention) {
    return attention;
  }
  const github = connectors.find(
    (connector) =>
      connector.provider === "github" && connectorState(connector) === "available"
  );
  if (github) {
    return github;
  }
  return (
    connectors.find(
      (connector) => connectorState(connector) === "available"
    ) ??
    connectors.find((connector) => connectorState(connector) === "connected") ??
    null
  );
}

function sourceMissionCurrent(data: ConnectorRegistryResponse): string {
  if (data.summary.connected > 0) {
    return `${data.summary.connected} ${sourceWord(data.summary.connected)} уже даёт факты компании.`;
  }
  return "Источники ещё не подключены. Начните с одного.";
}

function recommendedAction(
  connector: Connector | null,
  canManageSources: boolean
): string {
  if (!connector) {
    return "Посмотрите, какие источники появятся дальше.";
  }
  const state = connectorState(connector);
  if (state === "connected") {
    return `Откройте ${connector.name} и проверьте сохранённые данные.`;
  }
  if (state === "attention") {
    return canManageSources
      ? `Откройте ${connector.name} и проверьте подключение.`
      : `Откройте ${connector.name} и сообщите администратору о подключении.`;
  }
  return canManageSources
    ? `Откройте ${connector.name} и выполните короткую настройку.`
    : `Откройте ${connector.name} и посмотрите, какие данные он добавит.`;
}

function connectorActionLabel(
  state: ConnectorVisualState,
  canManageSources: boolean
): string {
  if (state === "connected") {
    return "Открыть данные";
  }
  if (!canManageSources) {
    return "Посмотреть источник";
  }
  return state === "attention" ? "Проверить подключение" : "Настроить источник";
}

function recommendedOutcome(
  connector: Connector | null,
  canManageSources: boolean
): string {
  if (!connector) {
    return "Здесь появится подтверждённая картина компании.";
  }
  const state = connectorState(connector);
  if (state === "connected") {
    return connectorOpenOutcome(connector);
  }
  if (!canManageSources) {
    return state === "attention"
      ? "Поймёте, что нужно передать администратору."
      : "Поймёте, какие данные сможет подключить администратор.";
  }
  return state === "attention"
    ? "Поймёте, почему источник пока не даёт факты."
    : connectorOutcome(connector);
}

function connectorOutcome(connector: Connector): string {
  const outcomes: Partial<Record<Connector["provider"], string>> = {
    github: "Появятся задачи разработки, pull request и движение по репозиториям.",
    jira: "Появятся задачи, ответственные и текущие статусы работы.",
    gmail: "Появятся ключевые люди, компании и история соприкосновений.",
    drive: "Появятся документы и факты, которые уже хранит команда."
  };
  return outcomes[connector.provider] ?? connector.summary;
}

function connectorOpenOutcome(connector: Connector): string {
  const outcomes: Partial<Record<Connector["provider"], string>> = {
    github: "Увидите сохранённые задачи разработки и движение по репозиториям.",
    jira: "Увидите сохранённые задачи, ответственных и статусы работы.",
    gmail: "Увидите ключевых людей, компании и историю соприкосновений.",
    drive: "Увидите документы и факты, которые уже хранит команда."
  };
  return outcomes[connector.provider] ?? "Увидите уже сохранённые факты источника.";
}

function sourceWord(count: number): string {
  const mod100 = count % 100;
  const mod10 = count % 10;
  if (mod100 >= 11 && mod100 <= 14) {
    return "источников";
  }
  if (mod10 === 1) {
    return "источник";
  }
  if (mod10 >= 2 && mod10 <= 4) {
    return "источника";
  }
  return "источников";
}
