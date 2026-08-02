import {
  ApiRequestError,
  approveActionProposal,
  rejectActionProposal
} from "./api";
import type {
  ActionProposal,
  ActionProposalDecisionResponse
} from "./types";

export type LocalActionDecision = "approved" | "rejected";
export type LocalActionDecisionContractPhase = "preflight" | "response";

export type SubmitLocalActionDecisionInput = {
  decision: LocalActionDecision;
  expectedSnapshotId?: string | null;
  idempotencyKey: string;
  proposal: ActionProposal;
  reason?: string | null;
  signal?: AbortSignal;
  workspaceId: string;
};

export class LocalActionDecisionContractError extends Error {
  readonly phase: LocalActionDecisionContractPhase;

  constructor(
    message: string,
    phase: LocalActionDecisionContractPhase = "response"
  ) {
    super(message);
    this.name = "LocalActionDecisionContractError";
    this.phase = phase;
  }
}

export function createLocalActionDecisionIdempotencyKey(
  proposalId: string,
  decision: LocalActionDecision
): string {
  const randomPart = globalThis.crypto?.randomUUID?.() ??
    `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
  return `hq-local-${decision}-${proposalId}-${randomPart}`;
}

export async function submitLocalActionDecision({
  decision,
  expectedSnapshotId = null,
  idempotencyKey,
  proposal,
  reason = null,
  signal,
  workspaceId
}: SubmitLocalActionDecisionInput): Promise<ActionProposalDecisionResponse> {
  if (
    proposal.id.length === 0 ||
    proposal.workspace_id !== workspaceId ||
    proposal.status !== "proposed" ||
    proposal.proposal_version.length === 0 ||
    idempotencyKey.length === 0
  ) {
    throw new LocalActionDecisionContractError(
      "Решение устарело или не относится к выбранной компании.",
      "preflight"
    );
  }

  const request = {
    expected_snapshot_id: expectedSnapshotId,
    idempotency_key: idempotencyKey,
    proposal_version: proposal.proposal_version
  };
  const response = decision === "approved"
    ? await approveActionProposal(workspaceId, proposal.id, request, { signal })
    : await rejectActionProposal(
        workspaceId,
        proposal.id,
        { ...request, reason },
        { signal }
      );
  validateLocalDecisionResponse({
    decision,
    proposal,
    response,
    workspaceId
  });
  return response;
}

export async function submitLocalActionDecisionWithOneRetry(
  input: SubmitLocalActionDecisionInput
): Promise<ActionProposalDecisionResponse> {
  try {
    return await submitLocalActionDecision(input);
  } catch (error: unknown) {
    if (!isAmbiguousLocalActionDecisionFailure(error)) {
      throw error;
    }
  }
  return submitLocalActionDecision(input);
}

export function isAmbiguousLocalActionDecisionFailure(error: unknown): boolean {
  if (error instanceof LocalActionDecisionContractError) {
    return error.phase === "response";
  }
  if (error instanceof ApiRequestError) {
    return error.status >= 500 && error.status <= 599;
  }
  if (error instanceof TypeError) {
    return true;
  }
  return typeof DOMException !== "undefined" &&
    error instanceof DOMException &&
    error.name === "NetworkError";
}

export function localDecisionLabel(decision: LocalActionDecision): string {
  return decision === "approved" ? "Принято" : "Отклонено";
}

function validateLocalDecisionResponse({
  decision,
  proposal,
  response,
  workspaceId
}: {
  decision: LocalActionDecision;
  proposal: ActionProposal;
  response: ActionProposalDecisionResponse;
  workspaceId: string;
}): void {
  const receipt = response.decision_receipt;
  if (
    response.proposal.id !== proposal.id ||
    response.proposal.workspace_id !== workspaceId ||
    !proposalStatusContainsDecision(response.proposal.status, decision) ||
    receipt === null ||
    receipt.receipt_id.length === 0 ||
    receipt.recorded_at.length === 0 ||
    receipt.proposal_id !== proposal.id ||
    receipt.decision !== decision ||
    receipt.proposal_version !== proposal.proposal_version ||
    receipt.external_write_performed !== false
  ) {
    throw new LocalActionDecisionContractError(
      "Сервер не подтвердил точную локальную квитанцию."
    );
  }
}

function proposalStatusContainsDecision(
  status: ActionProposal["status"],
  decision: LocalActionDecision
): boolean {
  if (decision === "rejected") return status === "rejected";
  return status === "approved" || status === "executed" || status === "failed";
}
