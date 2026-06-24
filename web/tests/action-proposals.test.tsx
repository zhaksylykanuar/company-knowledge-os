import assert from "node:assert/strict";
import test from "node:test";

import { renderToStaticMarkup } from "react-dom/server";

import {
  approveActionProposal,
  buildWorkspaceActionProposalApprovePath,
  buildWorkspaceActionProposalRejectPath,
  buildWorkspaceActionProposalsCollectionPath,
  buildWorkspaceActionProposalsPath,
  createActionProposal,
  fetchActionProposals,
  rejectActionProposal
} from "../lib/api";
import type {
  ActionProposal,
  ActionProposalListResponse,
  ActionProposalMutationResponse
} from "../lib/types";
import {
  ActionProposalsPanelView,
  DEFAULT_CREATE_FORM
} from "../components/ActionProposalsPanel";
import { EvidenceDrawer } from "../components/EvidenceDrawer";

const proposedProposal: ActionProposal = {
  id: "proposal-1",
  workspace_id: "workspace-123",
  briefing_item_id: null,
  target_provider: "github",
  action_type: "create_github_issue",
  title: "Create follow-up GitHub issue",
  description: "Track an evidence-backed follow-up locally before any write.",
  payload: {
    body: "Proposed future issue body.",
    repository_full_name: "qtwin-io/founderos-api",
    title: "Follow up on FounderOS signal"
  },
  status: "proposed",
  evidence_refs: [
    {
      kind: "github_issue",
      source: "github",
      ref: "qtwin-io/founderos-api#issue/42",
      url: "https://github.com/qtwin-io/founderos-api/issues/42"
    }
  ],
  created_by: "user",
  created_by_user_id: "user-1",
  approved_by_user_id: null,
  approved_at: null,
  rejected_by_user_id: null,
  rejected_at: null,
  rejection_reason: null,
  created_at: "2026-06-25T01:00:00+06:00",
  updated_at: "2026-06-25T01:00:00+06:00",
  is_live: false,
  execution_started: false,
  warnings: ["Action proposal API is local-only and does not execute provider actions."]
};

const approvedProposal: ActionProposal = {
  ...proposedProposal,
  id: "proposal-2",
  status: "approved",
  approved_by_user_id: "user-2",
  approved_at: "2026-06-25T01:05:00+06:00",
  title: "Approved local proposal"
};

const rejectedProposal: ActionProposal = {
  ...proposedProposal,
  id: "proposal-3",
  evidence_refs: [],
  rejected_by_user_id: "user-3",
  rejected_at: "2026-06-25T01:06:00+06:00",
  rejection_reason: "Not needed",
  status: "rejected",
  title: "Rejected local proposal"
};

const sampleList: ActionProposalListResponse = {
  count: 3,
  is_live: false,
  proposals: [proposedProposal, approvedProposal, rejectedProposal],
  warnings: ["Action proposal API is local-only and does not execute provider actions."]
};

const emptyList: ActionProposalListResponse = {
  count: 0,
  is_live: false,
  proposals: [],
  warnings: []
};

const mutationResponse: ActionProposalMutationResponse = {
  execution_started: false,
  is_live: false,
  proposal: approvedProposal,
  warnings: [
    "Action approved locally. Execution is deferred to a later step.",
    "Action proposal API is local-only and does not execute provider actions."
  ]
};

function renderPanel(
  props: Partial<Parameters<typeof ActionProposalsPanelView>[0]> = {}
): string {
  return renderToStaticMarkup(
    <ActionProposalsPanelView
      createForm={props.createForm ?? DEFAULT_CREATE_FORM}
      data={"data" in props ? props.data ?? null : sampleList}
      error={props.error ?? null}
      onApprove={props.onApprove}
      onCloseEvidence={props.onCloseEvidence}
      onCreate={props.onCreate}
      onCreateFormChange={props.onCreateFormChange}
      onReject={props.onReject}
      onRetry={props.onRetry}
      onSelectEvidence={props.onSelectEvidence}
      pendingMutation={props.pendingMutation ?? null}
      selectedEvidence={props.selectedEvidence ?? null}
      selectedEvidenceTitle={props.selectedEvidenceTitle ?? null}
      status={props.status ?? "ready"}
      successMessage={props.successMessage ?? null}
    />
  );
}

test("builds action proposal URLs", () => {
  assert.equal(
    buildWorkspaceActionProposalsCollectionPath("workspace-123"),
    "/api/v1/workspaces/workspace-123/actions/proposals"
  );
  assert.equal(
    buildWorkspaceActionProposalsPath("workspace-123"),
    "/api/v1/workspaces/workspace-123/actions/proposals?limit=50"
  );
  assert.equal(
    buildWorkspaceActionProposalsPath("workspace-123", {
      action_type: "create_github_issue",
      limit: 10,
      status: "proposed",
      target_provider: "github"
    }),
    "/api/v1/workspaces/workspace-123/actions/proposals?limit=10&status=proposed&target_provider=github&action_type=create_github_issue"
  );
  assert.equal(
    buildWorkspaceActionProposalApprovePath("workspace-123", "proposal-1"),
    "/api/v1/workspaces/workspace-123/actions/proposals/proposal-1/approve"
  );
  assert.equal(
    buildWorkspaceActionProposalRejectPath("workspace-123", "proposal-1"),
    "/api/v1/workspaces/workspace-123/actions/proposals/proposal-1/reject"
  );
});

test("fetches and parses local action proposals", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (input) => {
    assert.equal(
      String(input),
      "http://localhost:8000/api/v1/workspaces/workspace-123/actions/proposals?limit=50"
    );
    return new Response(JSON.stringify(sampleList), {
      headers: { "Content-Type": "application/json" },
      status: 200
    });
  }) as typeof fetch;

  try {
    const payload = await fetchActionProposals("workspace-123", {}, {
      includeOwnerEmail: false
    });
    assert.equal(payload.count, 3);
    assert.equal(payload.proposals[0]?.execution_started, false);
    assert.equal(payload.is_live, false);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("creates local action proposal without external execution", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (input, init) => {
    assert.equal(
      String(input),
      "http://localhost:8000/api/v1/workspaces/workspace-123/actions/proposals"
    );
    assert.equal(init?.method, "POST");
    assert.equal(
      init?.body,
      JSON.stringify({
        briefing_item_id: null,
        target_provider: "github",
        action_type: "create_github_issue",
        title: "Create follow-up GitHub issue",
        description: "Evidence-backed local proposal.",
        payload: {
          repository_full_name: "qtwin-io/founderos-api",
          title: "Create follow-up GitHub issue"
        },
        evidence_refs: [
          {
            kind: "github_issue",
            source: "github",
            ref: "qtwin-io/founderos-api#issue/42",
            url: null
          }
        ],
        created_by: "user"
      })
    );
    return new Response(JSON.stringify({ ...mutationResponse, proposal: proposedProposal }), {
      headers: { "Content-Type": "application/json" },
      status: 201
    });
  }) as typeof fetch;

  try {
    const payload = await createActionProposal(
      "workspace-123",
      {
        action_type: "create_github_issue",
        description: "Evidence-backed local proposal.",
        evidence_refs: [
          {
            kind: "github_issue",
            source: "github",
            ref: "qtwin-io/founderos-api#issue/42",
            url: null
          }
        ],
        payload: {
          repository_full_name: "qtwin-io/founderos-api",
          title: "Create follow-up GitHub issue"
        },
        target_provider: "github",
        title: "Create follow-up GitHub issue"
      },
      { includeOwnerEmail: false }
    );
    assert.equal(payload.execution_started, false);
    assert.equal(payload.proposal.status, "proposed");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("approves and rejects locally through supported endpoints", async () => {
  const originalFetch = globalThis.fetch;
  const calls: string[] = [];
  globalThis.fetch = (async (input, init) => {
    calls.push(`${init?.method ?? "GET"} ${String(input)}`);
    if (String(input).endsWith("/reject")) {
      assert.equal(init?.body, JSON.stringify({ reason: "Not now" }));
      return new Response(
        JSON.stringify({ ...mutationResponse, proposal: rejectedProposal }),
        {
          headers: { "Content-Type": "application/json" },
          status: 200
        }
      );
    }
    return new Response(JSON.stringify(mutationResponse), {
      headers: { "Content-Type": "application/json" },
      status: 200
    });
  }) as typeof fetch;

  try {
    const approved = await approveActionProposal("workspace-123", "proposal-1", {
      includeOwnerEmail: false
    });
    const rejected = await rejectActionProposal(
      "workspace-123",
      "proposal-1",
      { reason: "Not now" },
      { includeOwnerEmail: false }
    );

    assert.equal(approved.proposal.status, "approved");
    assert.equal(approved.execution_started, false);
    assert.equal(rejected.proposal.status, "rejected");
    assert.deepEqual(calls, [
      "POST http://localhost:8000/api/v1/workspaces/workspace-123/actions/proposals/proposal-1/approve",
      "POST http://localhost:8000/api/v1/workspaces/workspace-123/actions/proposals/proposal-1/reject"
    ]);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("surfaces unsupported transition errors", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async () =>
    new Response(JSON.stringify({ detail: "action proposal is not in proposed status" }), {
      headers: { "Content-Type": "application/json" },
      status: 409
    })) as typeof fetch;

  try {
    await assert.rejects(
      approveActionProposal("workspace-123", "proposal-1", {
        includeOwnerEmail: false
      }),
      /action proposal is not in proposed status/
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("renders loading, missing, empty, unsupported, and error states", () => {
  assert.match(renderPanel({ data: null, status: "loading" }), /Loading action proposals/);
  assert.match(renderPanel({ data: null, status: "missing" }), /Workspace settings required/);
  assert.match(renderPanel({ data: emptyList, status: "empty" }), /No action proposals yet/);
  assert.match(
    renderPanel({ data: null, status: "unsupported" }),
    /Action proposals unsupported/
  );
  const errorHtml = renderPanel({
    data: null,
    error: "transition failed",
    onRetry: () => undefined,
    status: "error"
  });
  assert.match(errorHtml, /Action proposals unavailable/);
  assert.match(errorHtml, /transition failed/);
  assert.match(errorHtml, /Retry/);
});

test("renders proposal cards, statuses, evidence refs, and local-only boundary", () => {
  const html = renderPanel({
    onApprove: () => undefined,
    onReject: () => undefined,
    onSelectEvidence: () => undefined
  });
  assert.match(html, /Action Proposals/);
  assert.match(html, /Local approval workflow/);
  assert.match(html, /External execution: disabled in this UI/);
  assert.match(html, /Create follow-up GitHub issue/);
  assert.match(html, /qtwin-io\/founderos-api/);
  assert.match(html, /Follow up on FounderOS signal/);
  assert.match(html, /Approve locally/);
  assert.match(html, /Reject locally/);
  assert.match(html, /Approved locally\. External execution is disabled in this UI/);
  assert.match(html, /Rejected locally\. No external action was run/);
  assert.match(html, /Evidence: qtwin-io\/founderos-api#issue\/42/);
  assert.match(html, /No evidence refs returned by backend for this proposal/);
  assert.doesNotMatch(html, /sent to GitHub/i);
  assert.doesNotMatch(html, /created GitHub issue/i);
  assert.doesNotMatch(html, /source_events/);
});

test("renders create form and pending local mutations", () => {
  const html = renderPanel({
    createForm: {
      ...DEFAULT_CREATE_FORM,
      repositoryFullName: "qtwin-io/founderos-api",
      title: "Create follow-up GitHub issue"
    },
    pendingMutation: "create"
  });
  assert.match(html, /Proposal type/);
  assert.match(html, /GitHub issue proposal/);
  assert.match(html, /Creating local proposal/);
  assert.match(html, /does not create a\s+GitHub issue or call a live provider/);
});

test("renders success message after local approval or rejection", () => {
  const html = renderPanel({
    successMessage: "Approved locally. External execution is not enabled in this UI."
  });
  assert.match(html, /Approved locally/);
  assert.match(html, /External execution is not enabled in this UI/);
});

test("renders proposal evidence drawer details without raw payload dumps", () => {
  const evidence = proposedProposal.evidence_refs[0] ?? null;
  const html = renderToStaticMarkup(
    <EvidenceDrawer
      evidence={evidence}
      itemTitle="Create follow-up GitHub issue"
      onClose={() => undefined}
    />
  );

  assert.match(html, /Source detail/);
  assert.match(html, /github_issue/);
  assert.match(html, /qtwin-io\/founderos-api#issue\/42/);
  assert.match(html, /Open source/);
  assert.match(html, /No snippet returned by backend/);
  assert.doesNotMatch(html, /provider_response/);
  assert.doesNotMatch(html, /access_token/);
});
