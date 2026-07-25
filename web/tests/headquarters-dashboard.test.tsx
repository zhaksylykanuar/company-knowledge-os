import assert from "node:assert/strict";
import test from "node:test";

import { renderToStaticMarkup } from "react-dom/server";

import {
  HeadquartersDashboardView,
  onboardingIntentFromSearch,
  reduceHeadquartersOnboardingIntent,
  resolveVisibleHeadquartersOverlay,
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

function pendingOnboardingSnapshot(
  state: "pending" | "unknown" = "pending"
): HeadquartersSnapshotResponse {
  return makeHeadquartersFixture((fixture) => {
    const step = fixture.onboarding.steps[2];
    assert.equal(step?.key, "canonical_data");
    if (!step) return;
    step.state = state;
    step.evidence[0] = {
      ...step.evidence[0]!,
      state,
      value: state === "unknown" ? null : 0,
      precision: state === "unknown" ? "unavailable" : "exact"
    };
    step.action = {
      kind: "import_source_data",
      label: "Получить первые данные",
      target: "/settings/integrations",
      enabled: true,
      disabled_reason: null
    };
    fixture.onboarding.ready = false;
    fixture.onboarding.completed_count = 4;
    fixture.onboarding.completed_required = 2;
    fixture.onboarding.current_step_key = "canonical_data";
    fixture.onboarding.next_action = structuredClone(step.action);
  });
}

test("renders one real priority, fixed pulse order, and backend actions", () => {
  const html = renderReady(makeHeadquartersFixture());

  assert.ok(html.includes("Acme Systems"));
  assert.ok(html.includes("Подтвердить план запуска Atlas"));
  assert.equal((html.match(/Открыть решение/g) ?? []).length, 1);
  assert.match(
    html,
    /<button class="headquarters-primary-action" type="button"><span>Открыть решение<\/span>/
  );
  assert.doesNotMatch(
    html,
    /<a class="headquarters-primary-action" href="\/actions\?proposal=11111111-1111-4111-8111-111111111111/
  );

  const waitingDecisions = html.indexOf('data-key="waiting_decisions"');
  const sourcesAttention = html.indexOf('data-key="sources_attention"');
  const pendingRelationships = html.indexOf('data-key="pending_relationships"');
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
  });
  const html = renderReady(snapshot);

  assert.ok(html.includes("Подтверждённых приоритетов сейчас нет"));
  assert.doesNotMatch(html, /Подтвердить план запуска Atlas/);
});

test("auto-opens one compact modal for the server-provided required blocker", () => {
  const snapshot = pendingOnboardingSnapshot();
  const html = renderReady(snapshot);

  assert.equal((html.match(/role="dialog"/g) ?? []).length, 1);
  assert.ok(html.includes("Запуск компании"));
  assert.ok(html.includes("Готово 2 из 3 обязательных"));
  assert.ok(html.includes("Первые данные подтверждены"));
  assert.ok(html.includes("FounderOS видит подтверждённые факты"));
  assert.ok(html.includes("Получить первые данные"));
  assert.ok(html.includes("Галочка появляется только после серверной проверки"));
  assert.equal(
    (html.match(/aria-label="(?:Компания|Источник|Факты|Контекст):/g) ?? [])
      .length,
    4
  );
  assert.doesNotMatch(html, /Отметить выполненным|Пропустить и завершить/);
});

test("keeps an unknown required step unresolved and offers a read-only retry", () => {
  const snapshot = pendingOnboardingSnapshot("unknown");
  const html = renderToStaticMarkup(
    <HeadquartersDashboardView
      onRetry={() => undefined}
      snapshot={snapshot}
      status="ready"
      workspaceName={snapshot.workspace.name}
    />
  );

  assert.ok(html.includes("Состояние пока неизвестно"));
  assert.ok(html.includes("Проверить снова"));
  assert.ok(html.includes("Не удалось подтвердить"));
  assert.doesNotMatch(html, /Обязательные шаги завершены|FounderOS готов к работе/);
});

test("explains the administrator path when an unknown step is read-only", () => {
  const snapshot = pendingOnboardingSnapshot("unknown");
  const step = snapshot.onboarding.steps[2];
  assert.equal(step?.key, "canonical_data");
  if (!step) return;
  step.action.enabled = false;
  step.action.disabled_reason = "Импорт запускает администратор или владелец.";
  snapshot.onboarding.next_action = structuredClone(step.action);
  snapshot.workspace.role = "viewer";
  const html = renderToStaticMarkup(
    <HeadquartersDashboardView
      onRetry={() => undefined}
      snapshot={snapshot}
      status="ready"
      workspaceName={snapshot.workspace.name}
    />
  );

  assert.ok(html.includes("Проверить снова"));
  assert.ok(html.includes("Импорт запускает администратор или владелец."));
  assert.doesNotMatch(html, /href="\/connectors"/);
});

test("shows a disabled server action and role reason without inventing a link", () => {
  const snapshot = pendingOnboardingSnapshot();
  const step = snapshot.onboarding.steps[2];
  assert.equal(step?.key, "canonical_data");
  if (!step) return;
  step.action.enabled = false;
  step.action.disabled_reason = "Импорт запускает администратор или владелец.";
  snapshot.onboarding.next_action = structuredClone(step.action);
  snapshot.workspace.role = "viewer";
  const parsed = makeHeadquartersFixture((fixture) => Object.assign(fixture, snapshot));
  const html = renderReady(parsed);

  assert.ok(html.includes("Импорт запускает администратор или владелец."));
  assert.match(html, /<button class="headquarters-primary-action" disabled=""/);
  assert.doesNotMatch(
    html,
    /<a class="headquarters-primary-action" href="\/connectors"><span>Получить первые данные/
  );
});

test("ready onboarding stays quiet unless the route explicitly requests its completion view", () => {
  const snapshot = makeHeadquartersFixture();
  const ordinary = renderReady(snapshot);
  const requested = renderToStaticMarkup(
    <HeadquartersDashboardView
      onboardingIntent
      snapshot={snapshot}
      status="ready"
      workspaceName={snapshot.workspace.name}
    />
  );

  assert.doesNotMatch(ordinary, /role="dialog"/);
  assert.equal((requested.match(/role="dialog"/g) ?? []).length, 1);
  assert.ok(requested.includes("FounderOS готов к работе"));
  assert.ok(requested.includes("Открыть текущую картину"));
});

test("onboarding has overlay priority until dismissed for the exact snapshot", () => {
  const snapshot = pendingOnboardingSnapshot();
  const coverage = { kind: "coverage" } as const;

  assert.equal(
    resolveVisibleHeadquartersOverlay({
      dismissedOnboardingSnapshotId: null,
      onboardingIntent: false,
      requestedOverlay: coverage,
      snapshot
    })?.kind,
    "onboarding"
  );
  assert.equal(
    resolveVisibleHeadquartersOverlay({
      dismissedOnboardingSnapshotId: snapshot.snapshot.id,
      onboardingIntent: false,
      requestedOverlay: coverage,
      snapshot
    })?.kind,
    "coverage"
  );

  const refreshed = structuredClone(snapshot);
  refreshed.snapshot.id = `${snapshot.snapshot.id}-next`;
  assert.equal(
    resolveVisibleHeadquartersOverlay({
      dismissedOnboardingSnapshotId: snapshot.snapshot.id,
      onboardingIntent: false,
      requestedOverlay: coverage,
      snapshot: refreshed
    })?.kind,
    "onboarding"
  );
});

test("recognizes only an explicit onboarding route intent", () => {
  assert.equal(onboardingIntentFromSearch("?onboarding=1"), true);
  assert.equal(onboardingIntentFromSearch("?onboarding=0"), false);
  assert.equal(onboardingIntentFromSearch("?mode=onboarding"), false);
  assert.equal(onboardingIntentFromSearch(""), false);
});

test("a dismissed route intent stays consumed when the workspace changes", () => {
  let state = reduceHeadquartersOnboardingIntent(false, {
    search: "?onboarding=1",
    type: "location"
  });
  assert.equal(state, true);
  state = reduceHeadquartersOnboardingIntent(state, { type: "dismiss" });
  assert.equal(state, false);
  state = reduceHeadquartersOnboardingIntent(state, { type: "workspace_changed" });
  assert.equal(state, false);

  state = reduceHeadquartersOnboardingIntent(state, {
    search: "?onboarding=1",
    type: "location"
  });
  assert.equal(state, true);
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

  assert.ok(html.includes("Открыть решение"));
  assert.ok(html.includes("Недостаточно прав для принятия решения"));
  assert.doesNotMatch(
    html,
    /<a class="headquarters-primary-action" href="\/actions\?proposal=11111111-1111-4111-8111-111111111111/
  );
});

test("does not invent an action when the backend enables it without a target", () => {
  const snapshot = makeHeadquartersFixture((fixture) => {
    fixture.priority!.proposal_id = null;
    fixture.priority!.proposal_version = null;
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
  assert.ok(html.includes("Требуют внимания: 1"));
  assert.ok(html.includes("Что пока неизвестно"));
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
    {
      refreshError: false,
      refreshing: false,
      requestId: 1,
      snapshot: null,
      status: "loading",
      workspaceId: "workspace-a"
    },
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

test("preserves the current snapshot throughout refresh and refresh failure", () => {
  const snapshot = makeHeadquartersFixture();
  const current = {
    refreshError: false,
    refreshing: false,
    requestId: 1,
    snapshot,
    status: "ready" as const,
    workspaceId: snapshot.workspace.id
  };

  const refreshing = reduceHeadquartersLoadState(current, {
    requestId: 2,
    type: "refresh_start",
    workspaceId: snapshot.workspace.id
  });
  assert.equal(refreshing.status, "ready");
  assert.equal(refreshing.refreshing, true);
  assert.equal(refreshing.refreshError, false);
  assert.equal(refreshing.snapshot, snapshot);

  const staleFailure = reduceHeadquartersLoadState(refreshing, {
    requestId: 1,
    type: "refresh_failure",
    workspaceId: snapshot.workspace.id
  });
  assert.equal(staleFailure, refreshing);

  const failed = reduceHeadquartersLoadState(refreshing, {
    requestId: 2,
    type: "refresh_failure",
    workspaceId: snapshot.workspace.id
  });
  assert.equal(failed.status, "ready");
  assert.equal(failed.refreshing, false);
  assert.equal(failed.refreshError, true);
  assert.equal(failed.snapshot, snapshot);
});

test("replaces a preserved snapshot only after a successful exact refresh", () => {
  const snapshot = makeHeadquartersFixture();
  const refreshing = reduceHeadquartersLoadState(
    {
      refreshError: true,
      refreshing: false,
      requestId: 4,
      snapshot,
      status: "ready",
      workspaceId: snapshot.workspace.id
    },
    {
      requestId: 5,
      type: "refresh_start",
      workspaceId: snapshot.workspace.id
    }
  );
  const refreshedSnapshot = makeHeadquartersFixture((fixture) => {
    fixture.snapshot.id = "snapshot-refreshed";
  });
  const succeeded = reduceHeadquartersLoadState(refreshing, {
    requestId: 5,
    snapshot: refreshedSnapshot,
    type: "success",
    workspaceId: snapshot.workspace.id
  });

  assert.equal(succeeded.snapshot, refreshedSnapshot);
  assert.equal(succeeded.status, "ready");
  assert.equal(succeeded.refreshing, false);
  assert.equal(succeeded.refreshError, false);

  const switchedWorkspace = reduceHeadquartersLoadState(succeeded, {
    requestId: 6,
    type: "refresh_start",
    workspaceId: "workspace-other"
  });
  assert.equal(switchedWorkspace.snapshot, null);
  assert.equal(switchedWorkspace.status, "loading");
  assert.equal(switchedWorkspace.refreshing, false);
  assert.equal(switchedWorkspace.workspaceId, "workspace-other");
});

test("renders explicit loading, missing, forbidden, offline, contract, and generic states", () => {
  const cases = [
    ["loading", "FounderOS вспоминает контекст"],
    ["missing", "Нужна компания"],
    ["forbidden", "Доступ закрыт"],
    ["offline", "Нет связи с системой"],
    ["contract_error", "Картина не подтверждена"],
    ["error", "Картина временно недоступна"]
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
