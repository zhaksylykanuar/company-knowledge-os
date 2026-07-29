"use client";

import { useState } from "react";

import {
  ApiRequestError,
  executeActionProposal,
  fetchActionProposalAudit,
  fetchActionExecutionPreview,
  syncActionProposalExecutionResult
} from "../lib/api";
import { M, T } from "../lib/messages";
import { useWorkspaceId } from "../lib/session";
import type {
  ActionExecutionAuditEvent,
  ActionExecutionPreviewResponse,
  ActionExecutionReceipt,
  ActionExecutionResultSyncResponse,
  ActionExecutionResponse,
  ActionProposal
} from "../lib/types";
import { SourceLink } from "./SourceLink";

type ActionExecutionControlsProps = {
  disabled?: boolean;
  onBusyChange?: (isBusy: boolean) => boolean | void;
  onComplete?: (outcome: ActionExecutionOutcome) => void;
  onRefresh?: () => void;
  proposal: ActionProposal;
};

export type ActionExecutionOutcome = {
  auditRefreshFailed: boolean;
  externalResultUrl: string | null;
  externalWritePerformed: boolean;
  providerResult: string;
  receiptStatus: string | null;
};

type ActionExecutionControlsViewProps = {
  auditEvents: ActionExecutionAuditEvent[];
  auditWarning?: string | null;
  confirmationChecked: boolean;
  connectionId: string;
  disabled?: boolean;
  error: string | null;
  executeResult: ActionExecutionResponse | null;
  isExecutePending: boolean;
  isHistoryPending: boolean;
  isPreviewPending: boolean;
  isReconcilePending: boolean;
  onConfirmationChange?: (checked: boolean) => void;
  onConnectionIdChange?: (value: string) => void;
  onExecute?: () => void;
  onLoadHistory?: () => void;
  onPreview?: () => void;
  onReconcile?: () => void;
  preview: ActionExecutionPreviewResponse | null;
  proposal: ActionProposal;
  reconciliationNeeded: boolean;
  reconciliationResult: ActionExecutionResultSyncResponse | null;
  receipt: ActionExecutionReceipt | null;
  successMessage?: string | null;
};

export function ActionExecutionControls({
  disabled = false,
  onBusyChange,
  onComplete,
  onRefresh,
  proposal
}: ActionExecutionControlsProps) {
  const workspaceId = useWorkspaceId();
  const [auditEvents, setAuditEvents] = useState<ActionExecutionAuditEvent[]>([]);
  const [auditWarning, setAuditWarning] = useState<string | null>(null);
  const [connectionId, setConnectionId] = useState("");
  const [confirmationChecked, setConfirmationChecked] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [executeResult, setExecuteResult] = useState<ActionExecutionResponse | null>(null);
  const [idempotencyKey, setIdempotencyKey] = useState<string | null>(null);
  const [isExecutePending, setIsExecutePending] = useState(false);
  const [isPreviewPending, setIsPreviewPending] = useState(false);
  const [isHistoryPending, setIsHistoryPending] = useState(false);
  const [isReconcilePending, setIsReconcilePending] = useState(false);
  const [preview, setPreview] = useState<ActionExecutionPreviewResponse | null>(null);
  const [reconciliationNeeded, setReconciliationNeeded] = useState(false);
  const [reconciliationResult, setReconciliationResult] =
    useState<ActionExecutionResultSyncResponse | null>(null);
  const [receipt, setReceipt] = useState<ActionExecutionReceipt | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  async function refreshAudit(workspaceId: string) {
    const response = await fetchActionProposalAudit(workspaceId, proposal.id);
    setAuditEvents(response.events);
    setReceipt(response.receipt);
    setReconciliationNeeded(auditRequiresReconciliation(response));
    return response;
  }

  async function loadHistory() {
    if (disabled || onBusyChange?.(true) === false) {
      return;
    }
    if (!workspaceId) {
      setError(M.actionExecution.noWorkspacePreview);
      onBusyChange?.(false);
      return;
    }

    setError(null);
    setAuditWarning(null);
    setSuccessMessage(null);
    setIsHistoryPending(true);
    try {
      await refreshAudit(workspaceId);
      setSuccessMessage(M.actionExecution.historyLoaded);
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : M.common.requestFailed);
    } finally {
      setIsHistoryPending(false);
      onBusyChange?.(false);
    }
  }

  async function previewExecution() {
    if (disabled || onBusyChange?.(true) === false) {
      return;
    }
    if (!workspaceId) {
      setError(M.actionExecution.noWorkspacePreview);
      onBusyChange?.(false);
      return;
    }

    setError(null);
    setAuditWarning(null);
    setSuccessMessage(null);
    setIsPreviewPending(true);
    try {
      const response = await fetchActionExecutionPreview(workspaceId, proposal.id);
      setPreview(response);
      setAuditEvents(response.audit);
      setSuccessMessage(M.actionExecution.previewLoaded);
      try {
        await refreshAudit(workspaceId);
      } catch {
        setAuditWarning(M.actionExecution.auditRefreshFailed);
      }
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : M.common.requestFailed);
    } finally {
      setIsPreviewPending(false);
      onBusyChange?.(false);
    }
  }

  async function executeWithConfirmation() {
    if (disabled || onBusyChange?.(true) === false) {
      return;
    }
    if (!workspaceId) {
      setError(M.actionExecution.noWorkspaceExecute);
      onBusyChange?.(false);
      return;
    }
    if (!preview?.capabilities.external_execution || !preview.capabilities.live_provider_write) {
      setError(M.actionExecution.externalDisabledError);
      onBusyChange?.(false);
      return;
    }
    if (!confirmationChecked || !connectionId.trim()) {
      setError(M.actionExecution.confirmRequired);
      onBusyChange?.(false);
      return;
    }

    setError(null);
    setAuditWarning(null);
    setSuccessMessage(null);
    setReconciliationResult(null);
    setIsExecutePending(true);
    const requestIdempotencyKey =
      idempotencyKey ?? createExecutionIdempotencyKey(proposal.id);
    setIdempotencyKey(requestIdempotencyKey);
    try {
      const response = await executeActionProposal(workspaceId, proposal.id, {
        connection_id: connectionId.trim(),
        confirm_external_write: true,
        idempotency_key: requestIdempotencyKey
      });
      setExecuteResult(response);
      setReceipt(response.receipt);
      setReconciliationNeeded(false);
      setSuccessMessage(
        response.warnings.some((warning) => warning.includes("existing successful"))
          ? M.actionExecution.successExisting
          : response.external_write_performed && response.receipt.provider_result === "succeeded"
            ? M.actionExecution.createdIssue
            : response.external_write_performed
              ? M.actionExecution.successExternalResult
              : M.actionExecution.successNoWrite
      );
      const outcome: ActionExecutionOutcome = {
        auditRefreshFailed: false,
        externalResultUrl: response.receipt.external_result_url,
        externalWritePerformed: response.external_write_performed,
        providerResult: response.receipt.provider_result,
        receiptStatus: response.receipt.status
      };
      onComplete?.(outcome);
      onRefresh?.();
      try {
        await refreshAudit(workspaceId);
      } catch {
        setAuditWarning(M.actionExecution.auditRefreshAfterExecuteFailed);
        onComplete?.({ ...outcome, auditRefreshFailed: true });
      }
    } catch (caught: unknown) {
      const message =
        caught instanceof Error ? caught.message : M.common.requestFailed;
      let requiresReconciliation = executionErrorRequiresReconciliation(caught);
      try {
        const audit = await refreshAudit(workspaceId);
        requiresReconciliation = auditRequiresReconciliation(audit);
      } catch {
        // Keep the primary execution error visible if audit refresh also fails.
      }
      if (requiresReconciliation) {
        setReconciliationNeeded(true);
        setError(null);
        setSuccessMessage(M.actionExecution.reconciliationRequired);
      } else {
        setIdempotencyKey(null);
        setError(message);
      }
    } finally {
      setIsExecutePending(false);
      onBusyChange?.(false);
    }
  }

  async function reconcileExecution() {
    if (disabled || onBusyChange?.(true) === false) {
      return;
    }
    if (!workspaceId) {
      setError(M.actionExecution.noWorkspaceExecute);
      onBusyChange?.(false);
      return;
    }

    setError(null);
    setAuditWarning(null);
    setSuccessMessage(null);
    setIsReconcilePending(true);
    try {
      const response = await syncActionProposalExecutionResult(
        workspaceId,
        proposal.id,
        {
          connection_id: connectionId.trim() || null
        }
      );
      setReconciliationResult(response);
      setAuditEvents(response.audit);
      if (response.status === "synced") {
        setReconciliationNeeded(false);
        setSuccessMessage(M.actionExecution.reconciliationSucceeded);
      } else if (response.status === "write_not_observed") {
        setReconciliationNeeded(false);
        setIdempotencyKey(null);
        setConfirmationChecked(false);
        setSuccessMessage(M.actionExecution.reconciliationNoWrite);
      } else {
        setReconciliationNeeded(true);
        setSuccessMessage(M.actionExecution.reconciliationPending);
      }
      try {
        await refreshAudit(workspaceId);
      } catch {
        setAuditWarning(M.actionExecution.auditRefreshFailed);
      }
      onRefresh?.();
    } catch (caught: unknown) {
      setReconciliationNeeded(true);
      setError(caught instanceof Error ? caught.message : M.common.requestFailed);
      try {
        await refreshAudit(workspaceId);
      } catch {
        // Keep the primary reconciliation error visible.
      }
    } finally {
      setIsReconcilePending(false);
      onBusyChange?.(false);
    }
  }

  return (
    <ActionExecutionControlsView
      auditEvents={auditEvents}
      auditWarning={auditWarning}
      confirmationChecked={confirmationChecked}
      connectionId={connectionId}
      disabled={disabled}
      error={error}
      executeResult={executeResult}
      isExecutePending={isExecutePending}
      isHistoryPending={isHistoryPending}
      isPreviewPending={isPreviewPending}
      isReconcilePending={isReconcilePending}
      onConfirmationChange={setConfirmationChecked}
      onConnectionIdChange={setConnectionId}
      onExecute={executeWithConfirmation}
      onLoadHistory={loadHistory}
      onPreview={previewExecution}
      onReconcile={reconcileExecution}
      preview={preview}
      proposal={proposal}
      reconciliationNeeded={reconciliationNeeded}
      reconciliationResult={reconciliationResult}
      receipt={receipt}
      successMessage={successMessage}
    />
  );
}

export function ActionExecutionControlsView({
  auditEvents,
  auditWarning = null,
  confirmationChecked,
  connectionId,
  disabled = false,
  error,
  executeResult,
  isExecutePending,
  isHistoryPending,
  isPreviewPending,
  isReconcilePending,
  onConfirmationChange,
  onConnectionIdChange,
  onExecute,
  onLoadHistory,
  onPreview,
  onReconcile,
  preview,
  proposal,
  reconciliationNeeded,
  reconciliationResult,
  receipt,
  successMessage = null
}: ActionExecutionControlsViewProps) {
  const isApproved = proposal.status === "approved";
  const supportsExternalPreview =
    proposal.target_provider === "github" &&
    proposal.action_type === "create_github_issue";
  const hasRecordedDecision = Boolean(proposal.approved_at || proposal.rejected_at);
  const externalExecutionEnabled = Boolean(
    preview?.capabilities.external_execution && preview.capabilities.live_provider_write
  );
  const isBusy =
    disabled ||
    isExecutePending ||
    isHistoryPending ||
    isPreviewPending ||
    isReconcilePending;
  const canExecute =
    externalExecutionEnabled &&
    preview?.status === "preview_ready" &&
    confirmationChecked &&
    Boolean(connectionId.trim()) &&
    !reconciliationNeeded &&
    !isBusy;
  const displayedAuditEvents =
    auditEvents.length > 0
      ? auditEvents
      : preview && preview.audit.length > 0
        ? preview.audit
        : fallbackAuditEvents(proposal);
  const displayedReceipt = executeResult?.receipt ?? receipt;
  const duplicateReceiptReturned = Boolean(
    executeResult?.warnings.some((warning) => warning.includes("existing successful"))
  );
  const createdGitHubIssue = Boolean(
    executeResult &&
      !duplicateReceiptReturned &&
      executeResult.external_write_performed &&
      executeResult.receipt.provider_result === "succeeded"
  );
  const evidenceCount = preview?.preview?.evidence_refs.length ?? proposal.evidence_refs.length;

  return (
    <section className="callout" aria-label={T.executionControlsFor(proposal.title)}>
      <strong>
        {supportsExternalPreview
          ? M.actionExecution.previewTitle
          : "История локального решения"}
      </strong>
      <p>
        {supportsExternalPreview
          ? M.actionExecution.previewIntro
          : "Здесь сохраняются решение человека и локальная история без внешнего выполнения."}
      </p>

      {!isApproved ? (
        <p className="muted">{M.actionExecution.approveFirst}</p>
      ) : !supportsExternalPreview ? (
        <p className="muted">
          Это локальное действие: внешний предпросмотр для него не нужен.
        </p>
      ) : (
        <button
          className="button secondary"
          disabled={isBusy}
          onClick={onPreview}
          type="button"
        >
          {isPreviewPending ? M.actionExecution.preparingPreview : M.actionExecution.preview}
        </button>
      )}

      {hasRecordedDecision ? (
        <button
          className="button secondary"
          disabled={isBusy}
          onClick={onLoadHistory}
          type="button"
        >
          {isHistoryPending
            ? M.actionExecution.historyLoading
            : M.actionExecution.historyLoad}
        </button>
      ) : null}

      <div className="execution-announcements">
        {error ? (
          <p className="state error" role="alert">{error}</p>
        ) : null}
        {successMessage ? (
          <p className="success-text" role="status">{successMessage}</p>
        ) : null}
        {auditWarning ? (
          <p className="state" role="status">{auditWarning}</p>
        ) : null}
      </div>

      {preview ? (
        <div className="work-item-main">
          <span className="badge">{preview.status}</span>
          <p className="muted">{preview.message}</p>
          <p className="muted">{M.actionExecution.previewOnly}</p>

          {preview.preview ? (
            <dl className="work-meta">
              <div>
                <dt>{M.actionExecution.metaProvider}</dt>
                <dd>{preview.preview.provider}</dd>
              </div>
              <div>
                <dt>{M.actionExecution.metaAction}</dt>
                <dd>{preview.preview.action}</dd>
              </div>
              <div>
                <dt>{M.actionExecution.metaRepository}</dt>
                <dd>{preview.preview.repository}</dd>
              </div>
              <div>
                <dt>{M.actionExecution.metaIssueTitle}</dt>
                <dd>{preview.preview.title}</dd>
              </div>
              {preview.preview.body ? (
                <div>
                  <dt>{M.actionExecution.metaIssueBody}</dt>
                  <dd>{preview.preview.body}</dd>
                </div>
              ) : null}
              <div>
                <dt>{M.actionExecution.metaLabels}</dt>
                <dd>{formatList(preview.preview.labels)}</dd>
              </div>
              <div>
                <dt>{M.actionExecution.metaAssignees}</dt>
                <dd>{formatList(preview.preview.assignees)}</dd>
              </div>
            </dl>
          ) : null}

          {evidenceCount === 0 ? (
            <p className="muted">{M.actionExecution.noEvidence}</p>
          ) : (
            <p className="muted">{T.evidenceAttached(evidenceCount)}</p>
          )}

          {externalExecutionEnabled ? (
            <div className="form" aria-label={M.actionExecution.liveLabel}>
              <p className="muted">{M.actionExecution.liveWarning}</p>
              <div className="field">
                <label htmlFor={`execution-connection-${proposal.id}`}>{M.actionExecution.connectionIdLabel}</label>
                <input
                  disabled={isBusy}
                  id={`execution-connection-${proposal.id}`}
                  onChange={(event) => onConnectionIdChange?.(event.target.value)}
                  placeholder={M.actionExecution.connectionIdPlaceholder}
                  value={connectionId}
                />
              </div>
              <label className="actions-row" htmlFor={`execution-confirm-${proposal.id}`}>
                <input
                  checked={confirmationChecked}
                  disabled={isBusy}
                  id={`execution-confirm-${proposal.id}`}
                  onChange={(event) => onConfirmationChange?.(event.target.checked)}
                  type="checkbox"
                />
                {M.actionExecution.confirmCheckbox}
              </label>
              <button
                className="button"
                disabled={!canExecute}
                onClick={onExecute}
                type="button"
              >
                {isExecutePending ? M.actionExecution.executing : M.actionExecution.execute}
              </button>
              {reconciliationNeeded ? (
                <div className="callout">
                  <strong>{M.actionExecution.reconciliationTitle}</strong>
                  <p className="muted">
                    {M.actionExecution.reconciliationDescription}
                  </p>
                  <button
                    className="button secondary"
                    disabled={isBusy}
                    onClick={onReconcile}
                    type="button"
                  >
                    {isReconcilePending
                      ? M.actionExecution.reconciling
                      : M.actionExecution.reconcile}
                  </button>
                </div>
              ) : null}
            </div>
          ) : (
            <p className="muted">{M.actionExecution.externalDisabled}</p>
          )}
        </div>
      ) : null}

      {displayedReceipt ? (
        <dl className="work-meta" aria-label={M.actionExecution.receiptLabel}>
          <div>
            <dt>{M.actionExecution.metaProvider}</dt>
            <dd>{displayedReceipt.provider ?? M.common.none}</dd>
          </div>
          <div>
            <dt>{M.actionExecution.metaAction}</dt>
            <dd>{displayedReceipt.action ?? M.common.none}</dd>
          </div>
          <div>
            <dt>{M.actionExecution.receiptStatus}</dt>
            <dd>{displayedReceipt.status ?? M.common.none}</dd>
          </div>
          <div>
            <dt>{M.actionExecution.receiptProviderResult}</dt>
            <dd>{displayedReceipt.provider_result}</dd>
          </div>
          <div>
            <dt>{M.actionExecution.receiptExternalWrite}</dt>
            <dd>
              {displayedReceipt.external_write_performed
                ? M.actionsPanel.executionReported
                : M.common.none}
            </dd>
          </div>
          <div>
            <dt>{M.actionExecution.receiptConfirmation}</dt>
            <dd>{displayedReceipt.confirmation_received ? M.actionExecution.confirmationReceived : M.actionExecution.confirmationNotReceived}</dd>
          </div>
          {displayedReceipt.external_result_id ? (
            <div>
              <dt>{M.actionExecution.receiptExternalIssue}</dt>
              <dd>{displayedReceipt.external_result_id}</dd>
            </div>
          ) : null}
          {displayedReceipt.external_result_url ? (
            <div>
              <dt>{M.actionExecution.receiptExternalUrl}</dt>
              <dd>
                <SourceLink url={displayedReceipt.external_result_url}>
                  {M.actionExecution.openGithubIssue}
                </SourceLink>
              </dd>
            </div>
          ) : null}
          {displayedReceipt.error_message ? (
            <div>
              <dt>{M.actionExecution.receiptError}</dt>
              <dd>{displayedReceipt.error_message}</dd>
            </div>
          ) : null}
        </dl>
      ) : null}

      {executeResult ? (
        <dl className="work-meta" aria-label={M.actionExecution.resultLabel}>
          <div>
            <dt>{M.actionExecution.resultStatus}</dt>
            <dd>{executeResult.execution.status}</dd>
          </div>
          <div>
            <dt>{M.actionExecution.resultExternalWrite}</dt>
            <dd>{executeResult.external_write_performed ? M.actionExecution.yes : M.actionExecution.no}</dd>
          </div>
          {executeResult.execution.external_id ? (
            <div>
              <dt>{M.actionExecution.resultExternalId}</dt>
              <dd>{executeResult.execution.external_id}</dd>
            </div>
          ) : null}
        </dl>
      ) : null}
      {createdGitHubIssue ? (
        <p className="success-text">{M.actionExecution.createdIssue}</p>
      ) : null}
      {reconciliationResult?.retry_after ? (
        <p className="muted">
          {M.actionExecution.reconciliationRetryAfter}{" "}
          {reconciliationResult.retry_after}
        </p>
      ) : null}

      {displayedAuditEvents.length > 0 ? (
        <AuditEventList events={displayedAuditEvents} proposalTitle={proposal.title} />
      ) : null}

      {preview?.warnings.length ? (
        <ul className="meta-list" aria-label={T.evidenceWarningsFor(proposal.title)}>
          {preview.warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

function createExecutionIdempotencyKey(proposalId: string): string {
  const randomPart =
    globalThis.crypto?.randomUUID?.() ??
    `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `web-execution-${proposalId}-${randomPart}`.slice(0, 255);
}

function executionErrorRequiresReconciliation(caught: unknown): boolean {
  if (!(caught instanceof ApiRequestError)) {
    return true;
  }
  const message = caught.message.toLocaleLowerCase();
  return (
    caught.status >= 500 ||
    message.includes("outcome is uncertain") ||
    message.includes("execution claim already exists") ||
    message.includes("reconcile")
  );
}

function auditRequiresReconciliation(audit: {
  events: ActionExecutionAuditEvent[];
  receipt: ActionExecutionReceipt;
}): boolean {
  if (audit.receipt.provider_result === "uncertain") {
    return true;
  }
  if (audit.receipt.provider_result === "succeeded") {
    return false;
  }
  const latestExecutionEvent = [...audit.events]
    .reverse()
    .find((event) => event.event_type.startsWith("execution_"));
  return Boolean(
    latestExecutionEvent &&
      [
        "execution_claimed",
        "execution_started",
        "execution_outcome_uncertain",
        "execution_reconciliation_pending",
        "execution_result_sync_failed"
      ].includes(latestExecutionEvent.event_type)
  );
}

function AuditEventList({
  events,
  proposalTitle
}: {
  events: ActionExecutionAuditEvent[];
  proposalTitle: string;
}) {
  return (
    <section className="work-section" aria-label={T.executionAuditFor(proposalTitle)}>
      <h3>{M.actionExecution.auditTitle}</h3>
      <div className="work-list">
        {events.map((event) => (
          <article className="work-item" key={event.id}>
            <div className="work-item-main">
              <span className="badge">{event.status}</span>
              <h4>{event.event_type}</h4>
            </div>
            <p className="muted">{event.message}</p>
            <dl className="work-meta">
              <div>
                <dt>{M.actionExecution.auditCreated}</dt>
                <dd>{event.created_at}</dd>
              </div>
              <div>
                <dt>{M.actionExecution.auditActor}</dt>
                <dd>{event.actor}</dd>
              </div>
              <div>
                <dt>{M.actionExecution.auditProvider}</dt>
                <dd>{event.provider ?? M.common.none}</dd>
              </div>
              <div>
                <dt>{M.actionExecution.auditAction}</dt>
                <dd>{event.action ?? M.common.none}</dd>
              </div>
              <div>
                <dt>{M.actionExecution.auditExternalWrite}</dt>
                <dd>{event.external_result_id ? M.actionsPanel.executionReported : M.common.none}</dd>
              </div>
            </dl>
            {event.external_result_url ? (
              <SourceLink url={event.external_result_url}>
                {M.actionExecution.openGithubIssue}
              </SourceLink>
            ) : null}
            {event.external_result_id === null ? (
              <p className="muted">{M.actionExecution.auditNoExternalWrite.trim()}</p>
            ) : null}
            {event.event_type.startsWith("execution_") ? (
              <p className="muted">{M.actionExecution.auditRecorded.trim()}</p>
            ) : null}
          </article>
        ))}
      </div>
    </section>
  );
}

function fallbackAuditEvents(proposal: ActionProposal): ActionExecutionAuditEvent[] {
  const events: ActionExecutionAuditEvent[] = [
    fallbackAuditEvent({
      actor: proposal.created_by,
      createdAt: proposal.created_at,
      eventType: "proposal_created",
      id: `${proposal.id}:created`,
      message: M.actionExecution.fallbackCreated
    })
  ];
  if (proposal.approved_at) {
    events.push(
      fallbackAuditEvent({
        actor: proposal.approved_by_user_id
          ? `user:${proposal.approved_by_user_id}`
          : "system",
        createdAt: proposal.approved_at,
        eventType: "proposal_approved",
        id: `${proposal.id}:approved`,
        message: M.actionExecution.fallbackApproved
      })
    );
  }
  if (proposal.rejected_at) {
    events.push(
      fallbackAuditEvent({
        actor: proposal.rejected_by_user_id
          ? `user:${proposal.rejected_by_user_id}`
          : "system",
        createdAt: proposal.rejected_at,
        eventType: "proposal_rejected",
        id: `${proposal.id}:rejected`,
        message: M.actionExecution.fallbackRejected
      })
    );
  }
  return events;
}

function fallbackAuditEvent({
  actor,
  createdAt,
  eventType,
  id,
  message
}: {
  actor: string;
  createdAt: string;
  eventType: string;
  id: string;
  message: string;
}): ActionExecutionAuditEvent {
  return {
    action: null,
    actor,
    confirmation_received: false,
    created_at: createdAt,
    error_code: null,
    error_message: null,
    event: eventType,
    event_metadata: {},
    event_type: eventType,
    external_execution_enabled: false,
    external_result_id: null,
    external_result_url: null,
    id,
    message,
    provider: null,
    status: "recorded"
  };
}

function formatList(values: string[]): string {
  return values.length > 0 ? values.join(", ") : "none returned";
}
