"use client";

import { type FormEvent, useEffect, useState } from "react";

import {
  approveActionProposal,
  createActionProposal,
  fetchActionProposals,
  rejectActionProposal
} from "../lib/api";
import { readOperatorConfig } from "../lib/config";
import type {
  ActionProposal,
  ActionProposalEvidenceRef,
  ActionProposalListResponse,
  ActionProposalType,
  ActionTargetProvider,
  OperatorConfig
} from "../lib/types";
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
  const [config, setConfig] = useState<OperatorConfig | null>(null);
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
    setConfig(readOperatorConfig());
  }, []);

  useEffect(() => {
    if (config === null) {
      return;
    }
    if (!config.workspaceId || !config.ownerEmail || !config.apiKey) {
      setData(null);
      setError(null);
      setStatus("missing");
      return;
    }

    let cancelled = false;
    setStatus("loading");
    setError(null);
    fetchActionProposals(config.workspaceId)
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
        setError(caught instanceof Error ? caught.message : "Request failed");
        setStatus("error");
      });

    return () => {
      cancelled = true;
    };
  }, [config, reloadKey]);

  function updateCreateForm(
    field: keyof ActionProposalCreateFormState,
    value: string
  ) {
    setCreateForm((current) => ({ ...current, [field]: value }));
  }

  async function submitCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!config?.workspaceId || !config.ownerEmail || !config.apiKey) {
      setStatus("missing");
      return;
    }
    const request = buildCreateRequest(createForm);
    if (!request) {
      setError("Title and repository are required for a local GitHub issue proposal.");
      setStatus("error");
      return;
    }

    setError(null);
    setSuccessMessage(null);
    setPendingMutation("create");
    try {
      const response = await createActionProposal(config.workspaceId, request);
      setData((current) => mergeCreatedProposal(current, response.proposal, response.warnings));
      setStatus("ready");
      setCreateForm(DEFAULT_CREATE_FORM);
      setSuccessMessage("Local proposal created. External execution is disabled here.");
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "Request failed");
      setStatus("error");
    } finally {
      setPendingMutation(null);
    }
  }

  async function approve(proposalId: string) {
    if (!config?.workspaceId || !config.ownerEmail || !config.apiKey) {
      setStatus("missing");
      return;
    }

    setError(null);
    setSuccessMessage(null);
    setPendingMutation(`approve:${proposalId}`);
    try {
      const response = await approveActionProposal(config.workspaceId, proposalId);
      setData((current) => mergeUpdatedProposal(current, response.proposal, response.warnings));
      setStatus("ready");
      setSuccessMessage("Approved locally. External execution is not enabled in this UI.");
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "Request failed");
      setStatus("error");
    } finally {
      setPendingMutation(null);
    }
  }

  async function reject(proposalId: string) {
    if (!config?.workspaceId || !config.ownerEmail || !config.apiKey) {
      setStatus("missing");
      return;
    }

    setError(null);
    setSuccessMessage(null);
    setPendingMutation(`reject:${proposalId}`);
    try {
      const response = await rejectActionProposal(config.workspaceId, proposalId, {
        reason: "Rejected locally from product UI."
      });
      setData((current) => mergeUpdatedProposal(current, response.proposal, response.warnings));
      setStatus("ready");
      setSuccessMessage("Rejected locally. Evidence and proposal history remain stored.");
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "Request failed");
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
          <span className="eyebrow">Actions</span>
          <h2 id="action-proposals-title">Action Proposals</h2>
        </div>
        <span className="badge">Local approval</span>
      </div>

      <p className="muted">
        Local approval workflow. Approval records a human decision; this product
        surface does not execute provider writes.
      </p>

      <section className="callout" aria-label="Action proposal capability boundary">
        <strong>Current capability mode</strong>
        <p>
          Local approval: available. External execution: disabled in this UI.
          Live provider writes: not started here. AI generation: not used here.
        </p>
      </section>

      <ActionProposalCreateForm
        form={createForm}
        isPending={pendingMutation === "create"}
        onChange={onCreateFormChange}
        onSubmit={onCreate}
        submitDisabled={!canCreate}
      />

      {successMessage ? <p className="success-text">{successMessage}</p> : null}

      {status === "loading" ? <LoadingState label="Loading action proposals" /> : null}

      {status === "missing" ? (
        <EmptyState
          description="Set the workspace ID, owner email, and operator API key in Settings to load local action proposals."
          title="Workspace settings required"
        />
      ) : null}

      {status === "unsupported" ? (
        <EmptyState
          description="The backend did not report a supported local ActionProposal capability."
          title="Action proposals unsupported"
        />
      ) : null}

      {status === "error" ? (
        <>
          <ErrorState
            description={error ?? "The action proposal request failed."}
            title="Action proposals unavailable"
          />
          <button className="button secondary" onClick={onRetry} type="button">
            Retry
          </button>
        </>
      ) : null}

      {status === "empty" ? (
        <EmptyState
          description="No local action proposals have been created for this workspace yet."
          title="No action proposals yet"
        />
      ) : null}

      {data && status !== "loading" && status !== "missing" && status !== "error" ? (
        <>
          <section className="grid" aria-label="Action proposal summary">
            <StatusCard
              description="Local proposals awaiting review."
              title="Proposed"
              value={String(countByStatus(proposals, "proposed"))}
            />
            <StatusCard
              description="Human-approved local proposals; not executed by this UI."
              title="Approved"
              value={String(countByStatus(proposals, "approved"))}
            />
            <StatusCard
              description="Locally rejected proposals."
              title="Rejected"
              value={String(countByStatus(proposals, "rejected"))}
            />
            <StatusCard
              description="Backend list count."
              title="Total"
              value={String(data.count)}
            />
          </section>

          <section className="work-columns">
            <ProposalList
              onApprove={onApprove}
              onReject={onReject}
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
            <ul className="meta-list" aria-label="Action proposal warnings">
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
        <label htmlFor="proposal-kind">Proposal type</label>
        <select
          id="proposal-kind"
          onChange={(event) => onChange?.("proposalKind", event.target.value)}
          value={form.proposalKind}
        >
          <option value="github_issue">GitHub issue proposal</option>
          <option value="internal_todo">Internal todo proposal</option>
        </select>
      </div>
      <div className="field">
        <label htmlFor="proposal-title">Title</label>
        <input
          id="proposal-title"
          maxLength={500}
          onChange={(event) => onChange?.("title", event.target.value)}
          placeholder="Describe the local action proposal"
          required
          value={form.title}
        />
      </div>
      <div className="field">
        <label htmlFor="proposal-description">Description</label>
        <textarea
          id="proposal-description"
          maxLength={5000}
          onChange={(event) => onChange?.("description", event.target.value)}
          placeholder="Why this proposal exists and what evidence should be reviewed"
          value={form.description}
        />
      </div>
      {isGitHubIssue ? (
        <>
          <div className="field">
            <label htmlFor="proposal-repository">Repository</label>
            <input
              id="proposal-repository"
              onChange={(event) => onChange?.("repositoryFullName", event.target.value)}
              placeholder="owner/repository"
              required
              value={form.repositoryFullName}
            />
          </div>
          <div className="field">
            <label htmlFor="proposal-issue-body">Issue body</label>
            <textarea
              id="proposal-issue-body"
              onChange={(event) => onChange?.("issueBody", event.target.value)}
              placeholder="Body for the proposed future GitHub issue"
              value={form.issueBody}
            />
          </div>
        </>
      ) : null}
      <button className="button" disabled={submitDisabled || isPending} type="submit">
        {isPending ? "Creating local proposal" : "Create local proposal"}
      </button>
      <p className="muted">
        Creating a proposal stores local review state only. It does not create a
        GitHub issue or call a live provider.
      </p>
    </form>
  );
}

function ProposalList({
  onApprove,
  onReject,
  onSelectEvidence,
  pendingMutation,
  proposals
}: {
  onApprove?: (proposalId: string) => void;
  onReject?: (proposalId: string) => void;
  onSelectEvidence?: (evidence: ActionProposalEvidenceRef, title: string) => void;
  pendingMutation: PendingMutation;
  proposals: ActionProposal[];
}) {
  return (
    <section className="work-section" aria-label="Local action proposal list">
      <h3>Local proposals</h3>
      {proposals.length === 0 ? (
        <p className="muted">No proposals returned by the backend.</p>
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
                <dt>Target</dt>
                <dd>{proposal.target_provider}</dd>
              </div>
              <div>
                <dt>Action</dt>
                <dd>{actionLabel(proposal.action_type)}</dd>
              </div>
              <div>
                <dt>Status</dt>
                <dd>{proposal.status}</dd>
              </div>
              <div>
                <dt>Execution</dt>
                <dd>
                  {proposal.execution_started
                    ? "reported by backend"
                    : "not executed by this UI"}
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
    return (
      <p className="muted">
        No target repository, issue title, or internal note returned.
      </p>
    );
  }

  return (
    <dl className="work-meta">
      {repository ? (
        <div>
          <dt>Repository</dt>
          <dd>{repository}</dd>
        </div>
      ) : null}
      {issueTitle ? (
        <div>
          <dt>Target record</dt>
          <dd>{issueTitle}</dd>
        </div>
      ) : null}
      {note ? (
        <div>
          <dt>Internal note</dt>
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
        <dt>Created</dt>
        <dd>{proposal.created_at}</dd>
      </div>
      <div>
        <dt>Updated</dt>
        <dd>{proposal.updated_at}</dd>
      </div>
      {proposal.approved_at ? (
        <div>
          <dt>Approved locally</dt>
          <dd>{proposal.approved_at}</dd>
        </div>
      ) : null}
      {proposal.rejected_at ? (
        <div>
          <dt>Rejected locally</dt>
          <dd>{proposal.rejected_at}</dd>
        </div>
      ) : null}
      {proposal.rejection_reason ? (
        <div>
          <dt>Rejection reason</dt>
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
    return (
      <p className="muted">
        No evidence refs returned by backend for this proposal.
      </p>
    );
  }

  return (
    <div className="actions-row" aria-label={`Evidence for ${proposalTitle}`}>
      {evidenceRefs.map((evidence, index) => (
        <button
          className="button secondary"
          key={`${evidence.kind}-${evidence.source}-${evidence.ref}-${index}`}
          onClick={() => onSelectEvidence?.(evidence, proposalTitle)}
          type="button"
        >
          Evidence: {evidence.ref}
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
    return (
      <p className="muted">
        Approved locally. External execution is disabled in this UI.
      </p>
    );
  }
  if (proposal.status === "rejected") {
    return <p className="muted">Rejected locally. No external action was run.</p>;
  }
  if (proposal.status !== "proposed") {
    return (
      <p className="muted">
        Status returned by backend. This UI did not execute provider work.
      </p>
    );
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
        {approvePending ? "Approving locally" : "Approve locally"}
      </button>
      <button
        className="button secondary"
        disabled={approvePending || rejectPending}
        onClick={() => onReject?.(proposal.id)}
        type="button"
      >
        {rejectPending ? "Rejecting locally" : "Reject locally"}
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
    return "Create GitHub issue";
  }
  if (actionType === "internal_todo") {
    return "Internal todo";
  }
  return actionType;
}

function payloadString(payload: Record<string, unknown>, key: string): string | null {
  const value = payload[key];
  return typeof value === "string" && value.trim() ? value : null;
}

export { DEFAULT_CREATE_FORM };
