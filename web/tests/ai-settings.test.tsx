import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

import {
  aiSettingsReadiness,
  canCheckAISettings,
  modelLabel
} from "../app/settings/ai/page";
import {
  applyWorkspaceAISettings,
  buildWorkspaceAISettingsPath,
  checkWorkspaceAIConnection,
  fetchWorkspaceAISettings,
  removeWorkspaceAICredential
} from "../lib/api";
import type { AISettings } from "../lib/types";

const SETTINGS: AISettings = {
  contract: "ai-settings.v1",
  workspace_id: "workspace-1",
  provider: "openai",
  configured: true,
  enabled: true,
  server_permitted: true,
  model: "gpt-5.6",
  supported_models: [
    "gpt-5.6",
    "gpt-5.6-sol",
    "gpt-5.6-terra",
    "gpt-5.6-luna"
  ],
  reasoning_effort: "medium",
  max_output_tokens: 1_200,
  configuration_version: 2,
  key_present: true,
  data_policy: {
    version: "openai-api-data-controls-2026-07-29",
    acknowledged: true,
    acknowledged_at: "2026-07-29T10:00:00Z",
    notice_code: "provider_retention_may_apply"
  },
  last_check: {
    status: "passed",
    code: "connection_verified",
    checked_at: "2026-07-29T10:01:00Z",
    model: "gpt-5.6",
    provider_call_performed: true
  },
  boundary: {
    provider_call_on_apply: false,
    company_data_sent_during_check: false,
    stored_secret_returned: false,
    chat_persisted: false,
    external_writes: false
  }
};

test("builds workspace-scoped AI settings requests without browser auth secrets", async () => {
  const originalFetch = globalThis.fetch;
  const requests: Array<{ method: string; url: string; body: unknown }> = [];
  globalThis.fetch = (async (input, init) => {
    requests.push({
      method: init?.method ?? "GET",
      url: String(input),
      body: init?.body ? JSON.parse(String(init.body)) : null
    });
    const headers = new Headers(init?.headers);
    assert.equal(init?.credentials, "include");
    assert.equal(headers.has("X-FounderOS-API-Key"), false);
    const response =
      String(input).endsWith("/check")
        ? {
            status: "passed",
            code: "connection_verified",
            message: "Connection verified.",
            checked_at: "2026-07-29T10:01:00Z",
            model: "gpt-5.6",
            provider_call_performed: true,
            company_data_sent: false,
            external_write_performed: false
          }
        : SETTINGS;
    return new Response(JSON.stringify(response), {
      status: 200,
      headers: { "Content-Type": "application/json" }
    });
  }) as typeof fetch;

  try {
    assert.equal(
      buildWorkspaceAISettingsPath("workspace/with space"),
      "/api/v1/workspaces/workspace%2Fwith%20space/ai-settings"
    );
    await fetchWorkspaceAISettings("workspace/with space");
    await applyWorkspaceAISettings("workspace/with space", {
      enabled: false,
      data_policy_acknowledged: true,
      model: "gpt-5.6-terra",
      reasoning_effort: "low",
      max_output_tokens: 900
    });
    await checkWorkspaceAIConnection("workspace/with space");
    await removeWorkspaceAICredential("workspace/with space");
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.deepEqual(
    requests.map((request) => [request.method, new URL(request.url).pathname]),
    [
      ["GET", "/api/v1/workspaces/workspace%2Fwith%20space/ai-settings"],
      [
        "POST",
        "/api/v1/workspaces/workspace%2Fwith%20space/ai-settings/configuration"
      ],
      ["POST", "/api/v1/workspaces/workspace%2Fwith%20space/ai-settings/check"],
      [
        "DELETE",
        "/api/v1/workspaces/workspace%2Fwith%20space/ai-settings/configuration"
      ]
    ]
  );
  assert.deepEqual(requests[1]?.body, {
    enabled: false,
    data_policy_acknowledged: true,
    model: "gpt-5.6-terra",
    reasoning_effort: "low",
    max_output_tokens: 900
  });
});

test("derives honest readiness and requires every check gate", () => {
  assert.deepEqual(aiSettingsReadiness(SETTINGS), {
    key: "Сохранён",
    check: "Работает",
    activation: "Включены"
  });
  assert.equal(
    canCheckAISettings({
      acknowledged: true,
      canManage: true,
      keyPresent: true,
      pending: false,
      serverPermitted: true
    }),
    true
  );
  for (const field of [
    "acknowledged",
    "canManage",
    "keyPresent",
    "serverPermitted"
  ] as const) {
    const gates = {
      acknowledged: true,
      canManage: true,
      keyPresent: true,
      pending: false,
      serverPermitted: true,
      [field]: false
    };
    assert.equal(canCheckAISettings(gates), false);
  }
  assert.equal(
    canCheckAISettings({
      acknowledged: true,
      canManage: true,
      keyPresent: true,
      pending: true,
      serverPermitted: true
    }),
    false
  );
  assert.equal(modelLabel("gpt-5.6-terra"), "GPT-5.6 Terra · баланс");
});

test("keeps the credential masked and makes privacy and removal explicit", () => {
  const source = readFileSync(
    resolve(process.cwd(), "app/settings/ai/page.tsx"),
    "utf8"
  );

  assert.ok(source.includes('type="password"'));
  assert.ok(source.includes("store=false"));
  assert.ok(source.includes("Zero Data"));
  assert.ok(source.includes("Данные компании не отправлялись"));
  assert.ok(source.includes("Подтвердить удаление"));
  assert.equal(source.includes("settings.api_key"), false);
});
