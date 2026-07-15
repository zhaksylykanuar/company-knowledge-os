import assert from "node:assert/strict";
import test from "node:test";

import { renderToStaticMarkup } from "react-dom/server";

import { DemoProductTour } from "../components/DemoProductTour";
import { DemoTourScenes } from "../components/DemoTourScenes";
import {
  DEMO_ATLAS_PROFILE,
  DEMO_COMPANY,
  DEMO_MISSIONS,
  DEMO_MISSION_SUMMARY,
  DEMO_PREVIEW,
  DEMO_RECEIPT,
  DEMO_RELATIONSHIPS,
  DEMO_SCENES,
  DEMO_SIGNAL,
  DEMO_SOURCES,
  DEMO_TEAM,
  DEMO_TRUTH_LABEL,
  demoSourceRecordTotal,
  demoTouchpointTotal,
  sceneIndexFromHash
} from "../lib/demo-tour";

const noop = () => undefined;

test("demo fixtures keep every cross-scene number internally consistent", () => {
  assert.equal(DEMO_SCENES.length, 12);
  assert.equal(DEMO_SOURCES.length, 4);
  assert.equal(DEMO_TEAM.length, 6);
  assert.equal(demoSourceRecordTotal(), 858);
  assert.equal(demoSourceRecordTotal(), DEMO_COMPANY.records);
  assert.equal(demoTouchpointTotal(), 37);
  assert.equal(demoTouchpointTotal(), DEMO_COMPANY.touchpoints);
  assert.equal(
    DEMO_MISSION_SUMMARY.waiting +
      DEMO_MISSION_SUMMARY.approved +
      DEMO_MISSION_SUMMARY.completed,
    DEMO_MISSION_SUMMARY.loaded
  );
  assert.equal(DEMO_MISSIONS.length, DEMO_MISSION_SUMMARY.waiting);
  assert.equal(DEMO_RELATIONSHIPS[0].touchpoints, DEMO_ATLAS_PROFILE.company.touchpoints);
  assert.equal(DEMO_ATLAS_PROFILE.people.length, DEMO_ATLAS_PROFILE.company.contacts);
  assert.equal(
    DEMO_ATLAS_PROFILE.people.reduce((total, person) => total + person.touchpoints, 0),
    DEMO_ATLAS_PROFILE.company.touchpoints
  );
  assert.equal(DEMO_MISSIONS[0].sourceCount, DEMO_SOURCES.length);
  assert.equal(DEMO_MISSIONS[0].evidenceRefs, 19);
});

test("demo deep links restore only known scenes and fail safely to the beginning", () => {
  assert.equal(sceneIndexFromHash("#scene-01"), 0);
  assert.equal(sceneIndexFromHash("scene-06"), 5);
  assert.equal(sceneIndexFromHash("#scene-12"), 11);
  assert.equal(sceneIndexFromHash("#unknown"), 0);
  assert.equal(sceneIndexFromHash(""), 0);
});

test("demo fixtures contain no provider URL or successful external-write claim", () => {
  const serialized = JSON.stringify({
    atlas: DEMO_ATLAS_PROFILE,
    missions: DEMO_MISSIONS,
    preview: DEMO_PREVIEW,
    receipt: DEMO_RECEIPT,
    relationships: DEMO_RELATIONSHIPS,
    sources: DEMO_SOURCES,
    team: DEMO_TEAM
  });

  assert.doesNotMatch(serialized, /https?:\/\//i);
  assert.doesNotMatch(serialized, /github\.com/i);
  assert.doesNotMatch(serialized, /external_write"\s*:\s*true/i);
  assert.equal(DEMO_RECEIPT.externalWrite, false);
  assert.match(DEMO_RECEIPT.receiptId, /^DEMO-/);
  assert.match(DEMO_RECEIPT.externalResult, /^SIM-/);
  assert.match(DEMO_PREVIEW.repository, /^demo-/);
});

test("desktop tour shell exposes all scenes, truth boundary, and presentation controls", () => {
  const html = renderToStaticMarkup(<DemoProductTour />);

  assert.ok(html.includes(DEMO_TRUTH_LABEL));
  assert.ok(html.includes("Полный путь пользователя"));
  assert.ok(html.includes("Запустить показ"));
  assert.ok(html.includes("Режим презентации"));
  assert.ok(html.includes("Исследовать"));
  assert.ok(html.includes("Скопировать ссылку"));
  assert.match(html, /href="\/dashboard"/);
  for (const scene of DEMO_SCENES) {
    assert.ok(html.includes(scene.navLabel));
  }
  assert.doesNotMatch(html, /href="https?:\/\//i);
  assert.doesNotMatch(html, /<form/i);
});

test("every demo scene renders its primary product claim from local fixtures", () => {
  const expectedScreenTitles = [
    "Компания уже живёт в FounderOS",
    "Вся работа компании синхронизирована",
    "Защитить запуск SSO для Atlas Retail",
    "Главное видно с первого взгляда",
    "Компания — это сеть живых отношений",
    "Контекст до разговора — в одном профиле",
    "У результата есть конкретные владельцы",
    "Основания решения собраны в один пакет",
    "Три решения вместо потока новостей",
    "Очередь показывает только решения человека",
    "Защитить запуск SSO для Atlas Retail",
    "Миссия завершилась проверяемой квитанцией"
  ] as const;

  for (const [sceneIndex, scene] of DEMO_SCENES.entries()) {
    const html = renderToStaticMarkup(
      <DemoTourScenes
        actionSimulated={sceneIndex === 11}
        confirmationChecked={false}
        decisionStep="review"
        hintsVisible
        onConfirmationChange={noop}
        onDecisionStepChange={noop}
        onNavigate={noop}
        onProfileViewChange={noop}
        onSelectRelationship={noop}
        onSelectSource={noop}
        onSimulateAction={noop}
        profileView="person"
        sceneIndex={sceneIndex}
        selectedRelationship="Atlas Retail"
        selectedSource="github"
      />
    );

    assert.ok(
      html.includes(expectedScreenTitles[sceneIndex]),
      `scene ${scene.id} must render its primary product claim`
    );
  }
});

test("decision preview remains explicitly simulated and requires confirmation", () => {
  const html = renderToStaticMarkup(
    <DemoTourScenes
      actionSimulated={false}
      confirmationChecked={false}
      decisionStep="preview"
      hintsVisible
      onConfirmationChange={noop}
      onDecisionStepChange={noop}
      onNavigate={noop}
      onProfileViewChange={noop}
      onSelectRelationship={noop}
      onSelectSource={noop}
      onSimulateAction={noop}
      profileView="person"
      sceneIndex={10}
      selectedRelationship="Atlas Retail"
      selectedSource="github"
    />
  );

  assert.ok(html.includes(DEMO_PREVIEW.repository));
  assert.ok(html.includes(DEMO_TRUTH_LABEL));
  assert.match(html, /type="checkbox"/);
  assert.match(html, /disabled=""/);
  assert.doesNotMatch(html, /задача GitHub создана/i);
});

test("final receipt closes the loop without claiming a provider write", () => {
  const html = renderToStaticMarkup(
    <DemoTourScenes
      actionSimulated
      confirmationChecked
      decisionStep="preview"
      hintsVisible
      onConfirmationChange={noop}
      onDecisionStepChange={noop}
      onNavigate={noop}
      onProfileViewChange={noop}
      onSelectRelationship={noop}
      onSelectSource={noop}
      onSimulateAction={noop}
      profileView="person"
      sceneIndex={11}
      selectedRelationship="Atlas Retail"
      selectedSource="github"
    />
  );

  assert.ok(html.includes(DEMO_RECEIPT.receiptId));
  assert.ok(html.includes(DEMO_RECEIPT.externalResult));
  assert.ok(html.includes("Внешняя запись"));
  assert.ok(html.includes("false"));
  assert.ok(html.includes(DEMO_RECEIPT.summary));
  assert.ok(html.includes("3"));
  assert.ok(html.includes("2"));
});

test("direct final-scene navigation stays an honest preview until simulation", () => {
  const html = renderToStaticMarkup(
    <DemoTourScenes
      actionSimulated={false}
      confirmationChecked={false}
      decisionStep="review"
      hintsVisible
      onConfirmationChange={noop}
      onDecisionStepChange={noop}
      onNavigate={noop}
      onProfileViewChange={noop}
      onSelectRelationship={noop}
      onSelectSource={noop}
      onSimulateAction={noop}
      profileView="person"
      sceneIndex={11}
      selectedRelationship="Atlas Retail"
      selectedSource="github"
    />
  );

  assert.ok(html.includes("Результат ещё не сохранён"));
  assert.ok(html.includes("Сначала пройти решение"));
  assert.doesNotMatch(html, /Результат сохранён/);
  assert.ok(!html.includes(DEMO_RECEIPT.receiptId));
  assert.ok(!html.includes(DEMO_RECEIPT.externalResult));
});

test("simulated result changes the headquarters instead of returning to stale state", () => {
  const html = renderToStaticMarkup(
    <DemoTourScenes
      actionSimulated
      confirmationChecked
      decisionStep="preview"
      hintsVisible
      onConfirmationChange={noop}
      onDecisionStepChange={noop}
      onNavigate={noop}
      onProfileViewChange={noop}
      onSelectRelationship={noop}
      onSelectSource={noop}
      onSimulateAction={noop}
      profileView="person"
      sceneIndex={3}
      selectedRelationship="Atlas Retail"
      selectedSource="github"
    />
  );

  assert.ok(html.includes("Результат изменил следующий приоритет"));
  assert.ok(html.includes("Назначить владельца повторной отправки уведомлений"));
  assert.ok(html.includes("Atlas SSO · на контроле"));
  assert.ok(html.includes(DEMO_RECEIPT.receiptId));
  assert.doesNotMatch(html, /Решение нужно принять до 12:00/);
});

test("simulated result removes Atlas from the waiting queue and updates totals", () => {
  const html = renderToStaticMarkup(
    <DemoTourScenes
      actionSimulated
      confirmationChecked
      decisionStep="preview"
      hintsVisible
      onConfirmationChange={noop}
      onDecisionStepChange={noop}
      onNavigate={noop}
      onProfileViewChange={noop}
      onSelectRelationship={noop}
      onSelectSource={noop}
      onSimulateAction={noop}
      profileView="person"
      sceneIndex={9}
      selectedRelationship="Atlas Retail"
      selectedSource="github"
    />
  );

  assert.ok(html.includes("Очередь пересчитана по результату"));
  assert.ok(html.includes("2 миссии"));
  assert.ok(html.includes("Назначить владельца повторной отправки уведомлений"));
  assert.match(html, />8<\/dd><dt>с результатом/);
  assert.ok(!html.includes(DEMO_SIGNAL.title));
});

test("completed decision opens its receipt instead of allowing a duplicate simulation", () => {
  const html = renderToStaticMarkup(
    <DemoTourScenes
      actionSimulated
      confirmationChecked
      decisionStep="preview"
      hintsVisible
      onConfirmationChange={noop}
      onDecisionStepChange={noop}
      onNavigate={noop}
      onProfileViewChange={noop}
      onSelectRelationship={noop}
      onSelectSource={noop}
      onSimulateAction={noop}
      profileView="person"
      sceneIndex={10}
      selectedRelationship="Atlas Retail"
      selectedSource="github"
    />
  );

  assert.ok(html.includes("Повторное выполнение не требуется"));
  assert.ok(html.includes("Открыть квитанцию"));
  assert.doesNotMatch(html, /type="checkbox"/);
  assert.ok(!html.includes("Симулировать результат"));
});

test("world inspector uses readable Russian touchpoint inflections", () => {
  for (const [selectedRelationship, value, label] of [
    ["Atlas Retail", "21", "касание"],
    ["Volna Bank", "9", "касаний"],
    ["Kinetic Legal", "7", "касаний"]
  ] as const) {
    const html = renderToStaticMarkup(
      <DemoTourScenes
        actionSimulated={false}
        confirmationChecked={false}
        decisionStep="review"
        hintsVisible
        onConfirmationChange={noop}
        onDecisionStepChange={noop}
        onNavigate={noop}
        onProfileViewChange={noop}
        onSelectRelationship={noop}
        onSelectSource={noop}
        onSimulateAction={noop}
        profileView="person"
        sceneIndex={4}
        selectedRelationship={selectedRelationship}
        selectedSource="github"
      />
    );

    assert.match(html, new RegExp(`>${value}<\\/dd><dt>${label}<`));
    if (selectedRelationship === "Atlas Retail") {
      assert.match(html, /<small>21 касание<\/small>/);
      assert.match(html, /<small>9 касаний<\/small>/);
      assert.match(html, /<small>7 касаний<\/small>/);
    }
  }
});
