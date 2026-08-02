import assert from "node:assert/strict";
import test from "node:test";

import { renderToStaticMarkup } from "react-dom/server";

import {
  HeadquartersMissionDetail,
  missionProfileTargets,
  profileSelectorFromTarget
} from "../components/HeadquartersMissionDetail";
import type { HeadquartersMission } from "../lib/headquarters";
import { makeHeadquartersFixture } from "./fixtures/headquarters";

function renderMission(mission: HeadquartersMission): string {
  return renderToStaticMarkup(
    <HeadquartersMissionDetail
      mission={mission}
      onOpenDecision={() => undefined}
      onOpenProfile={() => undefined}
      position="priority"
    />
  );
}

test("renders confirmed mission fields together with their field-level provenance", () => {
  const mission = makeHeadquartersFixture().priority;
  assert.ok(mission);
  const html = renderMission(mission);

  assert.ok(html.includes("Снимает блокировку запуска для ключевого заказчика."));
  assert.equal((html.match(/>Подтверждён</g) ?? []).length, 2);
  assert.equal(
    (html.match(/1 подтверждённых оснований поля/g) ?? []).length,
    4
  );
  assert.doesNotMatch(html, /Поле не подтверждено отдельным основанием/);
  assert.ok(html.includes("GitHub issue #42"));
  assert.match(html, /<summary>1 подтверждённых оснований поля<\/summary>/);
  assert.match(html, /href="https:\/\/github\.com\/acme\/founderos\/issues\/42"/);
  assert.ok(html.includes("Открыть точное решение"));
});

test("keeps unavailable fields explicit and never labels unproven values as confirmed", () => {
  const snapshot = makeHeadquartersFixture((fixture) => {
    const mission = fixture.priority;
    assert.ok(mission);
    mission.due_at = null;
    mission.fact_provenance.customer = [];
    mission.fact_provenance.due = [];
    mission.fact_provenance.impact = [];
    mission.fact_provenance.owner = [];
    mission.organization_id = null;
    mission.owner_person_ids = [];
  });
  assert.ok(snapshot.priority);
  const html = renderMission(snapshot.priority);

  assert.doesNotMatch(html, /Снимает блокировку запуска для ключевого заказчика/);
  assert.equal((html.match(/>Не определено</g) ?? []).length, 4);
  assert.equal(
    (html.match(/Поле не подтверждено отдельным основанием/g) ?? []).length,
    4
  );
  assert.doesNotMatch(html, />Подтверждён</);
});

test("builds exact canonical profile selectors for mission entities", () => {
  const mission = makeHeadquartersFixture().priority;
  assert.ok(mission);

  assert.deepEqual(missionProfileTargets(mission), [
    { label: "Ответственный", selector: "v1:person:person-owner-1" },
    { label: "Ключевое лицо", selector: "v1:person:person-customer-1" },
    {
      label: "Компания-заказчик",
      selector: "v1:organization:organization-atlas"
    }
  ]);
});

test("deduplicates exact selectors and adds a world profile only from its canonical target", () => {
  const snapshot = makeHeadquartersFixture((fixture) => {
    const mission = fixture.queue[0];
    assert.ok(mission);
    mission.owner_person_ids = ["person-customer-1", "person-owner-2"];
    mission.primary_person_id = "person-customer-1";
    mission.action.target =
      "/company-brain?view=map&profile=v1%3Aperson%3Aworld-candidate-7";
  });
  const mission = snapshot.queue[0];
  assert.ok(mission);

  assert.deepEqual(missionProfileTargets(mission), [
    { label: "Ответственный", selector: "v1:person:person-customer-1" },
    { label: "Ответственный", selector: "v1:person:person-owner-2" },
    {
      label: "Компания-заказчик",
      selector: "v1:organization:organization-atlas"
    },
    { label: "Найденный профиль", selector: "v1:person:world-candidate-7" }
  ]);
});

test("does not expose mission relations without field-level provenance", () => {
  const snapshot = makeHeadquartersFixture((fixture) => {
    const mission = fixture.priority;
    assert.ok(mission);
    mission.fact_provenance.owner = [];
    mission.fact_provenance.customer = [];
  });
  assert.ok(snapshot.priority);

  assert.deepEqual(missionProfileTargets(snapshot.priority), []);
});

test("aggregate field signals never expose confirmed facts or profile relations", () => {
  const snapshot = makeHeadquartersFixture((fixture) => {
    const mission = fixture.priority;
    assert.ok(mission);
    for (const key of ["owner", "customer", "due", "impact"] as const) {
      mission.fact_provenance[key] = mission.fact_provenance[key].map((item) => ({
        ...item,
        trust: "aggregate"
      }));
    }
  });
  assert.ok(snapshot.priority);
  const html = renderMission(snapshot.priority);

  assert.equal((html.match(/>Не определено</g) ?? []).length, 4);
  assert.equal((html.match(/агрегированных сигналов поля/g) ?? []).length, 4);
  assert.doesNotMatch(html, />Подтверждён</);
  assert.deepEqual(missionProfileTargets(snapshot.priority), []);
});

test("accepts profile selectors only from the company-brain route contract", () => {
  assert.equal(
    profileSelectorFromTarget(
      "/company-brain?view=map&profile=v1%3Aorganization%3Aatlas#profile"
    ),
    "v1:organization:atlas"
  );
  assert.equal(profileSelectorFromTarget("/company-brain?profile=v2:person:7"), null);
  assert.equal(profileSelectorFromTarget("/company-brain/profile?profile=v1:person:7"), null);
  assert.equal(profileSelectorFromTarget("https://example.com/?profile=v1:person:7"), null);
  assert.equal(profileSelectorFromTarget(null), null);
});
