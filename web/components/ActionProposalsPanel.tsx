"use client";

import { type FormEvent, useEffect, useState } from "react";

import {
  approveActionProposal,
  bulkApproveActionProposals,
  bulkRejectActionProposals,
  createActionProposal,
  fetchActionProposals,
  rejectActionProposal
} from "../lib/api";
import { M, T } from "../lib/messages";
import { useWorkspaceId } from "../lib/session";
import type {
  ActionProposal,
  ActionProposalBulkResponse,
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
type ProposalStatusFilter = "all" | "proposed" | "approved" | "rejected";
type ProposalOrigin = "briefing" | "github" | "internal";
type ProposalOriginFilter = "all" | ProposalOrigin;
type BulkMutation = "bulk-approve" | "bulk-reject";
type PendingMutation =
  | "create"
  | BulkMutation
  | `approve:${string}`
  | `reject:${string}`
  | null;
type EvidenceSelection = {
  evidence: ActionProposalEvidenceRef;
  title: string;
  count: number;
};

type ProposalGroup = {
  origin: ProposalOrigin;
  title: string;
  description: string;
  proposals: ActionProposal[];
};

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
  onOriginFilterChange?: (filter: ProposalOriginFilter) => void;
  onBulkApprove?: () => void;
  onBulkReject?: () => void;
  onClearSelectedProposals?: () => void;
  onSelectEvidence?: (
    evidence: ActionProposalEvidenceRef,
    title: string,
    count?: number
  ) => void;
  onSelectVisibleProposed?: () => void;
  onStatusFilterChange?: (filter: ProposalStatusFilter) => void;
  onToggleProposalSelection?: (proposalId: string) => void;
  pendingMutation: PendingMutation;
  originFilter?: ProposalOriginFilter;
  selectedProposalIds?: string[];
  selectedEvidence: ActionProposalEvidenceRef | null;
  selectedEvidenceTitle?: string | null;
  selectedEvidenceCount?: number | null;
  statusFilter?: ProposalStatusFilter;
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
  const [selectedEvidenceCount, setSelectedEvidenceCount] = useState<number | null>(null);
  const [selectedProposalIds, setSelectedProposalIds] = useState<string[]>([]);
  const [status, setStatus] = useState<PanelStatus>("loading");
  const [originFilter, setOriginFilter] = useState<ProposalOriginFilter>("all");
  const [statusFilter, setStatusFilter] = useState<ProposalStatusFilter>("proposed");
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

  useEffect(() => {
    const visibleProposedIds = visibleProposedProposalIds(
      data?.proposals ?? [],
      statusFilter,
      originFilter
    );
    setSelectedProposalIds((current) =>
      pruneProposalSelection(current, visibleProposedIds)
    );
  }, [data, originFilter, statusFilter]);

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

  function toggleProposalSelection(proposalId: string) {
    setSelectedProposalIds((current) =>
      current.includes(proposalId)
        ? current.filter((existingId) => existingId !== proposalId)
        : [...current, proposalId]
    );
  }

  function selectVisibleProposed() {
    setSelectedProposalIds(
      visibleProposedProposalIds(data?.proposals ?? [], statusFilter, originFilter)
    );
  }

  async function approveSelected() {
    await mutateSelectedProposals("bulk-approve");
  }

  async function rejectSelected() {
    await mutateSelectedProposals("bulk-reject");
  }

  async function mutateSelectedProposals(mutation: BulkMutation) {
    if (!workspaceId) {
      setStatus("missing");
      return;
    }
    const proposalsToMutate = selectedProposalsForBulkMutation(
      data?.proposals ?? [],
      selectedProposalIds
    );
    if (proposalsToMutate.length === 0) {
      return;
    }

    setError(null);
    setSuccessMessage(null);
    setPendingMutation(mutation);
    try {
      const proposalIds = proposalsToMutate.map((proposal) => proposal.id);
      const response =
        mutation === "bulk-approve"
          ? await bulkApproveActionProposals(workspaceId, {
              proposal_ids: proposalIds
            })
          : await bulkRejectActionProposals(workspaceId, {
              proposal_ids: proposalIds,
              reason: M.actionsPanel.rejectReason
            });
      const outcome = summarizeBulkResponse(response);
      if (outcome.succeeded.length > 0) {
        setData((current) =>
          mergeUpdatedProposals(
            current,
            outcome.succeeded,
            response.warnings
          )
        );
      }
      // Only clear the proposals that actually transitioned; keep failed ones
      // selected so the reviewer can retry them.
      setSelectedProposalIds((current) =>
        current.filter((proposalId) => !outcome.succeededIds.includes(proposalId))
      );
      setStatus("ready");
      if (outcome.failed.length === 0) {
        setSuccessMessage(
          mutation === "bulk-approve"
            ? T.actionsBulkApproveSuccess(outcome.succeeded.length)
            : T.actionsBulkRejectSuccess(outcome.succeeded.length)
        );
      } else if (outcome.succeeded.length === 0) {
        setError(T.actionsBulkAllFailed(outcome.failed.length));
      } else {
        setSuccessMessage(
          mutation === "bulk-approve"
            ? T.actionsBulkApprovePartial(
                outcome.succeeded.length,
                outcome.failed.length
              )
            : T.actionsBulkRejectPartial(
                outcome.succeeded.length,
                outcome.failed.length
              )
        );
        setError(outcome.firstFailureMessage ?? M.common.requestFailed);
      }
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
        setSelectedEvidenceCount(null);
      }}
      onCreate={submitCreate}
      onCreateFormChange={updateCreateForm}
      onReject={reject}
      onRefreshProposals={() => setReloadKey((current) => current + 1)}
      onRetry={() => setReloadKey((current) => current + 1)}
      onOriginFilterChange={setOriginFilter}
      onBulkApprove={approveSelected}
      onBulkReject={rejectSelected}
      onClearSelectedProposals={() => setSelectedProposalIds([])}
      onSelectEvidence={(evidence, title, count) => {
        setSelectedEvidence(evidence);
        setSelectedEvidenceTitle(title);
        setSelectedEvidenceCount(typeof count === "number" ? count : null);
      }}
      onSelectVisibleProposed={selectVisibleProposed}
      onStatusFilterChange={setStatusFilter}
      onToggleProposalSelection={toggleProposalSelection}
      pendingMutation={pendingMutation}
      originFilter={originFilter}
      selectedProposalIds={selectedProposalIds}
      selectedEvidence={selectedEvidence}
      selectedEvidenceTitle={selectedEvidenceTitle}
      selectedEvidenceCount={selectedEvidenceCount}
      statusFilter={statusFilter}
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
  onOriginFilterChange,
  onBulkApprove,
  onBulkReject,
  onClearSelectedProposals,
  onSelectEvidence,
  onSelectVisibleProposed,
  onStatusFilterChange,
  onToggleProposalSelection,
  pendingMutation,
  originFilter = "all",
  selectedProposalIds = [],
  selectedEvidence,
  selectedEvidenceTitle = null,
  selectedEvidenceCount = null,
  statusFilter = "all",
  status,
  successMessage = null
}: ActionProposalsPanelViewProps) {
  const proposals = data?.proposals ?? [];
  const statusFilteredProposals = filterProposalsByStatus(proposals, statusFilter);
  const filteredProposals = filterProposalsByOrigin(
    statusFilteredProposals,
    originFilter
  );
  const visibleProposedIds = proposedProposalIds(filteredProposals);
  const visibleProposedCount = visibleProposedIds.length;
  const selectedProposedCount = selectedProposalIds.filter((proposalId) =>
    visibleProposedIds.includes(proposalId)
  ).length;
  const groups = groupProposalsByOrigin(filteredProposals);
  const orderedProposals = groups.flatMap((group) => group.proposals);
  const defaultEvidenceSelection = firstEvidenceSelection(orderedProposals);
  const drawerEvidence = selectedEvidence ?? defaultEvidenceSelection?.evidence ?? null;
  const drawerTitle = selectedEvidence
    ? selectedEvidenceTitle
    : defaultEvidenceSelection?.title ?? null;
  const drawerCount = selectedEvidence
    ? selectedEvidenceCount
    : defaultEvidenceSelection?.count ?? null;
  const drawerSelectionMode: "default" | "manual" | null = drawerEvidence
    ? selectedEvidence
      ? "manual"
      : "default"
    : null;
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

      {error && status !== "error" ? (
        <p className="error-text" role="alert">
          {error}
        </p>
      ) : null}

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

          <ActionStatusFilter
            activeFilter={statusFilter}
            onChange={onStatusFilterChange}
            proposals={proposals}
          />

          <ActionOriginFilter
            activeFilter={originFilter}
            onChange={onOriginFilterChange}
            proposals={statusFilteredProposals}
          />

          <BulkReviewControls
            onApproveSelected={onBulkApprove}
            onClearSelection={onClearSelectedProposals}
            onRejectSelected={onBulkReject}
            onSelectVisibleProposed={onSelectVisibleProposed}
            pendingMutation={pendingMutation}
            selectedCount={selectedProposedCount}
            visibleProposedCount={visibleProposedCount}
          />

          <section className="work-columns">
            <ProposalList
              groups={groups}
              onApprove={onApprove}
              onReject={onReject}
              onRefreshProposals={onRefreshProposals}
              onSelectEvidence={onSelectEvidence}
              onToggleProposalSelection={onToggleProposalSelection}
              pendingMutation={pendingMutation}
              selectedProposalIds={selectedProposalIds}
              totalProposals={proposals.length}
              visibleProposals={filteredProposals.length}
            />
            <EvidenceDrawer
              evidence={drawerEvidence}
              evidenceCount={drawerCount}
              itemTitle={drawerTitle}
              onClose={selectedEvidence ? onCloseEvidence : undefined}
              selectionMode={drawerSelectionMode}
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

function ActionStatusFilter({
  activeFilter,
  onChange,
  proposals
}: {
  activeFilter: ProposalStatusFilter;
  onChange?: (filter: ProposalStatusFilter) => void;
  proposals: ActionProposal[];
}) {
  const filters: ProposalStatusFilter[] = ["proposed", "approved", "rejected", "all"];
  return (
    <section className="work-section" aria-label={M.actionsPanel.filterLabel}>
      <h3>{M.actionsPanel.filterTitle}</h3>
      <p className="muted">{M.actionsPanel.filterDescription}</p>
      <div className="segmented" role="tablist" aria-label={M.actionsPanel.filterLabel}>
        {filters.map((filter) => (
          <button
            aria-selected={activeFilter === filter}
            className={`segment${activeFilter === filter ? " active" : ""}`}
            key={filter}
            onClick={() => onChange?.(filter)}
            role="tab"
            type="button"
          >
            {filterLabel(filter)} · {filterCount(proposals, filter)}
          </button>
        ))}
      </div>
    </section>
  );
}

function ActionOriginFilter({
  activeFilter,
  onChange,
  proposals
}: {
  activeFilter: ProposalOriginFilter;
  onChange?: (filter: ProposalOriginFilter) => void;
  proposals: ActionProposal[];
}) {
  const filters: ProposalOriginFilter[] = ["all", "briefing", "github", "internal"];
  return (
    <section className="work-section" aria-label={M.actionsPanel.originFilterLabel}>
      <h3>{M.actionsPanel.originFilterTitle}</h3>
      <p className="muted">{M.actionsPanel.originFilterDescription}</p>
      <div className="segmented" role="tablist" aria-label={M.actionsPanel.originFilterLabel}>
        {filters.map((filter) => (
          <button
            aria-selected={activeFilter === filter}
            className={`segment${activeFilter === filter ? " active" : ""}`}
            key={filter}
            onClick={() => onChange?.(filter)}
            role="tab"
            type="button"
          >
            {originFilterLabel(filter)} · {originFilterCount(proposals, filter)}
          </button>
        ))}
      </div>
    </section>
  );
}

function BulkReviewControls({
  onApproveSelected,
  onClearSelection,
  onRejectSelected,
  onSelectVisibleProposed,
  pendingMutation,
  selectedCount,
  visibleProposedCount
}: {
  onApproveSelected?: () => void;
  onClearSelection?: () => void;
  onRejectSelected?: () => void;
  onSelectVisibleProposed?: () => void;
  pendingMutation: PendingMutation;
  selectedCount: number;
  visibleProposedCount: number;
}) {
  const bulkPending = isBulkMutationPending(pendingMutation);
  const hasSelection = selectedCount > 0;
  return (
    <section className="work-section" aria-label={M.actionsPanel.bulkLabel}>
      <h3>{M.actionsPanel.bulkTitle}</h3>
      <p className="muted">{M.actionsPanel.bulkDescription}</p>
      <p className="muted">
        {T.actionsBulkSelection(selectedCount, visibleProposedCount)}
      </p>
      <div className="actions-row">
        <button
          className="button secondary"
          disabled={bulkPending || visibleProposedCount === 0}
          onClick={onSelectVisibleProposed}
          type="button"
        >
          {M.actionsPanel.bulkSelectVisible}
        </button>
        <button
          className="button secondary"
          disabled={bulkPending || !hasSelection}
          onClick={onClearSelection}
          type="button"
        >
          {M.actionsPanel.bulkClearSelection}
        </button>
        <button
          className="button"
          disabled={bulkPending || !hasSelection}
          onClick={onApproveSelected}
          type="button"
        >
          {pendingMutation === "bulk-approve"
            ? M.actionsPanel.bulkApproving
            : M.actionsPanel.bulkApproveSelected}
        </button>
        <button
          className="button secondary"
          disabled={bulkPending || !hasSelection}
          onClick={onRejectSelected}
          type="button"
        >
          {pendingMutation === "bulk-reject"
            ? M.actionsPanel.bulkRejecting
            : M.actionsPanel.bulkRejectSelected}
        </button>
      </div>
    </section>
  );
}

function ProposalList({
  groups,
  onApprove,
  onReject,
  onRefreshProposals,
  onSelectEvidence,
  onToggleProposalSelection,
  pendingMutation,
  selectedProposalIds,
  totalProposals,
  visibleProposals
}: {
  groups: ProposalGroup[];
  onApprove?: (proposalId: string) => void;
  onReject?: (proposalId: string) => void;
  onRefreshProposals?: () => void;
  onSelectEvidence?: (
    evidence: ActionProposalEvidenceRef,
    title: string,
    count?: number
  ) => void;
  onToggleProposalSelection?: (proposalId: string) => void;
  pendingMutation: PendingMutation;
  selectedProposalIds: string[];
  totalProposals: number;
  visibleProposals: number;
}) {
  const bulkPending = isBulkMutationPending(pendingMutation);
  return (
    <section className="work-section" aria-label={M.actionsPanel.listTitle}>
      <h3>{M.actionsPanel.listTitle}</h3>
      {visibleProposals === 0 && totalProposals === 0 ? (
        <p className="muted">{M.actionsPanel.noProposals}</p>
      ) : null}
      {visibleProposals === 0 && totalProposals > 0 ? (
        <p className="muted">{M.actionsPanel.noProposalsForFilter}</p>
      ) : null}
      <div className="proposal-groups" aria-label={M.actionsPanel.groupsLabel}>
        {groups.map((group) => (
          <section
            className="proposal-group"
            key={group.origin}
            aria-label={group.title}
          >
            <div className="proposal-group-header">
              <h4>
                {group.title} · {group.proposals.length}
              </h4>
              <p className="muted">{group.description}</p>
            </div>
            <div className="work-list">
              {group.proposals.map((proposal) => (
                <article className="work-item" key={proposal.id}>
                  <div className="work-item-main">
                    <ProposalSelectionControl
                      disabled={bulkPending}
                      isSelected={selectedProposalIds.includes(proposal.id)}
                      onToggle={onToggleProposalSelection}
                      proposal={proposal}
                    />
                    <span className="badge">{proposal.status}</span>
                    {group.origin === "briefing" ? (
                      <span className="badge badge-origin">
                        {M.actionsPanel.originBriefingBadge}
                      </span>
                    ) : null}
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
        ))}
      </div>
    </section>
  );
}

function ProposalSelectionControl({
  disabled,
  isSelected,
  onToggle,
  proposal
}: {
  disabled: boolean;
  isSelected: boolean;
  onToggle?: (proposalId: string) => void;
  proposal: ActionProposal;
}) {
  if (!isProposalProposed(proposal)) {
    return null;
  }
  return (
    <label className="proposal-selection">
      <input
        checked={isSelected}
        disabled={disabled}
        onChange={() => onToggle?.(proposal.id)}
        type="checkbox"
      />
      <span>{M.actionsPanel.bulkSelectProposal}</span>
    </label>
  );
}

function ProposalPayloadDetails({ proposal }: { proposal: ActionProposal }) {
  const repository = payloadString(proposal.payload, "repository_full_name");
  const issueTitle = payloadString(proposal.payload, "title");
  const note = payloadString(proposal.payload, "note");
  const briefingItemKey = payloadString(proposal.payload, "briefing_item_key");
  const category = payloadString(proposal.payload, "category");
  const severity = payloadString(proposal.payload, "severity");
  const nextStep = payloadString(proposal.payload, "recommended_next_step");
  const relatedEntities = payloadStringList(proposal.payload, "related_entities");

  const hasDetails =
    repository ||
    issueTitle ||
    note ||
    briefingItemKey ||
    category ||
    severity ||
    nextStep ||
    relatedEntities.length > 0;

  if (!hasDetails) {
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
      {briefingItemKey ? (
        <div>
          <dt>{M.actionsPanel.payloadBriefingItem}</dt>
          <dd>{briefingItemKey}</dd>
        </div>
      ) : null}
      {category ? (
        <div>
          <dt>{M.actionsPanel.payloadCategory}</dt>
          <dd>{category}</dd>
        </div>
      ) : null}
      {severity ? (
        <div>
          <dt>{M.actionsPanel.payloadSeverity}</dt>
          <dd>{severity}</dd>
        </div>
      ) : null}
      {nextStep ? (
        <div>
          <dt>{M.actionsPanel.payloadNextStep}</dt>
          <dd>{nextStep}</dd>
        </div>
      ) : null}
      {relatedEntities.length > 0 ? (
        <div>
          <dt>{M.actionsPanel.payloadRelatedEntities}</dt>
          <dd>{relatedEntities.join(", ")}</dd>
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
  onSelectEvidence?: (
    evidence: ActionProposalEvidenceRef,
    title: string,
    count?: number
  ) => void;
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
          onClick={() => onSelectEvidence?.(evidence, proposalTitle, evidenceRefs.length)}
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
  const bulkPending = isBulkMutationPending(pendingMutation);
  return (
    <div className="actions-row">
      <button
        className="button"
        disabled={approvePending || rejectPending || bulkPending}
        onClick={() => onApprove?.(proposal.id)}
        type="button"
      >
        {approvePending ? M.actionsPanel.approving : M.actionsPanel.approve}
      </button>
      <button
        className="button secondary"
        disabled={approvePending || rejectPending || bulkPending}
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

function mergeUpdatedProposals(
  current: ActionProposalListResponse | null,
  proposals: ActionProposal[],
  warnings: string[]
): ActionProposalListResponse | null {
  if (!current) {
    return null;
  }
  const updates = new Map(proposals.map((proposal) => [proposal.id, proposal]));
  return {
    ...current,
    proposals: current.proposals.map((existing) => updates.get(existing.id) ?? existing),
    warnings
  };
}

function countByStatus(proposals: ActionProposal[], status: string): number {
  return proposals.filter((proposal) => proposal.status === status).length;
}

function isProposalProposed(proposal: ActionProposal): boolean {
  return proposal.status === "proposed";
}

function proposedProposalIds(proposals: ActionProposal[]): string[] {
  return proposals.filter(isProposalProposed).map((proposal) => proposal.id);
}

function visibleProposedProposalIds(
  proposals: ActionProposal[],
  statusFilter: ProposalStatusFilter,
  originFilter: ProposalOriginFilter
): string[] {
  return proposedProposalIds(
    filterProposalsByOrigin(
      filterProposalsByStatus(proposals, statusFilter),
      originFilter
    )
  );
}

function pruneProposalSelection(
  proposalIds: string[],
  visibleProposedIds: string[]
): string[] {
  const next = proposalIds.filter((proposalId) =>
    visibleProposedIds.includes(proposalId)
  );
  if (
    next.length === proposalIds.length &&
    next.every((proposalId, index) => proposalId === proposalIds[index])
  ) {
    return proposalIds;
  }
  return next;
}

function selectedProposalsForBulkMutation(
  proposals: ActionProposal[],
  proposalIds: string[]
): ActionProposal[] {
  return proposals.filter(
    (proposal) => proposalIds.includes(proposal.id) && isProposalProposed(proposal)
  );
}

function isBulkMutationPending(pendingMutation: PendingMutation): boolean {
  return pendingMutation === "bulk-approve" || pendingMutation === "bulk-reject";
}

type BulkOutcome = {
  succeeded: ActionProposal[];
  failed: { id: string; message: string }[];
  succeededIds: string[];
  firstFailureMessage: string | null;
};

function summarizeBulkResponse(response: ActionProposalBulkResponse): BulkOutcome {
  const failed = response.failures.map((failure) => ({
    id: failure.proposal_id,
    message: failure.detail
  }));
  return {
    succeeded: response.proposals,
    failed,
    succeededIds: response.proposals.map((proposal) => proposal.id),
    firstFailureMessage: failed[0]?.message ?? null
  };
}

function filterProposalsByStatus(
  proposals: ActionProposal[],
  filter: ProposalStatusFilter
): ActionProposal[] {
  if (filter === "all") {
    return proposals;
  }
  return proposals.filter((proposal) => proposal.status === filter);
}

function filterProposalsByOrigin(
  proposals: ActionProposal[],
  filter: ProposalOriginFilter
): ActionProposal[] {
  if (filter === "all") {
    return proposals;
  }
  return proposals.filter((proposal) => proposalOrigin(proposal) === filter);
}

function filterCount(
  proposals: ActionProposal[],
  filter: ProposalStatusFilter
): number {
  return filter === "all" ? proposals.length : countByStatus(proposals, filter);
}

function filterLabel(filter: ProposalStatusFilter): string {
  if (filter === "proposed") {
    return M.actionsPanel.filterProposed;
  }
  if (filter === "approved") {
    return M.actionsPanel.filterApproved;
  }
  if (filter === "rejected") {
    return M.actionsPanel.filterRejected;
  }
  return M.actionsPanel.filterAll;
}

function originFilterCount(
  proposals: ActionProposal[],
  filter: ProposalOriginFilter
): number {
  if (filter === "all") {
    return proposals.length;
  }
  return proposals.filter((proposal) => proposalOrigin(proposal) === filter).length;
}

function originFilterLabel(filter: ProposalOriginFilter): string {
  if (filter === "briefing") {
    return M.actionsPanel.originFilterBriefing;
  }
  if (filter === "github") {
    return M.actionsPanel.originFilterGithub;
  }
  if (filter === "internal") {
    return M.actionsPanel.originFilterInternal;
  }
  return M.actionsPanel.originFilterAll;
}

function firstEvidenceSelection(
  proposals: ActionProposal[]
): EvidenceSelection | null {
  for (const proposal of proposals) {
    const evidence = proposal.evidence_refs[0];
    if (evidence) {
      return {
        evidence,
        title: proposal.title,
        count: proposal.evidence_refs.length
      };
    }
  }
  return null;
}

function proposalOrigin(proposal: ActionProposal): ProposalOrigin {
  if (
    proposal.briefing_item_id !== null ||
    payloadString(proposal.payload, "source") === "briefing_item"
  ) {
    return "briefing";
  }
  if (proposal.action_type === "create_github_issue") {
    return "github";
  }
  return "internal";
}

function groupProposalsByOrigin(proposals: ActionProposal[]): ProposalGroup[] {
  const order: ProposalOrigin[] = ["briefing", "github", "internal"];
  const meta: Record<ProposalOrigin, { title: string; description: string }> = {
    briefing: {
      title: M.actionsPanel.groupBriefingTitle,
      description: M.actionsPanel.groupBriefingDescription
    },
    github: {
      title: M.actionsPanel.groupGithubTitle,
      description: M.actionsPanel.groupGithubDescription
    },
    internal: {
      title: M.actionsPanel.groupInternalTitle,
      description: M.actionsPanel.groupInternalDescription
    }
  };
  const buckets: Record<ProposalOrigin, ActionProposal[]> = {
    briefing: [],
    github: [],
    internal: []
  };
  for (const proposal of proposals) {
    buckets[proposalOrigin(proposal)].push(proposal);
  }
  return order
    .filter((origin) => buckets[origin].length > 0)
    .map((origin) => ({
      origin,
      title: meta[origin].title,
      description: meta[origin].description,
      proposals: buckets[origin]
    }));
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

function payloadStringList(
  payload: Record<string, unknown>,
  key: string
): string[] {
  const value = payload[key];
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter(
    (entry): entry is string => typeof entry === "string" && entry.trim().length > 0
  );
}

export { DEFAULT_CREATE_FORM, summarizeBulkResponse };
