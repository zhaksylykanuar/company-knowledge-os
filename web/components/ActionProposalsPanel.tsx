"use client";

import { type FormEvent, useEffect, useRef, useState } from "react";

import {
  ApiRequestError,
  bulkApproveActionProposals,
  bulkRejectActionProposals,
  createActionProposal,
  fetchActionProposal,
  fetchActionProposals
} from "../lib/api";
import {
  createLocalActionDecisionIdempotencyKey,
  isAmbiguousLocalActionDecisionFailure,
  submitLocalActionDecisionWithOneRetry
} from "../lib/action-proposal-decision";
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
import {
  ActionExecutionControls,
  type ActionExecutionOutcome
} from "./ActionExecutionControls";
import { EmptyState } from "./EmptyState";
import { ErrorState } from "./ErrorState";
import { EvidenceDrawer } from "./EvidenceDrawer";
import { LoadingState } from "./LoadingState";
import { MiniHint } from "./MissionStrip";
import { SourceLink } from "./SourceLink";
import { StatusCard } from "./StatusCard";

type PanelStatus =
  | "empty"
  | "error"
  | "forbidden"
  | "loading"
  | "missing"
  | "not_found"
  | "ready"
  | "unsupported";
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

type MutationError = {
  message: string;
  scope: "bulk" | "create" | `proposal:${string}`;
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
  initialProposalId?: string | null;
  initialStatusFilter?: string | null;
};

type ActionProposalsPanelViewProps = {
  canCreateProposals?: boolean;
  canReviewProposals?: boolean;
  createForm: ActionProposalCreateFormState;
  data: ActionProposalListResponse | null;
  error: string | null;
  executionBusyProposalId?: string | null;
  isRefreshing?: boolean;
  mutationError?: MutationError | null;
  onApprove?: (proposalId: string) => void;
  onCloseEvidence?: () => void;
  onCreate?: (event: FormEvent<HTMLFormElement>) => void;
  onCreateFormChange?: (
    field: keyof ActionProposalCreateFormState,
    value: string
  ) => void;
  onReject?: (proposalId: string) => void;
  onRefreshProposals?: () => void;
  onSelectProposal?: (proposalId: string) => void;
  onRetry?: () => void;
  onOriginFilterChange?: (filter: ProposalOriginFilter) => void;
  onBulkApprove?: () => void;
  onBulkReject?: () => void;
  onClearSelectedProposals?: () => void;
  onSelectEvidence?: (
    evidence: ActionProposalEvidenceRef,
    title: string,
    count?: number,
    proposalId?: string
  ) => void;
  onExecutionBusyChange?: (
    proposalId: string,
    isBusy: boolean
  ) => boolean | undefined;
  onExecutionComplete?: (proposalId: string) => void;
  onSelectVisibleProposed?: () => void;
  onStatusFilterChange?: (filter: ProposalStatusFilter) => void;
  onToggleProposalSelection?: (proposalId: string) => void;
  pendingMutation: PendingMutation;
  activeProposalId?: string | null;
  auditSourceFilter?: ProposalAuditSourceFilter;
  onAuditSourceFilterChange?: (filter: ProposalAuditSourceFilter) => void;
  originFilter?: ProposalOriginFilter;
  selectedProposalIds?: string[];
  selectedEvidence: ActionProposalEvidenceRef | null;
  selectedEvidenceTitle?: string | null;
  selectedEvidenceCount?: number | null;
  selectedEvidenceProposalId?: string | null;
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

export function canScheduleProposalRefresh(
  source: "execution_complete" | "user",
  operationActive: boolean
): boolean {
  return source === "execution_complete" || !operationActive;
}

export async function loadActionProposalPanelData(
  workspaceId: string,
  initialProposalId: string | null
): Promise<{
  data: ActionProposalListResponse | null;
  error: string | null;
  status: PanelStatus;
}> {
  const data = await fetchActionProposals(workspaceId, { limit: 100 });
  if (!initialProposalId) {
    return {
      data,
      error: null,
      status: data.proposals.length > 0 ? "ready" : "empty"
    };
  }

  const listedProposal = data.proposals.find(
    (proposal) => proposal.id === initialProposalId
  );
  if (listedProposal) {
    if (listedProposal.workspace_id !== workspaceId) {
      return { data: null, error: null, status: "not_found" };
    }
    return { data, error: null, status: "ready" };
  }

  try {
    const proposal = await fetchActionProposal(workspaceId, initialProposalId);
    if (
      proposal.id !== initialProposalId ||
      proposal.workspace_id !== workspaceId
    ) {
      return { data: null, error: null, status: "not_found" };
    }
    return {
      data: mergeExactActionProposal(data, proposal),
      error: null,
      status: "ready"
    };
  } catch (caught: unknown) {
    if (caught instanceof ApiRequestError && caught.status === 404) {
      return { data: null, error: null, status: "not_found" };
    }
    if (caught instanceof ApiRequestError && caught.status === 403) {
      return { data: null, error: null, status: "forbidden" };
    }
    return {
      data: null,
      error: M.actionsPanel.linkedProposalUnavailableDescription,
      status: "error"
    };
  }
}

export function ActionProposalsPanel({
  initialAuditSourceFilter = null,
  initialOriginFilter = null,
  initialProposalId = null,
  initialStatusFilter = null
}: ActionProposalsPanelProps = {}) {
  const session = useSession();
  const workspaceId = session?.workspaceId ?? null;
  const selectedRole =
    session?.workspaces.find((workspace) => workspace.id === workspaceId)?.role ?? null;
  const setExternalOperationPending = session?.setExternalOperationPending;
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
  const [selectedEvidenceProposalId, setSelectedEvidenceProposalId] =
    useState<string | null>(null);
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
  const [activeProposalId, setActiveProposalId] = useState<string | null>(
    initialProposalId
  );
  const [executionBusyProposalId, setExecutionBusyProposalId] =
    useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [mutationError, setMutationError] = useState<MutationError | null>(null);
  const dataRef = useRef<ActionProposalListResponse | null>(data);
  const loadedInitialProposalIdRef = useRef<string | null>(null);
  const loadedWorkspaceIdRef = useRef<string | null>(null);
  const focusAfterReloadRef = useRef(false);
  const mountedRef = useRef(true);
  const currentWorkspaceIdRef = useRef<string | null>(workspaceId);
  const decisionAttemptKeysRef = useRef(new Map<string, string>());
  const activeMutationTokenRef = useRef<number | null>(null);
  const mutationSequenceRef = useRef(0);
  const executionBusyProposalIdRef = useRef<string | null>(null);
  const operationWorkspaceIdRef = useRef<string | null>(workspaceId);
  currentWorkspaceIdRef.current = workspaceId;

  useEffect(() => {
    dataRef.current = data;
  }, [data]);

  function clearSelectedEvidenceContext() {
    setSelectedEvidence(null);
    setSelectedEvidenceTitle(null);
    setSelectedEvidenceCount(null);
    setSelectedEvidenceProposalId(null);
  }

  function isCurrentMutationContext(requestWorkspaceId: string): boolean {
    return (
      mountedRef.current && currentWorkspaceIdRef.current === requestWorkspaceId
    );
  }

  function beginMutation(mutation: Exclude<PendingMutation, null>): number | null {
    if (
      activeMutationTokenRef.current !== null ||
      executionBusyProposalIdRef.current !== null
    ) {
      return null;
    }
    const token = mutationSequenceRef.current + 1;
    mutationSequenceRef.current = token;
    activeMutationTokenRef.current = token;
    setPendingMutation(mutation);
    return token;
  }

  function finishMutation(token: number, requestWorkspaceId: string) {
    if (activeMutationTokenRef.current !== token) {
      return;
    }
    activeMutationTokenRef.current = null;
    if (isCurrentMutationContext(requestWorkspaceId)) {
      setPendingMutation(null);
    }
  }

  function operationIsActive(): boolean {
    return (
      activeMutationTokenRef.current !== null ||
      executionBusyProposalIdRef.current !== null
    );
  }

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    setAuditSourceFilter(normalizeAuditSourceFilter(initialAuditSourceFilter));
    setOriginFilter(normalizeOriginFilter(initialOriginFilter));
    setStatusFilter(normalizeStatusFilter(initialStatusFilter));
    setActiveProposalId(initialProposalId);
    setSelectedEvidence(null);
    setSelectedEvidenceTitle(null);
    setSelectedEvidenceCount(null);
    setSelectedEvidenceProposalId(null);
  }, [
    initialAuditSourceFilter,
    initialOriginFilter,
    initialProposalId,
    initialStatusFilter
  ]);

  useEffect(() => {
    const workspaceChanged = operationWorkspaceIdRef.current !== workspaceId;
    operationWorkspaceIdRef.current = workspaceId;
    setActiveProposalId(initialProposalId);
    setSelectedEvidence(null);
    setSelectedEvidenceTitle(null);
    setSelectedEvidenceCount(null);
    setSelectedEvidenceProposalId(null);
    setSelectedProposalIds([]);
    if (workspaceChanged) {
      activeMutationTokenRef.current = null;
      executionBusyProposalIdRef.current = null;
      decisionAttemptKeysRef.current.clear();
      setPendingMutation(null);
      setExecutionBusyProposalId(null);
    }
    setMutationError(null);
    setSuccessMessage(null);
    focusAfterReloadRef.current = false;
    if (!workspaceId) {
      loadedInitialProposalIdRef.current = null;
      loadedWorkspaceIdRef.current = null;
    }
  }, [initialProposalId, workspaceId]);

  useEffect(() => {
    const pending = executionBusyProposalId !== null || pendingMutation !== null;
    setExternalOperationPending?.(pending);
    return () => {
      if (pending) {
        setExternalOperationPending?.(false);
      }
    };
  }, [executionBusyProposalId, pendingMutation, setExternalOperationPending]);

  useEffect(() => {
    void reloadKey;
    if (!workspaceId) {
      setData(null);
      setError(null);
      setIsRefreshing(false);
      setStatus("missing");
      return;
    }

    let cancelled = false;
    const canRefreshInPlace =
      initialProposalId === null &&
      dataRef.current !== null &&
      loadedInitialProposalIdRef.current === initialProposalId &&
      loadedWorkspaceIdRef.current === workspaceId;
    if (canRefreshInPlace) {
      setIsRefreshing(true);
    } else {
      setData(null);
      setStatus("loading");
    }
    setError(null);
    loadActionProposalPanelData(workspaceId, initialProposalId)
      .then((result) => {
        if (cancelled) {
          return;
        }
        loadedInitialProposalIdRef.current = initialProposalId;
        loadedWorkspaceIdRef.current = workspaceId;
        setData(result.data);
        setError(result.error);
        setStatus(result.status);
        setIsRefreshing(false);
        if (
          focusAfterReloadRef.current &&
          (result.status === "ready" || result.status === "empty")
        ) {
          focusAfterReloadRef.current = false;
          focusMissionDestinationAfterRender();
        }
      })
      .catch((caught: unknown) => {
        if (cancelled) {
          return;
        }
        setIsRefreshing(false);
        setError(caught instanceof Error ? caught.message : M.common.requestFailed);
        if (!canRefreshInPlace) {
          loadedInitialProposalIdRef.current = initialProposalId;
          loadedWorkspaceIdRef.current = workspaceId;
          setData(null);
          setStatus("error");
        }
      });

    return () => {
      cancelled = true;
    };
  }, [initialProposalId, workspaceId, reloadKey]);

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
    if (operationIsActive()) return;
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
      setMutationError({ message: M.actionsPanel.createError, scope: "create" });
      return;
    }

    const mutationToken = beginMutation("create");
    if (mutationToken === null) {
      return;
    }
    setMutationError(null);
    setSuccessMessage(null);
    const requestWorkspaceId = workspaceId;
    try {
      const response = await createActionProposal(requestWorkspaceId, request);
      if (!isCurrentMutationContext(requestWorkspaceId)) {
        return;
      }
      setData((current) => mergeCreatedProposal(current, response.proposal, response.warnings));
      setStatus("ready");
      setCreateForm(DEFAULT_CREATE_FORM);
      setActiveProposalId(response.proposal.id);
      setSuccessMessage(M.actionsPanel.createSuccess);
      focusMissionDestinationAfterRender();
    } catch (caught: unknown) {
      if (!isCurrentMutationContext(requestWorkspaceId)) {
        return;
      }
      setMutationError({
        message: caught instanceof Error ? caught.message : M.common.requestFailed,
        scope: "create"
      });
    } finally {
      finishMutation(mutationToken, requestWorkspaceId);
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
    const requestWorkspaceId = workspaceId;
    const proposal = data?.proposals.find((item) => item.id === proposalId);
    if (!proposal) {
      setMutationError({
        message: "Точное решение больше не загружено. Обновите очередь.",
        scope: `proposal:${proposalId}`
      });
      return;
    }
    if (proposal.created_by === "ai" || proposal.created_by === "system") {
      setMutationError({
        message:
          "Решения ИИ и системы принимаются из Штаба, где зафиксирован точный снимок компании.",
        scope: `proposal:${proposalId}`
      });
      return;
    }
    const mutationToken = beginMutation(`approve:${proposalId}`);
    if (mutationToken === null) {
      return;
    }
    setMutationError(null);
    setSuccessMessage(null);
    const attemptKey = `approved:${proposalId}`;
    const idempotencyKey = decisionAttemptKeysRef.current.get(attemptKey) ??
      createLocalActionDecisionIdempotencyKey(proposalId, "approved");
    decisionAttemptKeysRef.current.set(attemptKey, idempotencyKey);
    try {
      const response = await submitLocalActionDecisionWithOneRetry({
        decision: "approved",
        idempotencyKey,
        proposal,
        workspaceId: requestWorkspaceId
      });
      if (!isCurrentMutationContext(requestWorkspaceId)) {
        return;
      }
      setData((current) => mergeUpdatedProposal(current, response.proposal, response.warnings));
      setStatus("ready");
      clearSelectedEvidenceContext();
      setSuccessMessage(M.actionsPanel.approveSuccess);
      decisionAttemptKeysRef.current.delete(attemptKey);
      focusMissionDestinationAfterRender();
    } catch (caught: unknown) {
      if (!isCurrentMutationContext(requestWorkspaceId)) {
        return;
      }
      setMutationError({
        message: caught instanceof Error ? caught.message : M.common.requestFailed,
        scope: `proposal:${proposalId}`
      });
      if (!isAmbiguousLocalActionDecisionFailure(caught)) {
        decisionAttemptKeysRef.current.delete(attemptKey);
      }
      if (caught instanceof ApiRequestError && caught.status === 409) {
        focusAfterReloadRef.current = true;
        setReloadKey((current) => current + 1);
      }
    } finally {
      finishMutation(mutationToken, requestWorkspaceId);
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
    const requestWorkspaceId = workspaceId;
    const proposal = data?.proposals.find((item) => item.id === proposalId);
    if (!proposal) {
      setMutationError({
        message: "Точное решение больше не загружено. Обновите очередь.",
        scope: `proposal:${proposalId}`
      });
      return;
    }
    const mutationToken = beginMutation(`reject:${proposalId}`);
    if (mutationToken === null) {
      return;
    }
    setMutationError(null);
    setSuccessMessage(null);
    const attemptKey = `rejected:${proposalId}`;
    const idempotencyKey = decisionAttemptKeysRef.current.get(attemptKey) ??
      createLocalActionDecisionIdempotencyKey(proposalId, "rejected");
    decisionAttemptKeysRef.current.set(attemptKey, idempotencyKey);
    try {
      const response = await submitLocalActionDecisionWithOneRetry({
        decision: "rejected",
        idempotencyKey,
        proposal,
        reason: M.actionsPanel.rejectReason,
        workspaceId: requestWorkspaceId
      });
      if (!isCurrentMutationContext(requestWorkspaceId)) {
        return;
      }
      setData((current) => mergeUpdatedProposal(current, response.proposal, response.warnings));
      setStatus("ready");
      clearSelectedEvidenceContext();
      setSuccessMessage(M.actionsPanel.rejectSuccess);
      decisionAttemptKeysRef.current.delete(attemptKey);
      focusMissionDestinationAfterRender();
    } catch (caught: unknown) {
      if (!isCurrentMutationContext(requestWorkspaceId)) {
        return;
      }
      setMutationError({
        message: caught instanceof Error ? caught.message : M.common.requestFailed,
        scope: `proposal:${proposalId}`
      });
      if (!isAmbiguousLocalActionDecisionFailure(caught)) {
        decisionAttemptKeysRef.current.delete(attemptKey);
      }
      if (caught instanceof ApiRequestError && caught.status === 409) {
        focusAfterReloadRef.current = true;
        setReloadKey((current) => current + 1);
      }
    } finally {
      finishMutation(mutationToken, requestWorkspaceId);
    }
  }

  function toggleProposalSelection(proposalId: string) {
    if (operationIsActive()) return;
    setSelectedProposalIds((current) =>
      current.includes(proposalId)
        ? current.filter((existingId) => existingId !== proposalId)
        : [...current, proposalId]
    );
  }

  function selectVisibleProposed() {
    if (operationIsActive()) return;
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
    if (
      mutation === "bulk-approve" &&
      proposalsToMutate.some(
        (proposal) => proposal.created_by === "ai" || proposal.created_by === "system"
      )
    ) {
      setMutationError({
        message:
          "Выберите в Штабе решения ИИ и системы: там каждое принятие связано с точным снимком компании.",
        scope: "bulk"
      });
      return;
    }

    const mutationToken = beginMutation(mutation);
    if (mutationToken === null) {
      return;
    }
    setMutationError(null);
    setSuccessMessage(null);
    const requestWorkspaceId = workspaceId;
    const decision = mutation === "bulk-approve" ? "approved" : "rejected";
    const decisions = proposalsToMutate.map((proposal) => {
      const attemptKey = `bulk-${decision}:${proposal.id}`;
      const idempotencyKey = decisionAttemptKeysRef.current.get(attemptKey) ??
        createLocalActionDecisionIdempotencyKey(proposal.id, decision);
      decisionAttemptKeysRef.current.set(attemptKey, idempotencyKey);
      return {
        expected_snapshot_id: null,
        idempotency_key: idempotencyKey,
        proposal_id: proposal.id,
        proposal_version: proposal.proposal_version
      };
    });
    try {
      const response =
        mutation === "bulk-approve"
          ? await bulkApproveActionProposals(requestWorkspaceId, {
              decisions
            })
          : await bulkRejectActionProposals(requestWorkspaceId, {
              decisions,
              reason: M.actionsPanel.rejectReason
            });
      if (!isCurrentMutationContext(requestWorkspaceId)) {
        return;
      }
      const outcome = summarizeBulkResponse(
        response,
        proposalsToMutate,
        decision
      );
      for (const proposal of proposalsToMutate) {
        decisionAttemptKeysRef.current.delete(`bulk-${decision}:${proposal.id}`);
      }
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
      if (outcome.succeeded.length > 0) {
        clearSelectedEvidenceContext();
        focusMissionDestinationAfterRender();
      }
      if (outcome.failed.length === 0) {
        setSuccessMessage(
          mutation === "bulk-approve"
            ? T.actionsBulkApproveSuccess(outcome.succeeded.length)
            : T.actionsBulkRejectSuccess(outcome.succeeded.length)
        );
      } else if (outcome.succeeded.length === 0) {
        setMutationError({
          message: T.actionsBulkAllFailed(outcome.failed.length),
          scope: "bulk"
        });
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
        setMutationError({
          message: outcome.firstFailureMessage ?? M.common.requestFailed,
          scope: "bulk"
        });
      }
    } catch (caught: unknown) {
      if (!isCurrentMutationContext(requestWorkspaceId)) {
        return;
      }
      setMutationError({
        message: caught instanceof Error ? caught.message : M.common.requestFailed,
        scope: "bulk"
      });
    } finally {
      finishMutation(mutationToken, requestWorkspaceId);
    }
  }

  const loadedContextMatches =
    workspaceId !== null &&
    loadedInitialProposalIdRef.current === initialProposalId &&
    loadedWorkspaceIdRef.current === workspaceId;
  const visibleData = loadedContextMatches ? data : null;
  const visibleStatus: PanelStatus = !workspaceId
    ? "missing"
    : loadedContextMatches
      ? status
      : "loading";

  return (
    <ActionProposalsPanelView
      canCreateProposals={capabilities.canCreateProposals}
      canReviewProposals={capabilities.canReviewProposals}
      activeProposalId={activeProposalId}
      createForm={createForm}
      data={visibleData}
      error={error}
      executionBusyProposalId={executionBusyProposalId}
      isRefreshing={isRefreshing}
      mutationError={mutationError}
      onApprove={capabilities.canReviewProposals ? approve : undefined}
      onCloseEvidence={() => {
        if (operationIsActive()) return;
        clearSelectedEvidenceContext();
      }}
      onCreate={capabilities.canCreateProposals ? submitCreate : undefined}
      onCreateFormChange={
        capabilities.canCreateProposals ? updateCreateForm : undefined
      }
      onReject={capabilities.canReviewProposals ? reject : undefined}
      onRefreshProposals={() => {
        // Trusted completion refresh: execution controls call this while they
        // still own the operation lock. User-triggered navigation and filters
        // remain guarded separately until onBusyChange(false).
        if (!canScheduleProposalRefresh("execution_complete", operationIsActive())) {
          return;
        }
        focusAfterReloadRef.current = true;
        setReloadKey((current) => current + 1);
      }}
      onSelectProposal={(proposalId) => {
        if (operationIsActive()) return;
        setActiveProposalId(proposalId);
        clearSelectedEvidenceContext();
      }}
      onRetry={() => {
        if (!canScheduleProposalRefresh("user", operationIsActive())) return;
        setReloadKey((current) => current + 1);
      }}
      onOriginFilterChange={(filter) => {
        if (operationIsActive()) return;
        setOriginFilter(filter);
        setActiveProposalId(null);
        clearSelectedEvidenceContext();
      }}
      onBulkApprove={
        capabilities.canReviewProposals ? approveSelected : undefined
      }
      onBulkReject={
        capabilities.canReviewProposals ? rejectSelected : undefined
      }
      onClearSelectedProposals={
        capabilities.canReviewProposals
          ? () => {
              if (operationIsActive()) return;
              setSelectedProposalIds([]);
            }
          : undefined
      }
      onSelectEvidence={(evidence, title, count, proposalId) => {
        if (operationIsActive()) return;
        setSelectedEvidence(evidence);
        setSelectedEvidenceTitle(title);
        setSelectedEvidenceCount(typeof count === "number" ? count : null);
        setSelectedEvidenceProposalId(proposalId ?? null);
      }}
      onSelectVisibleProposed={
        capabilities.canReviewProposals ? selectVisibleProposed : undefined
      }
      onAuditSourceFilterChange={(filter) => {
        if (operationIsActive()) return;
        setAuditSourceFilter(filter);
        setActiveProposalId(null);
        clearSelectedEvidenceContext();
      }}
      onExecutionBusyChange={(proposalId, isBusy) => {
        if (isBusy) {
          if (operationIsActive()) return false;
          executionBusyProposalIdRef.current = proposalId;
          setExecutionBusyProposalId(proposalId);
          return true;
        }
        if (executionBusyProposalIdRef.current === proposalId) {
          executionBusyProposalIdRef.current = null;
          setExecutionBusyProposalId(null);
        }
        return true;
      }}
      onExecutionComplete={(proposalId) => {
        setStatusFilter("all");
        setOriginFilter("all");
        setAuditSourceFilter("all");
        setActiveProposalId(proposalId);
        clearSelectedEvidenceContext();
      }}
      onStatusFilterChange={(filter) => {
        if (operationIsActive()) return;
        setStatusFilter(filter);
        setActiveProposalId(null);
        clearSelectedEvidenceContext();
      }}
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
      selectedEvidenceProposalId={selectedEvidenceProposalId}
      statusFilter={statusFilter}
      status={visibleStatus}
      successMessage={successMessage}
    />
  );
}

export function ActionProposalsPanelView({
  activeProposalId = null,
  canCreateProposals = true,
  canReviewProposals = true,
  createForm,
  data,
  error,
  executionBusyProposalId = null,
  isRefreshing = false,
  mutationError = null,
  onApprove,
  onCreate,
  onCreateFormChange,
  onReject,
  onRefreshProposals,
  onSelectProposal,
  onRetry,
  onOriginFilterChange,
  onBulkApprove,
  onBulkReject,
  onClearSelectedProposals,
  onSelectEvidence,
  onSelectVisibleProposed,
  onAuditSourceFilterChange,
  onExecutionBusyChange,
  onExecutionComplete,
  onStatusFilterChange,
  onToggleProposalSelection,
  pendingMutation,
  auditSourceFilter = "all",
  originFilter = "all",
  selectedProposalIds = [],
  selectedEvidence,
  selectedEvidenceTitle = null,
  selectedEvidenceCount = null,
  selectedEvidenceProposalId = null,
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
  const normallyFilteredProposals =
    originFilter === "audit"
      ? filterProposalsByAuditSource(originFilteredProposals, auditSourceFilter)
      : originFilteredProposals;
  const linkedProposal = activeProposalId
    ? proposals.find((proposal) => proposal.id === activeProposalId) ?? null
    : null;
  const linkedProposalOutsideFilter = Boolean(
    linkedProposal &&
      !normallyFilteredProposals.some((proposal) => proposal.id === linkedProposal.id)
  );
  const filteredProposals =
    linkedProposal && linkedProposalOutsideFilter
      ? [linkedProposal, ...normallyFilteredProposals]
      : normallyFilteredProposals;
  const visibleProposedIds = proposedProposalIds(filteredProposals);
  const visibleProposedCount = visibleProposedIds.length;
  const selectedProposedCount = selectedProposalIds.filter((proposalId) =>
    visibleProposedIds.includes(proposalId)
  ).length;
  const groups = groupProposalsByOrigin(filteredProposals);
  const orderedProposals = groups.flatMap((group) => group.proposals);
  const activeProposal = selectActiveMission(orderedProposals, activeProposalId);
  const defaultEvidenceSelection = firstEvidenceSelection(
    activeProposal ? [activeProposal] : []
  );
  const manualEvidenceMatchesActiveMission = Boolean(
    selectedEvidence &&
      activeProposal &&
      selectedEvidenceProposalId === activeProposal.id &&
      proposalContainsEvidence(activeProposal, selectedEvidence)
  );
  const drawerEvidence = manualEvidenceMatchesActiveMission
    ? selectedEvidence
    : defaultEvidenceSelection?.evidence ?? null;
  const drawerTitle = manualEvidenceMatchesActiveMission
    ? activeProposal?.title ?? selectedEvidenceTitle
    : defaultEvidenceSelection?.title ?? null;
  const drawerCount = manualEvidenceMatchesActiveMission
    ? activeProposal?.evidence_refs.length ?? selectedEvidenceCount
    : defaultEvidenceSelection?.count ?? null;
  const drawerSelectionMode: "default" | "manual" | null = drawerEvidence
    ? manualEvidenceMatchesActiveMission
      ? "manual"
      : "default"
    : null;
  const canCreate = canSubmitCreateForm(createForm);
  const executionBusy = executionBusyProposalId !== null;
  const operationBusy = executionBusy || pendingMutation !== null;

  return (
    <section className="missions-room" aria-labelledby="missions-title">
      <header className="missions-hero">
        <div className="missions-hero-copy">
          <span className="eyebrow">Комната решений</span>
          <h1 id="missions-title">Решения</h1>
          <p>
            Здесь вы решаете, что компания делает дальше. Сначала основание,
            потом решение, и только затем — отдельный внешний шаг.
          </p>
        </div>
        <div className="missions-human-control">
          <span className="missions-control-light" aria-hidden="true" />
          <div>
            <strong>Под контролем человека</strong>
            <small>Ничего не отправится само</small>
          </div>
        </div>
        <DecisionRoomAccessHint
          canCreateProposals={canCreateProposals}
          canReviewProposals={canReviewProposals}
        />
      </header>

      <div
        aria-atomic="true"
        aria-live="polite"
        className="missions-announcements"
        role="status"
      >
        {successMessage ? <p className="success-text">{successMessage}</p> : null}
      </div>

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

      {status === "not_found" ? (
        <EmptyState
          description={M.actionsPanel.linkedProposalNotFoundDescription}
          title={M.actionsPanel.linkedProposalNotFoundTitle}
        />
      ) : null}

      {status === "forbidden" ? (
        <ErrorState
          description={M.actionsPanel.linkedProposalForbiddenDescription}
          title={M.actionsPanel.linkedProposalForbiddenTitle}
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
          <button
            className="button secondary"
            disabled={operationBusy}
            onClick={onRetry}
            type="button"
          >
            {M.common.retry}
          </button>
        </>
      ) : null}

      {data && (status === "ready" || status === "empty") ? (
        <>
          <DecisionRoomSummary proposals={proposals} />

          <div className="missions-toolbar">
            <details className="decision-room-disclosure decision-room-filters">
              <summary>
                <span>Настроить очередь</span>
                <small>{decisionRoomFilterSummary(statusFilter, originFilter)}</small>
              </summary>
              <div className="decision-room-disclosure-body">
                <ActionStatusFilter
                  activeFilter={statusFilter}
                  disabled={operationBusy}
                  onChange={onStatusFilterChange}
                  proposals={proposals}
                />

                <ActionOriginFilter
                  activeFilter={originFilter}
                  disabled={operationBusy}
                  onChange={onOriginFilterChange}
                  proposals={statusFilteredProposals}
                />

                {originFilter === "audit" ? (
                  <ActionAuditSourceFilter
                    activeFilter={auditSourceFilter}
                    disabled={operationBusy}
                    onChange={onAuditSourceFilterChange}
                    proposals={statusFilteredProposals}
                  />
                ) : null}

                {canReviewProposals && selectedProposedCount === 0 ? (
                  <button
                    className="button secondary decision-room-select-visible"
                    disabled={operationBusy || visibleProposedCount === 0}
                    onClick={onSelectVisibleProposed}
                    type="button"
                  >
                    {M.actionsPanel.bulkSelectVisible}
                  </button>
                ) : null}
              </div>
            </details>
            <span className="missions-loaded-note">
              {linkedProposalOutsideFilter
                ? M.actionsPanel.linkedProposalOutsideFilter
                : isRefreshing
                  ? "Обновляем очередь…"
                  : "В загруженной очереди · до 100 решений"}
            </span>
          </div>

          {canReviewProposals && selectedProposedCount > 0 ? (
            <BulkReviewControls
              onApproveSelected={onBulkApprove}
              onClearSelection={onClearSelectedProposals}
              onRejectSelected={onBulkReject}
              onSelectVisibleProposed={onSelectVisibleProposed}
              disabled={operationBusy}
              error={mutationError?.scope === "bulk" ? mutationError.message : null}
              pendingMutation={pendingMutation}
              selectedCount={selectedProposedCount}
              visibleProposedCount={visibleProposedCount}
            />
          ) : null}

          {activeProposal ? (
            <section
              aria-busy={isRefreshing || operationBusy}
              aria-label="Рабочая зона решений"
              className="missions-workspace"
            >
              <MissionDecisionConsole
                key={activeProposal.id}
                canReviewProposals={canReviewProposals}
                drawerCount={drawerCount}
                drawerEvidence={drawerEvidence}
                drawerSelectionMode={drawerSelectionMode}
                drawerTitle={drawerTitle}
                onApprove={onApprove}
                onExecutionBusyChange={onExecutionBusyChange}
                onExecutionComplete={onExecutionComplete}
                onRefreshProposals={onRefreshProposals}
                onReject={onReject}
                onSelectEvidence={onSelectEvidence}
                pendingMutation={pendingMutation}
                proposal={activeProposal}
                proposalMutationError={
                  mutationError?.scope === `proposal:${activeProposal.id}`
                    ? mutationError.message
                    : null
                }
              />
              <MissionQueue
                activeProposalId={activeProposal.id}
                canReviewProposals={canReviewProposals}
                disabled={operationBusy}
                onSelectProposal={onSelectProposal}
                onToggleProposalSelection={onToggleProposalSelection}
                pendingMutation={pendingMutation}
                proposals={orderedProposals}
                selectedProposalIds={selectedProposalIds}
                statusFilter={statusFilter}
              />
            </section>
          ) : (
            <MissionQueueEmpty
              canCreateProposals={canCreateProposals}
              hasAnyProposals={proposals.length > 0}
            />
          )}

          <section className="missions-backstage" aria-label="Дополнительные возможности">
            {canCreateProposals ? (
              <details
                className="decision-room-disclosure decision-room-create"
                id="add-mission"
                open={status === "empty"}
              >
                <summary>
                  <span>Добавить решение</span>
                  <small>Сохранится в FounderOS и ничего не выполнит само</small>
                </summary>
                <div className="decision-room-disclosure-body">
                  {mutationError?.scope === "create" ? (
                    <p className="error-text" role="alert">
                      {mutationError.message}
                    </p>
                  ) : null}
                  <ActionProposalCreateForm
                    form={createForm}
                    isPending={pendingMutation === "create"}
                    onChange={onCreateFormChange}
                    onSubmit={onCreate}
                    operationDisabled={operationBusy}
                    submitDisabled={!canCreate || operationBusy}
                  />
                </div>
              </details>
            ) : null}

            {canReviewProposals ? (
              <details className="decision-room-disclosure decision-room-readiness">
                <summary>
                  <span>Контроль безопасности</span>
                  <small>Основания, предпросмотр и сохранённые результаты</small>
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
          </section>
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
  const failedCount = countByStatus(proposals, "failed");
  return (
    <div className="missions-pulse-wrap">
      <dl className="missions-pulse" aria-label={M.actionsPanel.summaryLabel}>
      <div className="missions-pulse-item missions-pulse-item--primary">
        <dt>Ждут вас</dt>
        <dd>{countByStatus(proposals, "proposed")}</dd>
        <small>Нужно открыть и решить</small>
      </div>
      <div className="missions-pulse-item">
        <dt>Приняты человеком</dt>
        <dd>{countAcceptedProposals(proposals)}</dd>
        <small>Это ещё не внешнее выполнение</small>
      </div>
      <div className="missions-pulse-item">
        <dt>С результатом</dt>
        <dd>{countByStatus(proposals, "executed")}</dd>
        <small>Есть сохранённая квитанция</small>
      </div>
      </dl>
      {failedCount > 0 ? (
        <p className="missions-attention" role="status">
          {failedCount === 1 ? (
            <><strong>1 выполнение</strong> требует внимания</>
          ) : (
            <><strong>{failedCount} выполнений</strong> требуют внимания</>
          )}
        </p>
      ) : null}
    </div>
  );
}

function decisionRoomFilterSummary(
  statusFilter: ProposalStatusFilter,
  originFilter: ProposalOriginFilter
): string {
  return `${filterLabel(statusFilter)} · ${originFilterLabel(originFilter)}`;
}

function selectActiveMission(
  proposals: ActionProposal[],
  activeProposalId: string | null
): ActionProposal | null {
  const selected = proposals.find((proposal) => proposal.id === activeProposalId);
  if (selected) {
    return selected;
  }
  return (
    proposals.reduce<ActionProposal | null>((best, proposal) => {
      if (!best || missionPriority(proposal) < missionPriority(best)) {
        return proposal;
      }
      return best;
    }, null)
  );
}

function missionPriority(proposal: ActionProposal): number {
  if (proposal.status === "failed") {
    return 0;
  }
  if (proposal.status === "proposed") {
    return 1;
  }
  if (isPreviewReadyGithubIssueProposal(proposal)) {
    return 2;
  }
  if (proposal.status === "approved") {
    return 3;
  }
  if (proposal.status === "executed") {
    return 4;
  }
  if (proposal.status === "rejected") {
    return 5;
  }
  return 6;
}

function missionStage(proposal: ActionProposal): number {
  if (proposal.status === "executed" || proposal.status === "rejected") {
    return 3;
  }
  if (proposal.status === "approved" || proposal.status === "failed") {
    return 2;
  }
  return 0;
}

function missionProgressLabels(proposal: ActionProposal): string[] {
  return [
    "Основание",
    "Решение",
    proposal.status === "rejected" ? "Закрыто" : "Следующий шаг"
  ];
}

function missionWhyNow(proposal: ActionProposal): string {
  if (proposal.description) {
    return proposal.description;
  }
  if (proposal.status === "failed") {
    return "Предыдущая попытка завершилась ошибкой и требует внимания человека.";
  }
  if (proposal.status === "approved") {
    return "Решение уже сохранено; следующий шаг ещё нужно проверить отдельно.";
  }
  if (proposal.status === "executed") {
    return "Для этого решения сохранён результат выполнения.";
  }
  if (proposal.status === "rejected") {
    return "Решение закрыто человеком и остаётся в истории.";
  }
  return "Решение сохранено в очереди и ждёт ответа человека.";
}

function missionQueueTitle(statusFilter: ProposalStatusFilter): string {
  if (statusFilter === "proposed") {
    return "Что ждёт вас";
  }
  if (statusFilter === "approved") {
    return "Принятые решения";
  }
  if (statusFilter === "rejected") {
    return "Закрытые решения";
  }
  return "Решения компании";
}

function focusMissionDestinationAfterRender() {
  if (typeof document === "undefined") {
    return;
  }
  requestAnimationFrame(() => {
    const destination =
      document.getElementById("mission-console-title") ??
      document.getElementById("mission-empty-title") ??
      document.getElementById("mission-queue-title");
    destination?.focus();
  });
}

function proposalOriginLabel(origin: ProposalOrigin): string {
  switch (origin) {
    case "audit":
      return "Аудит репо";
    case "briefing":
      return "Сводка";
    case "github":
      return "GitHub";
    case "internal":
      return "Внутри";
  }
}

function countAcceptedProposals(proposals: ActionProposal[]): number {
  return proposals.filter((proposal) =>
    ["approved", "executed", "failed"].includes(proposal.status)
  ).length;
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
  operationDisabled,
  submitDisabled
}: {
  form: ActionProposalCreateFormState;
  isPending: boolean;
  onChange?: (field: keyof ActionProposalCreateFormState, value: string) => void;
  onSubmit?: (event: FormEvent<HTMLFormElement>) => void;
  operationDisabled: boolean;
  submitDisabled: boolean;
}) {
  const isGitHubIssue = form.proposalKind === "github_issue";

  return (
    <form className="form proposal-form" onSubmit={onSubmit}>
      <div className="field">
        <label htmlFor="proposal-kind">{M.actionCreate.typeLabel}</label>
        <select
          disabled={operationDisabled || isPending}
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
          disabled={operationDisabled || isPending}
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
          disabled={operationDisabled || isPending}
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
              disabled={operationDisabled || isPending}
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
              disabled={operationDisabled || isPending}
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
  disabled = false,
  onChange,
  proposals
}: {
  activeFilter: ProposalStatusFilter;
  disabled?: boolean;
  onChange?: (filter: ProposalStatusFilter) => void;
  proposals: ActionProposal[];
}) {
  const filters: ProposalStatusFilter[] = ["proposed", "approved", "rejected", "all"];
  return (
    <section className="work-section" aria-label={M.actionsPanel.filterLabel}>
      <h3>{M.actionsPanel.filterTitle}</h3>
      <p className="muted">{M.actionsPanel.filterDescription}</p>
      <div className="segmented" role="group" aria-label={M.actionsPanel.filterLabel}>
        {filters.map((filter) => (
          <button
            aria-pressed={activeFilter === filter}
            className={`segment${activeFilter === filter ? " active" : ""}`}
            disabled={disabled}
            key={filter}
            onClick={() => onChange?.(filter)}
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
  disabled = false,
  onChange,
  proposals
}: {
  activeFilter: ProposalOriginFilter;
  disabled?: boolean;
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
      <div className="segmented" role="group" aria-label={M.actionsPanel.originFilterLabel}>
        {filters.map((filter) => (
          <button
            aria-pressed={activeFilter === filter}
            className={`segment${activeFilter === filter ? " active" : ""}`}
            disabled={disabled}
            key={filter}
            onClick={() => onChange?.(filter)}
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
  disabled = false,
  onChange,
  proposals
}: {
  activeFilter: ProposalAuditSourceFilter;
  disabled?: boolean;
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
        role="group"
        aria-label={M.actionsPanel.auditSourceFilterLabel}
      >
        {filters.map((filter) => (
          <button
            aria-pressed={activeFilter === filter}
            className={`segment${activeFilter === filter ? " active" : ""}`}
            disabled={disabled}
            key={filter}
            onClick={() => onChange?.(filter)}
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
  disabled = false,
  error = null,
  onApproveSelected,
  onClearSelection,
  onRejectSelected,
  onSelectVisibleProposed,
  pendingMutation,
  selectedCount,
  visibleProposedCount
}: {
  disabled?: boolean;
  error?: string | null;
  onApproveSelected?: () => void;
  onClearSelection?: () => void;
  onRejectSelected?: () => void;
  onSelectVisibleProposed?: () => void;
  pendingMutation: PendingMutation;
  selectedCount: number;
  visibleProposedCount: number;
}) {
  const bulkPending = isBulkMutationPending(pendingMutation);
  const controlsDisabled = disabled || bulkPending;
  return (
    <section
      className="decision-room-bulk-bar"
      aria-label={M.actionsPanel.bulkLabel}
    >
      <strong aria-live="polite" role="status">
        {T.actionsBulkSelection(selectedCount, visibleProposedCount)}
      </strong>
      {error ? (
        <p className="error-text" role="alert">
          {error}
        </p>
      ) : null}
      <div className="actions-row decision-room-bulk-actions">
        <button
          className="button secondary"
          disabled={controlsDisabled || visibleProposedCount === 0}
          onClick={onSelectVisibleProposed}
          type="button"
        >
          {M.actionsPanel.bulkSelectVisible}
        </button>
        <button
          className="button secondary"
          disabled={controlsDisabled}
          onClick={onClearSelection}
          type="button"
        >
          {M.actionsPanel.bulkClearSelection}
        </button>
      </div>
      <details className="missions-bulk-confirm">
        <summary>Проверить последствия</summary>
        <p>
          Статус изменится только внутри FounderOS для выбранных решений. Внешние
          действия не запустятся.
        </p>
        <div className="actions-row decision-room-bulk-actions">
          <button
            className="button"
            disabled={controlsDisabled}
            onClick={onApproveSelected}
            type="button"
          >
            {pendingMutation === "bulk-approve"
              ? M.actionsPanel.bulkApproving
              : M.actionsPanel.bulkApproveSelected}
          </button>
          <button
            className="button secondary"
            disabled={controlsDisabled}
            onClick={onRejectSelected}
            type="button"
          >
            {pendingMutation === "bulk-reject"
              ? M.actionsPanel.bulkRejecting
              : M.actionsPanel.bulkRejectSelected}
          </button>
        </div>
      </details>
    </section>
  );
}

function MissionQueue({
  activeProposalId,
  canReviewProposals,
  disabled = false,
  onSelectProposal,
  onToggleProposalSelection,
  pendingMutation,
  proposals,
  selectedProposalIds,
  statusFilter
}: {
  activeProposalId: string;
  canReviewProposals: boolean;
  disabled?: boolean;
  onSelectProposal?: (proposalId: string) => void;
  onToggleProposalSelection?: (proposalId: string) => void;
  pendingMutation: PendingMutation;
  proposals: ActionProposal[];
  selectedProposalIds: string[];
  statusFilter: ProposalStatusFilter;
}) {
  const bulkPending = isBulkMutationPending(pendingMutation);
  return (
    <section className="mission-queue" aria-labelledby="mission-queue-title">
      <header className="mission-queue-header">
        <div>
          <span className="eyebrow">Очередь</span>
          <h2 id="mission-queue-title" tabIndex={-1}>
            {missionQueueTitle(statusFilter)}
          </h2>
        </div>
        <span className="mission-queue-count">{proposals.length}</span>
      </header>
      <div className="mission-queue-list">
        {proposals.map((proposal, index) => {
          const isActive = proposal.id === activeProposalId;
          const origin = proposalOrigin(proposal);
          return (
            <article
              className={`mission-queue-card${isActive ? " is-active" : ""}`}
              key={proposal.id}
            >
              {canReviewProposals && selectedProposalIds.length > 0 ? (
                <ProposalSelectionControl
                  disabled={disabled || bulkPending}
                  isSelected={selectedProposalIds.includes(proposal.id)}
                  onToggle={onToggleProposalSelection}
                  proposal={proposal}
                />
              ) : null}
              <button
                aria-controls="mission-console"
                aria-pressed={isActive}
                className="mission-queue-open"
                disabled={disabled}
                id={`mission-queue-${proposal.id}`}
                onClick={() => {
                  onSelectProposal?.(proposal.id);
                  if (typeof document !== "undefined") {
                    requestAnimationFrame(() => {
                      document.getElementById("mission-console-title")?.focus();
                    });
                  }
                }}
                type="button"
              >
                <span className="mission-queue-number" aria-hidden="true">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <span className="mission-queue-copy">
                  <span className="mission-queue-badges">
                    <span
                      className={`badge decision-room-status decision-room-status--${proposalStatusTone(proposal.status)}`}
                    >
                      {proposalStatusLabel(proposal.status)}
                    </span>
                    <span className="badge badge-origin">
                      {proposalOriginLabel(origin)}
                    </span>
                  </span>
                  <strong>{proposal.title}</strong>
                  <small>
                    {proposal.description ||
                      `Если принять: ${actionLabel(proposal.action_type)}`}
                  </small>
                  <span className="mission-queue-meta">
                    Оснований: {proposal.evidence_refs.length} ·{" "}
                    {proposalTargetLabel(proposal.target_provider)}
                  </span>
                </span>
                <span className="mission-queue-arrow" aria-hidden="true">→</span>
              </button>
            </article>
          );
        })}
      </div>
    </section>
  );
}

function MissionDecisionConsole({
  canReviewProposals,
  drawerCount,
  drawerEvidence,
  drawerSelectionMode,
  drawerTitle,
  onApprove,
  onExecutionBusyChange,
  onExecutionComplete,
  onRefreshProposals,
  onReject,
  onSelectEvidence,
  pendingMutation,
  proposal,
  proposalMutationError
}: {
  canReviewProposals: boolean;
  drawerCount: number | null;
  drawerEvidence: ActionProposalEvidenceRef | null;
  drawerSelectionMode: "default" | "manual" | null;
  drawerTitle: string | null;
  onApprove?: (proposalId: string) => void;
  onExecutionBusyChange?: (
    proposalId: string,
    isBusy: boolean
  ) => boolean | undefined;
  onExecutionComplete?: (proposalId: string) => void;
  onRefreshProposals?: () => void;
  onReject?: (proposalId: string) => void;
  onSelectEvidence?: (
    evidence: ActionProposalEvidenceRef,
    title: string,
    count?: number,
    proposalId?: string
  ) => void;
  pendingMutation: PendingMutation;
  proposal: ActionProposal;
  proposalMutationError: string | null;
}) {
  const stage = missionStage(proposal);
  const [executionBusy, setExecutionBusy] = useState(false);
  const [executionOutcome, setExecutionOutcome] =
    useState<ActionExecutionOutcome | null>(null);

  function handleExecutionBusyChange(isBusy: boolean): boolean | undefined {
    const accepted = onExecutionBusyChange?.(proposal.id, isBusy);
    if (isBusy && accepted === false) {
      return false;
    }
    setExecutionBusy(isBusy);
    return accepted;
  }

  function handleExecutionComplete(outcome: ActionExecutionOutcome) {
    setExecutionOutcome(outcome);
    if (!outcome.auditRefreshFailed) {
      onExecutionComplete?.(proposal.id);
    }
  }

  const operationBusy = executionBusy || pendingMutation !== null;

  return (
    <article className="mission-console" id="mission-console" aria-labelledby="mission-console-title">
      <header className="mission-console-header">
        <div className="mission-console-heading">
          <span className="eyebrow">Активное решение</span>
          <div className="mission-console-heading-actions">
            <span
              className={`badge decision-room-status decision-room-status--${proposalStatusTone(proposal.status)}`}
            >
              {proposalStatusLabel(proposal.status)}
            </span>
            <button
              className="mission-console-return"
              disabled={operationBusy}
              onClick={() =>
                document.getElementById(`mission-queue-${proposal.id}`)?.focus()
              }
              type="button"
            >
              Вернуться к очереди
            </button>
          </div>
        </div>
        <h2 id="mission-console-title" tabIndex={-1}>{proposal.title}</h2>
        <p>
          {proposalOriginLabel(proposalOrigin(proposal))} · {proposalTargetLabel(proposal.target_provider)}
        </p>
      </header>

      {operationBusy ? (
        <p className="mission-operation-lock" role="status">
          Завершаем защищённую операцию. Переключение решения, компании и раздела
          временно приостановлено.
        </p>
      ) : null}

      <ol className="mission-progress" aria-label="Этапы решения">
        {missionProgressLabels(proposal).map((label, index) => (
          <li
            aria-current={index === stage ? "step" : undefined}
            className={`${index < stage ? "is-complete" : ""}${index === stage ? " is-current" : ""}`}
            key={label}
          >
            <span>{String(index + 1).padStart(2, "0")}</span>
            <strong>
              {label}
              {index < stage ? <span className="sr-only"> — завершено</span> : null}
              {index === stage ? <span className="sr-only"> — текущий этап</span> : null}
            </strong>
          </li>
        ))}
      </ol>

      <section className="mission-why" aria-labelledby="mission-why-title">
        <span>Почему сейчас</span>
        <h3 className="sr-only" id="mission-why-title">Причина выбора решения</h3>
        <p>{missionWhyNow(proposal)}</p>
      </section>

      <section className="mission-impact" aria-labelledby="mission-impact-title">
        <span>Если принять</span>
        <h3 id="mission-impact-title">{actionLabel(proposal.action_type)}</h3>
        <p>
          {isLocalOnlyProposal(proposal)
            ? "Решение останется внутри FounderOS; во внешние сервисы ничего не уйдёт."
            : "Сначала сохранится только решение. Внешний шаг появится отдельно и потребует нового подтверждения."}
        </p>
      </section>

      <section className="mission-evidence" aria-labelledby="mission-evidence-title">
        <div className="mission-section-heading">
          <div>
            <span className="eyebrow">Основание</span>
            <h3 id="mission-evidence-title">Почему FounderOS это предлагает</h3>
          </div>
          <span className="badge">{proposal.evidence_refs.length}</span>
        </div>
        <ActionEvidenceButtons
          evidenceRefs={proposal.evidence_refs}
          onSelectEvidence={onSelectEvidence}
          proposalId={proposal.id}
          proposalTitle={proposal.title}
        />
        <EvidenceDrawer
          evidence={drawerEvidence}
          evidenceCount={drawerCount}
          itemTitle={drawerTitle}
          selectionMode={drawerSelectionMode}
          selectionDescription={
            drawerSelectionMode === "manual"
              ? "Показано выбранное основание этого решения."
              : drawerSelectionMode === "default"
                ? "Показано первое основание выбранного решения."
                : null
          }
        />
      </section>

      {canReviewProposals ? (
        <section className="mission-decision" aria-label="Решение по предложению">
          {proposalMutationError ? (
            <p className="error-text" role="alert">
              {proposalMutationError}
            </p>
          ) : null}
          <ProposalActions
            onApprove={onApprove}
            onReject={onReject}
            pendingMutation={pendingMutation}
            proposal={proposal}
          />
          {proposal.status === "proposed" ? (
            <p>
              Решение сохранится в FounderOS. Во внешние сервисы ничего не
              отправится.
            </p>
          ) : null}
        </section>
      ) : null}

      {canReviewProposals ? (
        <ProposalNextStep
          disabled={pendingMutation !== null}
          onExecutionBusyChange={(_proposalId, isBusy) =>
            handleExecutionBusyChange(isBusy)
          }
          onExecutionComplete={handleExecutionComplete}
          onRefreshProposals={onRefreshProposals}
          proposal={proposal}
        />
      ) : null}

      {executionOutcome ? (
        <MissionExecutionOutcome outcome={executionOutcome} />
      ) : null}

      <details className="mission-technical decision-room-card-details">
        <summary>История и технические детали</summary>
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
          {canReviewProposals && !isPreviewReadyGithubIssueProposal(proposal) ? (
            <ActionExecutionControls
              disabled={pendingMutation !== null}
              key={proposal.id}
              onBusyChange={handleExecutionBusyChange}
              onComplete={handleExecutionComplete}
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
  );
}

function MissionQueueEmpty({
  canCreateProposals,
  hasAnyProposals
}: {
  canCreateProposals: boolean;
  hasAnyProposals: boolean;
}) {
  return (
    <section className="mission-empty" aria-labelledby="mission-empty-title">
      <span className="mission-empty-number" aria-hidden="true">00</span>
      <div>
        <span className="eyebrow">Очередь свободна</span>
        <h2 id="mission-empty-title" tabIndex={-1}>
          {hasAnyProposals ? "В этом фокусе решений нет" : "Добавьте первое решение"}
        </h2>
        <p>
          {hasAnyProposals
            ? "Измените фильтры — другие решения остаются в загруженной очереди."
            : "Зафиксируйте следующий ход. Он сохранится локально и не запустит внешнее действие."}
        </p>
        {!hasAnyProposals && canCreateProposals ? (
          <a className="button" href="#add-mission">Создать первое решение</a>
        ) : null}
      </div>
    </section>
  );
}

function MissionExecutionOutcome({
  outcome
}: {
  outcome: ActionExecutionOutcome;
}) {
  const succeeded = outcome.providerResult === "succeeded";
  return (
    <section className="mission-outcome" aria-label="Сохранённый результат решения">
      <span className="eyebrow">Результат решения</span>
      <h3>{succeeded ? "Внешний результат подтверждён" : "Результат сохранён"}</h3>
      <p>
        {outcome.externalWritePerformed
          ? "FounderOS получил подтверждение внешнего действия и сохранил квитанцию."
          : "Новая внешняя запись не выполнялась; сохранён безопасный результат запроса."}
      </p>
      <dl className="work-meta">
        <div>
          <dt>Статус квитанции</dt>
          <dd>{outcome.receiptStatus ?? "не указан"}</dd>
        </div>
        <div>
          <dt>Результат провайдера</dt>
          <dd>{outcome.providerResult}</dd>
        </div>
      </dl>
      {outcome.externalResultUrl ? (
        <SourceLink url={outcome.externalResultUrl}>Открыть внешний результат</SourceLink>
      ) : null}
      {outcome.auditRefreshFailed ? (
        <p className="mission-outcome-warning" role="status">
          {M.actionExecution.auditRefreshAfterExecuteFailed}
        </p>
      ) : null}
    </section>
  );
}

function ProposalNextStep({
  disabled = false,
  onExecutionBusyChange,
  onExecutionComplete,
  onRefreshProposals,
  proposal
}: {
  disabled?: boolean;
  onExecutionBusyChange?: (
    proposalId: string,
    isBusy: boolean
  ) => boolean | undefined;
  onExecutionComplete?: (outcome: ActionExecutionOutcome) => void;
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
          disabled={disabled}
          key={proposal.id}
          onBusyChange={(isBusy) =>
            onExecutionBusyChange?.(proposal.id, isBusy)
          }
          onComplete={onExecutionComplete}
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
  proposalId,
  proposalTitle
}: {
  evidenceRefs: ActionProposalEvidenceRef[];
  onSelectEvidence?: (
    evidence: ActionProposalEvidenceRef,
    title: string,
    count?: number,
    proposalId?: string
  ) => void;
  proposalId: string;
  proposalTitle: string;
}) {
  if (evidenceRefs.length === 0) {
    return <p className="muted">{M.actionsPanel.noEvidenceRefs}</p>;
  }

  return (
    <div className="decision-room-evidence">
      <div
        aria-label={T.evidenceFor(proposalTitle)}
        className="actions-row"
        role="group"
      >
        {evidenceRefs.map((evidence) => (
          <button
            className="button secondary"
            key={`${evidence.kind}-${evidence.source}-${evidence.ref}`}
            onClick={() =>
              onSelectEvidence?.(
                evidence,
                proposalTitle,
                evidenceRefs.length,
                proposalId
              )
            }
            type="button"
          >
            {T.evidenceButton(evidence.ref)}
          </button>
        ))}
      </div>
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
  if (proposal.status !== "proposed") {
    return null;
  }

  const approvePending = pendingMutation === `approve:${proposal.id}`;
  const rejectPending = pendingMutation === `reject:${proposal.id}`;
  const anyMutationPending = pendingMutation !== null;
  return (
    <div className="actions-row">
      <button
        className="button"
        disabled={anyMutationPending}
        onClick={() => onApprove?.(proposal.id)}
        type="button"
      >
        {approvePending ? M.actionsPanel.approving : M.actionsPanel.approve}
      </button>
      <button
        className="button secondary"
        disabled={anyMutationPending}
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
  const proposals = [
    proposal,
    ...current.proposals.filter((existing) => existing.id !== proposal.id)
  ].slice(0, 100);
  return {
    ...current,
    count: proposals.length,
    proposals,
    warnings
  };
}

export function mergeExactActionProposal(
  current: ActionProposalListResponse,
  proposal: ActionProposal
): ActionProposalListResponse {
  const proposals = [
    proposal,
    ...current.proposals.filter((existing) => existing.id !== proposal.id)
  ].slice(0, 100);
  return {
    ...current,
    count: proposals.length,
    proposals
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

function summarizeBulkResponse(
  response: ActionProposalBulkResponse,
  requestedProposals: ActionProposal[],
  decision: "approved" | "rejected"
): BulkOutcome {
  const requestedById = new Map(
    requestedProposals.map((proposal) => [proposal.id, proposal])
  );
  const receiptsByProposalId = new Map(
    response.decision_receipts.map((receipt) => [receipt.proposal_id, receipt])
  );
  const receiptContractIsValid =
    response.succeeded_count === response.proposals.length &&
    response.failed_count === response.failures.length &&
    response.decision_receipts.length === response.proposals.length &&
    response.proposals.every((proposal) => {
      const requested = requestedById.get(proposal.id);
      const receipt = receiptsByProposalId.get(proposal.id);
      return (
        requested !== undefined &&
        receipt !== undefined &&
        receipt.decision === decision &&
        receipt.external_write_performed === false &&
        receipt.proposal_version === requested.proposal_version
      );
    });
  if (!receiptContractIsValid) {
    throw new Error("Сервер не подтвердил точные квитанции массового решения.");
  }
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

function proposalContainsEvidence(
  proposal: ActionProposal,
  selectedEvidence: ActionProposalEvidenceRef
): boolean {
  return proposal.evidence_refs.some(
    (evidence) =>
      evidence.kind === selectedEvidence.kind &&
      evidence.source === selectedEvidence.source &&
      evidence.ref === selectedEvidence.ref &&
      evidence.url === selectedEvidence.url
  );
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
