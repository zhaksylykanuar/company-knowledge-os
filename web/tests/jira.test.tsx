import assert from "node:assert/strict";
import test from "node:test";

import { renderToStaticMarkup } from "react-dom/server";

import { extractJiraIssuesFromJson, JiraConnectorPanelView } from "../app/jira/page";
import { buildWorkspaceJiraImportPath, buildWorkspaceJiraIssuesPath } from "../lib/api";
import { M } from "../lib/messages";
import type { JiraIssueListResponse } from "../lib/types";

const jiraIssues: JiraIssueListResponse = {
  workspace_id: "workspace-1",
  counts: {
    total: 2,
    not_done: 1,
    done: 1
  },
  boundary: {
    provider_calls: false,
    sync_started: false,
    external_writes: false,
    llm: false,
    reads_secrets: false
  },
  warnings: [],
  issues: [
    {
      task_id: "task-1",
      source_record_id: "source-1",
      key: "FOS-123",
      title: "Review private beta onboarding",
      status: "To Do",
      status_category: "not_done",
      priority: "High",
      due_date: "2026-07-12",
      source_url: "https://jira.example/browse/FOS-123",
      updated_at: "2026-07-06T10:00:00Z",
      project_key: "FOS",
      issue_type: "Task",
      evidence_refs: [
        {
          kind: "jira_issue",
          source: "jira",
          ref: "FOS-123",
          url: "https://jira.example/browse/FOS-123"
        }
      ]
    },
    {
      task_id: "task-2",
      source_record_id: "source-2",
      key: "FOS-124",
      title: "Ship local Jira import",
      status: "Done",
      status_category: "done",
      priority: null,
      due_date: null,
      source_url: null,
      updated_at: null,
      project_key: "FOS",
      issue_type: null,
      evidence_refs: []
    }
  ]
};

function renderPanel(
  props: Partial<Parameters<typeof JiraConnectorPanelView>[0]> = {}
): string {
  return renderToStaticMarkup(
    <JiraConnectorPanelView
      canImport={props.canImport}
      data={props.data === undefined ? jiraIssues : props.data}
      error={props.error ?? null}
      importError={props.importError ?? null}
      importMessage={props.importMessage ?? null}
      importPending={props.importPending ?? false}
      importText={props.importText ?? ""}
      onImport={props.onImport}
      onImportTextChange={props.onImportTextChange}
      onRetry={props.onRetry}
      status={props.status ?? "ready"}
    />
  );
}

test("builds Jira connector API paths", () => {
  assert.equal(
    buildWorkspaceJiraIssuesPath("workspace/with slash"),
    "/api/v1/workspaces/workspace%2Fwith%20slash/jira/issues"
  );
  assert.equal(
    buildWorkspaceJiraImportPath("workspace/with slash"),
    "/api/v1/workspaces/workspace%2Fwith%20slash/jira/issues/import"
  );
});

test("extracts Jira issues from array or object JSON", () => {
  assert.deepEqual(extractJiraIssuesFromJson('[{"key":"FOS-1"}]'), [{ key: "FOS-1" }]);
  assert.deepEqual(extractJiraIssuesFromJson('{"issues":[{"key":"FOS-2"}]}'), [
    { key: "FOS-2" }
  ]);
  assert.throws(() => extractJiraIssuesFromJson('{"items":[]}'), /JSON/);
});

test("renders Jira issues with one setup path and a collapsed manual import", () => {
  const html = renderPanel({
    importMessage: M.jira.importSuccess(2, 0),
    importText: '[{"key":"FOS-123"}]'
  });

  assert.ok(html.includes("Данные Jira"));
  assert.ok(html.includes('href="/settings/integrations?provider=jira"'));
  assert.ok(html.includes("FOS-123"));
  assert.ok(html.includes("Review private beta onboarding"));
  assert.ok(html.includes("Импортировать JSON вручную"));
  assert.ok(html.includes(M.jira.importTitle));
  assert.ok(html.includes(M.jira.importSuccess(2, 0)));
  assert.ok(html.includes('href="https://jira.example/browse/FOS-123"'));
  assert.doesNotMatch(html, /Local-only|provider_calls|sync_started/);
  assert.doesNotMatch(html, /provider call started/i);
  assert.doesNotMatch(html, /external write performed/i);
  assert.doesNotMatch(html, /LLM started/i);
  assert.doesNotMatch(html, /SHOULD_NOT_LEAK/);
});

test("keeps Jira facts visible but removes import controls in read-only mode", () => {
  const html = renderPanel({ canImport: false });

  assert.ok(html.includes("FOS-123"));
  assert.ok(html.includes(M.common.sourceAdminOnlyNote));
  assert.doesNotMatch(html, new RegExp(M.jira.importTitle));
  assert.doesNotMatch(html, /<form/);
});

test("renders empty loading missing and error states", () => {
  const emptyHtml = renderPanel({
    data: { ...jiraIssues, counts: { done: 0, not_done: 0, total: 0 }, issues: [] }
  });
  assert.ok(emptyHtml.includes("Задач Jira пока нет"));
  assert.ok(emptyHtml.includes("Подключить Jira"));
  assert.ok(renderPanel({ data: null, status: "loading" }).includes(M.jira.loading));
  assert.ok(
    renderPanel({ data: null, status: "missing" }).includes(M.jira.noWorkspaceDescription)
  );
  const errorHtml = renderPanel({
    data: null,
    error: "jira backend unavailable",
    onRetry: () => undefined,
    status: "error"
  });
  assert.ok(errorHtml.includes(M.jira.unavailableTitle));
  assert.match(errorHtml, /jira backend unavailable/);
  assert.ok(errorHtml.includes(M.common.retry));
});
