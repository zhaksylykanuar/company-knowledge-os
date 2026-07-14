"use client";

import { useEffect, useRef, useState } from "react";

import {
  fetchGitHubConnectionStatus,
  fetchGitHubRepositories,
  runGitHubAppLiveSync
} from "../lib/api";
import { M, T } from "../lib/messages";
import {
  canAdministerSelectedWorkspace,
  useSession
} from "../lib/session";
import type {
  GitHubAppLiveSyncResponse,
  GitHubConnectionStatusResponse,
  GitHubRepositoryRead,
  GitHubRepositoryListResponse
} from "../lib/types";
import { EmptyState } from "./EmptyState";
import { ErrorState } from "./ErrorState";
import { LoadingState } from "./LoadingState";
import { MiniHint, MissionStrip } from "./MissionStrip";
import { SourceLink } from "./SourceLink";
import { StatusCard } from "./StatusCard";

const REPOSITORY_PREVIEW_LIMIT = 8;

type ProductConnectState = "loading" | "ready" | "error" | "missing";
type LiveSyncState =
  | "idle"
  | "syncing"
  | "pending"
  | "partial"
  | "success"
  | "error";
type RepositoryFocusFilter =
  | "active"
  | "all"
  | "archived"
  | "private"
  | "with_evidence";
type RepositorySyncStatus = {
  error: string | null;
  result: GitHubAppLiveSyncResponse | null;
  state: LiveSyncState;
};
type GitHubRealReadReadiness = {
  appEnvConfigured: boolean;
  blockers: string[];
  hasAppInstallationConnection: boolean;
  installationConnected: boolean;
  localRepositoryCount: number;
  localRepositorySurfaceAvailable: boolean;
  nextStep: string;
  ready: boolean;
};

type GitHubProductConnectPanelProps = {
  onSyncComplete?: () => void;
};

type GitHubProductConnectPanelViewProps = {
  canAdminister?: boolean;
  connectionStatus: GitHubConnectionStatusResponse | null;
  error: string | null;
  onRepositoryFocusChange?: (filter: RepositoryFocusFilter) => void;
  onRepositorySelect?: (repositoryFullName: string) => void;
  onRetry?: () => void;
  onRunRepositorySync?: (repositoryFullName: string) => void;
  repositoryFocus?: RepositoryFocusFilter;
  repositorySync: Record<string, RepositorySyncStatus>;
  repositories: GitHubRepositoryListResponse | null;
  selectedRepository?: string | null;
  state: ProductConnectState;
};

export function GitHubProductConnectPanel({
  onSyncComplete
}: GitHubProductConnectPanelProps = {}) {
  const session = useSession();
  const workspaceId = session?.workspaceId ?? null;
  const canAdminister = canAdministerSelectedWorkspace(
    session?.workspaces ?? [],
    workspaceId
  );
  const [connectionStatus, setConnectionStatus] =
    useState<GitHubConnectionStatusResponse | null>(null);
  const [repositories, setRepositories] =
    useState<GitHubRepositoryListResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [repositorySync, setRepositorySync] = useState<
    Record<string, RepositorySyncStatus>
  >({});
  const [repositoryFocus, setRepositoryFocus] =
    useState<RepositoryFocusFilter>("all");
  const [selectedRepository, setSelectedRepository] = useState<string | null>(
    null
  );
  const [state, setState] = useState<ProductConnectState>("loading");
  const syncInFlightRef = useRef(false);

  useEffect(() => {
    if (!workspaceId) {
      setConnectionStatus(null);
      setRepositories(null);
      setSelectedRepository(null);
      setError(null);
      setState("missing");
      return;
    }

    let cancelled = false;
    setError(null);
    setState("loading");
    Promise.all([
      fetchGitHubConnectionStatus(workspaceId),
      fetchGitHubRepositories(workspaceId)
    ])
      .then(([status, repositoryList]) => {
        if (cancelled) {
          return;
        }
        setConnectionStatus(status);
        setRepositories(repositoryList);
        setSelectedRepository((current) =>
          chooseAvailableRepository(repositoryList.repositories, current)
        );
        setState("ready");
      })
      .catch((caught: unknown) => {
        if (cancelled) {
          return;
        }
        setConnectionStatus(null);
        setRepositories(null);
        setSelectedRepository(null);
        setError(caught instanceof Error ? caught.message : M.common.requestFailed);
        setState("error");
      });

    return () => {
      cancelled = true;
    };
  }, [workspaceId, reloadKey]);

  function changeRepositoryFocus(filter: RepositoryFocusFilter) {
    const filteredRepositories = filterRepositoriesByFocus(
      repositories?.repositories ?? [],
      filter
    );
    setRepositoryFocus(filter);
    setSelectedRepository((current) =>
      chooseAvailableRepository(filteredRepositories, current)
    );
  }

  async function syncRepository(repositoryFullName: string) {
    const repository = repositoryFullName.trim();
    if (
      syncInFlightRef.current ||
      !workspaceId ||
      !canAdminister ||
      !connectionStatus?.app.configured ||
      connectionStatus?.status !== "connected" ||
      !connectionStatus.connection_id ||
      connectionStatus.connection_method !== "github_app_installation" ||
      !connectionStatus.has_connection_record ||
      !isRepositoryFullName(repository)
    ) {
      return;
    }

    syncInFlightRef.current = true;
    let completed = false;
    setRepositorySync((current) => ({
      ...current,
      [repository]: { error: null, result: null, state: "syncing" }
    }));
    try {
      const payload = await runGitHubAppLiveSync(workspaceId, {
        connection_id: connectionStatus.connection_id,
        repositories: [repository],
        include_issues: true,
        include_pull_requests: true
      });
      const resultState = classifyGitHubSyncState(payload.sync_job.status);
      setRepositorySync((current) => ({
        ...current,
        [repository]: { error: null, result: payload, state: resultState }
      }));
      if (shouldRefreshGitHubDataAfterSync(payload.sync_job.status)) {
        setReloadKey((current) => current + 1);
        completed = true;
      }
    } catch (caught: unknown) {
      setRepositorySync((current) => ({
        ...current,
        [repository]: {
          error: caught instanceof Error ? caught.message : M.common.requestFailed,
          result: null,
          state: "error"
        }
      }));
    } finally {
      syncInFlightRef.current = false;
    }

    if (completed) {
      onSyncComplete?.();
    }
  }

  return (
    <GitHubProductConnectPanelView
      canAdminister={canAdminister}
      connectionStatus={connectionStatus}
      error={error}
      onRepositoryFocusChange={changeRepositoryFocus}
      onRepositorySelect={setSelectedRepository}
      onRetry={() => setReloadKey((current) => current + 1)}
      onRunRepositorySync={canAdminister ? syncRepository : undefined}
      repositoryFocus={repositoryFocus}
      repositorySync={repositorySync}
      repositories={repositories}
      selectedRepository={selectedRepository}
      state={state}
    />
  );
}

export function GitHubProductConnectPanelView({
  canAdminister = true,
  connectionStatus,
  error,
  onRepositoryFocusChange,
  onRepositorySelect,
  onRetry,
  onRunRepositorySync,
  repositoryFocus = "all",
  repositorySync,
  repositories,
  selectedRepository,
  state
}: GitHubProductConnectPanelViewProps) {
  const appStatus = connectionStatus?.app ?? null;
  const appConnectionReady = Boolean(
    connectionStatus?.app.configured &&
      connectionStatus.status === "connected" &&
      connectionStatus.connection_id &&
      connectionStatus.connection_method === "github_app_installation" &&
      connectionStatus.has_connection_record
  );
  const repositoryItems = repositories?.repositories ?? [];
  const filteredRepositoryItems = filterRepositoriesByFocus(
    repositoryItems,
    repositoryFocus
  );
  const repositoryStats = repositoryFocusStats(repositoryItems);
  const selectedRepositoryItem = chooseSelectedRepository(
    filteredRepositoryItems,
    selectedRepository
  );
  const selectedSync = selectedRepositoryItem
    ? repositorySync[selectedRepositoryItem.full_name] ?? idleSyncStatus()
    : idleSyncStatus();
  const globalSyncInProgress = Object.values(repositorySync).some(
    (sync) => sync.state === "syncing"
  );
  const selectedRepositoryValid = selectedRepositoryItem
    ? isRepositoryFullName(selectedRepositoryItem.full_name)
    : false;
  const canRunSelectedSync = Boolean(
    canAdminister &&
      appConnectionReady &&
      selectedRepositoryValid &&
      onRunRepositorySync &&
      !globalSyncInProgress
  );
  const hasAppInstallationRecord = Boolean(
    connectionStatus?.has_connection_record &&
      connectionStatus.connection_method === "github_app_installation"
  );
  const showSetupAction = Boolean(
    canAdminister &&
      appStatus?.setup_url &&
      !appConnectionReady &&
      !hasAppInstallationRecord
  );
  const showConnectionAttentionAction = Boolean(
    canAdminister && hasAppInstallationRecord && !appConnectionReady
  );

  return (
    <section
      aria-busy={state === "loading" || globalSyncInProgress}
      aria-labelledby="github-product-connect-title"
      className="panel github-product-connect github-command-center"
    >
      <div className="section-header">
        <div>
          <span className="eyebrow">{M.githubProductConnect.eyebrow}</span>
          <h2 id="github-product-connect-title">
            {M.githubProductConnect.title}
          </h2>
        </div>
        <span className="badge">{M.githubProductConnect.badgeReadOnly}</span>
      </div>

      <p className="muted github-command-intro">
        {M.githubProductConnect.description}
      </p>

      {state === "loading" ? (
        <LoadingState label={M.githubProductConnect.loading} />
      ) : null}

      {state === "missing" ? (
        <EmptyState
          description={M.githubProductConnect.noWorkspaceDescription}
          title={M.common.noWorkspaceTitle}
        />
      ) : null}

      {state === "error" ? (
        <>
          <ErrorState
            description={M.githubProductConnect.unavailableDescription}
            title={M.githubProductConnect.unavailableTitle}
          />
          <button className="button secondary" onClick={onRetry} type="button">
            {M.common.retry}
          </button>
          {error ? (
            <details className="github-command-error-details">
              <summary>{M.githubProductConnect.errorDetails}</summary>
              <p>{error}</p>
            </details>
          ) : null}
        </>
      ) : null}

      {state === "ready" && connectionStatus && appStatus ? (
        <>
          <MissionStrip
            action={githubMissionAction({
              appConnectionReady,
              canAdminister,
              hasAppInstallationRecord,
              hasRepositories: repositoryItems.length > 0,
              setupAvailable: Boolean(appStatus.setup_url),
              syncPartial: selectedSync.state === "partial"
            })}
            current={githubMissionCurrent({
              appConnectionReady,
              canAdminister,
              hasAppInstallationRecord,
              hasRepositories: repositoryItems.length > 0,
              syncPartial: selectedSync.state === "partial",
              syncSucceeded: selectedSync.state === "success"
            })}
            details={<p>{M.githubProductConnect.missionSafeDetails}</p>}
            outcome={githubMissionOutcome({
              appConnectionReady,
              canAdminister,
              hasRepositories: repositoryItems.length > 0,
              syncPartial: selectedSync.state === "partial",
              syncSucceeded: selectedSync.state === "success"
            })}
          />

          {!canAdminister ? (
            <p className="muted github-command-role-note">
              {M.common.sourceAdminOnlyNote}
            </p>
          ) : null}

          <GitHubCommandFlow
            connected={appConnectionReady}
            repositorySelected={Boolean(selectedRepositoryItem)}
            synchronized={selectedSync.state === "success"}
          />

          <section
            aria-labelledby="github-command-metrics-title"
            className="github-command-metrics-section"
          >
            <div className="github-command-subheader">
              <h3 id="github-command-metrics-title">
                {M.githubProductConnect.metricsTitle}
              </h3>
              <MiniHint label={M.githubProductConnect.metricsHintLabel}>
                <p>{M.githubProductConnect.metricsHint}</p>
              </MiniHint>
            </div>
            <div
              aria-label={M.githubProductConnect.metricsLabel}
              className="github-command-metrics"
            >
              <GitHubMetric
                hint={githubAppDescription(connectionStatus)}
                label={M.githubProductConnect.connectionMetricTitle}
                tone={appConnectionReady ? "positive" : "attention"}
                value={
                  appConnectionReady
                    ? M.githubProductConnect.connectionMetricConnected
                    : M.githubProductConnect.connectionMetricAttention
                }
              />
              <GitHubMetric
                hint={T.githubLoadedRepositorySample(
                  repositoryItems.length,
                  repositories?.count ?? 0
                )}
                label={M.githubProductConnect.loadedMetricTitle}
                value={String(repositoryItems.length)}
              />
              <GitHubMetric
                hint={M.githubProductConnect.activeMetricHint}
                label={M.githubProductConnect.activeMetricTitle}
                value={String(repositoryStats.active)}
              />
              <GitHubMetric
                hint={M.githubProductConnect.lastSyncMetricHint}
                label={M.githubProductConnect.lastSyncMetricTitle}
                value={formatLastSync(connectionStatus.last_sync_at)}
              />
            </div>
          </section>

          {showSetupAction && appStatus.setup_url ? (
            <p className="github-command-primary-action">
              <SourceLink className="button" url={appStatus.setup_url}>
                {appConnectionReady
                  ? M.githubProductConnect.openSetupSettings
                  : M.githubProductConnect.openSetup}
              </SourceLink>
              <span className="muted">
                {appConnectionReady
                  ? M.githubProductConnect.repositoryAccessActionHint
                  : M.githubProductConnect.setupActionHint}
              </span>
              <button
                className="button secondary"
                onClick={onRetry}
                type="button"
              >
                {M.githubProductConnect.refreshConnection}
              </button>
            </p>
          ) : null}

          {showConnectionAttentionAction ? (
            <div className="github-command-primary-action">
              <button className="button" onClick={onRetry} type="button">
                {M.githubProductConnect.refreshConnection}
              </button>
              <span className="muted">
                {M.githubProductConnect.connectionAttentionActionHint}
              </span>
            </div>
          ) : null}

          <section
            aria-labelledby="github-repository-workbench-title"
            className="github-repository-workbench"
          >
            <div className="github-command-subheader">
              <div>
                <span className="eyebrow">
                  {M.githubProductConnect.repositoryWorkbenchEyebrow}
                </span>
                <h3 id="github-repository-workbench-title">
                  {M.githubProductConnect.repositoryWorkbenchTitle}
                </h3>
              </div>
              <p className="muted">
                {M.githubProductConnect.repositoryWorkbenchDescription}
              </p>
            </div>

            {repositoryItems.length === 0 ? (
              <EmptyState
                description={M.githubProductConnect.repositoryListEmptyDescription}
                title={M.githubProductConnect.repositoryListEmptyTitle}
              />
            ) : (
              <>
                <RepositoryFocusControl
                  activeFilter={repositoryFocus}
                  onChange={onRepositoryFocusChange}
                  repositories={repositoryItems}
                />

                {filteredRepositoryItems.length === 0 ? (
                  <p className="muted">
                    {M.githubProductConnect.repositoryListNoReposForFilter}
                  </p>
                ) : (
                  <RepositoryChooser
                    disabled={globalSyncInProgress}
                    onSelect={onRepositorySelect}
                    repositories={filteredRepositoryItems}
                    selectedRepository={selectedRepositoryItem?.full_name ?? null}
                  />
                )}

                {selectedRepositoryItem && canAdminister && appConnectionReady ? (
                  <div className="github-command-primary-action">
                    <button
                      className="button"
                      disabled={!canRunSelectedSync}
                      onClick={() =>
                        onRunRepositorySync?.(selectedRepositoryItem.full_name)
                      }
                      type="button"
                    >
                      {globalSyncInProgress
                        ? M.githubProductConnect.liveSyncRunning
                        : M.githubProductConnect.liveSyncRun}
                    </button>
                    <span className="muted">
                      {T.githubSelectedRepositoryAction(
                        selectedRepositoryItem.full_name
                      )}
                    </span>
                  </div>
                ) : null}

                {selectedRepositoryItem && !selectedRepositoryValid ? (
                  <p className="error-text">
                    {M.githubProductConnect.liveSyncRepositoryInvalid}
                  </p>
                ) : null}

                {selectedSync.state === "error" && !selectedSync.result ? (
                  <div className="github-sync-error">
                    <ErrorState
                      description={M.githubProductConnect.liveSyncFailedDescription}
                      title={M.githubProductConnect.liveSyncFailedTitle}
                    />
                    {selectedSync.error ? (
                      <details className="github-command-error-details">
                        <summary>{M.githubProductConnect.errorDetails}</summary>
                        <p>{selectedSync.error}</p>
                      </details>
                    ) : null}
                  </div>
                ) : null}

                {selectedSync.result ? (
                  <GitHubSyncReceipt
                    result={selectedSync.result}
                    state={classifyGitHubSyncState(
                      selectedSync.result.sync_job.status
                    )}
                  />
                ) : null}
              </>
            )}
          </section>

          <details className="github-command-technical">
            <summary>{M.githubProductConnect.technicalDetails}</summary>
            <div className="github-command-technical-body">
              <p className="muted">
                {M.githubProductConnect.technicalDescription}
              </p>

              <GitHubRealReadinessPanel
                connectionStatus={connectionStatus}
                repositories={repositories}
              />

              {!appStatus.configured && appStatus.missing_env.length > 0 ? (
                <section className="callout">
                  <strong>{M.githubProductConnect.missingEnvTitle}</strong>
                  <ul className="meta-list">
                    {appStatus.missing_env.map((name) => (
                      <li key={name}>{name}</li>
                    ))}
                  </ul>
                </section>
              ) : null}

              <dl className="github-command-facts">
                <div>
                  <dt>{M.githubProductConnect.tokenTitle}</dt>
                  <dd>
                    {appStatus.installation_tokens_persisted
                      ? M.common.yes
                      : M.common.no}
                  </dd>
                </div>
                <div>
                  <dt>{M.githubProductConnect.writeTitle}</dt>
                  <dd>
                    {appStatus.provider_writes_enabled
                      ? M.common.enabled
                      : M.common.notEnabled}
                  </dd>
                </div>
                <div>
                  <dt>{M.githubProductConnect.repositorySourceTitle}</dt>
                  <dd>{repositories?.source ?? M.common.unknown}</dd>
                </div>
              </dl>

              {canAdminister ? (
                <div className="actions-row">
                  <button
                    className="button secondary"
                    onClick={onRetry}
                    type="button"
                  >
                    {M.githubProductConnect.refreshConnection}
                  </button>
                </div>
              ) : null}

              {[
                ...connectionStatus.warnings,
                ...(repositories?.warnings ?? [])
              ].length > 0 ? (
                <ul className="meta-list" aria-label={M.common.warnings}>
                  {[
                    ...connectionStatus.warnings,
                    ...(repositories?.warnings ?? [])
                  ].map((warning) => (
                    <li key={warning}>{warning}</li>
                  ))}
                </ul>
              ) : null}
            </div>
          </details>
        </>
      ) : null}
    </section>
  );
}

function GitHubCommandFlow({
  connected,
  repositorySelected,
  synchronized
}: {
  connected: boolean;
  repositorySelected: boolean;
  synchronized: boolean;
}) {
  const steps = [
    {
      complete: connected,
      description: M.githubProductConnect.flowConnectionDescription,
      title: M.githubProductConnect.flowConnectionTitle
    },
    {
      complete: connected && repositorySelected,
      description: M.githubProductConnect.flowRepositoryDescription,
      title: M.githubProductConnect.flowRepositoryTitle
    },
    {
      complete: connected && repositorySelected && synchronized,
      description: M.githubProductConnect.flowFounderOSDescription,
      title: M.githubProductConnect.flowFounderOSTitle
    }
  ];
  const currentStep = steps.findIndex((step) => !step.complete);

  return (
    <ol aria-label={M.githubProductConnect.flowLabel} className="github-command-flow">
      {steps.map((step, index) => {
        const current = index === (currentStep === -1 ? steps.length - 1 : currentStep);
        return (
          <li
            aria-current={current ? "step" : undefined}
            className={`github-command-flow-step${
              step.complete ? " github-command-flow-step--complete" : ""
            }${current ? " github-command-flow-step--current" : ""}`}
            key={step.title}
          >
            <span className="github-command-flow-index" aria-hidden="true">
              {step.complete ? "✓" : index + 1}
            </span>
            <div>
              <strong>{step.title}</strong>
              <span>{step.description}</span>
            </div>
          </li>
        );
      })}
    </ol>
  );
}

function GitHubMetric({
  hint,
  label,
  tone,
  value
}: {
  hint: string;
  label: string;
  tone?: "attention" | "positive";
  value: string;
}) {
  return (
    <article
      className={`github-command-metric${
        tone ? ` github-command-metric--${tone}` : ""
      }`}
    >
      <span className="github-command-metric-label">{label}</span>
      <strong className="github-command-metric-value">{value}</strong>
      <span className="github-command-metric-hint">{hint}</span>
    </article>
  );
}

function RepositoryChooser({
  disabled,
  onSelect,
  repositories,
  selectedRepository
}: {
  disabled: boolean;
  onSelect?: (repositoryFullName: string) => void;
  repositories: GitHubRepositoryRead[];
  selectedRepository: string | null;
}) {
  const selected = selectedRepository
    ? repositories.find(
        (repository) => repository.full_name === selectedRepository
      )
    : null;
  const orderedRepositories = selected
    ? [
        selected,
        ...repositories.filter(
          (repository) => repository.full_name !== selected.full_name
        )
      ]
    : repositories;
  const previewRepositories = orderedRepositories.slice(
    0,
    REPOSITORY_PREVIEW_LIMIT
  );
  const remainingRepositories = orderedRepositories.slice(
    REPOSITORY_PREVIEW_LIMIT
  );

  return (
    <div className="github-repository-chooser">
      <div
        aria-label={M.githubProductConnect.repositoryListTitle}
        className="github-repository-grid"
        role="group"
      >
        {previewRepositories.map((repository) => (
          <RepositoryChoice
            disabled={disabled}
            key={repository.full_name}
            onSelect={onSelect}
            repository={repository}
            selected={selectedRepository === repository.full_name}
          />
        ))}
      </div>

      {remainingRepositories.length > 0 ? (
        <details className="github-repository-more">
          <summary>
            {T.githubShowMoreRepositories(remainingRepositories.length)}
          </summary>
          <div className="github-repository-grid">
            {remainingRepositories.map((repository) => (
              <RepositoryChoice
                disabled={disabled}
                key={repository.full_name}
                onSelect={onSelect}
                repository={repository}
                selected={selectedRepository === repository.full_name}
              />
            ))}
          </div>
        </details>
      ) : null}
    </div>
  );
}

function RepositoryChoice({
  disabled,
  onSelect,
  repository,
  selected
}: {
  disabled: boolean;
  onSelect?: (repositoryFullName: string) => void;
  repository: GitHubRepositoryRead;
  selected: boolean;
}) {
  return (
    <article
      className={`github-repository-choice${
        selected ? " github-repository-choice--selected" : ""
      }`}
    >
      <button
        aria-pressed={selected}
        className="github-repository-choice-main"
        disabled={disabled}
        onClick={() => onSelect?.(repository.full_name)}
        type="button"
      >
        <span className="github-repository-choice-copy">
          <strong>{repository.full_name}</strong>
          <span className="github-repository-badges">
            <span className="github-repository-badge">
              {repository.archived
                ? M.githubProductConnect.repositoryArchived
                : M.githubProductConnect.repositoryActive}
            </span>
            <span className="github-repository-badge">
              {repository.visibility || M.common.unknown}
            </span>
          </span>
          {repository.last_activity_at ? (
            <span className="muted">
              {T.githubRepositoryLastActivity(
                formatTimestamp(repository.last_activity_at)
              )}
            </span>
          ) : null}
        </span>
        <span className="github-repository-choice-state" aria-hidden="true">
          {selected ? "✓" : "→"}
        </span>
      </button>

      {repository.source_url ? (
        <div className="github-repository-actions">
          <SourceLink url={repository.source_url}>
            {M.common.openSource}
          </SourceLink>
        </div>
      ) : null}
    </article>
  );
}

function GitHubSyncReceipt({
  result,
  state
}: {
  result: GitHubAppLiveSyncResponse;
  state: Extract<
    LiveSyncState,
    "error" | "partial" | "pending" | "success"
  >;
}) {
  const receiptCopy =
    state === "success"
      ? {
          description: null,
          eyebrow: M.githubProductConnect.receiptEyebrow,
          title: M.githubProductConnect.liveSyncResultTitle
        }
      : state === "partial"
        ? {
            description: M.githubProductConnect.liveSyncPartialDescription,
            eyebrow: M.githubProductConnect.receiptPartialEyebrow,
            title: M.githubProductConnect.liveSyncPartialTitle
          }
        : state === "pending"
          ? {
              description: M.githubProductConnect.liveSyncPendingDescription,
              eyebrow: M.githubProductConnect.receiptPendingEyebrow,
              title: M.githubProductConnect.liveSyncPendingTitle
            }
          : {
              description: M.githubProductConnect.liveSyncResultFailedDescription,
              eyebrow: M.githubProductConnect.receiptErrorEyebrow,
              title: M.githubProductConnect.liveSyncResultFailedTitle
            };
  return (
    <section
      aria-label={M.githubProductConnect.liveSyncResultTitle}
      className={`github-sync-receipt github-sync-receipt--${state}`}
    >
      <div
        aria-atomic="true"
        aria-live="polite"
        className="github-sync-receipt-status"
        role="status"
      >
        <span className="eyebrow">{receiptCopy.eyebrow}</span>
        <h3>{receiptCopy.title}</h3>
        {receiptCopy.description ? (
          <p className="muted">{receiptCopy.description}</p>
        ) : null}
        <p>
          {T.githubAppLiveSyncResult(
            result.totals.repositories,
            result.totals.issues,
            result.totals.pull_requests,
            result.sync_job.status
          )}
        </p>
        <p className={state === "success" ? "success-text" : "muted"}>
          {M.githubProductConnect.liveSyncNoWrites}
        </p>
      </div>
      {result.warnings.length > 0 ? (
        <details className="github-sync-receipt-details">
          <summary>{M.githubProductConnect.receiptTechnicalDetails}</summary>
          <ul className="meta-list" aria-label={M.common.warnings}>
            {result.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </details>
      ) : null}
    </section>
  );
}

function GitHubRealReadinessPanel({
  connectionStatus,
  repositories
}: {
  connectionStatus: GitHubConnectionStatusResponse;
  repositories: GitHubRepositoryListResponse | null;
}) {
  const readiness = summarizeGitHubRealReadReadiness(connectionStatus, repositories);
  return (
    <section
      className="work-section"
      aria-label={M.githubProductConnect.realReadReadinessLabel}
    >
      <h3>{M.githubProductConnect.realReadReadinessTitle}</h3>
      <p className="muted">{M.githubProductConnect.realReadReadinessDescription}</p>
      <section className="grid" aria-label={M.githubProductConnect.realReadReadinessLabel}>
        <StatusCard
          description={M.githubProductConnect.realReadStatusDescription}
          title={M.githubProductConnect.realReadStatusTitle}
          value={
            readiness.ready
              ? M.githubProductConnect.realReadReady
              : M.githubProductConnect.realReadBlocked
          }
        />
        <StatusCard
          description={M.githubProductConnect.realReadEnvDescription}
          title={M.githubProductConnect.realReadEnvTitle}
          value={
            readiness.appEnvConfigured ? M.common.available : M.common.unavailable
          }
        />
        <StatusCard
          description={M.githubProductConnect.realReadInstallationDescription}
          title={M.githubProductConnect.realReadInstallationTitle}
          value={
            readiness.installationConnected ? M.common.available : M.common.unavailable
          }
        />
        <StatusCard
          description={M.githubProductConnect.realReadRepoSurfaceDescription}
          title={M.githubProductConnect.realReadRepoSurfaceTitle}
          value={String(readiness.localRepositoryCount)}
        />
      </section>
      {readiness.blockers.length > 0 ? (
        <section className="callout">
          <strong>{M.githubProductConnect.realReadBlockersTitle}</strong>
          <ul className="meta-list">
            {readiness.blockers.map((blocker) => (
              <li key={blocker}>{githubRealReadBlockerLabel(blocker)}</li>
            ))}
          </ul>
        </section>
      ) : null}
      <p className="muted">{readiness.nextStep}</p>
      <p className="muted">{M.githubProductConnect.realReadBoundary}</p>
    </section>
  );
}

function RepositoryFocusControl({
  activeFilter,
  onChange,
  repositories
}: {
  activeFilter: RepositoryFocusFilter;
  onChange?: (filter: RepositoryFocusFilter) => void;
  repositories: GitHubRepositoryRead[];
}) {
  const filters: RepositoryFocusFilter[] = [
    "all",
    "active",
    "archived",
    "private",
    "with_evidence"
  ];
  return (
    <div
      className="github-repository-filters"
      role="group"
      aria-label={M.githubProductConnect.repositoryFocusLabel}
    >
      {filters.map((filter) => (
        <button
          aria-pressed={activeFilter === filter}
          className={`segment${activeFilter === filter ? " active" : ""}`}
          key={filter}
          onClick={() => onChange?.(filter)}
          type="button"
        >
          {repositoryFocusLabel(filter)} · {repositoryFocusCount(repositories, filter)}
        </button>
      ))}
    </div>
  );
}

function repositoryFocusLabel(filter: RepositoryFocusFilter): string {
  switch (filter) {
    case "active":
      return M.githubProductConnect.repositoryFocusActive;
    case "archived":
      return M.githubProductConnect.repositoryFocusArchived;
    case "private":
      return M.githubProductConnect.repositoryFocusPrivate;
    case "with_evidence":
      return M.githubProductConnect.repositoryFocusWithEvidence;
    case "all":
    default:
      return M.githubProductConnect.repositoryFocusAll;
  }
}

function repositoryFocusCount(
  repositories: GitHubRepositoryRead[],
  filter: RepositoryFocusFilter
): number {
  return filterRepositoriesByFocus(repositories, filter).length;
}

function filterRepositoriesByFocus(
  repositories: GitHubRepositoryRead[],
  filter: RepositoryFocusFilter
): GitHubRepositoryRead[] {
  switch (filter) {
    case "active":
      return repositories.filter((repository) => !repository.archived);
    case "archived":
      return repositories.filter((repository) => repository.archived);
    case "private":
      return repositories.filter((repository) => repository.visibility === "private");
    case "with_evidence":
      return repositories.filter((repository) => repository.evidence_refs.length > 0);
    case "all":
    default:
      return repositories;
  }
}

function repositoryFocusStats(repositories: GitHubRepositoryRead[]) {
  return {
    active: filterRepositoriesByFocus(repositories, "active").length,
    archived: filterRepositoriesByFocus(repositories, "archived").length,
    private: filterRepositoriesByFocus(repositories, "private").length,
    withEvidence: filterRepositoriesByFocus(repositories, "with_evidence").length
  };
}

function chooseAvailableRepository(
  repositories: GitHubRepositoryRead[],
  current: string | null
): string | null {
  if (current && repositories.some((repository) => repository.full_name === current)) {
    return current;
  }
  return (
    repositories.find((repository) => !repository.archived)?.full_name ??
    repositories[0]?.full_name ??
    null
  );
}

function chooseSelectedRepository(
  repositories: GitHubRepositoryRead[],
  selectedRepository: string | null | undefined
): GitHubRepositoryRead | null {
  const selected = selectedRepository
    ? repositories.find(
        (repository) => repository.full_name === selectedRepository
      )
    : null;
  return (
    selected ??
    repositories.find((repository) => !repository.archived) ??
    repositories[0] ??
    null
  );
}

function idleSyncStatus(): RepositorySyncStatus {
  return { error: null, result: null, state: "idle" };
}

function summarizeGitHubRealReadReadiness(
  connectionStatus: GitHubConnectionStatusResponse,
  repositories: GitHubRepositoryListResponse | null
): GitHubRealReadReadiness {
  const appEnvConfigured = connectionStatus.app.configured;
  const hasAppInstallationConnection = Boolean(
    connectionStatus.connection_id &&
      connectionStatus.has_connection_record &&
      connectionStatus.connection_method === "github_app_installation"
  );
  const installationConnected =
    hasAppInstallationConnection && connectionStatus.status === "connected";
  const localRepositoryCount = repositories?.count ?? 0;
  const localRepositorySurfaceAvailable = localRepositoryCount > 0;

  const blockers: string[] = [];
  if (!appEnvConfigured) {
    blockers.push("github_app_env_incomplete");
  }
  if (!hasAppInstallationConnection) {
    blockers.push("github_app_installation_connection_missing");
  } else if (!installationConnected) {
    blockers.push("github_app_installation_connection_not_connected");
  }
  if (!localRepositorySurfaceAvailable) {
    blockers.push("local_repository_surface_empty");
  }

  const ready = blockers.length === 0;
  return {
    appEnvConfigured,
    blockers,
    hasAppInstallationConnection,
    installationConnected,
    localRepositoryCount,
    localRepositorySurfaceAvailable,
    nextStep: githubRealReadNextStep({
      appEnvConfigured,
      hasAppInstallationConnection,
      installationConnected,
      localRepositorySurfaceAvailable,
      ready
    }),
    ready
  };
}

function githubRealReadNextStep({
  appEnvConfigured,
  hasAppInstallationConnection,
  installationConnected,
  localRepositorySurfaceAvailable,
  ready
}: {
  appEnvConfigured: boolean;
  hasAppInstallationConnection: boolean;
  installationConnected: boolean;
  localRepositorySurfaceAvailable: boolean;
  ready: boolean;
}): string {
  return T.githubRealReadNextStep(
    appEnvConfigured,
    hasAppInstallationConnection,
    installationConnected,
    localRepositorySurfaceAvailable,
    ready
  );
}

function githubRealReadBlockerLabel(blocker: string): string {
  if (blocker === "github_app_env_incomplete") {
    return M.githubProductConnect.realReadBlockerEnv;
  }
  if (blocker === "github_app_installation_connection_missing") {
    return M.githubProductConnect.realReadBlockerConnectionMissing;
  }
  if (blocker === "github_app_installation_connection_not_connected") {
    return M.githubProductConnect.realReadBlockerConnectionNotConnected;
  }
  if (blocker === "local_repository_surface_empty") {
    return M.githubProductConnect.realReadBlockerReposEmpty;
  }
  return blocker;
}

function githubAppDescription(status: GitHubConnectionStatusResponse): string {
  if (status.connection_method === "github_app_installation") {
    if (status.status !== "connected" || !status.connection_id) {
      return M.githubProductConnect.appConnectionAttentionDescription;
    }
    return status.display_name ?? M.githubProductConnect.appInstallationDescription;
  }
  if (status.app.configured) {
    return M.githubProductConnect.appReadyDescription;
  }
  return M.githubProductConnect.appMissingDescription;
}

function githubMissionCurrent({
  appConnectionReady,
  canAdminister,
  hasAppInstallationRecord,
  hasRepositories,
  syncPartial,
  syncSucceeded
}: {
  appConnectionReady: boolean;
  canAdminister: boolean;
  hasAppInstallationRecord: boolean;
  hasRepositories: boolean;
  syncPartial: boolean;
  syncSucceeded: boolean;
}): string {
  if (!canAdminister) {
    return M.githubProductConnect.missionViewerCurrent;
  }
  if (!appConnectionReady) {
    return hasAppInstallationRecord
      ? M.githubProductConnect.missionConnectionAttentionCurrent
      : M.githubProductConnect.missionConnectionCurrent;
  }
  if (!hasRepositories) {
    return M.githubProductConnect.missionEmptyCurrent;
  }
  if (syncPartial) {
    return M.githubProductConnect.missionPartialCurrent;
  }
  if (syncSucceeded) {
    return M.githubProductConnect.missionSyncedCurrent;
  }
  return M.githubProductConnect.missionReadyCurrent;
}

function githubMissionAction({
  appConnectionReady,
  canAdminister,
  hasAppInstallationRecord,
  hasRepositories,
  setupAvailable,
  syncPartial
}: {
  appConnectionReady: boolean;
  canAdminister: boolean;
  hasAppInstallationRecord: boolean;
  hasRepositories: boolean;
  setupAvailable: boolean;
  syncPartial: boolean;
}): string {
  if (!canAdminister) {
    return M.githubProductConnect.missionViewerAction;
  }
  if (!appConnectionReady) {
    if (hasAppInstallationRecord) {
      return M.githubProductConnect.missionConnectionAttentionAction;
    }
    return setupAvailable
      ? M.githubProductConnect.missionConnectionAction
      : M.githubProductConnect.missionTechnicalAction;
  }
  if (!hasRepositories) {
    return M.githubProductConnect.missionEmptyAction;
  }
  if (syncPartial) {
    return M.githubProductConnect.missionPartialAction;
  }
  return M.githubProductConnect.missionReadyAction;
}

function githubMissionOutcome({
  appConnectionReady,
  canAdminister,
  hasRepositories,
  syncPartial,
  syncSucceeded
}: {
  appConnectionReady: boolean;
  canAdminister: boolean;
  hasRepositories: boolean;
  syncPartial: boolean;
  syncSucceeded: boolean;
}): string {
  if (!canAdminister) {
    return M.githubProductConnect.missionViewerOutcome;
  }
  if (!appConnectionReady) {
    return M.githubProductConnect.missionConnectionOutcome;
  }
  if (!hasRepositories) {
    return M.githubProductConnect.missionEmptyOutcome;
  }
  if (syncPartial) {
    return M.githubProductConnect.missionPartialOutcome;
  }
  if (syncSucceeded) {
    return M.githubProductConnect.missionSyncedOutcome;
  }
  return M.githubProductConnect.missionReadyOutcome;
}

function classifyGitHubSyncState(status: string): Extract<
  LiveSyncState,
  "error" | "partial" | "pending" | "success"
> {
  const normalized = status.trim().toLowerCase();
  if (normalized === "succeeded") {
    return "success";
  }
  if (normalized === "partial") {
    return "partial";
  }
  if (["pending", "queued", "running"].includes(normalized)) {
    return "pending";
  }
  return "error";
}

function shouldRefreshGitHubDataAfterSync(status: string): boolean {
  const state = classifyGitHubSyncState(status);
  return state === "success" || state === "partial";
}

function formatLastSync(value: string | null): string {
  if (!value) {
    return M.githubProductConnect.lastSyncNever;
  }
  return formatTimestamp(value);
}

function formatTimestamp(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  const day = String(parsed.getUTCDate()).padStart(2, "0");
  const month = String(parsed.getUTCMonth() + 1).padStart(2, "0");
  const year = parsed.getUTCFullYear();
  const hours = String(parsed.getUTCHours()).padStart(2, "0");
  const minutes = String(parsed.getUTCMinutes()).padStart(2, "0");
  return `${day}.${month}.${year} · ${hours}:${minutes} UTC`;
}

function isRepositoryFullName(value: string): boolean {
  return /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(value);
}

export {
  classifyGitHubSyncState,
  shouldRefreshGitHubDataAfterSync,
  summarizeGitHubRealReadReadiness
};
