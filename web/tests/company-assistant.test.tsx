import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

import { renderToStaticMarkup } from "react-dom/server";

import {
  canOpenCompanyAssistantShortcut,
  CompanyAssistantPanel,
  companyAssistantErrorStatus
} from "../components/CompanyAssistant";
import type { AssistantQueryResponse } from "../lib/assistant";
import { assistantSnapshotForWorkspace } from "../lib/assistant-snapshot";
import { ApiRequestError } from "../lib/api";
import { makeHeadquartersFixture } from "./fixtures/headquarters";

const ANSWER: AssistantQueryResponse = {
  contract_version: "assistant.v2",
  intent: "action_request",
  text: "Я не выполняю действия сам. Подтвердите решение лично.",
  citations: [
    {
      id: "evidence_ref:decision",
      kind: "github_issue",
      source_key: "github",
      label: "Решение #42",
      target: "https://github.com/acme/founderos/issues/42",
      provenance: "canonical_evidence_ref",
      trust: "verified",
      reference_type: "evidence_ref",
      reference_id: "decision",
      workspace_scoped: true
    }
  ],
  perspectives: {
    fact: {
      text: "Я не выполняю действия сам. Подтвердите решение лично.",
      citation_ids: ["evidence_ref:decision"]
    },
    interpretation: { text: null, citation_ids: [] },
    objection: { text: null, citation_ids: [] },
    recommendation: { text: null, citation_ids: [] }
  },
  suggestions: [
    {
      id: "sources",
      label: "Что с источниками?",
      query: "Что с источниками?"
    }
  ],
  action: {
    kind: "navigate",
    label: "Открыть подтверждение",
    target: "/actions?status=proposed",
    enabled: true,
    disabled_reason: null
  },
  snapshot_id: `hqs1_${"b".repeat(64)}`,
  as_of: "2026-07-22T10:00:00Z",
  partial: true,
  warnings: ["company_world_temporarily_unavailable"],
  is_live: true,
  llm_used: false,
  validation_status: "deterministic"
};

function renderPanel(
  overrides: Partial<Parameters<typeof CompanyAssistantPanel>[0]> = {}
): string {
  return renderToStaticMarkup(
    <CompanyAssistantPanel
      answer={ANSWER}
      error={null}
      onAction={() => undefined}
      onQueryChange={() => undefined}
      onSubmit={() => undefined}
      onSuggestion={() => undefined}
      query="Сделай сам"
      status="answer"
      {...overrides}
    />
  );
}

test("renders evidence, safe confirmation navigation, warnings, and read-only boundary", () => {
  const html = renderPanel();

  assert.ok(html.includes("Я не выполняю действия сам"));
  assert.ok(html.includes("Решение #42 · проверено"));
  assert.match(html, /href="https:\/\/github\.com\/acme\/founderos\/issues\/42"/);
  assert.match(html, /href="\/actions\?status=proposed"/);
  assert.ok(html.includes("Открыть подтверждение"));
  assert.ok(html.includes("только чтение"));
  assert.ok(html.includes("действий не выполнено"));
  assert.ok(html.includes("Факт"));
  assert.ok(html.includes("Интерпретация"));
  assert.ok(html.includes("Возражение"));
  assert.ok(html.includes("Рекомендация"));
  assert.ok(html.includes("без генерации"));
  assert.ok(html.includes("Ограничения снимка (1)"));
  assert.ok(html.includes("Что с источниками?"));
});

test("renders loading, stale, and rate-limit states without a stale answer", () => {
  const loading = renderPanel({ answer: null, query: "", status: "loading_snapshot" });
  const stale = renderPanel({
    answer: null,
    error: "Картина компании изменилась. Повторите вопрос.",
    status: "stale"
  });
  const limited = renderPanel({
    answer: null,
    error: "Слишком много вопросов подряд.",
    status: "rate_limited"
  });

  assert.ok(loading.includes("Сверяю текущую картину компании"));
  assert.ok(loading.includes("disabled=\"\""));
  assert.ok(stale.includes("Картина компании изменилась"));
  assert.equal(stale.includes(ANSWER.text), false);
  assert.ok(limited.includes("Слишком много вопросов подряд"));
});

test("maps stale and rate-limit responses explicitly and guards the global shortcut", () => {
  assert.equal(companyAssistantErrorStatus(new ApiRequestError("stale", 409)), "stale");
  assert.equal(
    companyAssistantErrorStatus(new ApiRequestError("limited", 429)),
    "rate_limited"
  );
  assert.equal(companyAssistantErrorStatus(new Error("failed")), "error");
  assert.equal(
    canOpenCompanyAssistantShortcut({ disabled: false, hasOpenDialog: false, target: null }),
    true
  );
  assert.equal(
    canOpenCompanyAssistantShortcut({ disabled: true, hasOpenDialog: false, target: null }),
    false
  );
  assert.equal(
    canOpenCompanyAssistantShortcut({ disabled: false, hasOpenDialog: true, target: null }),
    false
  );
});

test("uses the exact dashboard snapshot only for its matching workspace", () => {
  const snapshot = makeHeadquartersFixture();
  const source = {
    workspaceId: snapshot.workspace.id,
    snapshot,
    refresh: async () => snapshot
  };

  assert.equal(
    assistantSnapshotForWorkspace(source, snapshot.workspace.id),
    snapshot
  );
  assert.equal(assistantSnapshotForWorkspace(source, "another-workspace"), null);
  assert.equal(assistantSnapshotForWorkspace(null, snapshot.workspace.id), null);
});

test("mounts one launcher in the authenticated shell and none inside Headquarters", () => {
  const authGateSource = readFileSync(
    resolve(process.cwd(), "components/AuthGate.tsx"),
    "utf8"
  );
  const dashboardSource = readFileSync(
    resolve(process.cwd(), "components/HeadquartersDashboard.tsx"),
    "utf8"
  );

  assert.equal((authGateSource.match(/<CompanyAssistant\b/g) ?? []).length, 1);
  assert.equal(dashboardSource.includes("<CompanyAssistant"), false);
  assert.equal(dashboardSource.includes("headquarters-assistant-launcher"), false);
});
