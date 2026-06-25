import assert from "node:assert/strict";
import test from "node:test";

import { renderToStaticMarkup } from "react-dom/server";

import {
  buildWorkspaceActionProposalAuditPath,
  buildWorkspaceActionProposalExecutePath,
  buildWorkspaceActionProposalExecutionPreviewPath,
  executeActionProposal,
  fetchActionProposalAudit,
  fetchActionExecutionPreview
} from "../lib/api";
import type {
  ActionExecutionAuditEvent,
  ActionExecutionPreviewResponse,
  ActionExecutionReceipt,
  ActionExecutionResponse,
  ActionProposal
} from "../lib/types";
import { ActionExecutionControlsView } from "../components/ActionExecutionControls";

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
  evidence_refs: [],
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
  warnings: []
};

const approvedProposal: ActionProposal = {
  ...proposedProposal,
  approved_at: "2026-06-25T01:05:00+06:00",
  approved_by_user_id: "user-2",
  evidence_refs: [
    {
      kind: "repository",
      ref: "qtwin-io/founderos-api",
      source: "github_repository_read_api",
      url: null
    }
  ],
  id: "proposal-2",
  status: "approved",
  title: "Approved local proposal"
};

function auditEvent(
  overrides: Partial<ActionExecutionAuditEvent> = {}
): ActionExecutionAuditEvent {
  return {
    action: "create_github_issue",
    actor: "system",
    confirmation_received: false,
    created_at: "2026-06-25T01:06:00+06:00",
    error_code: null,
    error_message: null,
    event: "execution_preview_generated",
    event_metadata: {
      evidence_refs_count: 1,
      preview_hash: "preview-hash"
    },
    event_type: "execution_preview_generated",
    external_execution_enabled: false,
    external_result_id: null,
    external_result_url: null,
    id: "event-1",
    message:
      "Preview ready. External execution is disabled in this environment. No external write occurred.",
    provider: "github",
    status: "recorded",
    ...overrides
  };
}

const emptyReceipt: ActionExecutionReceipt = {
  action: "create_github_issue",
  confirmation_received: false,
  created_at: null,
  error_code: null,
  error_message: null,
  external_execution_enabled: false,
  external_result_id: null,
  external_result_url: null,
  external_write_performed: false,
  idempotency_key: null,
  provider: "github",
  provider_result: "none",
  status: null,
  updated_at: null
};

const successfulReceipt: ActionExecutionReceipt = {
  action: "create_github_issue",
  confirmation_received: true,
  created_at: "2026-06-25T01:06:00+06:00",
  error_code: null,
  error_message: null,
  external_execution_enabled: true,
  external_result_id: "42",
  external_result_url: "https://github.com/qtwin-io/founderos-api/issues/42",
  external_write_performed: true,
  idempotency_key: "issue-action-test",
  provider: "github",
  provider_result: "succeeded",
  status: "succeeded",
  updated_at: "2026-06-25T01:06:00+06:00"
};

const disabledPreview: ActionExecutionPreviewResponse = {
  audit: [auditEvent()],
  capabilities: {
    dry_run: true,
    external_execution: false,
    live_provider_write: false,
    local_approval: true,
    requires_confirmation: true
  },
  message: "Preview ready. External execution is disabled in this environment.",
  mode: "external_disabled",
  preview: {
    action: "create_github_issue",
    assignees: ["founder"],
    body: "Created through approved action execution.",
    evidence_refs: approvedProposal.evidence_refs,
    labels: ["founderos"],
    provider: "github",
    repository: "qtwin-io/founderos-api",
    title: "FounderOS follow-up"
  },
  proposal_id: "proposal-2",
  status: "preview_ready",
  warnings: ["Execution preview is dry-run only and does not call GitHub."],
  workspace_id: "workspace-123"
};

const enabledPreview: ActionExecutionPreviewResponse = {
  ...disabledPreview,
  capabilities: {
    ...disabledPreview.capabilities,
    external_execution: true,
    live_provider_write: true
  },
  message: "Preview ready. Live GitHub write requires explicit confirmation.",
  mode: "dry_run"
};

function renderControls(
  props: Partial<Parameters<typeof ActionExecutionControlsView>[0]> = {}
): string {
  return renderToStaticMarkup(
    <ActionExecutionControlsView
      auditEvents={props.auditEvents ?? []}
      confirmationChecked={props.confirmationChecked ?? false}
      connectionId={props.connectionId ?? ""}
      error={props.error ?? null}
      executeResult={props.executeResult ?? null}
      isExecutePending={props.isExecutePending ?? false}
      isPreviewPending={props.isPreviewPending ?? false}
      onConfirmationChange={props.onConfirmationChange}
      onConnectionIdChange={props.onConnectionIdChange}
      onExecute={props.onExecute}
      onPreview={props.onPreview}
      preview={props.preview ?? null}
      proposal={props.proposal ?? approvedProposal}
      receipt={props.receipt ?? null}
      successMessage={props.successMessage ?? null}
    />
  );
}

test("builds action execution preview, audit, and execute URLs", () => {
  assert.equal(
    buildWorkspaceActionProposalExecutionPreviewPath("workspace-123", "proposal-2"),
    "/api/v1/workspaces/workspace-123/actions/proposals/proposal-2/execution-preview"
  );
  assert.equal(
    buildWorkspaceActionProposalAuditPath("workspace-123", "proposal-2"),
    "/api/v1/workspaces/workspace-123/actions/proposals/proposal-2/audit"
  );
  assert.equal(
    buildWorkspaceActionProposalExecutePath("workspace-123", "proposal-2"),
    "/api/v1/workspaces/workspace-123/actions/proposals/proposal-2/execute"
  );
});

test("fetches execution preview without posting a live write", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (input, init) => {
    assert.equal(
      String(input),
      "http://localhost:8000/api/v1/workspaces/workspace-123/actions/proposals/proposal-2/execution-preview"
    );
    assert.equal(init?.method, undefined);
    return new Response(JSON.stringify(disabledPreview), {
      headers: { "Content-Type": "application/json" },
      status: 200
    });
  }) as typeof fetch;

  try {
    const payload = await fetchActionExecutionPreview(
      "workspace-123",
      "proposal-2",
      { includeOwnerEmail: false }
    );
    assert.equal(payload.status, "preview_ready");
    assert.equal(payload.capabilities.external_execution, false);
    assert.equal(payload.preview?.repository, "qtwin-io/founderos-api");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("fetches persisted action proposal audit trail", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (input, init) => {
    assert.equal(
      String(input),
      "http://localhost:8000/api/v1/workspaces/workspace-123/actions/proposals/proposal-2/audit"
    );
    assert.equal(init?.method, undefined);
    return new Response(
      JSON.stringify({
        events: [auditEvent()],
        proposal_id: "proposal-2",
        receipt: emptyReceipt,
        workspace_id: "workspace-123"
      }),
      {
        headers: { "Content-Type": "application/json" },
        status: 200
      }
    );
  }) as typeof fetch;

  try {
    const payload = await fetchActionProposalAudit(
      "workspace-123",
      "proposal-2",
      { includeOwnerEmail: false }
    );
    assert.equal(payload.events[0]?.event_type, "execution_preview_generated");
    assert.equal(payload.receipt.provider_result, "none");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("posts execute request only through explicit execute client", async () => {
  const responseBody: ActionExecutionResponse = {
    execution: {
      error_message: null,
      external_id: "https://github.com/qtwin-io/founderos-api/issues/42",
      finished_at: "2026-06-25T01:06:00+06:00",
      id: "execution-1",
      provider_response: { number: 42 },
      started_at: "2026-06-25T01:06:00+06:00",
      status: "succeeded"
    },
    external_write_performed: true,
    is_live: true,
    proposal: {
      id: "proposal-2",
      status: "executed"
    },
    provider: "github",
    receipt: successfulReceipt,
    warnings: []
  };
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (input, init) => {
    assert.equal(
      String(input),
      "http://localhost:8000/api/v1/workspaces/workspace-123/actions/proposals/proposal-2/execute"
    );
    assert.equal(init?.method, "POST");
    assert.equal(
      init?.body,
      JSON.stringify({
        connection_id: "connection-1",
        confirm_external_write: true,
        idempotency_key: null
      })
    );
    return new Response(JSON.stringify(responseBody), {
      headers: { "Content-Type": "application/json" },
      status: 200
    });
  }) as typeof fetch;

  try {
    const payload = await executeActionProposal(
      "workspace-123",
      "proposal-2",
      {
        connection_id: "connection-1",
        confirm_external_write: true
      },
      { includeOwnerEmail: false }
    );
    assert.equal(payload.external_write_performed, true);
    assert.equal(payload.execution.status, "succeeded");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("renders not-approved execution state without execute controls", () => {
  const html = renderControls({ proposal: proposedProposal });
  assert.match(html, /Approve locally before previewing execution readiness/);
  assert.doesNotMatch(html, /Execute with confirmation/);
});

test("renders approved previewable state and dry-run preview details", () => {
  const html = renderControls({
    onPreview: () => undefined,
    preview: disabledPreview
  });
  assert.match(html, /Execution preview/);
  assert.match(html, /Preview execution/);
  assert.match(html, /preview_ready/);
  assert.match(html, /Preview only\. This will not write to GitHub/);
  assert.match(html, /qtwin-io\/founderos-api/);
  assert.match(html, /FounderOS follow-up/);
  assert.match(html, /External execution disabled in this environment/);
  assert.match(html, /execution_preview_generated/);
  assert.match(html, /Audit event recorded locally/);
  assert.match(html, /Evidence refs attached: 1/);
  assert.doesNotMatch(html, /source_events/);
  assert.doesNotMatch(html, /Created GitHub issue/i);
});

test("renders persisted audit events and local receipt", () => {
  const html = renderControls({
    auditEvents: [
      auditEvent({
        event_type: "execution_confirmation_received_but_disabled",
        event: "execution_confirmation_received_but_disabled",
        status: "blocked",
        message:
          "Execution confirmation was received, but external execution is disabled. No external write occurred."
      })
    ],
    preview: disabledPreview,
    receipt: emptyReceipt
  });
  assert.match(html, /Execution receipt/);
  assert.match(html, /Provider result/);
  assert.match(html, /none/);
  assert.match(html, /execution_confirmation_received_but_disabled/);
  assert.match(html, /No external write occurred/);
  assert.match(html, /Audit event recorded locally/);
});

test("falls back to proposal status timestamps when audit trail is empty", () => {
  const html = renderControls({
    auditEvents: [],
    preview: {
      ...disabledPreview,
      audit: []
    }
  });
  assert.match(html, /proposal_created/);
  assert.match(html, /proposal_approved/);
});

test("renders missing evidence warning without fabricating source refs", () => {
  const html = renderControls({
    preview: {
      ...disabledPreview,
      preview: {
        ...disabledPreview.preview!,
        evidence_refs: []
      }
    },
    proposal: {
      ...approvedProposal,
      evidence_refs: []
    }
  });
  assert.match(html, /No evidence refs returned/);
});

test("requires explicit confirmation before enabled live execution button", () => {
  const disabledHtml = renderControls({
    connectionId: "",
    confirmationChecked: false,
    onExecute: () => undefined,
    preview: enabledPreview
  });
  assert.match(disabledHtml, /This will create a real GitHub issue/);
  assert.match(disabledHtml, /Requires explicit confirmation/);
  assert.match(disabledHtml, /I confirm this may write to GitHub/);
  assert.match(disabledHtml, /disabled=""/);

  const enabledHtml = renderControls({
    connectionId: "connection-1",
    confirmationChecked: true,
    onExecute: () => undefined,
    preview: enabledPreview
  });
  assert.match(enabledHtml, /Execute with confirmation/);
});

test("renders execute result without raw provider response dump", () => {
  const html = renderControls({
    executeResult: {
      execution: {
        error_message: null,
        external_id: "https://github.com/qtwin-io/founderos-api/issues/42",
        finished_at: "2026-06-25T01:06:00+06:00",
        id: "execution-1",
        provider_response: { body: "raw body is not rendered", number: 42 },
        started_at: "2026-06-25T01:06:00+06:00",
        status: "succeeded"
      },
      external_write_performed: true,
      is_live: true,
      proposal: {
        id: "proposal-2",
        status: "executed"
      },
      provider: "github",
      receipt: successfulReceipt,
      warnings: []
    },
    preview: enabledPreview
  });
  assert.match(html, /Execution status/);
  assert.match(html, /External write performed/);
  assert.match(html, /Execution receipt/);
  assert.match(html, /GitHub issue created/);
  assert.match(html, /Open GitHub issue/);
  assert.match(html, /href="https:\/\/github.com\/qtwin-io\/founderos-api\/issues\/42"/);
  assert.doesNotMatch(html, /raw body is not rendered/);
  assert.doesNotMatch(html, /provider_response/);
});

test("renders blocked execute audit without external-write claim", () => {
  const html = renderControls({
    auditEvents: [
      auditEvent({
        error_code: "evidence_refs_are_required_for_live_execution",
        error_message: "evidence_refs are required for live execution",
        event: "execution_blocked",
        event_type: "execution_blocked",
        message:
          "Execution blocked: evidence_refs are required for live execution. No external write occurred.",
        status: "blocked"
      })
    ],
    error: "evidence_refs are required for live execution",
    preview: enabledPreview,
    receipt: {
      ...emptyReceipt,
      confirmation_received: true,
      error_code: "evidence_refs_are_required_for_live_execution",
      error_message: "evidence_refs are required for live execution",
      status: "failed"
    }
  });
  assert.match(html, /evidence_refs are required for live execution/);
  assert.match(html, /No external write occurred/);
  assert.match(html, /execution_blocked/);
  assert.doesNotMatch(html, /GitHub issue created/);
});
