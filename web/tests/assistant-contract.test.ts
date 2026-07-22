import assert from "node:assert/strict";
import test from "node:test";

import {
  buildWorkspaceAssistantQueryPath,
  queryWorkspaceAssistant
} from "../lib/api";
import {
  AssistantContractError,
  isSafeAssistantActionTarget,
  isSafeInternalTarget,
  parseAssistantQueryResponse,
  type AssistantQueryResponse
} from "../lib/assistant";

const SNAPSHOT_ID = `hqs1_${"a".repeat(64)}`;

const VALID_RESPONSE: AssistantQueryResponse = {
  contract_version: "assistant.v1",
  intent: "current_priority",
  text: "Главный ход подтверждён текущим снимком.",
  citations: [
    {
      id: "evidence_ref:priority",
      kind: "github_issue",
      source_key: "github",
      label: "GitHub issue #42",
      target: "https://github.com/acme/founderos/issues/42",
      provenance: "canonical_evidence_ref",
      trust: "verified",
      reference_type: "evidence_ref",
      reference_id: "priority",
      workspace_scoped: true
    }
  ],
  suggestions: [
    {
      id: "why",
      label: "Почему этот ход главный?",
      query: "Почему этот ход главный?"
    }
  ],
  action: {
    kind: "navigate",
    label: "Открыть решение",
    target: "/actions?status=proposed",
    enabled: true,
    disabled_reason: null
  },
  snapshot_id: SNAPSHOT_ID,
  as_of: "2026-07-22T10:00:00Z",
  partial: false,
  warnings: [],
  is_live: true,
  llm_used: false
};

test("validates the fixed deterministic assistant contract", () => {
  assert.deepEqual(
    parseAssistantQueryResponse(structuredClone(VALID_RESPONSE)),
    VALID_RESPONSE
  );
  assert.equal(isSafeAssistantActionTarget("/actions?status=proposed"), true);
  assert.equal(isSafeAssistantActionTarget("/actionsevil"), false);
  assert.equal(isSafeAssistantActionTarget("/api/v1/logout"), false);
  assert.equal(isSafeInternalTarget("/company-brain?profile=person-1"), true);
  assert.equal(isSafeInternalTarget("//attacker.test/path"), false);
});

test("fails closed on unknown fields, unsafe links, LLM output, and malformed snapshots", () => {
  const cases: unknown[] = [
    { ...structuredClone(VALID_RESPONSE), private_payload: "must not pass" },
    {
      ...structuredClone(VALID_RESPONSE),
      citations: [{ ...VALID_RESPONSE.citations[0], target: "javascript:alert(1)" }]
    },
    {
      ...structuredClone(VALID_RESPONSE),
      citations: [{ ...VALID_RESPONSE.citations[0], target: "/api/v1/logout" }]
    },
    {
      ...structuredClone(VALID_RESPONSE),
      citations: [
        {
          ...VALID_RESPONSE.citations[0],
          target: "https://example.test/evidence?access-token=secret"
        }
      ]
    },
    {
      ...structuredClone(VALID_RESPONSE),
      action: { ...VALID_RESPONSE.action, target: "/api/v1/logout" }
    },
    { ...structuredClone(VALID_RESPONSE), llm_used: true },
    { ...structuredClone(VALID_RESPONSE), snapshot_id: "hqs1_not-content-addressed" }
  ];

  for (const malformed of cases) {
    assert.throws(
      () => parseAssistantQueryResponse(malformed),
      (error: unknown) => error instanceof AssistantContractError
    );
  }
});

test("posts only the bounded query and expected visible snapshot with session auth", async () => {
  const originalFetch = globalThis.fetch;
  const controller = new AbortController();
  let requestCount = 0;
  globalThis.fetch = (async (input, init) => {
    requestCount += 1;
    assert.equal(
      String(input),
      "http://localhost/api/v1/workspaces/workspace%2Fwith%20slash/assistant/query"
    );
    assert.equal(init?.method, "POST");
    assert.equal(init?.credentials, "include");
    assert.equal(init?.signal, controller.signal);
    assert.deepEqual(JSON.parse(String(init?.body)), {
      query: "Какой сейчас главный приоритет?",
      expected_snapshot_id: SNAPSHOT_ID
    });
    const headers = new Headers(init?.headers);
    assert.equal(headers.get("Accept"), "application/json");
    assert.equal(headers.get("Content-Type"), "application/json");
    assert.equal(headers.has("X-FounderOS-API-Key"), false);
    return new Response(JSON.stringify(VALID_RESPONSE), {
      status: 200,
      headers: { "Content-Type": "application/json" }
    });
  }) as typeof fetch;

  try {
    assert.equal(
      buildWorkspaceAssistantQueryPath("workspace/with slash"),
      "/api/v1/workspaces/workspace%2Fwith%20slash/assistant/query"
    );
    assert.deepEqual(
      await queryWorkspaceAssistant(
        "workspace/with slash",
        {
          query: "Какой сейчас главный приоритет?",
          expected_snapshot_id: SNAPSHOT_ID
        },
        { signal: controller.signal }
      ),
      VALID_RESPONSE
    );
    assert.equal(requestCount, 1);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
