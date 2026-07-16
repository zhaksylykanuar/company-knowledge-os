import assert from "node:assert/strict";
import test from "node:test";

import { renderToStaticMarkup } from "react-dom/server";

import {
  HeadquartersDashboardView,
  reduceHeadquartersLoadState
} from "../components/HeadquartersDashboard";
import type { HeadquartersSnapshotResponse } from "../lib/headquarters";
import { makeHeadquartersFixture } from "./fixtures/headquarters";

function renderReady(snapshot: HeadquartersSnapshotResponse): string {
  return renderToStaticMarkup(
    <HeadquartersDashboardView
      snapshot={snapshot}
      status="ready"
      workspaceName={snapshot.workspace.name}
    />
  );
}

test("renders one real priority, fixed pulse order, and backend actions", () => {
  const html = renderReady(makeHeadquartersFixture());

  assert.ok(html.includes("Acme Systems"));
  assert.ok(html.includes("Подтвердить план запуска Atlas"));
  assert.equal((html.match(/Проверить решение/g) ?? []).length, 1);
  assert.match(
    html,
    /href="\/actions\?proposal=11111111-1111-4111-8111-111111111111&amp;status=proposed"/
  );

  const waitingDecisions = html.indexOf("Ждут решения");
  const sourcesAttention = html.indexOf("Источники требуют внимания");
  const pendingRelationships = html.indexOf("Связи ждут проверки");
  assert.ok(waitingDecisions >= 0);
  assert.ok(waitingDecisions < sourcesAttention);
  assert.ok(sourcesAttention < pendingRelationships);

  assert.ok(html.includes("Проверить связь с заказчиком Atlas"));
  assert.ok(html.includes("GitHub"));
  assert.doesNotMatch(html, /<main/);
  assert.doesNotMatch(html, /Демо-данные|NovaFlow|Доброе утро, Алина|DEMO-MISSION/);
});

test("renders a calm state without inventing a priority", () => {
  const snapshot = makeHeadquartersFixture((fixture) => {
    fixture.priority = null;
    fixture.onboarding.next_action = {
      kind: "create_briefing",
      label: "Собрать первую сводку",
      target: "/briefings",
      enabled: true,
      disabled_reason: null
    };
  });
  const html = renderReady(snapshot);

  assert.ok(html.includes("Подтверждённых приоритетов сейчас нет"));
  assert.ok(html.includes("Собрать первую сводку"));
  assert.match(html, /href="\/briefings"/);
  assert.doesNotMatch(html, /Подтвердить план запуска Atlas/);
});

test("keeps a disabled mission non-clickable and explains the role boundary", () => {
  const snapshot = makeHeadquartersFixture((fixture) => {
    fixture.workspace.role = "viewer";
    fixture.priority!.action = {
      ...fixture.priority!.action,
      enabled: false,
      disabled_reason: "Недостаточно прав для принятия решения"
    };
    fixture.changes.items = [];
    for (const key of Object.keys(fixture.capabilities) as Array<
      keyof typeof fixture.capabilities
    >) {
      fixture.capabilities[key] = false;
    }
  });
  const html = renderReady(snapshot);

  assert.ok(html.includes("Проверить решение"));
  assert.ok(html.includes("Недостаточно прав для принятия решения"));
  assert.doesNotMatch(
    html,
    /href="\/actions\?proposal=11111111-1111-4111-8111-111111111111&amp;status=proposed"/
  );
});

test("does not invent an action when the backend enables it without a target", () => {
  const snapshot = makeHeadquartersFixture((fixture) => {
    fixture.priority!.action = {
      kind: "review_proposal",
      label: "Проверить решение",
      target: null,
      enabled: true,
      disabled_reason: null
    };
  });
  const html = renderReady(snapshot);

  assert.match(
    html,
    /<button class="headquarters-primary-action" disabled="" type="button"><span>Проверить решение/
  );
  assert.doesNotMatch(
    html,
    /<a class="headquarters-primary-action"[^>]*><span>Проверить решение/
  );
});

test("keeps verified priority visible while reporting partial and stale source truth", () => {
  const snapshot = makeHeadquartersFixture((fixture) => {
    fixture.snapshot.partial = true;
    fixture.snapshot.warnings = ["Часть данных источников временно недоступна"];
    fixture.snapshot.coverage[1] = {
      ...fixture.snapshot.coverage[1],
      status: "partial",
      watermark: "sources-partial-1",
      warning: "Покрытие GitHub рассчитано не полностью"
    };
    fixture.sources.healthy = 0;
    fixture.sources.attention_count = 1;
    fixture.pulse[1].value = 1;
    fixture.sources.items[0] = {
      ...fixture.sources.items[0]!,
      freshness: "stale",
      primary_state: "stale",
      attention_reason: "GitHub не обновлялся больше часа",
      fresh_until: "2026-07-16T09:00:00Z"
    };
  });
  const html = renderReady(snapshot);

  assert.ok(html.includes("Подтвердить план запуска Atlas"));
  assert.ok(html.includes("Картина собрана частично"));
  assert.ok(html.includes("Нужно проверить: 1"));
  assert.ok(html.includes("Что недоступно"));
  assert.doesNotMatch(html, /sources-partial-1|safe_debug_id/);
  assert.doesNotMatch(html, /Все данные подтверждены|Все источники в порядке/);
});

test("never turns an unknown signal timestamp into current recency", () => {
  const snapshot = makeHeadquartersFixture((fixture) => {
    fixture.changes.items[0]!.occurred_at = null;
  });
  const html = renderReady(snapshot);

  assert.ok(html.includes("Дата не подтверждена"));
  assert.doesNotMatch(html, /<time[^>]*>сейчас<\/time>/);
});

test("ignores a late response from the previous workspace request", () => {
  const started = reduceHeadquartersLoadState(
    { requestId: 1, snapshot: null, status: "loading", workspaceId: "workspace-a" },
    { requestId: 2, type: "start", workspaceId: "workspace-b" }
  );
  const lateSnapshot = makeHeadquartersFixture((fixture) => {
    fixture.workspace.id = "workspace-a";
  });
  const afterLateResponse = reduceHeadquartersLoadState(started, {
    requestId: 1,
    snapshot: lateSnapshot,
    type: "success",
    workspaceId: "workspace-a"
  });

  assert.equal(afterLateResponse, started);
  assert.equal(afterLateResponse.status, "loading");
  assert.equal(afterLateResponse.workspaceId, "workspace-b");
});

test("renders explicit loading, missing, forbidden, offline, contract, and generic states", () => {
  const cases = [
    ["loading", "Штаб просыпается"],
    ["missing", "Нужна компания"],
    ["forbidden", "Доступ закрыт"],
    ["offline", "Нет связи с системой"],
    ["contract_error", "Картина не подтверждена"],
    ["error", "Штаб временно недоступен"]
  ] as const;

  for (const [status, title] of cases) {
    const html = renderToStaticMarkup(
      <HeadquartersDashboardView
        onRetry={() => undefined}
        snapshot={null}
        status={status}
        workspaceName="Acme Systems"
      />
    );
    assert.ok(html.includes(title));
    assert.ok(html.includes("Acme Systems"));
    if (status === "forbidden") {
      assert.doesNotMatch(html, /Повторить/);
    }
  }
});
