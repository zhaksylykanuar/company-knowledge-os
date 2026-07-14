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
import { useSession } from "../lib/session";
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
import { MiniHint, MissionStrip } from "./MissionStrip";
import { StatusCard } from "./StatusCard";

type PanelStatus = "empty" | "error" | "loading" | "missing" | "ready" | "unsupported";
type ProposalKind = "github_issue" | "internal_todo";
type ProposalStatusFilter = "all" | "proposed" | "approved" | "rejected";
type ProposalOrigin = "audit" | "briefing" | "github" | "internal";
type ProposalOriginFilter = "all" | ProposalOrigin;
type ProposalAuditSource = "deterministic" | "imported";
type ProposalAuditSourceFilter = "all" | ProposalAuditSource;
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

type ActionReviewReadiness = {
  externalResultReported: number;
  localOnly: number;
  missingEvidence: number;
  pendingDecision: number;
  previewReady: number;
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

type ActionProposalsPanelProps = {
  initialAuditSourceFilter?: string | null;
  initialOriginFilter?: string | null;
  initialStatusFilter?: string | null;
};

type ActionProposalsPanelViewProps = {
  canCreateProposals?: boolean;
  canReviewProposals?: boolean;
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
  auditSourceFilter?: ProposalAuditSourceFilter;
  onAuditSourceFilterChange?: (filter: ProposalAuditSourceFilter) => void;
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

export function actionCapabilitiesForRole(role: string | null): {
  canCreateProposals: boolean;
  canReviewProposals: boolean;
} {
  const canReviewProposals = role === "owner" || role === "admin";
  return {
    canCreateProposals: canReviewProposals || role === "member",
    canReviewProposals
  };
}

export function ActionProposalsPanel({
  initialAuditSourceFilter = null,
  initialOriginFilter = null,
  initialStatusFilter = null
}: ActionProposalsPanelProps = {}) {
  const session = useSession();
  const workspaceId = session?.workspaceId ?? null;
  const selectedRole =
    session?.workspaces.find((workspace) => workspace.id === workspaceId)?.role ?? null;
  const capabilities = actionCapabilitiesForRole(selectedRole);
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
  const [auditSourceFilter, setAuditSourceFilter] =
    useState<ProposalAuditSourceFilter>(
      normalizeAuditSourceFilter(initialAuditSourceFilter)
    );
  const [originFilter, setOriginFilter] = useState<ProposalOriginFilter>(
    normalizeOriginFilter(initialOriginFilter)
  );
  const [statusFilter, setStatusFilter] = useState<ProposalStatusFilter>(
    normalizeStatusFilter(initialStatusFilter)
  );
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  useEffect(() => {
    setAuditSourceFilter(normalizeAuditSourceFilter(initialAuditSourceFilter));
    setOriginFilter(normalizeOriginFilter(initialOriginFilter));
    setStatusFilter(normalizeStatusFilter(initialStatusFilter));
  }, [initialAuditSourceFilter, initialOriginFilter, initialStatusFilter]);

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
    fetchActionProposals(workspaceId, {
      limit: 100,
      ...(statusFilter === "all" ? {} : { status: statusFilter })
    })
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
  }, [workspaceId, reloadKey, statusFilter]);

  useEffect(() => {
    const visibleProposedIds = visibleProposedProposalIds(
      data?.proposals ?? [],
      statusFilter,
      originFilter,
      auditSourceFilter
    );
    setSelectedProposalIds((current) =>
      pruneProposalSelection(current, visibleProposedIds)
    );
  }, [auditSourceFilter, data, originFilter, statusFilter]);

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
    if (!capabilities.canCreateProposals) {
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
    if (!capabilities.canReviewProposals) {
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
    if (!capabilities.canReviewProposals) {
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
      visibleProposedProposalIds(
        data?.proposals ?? [],
        statusFilter,
        originFilter,
        auditSourceFilter
      )
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
    if (!capabilities.canReviewProposals) {
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
      canCreateProposals={capabilities.canCreateProposals}
      canReviewProposals={capabilities.canReviewProposals}
      createForm={createForm}
      data={data}
      error={error}
      onApprove={capabilities.canReviewProposals ? approve : undefined}
      onCloseEvidence={() => {
        setSelectedEvidence(null);
        setSelectedEvidenceTitle(null);
        setSelectedEvidenceCount(null);
      }}
      onCreate={capabilities.canCreateProposals ? submitCreate : undefined}
      onCreateFormChange={
        capabilities.canCreateProposals ? updateCreateForm : undefined
      }
      onReject={capabilities.canReviewProposals ? reject : undefined}
      onRefreshProposals={() => setReloadKey((current) => current + 1)}
      onRetry={() => setReloadKey((current) => current + 1)}
      onOriginFilterChange={setOriginFilter}
      onBulkApprove={
        capabilities.canReviewProposals ? approveSelected : undefined
      }
      onBulkReject={
        capabilities.canReviewProposals ? rejectSelected : undefined
      }
      onClearSelectedProposals={
        capabilities.canReviewProposals
          ? () => setSelectedProposalIds([])
          : undefined
      }
      onSelectEvidence={(evidence, title, count) => {
        setSelectedEvidence(evidence);
        setSelectedEvidenceTitle(title);
        setSelectedEvidenceCount(typeof count === "number" ? count : null);
      }}
      onSelectVisibleProposed={
        capabilities.canReviewProposals ? selectVisibleProposed : undefined
      }
      onAuditSourceFilterChange={setAuditSourceFilter}
      onStatusFilterChange={setStatusFilter}
      onToggleProposalSelection={
        capabilities.canReviewProposals ? toggleProposalSelection : undefined
      }
      pendingMutation={pendingMutation}
      auditSourceFilter={auditSourceFilter}
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
  canCreateProposals = true,
  canReviewProposals = true,
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
  onAuditSourceFilterChange,
  onStatusFilterChange,
  onToggleProposalSelection,
  pendingMutation,
  auditSourceFilter = "all",
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
  const originFilteredProposals = filterProposalsByOrigin(
    statusFilteredProposals,
    originFilter
  );
  const filteredProposals =
    originFilter === "audit"
      ? filterProposalsByAuditSource(originFilteredProposals, auditSourceFilter)
      : originFilteredProposals;
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
  const mission = decisionRoomMission(
    filteredProposals,
    proposals.length,
    canCreateProposals,
    canReviewProposals
  );

  return (
    <section className="panel action-proposals" aria-labelledby="action-proposals-title">
      <div className="section-header decision-room-header">
        <div>
          <span className="eyebrow">{M.actionsPanel.eyebrow}</span>
          <h2 id="action-proposals-title">Очередь решений</h2>
        </div>
        <span className="badge">{M.actionsPanel.badgeLocalApproval}</span>
      </div>

      {data && status !== "error" && status !== "loading" && status !== "missing" ? (
        <MissionStrip
          action={mission.action}
          current={mission.current}
          outcome={mission.outcome}
          details={
            <>
              <p>{T.actionsCapability()}</p>
              <p>Внешнее действие не начнётся без отдельного подтверждения.</p>
            </>
          }
        />
      ) : null}

      <DecisionRoomAccessHint
        canCreateProposals={canCreateProposals}
        canReviewProposals={canReviewProposals}
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
          <DecisionRoomSummary proposals={proposals} />

          <details className="decision-room-disclosure decision-room-filters">
            <summary>
              <span>Фильтры очереди</span>
              <small>{decisionRoomFilterSummary(statusFilter, originFilter)}</small>
            </summary>
            <div className="decision-room-disclosure-body">
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

              {originFilter === "audit" ? (
                <ActionAuditSourceFilter
                  activeFilter={auditSourceFilter}
                  onChange={onAuditSourceFilterChange}
                  proposals={statusFilteredProposals}
                />
              ) : null}

              {canReviewProposals && selectedProposedCount === 0 ? (
                <button
                  className="button secondary decision-room-select-visible"
                  disabled={visibleProposedCount === 0}
                  onClick={onSelectVisibleProposed}
                  type="button"
                >
                  {M.actionsPanel.bulkSelectVisible}
                </button>
              ) : null}
            </div>
          </details>

          {canReviewProposals && selectedProposedCount > 0 ? (
            <BulkReviewControls
              onApproveSelected={onBulkApprove}
              onClearSelection={onClearSelectedProposals}
              onRejectSelected={onBulkReject}
              onSelectVisibleProposed={onSelectVisibleProposed}
              pendingMutation={pendingMutation}
              selectedCount={selectedProposedCount}
              visibleProposedCount={visibleProposedCount}
            />
          ) : null}

          <section className="work-columns">
            <ProposalList
              canReviewProposals={canReviewProposals}
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

          {canCreateProposals ? (
            <details className="decision-room-disclosure decision-room-create">
              <summary>
                <span>Предложить новое действие</span>
                <small>Сохранится локально и ничего не выполнит само</small>
              </summary>
              <div className="decision-room-disclosure-body">
                <ActionProposalCreateForm
                  form={createForm}
                  isPending={pendingMutation === "create"}
                  onChange={onCreateFormChange}
                  onSubmit={onCreate}
                  submitDisabled={!canCreate}
                />
              </div>
            </details>
          ) : null}

          {canReviewProposals ? (
            <details className="decision-room-disclosure decision-room-readiness">
              <summary>
                <span>Готовность и контроль</span>
                <small>Предпросмотр, доказательства и результаты</small>
              </summary>
              <div className="decision-room-disclosure-body">
                <ActionReviewReadinessPanel proposals={proposals} />
              </div>
            </details>
          ) : null}

          {data.warnings.length > 0 ? (
            <details className="decision-room-disclosure decision-room-warnings">
              <summary>
                <span>{M.common.warnings}</span>
                <small>{data.warnings.length}</small>
              </summary>
              <ul className="meta-list" aria-label={M.common.warnings}>
                {data.warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            </details>
          ) : null}
        </>
      ) : null}
    </section>
  );
}

function DecisionRoomAccessHint({
  canCreateProposals,
  canReviewProposals
}: {
  canCreateProposals: boolean;
  canReviewProposals: boolean;
}) {
  if (canReviewProposals) {
    return null;
  }
  if (canCreateProposals) {
    return (
      <div className="decision-room-access-hint">
        <span className="badge">Создание доступно</span>
        <MiniHint label="Кто может принимать решения?">
          <p>
            Вы можете создавать локальные предложения. Принимать, отклонять и
            выполнять их может владелец или администратор компании.
          </p>
        </MiniHint>
      </div>
    );
  }
  return (
    <div className="decision-room-access-hint">
      <span className="badge">Только просмотр</span>
      <MiniHint label="Что доступно в режиме просмотра?">
        <p>
          Можно изучать предложения и доказательства, но нельзя создавать,
          принимать, отклонять или выполнять решения.
        </p>
      </MiniHint>
    </div>
  );
}

function DecisionRoomSummary({ proposals }: { proposals: ActionProposal[] }) {
  return (
    <dl className="decision-room-summary" aria-label={M.actionsPanel.summaryLabel}>
      <div className="decision-room-summary-item decision-room-summary-item--pending">
        <dt>Ждут решения</dt>
        <dd>{countByStatus(proposals, "proposed")}</dd>
      </div>
      <div className="decision-room-summary-item">
        <dt>Приняты</dt>
        <dd>{countAcceptedProposals(proposals)}</dd>
      </div>
      <div className="decision-room-summary-item">
        <dt>Отклонены</dt>
        <dd>{countByStatus(proposals, "rejected")}</dd>
      </div>
    </dl>
  );
}

function decisionRoomFilterSummary(
  statusFilter: ProposalStatusFilter,
  originFilter: ProposalOriginFilter
): string {
  return `${filterLabel(statusFilter)} · ${originFilterLabel(originFilter)}`;
}

function decisionRoomMission(
  visibleProposals: ActionProposal[],
  totalProposalCount: number,
  canCreateProposals: boolean,
  canReviewProposals: boolean
): { action: string; current: string; outcome: string } {
  const pendingDecisionCount = countByStatus(visibleProposals, "proposed");
  const approvedCount = countByStatus(visibleProposals, "approved");
  const failedCount = countByStatus(visibleProposals, "failed");
  const executedCount = countByStatus(visibleProposals, "executed");
  const previewReadyCount = visibleProposals.filter(
    isPreviewReadyGithubIssueProposal
  ).length;

  if (failedCount > 0) {
    return {
      action: "Открыть «Детали и историю»",
      current: executionAttentionLabel(failedCount),
      outcome: "Увидите причину и сохранённую квитанцию"
    };
  }
  if (pendingDecisionCount > 0) {
    if (canReviewProposals) {
      return {
        action: "«Принять» или «Отклонить»",
        current: pendingDecisionLabel(pendingDecisionCount),
        outcome: "Решение сохранится локально"
      };
    }
    return {
      action: "Открыть доказательства",
      current: pendingDecisionLabel(pendingDecisionCount),
      outcome: "Вы увидите основание решения"
    };
  }
  if (previewReadyCount > 0 && canReviewProposals) {
    return {
      action: "«Подготовить предпросмотр» в принятом решении",
      current: acceptedDecisionLabel(previewReadyCount),
      outcome: "Увидите точный запрос без отправки"
    };
  }
  if (approvedCount > 0) {
    return {
      action: "Проверить основание и следующий шаг",
      current: acceptedDecisionStatusLabel(approvedCount),
      outcome: "Увидите, что доступно после принятия"
    };
  }
  if (executedCount > 0) {
    return {
      action: "Открыть «Детали и историю»",
      current: savedResultLabel(executedCount),
      outcome: "Проверите итог и историю выполнения"
    };
  }
  if (visibleProposals.length > 0) {
    return {
      action: "Открыть доказательства или историю",
      current: `${visibleProposals.length} ${visibleProposals.length === 1 ? "решение в выбранном разделе" : "решения в выбранном разделе"}`,
      outcome: "Увидите основание и сохранённый статус"
    };
  }
  if (totalProposalCount > 0) {
    return {
      action: "Открыть «Фильтры очереди»",
      current: "В выбранном фильтре решений нет",
      outcome: "Вернёте нужные решения в очередь"
    };
  }
  if (canCreateProposals) {
    return {
      action: "«Предложить новое действие»",
      current: "Очередь решений пуста",
      outcome: "Предложение появится в очереди"
    };
  }
  return {
    action: "Выбрать другой раздел",
    current: "В выбранном разделе решений нет",
    outcome: "Вы продолжите работу с компанией"
  };
}

function acceptedDecisionLabel(count: number): string {
  const lastTwoDigits = count % 100;
  const lastDigit = count % 10;
  if (lastTwoDigits < 11 || lastTwoDigits > 14) {
    if (lastDigit === 1) {
      return `${count} принятое решение готово к следующему шагу`;
    }
    if (lastDigit >= 2 && lastDigit <= 4) {
      return `${count} принятых решения готовы к следующему шагу`;
    }
  }
  return `${count} принятых решений готовы к следующему шагу`;
}

function acceptedDecisionStatusLabel(count: number): string {
  const lastTwoDigits = count % 100;
  const lastDigit = count % 10;
  if ((lastTwoDigits < 11 || lastTwoDigits > 14) && lastDigit === 1) {
    return `${count} решение принято`;
  }
  if (
    (lastTwoDigits < 11 || lastTwoDigits > 14) &&
    lastDigit >= 2 &&
    lastDigit <= 4
  ) {
    return `${count} решения приняты`;
  }
  return `${count} решений приняты`;
}

function executionAttentionLabel(count: number): string {
  return count % 10 === 1 && count % 100 !== 11
    ? `${count} выполнение требует внимания`
    : `${count} выполнений требуют внимания`;
}

function savedResultLabel(count: number): string {
  return count % 10 === 1 && count % 100 !== 11
    ? `${count} результат сохранён`
    : `${count} результатов сохранены`;
}

function countAcceptedProposals(proposals: ActionProposal[]): number {
  return proposals.filter((proposal) =>
    ["approved", "executed", "failed"].includes(proposal.status)
  ).length;
}

function pendingDecisionLabel(count: number): string {
  const lastTwoDigits = count % 100;
  const lastDigit = count % 10;
  if (lastTwoDigits >= 11 && lastTwoDigits <= 14) {
    return `${count} решений ждут проверки`;
  }
  if (lastDigit === 1) {
    return `${count} решение ждёт проверки`;
  }
  if (lastDigit >= 2 && lastDigit <= 4) {
    return `${count} решения ждут проверки`;
  }
  return `${count} решений ждут проверки`;
}

function ActionReviewReadinessPanel({ proposals }: { proposals: ActionProposal[] }) {
  const readiness = summarizeActionReviewReadiness(proposals);
  return (
    <section className="work-section" aria-label={M.actionsPanel.readinessLabel}>
      <h3>{M.actionsPanel.readinessTitle}</h3>
      <p className="muted">{M.actionsPanel.readinessDescription}</p>
      <section className="grid" aria-label={M.actionsPanel.readinessLabel}>
        <StatusCard
          description={M.actionsPanel.readinessPendingDescription}
          title={M.actionsPanel.readinessPendingTitle}
          value={String(readiness.pendingDecision)}
        />
        <StatusCard
          description={M.actionsPanel.readinessPreviewDescription}
          title={M.actionsPanel.readinessPreviewTitle}
          value={String(readiness.previewReady)}
        />
        <StatusCard
          description={M.actionsPanel.readinessLocalOnlyDescription}
          title={M.actionsPanel.readinessLocalOnlyTitle}
          value={String(readiness.localOnly)}
        />
        <StatusCard
          description={M.actionsPanel.readinessMissingEvidenceDescription}
          title={M.actionsPanel.readinessMissingEvidenceTitle}
          value={String(readiness.missingEvidence)}
        />
        <StatusCard
          description={M.actionsPanel.readinessExternalResultDescription}
          title={M.actionsPanel.readinessExternalResultTitle}
          value={String(readiness.externalResultReported)}
        />
      </section>
      <p className="muted">
        {T.actionsReadinessNextStep(
          readiness.pendingDecision,
          readiness.previewReady,
          readiness.missingEvidence,
          readiness.externalResultReported
        )}
      </p>
      <p className="muted">{M.actionsPanel.readinessBoundary}</p>
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

function normalizeStatusFilter(value: string | null | undefined): ProposalStatusFilter {
  if (
    value === "all" ||
    value === "approved" ||
    value === "proposed" ||
    value === "rejected"
  ) {
    return value;
  }
  return "proposed";
}

function normalizeOriginFilter(value: string | null | undefined): ProposalOriginFilter {
  if (
    value === "all" ||
    value === "audit" ||
    value === "briefing" ||
    value === "github" ||
    value === "internal"
  ) {
    return value;
  }
  return "all";
}

function normalizeAuditSourceFilter(
  value: string | null | undefined
): ProposalAuditSourceFilter {
  if (value === "deterministic" || value === "imported" || value === "all") {
    return value;
  }
  return "all";
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
  const filters: ProposalOriginFilter[] = [
    "all",
    "audit",
    "briefing",
    "github",
    "internal"
  ];
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

function ActionAuditSourceFilter({
  activeFilter,
  onChange,
  proposals
}: {
  activeFilter: ProposalAuditSourceFilter;
  onChange?: (filter: ProposalAuditSourceFilter) => void;
  proposals: ActionProposal[];
}) {
  const filters: ProposalAuditSourceFilter[] = ["all", "deterministic", "imported"];
  return (
    <section className="work-section" aria-label={M.actionsPanel.auditSourceFilterLabel}>
      <h3>{M.actionsPanel.auditSourceFilterTitle}</h3>
      <p className="muted">{M.actionsPanel.auditSourceFilterDescription}</p>
      <div
        className="segmented"
        role="tablist"
        aria-label={M.actionsPanel.auditSourceFilterLabel}
      >
        {filters.map((filter) => (
          <button
            aria-selected={activeFilter === filter}
            className={`segment${activeFilter === filter ? " active" : ""}`}
            key={filter}
            onClick={() => onChange?.(filter)}
            role="tab"
            type="button"
          >
            {auditSourceFilterLabel(filter)} · {auditSourceFilterCount(proposals, filter)}
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
  return (
    <section
      className="decision-room-bulk-bar"
      aria-label={M.actionsPanel.bulkLabel}
      aria-live="polite"
    >
      <strong>
        {T.actionsBulkSelection(selectedCount, visibleProposedCount)}
      </strong>
      <div className="actions-row decision-room-bulk-actions">
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
          disabled={bulkPending}
          onClick={onClearSelection}
          type="button"
        >
          {M.actionsPanel.bulkClearSelection}
        </button>
        <button
          className="button"
          disabled={bulkPending}
          onClick={onApproveSelected}
          type="button"
        >
          {pendingMutation === "bulk-approve"
            ? M.actionsPanel.bulkApproving
            : M.actionsPanel.bulkApproveSelected}
        </button>
        <button
          className="button secondary"
          disabled={bulkPending}
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
  canReviewProposals,
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
  canReviewProposals: boolean;
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
              <MiniHint label={`Что входит в раздел «${group.title}»?`}>
                <p>{group.description}</p>
              </MiniHint>
            </div>
            <div className="work-list">
              {group.proposals.map((proposal) => (
                <article className="work-item decision-room-card" key={proposal.id}>
                  <div className="work-item-main">
                    {canReviewProposals ? (
                      <ProposalSelectionControl
                        disabled={bulkPending}
                        isSelected={selectedProposalIds.includes(proposal.id)}
                        onToggle={onToggleProposalSelection}
                        proposal={proposal}
                      />
                    ) : null}
                    <span
                      className={`badge decision-room-status decision-room-status--${proposalStatusTone(proposal.status)}`}
                    >
                      {proposalStatusLabel(proposal.status)}
                    </span>
                    {group.origin === "audit" ? (
                      <>
                        <span className="badge badge-origin">
                          {M.actionsPanel.originAuditBadge}
                        </span>
                        <span className="badge badge-origin">
                          {auditSourceBadge(proposal)}
                        </span>
                      </>
                    ) : null}
                    {group.origin === "briefing" ? (
                      <span className="badge badge-origin">
                        {M.actionsPanel.originBriefingBadge}
                      </span>
                    ) : null}
                    <h4>{proposal.title}</h4>
                  </div>
                  {proposal.description ? (
                    <p className="muted decision-room-card-description">
                      {proposal.description}
                    </p>
                  ) : null}
                  <p className="decision-room-effect">
                    <strong>Что изменится:</strong> {actionLabel(proposal.action_type)}
                  </p>
                  <ActionEvidenceButtons
                    evidenceRefs={proposal.evidence_refs}
                    onSelectEvidence={onSelectEvidence}
                    proposalTitle={proposal.title}
                  />
                  {canReviewProposals ? (
                    <ProposalActions
                      onApprove={onApprove}
                      onReject={onReject}
                      pendingMutation={pendingMutation}
                      proposal={proposal}
                    />
                  ) : null}
                  {canReviewProposals ? (
                    <ProposalNextStep
                      onRefreshProposals={onRefreshProposals}
                      proposal={proposal}
                    />
                  ) : null}
                  <details className="decision-room-card-details">
                    <summary>Детали и история</summary>
                    <div className="decision-room-card-details-body">
                      <dl className="work-meta">
                        <div>
                          <dt>{M.actionsPanel.metaTarget}</dt>
                          <dd>{proposalTargetLabel(proposal.target_provider)}</dd>
                        </div>
                        <div>
                          <dt>{M.actionsPanel.metaAction}</dt>
                          <dd>{actionLabel(proposal.action_type)}</dd>
                        </div>
                        <div>
                          <dt>{M.actionsPanel.metaStatus}</dt>
                          <dd>{proposalStatusLabel(proposal.status)}</dd>
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
                      {canReviewProposals &&
                      !isPreviewReadyGithubIssueProposal(proposal) ? (
                        <ActionExecutionControls
                          onRefresh={onRefreshProposals}
                          proposal={proposal}
                        />
                      ) : null}
                      {proposal.warnings.length > 0 ? (
                        <ul className="meta-list">
                          {proposal.warnings.map((warning) => (
                            <li key={warning}>{warning}</li>
                          ))}
                        </ul>
                      ) : null}
                    </div>
                  </details>
                </article>
              ))}
            </div>
          </section>
        ))}
      </div>
    </section>
  );
}

function ProposalNextStep({
  onRefreshProposals,
  proposal
}: {
  onRefreshProposals?: () => void;
  proposal: ActionProposal;
}) {
  if (proposal.status !== "approved") {
    return null;
  }
  if (isPreviewReadyGithubIssueProposal(proposal)) {
    return (
      <div className="decision-room-next-step">
        <span>Следующий шаг</span>
        <ActionExecutionControls
          onRefresh={onRefreshProposals}
          proposal={proposal}
        />
      </div>
    );
  }
  return (
    <div className="decision-room-next-step decision-room-next-step--local">
      <span>{isLocalOnlyProposal(proposal) ? "Решение принято" : "Нужно основание"}</span>
      <p>
        {isLocalOnlyProposal(proposal)
          ? "Это действие остаётся внутри FounderOS. История доступна в деталях."
          : "До внешнего предпросмотра проверьте доказательства и готовность ниже."}
      </p>
    </div>
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
  const auditSource = proposalAuditSource(proposal);
  const repository = payloadString(proposal.payload, "repository_full_name");
  const issueTitle = payloadString(proposal.payload, "title");
  const note = payloadString(proposal.payload, "note");
  const briefingItemKey = payloadString(proposal.payload, "briefing_item_key");
  const category = payloadString(proposal.payload, "category");
  const severity = payloadString(proposal.payload, "severity");
  const nextStep = payloadString(proposal.payload, "recommended_next_step");
  const relatedEntities = payloadStringList(proposal.payload, "related_entities");
  const auditArea = payloadString(proposal.payload, "area_candidate");
  const auditActivity = payloadString(proposal.payload, "activity_bucket");

  const hasDetails =
    auditSource !== null ||
    repository ||
    issueTitle ||
    note ||
    briefingItemKey ||
    category ||
    severity ||
    nextStep ||
    auditArea ||
    auditActivity ||
    relatedEntities.length > 0;

  if (!hasDetails) {
    return <p className="muted">{M.actionsPanel.payloadNone}</p>;
  }

  return (
    <dl className="work-meta">
      {auditSource ? (
        <div>
          <dt>{M.actionsPanel.payloadAuditSource}</dt>
          <dd>{auditSourceLabel(auditSource)}</dd>
        </div>
      ) : null}
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
      {auditArea ? (
        <div>
          <dt>{M.actionsPanel.payloadAuditArea}</dt>
          <dd>{auditArea}</dd>
        </div>
      ) : null}
      {auditActivity ? (
        <div>
          <dt>{M.actionsPanel.payloadAuditActivity}</dt>
          <dd>{auditActivity}</dd>
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
    <details className="decision-room-evidence">
      <summary>
        <span>Доказательства</span>
        <small>{evidenceRefs.length}</small>
      </summary>
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
    </details>
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
  if (proposal.status !== "proposed") {
    return null;
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

function summarizeActionReviewReadiness(
  proposals: ActionProposal[]
): ActionReviewReadiness {
  return proposals.reduce<ActionReviewReadiness>(
    (summary, proposal) => {
      if (proposal.status === "proposed") {
        summary.pendingDecision += 1;
      }
      if (isPreviewReadyGithubIssueProposal(proposal)) {
        summary.previewReady += 1;
      }
      if (isLocalOnlyProposal(proposal)) {
        summary.localOnly += 1;
      }
      if (proposal.evidence_refs.length === 0) {
        summary.missingEvidence += 1;
      }
      if (proposal.execution_started) {
        summary.externalResultReported += 1;
      }
      return summary;
    },
    {
      externalResultReported: 0,
      localOnly: 0,
      missingEvidence: 0,
      pendingDecision: 0,
      previewReady: 0
    }
  );
}

function isPreviewReadyGithubIssueProposal(proposal: ActionProposal): boolean {
  return (
    proposal.status === "approved" &&
    proposal.action_type === "create_github_issue" &&
    proposal.target_provider === "github" &&
    proposal.evidence_refs.length > 0 &&
    !proposal.execution_started
  );
}

function isLocalOnlyProposal(proposal: ActionProposal): boolean {
  return proposal.action_type === "internal_todo" || proposal.target_provider === "internal";
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
  originFilter: ProposalOriginFilter,
  auditSourceFilter: ProposalAuditSourceFilter
): string[] {
  const originFilteredProposals = filterProposalsByOrigin(
    filterProposalsByStatus(proposals, statusFilter),
    originFilter
  );
  const filteredProposals =
    originFilter === "audit"
      ? filterProposalsByAuditSource(originFilteredProposals, auditSourceFilter)
      : originFilteredProposals;
  return proposedProposalIds(filteredProposals);
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

function filterProposalsByAuditSource(
  proposals: ActionProposal[],
  filter: ProposalAuditSourceFilter
): ActionProposal[] {
  if (filter === "all") {
    return proposals.filter((proposal) => proposalOrigin(proposal) === "audit");
  }
  return proposals.filter((proposal) => proposalAuditSource(proposal) === filter);
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
  if (filter === "audit") {
    return M.actionsPanel.originFilterAudit;
  }
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

function auditSourceFilterCount(
  proposals: ActionProposal[],
  filter: ProposalAuditSourceFilter
): number {
  if (filter === "all") {
    return proposals.filter((proposal) => proposalOrigin(proposal) === "audit").length;
  }
  return proposals.filter((proposal) => proposalAuditSource(proposal) === filter).length;
}

function auditSourceFilterLabel(filter: ProposalAuditSourceFilter): string {
  if (filter === "deterministic") {
    return M.actionsPanel.auditSourceFilterDeterministic;
  }
  if (filter === "imported") {
    return M.actionsPanel.auditSourceFilterImported;
  }
  return M.actionsPanel.auditSourceFilterAll;
}

function auditSourceLabel(source: ProposalAuditSource): string {
  return source === "imported"
    ? M.actionsPanel.auditSourceImported
    : M.actionsPanel.auditSourceDeterministic;
}

function auditSourceBadge(proposal: ActionProposal): string {
  const source = proposalAuditSource(proposal);
  if (source === "imported") {
    return M.actionsPanel.originAuditImportedBadge;
  }
  return M.actionsPanel.originAuditDeterministicBadge;
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
  if (proposalAuditSource(proposal) !== null) {
    return "audit";
  }
  const source = payloadString(proposal.payload, "source");
  if (
    proposal.briefing_item_id !== null ||
    source === "briefing_item"
  ) {
    return "briefing";
  }
  if (proposal.action_type === "create_github_issue") {
    return "github";
  }
  return "internal";
}

function proposalAuditSource(proposal: ActionProposal): ProposalAuditSource | null {
  const source = payloadString(proposal.payload, "source");
  if (source === "repo_audit") {
    return "deterministic";
  }
  if (source === "repo_audit_import") {
    return "imported";
  }
  return null;
}

function groupProposalsByOrigin(proposals: ActionProposal[]): ProposalGroup[] {
  const order: ProposalOrigin[] = ["audit", "briefing", "github", "internal"];
  const meta: Record<ProposalOrigin, { title: string; description: string }> = {
    audit: {
      title: M.actionsPanel.groupAuditTitle,
      description: M.actionsPanel.groupAuditDescription
    },
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
    audit: [],
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

function proposalStatusLabel(status: string): string {
  if (status === "proposed") {
    return "Ждёт решения";
  }
  if (status === "approved") {
    return "Принято";
  }
  if (status === "rejected") {
    return "Отклонено";
  }
  if (status === "executed") {
    return "Выполнено";
  }
  if (status === "failed") {
    return "Ошибка выполнения";
  }
  return "Неизвестный статус";
}

function proposalStatusTone(status: string): string {
  if (status === "proposed") {
    return "pending";
  }
  if (status === "approved") {
    return "approved";
  }
  if (status === "rejected") {
    return "rejected";
  }
  if (status === "executed") {
    return "executed";
  }
  if (status === "failed") {
    return "failed";
  }
  return "unknown";
}

function proposalTargetLabel(target: string): string {
  if (target === "github") {
    return "GitHub";
  }
  if (target === "internal") {
    return "Внутри FounderOS";
  }
  return "Другой контур";
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

export {
  DEFAULT_CREATE_FORM,
  summarizeActionReviewReadiness,
  summarizeBulkResponse
};
