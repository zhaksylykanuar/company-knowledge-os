import assert from "node:assert/strict";
import test from "node:test";

import { renderToStaticMarkup } from "react-dom/server";

import {
  connectorActionError,
  connectorDisconnectSuccessMessage,
  IntegrationsControlCenterView
} from "../app/settings/integrations/page";
import {
  buildWorkspaceConnectorCheckPath,
  buildWorkspaceConnectorConfigurationPath,
  buildWorkspaceConnectorControlCenterPath
} from "../lib/api";
import type {
  ConnectorControl,
  ConnectorControlCenterResponse,
  ConnectorProvider
} from "../lib/types";

function connector(
  provider: ConnectorProvider,
  overrides: Partial<ConnectorControl> = {}
): ConnectorControl {
  const names = {
    drive: "Google Drive",
    github: "GitHub",
    gmail: "Gmail",
    jira: "Jira"
  };
  return {
    account_label: null,
    auth_method: null,
    base_url: null,
    configured: false,
    connection_status: null,
    credential_present: false,
    display_name: null,
    last_checked_at: null,
    manage_path: `/${provider}`,
    name: names[provider],
    provider,
    read_check: null,
    read_test_supported: true,
    removable_credential_present: false,
    scopes: [],
    state: "not_configured",
    warnings: [],
    write_check: null,
    write_test_mode: "dry_run",
    ...overrides
  };
}

const controlCenter: ConnectorControlCenterResponse = {
  boundary: {
    external_writes: false,
    provider_calls: false,
    stored_secrets_returned: false,
    write_checks_are_dry_run: true
  },
  connectors: [
    connector("github", {
      account_label: "qtwin-io",
      auth_method: "github_app_installation",
      configured: true,
      connection_status: "connected",
      credential_present: true,
      display_name: "FounderOS GitHub App",
      last_checked_at: "2026-07-23T08:00:00+00:00",
      read_check: {
        account_label: "qtwin-io",
        checked_at: "2026-07-23T08:00:00+00:00",
        code: "read_verified",
        external_write_performed: false,
        message: "Read access verified.",
        provider_call_performed: true,
        records_visible: 7,
        scopes: ["contents"],
        status: "passed"
      },
      removable_credential_present: true,
      scopes: ["contents"],
      state: "read_verified",
      warnings: [
        "A managed GitHub App is recommended; personal tokens are an advanced fallback."
      ]
    }),
    connector("jira", {
      configured: true,
      credential_present: true,
      state: "saved_unverified"
    }),
    connector("gmail", {
      warnings: [
        "Manual OAuth access tokens can expire; automatic OAuth refresh is not implemented yet."
      ]
    }),
    connector("drive")
  ],
  contract: "connector-control.v1",
  summary: {
    configured: 2,
    errors: 0,
    total: 4,
    verified: 1
  },
  workspace_id: "workspace-1"
};

function renderControlCenter(
  canManage = true,
  data: ConnectorControlCenterResponse = controlCenter
): string {
  return renderToStaticMarkup(
    <IntegrationsControlCenterView
      canManage={canManage}
      data={data}
      error={null}
      status="ready"
    />
  );
}

test("builds safe same-origin connector control paths", () => {
  assert.equal(
    buildWorkspaceConnectorControlCenterPath("workspace/with slash"),
    "/api/v1/workspaces/workspace%2Fwith%20slash/connectors/control-center"
  );
  assert.equal(
    buildWorkspaceConnectorConfigurationPath("workspace-1", "jira"),
    "/api/v1/workspaces/workspace-1/connectors/jira/configuration"
  );
  assert.equal(
    buildWorkspaceConnectorCheckPath("workspace-1", "github", "write"),
    "/api/v1/workspaces/workspace-1/connectors/github/checks/write"
  );
});

test("renders one minimal connect-then-check workflow", () => {
  const html = renderControlCenter();

  assert.ok(html.includes("Источники данных"));
  assert.ok(html.includes("1 из 4 работают"));
  assert.ok(html.includes("GitHub"));
  assert.ok(html.includes("Jira"));
  assert.ok(html.includes("Gmail"));
  assert.ok(html.includes("Google Drive"));
  assert.ok(html.includes("Работает"));
  assert.ok(html.includes("GitHub App"));
  assert.ok(html.includes("Подключение работает"));
  assert.ok(html.includes("Проверить ещё раз"));
  assert.ok(html.includes("Дополнительные настройки"));
  assert.ok(html.includes("Проверить готовность записи"));
  assert.ok(html.includes("Удалить резервный token"));
  assert.ok(html.includes("Подтверждаю удаление сохранённого доступа"));
  assert.match(html, /disabled=""[^>]*>Удалить подключение/);
  assert.ok(html.includes("Токен шифруется и больше не показывается в браузере"));
  assert.ok(html.includes("Для постоянной работы лучше использовать GitHub App"));
  assert.doesNotMatch(html, /dry-run|provider payload|ActionProposal|allowlist/);
  assert.doesNotMatch(html, /managed GitHub App is recommended/);
});

test("never renders credential values or internal encrypted fields", () => {
  const html = renderControlCenter();

  assert.doesNotMatch(html, /connector-control-test-token/);
  assert.doesNotMatch(html, /encrypted_access_token/);
  assert.doesNotMatch(html, /fernet:v1/);
  assert.doesNotMatch(html, /installation_id/);
  assert.ok(html.includes('type="password"'));
  assert.ok(html.includes('placeholder="Введите новый токен для замены"'));
});

test("keeps connector configuration read-only for non-admin roles", () => {
  const html = renderControlCenter(false);

  assert.ok(html.includes("Подключения меняет владелец или администратор компании"));
  assert.doesNotMatch(html, /integration-config-form/);
  assert.doesNotMatch(html, /integration-disconnect/);
  assert.match(html, /disabled=""[^>]*>Проверить ещё раз/);
  assert.match(html, /disabled=""[^>]*>Проверить готовность записи/);
});

test("does not mistake a managed GitHub App for a stored PAT fallback", () => {
  const withoutFallback: ConnectorControlCenterResponse = {
    ...controlCenter,
    connectors: controlCenter.connectors.map((item) =>
      item.provider === "github"
        ? { ...item, removable_credential_present: false }
        : item
    )
  };
  const html = renderControlCenter(true, withoutFallback);

  assert.ok(html.includes('placeholder="Вставьте токен"'));
  assert.doesNotMatch(html, /Удалить резервный token/);
});

test("blocks meaningless checks until a connection is saved", () => {
  const unconfigured: ConnectorControlCenterResponse = {
    ...controlCenter,
    connectors: controlCenter.connectors.map((item) =>
      item.provider === "github" ? connector("github") : item
    ),
    summary: { ...controlCenter.summary, configured: 1, verified: 0 }
  };
  const html = renderControlCenter(true, unconfigured);

  assert.ok(html.includes("Станет доступна после сохранения подключения"));
  assert.match(html, /disabled=""[^>]*>Проверить подключение/);
  assert.doesNotMatch(html, /Проверить готовность записи/);
  assert.doesNotMatch(html, /integration-receipt/);
});

test("reports the actual GitHub credential lifecycle after removal", () => {
  assert.equal(
    connectorDisconnectSuccessMessage("github", false),
    "GitHub token удалён. Уже загруженные данные сохранены."
  );
  assert.equal(
    connectorDisconnectSuccessMessage("github", true),
    "Резервный GitHub token удалён. GitHub App продолжает работать."
  );
  assert.equal(
    connectorDisconnectSuccessMessage("jira", false),
    "Подключение удалено. Уже загруженные данные сохранены."
  );
});

test("maps Jira URL errors by exact backend contract, not hostname substrings", () => {
  assert.equal(
    connectorActionError(
      new Error("Jira URL must be an HTTPS *.atlassian.net site without a path")
    ),
    "Укажите адрес Jira Cloud вида https://company.atlassian.net."
  );
  assert.equal(
    connectorActionError(
      new Error("request failed for evil-atlassian.net.example")
    ),
    "Запрос не удался."
  );
});
