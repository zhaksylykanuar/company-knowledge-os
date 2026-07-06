import assert from "node:assert/strict";
import test from "node:test";

import { renderToStaticMarkup } from "react-dom/server";

import { ConnectorsPanelView } from "../app/connectors/page";
import { buildWorkspaceConnectorsPath } from "../lib/api";
import { M } from "../lib/messages";
import type { ConnectorRegistryResponse } from "../lib/types";

const registry: ConnectorRegistryResponse = {
  workspace_id: "workspace-1",
  summary: {
    total: 4,
    available: 1,
    planned: 3,
    connected: 1
  },
  boundary: {
    provider_calls: false,
    external_writes: false,
    llm: false,
    reads_secrets: false
  },
  connectors: [
    {
      provider: "github",
      name: "GitHub",
      status: "available",
      read_only: true,
      manage_path: "/github",
      summary: "Read-only repository/issue/PR normalization.",
      connection_count: 1,
      connected_count: 1,
      has_connection: true
    },
    {
      provider: "jira",
      name: "Jira",
      status: "planned",
      read_only: true,
      manage_path: null,
      summary: "Planned minimal read-only issue import.",
      connection_count: 0,
      connected_count: 0,
      has_connection: false
    },
    {
      provider: "gmail",
      name: "Gmail",
      status: "planned",
      read_only: true,
      manage_path: null,
      summary: "Planned minimal read-only message import.",
      connection_count: 0,
      connected_count: 0,
      has_connection: false
    },
    {
      provider: "drive",
      name: "Google Drive",
      status: "planned",
      read_only: true,
      manage_path: null,
      summary: "Planned minimal read-only document import.",
      connection_count: 0,
      connected_count: 0,
      has_connection: false
    }
  ]
};

function renderPanel(
  props: Partial<Parameters<typeof ConnectorsPanelView>[0]> = {}
): string {
  return renderToStaticMarkup(
    <ConnectorsPanelView
      data={props.data === undefined ? registry : props.data}
      error={props.error ?? null}
      onRetry={props.onRetry}
      status={props.status ?? "ready"}
    />
  );
}

test("builds the workspace connectors API path", () => {
  assert.equal(
    buildWorkspaceConnectorsPath("workspace/with slash"),
    "/api/v1/workspaces/workspace%2Fwith%20slash/connectors"
  );
});

test("renders connector registry summary and provider cards without write claims", () => {
  const html = renderPanel();

  assert.ok(html.includes(M.connectors.title));
  assert.ok(html.includes(M.connectors.badgeReadOnly));
  assert.ok(html.includes(M.connectors.statusAvailable));
  assert.ok(html.includes(M.connectors.statusPlanned));
  assert.ok(html.includes("GitHub"));
  assert.ok(html.includes("Jira"));
  assert.ok(html.includes("Gmail"));
  assert.ok(html.includes("Google Drive"));
  assert.ok(html.includes(M.connectors.boundaryNote));
  assert.ok(html.includes('href="/github"'));
  assert.doesNotMatch(html, /provider call started/i);
  assert.doesNotMatch(html, /external write performed/i);
  assert.doesNotMatch(html, /SHOULD_NOT_LEAK/);
});

test("renders loading missing and error states", () => {
  assert.ok(renderPanel({ data: null, status: "loading" }).includes(M.connectors.loading));
  assert.ok(
    renderPanel({ data: null, status: "missing" }).includes(
      M.connectors.noWorkspaceDescription
    )
  );
  const errorHtml = renderPanel({
    data: null,
    error: "connector registry unavailable",
    onRetry: () => undefined,
    status: "error"
  });
  assert.ok(errorHtml.includes(M.connectors.unavailableTitle));
  assert.match(errorHtml, /connector registry unavailable/);
  assert.ok(errorHtml.includes(M.common.retry));
});
