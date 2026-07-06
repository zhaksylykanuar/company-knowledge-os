import assert from "node:assert/strict";
import test from "node:test";

import { renderToStaticMarkup } from "react-dom/server";

import {
  buildWorkspaceCompanyBrainPath,
  fetchCompanyBrain
} from "../lib/api";
import { M } from "../lib/messages";
import type { CompanyBrainResponse } from "../lib/types";
import { CompanyBrainPanelView } from "../components/CompanyBrainPanel";

const sampleBrain: CompanyBrainResponse = {
  workspace_id: "workspace-123",
  mode: "github_first_canonical",
  source: "canonical_github_company_brain",
  summary: {
    repositories: 1,
    open_issues: 1,
    open_pull_requests: 1,
    closed_issues: 1,
    merged_pull_requests: 1
  },
  repositories: [
    {
      id: "repo-row-1",
      provider: "github",
      external_id: "qtwin-io/founderos-api",
      name: "founderos-api",
      full_name: "qtwin-io/founderos-api",
      visibility: "private",
      archived: false,
      source_url: "https://github.com/qtwin-io/founderos-api",
      last_activity_at: "2026-06-24T10:00:00+00:00",
      source_refs: [
        {
          id: "repo-source-1:0",
          kind: "repository_inventory_snapshot",
          source: "canonical_source_record",
          label: "repo-snapshot-1",
          url: "https://github.com/qtwin-io/founderos-api",
          record_type: "repository",
          record_id: "repo-source-1"
        }
      ]
    }
  ],
  work: {
    issues: [
      {
        id: "issue-row-1",
        type: "issue",
        external_id: "qtwin-io/founderos-api#issue/42",
        number: 42,
        title: "Investigate issue 42",
        state: "open",
        repository_full_name: "qtwin-io/founderos-api",
        repository_external_id: "qtwin-io/founderos-api",
        source_url: "https://github.com/qtwin-io/founderos-api/issues/42",
        updated_at: "2026-06-24T10:00:00+00:00",
        source_refs: [
          {
            id: "issue-source-1:0",
            kind: "github_issue",
            source: "github",
            label: "qtwin-io/founderos-api#issue/42",
            url: "https://github.com/qtwin-io/founderos-api/issues/42",
            record_type: "issue",
            record_id: "issue-source-1"
          }
        ]
      }
    ],
    pull_requests: [
      {
        id: "pr-row-1",
        type: "pull_request",
        external_id: "qtwin-io/founderos-api#pull/7",
        number: 7,
        title: "Ship PR 7",
        state: "open",
        repository_full_name: "qtwin-io/founderos-api",
        repository_external_id: "qtwin-io/founderos-api",
        source_url: "https://github.com/qtwin-io/founderos-api/pull/7",
        updated_at: "2026-06-24T10:00:00+00:00",
        source_refs: [
          {
            id: "pr-source-1:0",
            kind: "github_pull_request",
            source: "github",
            label: "qtwin-io/founderos-api#pull/7",
            url: "https://github.com/qtwin-io/founderos-api/pull/7",
            record_type: "pull_request",
            record_id: "pr-source-1"
          }
        ]
      }
    ],
    recent: [
      {
        id: "merged-pr-row-1",
        type: "pull_request",
        external_id: "qtwin-io/founderos-api#pull/8",
        number: 8,
        title: "Merge PR 8",
        state: "merged",
        repository_full_name: "qtwin-io/founderos-api",
        repository_external_id: "qtwin-io/founderos-api",
        source_url: "https://github.com/qtwin-io/founderos-api/pull/8",
        updated_at: "2026-06-24T10:00:00+00:00",
        source_refs: []
      }
    ]
  },
  communications: {
    messages: [
      {
        source_record_id: "gmail-source-1",
        message_id: "msg-1",
        thread_id: "thread-1",
        subject: "Investor follow-up",
        snippet: "Following up from imported Gmail metadata.",
        from_address: "founder@example.test",
        to_addresses: ["investor@example.test"],
        labels: ["INBOX", "UNREAD"],
        unread: true,
        received_at: "2026-07-06T10:00:00+00:00",
        source_url: "https://mail.google.com/mail/u/0/#inbox/msg-1",
        source_refs: [
          {
            id: "gmail-source-1:0",
            kind: "gmail_message",
            source: "gmail",
            label: "msg-1",
            url: "https://mail.google.com/mail/u/0/#inbox/msg-1",
            record_type: "message",
            record_id: "gmail-source-1"
          }
        ]
      }
    ]
  },
  documents: {
    files: [
      {
        source_record_id: "drive-source-1",
        file_id: "file-1",
        name: "Private beta checklist",
        mime_type: "application/vnd.google-apps.document",
        owners: ["founder@example.test"],
        drive_id: null,
        folder_path: null,
        shared: true,
        size_bytes: null,
        modified_at: "2026-07-06T10:00:00+00:00",
        source_url: "https://drive.google.com/file/d/file-1/view",
        source_refs: [
          {
            id: "drive-source-1:0",
            kind: "drive_file",
            source: "drive",
            label: "file-1",
            url: "https://drive.google.com/file/d/file-1/view",
            record_type: "file",
            record_id: "drive-source-1"
          }
        ]
      }
    ]
  },
  evidence: [
    {
      id: "repo-source-1:0",
      kind: "repository_inventory_snapshot",
      source: "canonical_source_record",
      label: "repo-snapshot-1",
      url: "https://github.com/qtwin-io/founderos-api",
      record_type: "repository",
      record_id: "repo-source-1"
    },
    {
      id: "issue-source-1:0",
      kind: "github_issue",
      source: "github",
      label: "qtwin-io/founderos-api#issue/42",
      url: "https://github.com/qtwin-io/founderos-api/issues/42",
      record_type: "issue",
      record_id: "issue-source-1"
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

const emptyBrain: CompanyBrainResponse = {
  ...sampleBrain,
  summary: {
    repositories: 0,
    open_issues: 0,
    open_pull_requests: 0,
    closed_issues: 0,
    merged_pull_requests: 0
  },
  repositories: [],
  work: {
    issues: [],
    pull_requests: [],
    recent: []
  },
  communications: {
    messages: []
  },
  documents: {
    files: []
  },
  evidence: [],
  warnings: ["No canonical GitHub records have been synced for this workspace yet."]
};

function renderPanel(
  props: Partial<Parameters<typeof CompanyBrainPanelView>[0]> = {}
): string {
  return renderToStaticMarkup(
    <CompanyBrainPanelView
      data={props.data ?? sampleBrain}
      error={props.error ?? null}
      onRetry={props.onRetry}
      status={props.status ?? "ready"}
    />
  );
}

test("builds the workspace Company Brain URL", () => {
  assert.equal(
    buildWorkspaceCompanyBrainPath("workspace-123"),
    "/api/v1/workspaces/workspace-123/company-brain"
  );
});

test("fetches and parses Company Brain payloads", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (input) => {
    assert.equal(
      String(input),
      "http://localhost/api/v1/workspaces/workspace-123/company-brain"
    );
    return new Response(JSON.stringify(sampleBrain), {
      headers: { "Content-Type": "application/json" },
      status: 200
    });
  }) as typeof fetch;

  try {
    const payload = await fetchCompanyBrain("workspace-123", {});
    assert.equal(payload.mode, "github_first_canonical");
    assert.equal(payload.summary.open_pull_requests, 1);
    assert.equal(payload.capabilities.live_provider_sync, false);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("renders loading state", () => {
  const html = renderPanel({ data: null, status: "loading" });
  assert.ok(html.includes(M.companyBrain.loading));
});

test("renders no-workspace state without any operator-key gate", () => {
  const html = renderPanel({ data: null, status: "missing" });
  assert.ok(html.includes(M.common.noWorkspaceTitle));
  assert.doesNotMatch(html, /operator API key/);
  assert.doesNotMatch(html, /owner email/);
});

test("renders empty state", () => {
  const html = renderPanel({ data: emptyBrain, status: "empty" });
  assert.ok(html.includes(M.companyBrain.emptyTitle));
  assert.ok(html.includes(M.companyBrain.emptyDescription));
});

test("renders backend error state with retry", () => {
  const html = renderPanel({
    data: null,
    error: "backend unavailable",
    onRetry: () => undefined,
    status: "error"
  });
  assert.ok(html.includes(M.companyBrain.unavailableTitle));
  assert.match(html, /backend unavailable/);
  assert.ok(html.includes(M.common.retry));
});

test("renders summary counts, repositories, issues, and PRs", () => {
  const html = renderPanel();
  assert.ok(html.includes(M.companyBrain.title));
  assert.ok(html.includes(M.companyBrain.reposTitle));
  assert.ok(html.includes(M.companyBrain.openIssuesTitle));
  assert.ok(html.includes(M.companyBrain.openPrsTitle));
  assert.match(html, /1 \/ 1/);
  assert.match(html, /qtwin-io\/founderos-api/);
  assert.match(html, /Investigate issue 42/);
  assert.match(html, /Ship PR 7/);
  assert.match(html, /Merge PR 8/);
});

test("renders Jira issues as first-class Company Brain work items", () => {
  const html = renderPanel({
    data: {
      ...sampleBrain,
      summary: {
        ...sampleBrain.summary,
        open_issues: 2
      },
      work: {
        ...sampleBrain.work,
        issues: [
          ...sampleBrain.work.issues,
          {
            id: "jira-task-1",
            type: "issue",
            source_provider: "jira",
            external_id: "FOS-123",
            number: null,
            title: "Review private beta onboarding",
            state: "To Do",
            repository_full_name: null,
            repository_external_id: null,
            project_key: "FOS",
            source_url: "https://jira.example/browse/FOS-123",
            updated_at: "2026-07-06T10:00:00+00:00",
            source_refs: [
              {
                id: "jira-source-1:0",
                kind: "jira_issue",
                source: "jira",
                label: "FOS-123",
                url: "https://jira.example/browse/FOS-123",
                record_type: "issue",
                record_id: "jira-source-1"
              }
            ]
          }
        ]
      }
    }
  });

  assert.match(html, /Review private beta onboarding/);
  assert.ok(html.includes(M.companyBrain.metaProvider));
  assert.match(html, /jira/);
  assert.ok(html.includes(M.companyBrain.metaScope));
  assert.match(html, /FOS/);
  assert.match(html, /FOS-123/);
  assert.doesNotMatch(html, /provider call started/i);
  assert.doesNotMatch(html, /external write performed/i);
});

test("renders Gmail messages and Drive files as first-class Company Brain sections", () => {
  const html = renderPanel();

  assert.ok(html.includes(M.companyBrain.messagesSection));
  assert.match(html, /Investor follow-up/);
  assert.ok(html.includes(M.companyBrain.badgeUnread));
  assert.match(html, /founder@example.test/);
  assert.match(html, /msg-1/);
  assert.ok(html.includes(M.companyBrain.filesSection));
  assert.match(html, /Private beta checklist/);
  assert.ok(html.includes(M.companyBrain.badgeSharedFile));
  assert.match(html, /application\/vnd.google-apps.document/);
  assert.match(html, /file-1/);
  assert.doesNotMatch(html, /raw body/i);
  assert.doesNotMatch(html, /provider call started/i);
});

test("renders evidence and source refs without fake company facts", () => {
  const html = renderPanel();
  assert.ok(html.includes(M.companyBrain.evidenceSection));
  assert.match(html, /repo-snapshot-1/);
  assert.match(html, /qtwin-io\/founderos-api#issue\/42/);
  assert.match(html, /github_issue/);
  assert.ok(html.includes(M.companyBrain.noSourceRef));
  assert.doesNotMatch(html, /source_events/);
  assert.doesNotMatch(html, /AI knows/);
  assert.doesNotMatch(html, /strategic priority/);
});

test("renders deterministic capability boundary", () => {
  const html = renderPanel();
  assert.ok(html.includes(M.companyBrain.badgeDeterministic));
  assert.match(html, /Живой OAuth: не включено/);
  assert.match(html, /Синхронизация провайдера: не включено/);
  assert.match(html, /Сводка ИИ: не включено/);
});
