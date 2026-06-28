"use client";

import { type FormEvent, useEffect, useState } from "react";

import {
  approveActionProposal,
  createActionProposal,
  fetchActionProposals,
  rejectActionProposal
} from "../lib/api";
import { M, T } from "../lib/messages";
import { useWorkspaceId } from "../lib/session";
import type {
  ActionProposal,
  ActionProposalEvidenceRef,
  ActionProposalListResponse,
  ActionProposalType,
  ActionTargetProvider
} from "../lib/types";
import { ActionExecutionControls } from "./ActionExecutionControls";
import { EmptyState } from "./EmptyState";
import { ErrorState } from "./ErrorState";
import { EvidenceDrawer } from "./EvidenceDrawer";
import { LoadingState } from "./LoadingState";
import { StatusCard } from "./StatusCard";

type PanelStatus = "empty" | "error" | "loading" | "missing" | "ready" | "unsupported";
type ProposalKind = "github_issue" | "internal_todo";
type PendingMutation = "create" | `approve:${string}` | `reject:${string}` | null;

type ActionProposalCreateFormState = {
  description: string;
  issueBody: string;
  proposalKind: ProposalKind;
  repositoryFullName: string;
  title: string;
};

type ActionProposalsPanelViewProps = {
  createForm: ActionProposalCreateFormState;
  data: ActionProposalListResponse | null;
  error: string | null;
  onApprove?: (proposalId: string) => void;
  onCloseEvidence?: () => void;
  onCreate?: (event: FormEvent<HTMLFormElement>) => void;
  onCreateFormChange?: (
    field: keyof ActionProposalCreateFormState,
    value: string
  ) => void;
  onReject?: (proposalId: string) => void;
  onRefreshProposals?: () => void;
  onRetry?: () => void;
  onSelectEvidence?: (evidence: ActionProposalEvidenceRef, title: string) => void;
  pendingMutation: PendingMutation;
  selectedEvidence: ActionProposalEvidenceRef | null;
  selectedEvidenceTitle?: string | null;
  status: PanelStatus;
  successMessage?: string | null;
};

const DEFAULT_CREATE_FORM: ActionProposalCreateFormState = {
  description: "",
  issueBody: "",
  proposalKind: "github_issue",
  repositoryFullName: "",
  title: ""
};

export function ActionProposalsPanel() {
  const workspaceId = useWorkspaceId();
  const [data, setData] = useState<ActionProposalListResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [createForm, setCreateForm] = useState<ActionProposalCreateFormState>(
    DEFAULT_CREATE_FORM
  );
  const [pendingMutation, setPendingMutation] = useState<PendingMutation>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [selectedEvidence, setSelectedEvidence] =
    useState<ActionProposalEvidenceRef | null>(null);
  const [selectedEvidenceTitle, setSelectedEvidenceTitle] = useState<string | null>(null);
  const [status, setStatus] = useState<PanelStatus>("loading");
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

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
    fetchActionProposals(workspaceId)
      .then((payload) => {
        if (cancelled) {
          return;
        }
        setData(payload);
        setStatus(payload.proposals.length > 0 ? "ready" : "empty");
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

  function updateCreateForm(
    field: keyof ActionProposalCreateFormState,
    value: string
  ) {
    setCreateForm((current) => ({ ...current, [field]: value }));
  }

  async function submitCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspaceId) {
      setStatus("missing");
      return;
    }
    const request = buildCreateRequest(createForm);
    if (!request) {
      setError(M.actionsPanel.createError);
      setStatus("error");
      return;
    }

    setError(null);
    setSuccessMessage(null);
    setPendingMutation("create");
    try {
      const response = await createActionProposal(workspaceId, request);
      setData((current) => mergeCreatedProposal(current, response.proposal, response.warnings));
      setStatus("ready");
      setCreateForm(DEFAULT_CREATE_FORM);
      setSuccessMessage(M.actionsPanel.createSuccess);
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : M.common.requestFailed);
      setStatus("error");
    } finally {
      setPendingMutation(null);
    }
  }

  async function approve(proposalId: string) {
    if (!workspaceId) {
      setStatus("missing");
      return;
    }

    setError(null);
    setSuccessMessage(null);
    setPendingMutation(`approve:${proposalId}`);
    try {
      const response = await approveActionProposal(workspaceId, proposalId);
      setData((current) => mergeUpdatedProposal(current, response.proposal, response.warnings));
      setStatus("ready");
      setSuccessMessage(M.actionsPanel.approveSuccess);
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : M.common.requestFailed);
      setStatus("error");
    } finally {
      setPendingMutation(null);
    }
  }

  async function reject(proposalId: string) {
    if (!workspaceId) {
      setStatus("missing");
      return;
    }

    setError(null);
    setSuccessMessage(null);
    setPendingMutation(`reject:${proposalId}`);
    try {
      const response = await rejectActionProposal(workspaceId, proposalId, {
        reason: M.actionsPanel.rejectReason
      });
      setData((current) => mergeUpdatedProposal(current, response.proposal, response.warnings));
      setStatus("ready");
      setSuccessMessage(M.actionsPanel.rejectSuccess);
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : M.common.requestFailed);
      setStatus("error");
    } finally {
      setPendingMutation(null);
    }
  }

  return (
    <ActionProposalsPanelView
      createForm={createForm}
      data={data}
      error={error}
      onApprove={approve}
      onCloseEvidence={() => {
        setSelectedEvidence(null);
        setSelectedEvidenceTitle(null);
      }}
      onCreate={submitCreate}
      onCreateFormChange={updateCreateForm}
      onReject={reject}
      onRefreshProposals={() => setReloadKey((current) => current + 1)}
      onRetry={() => setReloadKey((current) => current + 1)}
      onSelectEvidence={(evidence, title) => {
        setSelectedEvidence(evidence);
        setSelectedEvidenceTitle(title);
      }}
      pendingMutation={pendingMutation}
      selectedEvidence={selectedEvidence}
      selectedEvidenceTitle={selectedEvidenceTitle}
      status={status}
      successMessage={successMessage}
    />
  );
}

export function ActionProposalsPanelView({
  createForm,
  data,
  error,
  onApprove,
  onCloseEvidence,
  onCreate,
  onCreateFormChange,
  onReject,
  onRefreshProposals,
  onRetry,
  onSelectEvidence,
  pendingMutation,
  selectedEvidence,
  selectedEvidenceTitle = null,
  status,
  successMessage = null
}: ActionProposalsPanelViewProps) {
  const proposals = data?.proposals ?? [];
  const canCreate = canSubmitCreateForm(createForm);

  return (
    <section className="panel action-proposals" aria-labelledby="action-proposals-title">
      <div className="section-header">
        <div>
          <span className="eyebrow">{M.actionsPanel.eyebrow}</span>
          <h2 id="action-proposals-title">{M.actionsPanel.title}</h2>
        </div>
        <span className="badge">{M.actionsPanel.badgeLocalApproval}</span>
      </div>

      <p className="muted">{M.actionsPanel.intro}</p>

      <section className="callout" aria-label={M.actionsPanel.capabilityTitle}>
        <strong>{M.actionsPanel.capabilityTitle}</strong>
        <p>{T.actionsCapability()}</p>
      </section>

      <ActionProposalCreateForm
        form={createForm}
        isPending={pendingMutation === "create"}
        onChange={onCreateFormChange}
        onSubmit={onCreate}
        submitDisabled={!canCreate}
      />

      {successMessage ? <p className="success-text">{successMessage}</p> : null}

      {status === "loading" ? <LoadingState label={M.actionsPanel.loading} /> : null}

      {status === "missing" ? (
        <EmptyState
          description={M.actionsPanel.noWorkspaceDescription}
          title={M.common.noWorkspaceTitle}
        />
      ) : null}

      {status === "unsupported" ? (
        <EmptyState
          description={M.actionsPanel.unsupportedDescription}
          title={M.actionsPanel.unsupportedTitle}
        />
      ) : null}

      {status === "error" ? (
        <>
          <ErrorState
            description={error ?? M.actionsPanel.unavailableDescription}
            title={M.actionsPanel.unavailableTitle}
          />
          <button className="button secondary" onClick={onRetry} type="button">
            {M.common.retry}
          </button>
        </>
      ) : null}

      {status === "empty" ? (
        <EmptyState
          description={M.actionsPanel.emptyDescription}
          title={M.actionsPanel.emptyTitle}
        />
      ) : null}

      {data && status !== "loading" && status !== "missing" && status !== "error" ? (
        <>
          <section className="grid" aria-label={M.actionsPanel.summaryLabel}>
            <StatusCard
              description={M.actionsPanel.proposedDescription}
              title={M.actionsPanel.proposedTitle}
              value={String(countByStatus(proposals, "proposed"))}
            />
            <StatusCard
              description={M.actionsPanel.approvedDescription}
              title={M.actionsPanel.approvedTitle}
              value={String(countByStatus(proposals, "approved"))}
            />
            <StatusCard
              description={M.actionsPanel.rejectedDescription}
              title={M.actionsPanel.rejectedTitle}
              value={String(countByStatus(proposals, "rejected"))}
            />
            <StatusCard
              description={M.actionsPanel.totalDescription}
              title={M.actionsPanel.totalTitle}
              value={String(data.count)}
            />
          </section>

          <section className="work-columns">
            <ProposalList
              onApprove={onApprove}
              onReject={onReject}
              onRefreshProposals={onRefreshProposals}
              onSelectEvidence={onSelectEvidence}
              pendingMutation={pendingMutation}
              proposals={proposals}
            />
            <EvidenceDrawer
              evidence={selectedEvidence}
              itemTitle={selectedEvidenceTitle}
              onClose={selectedEvidence ? onCloseEvidence : undefined}
            />
          </section>

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

function ActionProposalCreateForm({
  form,
  isPending,
  onChange,
  onSubmit,
  submitDisabled
}: {
  form: ActionProposalCreateFormState;
  isPending: boolean;
  onChange?: (field: keyof ActionProposalCreateFormState, value: string) => void;
  onSubmit?: (event: FormEvent<HTMLFormElement>) => void;
  submitDisabled: boolean;
}) {
  const isGitHubIssue = form.proposalKind === "github_issue";

  return (
    <form className="form proposal-form" onSubmit={onSubmit}>
      <div className="field">
        <label htmlFor="proposal-kind">{M.actionCreate.typeLabel}</label>
        <select
          id="proposal-kind"
          onChange={(event) => onChange?.("proposalKind", event.target.value)}
          value={form.proposalKind}
        >
          <option value="github_issue">{M.actionCreate.typeGithubIssue}</option>
          <option value="internal_todo">{M.actionCreate.typeInternalTodo}</option>
        </select>
      </div>
      <div className="field">
        <label htmlFor="proposal-title">{M.actionCreate.titleLabel}</label>
        <input
          id="proposal-title"
          maxLength={500}
          onChange={(event) => onChange?.("title", event.target.value)}
          placeholder={M.actionCreate.titlePlaceholder}
          required
          value={form.title}
        />
      </div>
      <div className="field">
        <label htmlFor="proposal-description">{M.actionCreate.descriptionLabel}</label>
        <textarea
          id="proposal-description"
          maxLength={5000}
          onChange={(event) => onChange?.("description", event.target.value)}
          placeholder={M.actionCreate.descriptionPlaceholder}
          value={form.description}
        />
      </div>
      {isGitHubIssue ? (
        <>
          <div className="field">
            <label htmlFor="proposal-repository">{M.actionCreate.repositoryLabel}</label>
            <input
              id="proposal-repository"
              onChange={(event) => onChange?.("repositoryFullName", event.target.value)}
              placeholder={M.actionCreate.repositoryPlaceholder}
              required
              value={form.repositoryFullName}
            />
          </div>
          <div className="field">
            <label htmlFor="proposal-issue-body">{M.actionCreate.issueBodyLabel}</label>
            <textarea
              id="proposal-issue-body"
              onChange={(event) => onChange?.("issueBody", event.target.value)}
              placeholder={M.actionCreate.issueBodyPlaceholder}
              value={form.issueBody}
            />
          </div>
        </>
      ) : null}
      <button className="button" disabled={submitDisabled || isPending} type="submit">
        {isPending ? M.actionCreate.submitting : M.actionCreate.submit}
      </button>
      <p className="muted">{M.actionCreate.note}</p>
    </form>
  );
}

function ProposalList({
  onApprove,
  onReject,
  onRefreshProposals,
  onSelectEvidence,
  pendingMutation,
  proposals
}: {
  onApprove?: (proposalId: string) => void;
  onReject?: (proposalId: string) => void;
  onRefreshProposals?: () => void;
  onSelectEvidence?: (evidence: ActionProposalEvidenceRef, title: string) => void;
  pendingMutation: PendingMutation;
  proposals: ActionProposal[];
}) {
  return (
    <section className="work-section" aria-label={M.actionsPanel.listTitle}>
      <h3>{M.actionsPanel.listTitle}</h3>
      {proposals.length === 0 ? (
        <p className="muted">{M.actionsPanel.noProposals}</p>
      ) : null}
      <div className="work-list">
        {proposals.map((proposal) => (
          <article className="work-item" key={proposal.id}>
            <div className="work-item-main">
              <span className="badge">{proposal.status}</span>
              <h4>{proposal.title}</h4>
            </div>
            {proposal.description ? (
              <p className="muted">{proposal.description}</p>
            ) : null}
            <dl className="work-meta">
              <div>
                <dt>{M.actionsPanel.metaTarget}</dt>
                <dd>{proposal.target_provider}</dd>
              </div>
              <div>
                <dt>{M.actionsPanel.metaAction}</dt>
                <dd>{actionLabel(proposal.action_type)}</dd>
              </div>
              <div>
                <dt>{M.actionsPanel.metaStatus}</dt>
                <dd>{proposal.status}</dd>
              </div>
              <div>
                <dt>{M.actionsPanel.metaExecution}</dt>
                <dd>
                  {proposal.execution_started
                    ? M.actionsPanel.executionReported
                    : M.actionsPanel.executionNotExecuted}
                </dd>
              </div>
            </dl>
            <ProposalPayloadDetails proposal={proposal} />
            <ProposalAuditDetails proposal={proposal} />
            <ActionEvidenceButtons
              evidenceRefs={proposal.evidence_refs}
              onSelectEvidence={onSelectEvidence}
              proposalTitle={proposal.title}
            />
            <ProposalActions
              onApprove={onApprove}
              onReject={onReject}
              pendingMutation={pendingMutation}
              proposal={proposal}
            />
            <ActionExecutionControls
              onRefresh={onRefreshProposals}
              proposal={proposal}
            />
            {proposal.warnings.length > 0 ? (
              <ul className="meta-list">
                {proposal.warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            ) : null}
          </article>
        ))}
      </div>
    </section>
  );
}

function ProposalPayloadDetails({ proposal }: { proposal: ActionProposal }) {
  const repository = payloadString(proposal.payload, "repository_full_name");
  const issueTitle = payloadString(proposal.payload, "title");
  const note = payloadString(proposal.payload, "note");

  if (!repository && !issueTitle && !note) {
    return <p className="muted">{M.actionsPanel.payloadNone}</p>;
  }

  return (
    <dl className="work-meta">
      {repository ? (
        <div>
          <dt>{M.actionsPanel.payloadRepository}</dt>
          <dd>{repository}</dd>
        </div>
      ) : null}
      {issueTitle ? (
        <div>
          <dt>{M.actionsPanel.payloadTargetRecord}</dt>
          <dd>{issueTitle}</dd>
        </div>
      ) : null}
      {note ? (
        <div>
          <dt>{M.actionsPanel.payloadInternalNote}</dt>
          <dd>{note}</dd>
        </div>
      ) : null}
    </dl>
  );
}

function ProposalAuditDetails({ proposal }: { proposal: ActionProposal }) {
  return (
    <dl className="work-meta">
      <div>
        <dt>{M.actionsPanel.metaCreated}</dt>
        <dd>{proposal.created_at}</dd>
      </div>
      <div>
        <dt>{M.actionsPanel.metaUpdated}</dt>
        <dd>{proposal.updated_at}</dd>
      </div>
      {proposal.approved_at ? (
        <div>
          <dt>{M.actionsPanel.metaApprovedAt}</dt>
          <dd>{proposal.approved_at}</dd>
        </div>
      ) : null}
      {proposal.rejected_at ? (
        <div>
          <dt>{M.actionsPanel.metaRejectedAt}</dt>
          <dd>{proposal.rejected_at}</dd>
        </div>
      ) : null}
      {proposal.rejection_reason ? (
        <div>
          <dt>{M.actionsPanel.metaRejectionReason}</dt>
          <dd>{proposal.rejection_reason}</dd>
        </div>
      ) : null}
    </dl>
  );
}

function ActionEvidenceButtons({
  evidenceRefs,
  onSelectEvidence,
  proposalTitle
}: {
  evidenceRefs: ActionProposalEvidenceRef[];
  onSelectEvidence?: (evidence: ActionProposalEvidenceRef, title: string) => void;
  proposalTitle: string;
}) {
  if (evidenceRefs.length === 0) {
    return <p className="muted">{M.actionsPanel.noEvidenceRefs}</p>;
  }

  return (
    <div className="actions-row" aria-label={T.evidenceFor(proposalTitle)}>
      {evidenceRefs.map((evidence, index) => (
        <button
          className="button secondary"
          key={`${evidence.kind}-${evidence.source}-${evidence.ref}-${index}`}
          onClick={() => onSelectEvidence?.(evidence, proposalTitle)}
          type="button"
        >
          {T.evidenceButton(evidence.ref)}
        </button>
      ))}
    </div>
  );
}

function ProposalActions({
  onApprove,
  onReject,
  pendingMutation,
  proposal
}: {
  onApprove?: (proposalId: string) => void;
  onReject?: (proposalId: string) => void;
  pendingMutation: PendingMutation;
  proposal: ActionProposal;
}) {
  if (proposal.status === "approved") {
    return <p className="muted">{M.actionsPanel.actionsApprovedNote}</p>;
  }
  if (proposal.status === "rejected") {
    return <p className="muted">{M.actionsPanel.actionsRejectedNote}</p>;
  }
  if (proposal.status !== "proposed") {
    return <p className="muted">{M.actionsPanel.actionsOtherNote}</p>;
  }

  const approvePending = pendingMutation === `approve:${proposal.id}`;
  const rejectPending = pendingMutation === `reject:${proposal.id}`;
  return (
    <div className="actions-row">
      <button
        className="button"
        disabled={approvePending || rejectPending}
        onClick={() => onApprove?.(proposal.id)}
        type="button"
      >
        {approvePending ? M.actionsPanel.approving : M.actionsPanel.approve}
      </button>
      <button
        className="button secondary"
        disabled={approvePending || rejectPending}
        onClick={() => onReject?.(proposal.id)}
        type="button"
      >
        {rejectPending ? M.actionsPanel.rejecting : M.actionsPanel.reject}
      </button>
    </div>
  );
}

function buildCreateRequest(form: ActionProposalCreateFormState) {
  const title = form.title.trim();
  const description = form.description.trim();
  const repository = form.repositoryFullName.trim();
  const issueBody = form.issueBody.trim();
  if (!title) {
    return null;
  }
  if (form.proposalKind === "github_issue") {
    if (!repository) {
      return null;
    }
    return {
      action_type: "create_github_issue" as ActionProposalType,
      description: description || null,
      payload: {
        body: issueBody || description || title,
        repository_full_name: repository,
        title
      },
      target_provider: "github" as ActionTargetProvider,
      title
    };
  }
  return {
    action_type: "internal_todo" as ActionProposalType,
    description: description || null,
    payload: {
      note: description || title
    },
    target_provider: "internal" as ActionTargetProvider,
    title
  };
}

function canSubmitCreateForm(form: ActionProposalCreateFormState): boolean {
  if (!form.title.trim()) {
    return false;
  }
  if (form.proposalKind === "github_issue") {
    return Boolean(form.repositoryFullName.trim());
  }
  return true;
}

function mergeCreatedProposal(
  current: ActionProposalListResponse | null,
  proposal: ActionProposal,
  warnings: string[]
): ActionProposalListResponse {
  if (!current) {
    return {
      count: 1,
      is_live: false,
      proposals: [proposal],
      warnings
    };
  }
  return {
    ...current,
    count: current.count + 1,
    proposals: [proposal, ...current.proposals],
    warnings
  };
}

function mergeUpdatedProposal(
  current: ActionProposalListResponse | null,
  proposal: ActionProposal,
  warnings: string[]
): ActionProposalListResponse {
  if (!current) {
    return {
      count: 1,
      is_live: false,
      proposals: [proposal],
      warnings
    };
  }
  return {
    ...current,
    proposals: current.proposals.map((existing) =>
      existing.id === proposal.id ? proposal : existing
    ),
    warnings
  };
}

function countByStatus(proposals: ActionProposal[], status: string): number {
  return proposals.filter((proposal) => proposal.status === status).length;
}

function actionLabel(actionType: string): string {
  if (actionType === "create_github_issue") {
    return M.actionsPanel.actionLabelCreateIssue;
  }
  if (actionType === "internal_todo") {
    return M.actionsPanel.actionLabelInternalTodo;
  }
  return actionType;
}

function payloadString(payload: Record<string, unknown>, key: string): string | null {
  const value = payload[key];
  return typeof value === "string" && value.trim() ? value : null;
}

export { DEFAULT_CREATE_FORM };
