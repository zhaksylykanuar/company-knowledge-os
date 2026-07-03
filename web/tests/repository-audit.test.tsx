import assert from "node:assert/strict";
import test from "node:test";

import { renderToStaticMarkup } from "react-dom/server";

import {
  buildRepoAuditPath,
  buildWorkspaceRepoAuditImportPath,
  importRepoAuditFindings
} from "../lib/api";
import {
  parseExternalAuditFindings,
  RepositoryAuditPanelView
} from "../components/RepositoryAuditPanel";
import { M, T } from "../lib/messages";
import type { ActionProposal, RepoAuditResponse } from "../lib/types";

const sampleAudit: RepoAuditResponse = {
  status: "computed",
  preview_only: true,
  computed: true,
  db_written: false,
  network_calls: false,
  generated_at: "2026-07-02T15:59:16.938144+00:00",
  source_snapshot: {
    available: true,
    status: "available",
    path: "discovery/github/local-repos-current/raw/repos.json",
    snapshot_id: "local-repos-current",
    snapshot_age_seconds: 181783,
    repo_count: 25
  },
  repo_count: 25,
  catalog_count: 19,
  repo_facts: [
    {
      name: "base-collector",
      full_name: "qtwin-io/base-collector",
      org: "qtwin-io",
      description_status: "missing",
      archived: false,
      fork: false,
      private: true,
      visibility: "private",
      default_branch: "master",
      pushed_at: "2025-12-26T11:50:45Z",
      days_since_last_push: 188,
      activity_bucket: "stale",
      primary_language: null,
      stack_candidate: "unknown",
      ci_detected: false,
      tests_detected: false,
      license_status: "missing",
      readme_status: "missing",
      owner_candidate_status: "unknown",
      area_candidate: "OPS",
      area_confidence: 0.74,
      needs_founder_confirm: true,
      risks: ["description_missing", "readme_missing"],
      unknowns: ["area_candidate_unconfirmed"],
      evidence_refs: ["github_discovery_snapshot:repos.json:base-collector:metadata"]
    },
    {
      name: "active-service",
      full_name: "qtwin-io/active-service",
      org: "qtwin-io",
      description_status: "present",
      archived: false,
      fork: false,
      private: false,
      visibility: "public",
      default_branch: "main",
      pushed_at: "2026-06-30T11:50:45Z",
      days_since_last_push: 2,
      activity_bucket: "active",
      primary_language: "Python",
      stack_candidate: "python-service",
      ci_detected: true,
      tests_detected: true,
      license_status: "present",
      readme_status: "present",
      owner_candidate_status: "candidate",
      area_candidate: "CORE",
      area_confidence: 0.9,
      needs_founder_confirm: false,
      risks: [],
      unknowns: [],
      evidence_refs: ["github_discovery_snapshot:repos.json:active-service:metadata"]
    }
  ],
  summary_cards: [
    {
      key: "computed_repo_count",
      label_ru: "Репозитории",
      value: 25,
      detail_ru: "Вычисленные факты из локального снимка."
    }
  ],
  risk_summary: {
    ci_not_detected: 25,
    readme_missing: 25,
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

const auditProposal: ActionProposal = {
  action_type: "internal_todo",
  approved_at: null,
  approved_by_user_id: null,
  briefing_item_id: null,
  created_at: "2026-07-02T16:00:00+00:00",
  created_by: "user",
  created_by_user_id: null,
  description: "Repo audit follow-up",
  evidence_refs: [],
  execution_started: false,
  id: "proposal-audit-1",
  is_live: false,
  payload: {
    source: "repo_audit_import",
    repository_full_name: "qtwin-io/base-collector",
    activity_bucket: "stale"
  },
  rejected_at: null,
  rejected_by_user_id: null,
  rejection_reason: null,
  status: "proposed",
  target_provider: "internal",
  title: "Repo audit follow-up: qtwin-io/base-collector",
  updated_at: "2026-07-02T16:00:00+00:00",
  warnings: [],
  workspace_id: "workspace-123"
};

function renderPanel(
  props: Partial<Parameters<typeof RepositoryAuditPanelView>[0]> = {}
): string {
  return renderToStaticMarkup(
    <RepositoryAuditPanelView
      actionError={props.actionError ?? null}
      actionProposals={props.actionProposals ?? []}
      actionSuccessMessage={props.actionSuccessMessage ?? null}
      data={"data" in props ? props.data ?? null : sampleAudit}
      error={props.error ?? null}
      focus={props.focus ?? "all"}
      onCreateAction={props.onCreateAction}
      onFocusChange={props.onFocusChange}
      onRetry={props.onRetry}
      pendingRepo={props.pendingRepo ?? null}
      status={props.status ?? "ready"}
    />
  );
}

test("builds the founder repo-audit path", () => {
  assert.equal(buildRepoAuditPath(), "/api/v1/founder/company-brain/repo-audit");
  assert.equal(
    buildWorkspaceRepoAuditImportPath("workspace-123"),
    "/api/v1/workspaces/workspace-123/actions/proposals/import-repo-audit"
  );
});

test("posts external repo-audit findings through the backend import endpoint", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (input, init) => {
    assert.equal(
      String(input),
      "http://localhost/api/v1/workspaces/workspace-123/actions/proposals/import-repo-audit"
    );
    assert.equal(init?.method, "POST");
    assert.equal(
      init?.body,
      JSON.stringify({
        findings: [
          {
            repository_full_name: "qtwin-io/base-collector",
            summary: "CI не найден",
            evidence_refs: ["external-audit:base-collector:ci"]
          }
        ]
      })
    );
    return new Response(
      JSON.stringify({
        proposals: [auditProposal],
        failures: [],
        succeeded_count: 1,
        failed_count: 0,
        is_live: false,
        execution_started: false,
        warnings: ["local-only"]
      }),
      {
        headers: { "Content-Type": "application/json" },
        status: 200
      }
    );
  }) as typeof fetch;

  try {
    const payload = await importRepoAuditFindings("workspace-123", {
      findings: [
        {
          repository_full_name: "qtwin-io/base-collector",
          summary: "CI не найден",
          evidence_refs: ["external-audit:base-collector:ci"]
        }
      ]
    });
    assert.equal(payload.succeeded_count, 1);
    assert.equal(payload.failed_count, 0);
    assert.equal(payload.proposals[0]?.payload.source, "repo_audit_import");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("renders deterministic repo audit summary and per-repo facts", () => {
  const html = renderPanel();
  assert.ok(html.includes(M.repoAudit.title));
  assert.ok(html.includes(M.repoAudit.badgeDeterministic));
  assert.ok(html.includes("qtwin-io/base-collector"));
  assert.ok(html.includes("qtwin-io/active-service"));
  assert.ok(html.includes(M.repoAudit.boundaryNote));
  assert.ok(html.includes("25"));
  // Guardrails: external writes are not enabled.
  assert.ok(html.includes(M.common.notEnabled));
  assert.doesNotMatch(html, /provider read started/i);
  assert.doesNotMatch(html, /external write performed/i);
  // Copy explicitly states LLM is NOT used; assert the boundary note is present
  // rather than asserting the token never appears.
  assert.ok(html.includes(M.repoAudit.boundaryNote));
  assert.ok(html.includes(M.repoAudit.importTitle));
  assert.ok(html.includes(M.repoAudit.importBoundary));
  assert.doesNotMatch(html, /LLM generated/i);
});

test("filters repo facts by risk and stale focus without network calls", () => {
  const risksHtml = renderPanel({ focus: "risks" });
  assert.ok(risksHtml.includes("qtwin-io/base-collector"));
  assert.doesNotMatch(risksHtml, /qtwin-io\/active-service/);

  const staleHtml = renderPanel({ focus: "stale" });
  assert.ok(staleHtml.includes("qtwin-io/base-collector"));
  assert.doesNotMatch(staleHtml, /qtwin-io\/active-service/);
});

test("cross-links existing local audit actions to repos and blocks duplicates", () => {
  const html = renderPanel({
    actionProposals: [auditProposal],
    onCreateAction: () => undefined
  });
  assert.ok(html.includes(T.repoAuditLinkedActions(1, 1, 0)));
  assert.ok(html.includes(M.repoAudit.actionAlreadyCreated));
  assert.ok(html.includes(M.repoAudit.openActions));
  assert.match(html, /href="\/actions\?origin=audit&amp;status=proposed"/);
});

test("parses external repo-audit findings into sanitized local proposal requests", () => {
  const findings = parseExternalAuditFindings(
    JSON.stringify({
      findings: [
        {
          repository_full_name: "qtwin-io/base-collector",
          title: "Проверить CI token=SHOULD_NOT_PERSIST",
          summary: "CI не найден; password=SHOULD_NOT_PERSIST",
          severity: "high",
          risks: ["ci_not_detected"],
          evidence_refs: ["external-audit:base-collector:ci"],
          recommended_next_step: "Добавить CI"
        }
      ]
    })
  );

  assert.equal(findings.length, 1);
  assert.equal(findings[0]?.repository_full_name, "qtwin-io/base-collector");
  assert.match(findings[0]?.title ?? "", /token=\[redacted\]/);
  assert.match(findings[0]?.summary ?? "", /password=\[redacted\]/);

  assert.equal(findings[0]?.repository_full_name, "qtwin-io/base-collector");
  assert.equal(findings[0]?.evidence_refs?.[0], "external-audit:base-collector:ci");
  assert.doesNotMatch(findings[0]?.summary ?? "", /SHOULD_NOT_PERSIST/);
});

test("rejects external audit imports without finding objects", () => {
  assert.throws(
    () => parseExternalAuditFindings(JSON.stringify({ findings: ["not-object"] })),
    /findings/
  );
  assert.throws(() => parseExternalAuditFindings("{not-json"), /JSON/);
});

test("renders loading, missing, empty, and error states safely", () => {
  assert.ok(renderPanel({ data: null, status: "loading" }).includes(M.repoAudit.loading));
  assert.ok(
    renderPanel({ data: null, status: "missing" }).includes(M.common.noWorkspaceTitle)
  );
  assert.ok(
    renderPanel({ data: null, status: "empty" }).includes(M.repoAudit.emptyTitle)
  );
  const errorHtml = renderPanel({
    data: null,
    error: "repo audit backend unavailable",
    onRetry: () => undefined,
    status: "error"
  });
  assert.ok(errorHtml.includes(M.repoAudit.unavailableTitle));
  assert.match(errorHtml, /repo audit backend unavailable/);
  assert.ok(errorHtml.includes(M.common.retry));
});
