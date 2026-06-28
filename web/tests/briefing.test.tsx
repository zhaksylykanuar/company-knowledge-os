import assert from "node:assert/strict";
import test from "node:test";

import { renderToStaticMarkup } from "react-dom/server";

import {
  buildWorkspaceManualBriefingPath,
  generateManualFounderBriefing
} from "../lib/api";
import { M } from "../lib/messages";
import type { FounderBriefingResponse } from "../lib/types";
import { BriefingPanelView } from "../components/BriefingPanel";
import { EvidenceDrawer } from "../components/EvidenceDrawer";

const sampleBriefing: FounderBriefingResponse = {
  briefing: {
    title: "Founder Briefing",
    summary: "Deterministic briefing from canonical workspace records.",
    generated_at: "2026-06-24T10:00:00+00:00",
    workspace_id: "workspace-123",
    is_live: false,
    llm_used: false,
    persistence: "transient",
    items: [
      {
        id: "repo-coverage",
        category: "repository",
        title: "Repository inventory is available",
        summary: "One canonical GitHub repository is visible to the briefing.",
        severity: "info",
        confidence: 0.91,
        evidence_refs: [
          {
            kind: "repository_inventory_snapshot",
            source: "github",
            ref: "qtwin-io/founderos-api",
            url: "https://github.com/qtwin-io/founderos-api"
          }
        ],
        related_entities: ["qtwin-io/founderos-api"],
        recommended_next_step: "Review synced GitHub work before approving actions.",
        warnings: []
      },
      {
        id: "system-boundary",
        category: "system_fact",
        title: "Briefing is deterministic",
        summary: "The backend reports transient persistence and no LLM usage.",
        severity: "info",
        confidence: 1,
        evidence_refs: [],
        related_entities: [],
        recommended_next_step: null,
        warnings: ["No separate evidence ref returned for this system fact."]
      }
    ],
    signals: {
      github: {
        connection_status: "local_bridge_only",
        repository_count: 1,
        queued_sync_jobs: 0,
        latest_sync_job_status: "success"
      }
    },
    warnings: ["Founder Briefing v0 is deterministic and does not use an LLM."]
  }
};

const emptyBriefing: FounderBriefingResponse = {
  ...sampleBriefing,
  briefing: {
    ...sampleBriefing.briefing,
    items: [],
    signals: {
      github: {
        connection_status: "local_bridge_only",
        repository_count: 0,
        queued_sync_jobs: 0,
        latest_sync_job_status: null
      }
    },
    warnings: ["No evidence refs were available for this workspace."]
  }
};

function renderPanel(
  props: Partial<Parameters<typeof BriefingPanelView>[0]> = {}
): string {
  return renderToStaticMarkup(
    <BriefingPanelView
      data={"data" in props ? props.data ?? null : sampleBriefing}
      error={props.error ?? null}
      onCloseEvidence={props.onCloseEvidence}
      onGenerate={props.onGenerate}
      onRetry={props.onRetry}
      onSelectEvidence={props.onSelectEvidence}
      selectedEvidence={props.selectedEvidence ?? null}
      selectedEvidenceItemTitle={props.selectedEvidenceItemTitle ?? null}
      status={props.status ?? "success"}
    />
  );
}

test("builds the manual briefing URL", () => {
  assert.equal(
    buildWorkspaceManualBriefingPath("workspace-123"),
    "/api/v1/workspaces/workspace-123/briefings/manual"
  );
});

test("posts deterministic manual briefing request", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (input, init) => {
    assert.equal(
      String(input),
      "http://localhost/api/v1/workspaces/workspace-123/briefings/manual"
    );
    assert.equal(init?.method, "POST");
    assert.equal(
      init?.body,
      JSON.stringify({
        focus: ["github", "sync", "repositories"],
        include_github: true,
        include_connections: true,
        include_sync_jobs: true,
        include_repository_inventory: true,
        limit: 20
      })
    );
    return new Response(JSON.stringify(sampleBriefing), {
      headers: { "Content-Type": "application/json" },
      status: 200
    });
  }) as typeof fetch;

  try {
    const payload = await generateManualFounderBriefing("workspace-123", {}, {});
    assert.equal(payload.briefing.llm_used, false);
    assert.equal(payload.briefing.persistence, "transient");
    assert.equal(payload.briefing.items[0]?.evidence_refs[0]?.source, "github");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("renders loading state", () => {
  const html = renderPanel({ data: null, status: "loading" });
  assert.ok(html.includes(M.briefingPanel.loadingDeterministic));
});

test("renders no-workspace state without any operator-key gate", () => {
  const html = renderPanel({ data: null, status: "missing" });
  assert.ok(html.includes(M.common.noWorkspaceTitle));
  assert.doesNotMatch(html, /operator API key/);
  assert.doesNotMatch(html, /owner email/);
});

test("renders empty no-data state before generation", () => {
  const html = renderPanel({ data: null, status: "empty" });
  assert.ok(html.includes(M.briefingPanel.noBriefingTitle));
  assert.ok(html.includes(M.briefingPanel.noBriefingDescription));
});

test("renders unsupported state", () => {
  const html = renderPanel({ data: null, status: "unsupported" });
  assert.ok(html.includes(M.briefingPanel.unsupportedTitle));
  assert.ok(html.includes(M.briefingPanel.unsupportedDescription));
});

test("renders backend error state with retry", () => {
  const html = renderPanel({
    data: null,
    error: "briefing backend unavailable",
    onRetry: () => undefined,
    status: "error"
  });
  assert.ok(html.includes(M.briefingPanel.unavailableTitle));
  assert.match(html, /briefing backend unavailable/);
  assert.ok(html.includes(M.common.retry));
});

test("renders deterministic briefing sections and summary", () => {
  const html = renderPanel();
  assert.ok(html.includes(M.briefingPanel.title));
  assert.ok(html.includes(M.briefingPanel.intro));
  assert.ok(html.includes(M.briefingPanel.reposTitle));
  assert.ok(html.includes(M.briefingPanel.queuedTitle));
  assert.ok(html.includes(M.briefingPanel.latestSyncTitle));
  assert.ok(html.includes(M.briefingPanel.aiTitle));
  assert.match(html, /Repository inventory is available/);
  assert.match(html, /Briefing is deterministic/);
  assert.match(html, /91%/);
});

test("renders empty briefing payload without fake claims", () => {
  const html = renderPanel({ data: emptyBriefing, status: "empty" });
  assert.ok(html.includes(M.briefingPanel.noItems));
  assert.match(html, /No evidence refs were available/);
  assert.doesNotMatch(html, /strategic advice/);
  assert.doesNotMatch(html, /source_events/);
});

test("renders evidence buttons and deterministic system fact labels", () => {
  const html = renderPanel();
  assert.match(html, /Источник: qtwin-io\/founderos-api/);
  assert.ok(html.includes(M.briefingPanel.noEvidenceRef));
  assert.match(html, /Сводка ИИ: не включено/);
  assert.match(html, /Живая синхронизация провайдера: не включено/);
  assert.match(html, /Внешние действия: здесь не выполняются/);
  assert.doesNotMatch(html, /AI summary/);
});

test("renders evidence drawer with provider, source, record, and URL", () => {
  const evidence = sampleBriefing.briefing.items[0]?.evidence_refs[0] ?? null;
  const html = renderToStaticMarkup(
    <EvidenceDrawer
      evidence={evidence}
      itemTitle="Repository inventory is available"
      onClose={() => undefined}
    />
  );

  assert.ok(html.includes(M.evidence.title));
  assert.match(html, /qtwin-io\/founderos-api/);
  assert.match(html, /github/);
  assert.match(html, /repository_inventory_snapshot/);
  assert.ok(html.includes(M.evidence.noSnippet));
  assert.ok(html.includes(M.common.openSource));
  assert.doesNotMatch(html, /provider_metadata/);
  assert.doesNotMatch(html, /access_token/);
});

test("renders evidence drawer fallback when no evidence is selected", () => {
  const html = renderToStaticMarkup(<EvidenceDrawer evidence={null} />);
  assert.ok(html.includes(M.evidence.placeholder));
  assert.ok(!html.includes(M.common.openSource));
});
