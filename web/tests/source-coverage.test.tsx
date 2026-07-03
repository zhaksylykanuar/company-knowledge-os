import assert from "node:assert/strict";
import test from "node:test";

import { renderToStaticMarkup } from "react-dom/server";

import { M, T } from "../lib/messages";
import type { CompanyBrainResponse } from "../lib/types";
import { SourceCoveragePanelView } from "../components/SourceCoveragePanel";

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

const emptyCoverage: CompanyBrainResponse = {
  ...sampleCoverage,
  summary: {
    repositories: 0,
    open_issues: 0,
    open_pull_requests: 0,
    closed_issues: 0,
    merged_pull_requests: 0
  },
  evidence: [],
  warnings: ["No canonical GitHub records have been synced for this workspace yet."]
};

function renderPanel(
  props: Partial<Parameters<typeof SourceCoveragePanelView>[0]> = {}
): string {
  return renderToStaticMarkup(
    <SourceCoveragePanelView
      data={props.data ?? sampleCoverage}
      error={props.error ?? null}
      onRetry={props.onRetry}
      status={props.status ?? "ready"}
    />
  );
}

test("renders local source coverage counts without implying live provider or AI use", () => {
  const html = renderPanel();

  assert.ok(html.includes(M.sourceCoverage.title));
  assert.ok(html.includes(M.sourceCoverage.repositoriesTitle));
  assert.ok(html.includes("25"));
  assert.ok(html.includes("2 задач / 3 PR"));
  assert.ok(html.includes(M.sourceCoverage.modeLocal));
  assert.ok(html.includes(M.sourceCoverage.statusDeferred));
  assert.ok(html.includes(M.sourceCoverage.statusOff));
  assert.ok(html.includes(M.sourceCoverage.liveProviderDeferredDescription));
  assert.ok(html.includes(M.sourceCoverage.llmOffDescription));
  assert.doesNotMatch(html, /provider read запущен/i);
  assert.doesNotMatch(html, /ИИ сгенерировал/i);
});

test("renders loading, missing, error, and empty states", () => {
  assert.ok(renderPanel({ data: null, status: "loading" }).includes(M.sourceCoverage.loading));
  assert.ok(renderPanel({ data: null, status: "missing" }).includes(M.common.noWorkspaceTitle));

  const errorHtml = renderPanel({
    data: null,
    error: "backend unavailable",
    onRetry: () => undefined,
    status: "error"
  });
  assert.ok(errorHtml.includes(M.sourceCoverage.unavailableTitle));
  assert.match(errorHtml, /backend unavailable/);
  assert.ok(errorHtml.includes(M.common.retry));

  const emptyHtml = renderPanel({ data: emptyCoverage, status: "empty" });
  assert.ok(emptyHtml.includes(M.sourceCoverage.emptyTitle));
  assert.ok(emptyHtml.includes(M.sourceCoverage.emptyDescription));
});

test("renders evidence status from Company Brain evidence refs", () => {
  const readyHtml = renderPanel();
  assert.ok(readyHtml.includes(M.sourceCoverage.evidenceLabel));
  assert.ok(readyHtml.includes("Для текущей выборки возвращено evidence refs: 1."));

  const noEvidenceHtml = renderPanel({ data: { ...sampleCoverage, evidence: [] } });
  assert.ok(noEvidenceHtml.includes(M.sourceCoverage.statusNeedsEvidence));
  assert.ok(noEvidenceHtml.includes(M.sourceCoverage.evidenceEmpty));
});

const breakdownCoverage: CompanyBrainResponse = {
  ...sampleCoverage,
  summary: {
    repositories: 2,
    open_issues: 2,
    open_pull_requests: 3,
    closed_issues: 7,
    merged_pull_requests: 9
  },
  repositories: [
    {
      id: "repo-1",
      provider: "github",
      external_id: "ext-1",
      name: "base-collector",
      full_name: "qtwin-io/base-collector",
      visibility: "private",
      archived: false,
      source_url: "https://github.com/qtwin-io/base-collector",
      last_activity_at: null,
      source_refs: [
        {
          id: "repo-source-1:0",
          kind: "repository_inventory_snapshot",
          source: "canonical_source_record",
          label: "qtwin-io/base-collector",
          url: null,
          record_type: "repository",
          record_id: "repo-source-1"
        }
      ]
    },
    {
      id: "repo-2",
      provider: "github",
      external_id: "ext-2",
      name: "no-refs",
      full_name: "qtwin-io/no-refs",
      visibility: "public",
      archived: false,
      source_url: null,
      last_activity_at: null,
      source_refs: []
    }
  ],
  work: {
    issues: [],
    pull_requests: [],
    recent: [
      {
        id: "work-1",
        type: "issue",
        external_id: "i-1",
        number: 12,
        title: "Recent issue",
        state: "open",
        repository_full_name: "qtwin-io/base-collector",
        repository_external_id: "ext-1",
        source_url: null,
        updated_at: null,
        source_refs: []
      }
    ]
  },
  evidence: [
    {
      id: "repo-source-1:0",
      kind: "repository_inventory_snapshot",
      source: "canonical_source_record",
      label: "qtwin-io/base-collector",
      url: null,
      record_type: "repository",
      record_id: "repo-source-1"
    },
    {
      id: "repo-source-2:0",
      kind: "repository_inventory_snapshot",
      source: "canonical_source_record",
      label: "qtwin-io/no-refs",
      url: null,
      record_type: "repository",
      record_id: "repo-source-2"
    },
    {
      id: "issue-source-1:0",
      kind: "work_item_snapshot",
      source: "canonical_source_record",
      label: "qtwin-io/base-collector#12",
      url: null,
      record_type: "work_item",
      record_id: "issue-source-1"
    }
  ]
};

test("renders local coverage breakdown from already loaded Company Brain payload", () => {
  const html = renderPanel({ data: breakdownCoverage });

  assert.ok(html.includes(M.sourceCoverage.breakdownTitle));
  assert.ok(html.includes(M.sourceCoverage.closedWorkTitle));
  assert.ok(html.includes(T.sourceCoverageClosedWork(7, 9)));
  assert.ok(html.includes(M.sourceCoverage.recentTitle));
  assert.ok(html.includes(T.sourceCoverageReposWithEvidence(1, 2)));
  assert.ok(html.includes(T.sourceCoverageReposWithoutEvidence(1)));
  assert.ok(html.includes(T.sourceCoverageEvidenceKind("repository_inventory_snapshot", 2)));
  assert.ok(html.includes(T.sourceCoverageEvidenceKind("work_item_snapshot", 1)));
});

test("breakdown stays safe with no repositories or evidence and makes no live/AI claim", () => {
  const html = renderPanel({ data: { ...sampleCoverage, repositories: [], evidence: [] } });

  assert.ok(html.includes(M.sourceCoverage.breakdownTitle));
  assert.ok(html.includes(M.sourceCoverage.evidenceKindsEmpty));
  assert.doesNotMatch(html, /provider read запущен/i);
  assert.doesNotMatch(html, /ИИ сгенерировал/i);
});
