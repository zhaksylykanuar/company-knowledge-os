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
    available: 4,
    planned: 0,
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
      status: "available",
      read_only: true,
      manage_path: "/jira",
      summary: "Local read-only issue import.",
      connection_count: 0,
      connected_count: 0,
      has_connection: false
    },
    {
      provider: "gmail",
      name: "Gmail",
      status: "available",
      read_only: true,
      manage_path: "/gmail",
      summary: "Local read-only message import.",
      connection_count: 0,
      connected_count: 0,
      has_connection: false
    },
    {
      provider: "drive",
      name: "Google Drive",
      status: "available",
      read_only: true,
      manage_path: "/drive",
      summary: "Local read-only file import.",
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
      canManageSources={props.canManageSources ?? true}
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

test("renders a recommended source mission and clear provider states without write claims", () => {
  const html = renderPanel();

  assert.ok(html.includes("Ваши источники"));
  assert.ok(html.includes("1 источник уже даёт факты компании"));
  assert.ok(html.includes("Откройте Jira и выполните короткую настройку"));
  assert.ok(html.includes("Появятся задачи, ответственные"));
  assert.ok(html.includes("Подключён"));
  assert.ok(html.includes("Можно подключить"));
  assert.ok(html.includes("connector-card--connected"));
  assert.ok(html.includes("connector-card--available"));
  assert.ok(html.includes("GitHub"));
  assert.ok(html.includes("Jira"));
  assert.ok(html.includes("Gmail"));
  assert.ok(html.includes("Google Drive"));
  assert.ok(html.includes(M.connectors.boundaryNote));
  assert.ok(html.includes("mission-strip-details"));
  assert.ok(html.includes('href="/github"'));
  assert.ok(html.includes('href="/jira"'));
  assert.ok(html.includes('href="/gmail"'));
  assert.ok(html.includes('href="/drive"'));
  assert.doesNotMatch(html, /provider call started/i);
  assert.doesNotMatch(html, /external write performed/i);
  assert.doesNotMatch(html, /SHOULD_NOT_LEAK/);
});

test("does not call an inactive connection connected", () => {
  const attentionRegistry: ConnectorRegistryResponse = {
    ...registry,
    summary: { ...registry.summary, connected: 0 },
    connectors: registry.connectors.map((connector) =>
      connector.provider === "github"
        ? { ...connector, connected_count: 0, has_connection: true }
        : connector
    )
  };
  const html = renderPanel({ data: attentionRegistry });

  assert.ok(html.includes("connector-card--attention"));
  assert.ok(html.includes("Нужно проверить"));
  assert.ok(html.includes("Проверить подключение"));
  assert.doesNotMatch(html, /connector-card connector-card--connected/);
});

test("keeps source setup role-aware for a read-only participant", () => {
  const html = renderPanel({ canManageSources: false });

  assert.ok(html.includes("посмотрите, какие данные он добавит"));
  assert.ok(html.includes("какие данные сможет подключить администратор"));
  assert.ok(html.includes("Посмотреть источник"));
  assert.ok(html.includes("владелец или администратор"));
  assert.doesNotMatch(html, />Настроить источник</);
  assert.doesNotMatch(html, /Результат<\/small><strong>Появятся/);
});

test("renders planned connectors as a distinct later state", () => {
  const plannedRegistry: ConnectorRegistryResponse = {
    ...registry,
    summary: { ...registry.summary, available: 3, planned: 1 },
    connectors: registry.connectors.map((connector) =>
      connector.provider === "drive"
        ? {
            ...connector,
            status: "planned",
            manage_path: null
          }
        : connector
    )
  };
  const html = renderPanel({ data: plannedRegistry });

  assert.ok(html.includes("connector-card--later"));
  assert.ok(html.includes("Этот источник появится позже"));
  assert.ok(html.includes("Позже"));
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
