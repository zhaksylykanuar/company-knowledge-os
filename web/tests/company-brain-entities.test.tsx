import assert from "node:assert/strict";
import test from "node:test";

import { renderToStaticMarkup } from "react-dom/server";

import {
  NormalizedEntitiesPanelView,
  filterEntitiesByType
} from "../components/NormalizedEntitiesPanel";
import {
  buildWorkspaceCompanyBrainEntitiesPath,
  fetchCompanyBrainEntities
} from "../lib/api";
import { M } from "../lib/messages";
import type { NormalizedEntitiesResponse } from "../lib/types";

const sampleEntities: NormalizedEntitiesResponse = {
  workspace_id: "workspace-123",
  mode: "github_first_canonical",
  source: "canonical_company_brain_entities",
  summary: {
    total: 3,
    by_entity_type: [
      { entity_type: "repository", count: 1 },
      { entity_type: "issue", count: 1 },
      { entity_type: "document", count: 1 }
    ],
    by_source_provider: [
      { source_provider: "github", count: 2 },
      { source_provider: "internal", count: 1 }
    ]
  },
  entities: [
    {
      entity_type: "repository",
      key: "github:repository:qtwin-io/founderos-api",
      external_id: "qtwin-io/founderos-api",
      title: "qtwin-io/founderos-api",
      source_provider: "github",
      status: "active",
      source_url: "https://github.com/qtwin-io/founderos-api",
      updated_at: "2026-07-06T10:00:00+00:00",
      reference_id: "repo-row-1",
      source_refs: [
        {
          id: "repo-source-1:0",
          kind: "repository_inventory_snapshot",
          source: "github",
          label: "repo-snapshot-1",
          url: "https://github.com/qtwin-io/founderos-api",
          record_type: "repository",
          record_id: "repo-source-1"
        }
      ]
    },
    {
      entity_type: "issue",
      key: "github:issue:qtwin-io/founderos-api#issue/42",
      external_id: "qtwin-io/founderos-api#issue/42",
      title: "Investigate issue 42",
      source_provider: "github",
      status: "open",
      source_url: "https://github.com/qtwin-io/founderos-api/issues/42",
      updated_at: "2026-07-06T10:00:00+00:00",
      reference_id: "issue-row-1",
      source_refs: []
    },
    {
      entity_type: "document",
      key: "internal:document:doc-1",
      external_id: "doc-1",
      title: "Private beta checklist",
      source_provider: "internal",
      status: "published",
      source_url: null,
      updated_at: "2026-07-06T10:00:00+00:00",
      reference_id: "doc-1",
      source_refs: [
        {
          id: "doc-1:document",
          kind: "internal_document",
          source: "internal",
          label: "Private beta checklist",
          url: null,
          record_type: "document",
          record_id: "doc-1"
        }
      ]
    }
  ],
  evidence: [
    {
      id: "repo-source-1:0",
      kind: "repository_inventory_snapshot",
      source: "github",
      label: "repo-snapshot-1",
      url: "https://github.com/qtwin-io/founderos-api",
      record_type: "repository",
      record_id: "repo-source-1"
    },
    {
      id: "doc-1:document",
      kind: "internal_document",
      source: "internal",
      label: "Private beta checklist",
      url: null,
      record_type: "document",
      record_id: "doc-1"
    }
  ],
  capabilities: {
    live_github_oauth: false,
    live_provider_sync: false,
    local_sync: true,
    llm_briefing: false
  },
  is_live: false,
  llm_used: false,
  warnings: []
};

function renderPanel(
  props: Partial<Parameters<typeof NormalizedEntitiesPanelView>[0]> = {}
): string {
  return renderToStaticMarkup(
    <NormalizedEntitiesPanelView
      data={"data" in props ? props.data ?? null : sampleEntities}
      error={props.error ?? null}
      onRetry={props.onRetry}
      status={props.status ?? "ready"}
    />
  );
}

test("builds normalized entities API path", () => {
  assert.equal(
    buildWorkspaceCompanyBrainEntitiesPath("workspace-123"),
    "/api/v1/workspaces/workspace-123/company-brain/entities"
  );
});

test("fetches normalized entities without provider writes", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (input, init) => {
    assert.equal(
      String(input),
      "http://localhost/api/v1/workspaces/workspace-123/company-brain/entities"
    );
    assert.equal(init?.method, undefined);
    return new Response(JSON.stringify(sampleEntities), {
      headers: { "Content-Type": "application/json" },
      status: 200
    });
  }) as typeof fetch;

  try {
    const payload = await fetchCompanyBrainEntities("workspace-123", {});
    assert.equal(payload.summary.total, 3);
    assert.equal(payload.is_live, false);
    assert.equal(payload.llm_used, false);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("renders normalized entities list and boundary copy", () => {
  const html = renderPanel();
  assert.ok(html.includes(M.companyBrainEntities.title));
  assert.ok(html.includes(M.companyBrainEntities.badgeProjection));
  assert.ok(html.includes(M.companyBrainEntities.filterTitle));
  assert.ok(html.includes(`${M.companyBrainEntities.filterAll} · 3`));
  assert.ok(html.includes("repository · 1"));
  assert.ok(html.includes("document · 1"));
  assert.ok(html.includes("qtwin-io/founderos-api"));
  assert.ok(html.includes("Investigate issue 42"));
  assert.ok(html.includes("Private beta checklist"));
  assert.ok(html.includes(M.companyBrainEntities.boundaryNote));
  assert.doesNotMatch(html, /provider call started/i);
  assert.doesNotMatch(html, /LLM used/i);
});

test("filters normalized entities by type locally", () => {
  assert.equal(filterEntitiesByType(sampleEntities.entities, "all").length, 3);
  const documents = filterEntitiesByType(sampleEntities.entities, "document");
  assert.equal(documents.length, 1);
  assert.equal(documents[0]?.title, "Private beta checklist");
  assert.deepEqual(filterEntitiesByType(sampleEntities.entities, "missing_type"), []);
});

test("renders normalized entities empty and error states", () => {
  const empty = renderPanel({ data: null, status: "empty" });
  assert.ok(empty.includes(M.companyBrainEntities.emptyTitle));
  const errored = renderPanel({
    data: null,
    error: "backend down",
    onRetry: () => undefined,
    status: "error"
  });
  assert.ok(errored.includes(M.companyBrainEntities.unavailableTitle));
  assert.match(errored, /backend down/);
  assert.ok(errored.includes(M.common.retry));
});
