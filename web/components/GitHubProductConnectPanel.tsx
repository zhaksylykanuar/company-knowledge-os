"use client";

import type { ReactNode } from "react";
import { useEffect, useRef, useState } from "react";

import {
  cancelGitHubSyncJob,
  fetchGitHubConnectionStatus,
  fetchGitHubRepositories,
  runGitHubAppLiveSync,
  waitForGitHubSyncJob
} from "../lib/api";
import { M, T } from "../lib/messages";
import {
  canAdministerSelectedWorkspace,
  useSession
} from "../lib/session";
import type {
  GitHubAppLiveSyncResponse,
  GitHubConnectionStatusResponse,
  GitHubRepositoryListResponse,
  GitHubRepositoryRead,
  GitHubSyncJobRead
} from "../lib/types";
import { EmptyState } from "./EmptyState";
import { ErrorState } from "./ErrorState";
import { GitHubAppSetupWizard } from "./GitHubAppSetupWizard";
import { LoadingState } from "./LoadingState";
import { SourceLink } from "./SourceLink";

type ProductConnectState = "loading" | "ready" | "error" | "missing";
type LiveSyncState =
  | "idle"
  | "syncing"
  | "pending"
  | "partial"
  | "success"
  | "error";
type RepositorySyncStatus = {
  error: string | null;
  result: GitHubAppLiveSyncResponse | null;
  state: LiveSyncState;
};
type GitHubRealReadReadiness = {
  appConfigured: boolean;
  blockers: string[];
  hasAppInstallationConnection: boolean;
  installationConnected: boolean;
  localRepositoryCount: number;
  localRepositorySurfaceAvailable: boolean;
  nextStep: string;
  ready: boolean;
};

type GitHubProductConnectPanelProps = {
  onConnectionReadyChange?: (ready: boolean) => void;
  onSelectedRepositoryChange?: (repositoryFullName: string | null) => void;
  onSyncComplete?: () => void;
};

type GitHubProductConnectPanelViewProps = {
  canAdminister?: boolean;
  connectionStatus: GitHubConnectionStatusResponse | null;
  error: string | null;
  onCloseSetup?: () => void;
  onCancelRepositorySync?: (repositoryFullName: string) => void;
  onOpenSetup?: () => void;
  onRepositorySelect?: (repositoryFullName: string) => void;
  onRetry?: () => void;
  onRunRepositorySync?: (repositoryFullName: string) => void;
  repositorySync: Record<string, RepositorySyncStatus>;
  repositories: GitHubRepositoryListResponse | null;
  selectedRepository?: string | null;
  selfServiceSetupEnabled?: boolean;
  setupOpen?: boolean;
  setupWizard?: ReactNode;
  state: ProductConnectState;
};

export function GitHubProductConnectPanel({
  onConnectionReadyChange,
  onSelectedRepositoryChange,
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
  const [selectedRepository, setSelectedRepository] = useState<string | null>(
    null
  );
  const [setupOpen, setSetupOpen] = useState(false);
  const [state, setState] = useState<ProductConnectState>("loading");
  const cancelInFlightRef = useRef(false);
  const syncInFlightRef = useRef(false);
  const syncAbortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    void reloadKey;
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
        const visibleRepositories = githubVisibleRepositories(
          status,
          repositoryList.repositories
        );
        setConnectionStatus(status);
        setRepositories(repositoryList);
        setSelectedRepository((current) =>
          chooseAvailableRepository(visibleRepositories, current)
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
      syncAbortRef.current?.abort();
    };
  }, [workspaceId, reloadKey]);

  useEffect(() => {
    onSelectedRepositoryChange?.(selectedRepository);
  }, [onSelectedRepositoryChange, selectedRepository]);

  useEffect(() => {
    onConnectionReadyChange?.(
      connectionStatus ? isGitHubAppConnectionReady(connectionStatus) : false
    );
  }, [connectionStatus, onConnectionReadyChange]);

  async function syncRepository(repositoryFullName: string) {
    const repository = repositoryFullName.trim();
    if (
      syncInFlightRef.current ||
      !workspaceId ||
      !canAdminister ||
      !connectionStatus ||
      !isGitHubAppConnectionReady(connectionStatus) ||
      !connectionStatus.connection_id ||
      !isRepositoryFullName(repository)
    ) {
      return;
    }

    syncInFlightRef.current = true;
    const controller = new AbortController();
    syncAbortRef.current = controller;
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
      let currentResult = payload;
      const resultState = classifyGitHubSyncState(currentResult.sync_job.status);
      setRepositorySync((current) => ({
        ...current,
        [repository]: {
          error: null,
          result: currentResult,
          state: resultState
        }
      }));
      if (!isGitHubSyncTerminalStatus(currentResult.sync_job.status)) {
        const syncJob = await waitForGitHubSyncJob(
          workspaceId,
          currentResult.sync_job.id,
          {
            onUpdate: (updatedJob) => {
              currentResult = mergeGitHubSyncJobResult(
                currentResult,
                updatedJob
              );
              setRepositorySync((current) => ({
                ...current,
                [repository]: {
                  error: null,
                  result: currentResult,
                  state: classifyGitHubSyncState(updatedJob.status)
                }
              }));
            },
            signal: controller.signal
          }
        );
        currentResult = mergeGitHubSyncJobResult(currentResult, syncJob);
      }
      if (shouldRefreshGitHubDataAfterSync(currentResult.sync_job.status)) {
        setReloadKey((current) => current + 1);
        completed = true;
      }
    } catch (caught: unknown) {
      if (controller.signal.aborted) {
        return;
      }
      setRepositorySync((current) => ({
        ...current,
        [repository]: {
          error: caught instanceof Error ? caught.message : M.common.requestFailed,
          result: null,
          state: "error"
        }
      }));
    } finally {
      if (syncAbortRef.current === controller) {
        syncAbortRef.current = null;
      }
      syncInFlightRef.current = false;
    }

    if (completed) {
      onSyncComplete?.();
    }
  }

  async function cancelRepositorySync(repositoryFullName: string) {
    if (!workspaceId || !canAdminister || cancelInFlightRef.current) {
      return;
    }
    const currentResult = repositorySync[repositoryFullName]?.result;
    if (
      !currentResult ||
      isGitHubSyncTerminalStatus(currentResult.sync_job.status)
    ) {
      return;
    }
    cancelInFlightRef.current = true;
    setRepositorySync((current) => ({
      ...current,
      [repositoryFullName]: {
        error: null,
        result: currentResult,
        state: "syncing"
      }
    }));
    try {
      const syncJob = await cancelGitHubSyncJob(
        workspaceId,
        currentResult.sync_job.id
      );
      syncAbortRef.current?.abort();
      const result = mergeGitHubSyncJobResult(currentResult, syncJob);
      setRepositorySync((current) => ({
        ...current,
        [repositoryFullName]: {
          error: null,
          result,
          state: classifyGitHubSyncState(syncJob.status)
        }
      }));
    } catch (caught: unknown) {
      setRepositorySync((current) => ({
        ...current,
        [repositoryFullName]: {
          error: caught instanceof Error ? caught.message : M.common.requestFailed,
          result: currentResult,
          state: "pending"
        }
      }));
    } finally {
      cancelInFlightRef.current = false;
    }
  }

  return (
    <GitHubProductConnectPanelView
      canAdminister={canAdminister}
      connectionStatus={connectionStatus}
      error={error}
      onCancelRepositorySync={
        canAdminister ? cancelRepositorySync : undefined
      }
      onCloseSetup={() => setSetupOpen(false)}
      onOpenSetup={() => setSetupOpen(true)}
      onRepositorySelect={setSelectedRepository}
      onRetry={() => setReloadKey((current) => current + 1)}
      onRunRepositorySync={canAdminister ? syncRepository : undefined}
      repositorySync={repositorySync}
      repositories={repositories}
      selectedRepository={selectedRepository}
      selfServiceSetupEnabled
      setupOpen={setupOpen}
      setupWizard={
        workspaceId ? (
          <GitHubAppSetupWizard
            canAdminister={canAdminister}
            onSetupChange={() => setReloadKey((current) => current + 1)}
            workspaceId={workspaceId}
          />
        ) : null
      }
      state={state}
    />
  );
}

export function GitHubProductConnectPanelView({
  canAdminister = true,
  connectionStatus,
  error,
  onCancelRepositorySync,
  onCloseSetup,
  onOpenSetup,
  onRepositorySelect,
  onRetry,
  onRunRepositorySync,
  repositorySync,
  repositories,
  selectedRepository,
  selfServiceSetupEnabled = false,
  setupOpen = false,
  setupWizard,
  state
}: GitHubProductConnectPanelViewProps) {
  if (state === "loading") {
    return (
      <section
        aria-busy="true"
        aria-label={M.githubProductConnect.loading}
        className="panel github-source github-source--state"
      >
        <LoadingState label={M.githubProductConnect.loading} />
      </section>
    );
  }

  if (state === "missing") {
    return (
      <section className="panel github-source github-source--state">
        <EmptyState
          description={M.githubProductConnect.noWorkspaceDescription}
          title={M.common.noWorkspaceTitle}
        />
      </section>
    );
  }

  if (state === "error") {
    return (
      <section className="panel github-source github-source--state">
        <ErrorState
          description={M.githubProductConnect.unavailableDescription}
          title={M.githubProductConnect.unavailableTitle}
        />
        <button className="button secondary" onClick={onRetry} type="button">
          {M.common.retry}
        </button>
        {error ? (
          <details className="github-source__error-details">
            <summary>{M.githubProductConnect.errorDetails}</summary>
            <p>{error}</p>
          </details>
        ) : null}
      </section>
    );
  }

  if (!connectionStatus) {
    return null;
  }

  const appConnectionReady = isGitHubAppConnectionReady(connectionStatus);
  const hasInstallationRecord = Boolean(
    connectionStatus.has_connection_record &&
      connectionStatus.connection_method === "github_app_installation"
  );
  const repositoryItems = githubVisibleRepositories(
    connectionStatus,
    repositories?.repositories ?? []
  );
  const selectedRepositoryItem = chooseSelectedRepository(
    repositoryItems,
    selectedRepository
  );
  const selectedSync = selectedRepositoryItem
    ? repositorySync[selectedRepositoryItem.full_name] ?? idleSyncStatus()
    : idleSyncStatus();
  const globalSyncInProgress = Object.values(repositorySync).some(
    (sync) => sync.state === "syncing" || sync.state === "pending"
  );
  const canRunSelectedSync = Boolean(
    canAdminister &&
      appConnectionReady &&
      selectedRepositoryItem &&
      isRepositoryFullName(selectedRepositoryItem.full_name) &&
      onRunRepositorySync &&
      !globalSyncInProgress
  );

  if (!appConnectionReady) {
    return (
      <section
        aria-labelledby="github-connect-title"
        className="panel github-source github-connect"
      >
        <div className="github-connect__hero">
          <GitHubMark />
          <div className="github-connect__copy">
            <span className="github-source__status github-source__status--idle">
              {hasInstallationRecord
                ? M.githubProductConnect.connectionAttentionBadge
                : M.githubProductConnect.notConnectedBadge}
            </span>
            <h2 id="github-connect-title">
              {hasInstallationRecord
                ? M.githubProductConnect.connectionAttentionTitle
                : M.githubProductConnect.connectTitle}
            </h2>
            <p>
              {hasInstallationRecord
                ? M.githubProductConnect.connectionAttentionDescription
                : M.githubProductConnect.connectDescription}
            </p>
          </div>
        </div>

        {!setupOpen ? (
          <>
            <ul
              aria-label={M.githubProductConnect.capabilitiesLabel}
              className="github-connect__capabilities"
            >
              <li>
                <span aria-hidden="true">✓</span>
                {M.githubProductConnect.capabilityRepositories}
              </li>
              <li>
                <span aria-hidden="true">✓</span>
                {M.githubProductConnect.capabilityIssues}
              </li>
              <li>
                <span aria-hidden="true">✓</span>
                {M.githubProductConnect.capabilityPullRequests}
              </li>
            </ul>

            {canAdminister ? (
              <div className="github-connect__actions">
                {selfServiceSetupEnabled ? (
                  <button
                    className="button github-source__primary"
                    onClick={onOpenSetup}
                    type="button"
                  >
                    {hasInstallationRecord
                      ? M.githubProductConnect.continueSetupAction
                      : M.githubProductConnect.connectAction}
                  </button>
                ) : connectionStatus.app.setup_url &&
                  !hasInstallationRecord ? (
                  <SourceLink
                    className="button github-source__primary"
                    url={connectionStatus.app.setup_url}
                  >
                    {M.githubProductConnect.connectAction}
                  </SourceLink>
                ) : (
                  <button
                    className="button github-source__primary"
                    onClick={onRetry}
                    type="button"
                  >
                    {M.githubProductConnect.refreshConnection}
                  </button>
                )}
                <span>{M.githubProductConnect.readOnlyPromise}</span>
              </div>
            ) : (
              <p className="github-connect__viewer-note">
                {M.common.sourceAdminOnlyNote}
              </p>
            )}
          </>
        ) : null}

        {setupOpen && setupWizard ? (
          <div className="github-source__setup-shell">
            <div className="github-source__setup-toolbar">
              <strong>{M.githubProductConnect.setupPanelTitle}</strong>
              <button
                className="button ghost"
                onClick={onCloseSetup}
                type="button"
              >
                {M.githubProductConnect.closeSetupAction}
              </button>
            </div>
            {setupWizard}
          </div>
        ) : null}

        <GitHubSafetyDetails
          connectionStatus={connectionStatus}
          repositories={repositories}
        />
      </section>
    );
  }

  return (
    <section
      aria-busy={globalSyncInProgress}
      aria-labelledby="github-source-title"
      className="panel github-source github-source--connected"
    >
      <div className="github-source__topbar">
        <div className="github-source__identity">
          <GitHubMark />
          <div>
            <span className="github-source__status github-source__status--ready">
              <span aria-hidden="true" />
              {M.githubProductConnect.connectedBadge}
            </span>
            <h2 id="github-source-title">
              {connectionStatus.display_name ??
                M.githubProductConnect.connectedTitle}
            </h2>
            <p>{M.githubProductConnect.connectedDescription}</p>
          </div>
        </div>
        {canAdminister && selfServiceSetupEnabled ? (
          <button
            className="button ghost github-source__manage"
            onClick={setupOpen ? onCloseSetup : onOpenSetup}
            type="button"
          >
            {setupOpen
              ? M.githubProductConnect.closeSetupAction
              : M.githubProductConnect.manageConnection}
          </button>
        ) : null}
      </div>

      {setupOpen && setupWizard ? (
        <div className="github-source__setup-shell">{setupWizard}</div>
      ) : null}

      <div className="github-source__workspace">
        <div className="github-source__workspace-copy">
          <span className="eyebrow">
            {M.githubProductConnect.repositoryControlEyebrow}
          </span>
          <h3>{M.githubProductConnect.repositoryControlTitle}</h3>
          <p>{M.githubProductConnect.repositoryControlDescription}</p>
        </div>

        {repositoryItems.length > 0 ? (
          <div className="github-source__controls">
            <label className="github-source__repository-field">
              <span>{M.githubProductConnect.repositorySelectLabel}</span>
              <select
                disabled={globalSyncInProgress}
                onChange={(event) => onRepositorySelect?.(event.target.value)}
                value={selectedRepositoryItem?.full_name ?? ""}
              >
                {repositoryItems.map((repository) => (
                  <option key={repository.full_name} value={repository.full_name}>
                    {repository.full_name}
                    {repository.archived
                      ? ` · ${M.githubProductConnect.repositoryArchived}`
                      : ""}
                  </option>
                ))}
              </select>
            </label>
            {selectedRepositoryItem?.source_url ? (
              <SourceLink
                className="github-source__repo-link"
                url={selectedRepositoryItem.source_url}
              >
                {M.githubProductConnect.openRepository}
              </SourceLink>
            ) : null}
            {canAdminister ? (
              <button
                className="button github-source__primary"
                disabled={!canRunSelectedSync}
                onClick={() =>
                  selectedRepositoryItem
                    ? onRunRepositorySync?.(selectedRepositoryItem.full_name)
                    : undefined
                }
                type="button"
              >
                {globalSyncInProgress
                  ? M.githubProductConnect.updatingData
                  : M.githubProductConnect.updateData}
              </button>
            ) : null}
          </div>
        ) : (
          <div className="github-source__empty-repositories">
            <strong>{M.githubProductConnect.repositoryListEmptyTitle}</strong>
            <p>{M.githubProductConnect.repositoryListEmptyDescription}</p>
            {canAdminister ? (
              <button
                className="button secondary"
                onClick={onOpenSetup}
                type="button"
              >
                {M.githubProductConnect.manageRepositoryAccess}
              </button>
            ) : null}
          </div>
        )}

        <div className="github-source__meta">
          <span>
            {M.githubProductConnect.lastUpdatedLabel}:{" "}
            <strong>{formatLastSync(connectionStatus.last_sync_at)}</strong>
          </span>
          <span>
            {M.githubProductConnect.repositoryCountLabel}:{" "}
            <strong>{repositoryItems.length}</strong>
          </span>
          <span>{M.githubProductConnect.readOnlyPromise}</span>
        </div>
      </div>

      {selectedRepositoryItem &&
      !isRepositoryFullName(selectedRepositoryItem.full_name) ? (
        <p className="error-text">
          {M.githubProductConnect.liveSyncRepositoryInvalid}
        </p>
      ) : null}

      {selectedSync.state === "error" && !selectedSync.result ? (
        <div className="github-source__sync-error">
          <ErrorState
            description={M.githubProductConnect.liveSyncFailedDescription}
            title={M.githubProductConnect.liveSyncFailedTitle}
          />
          {selectedSync.error ? (
            <details className="github-source__error-details">
              <summary>{M.githubProductConnect.errorDetails}</summary>
              <p>{selectedSync.error}</p>
            </details>
          ) : null}
        </div>
      ) : null}

      {selectedSync.result ? (
        <GitHubSyncReceipt
          onCancel={
            selectedSync.state === "pending" &&
            selectedRepositoryItem &&
            onCancelRepositorySync
              ? () =>
                  onCancelRepositorySync?.(selectedRepositoryItem.full_name)
              : undefined
          }
          result={selectedSync.result}
          state={classifyGitHubSyncState(selectedSync.result.sync_job.status)}
        />
      ) : null}

      <GitHubSafetyDetails
        connectionStatus={connectionStatus}
        repositories={repositories}
      />
    </section>
  );
}

function GitHubMark() {
  return (
    <span className="github-source__mark" aria-hidden="true">
      <svg aria-hidden="true" viewBox="0 0 24 24">
        <path
          d="M12 2.4a9.8 9.8 0 0 0-3.1 19.1c.5.1.7-.2.7-.5v-1.9c-2.9.6-3.5-1.2-3.5-1.2-.5-1.2-1.2-1.5-1.2-1.5-.9-.7.1-.7.1-.7 1.1.1 1.7 1.1 1.7 1.1 1 1.7 2.6 1.2 3.2.9.1-.7.4-1.2.7-1.5-2.3-.3-4.7-1.1-4.7-4.9 0-1.1.4-2 1-2.7-.1-.3-.4-1.3.1-2.7 0 0 .8-.3 2.7 1a9.2 9.2 0 0 1 4.9 0c1.9-1.3 2.7-1 2.7-1 .5 1.4.2 2.4.1 2.7.6.7 1 1.6 1 2.7 0 3.8-2.4 4.6-4.7 4.9.4.3.7 1 .7 2V21c0 .3.2.6.7.5A9.8 9.8 0 0 0 12 2.4Z"
          fill="currentColor"
        />
      </svg>
    </span>
  );
}

function GitHubSafetyDetails({
  connectionStatus,
  repositories
}: {
  connectionStatus: GitHubConnectionStatusResponse;
  repositories: GitHubRepositoryListResponse | null;
}) {
  const warnings = [
    ...connectionStatus.warnings,
    ...(repositories?.warnings ?? [])
  ];
  return (
    <details className="github-source__safety">
      <summary>{M.githubProductConnect.safetyDetails}</summary>
      <div className="github-source__safety-body">
        <p>{M.githubProductConnect.safetyDescription}</p>
        <dl>
          <div>
            <dt>{M.githubProductConnect.tokenTitle}</dt>
            <dd>
              {connectionStatus.app.installation_tokens_persisted
                ? M.common.yes
                : M.common.no}
            </dd>
          </div>
          <div>
            <dt>{M.githubProductConnect.writeTitle}</dt>
            <dd>
              {connectionStatus.app.provider_writes_enabled
                ? M.common.enabled
                : M.common.notEnabled}
            </dd>
          </div>
          <div>
            <dt>{M.githubProductConnect.repositorySourceTitle}</dt>
            <dd>{repositories?.source ?? M.common.unknown}</dd>
          </div>
        </dl>
        {warnings.length > 0 ? (
          <div className="github-source__technical-note">
            <strong>{M.common.warnings}</strong>
            <ul>
              {warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>
    </details>
  );
}

function GitHubSyncReceipt({
  onCancel,
  result,
  state
}: {
  onCancel?: () => void;
  result: GitHubAppLiveSyncResponse;
  state: Extract<LiveSyncState, "error" | "partial" | "pending" | "success">;
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
      <div aria-atomic="true" aria-live="polite" role="status">
        <span className="eyebrow">{receiptCopy.eyebrow}</span>
        <h3>{receiptCopy.title}</h3>
        {receiptCopy.description ? <p>{receiptCopy.description}</p> : null}
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
        {state === "pending" && onCancel ? (
          <button className="button secondary" onClick={onCancel} type="button">
            {M.githubProductConnect.liveSyncCancel}
          </button>
        ) : null}
      </div>
      {result.warnings.length > 0 ? (
        <details>
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

function githubVisibleRepositories(
  connectionStatus: GitHubConnectionStatusResponse,
  repositories: GitHubRepositoryRead[]
): GitHubRepositoryRead[] {
  const selected = new Set(
    (connectionStatus.selected_repositories ?? []).map((repository) =>
      repository.toLowerCase()
    )
  );
  if (
    connectionStatus.app.credential_source !== "managed" ||
    !connectionStatus.installation_verified ||
    selected.size === 0
  ) {
    return repositories;
  }
  return repositories.filter((repository) =>
    selected.has(repository.full_name.toLowerCase())
  );
}

function chooseAvailableRepository(
  repositories: GitHubRepositoryRead[],
  current: string | null
): string | null {
  if (
    current &&
    repositories.some((repository) => repository.full_name === current)
  ) {
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

function isGitHubAppConnectionReady(
  status: GitHubConnectionStatusResponse
): boolean {
  return Boolean(
    status.app.configured &&
      status.installation_verified &&
      status.live_read_available &&
      status.status === "connected" &&
      status.connection_id &&
      status.connection_method === "github_app_installation" &&
      status.has_connection_record
  );
}

function summarizeGitHubRealReadReadiness(
  connectionStatus: GitHubConnectionStatusResponse,
  repositories: GitHubRepositoryListResponse | null
): GitHubRealReadReadiness {
  const appConfigured = connectionStatus.app.configured;
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
  if (!appConfigured) {
    blockers.push("github_app_not_configured");
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
    appConfigured,
    blockers,
    hasAppInstallationConnection,
    installationConnected,
    localRepositoryCount,
    localRepositorySurfaceAvailable,
    nextStep: T.githubRealReadNextStep(
      appConfigured,
      hasAppInstallationConnection,
      installationConnected,
      localRepositorySurfaceAvailable,
      ready
    ),
    ready
  };
}

function classifyGitHubSyncState(
  status: string
): Extract<LiveSyncState, "error" | "partial" | "pending" | "success"> {
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

function isGitHubSyncTerminalStatus(status: string): boolean {
  return ["cancelled", "failed", "partial", "succeeded"].includes(
    status.trim().toLowerCase()
  );
}

function mergeGitHubSyncJobResult(
  result: GitHubAppLiveSyncResponse,
  syncJob: GitHubSyncJobRead
): GitHubAppLiveSyncResponse {
  const progressCounts = syncJob.progress?.counts;
  const repositories = syncJob.progress?.repositories ?? result.repositories;
  const warnings = [
    ...result.warnings,
    ...syncJob.warnings,
    ...(syncJob.error_message ? [syncJob.error_message] : [])
  ].filter((warning, index, all) => all.indexOf(warning) === index);
  const status = syncJob.status.trim().toLowerCase();
  const normalizationCompleted = ["partial", "succeeded"].includes(status);
  return {
    ...result,
    repositories,
    totals: {
      repositories:
        progressCounts?.repositories ?? result.totals.repositories,
      issues: progressCounts?.issues ?? result.totals.issues,
      pull_requests:
        progressCounts?.pull_requests ?? result.totals.pull_requests,
      skipped_pull_requests:
        progressCounts?.skipped_pull_requests ??
        result.totals.skipped_pull_requests
    },
    sync_job: {
      id: syncJob.id,
      status: syncJob.status,
      records_seen: syncJob.records_seen,
      records_created: syncJob.records_created,
      records_updated: syncJob.records_updated,
      started_at: syncJob.started_at,
      finished_at: syncJob.finished_at,
      attempt_count: syncJob.attempt_count,
      max_attempts: syncJob.max_attempts,
      next_attempt_at: syncJob.next_attempt_at,
      cancel_requested_at: syncJob.cancel_requested_at,
      progress: syncJob.progress
    },
    counts: {
      repositories:
        progressCounts?.repositories ?? result.counts.repositories,
      issues: progressCounts?.issues ?? result.counts.issues,
      pull_requests:
        progressCounts?.pull_requests ?? result.counts.pull_requests
    },
    is_live: syncJob.is_live,
    provider_sync_started: syncJob.execution_started,
    local_normalization_performed: normalizationCompleted,
    persistence_mode: normalizationCompleted ? "canonical" : status,
    warnings
  };
}

function shouldRefreshGitHubDataAfterSync(status: string): boolean {
  const state = classifyGitHubSyncState(status);
  return state === "success" || state === "partial";
}

function formatLastSync(value: string | null): string {
  if (!value) {
    return M.githubProductConnect.lastSyncNever;
  }
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
  mergeGitHubSyncJobResult,
  shouldRefreshGitHubDataAfterSync,
  summarizeGitHubRealReadReadiness
};
