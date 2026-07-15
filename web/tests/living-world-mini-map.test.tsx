import assert from "node:assert/strict";
import test from "node:test";

import { renderToStaticMarkup } from "react-dom/server";

import {
  buildLivingWorldMiniMapModel,
  LivingWorldMiniMap
} from "../components/LivingWorldMiniMap";
import type { CompanyMapResponse } from "../lib/types";

const sourceRef = {
  id: "source-1",
  kind: "gmail_message",
  source: "gmail",
  label: "message-1",
  url: null,
  record_type: "message",
  record_id: "message-1"
};

const sampleMap: CompanyMapResponse = {
  workspace_id: "workspace-1",
  mode: "evidence_backed_projection",
  source: "workspace_and_company_brain_projection",
  company: {
    key: "workspace:workspace-1",
    workspace_id: "workspace-1",
    name: "Northstar",
    slug: "northstar",
    status: "active",
    source_refs: [sourceRef]
  },
  summary: {
    internal_people: 1,
    confirmed_external_people: 2,
    confirmed_organizations: 1,
    external_contacts_in_window: 1,
    organizations_in_window: 1,
    touchpoints_in_window: 4
  },
  window: {
    gmail_messages_available: 4,
    gmail_messages_considered: 4,
    message_limit: 50,
    truncated: false,
    order: "newest_first"
  },
  people: {
    internal: [
      {
        key: "user:anna",
        person_id: null,
        user_id: "anna",
        name: "Анна",
        email: "anna@northstar.test",
        status: "active",
        role: "owner",
        source_refs: [sourceRef]
      }
    ],
    confirmed_external: [
      {
        key: "person:olga",
        person_id: "olga",
        email: "olga@acme.test",
        display_name: "Ольга Соколова",
        status: "confirmed",
        organization_id: "acme",
        organization_key: "organization:acme",
        organization_name: "Acme",
        relationship_type: "decision_maker",
        role_title: "COO",
        interaction_count: 3,
        last_interaction_at: "2026-07-13T12:00:00Z",
        source_refs: [sourceRef]
      },
      {
        key: "person:standalone",
        person_id: "standalone",
        email: "standalone@example.test",
        display_name: "Свободный контакт",
        status: "confirmed",
        organization_id: "missing",
        organization_key: "organization:missing",
        organization_name: "Нельзя показывать как связь",
        relationship_type: "contact",
        role_title: null,
        interaction_count: 1,
        last_interaction_at: "2026-07-13T12:00:00Z",
        source_refs: [sourceRef]
      }
    ],
    external_candidates: [
      {
        key: "candidate:ivan",
        candidate_version: "a".repeat(64),
        email: "ivan@prospect.test",
        display_name: "Иван Петров",
        organization_key: "candidate:prospect",
        last_interaction_at: "2026-07-13T12:00:00Z",
        interaction_count: 2,
        source_refs: [sourceRef],
        needs_founder_confirm: true
      }
    ]
  },
  organizations: [
    {
      key: "candidate:prospect",
      candidate_version: "b".repeat(64),
      domain: "prospect.test",
      name: "Prospect",
      kind: "external_candidate",
      people_count: 1,
      interaction_count: 2,
      last_interaction_at: "2026-07-13T12:00:00Z",
      source_refs: [sourceRef],
      needs_founder_confirm: true
    }
  ],
  confirmed_organizations: [
    {
      key: "organization:acme",
      organization_id: "acme",
      domain: "acme.test",
      name: "Acme",
      relationship_kind: "customer",
      status: "confirmed",
      people_count: 1,
      interaction_count: 3,
      last_interaction_at: "2026-07-13T12:00:00Z",
      source_refs: [sourceRef]
    }
  ],
  touchpoints: [],
  capabilities: {
    read_only: true,
    can_resolve: true,
    required_role: "member",
    provider_calls: false,
    llm_used: false
  },
  warnings: [],
  is_live: false,
  llm_used: false
};

test("builds a compact world model without inventing affiliations", () => {
  const model = buildLivingWorldMiniMapModel(sampleMap, "Fallback");

  assert.equal(model.company.label, "Northstar");
  assert.deepEqual(model.internalPeople.map((node) => node.label), ["Анна"]);
  assert.deepEqual(model.confirmedNetwork.map((node) => node.label), [
    "Acme",
    "Ольга Соколова",
    "Свободный контакт"
  ]);
  assert.deepEqual(model.candidates.map((node) => node.label), [
    "Prospect",
    "Иван Петров"
  ]);
  assert.match(model.confirmedNetwork[1]?.detail ?? "", /Acme/);
  assert.doesNotMatch(
    model.confirmedNetwork[2]?.detail ?? "",
    /Нельзя показывать как связь/
  );
  assert.doesNotMatch(model.candidates[1]?.detail ?? "", /Prospect/);
  assert.equal(model.company.profileTarget?.selector, "v1:company");
  assert.equal(
    model.candidates[0]?.profileTarget?.href.includes("prospect.test"),
    false
  );
});

test("renders real map zones as keyboard-accessible controls with an inspector", () => {
  const html = renderToStaticMarkup(
    <LivingWorldMiniMap data={sampleMap} workspaceName="Northstar" />
  );

  assert.ok(html.includes("Живая карта"));
  assert.ok(html.includes("Команда"));
  assert.ok(html.includes("Подтверждённая сеть"));
  assert.ok(html.includes("Неизвестное"));
  assert.ok(html.includes("Анна"));
  assert.ok(html.includes("Ольга Соколова"));
  assert.ok(html.includes("Иван Петров"));
  assert.ok(html.includes("Нужно подтвердить"));
  assert.match(html, /<button[^>]*aria-controls="[^"]+"/);
  assert.match(html, /<button[^>]*aria-pressed="true"/);
  assert.match(html, /<aside[^>]*aria-live="polite"/);
  assert.match(html, /Открыть профиль: Анна/);
  assert.ok(html.includes("Открыть полный профиль"));
  assert.match(
    html,
    /href="\/company-brain\?profile=v1%3Acompany#company-world-profile"/
  );
  assert.doesNotMatch(html, /<canvas|<svg/);
});

test("marks touchpoint counts as lower bounds when the source window is truncated", () => {
  const truncatedMap: CompanyMapResponse = {
    ...sampleMap,
    window: { ...sampleMap.window, truncated: true }
  };
  const model = buildLivingWorldMiniMapModel(
    truncatedMap,
    "Northstar"
  );

  assert.match(model.company.detail, /≥4 касания в показанном окне/);
  assert.match(model.confirmedNetwork[0]?.detail ?? "", /≥3 касания/);
  assert.match(model.candidates[0]?.detail ?? "", /≥1 человек в показанном окне/);
  const html = renderToStaticMarkup(
    <LivingWorldMiniMap data={truncatedMap} workspaceName="Northstar" />
  );
  assert.match(html, /Неизвестное: ≥2/);

  const candidateTemplate = sampleMap.people.external_candidates[0];
  assert.ok(candidateTemplate);
  const crowdedMap: CompanyMapResponse = {
    ...truncatedMap,
    people: {
      ...truncatedMap.people,
      external_candidates: Array.from({ length: 7 }, (_, index) => ({
        ...candidateTemplate,
        candidate_version: String(index).padStart(64, "a"),
        email: `candidate-${index}@prospect.test`,
        key: `candidate:${index}`
      }))
    }
  };
  const crowdedHtml = renderToStaticMarkup(
    <LivingWorldMiniMap data={crowdedMap} workspaceName="Northstar" />
  );
  assert.ok(crowdedHtml.includes("Ещё ≥2 — в полном мире"));
});

test("limits an empty candidate mini-map to the shown truncated window", () => {
  const data: CompanyMapResponse = {
    ...sampleMap,
    organizations: [],
    people: { ...sampleMap.people, external_candidates: [] },
    window: { ...sampleMap.window, truncated: true }
  };
  const html = renderToStaticMarkup(
    <LivingWorldMiniMap data={data} workspaceName="Northstar" />
  );

  assert.ok(html.includes("В показанном окне новых кандидатов"));
  assert.match(html, /Неизвестное: ≥0/);
});

test("uses a compact honest empty state while the world has no data", () => {
  const html = renderToStaticMarkup(
    <LivingWorldMiniMap data={null} workspaceName="Пустой штаб" />
  );

  assert.ok(html.includes("Карта ещё не собрана"));
  assert.ok(html.includes("Подключите радар"));
  assert.doesNotMatch(html, /Подтверждённая сеть пока пуста/);
  assert.doesNotMatch(html, /Доказательств пока нет/);
});

test("distinguishes a failed map read and exposes a retry", () => {
  const html = renderToStaticMarkup(
    <LivingWorldMiniMap
      data={null}
      onRetry={() => undefined}
      state="error"
      workspaceName="Пустой штаб"
    />
  );

  assert.ok(html.includes("Не удалось загрузить карту"));
  assert.ok(html.includes("Повторить"));
  assert.match(html, /role="alert"/);
});
