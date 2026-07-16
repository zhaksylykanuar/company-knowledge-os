import assert from "node:assert/strict";
import test from "node:test";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { DemoCommandCenter } from "../components/DemoCommandCenter";
import { DemoCommandCenterOverlays } from "../components/DemoCommandCenterOverlays";
import {
  demoCommandCenterReducer,
  getDemoCommandCenterSnapshot,
  INITIAL_DEMO_COMMAND_CENTER_STATE,
  resolveDemoAssistant
} from "../lib/demo-command-center";
import {
  DEMO_ATLAS_PROFILE,
  DEMO_COMPANY,
  DEMO_MISSIONS,
  DEMO_MISSION_SUMMARY,
  DEMO_RECEIPT,
  DEMO_RELATIONSHIPS,
  DEMO_SOURCES,
  demoSourceRecordTotal,
  demoTouchpointTotal
} from "../lib/demo-tour";

const noop = () => {};

test("demo fixtures keep company, source, relationship, and queue totals consistent", () => {
  assert.equal(demoSourceRecordTotal(), DEMO_COMPANY.records);
  assert.equal(demoTouchpointTotal(), DEMO_COMPANY.touchpoints);
  assert.equal(DEMO_SOURCES.length, DEMO_COMPANY.sourcesConnected);
  assert.ok(DEMO_MISSIONS.every((mission) => mission.sourceKeys.length === mission.sourceCount));
  assert.equal(DEMO_RELATIONSHIPS.length, DEMO_COMPANY.relationships);
  assert.equal(DEMO_MISSIONS.length, DEMO_MISSION_SUMMARY.waiting);
  assert.equal(
    DEMO_ATLAS_PROFILE.people.reduce((total, person) => total + person.touchpoints, 0),
    DEMO_ATLAS_PROFILE.company.touchpoints
  );
});

test("initial command-center snapshot exposes one priority and only two next decisions", () => {
  const snapshot = getDemoCommandCenterSnapshot(false);
  assert.equal(snapshot.activeMission.id, "DEMO-MISSION-042");
  assert.equal(snapshot.waiting, 3);
  assert.equal(snapshot.criticalRisks, 1);
  assert.deepEqual(snapshot.nextMissions.map((mission) => mission.id), [
    "DEMO-MISSION-041",
    "DEMO-MISSION-040"
  ]);
});

test("completed command-center snapshot removes Atlas and raises the next priority", () => {
  const snapshot = getDemoCommandCenterSnapshot(true);
  assert.equal(snapshot.activeMission.id, "DEMO-MISSION-041");
  assert.equal(snapshot.activeMission.sourceCount, 2);
  assert.equal(snapshot.waiting, 2);
  assert.equal(snapshot.completed, 8);
  assert.equal(snapshot.criticalRisks, 0);
  assert.ok(snapshot.queue.every((mission) => mission.id !== "DEMO-MISSION-042"));
});

test("demo receipt cannot claim a live provider write", () => {
  assert.equal(DEMO_RECEIPT.externalWrite, false);
  assert.match(DEMO_RECEIPT.receiptId, /^DEMO-/);
  assert.match(DEMO_RECEIPT.externalResult, /^SIM-/);
  assert.match(DEMO_RECEIPT.summary, /не изменялись/);
});

test("command center renders a restrained surface without tour chrome or hidden details", () => {
  const html = renderToStaticMarkup(createElement(DemoCommandCenter));
  assert.match(html, /Доброе утро, Алина/);
  assert.match(html, /Требует решения/);
  assert.match(html, /Спросить FounderOS/);
  assert.match(html, /Следующие решения/);
  assert.match(html, /Последние сигналы/);
  assert.doesNotMatch(html, /12 сцен|Запустить показ|Следующая сцена|Режим презентации/);
  assert.doesNotMatch(html, /Елена Миронова|Atlas SSO · План запуска|Руководитель платформы/);
});

test("surface keeps exactly three clickable pulse metrics", () => {
  const html = renderToStaticMarkup(createElement(DemoCommandCenter));
  assert.equal((html.match(/class="[^\"]*pulseIcon/g) ?? []).length, 3);
  assert.match(html, /решения ждут/);
  assert.match(html, /критический риск/);
  assert.match(html, /сотрудников/);
});

test("assistant resolves the current priority with evidence and a drill-down action", () => {
  const reply = resolveDemoAssistant("Что главное сегодня?", false);
  assert.match(reply.text, /Защитить запуск SSO/);
  assert.equal(reply.citations?.[0].source, "FounderOS");
  assert.deepEqual(reply.action?.overlay, { detail: "priority", kind: "detail" });
});

test("assistant answers about people and customers without inventing provider execution", () => {
  const ownerReply = resolveDemoAssistant("Кто отвечает?", false);
  const customerReply = resolveDemoAssistant("Покажи заказчика", false);
  assert.match(ownerReply.text, /Тимур.*София.*Данияр/);
  assert.deepEqual(ownerReply.action?.overlay, { detail: "team", kind: "detail" });
  assert.match(customerReply.text, /Елена Миронова/);
  assert.deepEqual(customerReply.action?.overlay, { detail: "company", kind: "detail" });
  assert.ok(customerReply.citations?.every((citation) => citation.source !== "FounderOS"));
});

test("overlay reducer keeps one mutually exclusive surface and closes cleanly", () => {
  const assistant = demoCommandCenterReducer(INITIAL_DEMO_COMMAND_CENTER_STATE, {
    overlay: { kind: "assistant" },
    type: "open"
  });
  const detail = demoCommandCenterReducer(assistant, {
    overlay: { detail: "company", kind: "detail" },
    type: "open"
  });
  assert.deepEqual(detail.overlay, { detail: "company", kind: "detail" });
  const closed = demoCommandCenterReducer(detail, { type: "close" });
  assert.equal(closed.overlay, null);
  assert.equal(closed.confirmationChecked, false);

  const withHistory = demoCommandCenterReducer(assistant, {
    query: "Что главное?",
    type: "ask"
  });
  const reset = demoCommandCenterReducer(
    { ...withHistory, decisionCompleted: true },
    { type: "reset" }
  );
  assert.deepEqual(reset, INITIAL_DEMO_COMMAND_CENTER_STATE);
});

test("decision cannot complete without confirmation or outside the decision dialog", () => {
  const decisionOpen = demoCommandCenterReducer(INITIAL_DEMO_COMMAND_CENTER_STATE, {
    overlay: { kind: "decision" },
    type: "open"
  });
  assert.equal(
    demoCommandCenterReducer(decisionOpen, { type: "complete-decision" }).decisionCompleted,
    false
  );
  const confirmed = demoCommandCenterReducer(decisionOpen, {
    checked: true,
    type: "confirm"
  });
  const completed = demoCommandCenterReducer(confirmed, { type: "complete-decision" });
  assert.equal(completed.decisionCompleted, true);
  assert.equal(completed.confirmationChecked, false);
});

test("completed decision is idempotent and assistant reports the receipt state", () => {
  const completed = {
    ...INITIAL_DEMO_COMMAND_CENTER_STATE,
    confirmationChecked: false,
    decisionCompleted: true,
    overlay: { kind: "decision" } as const
  };
  assert.equal(
    demoCommandCenterReducer(completed, { type: "complete-decision" }),
    completed
  );
  const reply = resolveDemoAssistant("Что сделать?", true);
  assert.match(reply.text, /очередь пересчитана с 3 до 2/);
  assert.equal(reply.citations?.[0].label, DEMO_RECEIPT.receiptId);
});

test("decision dialog keeps preview, confirmation, and no-write boundary in one modal", () => {
  const state = {
    ...INITIAL_DEMO_COMMAND_CENTER_STATE,
    overlay: { kind: "decision" } as const
  };
  const html = renderToStaticMarkup(
    <DemoCommandCenterOverlays
      onAsk={noop}
      onClose={noop}
      onCompleteDecision={noop}
      onConfirmationChange={noop}
      onOpen={noop}
      onReset={noop}
      state={state}
    />
  );
  assert.match(html, /Контекст, точный предпросмотр и подтверждение находятся в одном окне/);
  assert.match(html, /Подтверждаю симуляцию/);
  assert.match(html, /Внешней записи не будет/);
  assert.match(html, /disabled=""/);

  const completedTeamHtml = renderToStaticMarkup(
    <DemoCommandCenterOverlays
      onAsk={noop}
      onClose={noop}
      onCompleteDecision={noop}
      onConfirmationChange={noop}
      onOpen={noop}
      onReset={noop}
      state={{
        ...INITIAL_DEMO_COMMAND_CENTER_STATE,
        decisionCompleted: true,
        overlay: { detail: "team", kind: "detail" }
      }}
    />
  );
  assert.match(completedTeamHtml, /В новом приоритете/);
  assert.match(completedTeamHtml, /Мила Орлова/);

  const selectedMissionHtml = renderToStaticMarkup(
    <DemoCommandCenterOverlays
      onAsk={noop}
      onClose={noop}
      onCompleteDecision={noop}
      onConfirmationChange={noop}
      onOpen={noop}
      onReset={noop}
      state={{
        ...INITIAL_DEMO_COMMAND_CENTER_STATE,
        overlay: { kind: "mission", missionId: "DEMO-MISSION-040" }
      }}
    />
  );
  assert.match(selectedMissionHtml, /Ответить Volna Bank по безопасности/);
  assert.match(selectedMissionHtml, /Gmail · 2 мин назад/);
  assert.match(selectedMissionHtml, /Drive · 13 мин назад/);
  assert.doesNotMatch(selectedMissionHtml, /Atlas SSO · План запуска/);
});
