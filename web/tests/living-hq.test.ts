import assert from "node:assert/strict";
import test from "node:test";

import {
  deriveLivingHqView,
  type LivingHqWorldMetricKey
} from "../lib/living-hq";
import type { TodayFacts } from "../lib/today";
import type {
  ActionProposal,
  CompanyBrainSourceRef,
  CompanyMapResponse
} from "../lib/types";

const facts: TodayFacts = {
  briefingCount: 1,
  candidateCount: 2,
  memberCount: 2,
  proposedDecisionCount: 2,
  role: "owner",
  sourceRecordCount: 8,
  workspaceId: "workspace-1",
  workspaceName: "Northstar"
};

const sourceRef: CompanyBrainSourceRef = {
  id: "gmail:message-1",
  kind: "gmail_message",
  source: "gmail",
  label: "Message 1",
  url: "https://mail.google.com/message-1",
  record_type: "message",
  record_id: "message-1"
};

function proposal(
  overrides: Partial<ActionProposal> = {}
): ActionProposal {
  return {
    id: "proposal-1",
    workspace_id: "workspace-1",
    briefing_item_id: null,
    target_provider: "internal",
    action_type: "internal_todo",
    title: "Позвонить заказчику",
    description: "Проверить следующую договорённость.",
    payload: { severity: "medium" },
    status: "proposed",
    evidence_refs: [
      {
        kind: "gmail_message",
        source: "gmail",
        ref: "message-1",
        url: "https://mail.google.com/message-1"
      }
    ],
    created_by: "system",
    created_by_user_id: null,
    approved_by_user_id: null,
    approved_at: null,
    rejected_by_user_id: null,
    rejected_at: null,
    rejection_reason: null,
    created_at: "2026-07-14T08:00:00Z",
    updated_at: "2026-07-14T08:00:00Z",
    proposal_version: "ap1_proposal_1",
    is_live: false,
    execution_started: false,
    warnings: [],
    ...overrides
  };
}

function companyMap(
  overrides: Partial<CompanyMapResponse> = {}
): CompanyMapResponse {
  return {
    workspace_id: "workspace-1",
    mode: "evidence_backed_projection",
    source: "workspace_and_company_brain_projection",
    company: {
      key: "workspace:workspace-1",
      workspace_id: "workspace-1",
      name: "Northstar",
      slug: "northstar",
      status: "active",
      source_refs: [
        {
          ...sourceRef,
          id: "workspace:workspace-1",
          kind: "workspace",
          source: "founderos",
          label: "Northstar",
          url: null,
          record_type: "workspace",
          record_id: "workspace-1"
        }
      ]
    },
    summary: {
      internal_people: 2,
      confirmed_external_people: 1,
      confirmed_organizations: 1,
      external_contacts_in_window: 1,
      organizations_in_window: 1,
      touchpoints_in_window: 1
    },
    window: {
      gmail_messages_available: 3,
      gmail_messages_considered: 1,
      message_limit: 1,
      truncated: true,
      order: "newest_first"
    },
    people: {
      internal: [],
      confirmed_external: [],
      external_candidates: [
        {
          key: "external-person:buyer",
          candidate_version: "a".repeat(64),
          email: "buyer@example.test",
          display_name: "Покупатель",
          organization_key: "organization:example.test",
          last_interaction_at: "2026-07-14T10:00:00Z",
          interaction_count: 2,
          source_refs: [sourceRef],
          needs_founder_confirm: true
        }
      ]
    },
    organizations: [
      {
        key: "organization:example.test",
        candidate_version: "b".repeat(64),
        domain: "example.test",
        name: "Example",
        kind: "external_candidate",
        people_count: 1,
        interaction_count: 2,
        last_interaction_at: "2026-07-14T10:00:00Z",
        source_refs: [sourceRef],
        needs_founder_confirm: true
      }
    ],
    confirmed_organizations: [],
    touchpoints: [
      {
        key: "touchpoint:message-1",
        channel: "email",
        source_record_id: "message-1",
        subject: "Следующие шаги",
        direction: "inbound",
        occurred_at: "2026-07-14T11:00:00Z",
        person_keys: ["external-person:buyer"],
        organization_keys: ["organization:example.test"],
        source_url: "https://mail.google.com/message-1",
        source_refs: [sourceRef]
      }
    ],
    capabilities: {
      read_only: true,
      can_resolve: true,
      required_role: "member",
      provider_calls: false,
      llm_used: false
    },
    warnings: ["Окно писем ограничено."],
    is_live: false,
    llm_used: false,
    ...overrides
  };
}

function metric(
  view: ReturnType<typeof deriveLivingHqView>,
  key: LivingHqWorldMetricKey
) {
  const found = view.world.metrics.find((item) => item.key === key);
  assert.ok(found);
  return found;
}

test("Living HQ deterministically selects the highest-severity evidenced proposal", () => {
  const newerLow = proposal({
    id: "proposal-low",
    payload: { severity: "low" },
    title: "Низкий приоритет",
    updated_at: "2026-07-14T12:00:00Z"
  });
  const olderHigh = proposal({
    id: "proposal-high",
    payload: { severity: "high" },
    title: "Высокий приоритет",
    updated_at: "2026-07-14T09:00:00Z"
  });

  const first = deriveLivingHqView({
    facts,
    companyMap: companyMap(),
    actionProposals: [newerLow, olderHigh]
  });
  const reversed = deriveLivingHqView({
    facts,
    companyMap: companyMap(),
    actionProposals: [olderHigh, newerLow]
  });

  assert.equal(first.mission.proposalId, "proposal-high");
  assert.equal(reversed.mission.proposalId, "proposal-high");
  assert.equal(first.mission.evidenceState, "referenced");
  assert.equal(first.mission.evidence.length, 1);
  assert.equal(first.mission.canAct, true);
});

test("Living HQ never turns an unsupported proposal into a specific mission or change", () => {
  const unsupported = proposal({
    id: "proposal-unsupported",
    evidence_refs: [],
    title: "Недоказанное утверждение"
  });
  const view = deriveLivingHqView({
    facts: { ...facts, proposedDecisionCount: 1 },
    companyMap: companyMap(),
    actionProposals: [unsupported]
  });

  assert.equal(view.mission.id, "review-proposals");
  assert.equal(view.mission.proposalId, null);
  assert.equal(view.mission.evidenceState, "unavailable");
  assert.doesNotMatch(view.mission.title, /Недоказанное утверждение/);
  assert.equal(view.changes.some((item) => item.id.includes("unsupported")), false);
  assert.equal(view.unsupportedSignalCount, 1);
});

test("change feed is a current evidence snapshot and labels evidence trust", () => {
  const view = deriveLivingHqView({
    facts,
    companyMap: companyMap(),
    actionProposals: [proposal()]
  });

  assert.equal(view.changeBasis, "current_evidence_snapshot");
  assert.equal(view.changesAreSinceLastVisit, false);
  assert.equal(view.changes[0]?.id, "touchpoint:touchpoint:message-1");
  assert.equal(
    view.changes.find((item) => item.id.startsWith("proposal:"))?.evidenceState,
    "referenced"
  );
  assert.equal(
    view.changes.find((item) => item.id.startsWith("touchpoint:"))?.evidenceState,
    "direct"
  );
  assert.ok(view.changes.every((item) => item.evidence.length > 0));
});

test("world missions and candidate signals open the exact opaque profile", () => {
  const view = deriveLivingHqView({
    facts: { ...facts, proposedDecisionCount: 0 },
    companyMap: companyMap(),
    actionProposals: []
  });

  assert.equal(view.mission.kind, "review_world");
  assert.equal(
    view.mission.href,
    `/company-brain?profile=${encodeURIComponent(
      `v1:person-candidate:${"a".repeat(64)}`
    )}#company-world-profile`
  );
  const personSignal = view.changes.find((item) =>
    item.id.startsWith("person:")
  );
  assert.ok(personSignal?.href);
  assert.equal(personSignal.href.includes("buyer@example.test"), false);
  assert.equal(personSignal.href.includes("example.test"), false);
});

test("world summary marks window-derived counts as lower bounds", () => {
  const view = deriveLivingHqView({
    facts,
    companyMap: companyMap(),
    actionProposals: []
  });

  assert.equal(view.world.availability, "partial");
  assert.equal(metric(view, "internal_people").value, 2);
  assert.equal(metric(view, "internal_people").precision, "exact");
  assert.equal(metric(view, "pending_confirmations").value, 2);
  assert.equal(metric(view, "pending_confirmations").precision, "at_least");
  assert.equal(metric(view, "touchpoints").precision, "at_least");
  assert.ok(view.world.evidenceCount > 0);
  assert.equal(view.world.isLive, false);
});

test("missing map remains explicit instead of inventing world counts", () => {
  const view = deriveLivingHqView({
    facts: { ...facts, candidateCount: null },
    companyMap: null,
    actionProposals: []
  });

  assert.equal(view.isPartial, true);
  assert.equal(view.world.availability, "unavailable");
  assert.equal(metric(view, "confirmed_external_people").value, null);
  assert.equal(
    metric(view, "confirmed_external_people").precision,
    "unavailable"
  );
  assert.equal(view.world.evidenceCount, 0);
});

test("foreign-workspace map and proposals are ignored", () => {
  const foreignMap = companyMap({ workspace_id: "workspace-2" });
  const foreignProposal = proposal({
    id: "foreign-proposal",
    workspace_id: "workspace-2"
  });
  const view = deriveLivingHqView({
    facts: { ...facts, proposedDecisionCount: 0, candidateCount: 0 },
    companyMap: foreignMap,
    actionProposals: [foreignProposal]
  });

  assert.deepEqual(view.inputIssues, [
    "company_map_workspace_mismatch",
    "proposal_workspace_mismatch"
  ]);
  assert.equal(view.world.availability, "unavailable");
  assert.equal(view.changes.length, 0);
  assert.notEqual(view.mission.proposalId, "foreign-proposal");
});

test("setup mission is derived from aggregate facts without fake evidence", () => {
  const view = deriveLivingHqView({
    facts: {
      ...facts,
      briefingCount: 0,
      candidateCount: 0,
      proposedDecisionCount: 0,
      sourceRecordCount: 0
    },
    companyMap: companyMap({
      people: {
        internal: [],
        confirmed_external: [],
        external_candidates: []
      },
      organizations: [],
      touchpoints: []
    }),
    actionProposals: []
  });

  assert.equal(view.mission.kind, "connect_source");
  assert.equal(view.mission.evidenceState, "aggregate");
  assert.deepEqual(view.mission.evidence, []);
  assert.equal(view.mission.href, "/github");
});
