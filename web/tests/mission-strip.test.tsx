import assert from "node:assert/strict";
import test from "node:test";

import { renderToStaticMarkup } from "react-dom/server";

import { MiniHint, MissionStrip } from "../components/MissionStrip";

test("mission strip explains the next action and outcome without hiding the CTA", () => {
  const html = renderToStaticMarkup(
    <MissionStrip
      action="Открыть первое решение"
      current="Три решения ждут ответа"
      details={<p>Без подтверждения ничего не отправится наружу.</p>}
      outcome="Команда увидит подтверждённый следующий шаг"
    />
  );

  assert.ok(html.includes("Сейчас"));
  assert.ok(html.includes("Нажмите"));
  assert.ok(html.includes("Результат"));
  assert.ok(html.includes("Открыть первое решение"));
  assert.ok(html.includes("Как это работает безопасно"));
  assert.match(html, /<details class="mission-strip-details">/);
  assert.doesNotMatch(html, /<details[^>]* open/);
});

test("mini hint is an explicit keyboard-accessible disclosure", () => {
  const html = renderToStaticMarkup(
    <MiniHint label="Что показывает сигнал?">
      Только подтверждённые данные.
    </MiniHint>
  );

  assert.match(html, /<summary aria-label="Что показывает сигнал\?">\?<\/summary>/);
  assert.ok(html.includes("Только подтверждённые данные"));
});
