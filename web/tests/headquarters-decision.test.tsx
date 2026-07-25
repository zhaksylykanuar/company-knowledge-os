import assert from "node:assert/strict";
import test from "node:test";

import { createRef, type ComponentProps } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import {
  decisionStatusAfterSubmitFailure,
  HeadquartersDecisionContent,
  HeadquartersDecisionModal,
  resolveLocalDecisionAttempt
} from "../components/HeadquartersDecisionModal";
import { LocalActionDecisionContractError } from "../lib/action-proposal-decision";
import { ApiRequestError } from "../lib/api";
import type { HeadquartersMission } from "../lib/headquarters";
import type {
  ActionProposal,
  LocalActionDecisionReceipt
} from "../lib/types";
import { makeHeadquartersFixture } from "./fixtures/headquarters";

type DecisionContentProps = ComponentProps<typeof HeadquartersDecisionContent>;

function missionFixture(): HeadquartersMission {
  const mission = structuredClone(makeHeadquartersFixture().priority);
  if (!mission) {
    throw new Error("Headquarters fixture must include a priority mission");
  }
  return mission;
}

function proposalFixture(
  overrides: Partial<ActionProposal> = {}
): ActionProposal {
  const mission = missionFixture();
  return {
    id: mission.proposal_id ?? "proposal-1",
    workspace_id: "workspace-1",
    briefing_item_id: null,
    target_provider: "github",
    action_type: "create_github_issue",
    title: mission.title,
    description: mission.summary,
    payload: {},
    status: "proposed",
    evidence_refs: [],
    created_by: "user",
    created_by_user_id: "user-1",
    approved_by_user_id: null,
    approved_at: null,
    rejected_by_user_id: null,
    rejected_at: null,
    rejection_reason: null,
    created_at: "2026-07-17T08:00:00Z",
    updated_at: "2026-07-17T08:00:00Z",
    proposal_version: mission.proposal_version ?? "proposal-version-1",
    is_live: false,
    execution_started: false,
    warnings: [],
    ...overrides
  };
}

function renderDecisionContent(
  overrides: Partial<DecisionContentProps> = {}
): string {
  const props: DecisionContentProps = {
    canReview: true,
    error: null,
    mission: missionFixture(),
    pending: false,
    proposal: proposalFixture(),
    receipt: null,
    refetchStatus: "idle",
    status: "ready",
    ...overrides
  };
  return renderToStaticMarkup(<HeadquartersDecisionContent {...props} />);
}

test("decision modal starts in an exact loading state", () => {
  const snapshot = makeHeadquartersFixture();
  const mission = snapshot.priority;
  assert.ok(mission);

  const html = renderToStaticMarkup(
    <HeadquartersDecisionModal
      backgroundRef={createRef<HTMLElement>()}
      mission={mission}
      onClose={() => undefined}
      onRefetch={async () => snapshot}
      snapshot={snapshot}
    />
  );

  assert.match(html, /role="dialog"/);
  assert.ok(html.includes("Решение по ситуации"));
  assert.match(html, /aria-busy="true"/);
  assert.ok(html.includes("Проверяем точное решение…"));
  assert.doesNotMatch(html, /Принять локально|Отклонить/);
});

test("read-only decision explains authority and keeps external execution separate", () => {
  const html = renderDecisionContent({ canReview: false });

  assert.ok(html.includes("Только просмотр"));
  assert.ok(
    html.includes("Решение может принять администратор или владелец компании.")
  );
  assert.ok(
    html.includes(
      "Сейчас сохранится только решение. Любое внешнее действие остаётся отдельным шагом вне этого окна."
    )
  );
  assert.doesNotMatch(html, />Принять локально<|>Отклонить</);
});

test("stale decision falls back to the exact proposal history", () => {
  const mission = missionFixture();
  mission.proposal_id = "proposal/id?scope=one";
  const html = renderDecisionContent({
    error: "Решение изменилось после формирования этого снимка.",
    mission,
    proposal: null,
    status: "stale"
  });

  assert.ok(html.includes("Решение изменилось после формирования этого снимка."));
  assert.match(
    html,
    /href="\/actions\?proposal=proposal%2Fid%3Fscope%3Done"/
  );
  assert.ok(html.includes("Открыть точную историю"));
  assert.doesNotMatch(html, />Принять локально<|>Отклонить</);
});

test("manual retry of the same decision preserves its idempotency key", () => {
  const current = {
    decision: "approved" as const,
    idempotencyKey: "stable-manual-retry-key"
  };
  const repeated = resolveLocalDecisionAttempt(
    current,
    "approved",
    "proposal-1"
  );

  assert.equal(repeated, current);
  assert.equal(repeated.idempotencyKey, "stable-manual-retry-key");

  const changedDecision = resolveLocalDecisionAttempt(
    current,
    "rejected",
    "proposal-1"
  );
  assert.equal(changedDecision.decision, "rejected");
  assert.notEqual(changedDecision.idempotencyKey, current.idempotencyKey);
  assert.match(changedDecision.idempotencyKey, /^hq-local-rejected-proposal-1-/);
});

test("403, 404, 409, and contract failures leave the modal fail-closed", () => {
  const failures: Array<{ error: unknown; status: "error" | "stale" }> = [
    { error: new ApiRequestError("forbidden", 403), status: "error" },
    { error: new ApiRequestError("missing", 404), status: "error" },
    { error: new ApiRequestError("stale", 409), status: "stale" },
    {
      error: new LocalActionDecisionContractError("receipt mismatch", "response"),
      status: "error"
    }
  ];

  for (const failure of failures) {
    const status = decisionStatusAfterSubmitFailure(failure.error);
    assert.equal(status, failure.status);
    const html = renderDecisionContent({
      error: "Сохранение решения заблокировано.",
      status
    });
    assert.ok(html.includes("Сохранение решения заблокировано."));
    assert.ok(html.includes("Открыть точную историю"));
    assert.doesNotMatch(html, />Принять локально<|>Отклонить</);
  }
});

test("network and 5xx exhaustion keep the modal ready for a manual retry", () => {
  const failures = [
    new TypeError("network connection closed"),
    new ApiRequestError("temporarily unavailable", 503)
  ];

  for (const failure of failures) {
    const status = decisionStatusAfterSubmitFailure(failure);
    assert.equal(status, "ready");
    const html = renderDecisionContent({
      error: "Автоматический повтор не подтвердил результат.",
      status
    });
    assert.ok(html.includes("Автоматический повтор не подтвердил результат."));
    assert.ok(html.includes("Принять локально"));
    assert.ok(html.includes("Отклонить"));
    assert.doesNotMatch(html, /Открыть точную историю/);
  }
});

test("saved receipt remains visible when headquarters refetch fails", () => {
  const receipt: LocalActionDecisionReceipt = {
    receipt_id: "receipt-1234567890-cdef",
    proposal_id: "proposal-1",
    decision: "approved",
    recorded_at: "2026-07-17T09:30:00Z",
    replayed: false,
    external_write_performed: false,
    proposal_version: "proposal-version-1"
  };
  const html = renderDecisionContent({
    proposal: proposalFixture({ status: "approved" }),
    receipt,
    refetchStatus: "failed",
    status: "receipt"
  });

  assert.ok(html.includes("Локальная квитанция сохранена"));
  assert.ok(html.includes("Решение: Принято"));
  assert.ok(html.includes("receipt-…cdef"));
  assert.ok(
    html.includes("Квитанция сохранена, но новый снимок пока не загрузился.")
  );
  assert.ok(html.includes("Повторить обновление"));
  assert.ok(html.includes("Вернуться в FounderOS"));
  assert.ok(
    html.includes("Во внешние сервисы ничего не отправлялось.")
  );
  assert.match(html, /<dt>Внешняя запись<\/dt><dd>Нет<\/dd>/);
  assert.doesNotMatch(html, /FounderOS обновлён и пересчитал следующий ход/);
});
