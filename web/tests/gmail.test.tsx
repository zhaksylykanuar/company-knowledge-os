import assert from "node:assert/strict";
import test from "node:test";

import { renderToStaticMarkup } from "react-dom/server";

import { extractGmailMessagesFromJson, GmailConnectorPanelView } from "../app/gmail/page";
import { buildWorkspaceGmailImportPath, buildWorkspaceGmailMessagesPath } from "../lib/api";
import { M } from "../lib/messages";
import type { GmailMessageListResponse } from "../lib/types";

const gmailMessages: GmailMessageListResponse = {
  workspace_id: "workspace-1",
  counts: {
    total: 2,
    unread: 1,
    read: 1
  },
  boundary: {
    provider_calls: false,
    sync_started: false,
    external_writes: false,
    llm: false,
    reads_secrets: false
  },
  warnings: [],
  messages: [
    {
      source_record_id: "source-1",
      message_id: "msg-1",
      thread_id: "thread-1",
      subject: "Investor intro follow-up",
      snippet: "Following up on the intro call from yesterday.",
      from_address: "founder@example.test",
      to_addresses: ["investor@example.test"],
      labels: ["INBOX", "UNREAD"],
      unread: true,
      received_at: "2026-07-06T10:00:00Z",
      source_url: "https://mail.google.com/mail/u/0/#inbox/msg-1",
      evidence_refs: [
        {
          kind: "gmail_message",
          source: "gmail",
          ref: "msg-1",
          url: "https://mail.google.com/mail/u/0/#inbox/msg-1"
        }
      ]
    },
    {
      source_record_id: "source-2",
      message_id: "msg-2",
      thread_id: null,
      subject: "Weekly ops digest",
      snippet: null,
      from_address: null,
      to_addresses: [],
      labels: ["INBOX"],
      unread: false,
      received_at: null,
      source_url: null,
      evidence_refs: []
    }
  ]
};

function renderPanel(
  props: Partial<Parameters<typeof GmailConnectorPanelView>[0]> = {}
): string {
  return renderToStaticMarkup(
    <GmailConnectorPanelView
      canImport={props.canImport}
      data={props.data === undefined ? gmailMessages : props.data}
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

test("builds Gmail connector API paths", () => {
  assert.equal(
    buildWorkspaceGmailMessagesPath("workspace/with slash"),
    "/api/v1/workspaces/workspace%2Fwith%20slash/gmail/messages"
  );
  assert.equal(
    buildWorkspaceGmailImportPath("workspace/with slash"),
    "/api/v1/workspaces/workspace%2Fwith%20slash/gmail/messages/import"
  );
});

test("extracts Gmail messages from array or object JSON", () => {
  assert.deepEqual(extractGmailMessagesFromJson('[{"id":"msg-1"}]'), [{ id: "msg-1" }]);
  assert.deepEqual(extractGmailMessagesFromJson('{"messages":[{"id":"msg-2"}]}'), [
    { id: "msg-2" }
  ]);
  assert.throws(() => extractGmailMessagesFromJson('{"items":[]}'), /JSON/);
});

test("renders Gmail messages with one setup path and a collapsed manual import", () => {
  const html = renderPanel({
    importMessage: M.gmail.importSuccess(2, 0),
    importText: '[{"id":"msg-1"}]'
  });

  assert.ok(html.includes("Данные Gmail"));
  assert.ok(html.includes('href="/settings/integrations?provider=gmail"'));
  assert.ok(html.includes("Investor intro follow-up"));
  assert.ok(html.includes(M.gmail.unreadBadge));
  assert.ok(html.includes("Импортировать JSON вручную"));
  assert.ok(html.includes(M.gmail.importTitle));
  assert.ok(html.includes(M.gmail.importSuccess(2, 0)));
  assert.ok(html.includes('href="https://mail.google.com/mail/u/0/#inbox/msg-1"'));
  assert.doesNotMatch(html, /Local-only|provider_calls|sync_started/);
  assert.doesNotMatch(html, /provider call started/i);
  assert.doesNotMatch(html, /external write performed/i);
  assert.doesNotMatch(html, /LLM started/i);
  assert.doesNotMatch(html, /RAW_BODY/);
});

test("keeps Gmail facts visible but removes import controls in read-only mode", () => {
  const html = renderPanel({ canImport: false });

  assert.ok(html.includes("Investor intro follow-up"));
  assert.ok(html.includes(M.common.sourceAdminOnlyNote));
  assert.doesNotMatch(html, new RegExp(M.gmail.importTitle));
  assert.doesNotMatch(html, /<form/);
});

test("renders empty loading missing and error states", () => {
  const emptyHtml = renderPanel({
    data: { ...gmailMessages, counts: { read: 0, total: 0, unread: 0 }, messages: [] }
  });
  assert.ok(emptyHtml.includes("Писем Gmail пока нет"));
  assert.ok(emptyHtml.includes("Подключить Gmail"));
  assert.ok(renderPanel({ data: null, status: "loading" }).includes(M.gmail.loading));
  assert.ok(
    renderPanel({ data: null, status: "missing" }).includes(M.gmail.noWorkspaceDescription)
  );
  const errorHtml = renderPanel({
    data: null,
    error: "gmail backend unavailable",
    onRetry: () => undefined,
    status: "error"
  });
  assert.ok(errorHtml.includes(M.gmail.unavailableTitle));
  assert.match(errorHtml, /gmail backend unavailable/);
  assert.ok(errorHtml.includes(M.common.retry));
});
