import assert from "node:assert/strict";
import test from "node:test";

import { renderToStaticMarkup } from "react-dom/server";

import {
  countAuditActionProposals,
  RepositoryAuditOverviewPanelView
} from "../components/RepositoryAuditOverviewPanel";
import { M, T } from "../lib/messages";
import type { ActionProposal, RepoAuditResponse } from "../lib/types";

const sampleAudit: RepoAuditResponse = {
  status: "computed",
  preview_only: true,
  computed: true,
  db_written: false,
  network_calls: false,
  generated_at: "2026-07-03T10:00:00+00:00",
  source_snapshot: {
    available: true,
    status: "available",
    path: "discovery/github/local-repos-current/raw/repos.json",
    snapshot_id: "local-repos-current",
    snapshot_age_seconds: 120,
    repo_count: 25
  },
  repo_count: 25,
  catalog_count: 19,
  repo_facts: [],
  summary_cards: [],
  risk_summary: {
    ci_not_detected: 25,
    readme_missing: 20,
    tests_not_detected: 25
  },
  area_candidate_counts: { CORE: 5, OPS: 4 },
  guardrails: {
    preview_only: true,
    computed: true,
    db_written: false,
    network_calls: false,
    external_writes: false,
    github_writes: false,
    jira_writes: false,
    obsidian_written: false
  }
};

const baseProposal: ActionProposal = {
  id: "proposal-1",
  workspace_id: "workspace-123",
  briefing_item_id: null,
  target_provider: "internal",
  action_type: "internal_todo",
  title: "Repo audit follow-up",
  description: null,
  payload: {},
  status: "proposed",
  evidence_refs: [],
  created_by: "user",
  created_by_user_id: null,
  approved_by_user_id: null,
  approved_at: null,
  rejected_by_user_id: null,
  rejected_at: null,
  rejection_reason: null,
  created_at: "2026-07-03T10:00:00+00:00",
  updated_at: "2026-07-03T10:00:00+00:00",
  proposal_version: "ap1_proposal_1",
  is_live: false,
  execution_started: false,
  warnings: []
};

const deterministicProposed: ActionProposal = {
  ...baseProposal,
  id: "audit-det-1",
  payload: { source: "repo_audit", repository_full_name: "qtwin-io/local-service" }
};

const deterministicApproved: ActionProposal = {
  ...baseProposal,
  id: "audit-det-2",
  status: "approved",
  payload: { source: "repo_audit", repository_full_name: "qtwin-io/core" }
};

const importedProposed: ActionProposal = {
  ...baseProposal,
  id: "audit-imp-1",
  payload: {
    source: "repo_audit_import",
    repository_full_name: "qtwin-io/base-collector"
  }
};

const nonAuditProposal: ActionProposal = {
  ...baseProposal,
  id: "briefing-1",
  payload: { source: "briefing_item" }
};

function renderPanel(
  props: Partial<Parameters<typeof RepositoryAuditOverviewPanelView>[0]> = {}
): string {
  return renderToStaticMarkup(
    <RepositoryAuditOverviewPanelView
      audit={"audit" in props ? props.audit ?? null : sampleAudit}
      counts={
        props.counts ?? {
          total: 3,
          deterministic: 2,
          imported: 1,
          proposed: 2
        }
      }
      error={props.error ?? null}
      onRetry={props.onRetry}
      status={props.status ?? "ready"}
    />
  );
}

test("counts audit-derived proposals by source and proposed status", () => {
  const counts = countAuditActionProposals([
    deterministicProposed,
    deterministicApproved,
    importedProposed,
    nonAuditProposal
  ]);
  assert.equal(counts.total, 3);
  assert.equal(counts.deterministic, 2);
  assert.equal(counts.imported, 1);
  assert.equal(counts.proposed, 2);
});

test("ignores non-audit proposals entirely in counts", () => {
  const counts = countAuditActionProposals([nonAuditProposal]);
  assert.equal(counts.total, 0);
  assert.equal(counts.deterministic, 0);
  assert.equal(counts.imported, 0);
  assert.equal(counts.proposed, 0);
});

test("renders deterministic audit summary and audit action counts with deep links", () => {
  const html = renderPanel();
  assert.ok(html.includes(M.repoAuditOverview.title));
  assert.ok(html.includes(M.repoAuditOverview.badge));
  // repo_count and total risk flags (25 + 20 + 25 = 70).
  assert.ok(html.includes("25"));
  assert.ok(html.includes("70"));
  assert.ok(html.includes(T.repoAuditOverviewActions(3, 2, 1, 2)));
  assert.ok(html.includes(M.repoAuditOverview.boundaryNote));
  assert.match(html, /href="\/audit"/);
  assert.match(html, /href="\/actions\?origin=audit&amp;status=proposed"/);
  assert.match(
    html,
    /href="\/actions\?origin=audit&amp;status=proposed&amp;audit_source=deterministic"/
  );
  assert.match(
    html,
    /href="\/actions\?origin=audit&amp;status=proposed&amp;audit_source=imported"/
  );
  assert.doesNotMatch(html, /provider call started/i);
  assert.doesNotMatch(html, /external write performed/i);
  assert.doesNotMatch(html, /LLM generated/i);
});

test("hides source-specific deep links and shows hint when there are no audit actions", () => {
  const html = renderPanel({
    counts: { total: 0, deterministic: 0, imported: 0, proposed: 0 }
  });
  assert.ok(html.includes(M.repoAuditOverview.emptyActionsHint));
  // The generic audit + audit-actions links remain, source-specific ones do not.
  assert.match(html, /href="\/audit"/);
  assert.doesNotMatch(html, /audit_source=deterministic/);
  assert.doesNotMatch(html, /audit_source=imported/);
});

test("renders loading, missing, and error states safely", () => {
  assert.ok(
    renderPanel({ audit: null, status: "loading" }).includes(
      M.repoAuditOverview.loading
    )
  );
  assert.ok(
    renderPanel({ audit: null, status: "missing" }).includes(
      M.common.noWorkspaceTitle
    )
  );
  const errorHtml = renderPanel({
    audit: null,
    error: "repo audit overview backend unavailable",
    onRetry: () => undefined,
    status: "error"
  });
  assert.ok(errorHtml.includes(M.repoAuditOverview.unavailableTitle));
  assert.match(errorHtml, /repo audit overview backend unavailable/);
  assert.ok(errorHtml.includes(M.common.retry));
});
