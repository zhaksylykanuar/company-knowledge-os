import assert from "node:assert/strict";
import test from "node:test";

import { renderToStaticMarkup } from "react-dom/server";

import {
  CompanyWorldPanelView,
  validSelectedKey
} from "../components/CompanyWorldPanel";
import {
  buildWorkspaceCompanyMapPath,
  fetchCompanyMap
} from "../lib/api";
import { M } from "../lib/messages";
import type { CompanyMapResponse } from "../lib/types";

const sourceRef = {
  id: "source-1:0",
  kind: "gmail_message",
  source: "gmail",
  label: "message-1",
  url: "https://mail.google.com/mail/u/0/#inbox/message-1",
  record_type: "message",
  record_id: "source-1"
};

const sampleMap: CompanyMapResponse = {
  workspace_id: "workspace-123",
  mode: "evidence_backed_projection",
  source: "workspace_and_company_brain_projection",
  company: {
    key: "workspace:workspace-123",
    workspace_id: "workspace-123",
    name: "Northstar Labs",
    slug: "northstar-labs",
    status: "active",
    source_refs: [
      {
        ...sourceRef,
        id: "workspace:workspace-123",
        kind: "workspace",
        source: "founderos",
        label: "Northstar Labs",
        url: null,
        record_type: "workspace",
        record_id: "workspace-123"
      }
    ]
  },
  summary: {
    internal_people: 1,
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
    internal: [
      {
        key: "user:user-1",
        user_id: "user-1",
        name: "Анна",
        email: "anna@northstar.test",
        status: "active",
        role: "owner",
        source_refs: [
          {
            ...sourceRef,
            id: "membership:membership-1",
            kind: "workspace_membership",
            source: "founderos",
            label: "owner",
            url: null,
            record_type: "membership",
            record_id: "membership-1"
          }
        ]
      }
    ],
    external_candidates: [
      {
        key: "external-person:buyer",
        email: "buyer@acme.test",
        display_name: "Buyer Person",
        organization_key: "organization:acme.test",
        last_interaction_at: "2026-07-12T12:00:00Z",
        interaction_count: 2,
        source_refs: [sourceRef],
        needs_founder_confirm: true
      }
    ]
  },
  organizations: [
    {
      key: "organization:acme.test",
      domain: "acme.test",
      name: null,
      kind: "external_candidate",
      people_count: 1,
      interaction_count: 2,
      last_interaction_at: "2026-07-12T12:00:00Z",
      source_refs: [sourceRef],
      needs_founder_confirm: true
    }
  ],
  touchpoints: [
    {
      key: "touchpoint:source-1",
      channel: "email",
      source_record_id: "source-1",
      subject: "Kickoff and next steps",
      direction: "inbound",
      occurred_at: "2026-07-12T12:00:00Z",
      person_keys: ["user:user-1", "external-person:buyer"],
      organization_keys: ["organization:acme.test"],
      source_url: "https://mail.google.com/mail/u/0/#inbox/message-1",
      source_refs: [sourceRef]
    }
  ],
  capabilities: {
    read_only: true,
    provider_calls: false,
    llm_used: false
  },
  warnings: ["Кандидаты требуют подтверждения."],
  is_live: false,
  llm_used: false
};

function renderPanel(
  status: "loading" | "ready" | "empty" | "error" | "missing",
  data: CompanyMapResponse | null = sampleMap
): string {
  return renderToStaticMarkup(
    <CompanyWorldPanelView data={data} error={null} status={status} />
  );
}

test("builds and fetches the workspace company-map endpoint", async () => {
  assert.equal(
    buildWorkspaceCompanyMapPath("workspace-123"),
    "/api/v1/workspaces/workspace-123/company-map"
  );

  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (input) => {
    assert.equal(
      String(input),
      "http://localhost/api/v1/workspaces/workspace-123/company-map"
    );
    return new Response(JSON.stringify(sampleMap), {
      headers: { "Content-Type": "application/json" },
      status: 200
    });
  }) as typeof fetch;

  try {
    const payload = await fetchCompanyMap("workspace-123");
    assert.equal(payload.summary.internal_people, 1);
    assert.equal(payload.people.external_candidates[0]?.needs_founder_confirm, true);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("renders loading, missing, empty, and error states", () => {
  assert.ok(renderPanel("loading", null).includes(M.companyWorld.loading));
  assert.ok(renderPanel("missing", null).includes(M.common.noWorkspaceTitle));
  assert.ok(renderPanel("empty").includes(M.companyWorld.emptyTitle));
  assert.ok(
    renderToStaticMarkup(
      <CompanyWorldPanelView data={null} error="offline" status="error" />
    ).includes("offline")
  );
});

test("renders an evidence-backed company world with provisional candidates", () => {
  const html = renderPanel("ready");

  assert.ok(html.includes("Northstar Labs"));
  assert.ok(html.includes("Анна"));
  assert.ok(html.includes("Buyer Person"));
  assert.ok(html.includes("acme.test"));
  assert.ok(html.includes("Kickoff and next steps"));
  assert.ok(html.includes(M.companyWorld.needsConfirmation));
  assert.ok(html.includes(M.companyWorld.boundary));
  assert.ok(html.includes(M.companyWorld.windowTruncated));
  assert.ok(html.includes("Кандидаты требуют подтверждения."));
  assert.ok(html.includes(M.companyWorld.readOnly));
  assert.ok(html.includes(M.companyWorld.noProviderCalls));
  assert.ok(html.includes(M.companyWorld.localProjection));
  assert.ok(html.includes('aria-pressed="true"'));
  assert.doesNotMatch(html, /PRIVATE_BODY|raw_body/);
});

test("falls back to the company when a selected profile disappears", () => {
  assert.equal(
    validSelectedKey(sampleMap, "external-person:removed"),
    sampleMap.company.key
  );
  assert.equal(
    validSelectedKey(sampleMap, sampleMap.people.external_candidates[0]?.key ?? null),
    sampleMap.people.external_candidates[0]?.key
  );
});
