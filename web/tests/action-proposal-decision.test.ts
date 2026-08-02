import assert from "node:assert/strict";
import test from "node:test";

import {
  isAmbiguousLocalActionDecisionFailure,
  LocalActionDecisionContractError,
  submitLocalActionDecision,
  submitLocalActionDecisionWithOneRetry
} from "../lib/action-proposal-decision";
import { ApiRequestError } from "../lib/api";
import type {
  ActionProposal,
  ActionProposalDecisionResponse,
  LocalActionDecisionReceipt
} from "../lib/types";

const proposedProposal: ActionProposal = {
  action_type: "internal_todo",
  approved_at: null,
  approved_by_user_id: null,
  briefing_item_id: null,
  created_at: "2026-07-17T08:00:00Z",
  created_by: "user",
  created_by_user_id: "user-1",
  description: "Review the evidence before recording a local decision.",
  evidence_refs: [],
  execution_started: false,
  id: "proposal-1",
  is_live: false,
  payload: { source: "headquarters" },
  proposal_version: "proposal-version-1",
  rejected_at: null,
  rejected_by_user_id: null,
  rejection_reason: null,
  status: "proposed",
  target_provider: "internal",
  title: "Confirm the launch plan",
  updated_at: "2026-07-17T08:00:00Z",
  warnings: [],
  workspace_id: "workspace-123"
};

function decidedProposal(
  decision: "approved" | "rejected"
): ActionProposal {
  return {
    ...proposedProposal,
    approved_at: decision === "approved" ? "2026-07-17T08:05:00Z" : null,
    approved_by_user_id: decision === "approved" ? "user-1" : null,
    rejected_at: decision === "rejected" ? "2026-07-17T08:05:00Z" : null,
    rejected_by_user_id: decision === "rejected" ? "user-1" : null,
    rejection_reason: decision === "rejected" ? "Evidence is incomplete" : null,
    status: decision,
    updated_at: "2026-07-17T08:05:00Z"
  };
}

function localReceipt(
  decision: "approved" | "rejected"
): LocalActionDecisionReceipt {
  return {
    decision,
    external_write_performed: false,
    proposal_id: proposedProposal.id,
    proposal_version: proposedProposal.proposal_version,
    receipt_id: `receipt-${decision}`,
    recorded_at: "2026-07-17T08:05:00Z",
    replayed: false
  };
}

function mutationResponse(
  decision: "approved" | "rejected"
): ActionProposalDecisionResponse {
  return {
    decision_receipt: localReceipt(decision),
    execution_started: false,
    is_live: false,
    proposal: decidedProposal(decision),
    warnings: []
  };
}

function jsonResponse(payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    headers: { "Content-Type": "application/json" },
    status: 200
  });
}

type MutableMutationResponse = Omit<
  ActionProposalDecisionResponse,
  "decision_receipt"
> & {
  decision_receipt:
    | (Omit<LocalActionDecisionReceipt, "external_write_performed"> & {
        external_write_performed: boolean;
      })
    | null;
};

test("submits exact local approve and reject contracts", async () => {
  const originalFetch = globalThis.fetch;
  const calls: string[] = [];
  globalThis.fetch = (async (input, init) => {
    const url = String(input);
    calls.push(`${init?.method ?? "GET"} ${url}`);
    if (url.endsWith("/approve")) {
      assert.equal(
        init?.body,
        JSON.stringify({
          expected_snapshot_id: "snapshot-7",
          idempotency_key: "approve-key",
          proposal_version: proposedProposal.proposal_version
        })
      );
      return jsonResponse(mutationResponse("approved"));
    }
    assert.ok(url.endsWith("/reject"));
    assert.equal(
      init?.body,
      JSON.stringify({
        expected_snapshot_id: null,
        idempotency_key: "reject-key",
        proposal_version: proposedProposal.proposal_version,
        reason: "Evidence is incomplete"
      })
    );
    return jsonResponse(mutationResponse("rejected"));
  }) as typeof fetch;

  try {
    const approved = await submitLocalActionDecision({
      decision: "approved",
      expectedSnapshotId: "snapshot-7",
      idempotencyKey: "approve-key",
      proposal: proposedProposal,
      workspaceId: "workspace-123"
    });
    const rejected = await submitLocalActionDecision({
      decision: "rejected",
      idempotencyKey: "reject-key",
      proposal: proposedProposal,
      reason: "Evidence is incomplete",
      workspaceId: "workspace-123"
    });

    assert.equal(approved.decision_receipt?.decision, "approved");
    assert.equal(rejected.decision_receipt?.decision, "rejected");
    assert.deepEqual(calls, [
      "POST http://localhost/api/v1/workspaces/workspace-123/actions/proposals/proposal-1/approve",
      "POST http://localhost/api/v1/workspaces/workspace-123/actions/proposals/proposal-1/reject"
    ]);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("rejects stale input before the request and rejects imprecise receipts", async () => {
  const originalFetch = globalThis.fetch;
  let fetchCalled = false;
  globalThis.fetch = (async () => {
    fetchCalled = true;
    return jsonResponse(mutationResponse("approved"));
  }) as typeof fetch;

  try {
    const invalidProposals: ActionProposal[] = [
      { ...proposedProposal, id: "" },
      { ...proposedProposal, workspace_id: "workspace-other" },
      { ...proposedProposal, status: "approved" },
      { ...proposedProposal, proposal_version: "" }
    ];
    for (const proposal of invalidProposals) {
      await assert.rejects(
        submitLocalActionDecisionWithOneRetry({
          decision: "approved",
          idempotencyKey: "approve-key",
          proposal,
          workspaceId: "workspace-123"
        }),
        LocalActionDecisionContractError
      );
    }
    await assert.rejects(
      submitLocalActionDecisionWithOneRetry({
        decision: "approved",
        idempotencyKey: "",
        proposal: proposedProposal,
        workspaceId: "workspace-123"
      }),
      LocalActionDecisionContractError
    );
    assert.equal(fetchCalled, false);

    const invalidResponses: Array<{
      mutate: (payload: MutableMutationResponse) => void;
      name: string;
    }> = [
      {
        name: "different proposal",
        mutate: (payload) => { payload.proposal.id = "proposal-other"; }
      },
      {
        name: "different workspace",
        mutate: (payload) => { payload.proposal.workspace_id = "workspace-other"; }
      },
      {
        name: "wrong decision status",
        mutate: (payload) => { payload.proposal.status = "rejected"; }
      },
      {
        name: "missing receipt",
        mutate: (payload) => { payload.decision_receipt = null; }
      },
      {
        name: "different receipt proposal",
        mutate: (payload) => {
          payload.decision_receipt!.proposal_id = "proposal-other";
        }
      },
      {
        name: "wrong receipt decision",
        mutate: (payload) => { payload.decision_receipt!.decision = "rejected"; }
      },
      {
        name: "stale receipt version",
        mutate: (payload) => {
          payload.decision_receipt!.proposal_version = "stale-version";
        }
      },
      {
        name: "external write claim",
        mutate: (payload) => {
          payload.decision_receipt!.external_write_performed = true;
        }
      }
    ];

    for (const invalid of invalidResponses) {
      const payload = structuredClone(
        mutationResponse("approved")
      ) as MutableMutationResponse;
      invalid.mutate(payload);
      globalThis.fetch = (async () => jsonResponse(payload)) as typeof fetch;
      await assert.rejects(
        submitLocalActionDecision({
          decision: "approved",
          idempotencyKey: "approve-key",
          proposal: proposedProposal,
          workspaceId: "workspace-123"
        }),
        (error: unknown) => {
          assert.ok(error instanceof LocalActionDecisionContractError, invalid.name);
          assert.match(error.message, /точную локальную квитанцию/);
          return true;
        }
      );
    }
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("retries one network failure with the exact same POST contract", async () => {
  const originalFetch = globalThis.fetch;
  const calls: Array<{ body: BodyInit | null | undefined; url: string }> = [];
  globalThis.fetch = (async (input, init) => {
    calls.push({ body: init?.body, url: String(input) });
    if (calls.length === 1) {
      throw new TypeError("network connection closed before a response");
    }
    return jsonResponse(mutationResponse("approved"));
  }) as typeof fetch;

  try {
    const response = await submitLocalActionDecisionWithOneRetry({
      decision: "approved",
      expectedSnapshotId: "snapshot-7",
      idempotencyKey: "stable-idempotency-key",
      proposal: proposedProposal,
      workspaceId: proposedProposal.workspace_id
    });

    assert.equal(response.decision_receipt.decision, "approved");
    assert.equal(calls.length, 2);
    assert.deepEqual(calls[1], calls[0]);
    assert.equal(
      calls[0]?.body,
      JSON.stringify({
        expected_snapshot_id: "snapshot-7",
        idempotency_key: "stable-idempotency-key",
        proposal_version: proposedProposal.proposal_version
      })
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("retries one 5xx and one malformed response, then accepts only a real receipt", async () => {
  const originalFetch = globalThis.fetch;

  try {
    for (const failure of ["5xx", "contract"] as const) {
      let calls = 0;
      globalThis.fetch = (async () => {
        calls += 1;
        if (calls === 1 && failure === "5xx") {
          return new Response(JSON.stringify({ detail: "temporarily unavailable" }), {
            headers: { "Content-Type": "application/json" },
            status: 503
          });
        }
        if (calls === 1) {
          return jsonResponse({
            ...mutationResponse("approved"),
            decision_receipt: null
          });
        }
        return jsonResponse(mutationResponse("approved"));
      }) as typeof fetch;

      const response = await submitLocalActionDecisionWithOneRetry({
        decision: "approved",
        idempotencyKey: `${failure}-same-key`,
        proposal: proposedProposal,
        workspaceId: proposedProposal.workspace_id
      });
      assert.equal(response.decision_receipt.receipt_id, "receipt-approved");
      assert.equal(calls, 2, failure);
    }
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("never retries a 4xx response", async () => {
  const originalFetch = globalThis.fetch;

  try {
    for (const status of [400, 403, 404, 409, 422]) {
      let calls = 0;
      globalThis.fetch = (async () => {
        calls += 1;
        return new Response(JSON.stringify({ detail: `request failed: ${status}` }), {
          headers: { "Content-Type": "application/json" },
          status
        });
      }) as typeof fetch;

      await assert.rejects(
        submitLocalActionDecisionWithOneRetry({
          decision: "approved",
          idempotencyKey: `status-${status}-key`,
          proposal: proposedProposal,
          workspaceId: proposedProposal.workspace_id
        }),
        (error: unknown) => {
          assert.ok(error instanceof ApiRequestError);
          assert.equal(error.status, status);
          return true;
        }
      );
      assert.equal(calls, 1, `HTTP ${status}`);
    }
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("stops after exactly one retry when an ambiguous failure persists", async () => {
  const originalFetch = globalThis.fetch;

  try {
    for (const failure of ["network", "contract"] as const) {
      let calls = 0;
      globalThis.fetch = (async () => {
        calls += 1;
        if (failure === "network") {
          throw new TypeError("network still unavailable");
        }
        return jsonResponse({
          ...mutationResponse("approved"),
          decision_receipt: null
        });
      }) as typeof fetch;

      await assert.rejects(
        submitLocalActionDecisionWithOneRetry({
          decision: "approved",
          idempotencyKey: `${failure}-stable-key`,
          proposal: proposedProposal,
          workspaceId: proposedProposal.workspace_id
        }),
        failure === "network" ? TypeError : LocalActionDecisionContractError
      );
      assert.equal(calls, 2, failure);
    }
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("retains an attempt key only while the outcome is still ambiguous", () => {
  assert.equal(isAmbiguousLocalActionDecisionFailure(new TypeError("network")), true);
  assert.equal(
    isAmbiguousLocalActionDecisionFailure(new ApiRequestError("unavailable", 503)),
    true
  );
  assert.equal(
    isAmbiguousLocalActionDecisionFailure(
      new LocalActionDecisionContractError("receipt mismatch", "response")
    ),
    true
  );
  assert.equal(
    isAmbiguousLocalActionDecisionFailure(new ApiRequestError("stale", 409)),
    false
  );
  assert.equal(
    isAmbiguousLocalActionDecisionFailure(
      new LocalActionDecisionContractError("stale input", "preflight")
    ),
    false
  );
});
