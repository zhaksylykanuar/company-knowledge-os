import assert from "node:assert/strict";
import test from "node:test";

import { renderToStaticMarkup } from "react-dom/server";

import {
  approveActionProposal,
  bulkApproveActionProposals,
  bulkRejectActionProposals,
  buildWorkspaceActionProposalApprovePath,
  buildWorkspaceActionProposalBulkApprovePath,
  buildWorkspaceActionProposalBulkRejectPath,
  buildWorkspaceActionProposalPath,
  buildWorkspaceActionProposalRejectPath,
  buildWorkspaceActionProposalsCollectionPath,
  buildWorkspaceActionProposalsPath,
  createActionProposal,
  fetchActionProposal,
  fetchActionProposals,
  rejectActionProposal
} from "../lib/api";
import { M, T } from "../lib/messages";
import type {
  ActionProposal,
  ActionProposalDecisionResponse,
  ActionProposalListResponse,
  ActionProposalMutationResponse
} from "../lib/types";
import {
  actionCapabilitiesForRole,
  ActionProposalsPanelView,
  canScheduleProposalRefresh,
  DEFAULT_CREATE_FORM,
  loadActionProposalPanelData,
  mergeExactActionProposal,
  summarizeActionReviewReadiness,
  summarizeBulkResponse
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
  proposal_version: "ap1_proposal_1",
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

const briefingProposal: ActionProposal = {
  ...proposedProposal,
  id: "proposal-4",
  target_provider: "internal",
  action_type: "internal_todo",
  title: "Review synced GitHub work before approving actions",
  description: "Repository inventory is available\n\nOne canonical repo is visible.",
  payload: {
    briefing_item_key: "repo-coverage",
    category: "repository",
    recommended_next_step: "Review synced GitHub work before approving actions.",
    related_entities: ["qtwin-io/founderos-api", "qtwin-io/founderos-web"],
    severity: "info",
    source: "briefing_item"
  },
  evidence_refs: [
    {
      kind: "repository_inventory_snapshot",
      source: "github",
      ref: "qtwin-io/founderos-api",
      url: "https://github.com/qtwin-io/founderos-api"
    },
    {
      kind: "repository_inventory_snapshot",
      source: "github",
      ref: "qtwin-io/founderos-web",
      url: "https://github.com/qtwin-io/founderos-web"
    }
  ]
};

const manualInternalProposal: ActionProposal = {
  ...proposedProposal,
  id: "proposal-5",
  target_provider: "internal",
  action_type: "internal_todo",
  title: "Manual internal follow-up",
  description: "A manually created local todo.",
  payload: {
    note: "Manual local review note"
  },
  evidence_refs: [
    {
      kind: "internal_note",
      source: "founderos",
      ref: "manual-note-1",
      url: null
    }
  ]
};

const auditProposal: ActionProposal = {
  ...proposedProposal,
  id: "proposal-6",
  target_provider: "internal",
  action_type: "internal_todo",
  title: "Imported repo audit follow-up: qtwin-io/base-collector",
  description: "Repository: qtwin-io/base-collector",
  payload: {
    source: "repo_audit_import",
    repository_full_name: "qtwin-io/base-collector",
    area_candidate: "OPS",
    recommended_next_step: "Add CI before private beta.",
    related_entities: ["ci_not_detected", "tests_not_detected"],
    severity: "high"
  },
  evidence_refs: [
    {
      kind: "repo_audit_external",
      source: "external_repo_audit_import",
      ref: "external-audit:base-collector:ci",
      url: null
    }
  ]
};

const deterministicAuditProposal: ActionProposal = {
  ...proposedProposal,
  id: "proposal-7",
  target_provider: "internal",
  action_type: "internal_todo",
  title: "Repo audit follow-up: qtwin-io/local-service",
  description: "Repository: qtwin-io/local-service",
  payload: {
    source: "repo_audit",
    repository_full_name: "qtwin-io/local-service",
    activity_bucket: "stale",
    area_candidate: "CORE",
    related_entities: ["readme_missing"]
  },
  evidence_refs: [
    {
      kind: "repo_audit_fact",
      source: "repo_audit",
      ref: "github_discovery_snapshot:repos.json:local-service:metadata",
      url: null
    }
  ]
};

const executedProposal: ActionProposal = {
  ...approvedProposal,
  id: "proposal-8",
  execution_started: true,
  title: "Executed GitHub proposal"
};

const failedProposal: ActionProposal = {
  ...approvedProposal,
  id: "proposal-9",
  execution_started: true,
  status: "failed",
  title: "Failed GitHub proposal"
};

const approvedInternalProposal: ActionProposal = {
  ...manualInternalProposal,
  approved_at: "2026-07-14T10:00:00Z",
  id: "proposal-10",
  status: "approved",
  title: "Approved internal follow-up"
};

const sampleList: ActionProposalListResponse = {
  count: 3,
  is_live: false,
  proposals: [proposedProposal, approvedProposal, rejectedProposal],
  warnings: ["Action proposal API is local-only and does not execute provider actions."]
};

const groupedList: ActionProposalListResponse = {
  count: 5,
  is_live: false,
  proposals: [
    proposedProposal,
    approvedProposal,
    rejectedProposal,
    briefingProposal,
    manualInternalProposal
  ],
  warnings: []
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

const decisionResponse: ActionProposalDecisionResponse = {
  ...mutationResponse,
  decision_receipt: {
    decision: "approved",
    external_write_performed: false,
    proposal_id: approvedProposal.id,
    proposal_version: proposedProposal.proposal_version,
    receipt_id: "receipt-1",
    recorded_at: "2026-06-25T01:05:00+06:00",
    replayed: false
  },
  execution_started: false,
  is_live: false
};

function renderPanel(
  props: Partial<Parameters<typeof ActionProposalsPanelView>[0]> = {}
): string {
  return renderToStaticMarkup(
    <ActionProposalsPanelView
      activeProposalId={props.activeProposalId ?? null}
      canCreateProposals={props.canCreateProposals ?? true}
      canReviewProposals={props.canReviewProposals ?? true}
      createForm={props.createForm ?? DEFAULT_CREATE_FORM}
      data={"data" in props ? props.data ?? null : sampleList}
      error={props.error ?? null}
      executionBusyProposalId={props.executionBusyProposalId ?? null}
      isRefreshing={props.isRefreshing ?? false}
      mutationError={props.mutationError ?? null}
      onApprove={props.onApprove}
      onCloseEvidence={props.onCloseEvidence}
      onCreate={props.onCreate}
      onCreateFormChange={props.onCreateFormChange}
      onReject={props.onReject}
      onRefreshProposals={props.onRefreshProposals}
      onSelectProposal={props.onSelectProposal}
      onRetry={props.onRetry}
      onOriginFilterChange={props.onOriginFilterChange}
      onBulkApprove={props.onBulkApprove}
      onBulkReject={props.onBulkReject}
      onClearSelectedProposals={props.onClearSelectedProposals}
      onSelectEvidence={props.onSelectEvidence}
      onSelectVisibleProposed={props.onSelectVisibleProposed}
      onAuditSourceFilterChange={props.onAuditSourceFilterChange}
      onExecutionBusyChange={props.onExecutionBusyChange}
      onStatusFilterChange={props.onStatusFilterChange}
      onToggleProposalSelection={props.onToggleProposalSelection}
      pendingMutation={props.pendingMutation ?? null}
      auditSourceFilter={props.auditSourceFilter ?? "all"}
      originFilter={props.originFilter ?? "all"}
      selectedProposalIds={props.selectedProposalIds ?? []}
      selectedEvidence={props.selectedEvidence ?? null}
      selectedEvidenceTitle={props.selectedEvidenceTitle ?? null}
      selectedEvidenceCount={props.selectedEvidenceCount ?? null}
      selectedEvidenceProposalId={props.selectedEvidenceProposalId ?? null}
      statusFilter={props.statusFilter ?? "all"}
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
    buildWorkspaceActionProposalPath("workspace-123", "proposal/1"),
    "/api/v1/workspaces/workspace-123/actions/proposals/proposal%2F1"
  );
  assert.equal(
    buildWorkspaceActionProposalApprovePath("workspace-123", "proposal-1"),
    "/api/v1/workspaces/workspace-123/actions/proposals/proposal-1/approve"
  );
  assert.equal(
    buildWorkspaceActionProposalRejectPath("workspace-123", "proposal-1"),
    "/api/v1/workspaces/workspace-123/actions/proposals/proposal-1/reject"
  );
  assert.equal(
    buildWorkspaceActionProposalBulkApprovePath("workspace-123"),
    "/api/v1/workspaces/workspace-123/actions/proposals/bulk-approve"
  );
  assert.equal(
    buildWorkspaceActionProposalBulkRejectPath("workspace-123"),
    "/api/v1/workspaces/workspace-123/actions/proposals/bulk-reject"
  );
});

test("maps the selected workspace role to the backend action capability boundary", () => {
  assert.deepEqual(actionCapabilitiesForRole("viewer"), {
    canCreateProposals: false,
    canReviewProposals: false
  });
  assert.deepEqual(actionCapabilitiesForRole("member"), {
    canCreateProposals: true,
    canReviewProposals: false
  });
  assert.deepEqual(actionCapabilitiesForRole("admin"), {
    canCreateProposals: true,
    canReviewProposals: true
  });
  assert.deepEqual(actionCapabilitiesForRole("owner"), {
    canCreateProposals: true,
    canReviewProposals: true
  });
  assert.deepEqual(actionCapabilitiesForRole(null), {
    canCreateProposals: false,
    canReviewProposals: false
  });
});

test("keeps viewer actions read-only while preserving proposal evidence", () => {
  const html = renderPanel({
    canCreateProposals: false,
    canReviewProposals: false
  });

  assert.ok(html.includes("Только просмотр"));
  assert.ok(html.includes("Что доступно в режиме просмотра?"));
  assert.ok(html.includes(proposedProposal.title));
  assert.ok(html.includes(proposedProposal.evidence_refs[0]!.ref));
  assert.doesNotMatch(html, /proposal-form/);
  assert.doesNotMatch(html, /proposal-selection/);
  assert.doesNotMatch(html, new RegExp(M.actionsPanel.bulkTitle));
  assert.doesNotMatch(html, new RegExp(M.actionExecution.previewTitle));
});

test("lets members create local proposals without review or execution controls", () => {
  const html = renderPanel({
    canCreateProposals: true,
    canReviewProposals: false
  });

  assert.match(html, /proposal-form/);
  assert.ok(html.includes("можете создавать локальные предложения"));
  assert.doesNotMatch(html, /proposal-selection/);
  assert.doesNotMatch(html, new RegExp(M.actionsPanel.bulkTitle));
  assert.doesNotMatch(html, new RegExp(M.actionExecution.previewTitle));
});

test("fetches and parses local action proposals", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (input) => {
    assert.equal(
      String(input),
      "http://localhost/api/v1/workspaces/workspace-123/actions/proposals?limit=50"
    );
    return new Response(JSON.stringify(sampleList), {
      headers: { "Content-Type": "application/json" },
      status: 200
    });
  }) as typeof fetch;

  try {
    const payload = await fetchActionProposals("workspace-123", {}, {});
    assert.equal(payload.count, 3);
    assert.equal(payload.proposals[0]?.execution_started, false);
    assert.equal(payload.is_live, false);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("fetches one exact workspace-scoped action proposal", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (input) => {
    assert.equal(
      String(input),
      "http://localhost/api/v1/workspaces/workspace-123/actions/proposals/proposal-5"
    );
    return new Response(JSON.stringify(manualInternalProposal), {
      headers: { "Content-Type": "application/json" },
      status: 200
    });
  }) as typeof fetch;

  try {
    const proposal = await fetchActionProposal("workspace-123", "proposal-5");
    assert.equal(proposal.id, manualInternalProposal.id);
    assert.equal(proposal.workspace_id, "workspace-123");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("loads and deduplicates an exact linked proposal outside the bounded list", async () => {
  const originalFetch = globalThis.fetch;
  const requests: string[] = [];
  globalThis.fetch = (async (input) => {
    const request = String(input);
    requests.push(request);
    if (request.endsWith("/actions/proposals?limit=100")) {
      return new Response(JSON.stringify(sampleList), {
        headers: { "Content-Type": "application/json" },
        status: 200
      });
    }
    return new Response(JSON.stringify(manualInternalProposal), {
      headers: { "Content-Type": "application/json" },
      status: 200
    });
  }) as typeof fetch;

  try {
    const result = await loadActionProposalPanelData(
      "workspace-123",
      manualInternalProposal.id
    );
    assert.equal(result.status, "ready");
    assert.equal(result.error, null);
    assert.equal(result.data?.proposals[0]?.id, manualInternalProposal.id);
    assert.equal(
      result.data?.proposals.filter(
        (proposal) => proposal.id === manualInternalProposal.id
      ).length,
      1
    );
    assert.deepEqual(requests, [
      "http://localhost/api/v1/workspaces/workspace-123/actions/proposals?limit=100",
      "http://localhost/api/v1/workspaces/workspace-123/actions/proposals/proposal-5"
    ]);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("exact proposal merge replaces a duplicate without exceeding the bounded list", () => {
  const merged = mergeExactActionProposal(
    {
      ...sampleList,
      proposals: [manualInternalProposal, ...sampleList.proposals],
      count: 4
    },
    { ...manualInternalProposal, title: "Fresh exact mission" }
  );

  assert.equal(merged.proposals[0]?.title, "Fresh exact mission");
  assert.equal(
    merged.proposals.filter((proposal) => proposal.id === manualInternalProposal.id)
      .length,
    1
  );
  assert.equal(merged.count, merged.proposals.length);
});

test("linked proposal 404 and forbidden responses never fall back to another mission", async () => {
  const originalFetch = globalThis.fetch;

  try {
    for (const failure of [
      {
        expectedStatus: "not_found" as const,
        httpStatus: 404,
        title: M.actionsPanel.linkedProposalNotFoundTitle
      },
      {
        expectedStatus: "forbidden" as const,
        httpStatus: 403,
        title: M.actionsPanel.linkedProposalForbiddenTitle
      }
    ]) {
      globalThis.fetch = (async (input) => {
        const request = String(input);
        if (request.endsWith("/actions/proposals?limit=100")) {
          return new Response(JSON.stringify(sampleList), {
            headers: { "Content-Type": "application/json" },
            status: 200
          });
        }
        return new Response(JSON.stringify({ detail: "private backend detail" }), {
          headers: { "Content-Type": "application/json" },
          status: failure.httpStatus
        });
      }) as typeof fetch;

      const result = await loadActionProposalPanelData(
        "workspace-123",
        manualInternalProposal.id
      );
      assert.equal(result.status, failure.expectedStatus);
      assert.equal(result.data, null);
      const html = renderPanel({
        data: sampleList,
        error: result.error,
        status: result.status
      });
      assert.ok(html.includes(failure.title));
      assert.doesNotMatch(html, /private backend detail/);
      assert.doesNotMatch(html, /class="mission-console"/);
      assert.doesNotMatch(html, /Create follow-up GitHub issue/);
    }
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("requests the full proposed queue from the server", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (input) => {
    assert.equal(
      String(input),
      "http://localhost/api/v1/workspaces/workspace-123/actions/proposals?limit=100&status=proposed"
    );
    return new Response(JSON.stringify(sampleList), {
      headers: { "Content-Type": "application/json" },
      status: 200
    });
  }) as typeof fetch;

  try {
    await fetchActionProposals(
      "workspace-123",
      { limit: 100, status: "proposed" },
      {}
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("creates local action proposal without external execution", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (input, init) => {
    assert.equal(
      String(input),
      "http://localhost/api/v1/workspaces/workspace-123/actions/proposals"
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
      {}
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
      assert.equal(init?.body, JSON.stringify({
        expected_snapshot_id: null,
        idempotency_key: "reject-key",
        proposal_version: proposedProposal.proposal_version,
        reason: "Not now"
      }));
      return new Response(
        JSON.stringify({ ...decisionResponse, proposal: rejectedProposal }),
        {
          headers: { "Content-Type": "application/json" },
          status: 200
        }
      );
    }
    return new Response(JSON.stringify(decisionResponse), {
      headers: { "Content-Type": "application/json" },
      status: 200
    });
  }) as typeof fetch;

  try {
    const approved = await approveActionProposal("workspace-123", "proposal-1", {
      idempotency_key: "approve-key",
      proposal_version: proposedProposal.proposal_version
    });
    const rejected = await rejectActionProposal(
      "workspace-123",
      "proposal-1",
      {
        idempotency_key: "reject-key",
        proposal_version: proposedProposal.proposal_version,
        reason: "Not now"
      },
      {}
    );

    assert.equal(approved.proposal.status, "approved");
    assert.equal(approved.execution_started, false);
    assert.equal(rejected.proposal.status, "rejected");
    assert.deepEqual(calls, [
      "POST http://localhost/api/v1/workspaces/workspace-123/actions/proposals/proposal-1/approve",
      "POST http://localhost/api/v1/workspaces/workspace-123/actions/proposals/proposal-1/reject"
    ]);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("bulk approves and rejects locally through backend bulk endpoints", async () => {
  const originalFetch = globalThis.fetch;
  const calls: string[] = [];
  globalThis.fetch = (async (input, init) => {
    calls.push(`${init?.method ?? "GET"} ${String(input)}`);
    if (String(input).endsWith("/bulk-reject")) {
      assert.equal(
        init?.body,
        JSON.stringify({
          proposal_ids: ["proposal-4"],
          reason: "Not now"
        })
      );
      return new Response(
        JSON.stringify({
          execution_started: false,
          failed_count: 0,
          failures: [],
          is_live: false,
          proposals: [rejectedProposal],
          succeeded_count: 1,
          warnings: ["Action proposal API is local-only and does not execute provider actions."]
        }),
        {
          headers: { "Content-Type": "application/json" },
          status: 200
        }
      );
    }
    assert.equal(
      init?.body,
      JSON.stringify({
        proposal_ids: ["proposal-1", "proposal-4"]
      })
    );
    return new Response(
      JSON.stringify({
        execution_started: false,
        failed_count: 1,
        failures: [
          {
            detail: "action proposal is not in proposed status",
            proposal_id: "proposal-9",
            status_code: 409
          }
        ],
        is_live: false,
        proposals: [approvedProposal],
        succeeded_count: 1,
        warnings: ["Action proposal API is local-only and does not execute provider actions."]
      }),
      {
        headers: { "Content-Type": "application/json" },
        status: 200
      }
    );
  }) as typeof fetch;

  try {
    const approved = await bulkApproveActionProposals(
      "workspace-123",
      { proposal_ids: ["proposal-1", "proposal-4"] },
      {}
    );
    const rejected = await bulkRejectActionProposals(
      "workspace-123",
      { proposal_ids: ["proposal-4"], reason: "Not now" },
      {}
    );

    assert.equal(approved.succeeded_count, 1);
    assert.equal(approved.failed_count, 1);
    assert.equal(approved.failures[0]?.status_code, 409);
    assert.equal(approved.execution_started, false);
    assert.equal(rejected.succeeded_count, 1);
    assert.deepEqual(calls, [
      "POST http://localhost/api/v1/workspaces/workspace-123/actions/proposals/bulk-approve",
      "POST http://localhost/api/v1/workspaces/workspace-123/actions/proposals/bulk-reject"
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
        idempotency_key: "approve-key",
        proposal_version: proposedProposal.proposal_version
      }),
      /action proposal is not in proposed status/
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("renders loading, missing, empty, unsupported, and error states", () => {
  assert.ok(renderPanel({ data: null, status: "loading" }).includes(M.actionsPanel.loading));
  assert.ok(renderPanel({ data: null, status: "missing" }).includes(M.common.noWorkspaceTitle));
  const emptyHtml = renderPanel({ data: emptyList, status: "empty" });
  assert.ok(emptyHtml.includes("Добавьте первое решение"));
  assert.match(emptyHtml, /id="add-mission" open=""/);
  assert.ok(emptyHtml.includes("Создать первое решение"));
  assert.ok(
    renderPanel({ data: null, status: "unsupported" }).includes(M.actionsPanel.unsupportedTitle)
  );
  const errorHtml = renderPanel({
    data: null,
    error: "transition failed",
    onRetry: () => undefined,
    status: "error"
  });
  assert.ok(errorHtml.includes(M.actionsPanel.unavailableTitle));
  assert.match(errorHtml, /transition failed/);
  assert.ok(errorHtml.includes(M.common.retry));
});

test("renders one active mission console, queue statuses, evidence, and local-only boundary", () => {
  const html = renderPanel({
    onApprove: () => undefined,
    onReject: () => undefined,
    onSelectEvidence: () => undefined
  });
  assert.ok(html.includes("Решения"));
  assert.ok(html.includes("Решения компании"));
  assert.equal((html.match(/class="mission-console"/g) ?? []).length, 1);
  assert.equal((html.match(/aria-controls="mission-console"/g) ?? []).length, 3);
  assert.match(html, /aria-pressed="true"/);
  assert.match(html, /Ничего не отправится само/);
  assert.match(html, /Create follow-up GitHub issue/);
  assert.match(html, /qtwin-io\/founderos-api/);
  assert.match(html, /Follow up on FounderOS signal/);
  assert.ok(html.includes(M.actionsPanel.approve));
  assert.ok(html.includes(M.actionsPanel.reject));
  assert.ok(html.includes("Ждёт решения"));
  assert.ok(html.includes("Принято"));
  assert.ok(html.includes("Отклонено"));
  assert.ok(html.includes("История и технические детали"));
  assert.match(html, /decision-room-evidence/);
  assert.ok(html.includes("Почему FounderOS это предлагает"));
  assert.match(html, /Источник: qtwin-io\/founderos-api#issue\/42/);
  assert.equal((html.match(new RegExp(`>${M.actionsPanel.approve}<`, "g")) ?? []).length, 1);
  assert.equal((html.match(new RegExp(`>${M.actionsPanel.reject}<`, "g")) ?? []).length, 1);
  const rejectedHtml = renderPanel({ activeProposalId: rejectedProposal.id });
  assert.ok(rejectedHtml.includes(M.actionsPanel.noEvidenceRefs));
  assert.doesNotMatch(html, /sent to GitHub/i);
  assert.doesNotMatch(html, /created GitHub issue/i);
  assert.doesNotMatch(html, /source_events/);
});

test("summarizes action review readiness without starting external execution", () => {
  const summary = summarizeActionReviewReadiness([
    proposedProposal,
    approvedProposal,
    rejectedProposal,
    briefingProposal,
    manualInternalProposal,
    executedProposal
  ]);

  assert.deepEqual(summary, {
    externalResultReported: 1,
    localOnly: 2,
    missingEvidence: 1,
    pendingDecision: 3,
    previewReady: 1
  });
});

test("renders action review readiness next steps from the loaded local list", () => {
  const html = renderPanel({
    data: {
      ...groupedList,
      count: 6,
      proposals: [...groupedList.proposals, executedProposal]
    },
    statusFilter: "all"
  });

  assert.ok(html.includes(M.actionsPanel.readinessTitle));
  assert.ok(html.includes(M.actionsPanel.readinessDescription));
  assert.ok(html.includes(M.actionsPanel.readinessPendingTitle));
  assert.ok(html.includes(M.actionsPanel.readinessPreviewTitle));
  assert.ok(html.includes(M.actionsPanel.readinessLocalOnlyTitle));
  assert.ok(html.includes(M.actionsPanel.readinessMissingEvidenceTitle));
  assert.ok(html.includes(M.actionsPanel.readinessExternalResultTitle));
  assert.ok(html.includes(T.actionsReadinessNextStep(3, 1, 1, 1)));
  assert.ok(html.includes(M.actionsPanel.readinessBoundary));
  assert.doesNotMatch(html, /execute started by summary/i);
  assert.doesNotMatch(html, /provider call started/i);
  assert.doesNotMatch(html, /created GitHub issue/i);
});

test("filters loaded local proposals without changing provider state", () => {
  const proposedHtml = renderPanel({
    onStatusFilterChange: () => undefined,
    statusFilter: "proposed"
  });
  assert.ok(proposedHtml.includes(M.actionsPanel.filterTitle));
  assert.ok(proposedHtml.includes(`${M.actionsPanel.filterProposed} · 1`));
  assert.ok(proposedHtml.includes(`${M.actionsPanel.filterAll} · 3`));
  assert.match(proposedHtml, /Create follow-up GitHub issue/);
  assert.doesNotMatch(proposedHtml, /Approved local proposal/);
  assert.doesNotMatch(proposedHtml, /Rejected local proposal/);
  assert.ok(proposedHtml.includes(M.actionsPanel.filterDescription));
  assert.match(proposedHtml, /<dt>Приняты человеком<\/dt><dd>1<\/dd>/);
  assert.match(proposedHtml, /role="group"/);
  assert.match(proposedHtml, /aria-pressed="true"/);
  assert.doesNotMatch(proposedHtml, /role="tab(list)?"/);
  assert.doesNotMatch(proposedHtml, /provider call started/i);

  const rejectedHtml = renderPanel({ statusFilter: "rejected" });
  assert.match(rejectedHtml, /Rejected local proposal/);
  assert.doesNotMatch(rejectedHtml, /Create follow-up GitHub issue/);
});

test("filters loaded proposals by local origin on top of status", () => {
  const proposedHtml = renderPanel({
    data: groupedList,
    onOriginFilterChange: () => undefined,
    statusFilter: "proposed"
  });
  assert.ok(proposedHtml.includes(M.actionsPanel.originFilterTitle));
  assert.ok(proposedHtml.includes(M.actionsPanel.originFilterDescription));
  assert.ok(proposedHtml.includes(`${M.actionsPanel.originFilterAll} · 3`));
  assert.ok(proposedHtml.includes(`${M.actionsPanel.originFilterBriefing} · 1`));
  assert.ok(proposedHtml.includes(`${M.actionsPanel.originFilterGithub} · 1`));
  assert.ok(proposedHtml.includes(`${M.actionsPanel.originFilterInternal} · 1`));
  assert.doesNotMatch(proposedHtml, /provider call started/i);

  const briefingHtml = renderPanel({
    data: groupedList,
    originFilter: "briefing",
    statusFilter: "proposed"
  });
  assert.match(briefingHtml, /<span class="mission-queue-count">1<\/span>/);
  assert.match(briefingHtml, /<span class="badge badge-origin">Сводка<\/span>/);
  assert.match(briefingHtml, /Review synced GitHub work before approving actions/);
  assert.doesNotMatch(briefingHtml, /Create follow-up GitHub issue/);
  assert.doesNotMatch(briefingHtml, /Manual internal follow-up/);
});

test("keeps audit-derived missions flat while preserving origin and audit-source truth", () => {
  const auditList: ActionProposalListResponse = {
    ...sampleList,
    proposals: [deterministicAuditProposal, auditProposal],
    count: 2
  };
  const auditHtml = renderPanel({
    data: auditList,
    originFilter: "audit",
    statusFilter: "proposed"
  });
  assert.ok(auditHtml.includes(`${M.actionsPanel.originFilterAudit} · 2`));
  assert.equal((auditHtml.match(/>Аудит репо<\/span>/g) ?? []).length, 2);
  assert.ok(auditHtml.includes(M.actionsPanel.auditSourceFilterTitle));
  assert.ok(auditHtml.includes(`${M.actionsPanel.auditSourceFilterAll} · 2`));
  assert.ok(
    auditHtml.includes(`${M.actionsPanel.auditSourceFilterDeterministic} · 1`)
  );
  assert.ok(auditHtml.includes(`${M.actionsPanel.auditSourceFilterImported} · 1`));
  assert.ok(auditHtml.includes("qtwin-io/local-service"));
  assert.ok(auditHtml.includes("qtwin-io/base-collector"));
  assert.ok(auditHtml.includes(M.actionsPanel.payloadAuditSource));
  assert.ok(auditHtml.includes(M.actionsPanel.auditSourceDeterministic));
  const importedHtml = renderPanel({
    activeProposalId: auditProposal.id,
    data: auditList,
    originFilter: "audit",
    statusFilter: "proposed"
  });
  assert.ok(importedHtml.includes(M.actionsPanel.auditSourceImported));
  assert.ok(importedHtml.includes("Add CI before private beta."));
  assert.ok(importedHtml.includes("ci_not_detected, tests_not_detected"));
  assert.doesNotMatch(auditHtml, /provider call started/i);
});

test("filters audit-origin proposals by deterministic or imported source locally", () => {
  const auditList: ActionProposalListResponse = {
    ...sampleList,
    proposals: [deterministicAuditProposal, auditProposal, briefingProposal],
    count: 3
  };
  const importedHtml = renderPanel({
    auditSourceFilter: "imported",
    data: auditList,
    onAuditSourceFilterChange: () => undefined,
    originFilter: "audit",
    statusFilter: "proposed"
  });

  assert.match(importedHtml, /<span class="mission-queue-count">1<\/span>/);
  assert.match(importedHtml, />Аудит репо<\/span>/);
  assert.ok(importedHtml.includes("qtwin-io/base-collector"));
  assert.doesNotMatch(importedHtml, /qtwin-io\/local-service/);
  assert.doesNotMatch(importedHtml, /Review synced GitHub work/);
  assert.ok(importedHtml.includes(M.actionsPanel.auditSourceImported));

  const deterministicHtml = renderPanel({
    auditSourceFilter: "deterministic",
    data: auditList,
    originFilter: "audit",
    statusFilter: "proposed"
  });
  assert.ok(deterministicHtml.includes("qtwin-io/local-service"));
  assert.doesNotMatch(deterministicHtml, /qtwin-io\/base-collector/);
  assert.ok(deterministicHtml.includes(M.actionsPanel.auditSourceDeterministic));
  assert.doesNotMatch(deterministicHtml, /provider call started/i);
});

test("shows empty state for origin and status intersections with no local proposals", () => {
  const html = renderPanel({
    data: groupedList,
    originFilter: "briefing",
    statusFilter: "rejected"
  });
  assert.ok(html.includes("В этом фокусе решений нет"));
  assert.ok(html.includes("Измените фильтры"));
  assert.doesNotMatch(html, /Создать первое решение/);
  assert.ok(html.includes(`${M.actionsPanel.originFilterAll} · 1`));
  assert.ok(html.includes(`${M.actionsPanel.originFilterBriefing} · 0`));
  assert.doesNotMatch(html, /Review synced GitHub work before approving actions/);
  assert.doesNotMatch(html, /Create follow-up GitHub issue/);
});

test("origin filtering updates the active mission evidence without provider calls", () => {
  const internalHtml = renderPanel({
    data: groupedList,
    originFilter: "internal",
    statusFilter: "proposed"
  });
  assert.match(internalHtml, /<span class="mission-queue-count">1<\/span>/);
  assert.match(internalHtml, />Внутри<\/span>/);
  assert.match(internalHtml, /Manual internal follow-up/);
  assert.match(internalHtml, /manual-note-1/);
  assert.ok(internalHtml.includes("Показано первое основание выбранного решения."));
  assert.doesNotMatch(internalHtml, /Review synced GitHub work before approving actions/);
  assert.doesNotMatch(internalHtml, /href="https:\/\/github.com\/qtwin-io\/founderos-api/);
});

test("renders bulk local review controls for visible proposed proposals only", () => {
  const html = renderPanel({
    data: groupedList,
    onBulkApprove: () => undefined,
    onBulkReject: () => undefined,
    onClearSelectedProposals: () => undefined,
    onSelectVisibleProposed: () => undefined,
    onToggleProposalSelection: () => undefined,
    statusFilter: "all"
  });
  assert.doesNotMatch(html, /decision-room-bulk-bar/);
  assert.ok(html.includes(M.actionsPanel.bulkSelectVisible));
  assert.doesNotMatch(html, new RegExp(M.actionsPanel.bulkApproveSelected));
  assert.doesNotMatch(html, new RegExp(M.actionsPanel.bulkRejectSelected));
  assert.doesNotMatch(html, new RegExp(T.actionsBulkSelection(0, 3)));
  assert.equal((html.match(/type="checkbox"/g) ?? []).length, 0);
  assert.doesNotMatch(html, /missions-bulk-confirm/);
  assert.doesNotMatch(html, /external write performed/i);
  assert.doesNotMatch(html, /created GitHub issue/i);
});

test("bulk local review controls show selected counts and pending labels", () => {
  const html = renderPanel({
    data: groupedList,
    pendingMutation: "bulk-approve",
    selectedProposalIds: ["proposal-1", "proposal-4"],
    statusFilter: "proposed"
  });
  assert.ok(html.includes(T.actionsBulkSelection(2, 3)));
  assert.match(html, /decision-room-bulk-bar/);
  assert.ok(html.includes(M.actionsPanel.bulkApproving));
  assert.ok(html.includes(M.actionsPanel.bulkRejectSelected));
  assert.match(html, /checked=""/);
});

test("bulk origin/status intersections select only currently visible proposed proposals", () => {
  const html = renderPanel({
    data: groupedList,
    originFilter: "briefing",
    selectedProposalIds: ["proposal-4"],
    statusFilter: "proposed"
  });
  assert.ok(html.includes(T.actionsBulkSelection(1, 1)));
  assert.equal((html.match(/type="checkbox"/g) ?? []).length, 1);
  assert.match(html, /Review synced GitHub work before approving actions/);
  assert.doesNotMatch(html, /Manual internal follow-up/);
  assert.doesNotMatch(html, /Approved local proposal/);
});

test("summarizeBulkResponse partitions backend bulk results and keeps first failure", () => {
  const outcome = summarizeBulkResponse({
    execution_started: false,
    failed_count: 1,
    failures: [
      {
        detail: "action proposal is not in proposed status",
        proposal_id: "proposal-9",
        status_code: 409
      }
    ],
    is_live: false,
    proposals: [
      { ...approvedProposal, id: "proposal-1" },
      { ...approvedProposal, id: "proposal-4" }
    ],
    succeeded_count: 2,
    warnings: []
  });

  assert.deepEqual(outcome.succeededIds, ["proposal-1", "proposal-4"]);
  assert.equal(outcome.succeeded.length, 2);
  assert.equal(outcome.failed.length, 1);
  assert.equal(outcome.failed[0]?.id, "proposal-9");
  assert.equal(outcome.firstFailureMessage, "action proposal is not in proposed status");
});

test("summarizeBulkResponse reports no failure message when all succeed", () => {
  const outcome = summarizeBulkResponse({
    execution_started: false,
    failed_count: 0,
    failures: [],
    is_live: false,
    proposals: [{ ...approvedProposal, id: "proposal-1" }],
    succeeded_count: 1,
    warnings: []
  });
  assert.equal(outcome.failed.length, 0);
  assert.equal(outcome.firstFailureMessage, null);
  assert.deepEqual(outcome.succeededIds, ["proposal-1"]);
});

test("renders inline partial bulk failure without hiding the loaded list", () => {
  const html = renderPanel({
    data: groupedList,
    error: T.actionsBulkApprovePartial(2, 1),
    status: "ready",
    successMessage: T.actionsBulkApprovePartial(2, 1)
  });
  // Inline alert is shown while the list stays visible (status stays "ready").
  assert.match(html, /role="alert"/);
  assert.match(html, /Не удалось: 1/);
  assert.match(html, /Успешные локальные изменения сохранены/);
  assert.match(html, /Review synced GitHub work before approving actions/);
  assert.doesNotMatch(html, new RegExp(M.actionsPanel.unavailableTitle));
  assert.doesNotMatch(html, /external write performed/i);
});

test("defaults evidence drawer to first visible proposal evidence", () => {
  const proposedHtml = renderPanel({ statusFilter: "proposed" });
  assert.ok(proposedHtml.includes(M.evidence.title));
  assert.ok(proposedHtml.includes(M.evidence.source));
  assert.match(proposedHtml, /qtwin-io\/founderos-api#issue\/42/);
  assert.ok(proposedHtml.includes(M.common.openSource));
  assert.ok(proposedHtml.includes("Показано первое основание выбранного решения."));
  // Default evidence is contextual and not an explicit selection, so no close button.
  assert.doesNotMatch(proposedHtml, new RegExp(`>${M.common.close}<`));

  const rejectedHtml = renderPanel({ statusFilter: "rejected" });
  assert.ok(rejectedHtml.includes(M.evidence.placeholder));
  assert.doesNotMatch(rejectedHtml, /href="https:\/\/github.com\/qtwin-io\/founderos-api\/issues\/42"/);
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
  assert.ok(html.includes(M.actionCreate.typeLabel));
  assert.ok(html.includes("Добавить решение"));
  assert.ok(html.includes(M.actionCreate.typeGithubIssue));
  assert.ok(html.includes(M.actionCreate.submitting));
  assert.ok(html.includes(M.actionCreate.note));
});

test("puts the active mission workspace before creation and safety backstage", () => {
  const html = renderPanel({ data: groupedList, statusFilter: "proposed" });
  const queueIndex = html.indexOf("missions-workspace");
  const consoleIndex = html.indexOf("mission-console");
  const createIndex = html.indexOf("decision-room-create");
  const readinessIndex = html.indexOf("decision-room-readiness");

  assert.ok(queueIndex >= 0);
  assert.ok(consoleIndex > queueIndex);
  assert.ok(createIndex > queueIndex);
  assert.ok(readinessIndex > createIndex);
  assert.match(html, /<details class="decision-room-disclosure decision-room-filters">/);
  assert.match(
    html,
    /<details class="decision-room-disclosure decision-room-create" id="add-mission">/
  );
  assert.match(html, /<details class="decision-room-disclosure decision-room-readiness">/);
});

test("keeps visible proposal status labels in Russian", () => {
  const html = renderPanel({ statusFilter: "all" });

  assert.match(
    html,
    /decision-room-status--pending[^>]*>Ждёт решения<\/span>/
  );
  assert.match(
    html,
    /decision-room-status--approved[^>]*>Принято<\/span>/
  );
  assert.match(
    html,
    /decision-room-status--rejected[^>]*>Отклонено<\/span>/
  );
  assert.doesNotMatch(html, /<span class="badge">proposed<\/span>/);
  assert.doesNotMatch(html, /<dd>approved<\/dd>/);
  assert.doesNotMatch(html, /<dd>rejected<\/dd>/);
});

test("guides an approved filter to the visible preview step", () => {
  const html = renderPanel({ statusFilter: "approved" });

  assert.ok(html.includes("Approved local proposal"));
  assert.ok(html.includes(M.actionExecution.preview));
  assert.match(html, /<li class="is-complete">/);
  assert.match(html, /<li aria-current="step" class=" is-current">/);
  assert.match(html, /decision-room-next-step/);
  assert.ok(
    html.indexOf("decision-room-next-step") <
      html.indexOf("История и технические детали")
  );
  assert.doesNotMatch(html, /решение ждёт проверки/);
});

test("keeps an approved internal todo local instead of promoting external preview", () => {
  const html = renderPanel({
    data: {
      count: 1,
      is_live: false,
      proposals: [approvedInternalProposal],
      warnings: []
    },
    statusFilter: "approved"
  });

  assert.ok(html.includes("Approved internal follow-up"));
  assert.match(html, /decision-room-next-step--local/);
  assert.ok(html.includes("Это действие остаётся внутри FounderOS"));
});

test("renders a failed execution as an explicit attention state", () => {
  const html = renderPanel({
    data: {
      count: 1,
      is_live: false,
      proposals: [failedProposal],
      warnings: []
    },
    statusFilter: "all"
  });

  assert.ok(html.includes("1 выполнение"));
  assert.ok(html.includes("требует внимания"));
  assert.match(html, /decision-room-status--failed[^>]*>Ошибка выполнения/);
  assert.doesNotMatch(html, /Неизвестный статус/);
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

  assert.ok(html.includes(M.evidence.title));
  assert.match(html, /github_issue/);
  assert.match(html, /qtwin-io\/founderos-api#issue\/42/);
  assert.ok(html.includes(M.common.openSource));
  assert.ok(html.includes(M.evidence.noSnippet));
  assert.doesNotMatch(html, /provider_response/);
  assert.doesNotMatch(html, /access_token/);
});

test("renders a flat queue with compact origin badges", () => {
  const html = renderPanel({ data: groupedList, statusFilter: "all" });
  assert.equal((html.match(/>Сводка<\/span>/g) ?? []).length, 1);
  assert.equal((html.match(/>GitHub<\/span>/g) ?? []).length, 3);
  assert.equal((html.match(/>Внутри<\/span>/g) ?? []).length, 1);
  assert.doesNotMatch(html, /proposal-group-header/);
  assert.match(html, /Review synced GitHub work before approving actions/);
});

test("omits non-matching origin badges from the active filter", () => {
  const html = renderPanel({ data: groupedList, statusFilter: "rejected" });
  assert.match(html, />GitHub<\/span>/);
  assert.doesNotMatch(html, />Сводка<\/span>/);
  assert.doesNotMatch(html, />Внутри<\/span>/);
});

test("renders briefing internal_todo payload metadata", () => {
  const html = renderPanel({ data: groupedList, statusFilter: "proposed" });
  assert.ok(html.includes(M.actionsPanel.payloadBriefingItem));
  assert.match(html, /repo-coverage/);
  assert.ok(html.includes(M.actionsPanel.payloadCategory));
  assert.ok(html.includes(M.actionsPanel.payloadSeverity));
  assert.ok(html.includes(M.actionsPanel.payloadNextStep));
  assert.ok(html.includes(M.actionsPanel.payloadRelatedEntities));
  assert.match(html, /qtwin-io\/founderos-api, qtwin-io\/founderos-web/);
  // Bridge marker keys should not leak as raw payload dumps.
  assert.doesNotMatch(html, /"source":\s*"briefing_item"/);
});

test("evidence drawer shows contextual default hint and evidence count", () => {
  const html = renderPanel({ data: groupedList, statusFilter: "proposed" });
  assert.ok(html.includes("Показано первое основание выбранного решения."));
  assert.ok(html.includes(M.evidence.countLabel));
  // Briefing proposal is first in grouped order and carries two evidence refs.
  assert.match(html, /qtwin-io\/founderos-api/);
  assert.doesNotMatch(html, new RegExp(`>${M.common.close}<`));
});

test("selected mission drives the single console and its evidence context", () => {
  const html = renderPanel({
    activeProposalId: manualInternalProposal.id,
    data: groupedList,
    statusFilter: "all"
  });

  assert.match(
    html,
    /aria-pressed="true" class="mission-queue-open"[^>]*>[\s\S]*?Manual internal follow-up/
  );
  assert.match(
    html,
    /id="mission-console-title" tabindex="-1">Manual internal follow-up<\/h2>/
  );
  assert.match(html, /manual-note-1/);
  assert.doesNotMatch(
    html,
    /href="https:\/\/github.com\/qtwin-io\/founderos-api\/issues\/42"/
  );
  assert.equal((html.match(/class="mission-console"/g) ?? []).length, 1);
});

test("keeps an exact linked mission visible outside the current filters", () => {
  const html = renderPanel({
    activeProposalId: approvedProposal.id,
    data: sampleList,
    originFilter: "internal",
    statusFilter: "proposed"
  });

  assert.ok(html.includes(M.actionsPanel.linkedProposalOutsideFilter));
  assert.match(
    html,
    /id="mission-console-title" tabindex="-1">Approved local proposal<\/h2>/
  );
  assert.equal((html.match(/class="mission-console"/g) ?? []).length, 1);
});

test("evidence drawer marks manual selection without a misleading close affordance", () => {
  const manualEvidence = proposedProposal.evidence_refs[0] ?? null;
  const html = renderPanel({
    data: groupedList,
    activeProposalId: proposedProposal.id,
    onCloseEvidence: () => undefined,
    selectedEvidence: manualEvidence,
    selectedEvidenceCount: 1,
    selectedEvidenceProposalId: proposedProposal.id,
    selectedEvidenceTitle: "Create follow-up GitHub issue",
    statusFilter: "all"
  });
  assert.ok(html.includes("Показано выбранное основание этого решения."));
  assert.doesNotMatch(html, new RegExp(`>${M.common.close}<`));
  assert.equal((html.match(/class="mission-console"/g) ?? []).length, 1);
});

test("manual evidence never crosses into another active mission", () => {
  const staleEvidence = proposedProposal.evidence_refs[0] ?? null;
  const html = renderPanel({
    activeProposalId: manualInternalProposal.id,
    data: groupedList,
    selectedEvidence: staleEvidence,
    selectedEvidenceCount: 1,
    selectedEvidenceProposalId: proposedProposal.id,
    selectedEvidenceTitle: proposedProposal.title,
    statusFilter: "all"
  });

  assert.match(html, /manual-note-1/);
  assert.doesNotMatch(html, /Показано выбранное основание этого решения/);
  assert.doesNotMatch(
    html,
    /href="https:\/\/github.com\/qtwin-io\/founderos-api\/issues\/42"/
  );
});

test("busy external control locks mission switching and local filters", () => {
  const html = renderPanel({
    activeProposalId: approvedProposal.id,
    executionBusyProposalId: approvedProposal.id,
    statusFilter: "all"
  });

  assert.match(
    html,
    /class="mission-queue-open" disabled="" id="mission-queue-proposal-2"/
  );
  assert.match(html, /class="segment active" disabled=""/);
});

test("a local mutation locks every other mission and execution control", () => {
  const html = renderPanel({
    activeProposalId: approvedProposal.id,
    pendingMutation: "create",
    statusFilter: "all"
  });

  assert.match(html, /Завершаем защищённую операцию/);
  assert.match(
    html,
    /class="mission-queue-open" disabled="" id="mission-queue-proposal-1"/
  );
  assert.match(html, /class="segment active" disabled=""/);
  assert.match(html, /<select disabled="" id="proposal-kind"/);
  assert.match(
    html,
    /<button class="button secondary" disabled="" type="button">Проверить внешний шаг<\/button>/
  );
});

test("only an execution completion may schedule refresh while the operation lock is held", () => {
  assert.equal(canScheduleProposalRefresh("user", true), false);
  assert.equal(canScheduleProposalRefresh("user", false), true);
  assert.equal(canScheduleProposalRefresh("execution_complete", true), true);
});

test("mutation errors stay next to their proposal or creation form", () => {
  const proposalHtml = renderPanel({
    activeProposalId: proposedProposal.id,
    mutationError: {
      message: "decision failed",
      scope: `proposal:${proposedProposal.id}`
    }
  });
  const decisionIndex = proposalHtml.indexOf("mission-decision");
  const proposalErrorIndex = proposalHtml.indexOf("decision failed");
  assert.ok(proposalErrorIndex > decisionIndex);

  const createHtml = renderPanel({
    mutationError: { message: "create failed", scope: "create" }
  });
  const createIndex = createHtml.indexOf("decision-room-create");
  const createErrorIndex = createHtml.indexOf("create failed");
  assert.ok(createErrorIndex > createIndex);
});
