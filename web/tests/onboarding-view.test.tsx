import assert from "node:assert/strict";
import test from "node:test";

import { renderToStaticMarkup } from "react-dom/server";

import { OnboardingRecoveryView } from "../app/onboarding/page";

test("workspace-less recovery refuses to guess or create a company", () => {
  const html = renderToStaticMarkup(
    <OnboardingRecoveryView onSignOut={() => undefined} />
  );

  assert.ok(html.includes("Компания пока не привязана"));
  assert.ok(html.includes("не будем угадывать рабочее пространство"));
  assert.ok(html.includes("попросите добавить вас"));
  assert.ok(html.includes("Новая ссылка основателя создаёт другой аккаунт"));
  assert.ok(html.includes("Выйти из аккаунта"));
  assert.doesNotMatch(html, /Создать компанию|API key|workspace id/i);
});
