import assert from "node:assert/strict";
import test from "node:test";

import { renderToStaticMarkup } from "react-dom/server";

import { PrivateBetaReadinessPanelView } from "../components/PrivateBetaReadinessPanel";
import { M, T } from "../lib/messages";
import type { CompanyBrainResponse } from "../lib/types";

const sampleCoverage: CompanyBrainResponse = {
  workspace_id: "workspace-123",
  mode: "github_first_canonical",
  source: "canonical_github_company_brain",
  summary: {
    repositories: 25,
    open_issues: 2,
    open_pull_requests: 3,
    closed_issues: 1,
    merged_pull_requests: 4
  },
  repositories: [],
  work: {
    issues: [],
    pull_requests: [],
    recent: []
  },
  evidence: [
    {
      id: "repo-source-1:0",
      kind: "repository_inventory_snapshot",
      source: "canonical_source_record",
      label: "qtwin-io/base-collector",
      url: "https://github.com/qtwin-io/base-collector",
      record_type: "repository",
      record_id: "repo-source-1"
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
  props: Partial<Parameters<typeof PrivateBetaReadinessPanelView>[0]> = {}
): string {
  return renderToStaticMarkup(
    <PrivateBetaReadinessPanelView
      data={props.data ?? sampleCoverage}
      error={props.error ?? null}
      onRetry={props.onRetry}
      status={props.status ?? "ready"}
    />
  );
}

test("renders private beta readiness from local canonical data only", () => {
  const html = renderPanel();

  assert.ok(html.includes(M.privateBetaReadiness.title));
  assert.ok(html.includes(M.privateBetaReadiness.badgeManual));
  assert.ok(html.includes(M.privateBetaReadiness.externalWritesValue));
  assert.ok(html.includes(M.privateBetaReadiness.deployValue));
  assert.ok(html.includes(M.privateBetaReadiness.aiValue));
  assert.ok(html.includes(T.privateBetaReadinessDataReady(25, 1, 5)));
  assert.ok(html.includes(M.privateBetaReadiness.providerReadDeferredDescription));
  assert.ok(html.includes(M.privateBetaReadiness.externalWritesOffDescription));
  assert.ok(html.includes(M.privateBetaReadiness.llmOffDescription));
  assert.ok(html.includes(M.privateBetaReadiness.runbookTitle));
  assert.ok(html.includes(M.privateBetaReadiness.runbookDescription));
  assert.ok(html.includes(M.privateBetaReadiness.runbookLocalGateLabel));
  assert.ok(html.includes(M.privateBetaReadiness.runbookBackupLabel));
  assert.ok(html.includes(M.privateBetaReadiness.runbookMigrationLabel));
  assert.ok(html.includes(M.privateBetaReadiness.runbookServicesLabel));
  assert.ok(html.includes(M.privateBetaReadiness.runbookSmokeLabel));
  assert.ok(html.includes(M.privateBetaReadiness.runbookRollbackLabel));
  assert.ok(html.includes(M.privateBetaReadiness.runbookBoundary));
  assert.doesNotMatch(html, /deploy started/i);
  assert.doesNotMatch(html, /external write performed/i);
  assert.doesNotMatch(html, /LLM generated/i);
});

test("renders missing/error states and needs-data readiness safely", () => {
  assert.ok(
    renderPanel({ data: null, status: "loading" }).includes(
      M.privateBetaReadiness.loading
    )
  );
  assert.ok(
    renderPanel({ data: null, status: "missing" }).includes(M.common.noWorkspaceTitle)
  );

  const errorHtml = renderPanel({
    data: null,
    error: "readiness backend unavailable",
    onRetry: () => undefined,
    status: "error"
  });
  assert.ok(errorHtml.includes(M.privateBetaReadiness.unavailableTitle));
  assert.match(errorHtml, /readiness backend unavailable/);
  assert.ok(errorHtml.includes(M.common.retry));

  const noDataHtml = renderPanel({
    data: {
      ...sampleCoverage,
      evidence: [],
      summary: {
        ...sampleCoverage.summary,
        open_issues: 0,
        open_pull_requests: 0,
        repositories: 0
      }
    }
  });
  assert.ok(noDataHtml.includes(M.privateBetaReadiness.statusNeedsData));
  assert.ok(noDataHtml.includes(M.privateBetaReadiness.dataNeedsEvidenceDescription));
  assert.doesNotMatch(noDataHtml, /fake/i);
});

test("labels live capabilities as available without claiming this panel starts them", () => {
  const html = renderPanel({
    data: {
      ...sampleCoverage,
      capabilities: {
        ...sampleCoverage.capabilities,
        live_provider_sync: true,
        llm_briefing: true
      }
    }
  });

  assert.ok(html.includes(M.privateBetaReadiness.statusAvailable));
  assert.ok(html.includes(M.privateBetaReadiness.providerReadAvailableDescription));
  assert.ok(html.includes(M.privateBetaReadiness.llmAvailableDescription));
  assert.doesNotMatch(html, /provider read запущен/i);
  assert.doesNotMatch(html, /LLM вызван/i);
});
