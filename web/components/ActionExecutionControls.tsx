"use client";

import { useState } from "react";

import {
  executeActionProposal,
  fetchActionProposalAudit,
  fetchActionExecutionPreview
} from "../lib/api";
import { M, T } from "../lib/messages";
import { useWorkspaceId } from "../lib/session";
import type {
  ActionExecutionAuditEvent,
  ActionExecutionPreviewResponse,
  ActionExecutionReceipt,
  ActionExecutionResponse,
  ActionProposal
} from "../lib/types";
import { SourceLink } from "./SourceLink";

type ActionExecutionControlsProps = {
  onRefresh?: () => void;
  proposal: ActionProposal;
};

type ActionExecutionControlsViewProps = {
  auditEvents: ActionExecutionAuditEvent[];
  confirmationChecked: boolean;
  connectionId: string;
  error: string | null;
  executeResult: ActionExecutionResponse | null;
  isExecutePending: boolean;
  isPreviewPending: boolean;
  onConfirmationChange?: (checked: boolean) => void;
  onConnectionIdChange?: (value: string) => void;
  onExecute?: () => void;
  onPreview?: () => void;
  preview: ActionExecutionPreviewResponse | null;
  proposal: ActionProposal;
  receipt: ActionExecutionReceipt | null;
  successMessage?: string | null;
};

export function ActionExecutionControls({
  onRefresh,
  proposal
}: ActionExecutionControlsProps) {
  const workspaceId = useWorkspaceId();
  const [auditEvents, setAuditEvents] = useState<ActionExecutionAuditEvent[]>([]);
  const [connectionId, setConnectionId] = useState("");
  const [confirmationChecked, setConfirmationChecked] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [executeResult, setExecuteResult] = useState<ActionExecutionResponse | null>(null);
  const [isExecutePending, setIsExecutePending] = useState(false);
  const [isPreviewPending, setIsPreviewPending] = useState(false);
  const [preview, setPreview] = useState<ActionExecutionPreviewResponse | null>(null);
  const [receipt, setReceipt] = useState<ActionExecutionReceipt | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  async function refreshAudit(workspaceId: string) {
    const response = await fetchActionProposalAudit(workspaceId, proposal.id);
    setAuditEvents(response.events);
    setReceipt(response.receipt);
  }

  async function previewExecution() {
    if (!workspaceId) {
      setError(M.actionExecution.noWorkspacePreview);
      return;
    }

    setError(null);
    setSuccessMessage(null);
    setIsPreviewPending(true);
    try {
      const response = await fetchActionExecutionPreview(workspaceId, proposal.id);
      setPreview(response);
      setAuditEvents(response.audit);
      await refreshAudit(workspaceId);
      setSuccessMessage(M.actionExecution.previewLoaded);
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : M.common.requestFailed);
    } finally {
      setIsPreviewPending(false);
    }
  }

  async function executeWithConfirmation() {
    if (!workspaceId) {
      setError(M.actionExecution.noWorkspaceExecute);
      return;
    }
    if (!preview?.capabilities.external_execution || !preview.capabilities.live_provider_write) {
      setError(M.actionExecution.externalDisabledError);
      return;
    }
    if (!confirmationChecked || !connectionId.trim()) {
      setError(M.actionExecution.confirmRequired);
      return;
    }

    setError(null);
    setSuccessMessage(null);
    setIsExecutePending(true);
    try {
      const response = await executeActionProposal(workspaceId, proposal.id, {
        connection_id: connectionId.trim(),
        confirm_external_write: true
      });
      setExecuteResult(response);
      setReceipt(response.receipt);
      await refreshAudit(workspaceId);
      setSuccessMessage(
        response.warnings.some((warning) => warning.includes("existing successful"))
          ? M.actionExecution.successExisting
          : response.external_write_performed && response.receipt.provider_result === "succeeded"
            ? M.actionExecution.createdIssue
            : response.external_write_performed
          ? M.actionExecution.successExternalResult
          : M.actionExecution.successNoWrite
      );
      onRefresh?.();
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : M.common.requestFailed);
      try {
        await refreshAudit(workspaceId);
      } catch {
        // Keep the primary execution error visible if audit refresh also fails.
      }
    } finally {
      setIsExecutePending(false);
    }
  }

  return (
    <ActionExecutionControlsView
      auditEvents={auditEvents}
      confirmationChecked={confirmationChecked}
      connectionId={connectionId}
      error={error}
      executeResult={executeResult}
      isExecutePending={isExecutePending}
      isPreviewPending={isPreviewPending}
      onConfirmationChange={setConfirmationChecked}
      onConnectionIdChange={setConnectionId}
      onExecute={executeWithConfirmation}
      onPreview={previewExecution}
      preview={preview}
      proposal={proposal}
      receipt={receipt}
      successMessage={successMessage}
    />
  );
}

export function ActionExecutionControlsView({
  auditEvents,
  confirmationChecked,
  connectionId,
  error,
  executeResult,
  isExecutePending,
  isPreviewPending,
  onConfirmationChange,
  onConnectionIdChange,
  onExecute,
  onPreview,
  preview,
  proposal,
  receipt,
  successMessage = null
}: ActionExecutionControlsViewProps) {
  const isApproved = proposal.status === "approved";
  const externalExecutionEnabled = Boolean(
    preview?.capabilities.external_execution && preview.capabilities.live_provider_write
  );
  const canExecute =
    externalExecutionEnabled &&
    preview?.status === "preview_ready" &&
    confirmationChecked &&
    Boolean(connectionId.trim()) &&
    !isExecutePending;
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
      <strong>{M.actionExecution.previewTitle}</strong>
      <p>{M.actionExecution.previewIntro}</p>

      {!isApproved ? (
        <p className="muted">{M.actionExecution.approveFirst}</p>
      ) : (
        <button
          className="button secondary"
          disabled={isPreviewPending}
          onClick={onPreview}
          type="button"
        >
          {isPreviewPending ? M.actionExecution.preparingPreview : M.actionExecution.preview}
        </button>
      )}

      {error ? <p className="state error">{error}</p> : null}
      {successMessage ? <p className="success-text">{successMessage}</p> : null}

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
                  id={`execution-connection-${proposal.id}`}
                  onChange={(event) => onConnectionIdChange?.(event.target.value)}
                  placeholder={M.actionExecution.connectionIdPlaceholder}
                  value={connectionId}
                />
              </div>
              <label className="actions-row" htmlFor={`execution-confirm-${proposal.id}`}>
                <input
                  checked={confirmationChecked}
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

      {displayedAuditEvents.length > 0 ? (
        <ul className="meta-list" aria-label={T.executionAuditFor(proposal.title)}>
          {displayedAuditEvents.map((event) => (
            <li key={event.id}>
              {event.event_type}: {event.message} ({event.created_at})
              {event.status === "blocked" || event.external_result_id === null
                ? M.actionExecution.auditNoExternalWrite
                : ""}
              {event.event_type.startsWith("execution_")
                ? M.actionExecution.auditRecorded
                : ""}
            </li>
          ))}
        </ul>
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
        actor: "workspace_admin",
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
        actor: "workspace_admin",
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
