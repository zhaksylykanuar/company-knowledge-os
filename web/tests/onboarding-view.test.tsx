import assert from "node:assert/strict";
import test from "node:test";

import { renderToStaticMarkup } from "react-dom/server";

import {
  OnboardingJourneyView,
  OnboardingRecoveryView
} from "../app/onboarding/page";
import type { OnboardingProgress } from "../lib/onboarding";

const pendingProgress: OnboardingProgress = {
  checks: {
    company: {
      id: "company",
      state: "complete",
      evidence: "Рабочее пространство создано"
    },
    source: {
      id: "source",
      state: "pending",
      evidence: "источников настроено: 1, но загруженных записей пока нет"
    },
    map: {
      id: "map",
      state: "complete",
      evidence: "людей: 1 · компаний: 0 · контактов: 0"
    },
    team: {
      id: "team",
      state: "pending",
      evidence: "Пока вы единственный участник"
    },
    ready: {
      id: "ready",
      state: "pending",
      evidence: "Подключите источник"
    }
  },
  completedCount: 2,
  totalCount: 4,
  ready: false,
  unavailable: []
};

test("source step keeps a configured but empty source visibly pending", () => {
  const html = renderToStaticMarkup(
    <OnboardingJourneyView
      activeStep={2}
      onChangeStep={() => undefined}
      onRefresh={() => undefined}
      progress={pendingProgress}
      workspace={{
        id: "workspace-1",
        name: "Atlas",
        role: "owner",
        slug: "atlas"
      }}
    />
  );

  assert.ok(html.includes("Откуда FounderOS узнает правду?"));
  assert.ok(html.includes("источников настроено: 1"));
  assert.ok(html.includes("загруженных записей пока нет"));
  assert.ok(html.includes('href="/connectors"'));
  assert.ok(html.includes("Пока продолжить без источника"));
  assert.doesNotMatch(html, /Контекст уже поступает/);
  assert.match(html, /aria-valuenow="2"/);
});

test("final step allows work without claiming skipped setup is complete", () => {
  const html = renderToStaticMarkup(
    <OnboardingJourneyView
      activeStep={5}
      onChangeStep={() => undefined}
      onRefresh={() => undefined}
      progress={pendingProgress}
      workspace={{
        id: "workspace-1",
        name: "Atlas",
        role: "owner",
        slug: "atlas"
      }}
    />
  );

  assert.ok(html.includes("Начало положено"));
  assert.ok(html.includes("не будем выдавать пропуск за подключение"));
  assert.match(html, /2.*из.*4 шагов подтверждены/);
  assert.ok(html.includes('href="/dashboard"'));
  assert.doesNotMatch(html, /Система видит вашу компанию/);
});

test("workspace-less recovery refuses to guess a company", () => {
  const html = renderToStaticMarkup(
    <OnboardingRecoveryView onSignOut={() => undefined} />
  );

  assert.ok(html.includes("Компания пока не привязана"));
  assert.ok(html.includes("не будем угадывать рабочее пространство"));
  assert.ok(html.includes("попросите добавить вас"));
  assert.ok(html.includes("Новая ссылка основателя создаёт другой аккаунт"));
  assert.ok(html.includes("Выйти из аккаунта"));
});

test("viewer onboarding stays read-only for sources and team", () => {
  const sourceHtml = renderToStaticMarkup(
    <OnboardingJourneyView
      activeStep={2}
      onChangeStep={() => undefined}
      onRefresh={() => undefined}
      progress={pendingProgress}
      workspace={{
        id: "workspace-1",
        name: "Atlas",
        role: "viewer",
        slug: "atlas"
      }}
    />
  );
  const teamHtml = renderToStaticMarkup(
    <OnboardingJourneyView
      activeStep={4}
      onChangeStep={() => undefined}
      onRefresh={() => undefined}
      progress={pendingProgress}
      workspace={{
        id: "workspace-1",
        name: "Atlas",
        role: "viewer",
        slug: "atlas"
      }}
    />
  );

  assert.ok(sourceHtml.includes("Посмотреть данные"));
  assert.ok(sourceHtml.includes("доступны только владельцу"));
  assert.doesNotMatch(sourceHtml, />Добавить первые данные</);
  assert.ok(teamHtml.includes("Посмотреть команду"));
  assert.ok(teamHtml.includes("Менять состав может только владелец"));
  assert.doesNotMatch(teamHtml, />Добавить человека</);
});
