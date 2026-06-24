"use client";

import { useState } from "react";

import {
  executeActionProposal,
  fetchActionExecutionPreview
} from "../lib/api";
import { readOperatorConfig } from "../lib/config";
import type {
  ActionExecutionAuditEvent,
  ActionExecutionPreviewResponse,
  ActionExecutionResponse,
  ActionProposal
} from "../lib/types";

type ActionExecutionControlsProps = {
  onRefresh?: () => void;
  proposal: ActionProposal;
};

type ActionExecutionControlsViewProps = {
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
  successMessage?: string | null;
};

export function ActionExecutionControls({
  onRefresh,
  proposal
}: ActionExecutionControlsProps) {
  const [connectionId, setConnectionId] = useState("");
  const [confirmationChecked, setConfirmationChecked] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [executeResult, setExecuteResult] = useState<ActionExecutionResponse | null>(null);
  const [isExecutePending, setIsExecutePending] = useState(false);
  const [isPreviewPending, setIsPreviewPending] = useState(false);
  const [preview, setPreview] = useState<ActionExecutionPreviewResponse | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  async function previewExecution() {
    const config = readOperatorConfig();
    if (!config.workspaceId || !config.ownerEmail || !config.apiKey) {
      setError("Workspace ID, owner email, and API key are required for preview.");
      return;
    }

    setError(null);
    setSuccessMessage(null);
    setIsPreviewPending(true);
    try {
      const response = await fetchActionExecutionPreview(config.workspaceId, proposal.id);
      setPreview(response);
      setSuccessMessage("Execution preview loaded. No external write was performed.");
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "Request failed");
    } finally {
      setIsPreviewPending(false);
    }
  }

  async function executeWithConfirmation() {
    const config = readOperatorConfig();
    if (!config.workspaceId || !config.ownerEmail || !config.apiKey) {
      setError("Workspace ID, owner email, and API key are required for execution.");
      return;
    }
    if (!preview?.capabilities.external_execution || !preview.capabilities.live_provider_write) {
      setError("External execution is disabled in this environment.");
      return;
    }
    if (!confirmationChecked || !connectionId.trim()) {
      setError("Connection ID and explicit confirmation are required before execution.");
      return;
    }

    setError(null);
    setSuccessMessage(null);
    setIsExecutePending(true);
    try {
      const response = await executeActionProposal(config.workspaceId, proposal.id, {
        connection_id: connectionId.trim(),
        confirm_external_write: true
      });
      setExecuteResult(response);
      setSuccessMessage(
        response.external_write_performed
          ? "Backend reported an external execution result."
          : "Execution request completed without an external write."
      );
      onRefresh?.();
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "Request failed");
    } finally {
      setIsExecutePending(false);
    }
  }

  return (
    <ActionExecutionControlsView
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
      successMessage={successMessage}
    />
  );
}

export function ActionExecutionControlsView({
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
  const auditEvents =
    preview && preview.audit.length > 0 ? preview.audit : fallbackAuditEvents(proposal);
  const evidenceCount = preview?.preview?.evidence_refs.length ?? proposal.evidence_refs.length;

  return (
    <section className="callout" aria-label={`Execution controls for ${proposal.title}`}>
      <strong>Execution preview</strong>
      <p>
        Approval does not execute provider writes. Use preview to inspect the
        guarded GitHub issue action before any live write path is considered.
      </p>

      {!isApproved ? (
        <p className="muted">Approve locally before previewing execution readiness.</p>
      ) : (
        <button
          className="button secondary"
          disabled={isPreviewPending}
          onClick={onPreview}
          type="button"
        >
          {isPreviewPending ? "Preparing preview" : "Preview execution"}
        </button>
      )}

      {error ? <p className="state error">{error}</p> : null}
      {successMessage ? <p className="success-text">{successMessage}</p> : null}

      {preview ? (
        <div className="work-item-main">
          <span className="badge">{preview.status}</span>
          <p className="muted">{preview.message}</p>
          <p className="muted">Preview only. This will not write to GitHub.</p>

          {preview.preview ? (
            <dl className="work-meta">
              <div>
                <dt>Provider</dt>
                <dd>{preview.preview.provider}</dd>
              </div>
              <div>
                <dt>Action</dt>
                <dd>{preview.preview.action}</dd>
              </div>
              <div>
                <dt>Repository</dt>
                <dd>{preview.preview.repository}</dd>
              </div>
              <div>
                <dt>Issue title</dt>
                <dd>{preview.preview.title}</dd>
              </div>
              {preview.preview.body ? (
                <div>
                  <dt>Issue body</dt>
                  <dd>{preview.preview.body}</dd>
                </div>
              ) : null}
              <div>
                <dt>Labels</dt>
                <dd>{formatList(preview.preview.labels)}</dd>
              </div>
              <div>
                <dt>Assignees</dt>
                <dd>{formatList(preview.preview.assignees)}</dd>
              </div>
            </dl>
          ) : null}

          {evidenceCount === 0 ? (
            <p className="muted">
              No evidence refs returned for this proposal. The UI does not
              fabricate source refs.
            </p>
          ) : (
            <p className="muted">Evidence refs attached: {evidenceCount}</p>
          )}

          {externalExecutionEnabled ? (
            <div className="form" aria-label="Live execution confirmation">
              <p className="muted">
                Live GitHub write requires explicit confirmation and a connected
                GitHub connection ID.
              </p>
              <div className="field">
                <label htmlFor={`execution-connection-${proposal.id}`}>Connection ID</label>
                <input
                  id={`execution-connection-${proposal.id}`}
                  onChange={(event) => onConnectionIdChange?.(event.target.value)}
                  placeholder="GitHub IntegrationConnection ID"
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
                I confirm this may write to GitHub.
              </label>
              <button
                className="button"
                disabled={!canExecute}
                onClick={onExecute}
                type="button"
              >
                {isExecutePending ? "Executing with confirmation" : "Execute with confirmation"}
              </button>
            </div>
          ) : (
            <p className="muted">External execution disabled in this environment.</p>
          )}
        </div>
      ) : null}

      {executeResult ? (
        <dl className="work-meta" aria-label="Execution result">
          <div>
            <dt>Execution status</dt>
            <dd>{executeResult.execution.status}</dd>
          </div>
          <div>
            <dt>External write performed</dt>
            <dd>{executeResult.external_write_performed ? "yes" : "no"}</dd>
          </div>
          {executeResult.execution.external_id ? (
            <div>
              <dt>External id</dt>
              <dd>{executeResult.execution.external_id}</dd>
            </div>
          ) : null}
        </dl>
      ) : null}

      {auditEvents.length > 0 ? (
        <ul className="meta-list" aria-label={`Execution audit for ${proposal.title}`}>
          {auditEvents.map((event) => (
            <li key={event.id}>
              {event.event}: {event.message} ({event.created_at})
            </li>
          ))}
        </ul>
      ) : null}

      {preview?.warnings.length ? (
        <ul className="meta-list" aria-label={`Execution warnings for ${proposal.title}`}>
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
    {
      actor: proposal.created_by,
      created_at: proposal.created_at,
      event: "proposal_created",
      id: `${proposal.id}:created`,
      message: "Local action proposal was created."
    }
  ];
  if (proposal.approved_at) {
    events.push({
      actor: "workspace_admin",
      created_at: proposal.approved_at,
      event: "proposal_approved",
      id: `${proposal.id}:approved`,
      message: "Proposal was approved locally. No external write was run."
    });
  }
  if (proposal.rejected_at) {
    events.push({
      actor: "workspace_admin",
      created_at: proposal.rejected_at,
      event: "proposal_rejected",
      id: `${proposal.id}:rejected`,
      message: "Proposal was rejected locally. No external write was run."
    });
  }
  return events;
}

function formatList(values: string[]): string {
  return values.length > 0 ? values.join(", ") : "none returned";
}
