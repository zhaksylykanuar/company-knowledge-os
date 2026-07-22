"use client";

import Link from "next/link";
import {
  type RefObject,
  useCallback,
  useEffect,
  useReducer,
  useRef,
  useState
} from "react";

import { useAssistantSnapshotRegistration } from "../lib/assistant-snapshot";
import { ApiRequestError, fetchCompanyMap, fetchHeadquarters } from "../lib/api";
import {
  HeadquartersContractError,
  type HeadquartersMission,
  type HeadquartersPrecision,
  type HeadquartersPulseMetric,
  type HeadquartersSnapshotResponse,
  type HeadquartersSourceHealth
} from "../lib/headquarters";
import { useSession } from "../lib/session";
import type { CompanyMapResponse } from "../lib/types";
import { HeadquartersActionControl } from "./HeadquartersActionControl";
import { HeadquartersDecisionModal } from "./HeadquartersDecisionModal";
import { HeadquartersMissionDetail } from "./HeadquartersMissionDetail";
import { HeadquartersOnboardingModal } from "./HeadquartersOnboardingModal";
import { HeadquartersProfileDrawer } from "./HeadquartersProfileDrawer";
import { OverlayShell } from "./OverlayShell";

export type HeadquartersDashboardStatus =
  | "contract_error"
  | "error"
  | "forbidden"
  | "loading"
  | "missing"
  | "offline"
  | "ready";

type HeadquartersLoadState = {
  refreshError: boolean;
  refreshing: boolean;
  requestId: number;
  snapshot: HeadquartersSnapshotResponse | null;
  status: HeadquartersDashboardStatus;
  workspaceId: string | null;
};

type HeadquartersLoadAction =
  | { requestId: number; type: "clear" }
  | { requestId: number; type: "start"; workspaceId: string }
  | { requestId: number; type: "refresh_start"; workspaceId: string }
  | {
      requestId: number;
      snapshot: HeadquartersSnapshotResponse;
      type: "success";
      workspaceId: string;
    }
  | {
      requestId: number;
      status: Exclude<HeadquartersDashboardStatus, "loading" | "missing" | "ready">;
      type: "failure";
      workspaceId: string;
    }
  | { requestId: number; type: "refresh_failure"; workspaceId: string };

export type HeadquartersOverlay =
  | { kind: "coverage" }
  | { kind: "decision"; mission: HeadquartersMission }
  | { kind: "mission"; mission: HeadquartersMission; position: "priority" | "queue" }
  | { kind: "onboarding" }
  | { kind: "profile"; label: string; selector: string }
  | { kind: "pulse"; metric: HeadquartersPulseMetric }
  | { kind: "sources" };

const INITIAL_LOAD_STATE: HeadquartersLoadState = {
  refreshError: false,
  refreshing: false,
  requestId: 0,
  snapshot: null,
  status: "loading",
  workspaceId: null
};

export function reduceHeadquartersLoadState(
  state: HeadquartersLoadState,
  action: HeadquartersLoadAction
): HeadquartersLoadState {
  if (action.type === "clear") {
    return {
      refreshError: false,
      refreshing: false,
      requestId: action.requestId,
      snapshot: null,
      status: "missing",
      workspaceId: null
    };
  }
  if (action.type === "start") {
    return {
      refreshError: false,
      refreshing: false,
      requestId: action.requestId,
      snapshot: null,
      status: "loading",
      workspaceId: action.workspaceId
    };
  }
  if (action.type === "refresh_start") {
    if (state.workspaceId === action.workspaceId && state.snapshot !== null) {
      return {
        ...state,
        refreshError: false,
        refreshing: true,
        requestId: action.requestId,
        status: "ready"
      };
    }
    return {
      refreshError: false,
      refreshing: false,
      requestId: action.requestId,
      snapshot: null,
      status: "loading",
      workspaceId: action.workspaceId
    };
  }
  if (
    action.requestId !== state.requestId ||
    action.workspaceId !== state.workspaceId
  ) {
    return state;
  }
  if (action.type === "success") {
    return {
      ...state,
      refreshError: false,
      refreshing: false,
      snapshot: action.snapshot,
      status: "ready"
    };
  }
  if (action.type === "refresh_failure") {
    return state.snapshot !== null
      ? {
          ...state,
          refreshError: true,
          refreshing: false,
          status: "ready"
        }
      : {
          ...state,
          refreshError: false,
          refreshing: false,
          status: "error"
        };
  }
  return {
    ...state,
    refreshError: false,
    refreshing: false,
    snapshot: null,
    status: action.status
  };
}

export function onboardingIntentFromSearch(search: string): boolean {
  return new URLSearchParams(search).get("onboarding") === "1";
}

type HeadquartersOnboardingIntentEvent =
  | { search: string; type: "location" }
  | { type: "dismiss" }
  | { type: "workspace_changed" };

export function reduceHeadquartersOnboardingIntent(
  state: boolean,
  event: HeadquartersOnboardingIntentEvent
): boolean {
  if (event.type === "location") {
    return onboardingIntentFromSearch(event.search);
  }
  if (event.type === "dismiss") {
    return false;
  }
  return state;
}

export function resolveVisibleHeadquartersOverlay({
  dismissedOnboardingSnapshotId,
  onboardingIntent,
  requestedOverlay,
  snapshot
}: {
  dismissedOnboardingSnapshotId: string | null;
  onboardingIntent: boolean;
  requestedOverlay: HeadquartersOverlay | null;
  snapshot: HeadquartersSnapshotResponse;
}): HeadquartersOverlay | null {
  if (requestedOverlay?.kind === "onboarding") {
    return requestedOverlay;
  }
  if (requestedOverlay?.kind === "decision") {
    return requestedOverlay;
  }
  if (
    (!snapshot.onboarding.ready || onboardingIntent) &&
    dismissedOnboardingSnapshotId !== snapshot.snapshot.id
  ) {
    return { kind: "onboarding" };
  }
  return requestedOverlay;
}

export function HeadquartersDashboard() {
  const session = useSession();
  const registerAssistantSnapshot = useAssistantSnapshotRegistration();
  const workspaceId = session?.workspaceId ?? null;
  const workspaceName =
    session?.workspaces.find((workspace) => workspace.id === workspaceId)?.name ?? null;
  const [state, dispatch] = useReducer(
    reduceHeadquartersLoadState,
    INITIAL_LOAD_STATE
  );
  const requestIdRef = useRef(0);
  const [reloadKey, setReloadKey] = useState(0);
  const [onboardingIntent, dispatchOnboardingIntent] = useReducer(
    reduceHeadquartersOnboardingIntent,
    false
  );

  const refetchPreservingSnapshot = useCallback(async (): Promise<HeadquartersSnapshotResponse> => {
    if (!workspaceId) {
      throw new Error("Компания не выбрана.");
    }
    const requestWorkspaceId = workspaceId;
    const requestId = ++requestIdRef.current;
    dispatch({ requestId, type: "refresh_start", workspaceId: requestWorkspaceId });
    try {
      const snapshot = await fetchHeadquarters(requestWorkspaceId);
      if (snapshot.workspace.id !== requestWorkspaceId) {
        throw new HeadquartersContractError(
          "headquarters.workspace.id does not match selected workspace"
        );
      }
      dispatch({
        requestId,
        snapshot,
        type: "success",
        workspaceId: requestWorkspaceId
      });
      return snapshot;
    } catch (error) {
      dispatch({ requestId, type: "refresh_failure", workspaceId: requestWorkspaceId });
      throw error;
    }
  }, [workspaceId]);

  useEffect(() => {
    function syncOnboardingIntent() {
      dispatchOnboardingIntent({
        search: window.location.search,
        type: "location"
      });
    }
    syncOnboardingIntent();
    window.addEventListener("popstate", syncOnboardingIntent);
    return () => window.removeEventListener("popstate", syncOnboardingIntent);
  }, []);

  useEffect(() => {
    dispatchOnboardingIntent({ type: "workspace_changed" });
  }, [workspaceId]);

  useEffect(() => {
    const requestId = ++requestIdRef.current;
    if (!workspaceId) {
      dispatch({ requestId, type: "clear" });
      return;
    }

    const controller = new AbortController();
    dispatch({ requestId, type: "start", workspaceId });
    fetchHeadquarters(workspaceId, { signal: controller.signal })
      .then((snapshot) => {
        if (snapshot.workspace.id !== workspaceId) {
          dispatch({
            requestId,
            status: "contract_error",
            type: "failure",
            workspaceId
          });
          return;
        }
        dispatch({ requestId, snapshot, type: "success", workspaceId });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted || isAbortError(error)) {
          return;
        }
        dispatch({
          requestId,
          status: dashboardStatusFromError(error),
          type: "failure",
          workspaceId
        });
      });

    return () => controller.abort();
  }, [reloadKey, workspaceId]);

  const visibleStatus =
    workspaceId && state.workspaceId !== workspaceId ? "loading" : state.status;
  const visibleSnapshot =
    visibleStatus === "ready" && state.workspaceId === workspaceId
      ? state.snapshot
      : null;

  useEffect(() => {
    if (!registerAssistantSnapshot || !visibleSnapshot || !workspaceId) return;
    return registerAssistantSnapshot({
      refresh: refetchPreservingSnapshot,
      snapshot: visibleSnapshot,
      workspaceId
    });
  }, [
    refetchPreservingSnapshot,
    registerAssistantSnapshot,
    visibleSnapshot,
    workspaceId
  ]);

  return (
    <HeadquartersDashboardView
      isRefreshing={state.refreshing}
      onDecisionRefetch={refetchPreservingSnapshot}
      onRetry={() => setReloadKey((value) => value + 1)}
      onConsumeOnboardingIntent={() =>
        dispatchOnboardingIntent({ type: "dismiss" })
      }
      onboardingIntent={onboardingIntent}
      snapshot={visibleSnapshot}
      status={visibleStatus}
      refreshError={state.refreshError}
      workspaceName={workspaceName}
    />
  );
}

export function HeadquartersDashboardView({
  isRefreshing = false,
  onDecisionRefetch,
  onboardingIntent = false,
  onConsumeOnboardingIntent,
  onRetry,
  refreshError = false,
  snapshot,
  status,
  workspaceName = null
}: {
  isRefreshing?: boolean;
  onDecisionRefetch?: () => Promise<HeadquartersSnapshotResponse>;
  onboardingIntent?: boolean;
  onConsumeOnboardingIntent?: () => void;
  onRetry?: () => void;
  refreshError?: boolean;
  snapshot: HeadquartersSnapshotResponse | null;
  status: HeadquartersDashboardStatus;
  workspaceName?: string | null;
}) {
  const [requestedOverlay, setRequestedOverlay] =
    useState<HeadquartersOverlay | null>(null);
  const [dismissedOnboardingSnapshotId, setDismissedOnboardingSnapshotId] =
    useState<string | null>(null);
  const backgroundRef = useRef<HTMLDivElement>(null);
  const visibleOverlay = snapshot
    ? resolveVisibleHeadquartersOverlay({
        dismissedOnboardingSnapshotId,
        onboardingIntent,
        requestedOverlay,
        snapshot
      })
    : null;

  useEffect(() => {
    setRequestedOverlay(null);
    setDismissedOnboardingSnapshotId(null);
  }, [snapshot?.workspace.id]);

  if (status !== "ready" || snapshot === null) {
    return (
      <HeadquartersState
        onRetry={onRetry}
        status={status === "ready" ? "contract_error" : status}
        workspaceName={workspaceName}
      />
    );
  }
  const snapshotId = snapshot.snapshot.id;

  function closeVisibleOverlay() {
    if (visibleOverlay?.kind === "onboarding") {
      setDismissedOnboardingSnapshotId(snapshotId);
      onConsumeOnboardingIntent?.();
      clearOnboardingIntentFromLocation();
    }
    setRequestedOverlay(null);
  }

  function finishOnboarding() {
    closeVisibleOverlay();
    onRetry?.();
  }

  return (
    <section className="headquarters" aria-labelledby="headquarters-title">
      <div className="headquarters-surface" ref={backgroundRef}>
        <div className="headquarters-command-deck">
          <header className="headquarters-intro">
            <div>
              <span className="eyebrow">Живой штаб</span>
              <h1 id="headquarters-title">{snapshot.workspace.name}</h1>
            </div>
            <div className="headquarters-intro-meta">
              <p>Один подтверждённый ход — затем вся картина по запросу.</p>
              <HeadquartersControls
                onOpenCoverage={() => setRequestedOverlay({ kind: "coverage" })}
                onOpenOnboarding={() =>
                  setRequestedOverlay({ kind: "onboarding" })
                }
                onOpenSources={() => setRequestedOverlay({ kind: "sources" })}
                snapshot={snapshot}
              />
            </div>
          </header>

          <PriorityStage
            onOpenDecision={(mission) =>
              setRequestedOverlay({ kind: "decision", mission })
            }
            onOpen={(mission) =>
              setRequestedOverlay({
                kind: "mission",
                mission,
                position: "priority"
              })
            }
            snapshot={snapshot}
          />

          <PulseRow
            metrics={snapshot.pulse}
            onOpen={(metric) => setRequestedOverlay({ kind: "pulse", metric })}
          />

          <div className="headquarters-lower-deck">
            <MissionQueue
              missions={snapshot.queue}
              onOpen={(mission) =>
                setRequestedOverlay({
                  kind: "mission",
                  mission,
                  position: "queue"
                })
              }
            />
            <CurrentSignals snapshot={snapshot} />
          </div>

          <TruthStrip
            isRefreshing={isRefreshing}
            onOpenCoverage={() => setRequestedOverlay({ kind: "coverage" })}
            onRetry={onRetry}
            snapshot={snapshot}
          />
          {refreshError ? (
            <p className="headquarters-refresh-warning" role="status">
              Последнее обновление не удалось; показан предыдущий подтверждённый снимок.
            </p>
          ) : null}
        </div>
      </div>

      {visibleOverlay?.kind === "onboarding" ? (
        <HeadquartersOnboardingModal
          backgroundRef={backgroundRef}
          key={`onboarding:${snapshot.snapshot.id}`}
          onClose={closeVisibleOverlay}
          onFinish={finishOnboarding}
          onRetry={onRetry}
          snapshot={snapshot}
        />
      ) : visibleOverlay?.kind === "decision" ? (
        <HeadquartersDecisionModal
          backgroundRef={backgroundRef}
          mission={visibleOverlay.mission}
          onClose={closeVisibleOverlay}
          onRefetch={
            onDecisionRefetch ??
            (async () => {
              onRetry?.();
              throw new Error("Результат обновления Штаба пока не подтверждён.");
            })
          }
          snapshot={snapshot}
        />
      ) : visibleOverlay ? (
        <HeadquartersDrawer
          backgroundRef={backgroundRef}
          key={overlayIdentity(visibleOverlay)}
          onClose={closeVisibleOverlay}
          onOpen={setRequestedOverlay}
          overlay={visibleOverlay}
          snapshot={snapshot}
        />
      ) : null}
    </section>
  );
}

function HeadquartersControls({
  onOpenCoverage,
  onOpenOnboarding,
  onOpenSources,
  snapshot
}: {
  onOpenCoverage: () => void;
  onOpenOnboarding: () => void;
  onOpenSources: () => void;
  snapshot: HeadquartersSnapshotResponse;
}) {
  const sourcesState =
    snapshot.sources.attention_count > 0
      ? "attention"
      : snapshot.sources.healthy === snapshot.sources.total
        ? "healthy"
        : "quiet";

  return (
    <div className="headquarters-command-actions">
      {!snapshot.onboarding.ready ? (
        <button
          aria-haspopup="dialog"
          className="headquarters-onboarding-launcher"
          onClick={onOpenOnboarding}
          type="button"
        >
          <span aria-hidden="true">◌</span>
          <span>
            <strong>
              Настройка {snapshot.onboarding.completed_required}/
              {snapshot.onboarding.required_total}
            </strong>
            <small>Продолжить запуск</small>
          </span>
        </button>
      ) : null}
      {snapshot.snapshot.partial ? (
        <button
          aria-haspopup="dialog"
          className="headquarters-partial-badge"
          onClick={onOpenCoverage}
          type="button"
        >
          Картина частичная · что недоступно?
        </button>
      ) : null}
      <button
        className="headquarters-source-health"
        data-state={sourcesState}
        onClick={onOpenSources}
        type="button"
      >
        <i aria-hidden="true" />
        <span>
          <strong>{snapshot.sources.healthy} из {snapshot.sources.total} радаров</strong>
          <small>
            {snapshot.sources.attention_count > 0
              ? `Нужно проверить: ${snapshot.sources.attention_count}`
              : "Состояние источников"}
          </small>
        </span>
      </button>
    </div>
  );
}

function PriorityStage({
  onOpenDecision,
  onOpen,
  snapshot
}: {
  onOpenDecision: (mission: HeadquartersMission) => void;
  onOpen: (mission: HeadquartersMission) => void;
  snapshot: HeadquartersSnapshotResponse;
}) {
  const mission = snapshot.priority;
  if (!mission) {
    return (
      <article className="headquarters-priority headquarters-priority--calm">
        <div className="headquarters-priority-topline">
          <span>Ход сейчас</span>
          <span>Спокойный режим</span>
        </div>
        <div className="headquarters-priority-copy">
          <h2>Подтверждённых приоритетов сейчас нет</h2>
          <p>Штаб продолжает наблюдать за доступным снимком и ничего не придумывает.</p>
        </div>
        {snapshot.onboarding.next_action ? (
          <HeadquartersActionControl action={snapshot.onboarding.next_action} />
        ) : null}
      </article>
    );
  }

  return (
    <article
      className="headquarters-priority"
      data-severity={mission.severity}
      data-trust={mission.trust_class}
    >
      <div className="headquarters-priority-topline">
        <span>Ход сейчас · №1</span>
        <span>{missionTrustLabel(mission)}</span>
      </div>
      <div className="headquarters-priority-copy">
        <div className="headquarters-priority-tags">
          <span>{severityLabel(mission.severity)}</span>
          {mission.source_keys.slice(0, 2).map((source) => (
            <span key={source}>{sourceLabel(source)}</span>
          ))}
        </div>
        <h2>{mission.title}</h2>
        <p>{mission.summary}</p>
      </div>
      <div className="headquarters-priority-actions">
        {mission.proposal_id ? (
          <button
            className="headquarters-primary-action"
            onClick={() => onOpenDecision(mission)}
            type="button"
          >
            <span>Открыть решение</span><span aria-hidden="true">→</span>
          </button>
        ) : (
          <HeadquartersActionControl action={mission.action} />
        )}
        <button
          className="headquarters-why-action"
          onClick={() => onOpen(mission)}
          type="button"
        >
          Почему это №1?
          <span aria-hidden="true">↗</span>
        </button>
        {!mission.action.enabled && mission.action.disabled_reason ? (
          <span className="headquarters-priority-disabled">
            {mission.action.disabled_reason}
          </span>
        ) : null}
      </div>
    </article>
  );
}

function PulseRow({
  metrics,
  onOpen
}: {
  metrics: HeadquartersSnapshotResponse["pulse"];
  onOpen: (metric: HeadquartersPulseMetric) => void;
}) {
  return (
    <section className="headquarters-pulse" aria-label="Пульс компании">
      {metrics.map((metric, index) => (
        <button
          className="headquarters-pulse-card"
          data-key={metric.key}
          key={metric.key}
          onClick={() => onOpen(metric)}
          type="button"
        >
          <span className="headquarters-pulse-index">0{index + 1}</span>
          <span className="headquarters-pulse-value">
            {formatMetric(metric.value, metric.precision)}
          </span>
          <span className="headquarters-pulse-label">{metric.label}</span>
          <span className="headquarters-pulse-open" aria-hidden="true">→</span>
        </button>
      ))}
    </section>
  );
}

function MissionQueue({
  missions,
  onOpen
}: {
  missions: HeadquartersMission[];
  onOpen: (mission: HeadquartersMission) => void;
}) {
  return (
    <section className="headquarters-queue" aria-labelledby="headquarters-queue-title">
      <header className="headquarters-section-header">
        <div>
          <span className="eyebrow">Следом</span>
          <h2 id="headquarters-queue-title">Очередь ходов</h2>
        </div>
        <span>{missions.length}/2</span>
      </header>
      {missions.length > 0 ? (
        <ol>
          {missions.slice(0, 2).map((mission, index) => (
            <li key={mission.id}>
              <button
                data-mission-id={mission.id}
                data-reference-id={mission.reference_id}
                onClick={() => onOpen(mission)}
                type="button"
              >
                <span className="headquarters-queue-number">0{index + 2}</span>
                <span className="headquarters-queue-copy">
                  <strong>{mission.title}</strong>
                  <small>{mission.next_step}</small>
                </span>
                <span className="headquarters-queue-severity" data-severity={mission.severity}>
                  {severityLabel(mission.severity)}
                </span>
                <span aria-hidden="true">→</span>
              </button>
            </li>
          ))}
        </ol>
      ) : (
        <div className="headquarters-empty-panel">
          <strong>Следующих ходов нет</strong>
          <span>Штаб не создаёт очередь без подтверждённых оснований.</span>
        </div>
      )}
    </section>
  );
}

function CurrentSignals({ snapshot }: { snapshot: HeadquartersSnapshotResponse }) {
  const items = snapshot.changes.items.slice(0, 3);
  return (
    <section className="headquarters-signals" aria-labelledby="headquarters-signals-title">
      <header className="headquarters-section-header">
        <div>
          <span className="eyebrow">Текущий снимок</span>
          <h2 id="headquarters-signals-title">Сигналы</h2>
        </div>
        <span>{items.length}/3</span>
      </header>
      {items.length > 0 ? (
        <ol>
          {items.map((item) => {
            const occurredAt = formatSnapshotTime(item.occurred_at);
            return (
              <li key={item.id}>
                <Link href={item.target}>
                  <span className="headquarters-signal-mark" data-kind={item.kind} aria-hidden="true">
                    {changeIcon(item.kind)}
                  </span>
                  <span>
                    <strong>{item.title}</strong>
                    <small>{item.summary}</small>
                  </span>
                  {occurredAt ? (
                    <time dateTime={item.occurred_at ?? undefined}>{occurredAt}</time>
                  ) : (
                    <span className="headquarters-signal-time">Дата не подтверждена</span>
                  )}
                </Link>
              </li>
            );
          })}
        </ol>
      ) : (
        <div className="headquarters-empty-panel">
          <strong>Новых подтверждённых сигналов нет</strong>
          <span>Это состояние текущего снимка, а не история с прошлого визита.</span>
        </div>
      )}
    </section>
  );
}

function TruthStrip({
  isRefreshing,
  onOpenCoverage,
  onRetry,
  snapshot
}: {
  isRefreshing: boolean;
  onOpenCoverage: () => void;
  onRetry?: () => void;
  snapshot: HeadquartersSnapshotResponse;
}) {
  return (
    <footer
      className="headquarters-truth-strip"
      data-partial={snapshot.snapshot.partial ? "true" : "false"}
    >
      <span className="headquarters-truth-state" aria-hidden="true">
        {snapshot.snapshot.partial ? "!" : "✓"}
      </span>
      <span>
        <strong>
          {snapshot.snapshot.partial ? "Картина собрана частично" : "Текущий снимок проверен"}
        </strong>
        <small>Собрано {formatDateTime(snapshot.snapshot.as_of)}</small>
      </span>
      <div>
        <button onClick={onOpenCoverage} type="button">
          {snapshot.snapshot.partial ? "Что недоступно" : "Как собран снимок"}
        </button>
        {onRetry ? (
          <button disabled={isRefreshing} onClick={onRetry} type="button">
            {isRefreshing ? "Обновляем…" : "Обновить"}
          </button>
        ) : null}
      </div>
    </footer>
  );
}

function HeadquartersDrawer({
  backgroundRef,
  onClose,
  onOpen,
  overlay,
  snapshot
}: {
  backgroundRef: RefObject<HTMLDivElement | null>;
  onClose: () => void;
  onOpen: (overlay: HeadquartersOverlay) => void;
  overlay: HeadquartersOverlay;
  snapshot: HeadquartersSnapshotResponse;
}) {
  const title = overlayTitle(overlay);
  return (
    <OverlayShell
      backgroundRef={backgroundRef}
      label={title}
      mode="drawer"
      onClose={onClose}
    >
      {overlay.kind === "mission" ? (
        <HeadquartersMissionDetail
          mission={overlay.mission}
          onOpenDecision={(mission) => onOpen({ kind: "decision", mission })}
          onOpenProfile={(selector, label) =>
            onOpen({ kind: "profile", label, selector })
          }
          position={overlay.position}
        />
      ) : null}
      {overlay.kind === "profile" ? (
        <HeadquartersProfileLoader
          selector={overlay.selector}
          workspaceId={snapshot.workspace.id}
        />
      ) : null}
      {overlay.kind === "pulse" ? <PulseDrawer metric={overlay.metric} /> : null}
      {overlay.kind === "sources" ? <SourcesDrawer snapshot={snapshot} /> : null}
      {overlay.kind === "coverage" ? <CoverageDrawer snapshot={snapshot} /> : null}
    </OverlayShell>
  );
}

function HeadquartersProfileLoader({
  selector,
  workspaceId
}: {
  selector: string;
  workspaceId: string;
}) {
  const [data, setData] = useState<CompanyMapResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    setData(null);
    setError(null);
    fetchCompanyMap(workspaceId, { signal: controller.signal })
      .then((response) => {
        if (response.workspace_id !== workspaceId) {
          setError("Сервер вернул профиль из другой компании.");
          return;
        }
        setData(response);
      })
      .catch((caught: unknown) => {
        if (controller.signal.aborted) return;
        setError(
          caught instanceof Error
            ? caught.message
            : "Не удалось загрузить точный профиль."
        );
      });
    return () => controller.abort();
  }, [selector, workspaceId]);

  if (error) {
    return (
      <div className="headquarters-profile-state" role="alert">
        <strong>Профиль не загружен</strong><p>{error}</p>
      </div>
    );
  }
  if (!data) {
    return <p className="headquarters-profile-state" aria-busy="true">Загружаем точный профиль…</p>;
  }
  return <HeadquartersProfileDrawer data={data} selector={selector} />;
}

function PulseDrawer({ metric }: { metric: HeadquartersPulseMetric }) {
  return (
    <div className="headquarters-drawer-content">
      <div className="headquarters-drawer-metric">
        <strong>{formatMetric(metric.value, metric.precision)}</strong>
        <span>{precisionLabel(metric.precision)}</span>
      </div>
      <p className="headquarters-drawer-lead">
        {metric.value === 0 || metric.value === null
          ? metric.empty_state
          : "Показатель рассчитан сервером из текущего согласованного снимка."}
      </p>
      <HeadquartersActionControl action={metric.action} />
      {!metric.action.enabled && metric.action.disabled_reason ? (
        <p className="headquarters-disabled-reason">{metric.action.disabled_reason}</p>
      ) : null}
    </div>
  );
}

function SourcesDrawer({ snapshot }: { snapshot: HeadquartersSnapshotResponse }) {
  return (
    <div className="headquarters-drawer-content">
      <p className="headquarters-drawer-lead">
        Здоровы {snapshot.sources.healthy} из {snapshot.sources.total}. Здесь показано состояние локальных данных, а не обещание live-доступа к провайдеру.
      </p>
      <div className="headquarters-source-list">
        {snapshot.sources.items.map((source) => (
          <SourceHealthCard key={source.key} source={source} />
        ))}
      </div>
    </div>
  );
}

function SourceHealthCard({ source }: { source: HeadquartersSourceHealth }) {
  return (
    <article className="headquarters-source-card" data-state={source.primary_state}>
      <header>
        <span className="headquarters-source-dot" aria-hidden="true" />
        <div><strong>{source.name}</strong><small>{sourceStateLabel(source.primary_state)}</small></div>
        <span>{source.record_count}</span>
      </header>
      <dl>
        <div><dt>Данные</dt><dd>{sourceDataLabel(source.data)}</dd></div>
        <div><dt>Свежесть</dt><dd>{freshnessLabel(source.freshness)}</dd></div>
        <div><dt>Последняя попытка</dt><dd>{formatDateTime(source.last_attempt_at)}</dd></div>
        <div><dt>Последний успех</dt><dd>{formatDateTime(source.last_success_at)}</dd></div>
        <div><dt>Свежи до</dt><dd>{formatDateTime(source.fresh_until)}</dd></div>
      </dl>
      {source.attention_reason ? (
        <p className="headquarters-source-attention">
          {sourceAttentionLabel(source.attention_reason)}
        </p>
      ) : null}
      {source.blocker ? <p>{source.blocker}</p> : null}
      <HeadquartersActionControl action={source.next_action} />
    </article>
  );
}

function CoverageDrawer({ snapshot }: { snapshot: HeadquartersSnapshotResponse }) {
  return (
    <div className="headquarters-drawer-content">
      <p className="headquarters-drawer-lead">
        Все блоки относятся к одному read-only снимку. Недоступные данные не заменяются нулями или догадками.
      </p>
      <div className="headquarters-coverage-list">
        {snapshot.snapshot.coverage.map((item) => (
          <div data-state={item.status} key={item.key}>
            <span>{coverageLabel(item.key)}</span>
            <strong>{coverageStateLabel(item.status)}</strong>
            {item.warning ? <small>{item.warning}</small> : null}
          </div>
        ))}
      </div>
      {snapshot.snapshot.warnings.length > 0 ? (
        <ul className="headquarters-warning-list">
          {snapshot.snapshot.warnings.map((warning) => <li key={warning}>{warning}</li>)}
        </ul>
      ) : null}
      <p className="headquarters-boundary-note">
        Этот просмотр не вызывает провайдеров, LLM или внешние записи.
      </p>
    </div>
  );
}

function HeadquartersState({
  onRetry,
  status,
  workspaceName
}: {
  onRetry?: () => void;
  status: Exclude<HeadquartersDashboardStatus, "ready">;
  workspaceName: string | null;
}) {
  const content = stateContent(status);
  return (
    <section
      aria-busy={status === "loading"}
      aria-live="polite"
      className="headquarters headquarters--state"
    >
      <header className="headquarters-intro">
        <div>
          <span className="eyebrow">Живой штаб</span>
          <h1>{workspaceName ?? "Штаб компании"}</h1>
        </div>
        <p>{content.description}</p>
      </header>
      <div className="headquarters-state-card" data-state={status}>
        <span className="headquarters-state-mark" aria-hidden="true">
          {status === "loading" ? "" : content.icon}
        </span>
        <div><h2>{content.title}</h2><p>{content.description}</p></div>
        {status === "missing" ? (
          <Link className="headquarters-primary-action" href="/onboarding">
            <span>Выбрать компанию</span><span aria-hidden="true">→</span>
          </Link>
        ) : status !== "loading" && status !== "forbidden" && onRetry ? (
          <button className="headquarters-primary-action" onClick={onRetry} type="button">
            <span>Повторить</span><span aria-hidden="true">↻</span>
          </button>
        ) : null}
      </div>
      <div className="headquarters-state-skeleton" aria-hidden="true">
        <span /><span /><span />
      </div>
    </section>
  );
}

function dashboardStatusFromError(
  error: unknown
): Exclude<HeadquartersDashboardStatus, "loading" | "missing" | "ready"> {
  if (error instanceof ApiRequestError && error.status === 403) return "forbidden";
  if (error instanceof HeadquartersContractError) return "contract_error";
  if (error instanceof TypeError) return "offline";
  return "error";
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

function stateContent(status: Exclude<HeadquartersDashboardStatus, "ready">) {
  if (status === "loading") {
    return { description: "Собираем один согласованный снимок компании.", icon: "", title: "Штаб просыпается" };
  }
  if (status === "missing") {
    return { description: "Сначала выберите рабочее пространство компании.", icon: "+", title: "Нужна компания" };
  }
  if (status === "forbidden") {
    return { description: "У этого аккаунта нет доступа к выбранному штабу.", icon: "×", title: "Доступ закрыт" };
  }
  if (status === "offline") {
    return { description: "Локальный FounderOS сейчас не отвечает. Проверьте runtime и попробуйте снова.", icon: "↯", title: "Нет связи с системой" };
  }
  if (status === "contract_error") {
    return { description: "Ответ не прошёл безопасную проверку и поэтому не показан.", icon: "!", title: "Картина не подтверждена" };
  }
  return { description: "Не удалось собрать штаб. Старые данные не показаны как актуальные.", icon: "!", title: "Штаб временно недоступен" };
}

function overlayTitle(overlay: HeadquartersOverlay): string {
  if (overlay.kind === "coverage") return "Как собран снимок";
  if (overlay.kind === "decision") return overlay.mission.title;
  if (overlay.kind === "onboarding") return "Запуск компании";
  if (overlay.kind === "profile") return overlay.label;
  if (overlay.kind === "sources") return "Радары компании";
  if (overlay.kind === "pulse") return overlay.metric.label;
  return overlay.mission.title;
}

function overlayIdentity(overlay: HeadquartersOverlay): string {
  if (overlay.kind === "mission") {
    return `${overlay.kind}:${overlay.position}:${overlay.mission.id}`;
  }
  if (overlay.kind === "pulse") {
    return `${overlay.kind}:${overlay.metric.key}`;
  }
  if (overlay.kind === "profile") {
    return `${overlay.kind}:${overlay.selector}`;
  }
  if (overlay.kind === "decision") {
    return `${overlay.kind}:${overlay.mission.id}`;
  }
  return overlay.kind;
}

function clearOnboardingIntentFromLocation(): void {
  if (typeof window === "undefined") {
    return;
  }
  const url = new URL(window.location.href);
  if (!url.searchParams.has("onboarding")) {
    return;
  }
  url.searchParams.delete("onboarding");
  window.history.replaceState(null, "", `${url.pathname}${url.search}${url.hash}`);
}

function formatMetric(value: number | null, precision: HeadquartersPrecision): string {
  if (value === null || precision === "unavailable") return "—";
  return precision === "at_least" ? `≥${value}` : String(value);
}

function precisionLabel(precision: HeadquartersPrecision): string {
  if (precision === "at_least") return "не меньше";
  if (precision === "unavailable") return "нет подтверждённых данных";
  return "точное значение";
}

function severityLabel(severity: HeadquartersMission["severity"]): string {
  const labels: Record<HeadquartersMission["severity"], string> = {
    critical: "Критично",
    high: "Высокий приоритет",
    info: "Информация",
    low: "Низкий приоритет",
    medium: "Средний приоритет",
    unknown: "Без оценки"
  };
  return labels[severity];
}

function missionTrustLabel(mission: HeadquartersMission): string {
  return mission.trust_class === "verified_canonical"
    ? `${mission.evidence_refs.length} проверенных оснований`
    : "Агрегатный сигнал";
}

function sourceLabel(source: string): string {
  const labels: Record<string, string> = {
    drive: "Drive",
    github: "GitHub",
    gmail: "Gmail",
    internal: "FounderOS",
    jira: "Jira"
  };
  return labels[source] ?? "Источник";
}

function sourceAttentionLabel(reason: string): string {
  const labels: Record<string, string> = {
    no_data: "Источник подключён, но подтверждённых данных пока нет.",
    partial_data: "Источник передал только часть ожидаемых данных.",
    read_failed: "Последняя попытка чтения завершилась ошибкой.",
    stale_data: "Данные источника вышли за подтверждённое окно свежести."
  };
  return labels[reason] ?? "Источник требует проверки.";
}

function sourceStateLabel(state: HeadquartersSourceHealth["primary_state"]): string {
  const labels: Record<HeadquartersSourceHealth["primary_state"], string> = {
    failed: "Ошибка чтения",
    healthy: "Готов",
    no_data: "Нет данных",
    partial: "Частично",
    setup: "Не настроен",
    stale: "Устарел"
  };
  return labels[state];
}

function sourceDataLabel(state: HeadquartersSourceHealth["data"]): string {
  if (state === "available") return "доступны";
  if (state === "partial") return "частично";
  return "нет";
}

function freshnessLabel(state: HeadquartersSourceHealth["freshness"]): string {
  if (state === "fresh") return "свежие";
  if (state === "stale") return "устарели";
  return "неизвестно";
}

function coverageLabel(key: HeadquartersSnapshotResponse["snapshot"]["coverage"][number]["key"]): string {
  const labels = {
    company_world: "Люди и связи",
    decisions: "Решения",
    identity: "Компания",
    sources: "Источники"
  } as const;
  return labels[key];
}

function coverageStateLabel(status: "complete" | "partial" | "unavailable"): string {
  if (status === "complete") return "Готово";
  if (status === "partial") return "Частично";
  return "Недоступно";
}

function formatDateTime(value: string | null): string {
  if (!value) return "Нет подтверждённой даты";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "Нет подтверждённой даты";
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    month: "short"
  }).format(parsed);
}

function formatSnapshotTime(value: string | null): string | null {
  if (!value) return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return null;
  return new Intl.DateTimeFormat("ru-RU", { day: "2-digit", month: "short" }).format(parsed);
}

function changeIcon(kind: HeadquartersSnapshotResponse["changes"]["items"][number]["kind"]): string {
  if (kind === "proposal") return "!";
  if (kind === "relationship") return "↔";
  return "●";
}
