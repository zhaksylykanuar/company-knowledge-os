import assert from "node:assert/strict";
import test from "node:test";

import { renderToStaticMarkup } from "react-dom/server";

import {
  HeadquartersProfileDrawer,
  organizationTabIndexAfterKey
} from "../components/HeadquartersProfileDrawer";
import type { CompanyMapResponse } from "../lib/types";

function fixture(): CompanyMapResponse {
  return {
    workspace_id: "workspace-1",
    mode: "evidence_backed_projection",
    source: "workspace_and_company_brain_projection",
    company: {
      key: "company:workspace-1",
      workspace_id: "workspace-1",
      name: "Atlas",
      slug: "atlas",
      status: "active",
      source_refs: []
    },
    summary: {
      internal_people: 1,
      confirmed_external_people: 2,
      confirmed_organizations: 1,
      external_contacts_in_window: 1,
      organizations_in_window: 1,
      touchpoints_in_window: 2
    },
    window: {
      gmail_messages_available: 18,
      gmail_messages_considered: 10,
      message_limit: 10,
      truncated: true,
      order: "newest_first"
    },
    people: {
      internal: [
        {
          key: "member:owner@example.test",
          person_id: null,
          user_id: "user-1",
          name: "Анна",
          email: "owner@example.test",
          status: "active",
          role: "owner",
          source_refs: []
        }
      ],
      confirmed_external: [
        {
          key: "person:alex@example.test",
          person_id: "person-1",
          email: "alex@example.test",
          display_name: "Алекс Клиент",
          status: "active",
          organization_id: "org-1",
          organization_key: "organization:atlas-client.test",
          organization_name: "Atlas Client",
          relationship_type: "decision_maker",
          role_title: "COO",
          interaction_count: 4,
          last_interaction_at: "2026-07-16T10:00:00Z",
          source_refs: []
        },
        {
          key: "person:unconfirmed-affiliation@example.test",
          person_id: "person-2",
          email: "unconfirmed-affiliation@example.test",
          display_name: "Случайный контакт",
          status: "active",
          organization_id: "org-1",
          organization_key: "organization:atlas-client.test",
          organization_name: "Atlas Client",
          relationship_type: null,
          role_title: null,
          interaction_count: 1,
          last_interaction_at: null,
          source_refs: []
        }
      ],
      external_candidates: [
        {
          key: "candidate:person@example.test",
          candidate_version: "person-candidate-v1",
          email: "person@example.test",
          display_name: "Новый контакт",
          organization_key: "candidate-org.test",
          last_interaction_at: "2026-07-15T10:00:00Z",
          interaction_count: 2,
          source_refs: [],
          needs_founder_confirm: true
        }
      ]
    },
    organizations: [
      {
        key: "candidate-org.test",
        candidate_version: "organization-candidate-v1",
        domain: "candidate-org.test",
        name: "Candidate Org",
        kind: "external_candidate",
        people_count: 1,
        interaction_count: 2,
        last_interaction_at: "2026-07-15T10:00:00Z",
        source_refs: [],
        needs_founder_confirm: true
      }
    ],
    confirmed_organizations: [
      {
        key: "organization:atlas-client.test",
        organization_id: "org-1",
        domain: "atlas-client.test",
        name: "Atlas Client",
        relationship_kind: "customer",
        status: "active",
        people_count: 1,
        interaction_count: 4,
        last_interaction_at: "2026-07-16T10:00:00Z",
        source_refs: []
      }
    ],
    touchpoints: [
      {
        key: "touchpoint-1",
        channel: "email",
        source_record_id: "source-1",
        subject: "Подтверждённая встреча",
        direction: "mixed",
        occurred_at: "2026-07-16T10:00:00Z",
        person_keys: ["person:alex@example.test"],
        organization_keys: ["organization:atlas-client.test"],
        source_url: null,
        source_refs: []
      },
      {
        key: "touchpoint-unrelated",
        channel: "email",
        source_record_id: "source-2",
        subject: "Чужая переписка",
        direction: "inbound",
        occurred_at: "2026-07-14T10:00:00Z",
        person_keys: ["candidate:person@example.test"],
        organization_keys: ["candidate-org.test"],
        source_url: null,
        source_refs: []
      }
    ],
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
}

test("fails closed for a missing or raw profile selector", () => {
  const data = fixture();
  const missing = renderToStaticMarkup(
    <HeadquartersProfileDrawer data={data} selector="v1:person:missing" />
  );
  const rawKey = renderToStaticMarkup(
    <HeadquartersProfileDrawer data={data} selector="member:owner@example.test" />
  );

  for (const html of [missing, rawKey]) {
    assert.ok(html.includes("Профиль недоступен"));
    assert.ok(html.includes("не откроет вместо него другой профиль"));
    assert.doesNotMatch(html, />Atlas</);
  }
});

test("separates FounderOS access from an undefined employee business role", () => {
  const html = renderToStaticMarkup(
    <HeadquartersProfileDrawer data={fixture()} selector="v1:member:user-1" />
  );

  assert.ok(html.includes("Анна"));
  assert.ok(html.includes("Роль доступа FounderOS"));
  assert.ok(html.includes("Владелец"));
  assert.ok(html.includes("Бизнес-роль"));
  assert.ok(html.includes("Не определено"));
  assert.ok(html.includes("Должность и функция сотрудника"));
});

test("renders a confirmed customer from durable people and exact touchpoints only", () => {
  const html = renderToStaticMarkup(
    <HeadquartersProfileDrawer data={fixture()} selector="v1:organization:org-1" />
  );

  assert.ok(html.includes("Подтверждённый заказчик"));
  assert.ok(html.includes("Atlas Client"));
  assert.ok(html.includes("Заказчик"));
  assert.match(html, /role="tab"[^>]*>Обзор</);
  assert.match(html, /role="tab"[^>]*>Люди</);
  assert.match(html, /role="tab"[^>]*>История</);
  assert.equal((html.match(/role="tab" tabindex="-1"/g) ?? []).length, 2);
  assert.equal((html.match(/role="tab" tabindex="0"/g) ?? []).length, 1);
  assert.ok(html.includes("Алекс Клиент"));
  assert.doesNotMatch(html, /Случайный контакт/);
  assert.ok(html.includes("Подтверждённая встреча"));
  assert.doesNotMatch(html, /Чужая переписка/);
  assert.ok(html.includes("окно усечено"));
  assert.ok(html.includes("Здоровье, обязательства и тон отношений не вычисляются"));
});

test("customer tabs implement roving focus for arrows, Home, and End", () => {
  assert.equal(organizationTabIndexAfterKey(0, "ArrowRight"), 1);
  assert.equal(organizationTabIndexAfterKey(2, "ArrowRight"), 0);
  assert.equal(organizationTabIndexAfterKey(0, "ArrowLeft"), 2);
  assert.equal(organizationTabIndexAfterKey(1, "Home"), 0);
  assert.equal(organizationTabIndexAfterKey(1, "End"), 2);
  assert.equal(organizationTabIndexAfterKey(1, "Enter"), null);
});

test("marks person and organization candidates as unconfirmed read-only projections", () => {
  const data = fixture();
  const person = renderToStaticMarkup(
    <HeadquartersProfileDrawer
      data={data}
      selector="v1:person-candidate:person-candidate-v1"
    />
  );
  const organization = renderToStaticMarkup(
    <HeadquartersProfileDrawer
      data={data}
      selector="v1:organization-candidate:organization-candidate-v1"
    />
  );

  for (const html of [person, organization]) {
    assert.ok(html.includes("Кандидат на связь"));
    assert.ok(html.includes("Не подтверждено"));
    assert.ok(html.includes("не назначает роль"));
    assert.ok(html.includes("Только чтение"));
  }
  assert.doesNotMatch(person, /Подтверждённый заказчик/);
  assert.doesNotMatch(organization, /Подтверждённый заказчик/);
});
