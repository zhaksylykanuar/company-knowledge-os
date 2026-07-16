"use client";

import {
  useEffect,
  useId,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode
} from "react";

import { resolveCompanyWorldProfileSelector } from "../lib/company-world-profile";
import type {
  CompanyMapConfirmedExternalPerson,
  CompanyMapConfirmedOrganization,
  CompanyMapExternalCandidate,
  CompanyMapInternalPerson,
  CompanyMapOrganizationCandidate,
  CompanyMapResponse,
  CompanyMapTouchpoint
} from "../lib/types";
import styles from "./headquarters-profile-drawer.module.css";

const UNDEFINED_VALUE = "Не определено";
const HISTORY_LIMIT = 5;

type HeadquartersProfileSelection =
  | { kind: "company"; key: string }
  | { kind: "internal_person"; person: CompanyMapInternalPerson }
  | { kind: "confirmed_person"; person: CompanyMapConfirmedExternalPerson }
  | { kind: "person_candidate"; person: CompanyMapExternalCandidate }
  | {
      kind: "confirmed_organization";
      organization: CompanyMapConfirmedOrganization;
    }
  | {
      kind: "organization_candidate";
      organization: CompanyMapOrganizationCandidate;
    };

type OrganizationTab = "overview" | "people" | "history";
const ORGANIZATION_TABS: readonly OrganizationTab[] = [
  "overview",
  "people",
  "history"
];

export function organizationTabIndexAfterKey(
  currentIndex: number,
  key: string
): number | null {
  if (key === "Home") return 0;
  if (key === "End") return ORGANIZATION_TABS.length - 1;
  if (key === "ArrowRight") {
    return (currentIndex + 1) % ORGANIZATION_TABS.length;
  }
  if (key === "ArrowLeft") {
    return (currentIndex - 1 + ORGANIZATION_TABS.length) % ORGANIZATION_TABS.length;
  }
  return null;
}

export function resolveHeadquartersProfileSelection(
  data: CompanyMapResponse,
  selector: string | null
): HeadquartersProfileSelection | null {
  const key = resolveCompanyWorldProfileSelector(data, selector);
  if (!key) {
    return null;
  }
  if (key === data.company.key) {
    return { key, kind: "company" };
  }

  const internalPerson = data.people.internal.find((person) => person.key === key);
  if (internalPerson) {
    return { kind: "internal_person", person: internalPerson };
  }
  const confirmedPerson = data.people.confirmed_external.find(
    (person) => person.key === key
  );
  if (confirmedPerson) {
    return { kind: "confirmed_person", person: confirmedPerson };
  }
  const personCandidate = data.people.external_candidates.find(
    (person) => person.key === key
  );
  if (personCandidate) {
    return { kind: "person_candidate", person: personCandidate };
  }
  const confirmedOrganization = data.confirmed_organizations.find(
    (organization) => organization.key === key
  );
  if (confirmedOrganization) {
    return {
      kind: "confirmed_organization",
      organization: confirmedOrganization
    };
  }
  const organizationCandidate = data.organizations.find(
    (organization) => organization.key === key
  );
  if (organizationCandidate) {
    return {
      kind: "organization_candidate",
      organization: organizationCandidate
    };
  }
  return null;
}

export function HeadquartersProfileDrawer({
  data,
  selector
}: {
  data: CompanyMapResponse;
  selector: string | null;
}) {
  const selection = resolveHeadquartersProfileSelection(data, selector);
  if (!selection) {
    return <UnavailableProfile />;
  }
  if (selection.kind === "company") {
    return <CompanyProfile data={data} />;
  }
  if (selection.kind === "internal_person") {
    return <InternalPersonProfile person={selection.person} />;
  }
  if (selection.kind === "confirmed_person") {
    return <ConfirmedPersonProfile data={data} person={selection.person} />;
  }
  if (selection.kind === "person_candidate") {
    return <PersonCandidateProfile data={data} person={selection.person} />;
  }
  if (selection.kind === "confirmed_organization") {
    return (
      <ConfirmedOrganizationProfile
        data={data}
        organization={selection.organization}
        selector={selector}
      />
    );
  }
  return (
    <OrganizationCandidateProfile
      data={data}
      organization={selection.organization}
    />
  );
}

function UnavailableProfile() {
  return (
    <section className={styles.unavailable} role="status">
      <span aria-hidden="true">?</span>
      <div>
        <p className={styles.kicker}>Точный профиль</p>
        <h3>Профиль недоступен</h3>
        <p>
          Объект не найден в текущем снимке компании. FounderOS не откроет вместо
          него другой профиль.
        </p>
      </div>
    </section>
  );
}

function CompanyProfile({ data }: { data: CompanyMapResponse }) {
  return (
    <ProfileFrame kicker="Компания" title={data.company.name} tone="company">
      <FactGrid
        facts={[
          ["Пространство", data.company.slug],
          ["Статус", data.company.status || UNDEFINED_VALUE],
          ["Подтверждённых источников", String(data.company.source_refs.length)]
        ]}
      />
      <ReadOnlyBoundary />
    </ProfileFrame>
  );
}

function InternalPersonProfile({ person }: { person: CompanyMapInternalPerson }) {
  return (
    <ProfileFrame
      kicker="Сотрудник компании"
      title={person.name ?? person.email}
      tone="internal"
    >
      {person.name ? <p className={styles.secondary}>{person.email}</p> : null}
      <FactGrid
        facts={[
          ["Роль доступа FounderOS", accessRoleLabel(person.role)],
          ["Бизнес-роль", UNDEFINED_VALUE],
          ["Статус аккаунта", person.status || UNDEFINED_VALUE]
        ]}
      />
      <p className={styles.honestyNote}>
        Роль доступа управляет правами в FounderOS. Должность и функция сотрудника
        в текущем снимке не подтверждены.
      </p>
      <ReadOnlyBoundary />
    </ProfileFrame>
  );
}

function ConfirmedPersonProfile({
  data,
  person
}: {
  data: CompanyMapResponse;
  person: CompanyMapConfirmedExternalPerson;
}) {
  const organization = data.confirmed_organizations.find(
    (candidate) =>
      person.organization_id === candidate.organization_id &&
      person.organization_key === candidate.key
  );
  const touchpoints = touchpointsForKey(data, person.key);
  return (
    <ProfileFrame
      kicker="Подтверждённый контакт"
      title={person.display_name ?? person.email}
      tone="confirmed"
    >
      {person.display_name ? <p className={styles.secondary}>{person.email}</p> : null}
      <FactGrid
        facts={[
          ["Связь", relationshipTypeLabel(person.relationship_type)],
          ["Бизнес-роль", person.role_title ?? UNDEFINED_VALUE],
          [
            "Компания",
            organization?.name ?? organization?.domain ?? UNDEFINED_VALUE
          ],
          ["Касания в текущем окне", boundedCount(person.interaction_count, data)]
        ]}
      />
      <CompactHistory data={data} touchpoints={touchpoints} />
      <ReadOnlyBoundary />
    </ProfileFrame>
  );
}

function ConfirmedOrganizationProfile({
  data,
  organization,
  selector
}: {
  data: CompanyMapResponse;
  organization: CompanyMapConfirmedOrganization;
  selector: string | null;
}) {
  const [activeTab, setActiveTab] = useState<OrganizationTab>("overview");
  const tabId = useId().replaceAll(":", "");
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);
  useEffect(() => setActiveTab("overview"), [data.workspace_id, selector]);

  function handleTabKeyDown(
    event: KeyboardEvent<HTMLButtonElement>,
    currentIndex: number
  ) {
    const nextIndex = organizationTabIndexAfterKey(currentIndex, event.key);
    if (nextIndex === null) return;
    event.preventDefault();
    const nextTab = ORGANIZATION_TABS[nextIndex];
    if (!nextTab) return;
    setActiveTab(nextTab);
    tabRefs.current[nextIndex]?.focus();
  }

  const people = data.people.confirmed_external.filter(
    (person) =>
      person.organization_id === organization.organization_id &&
      person.organization_key === organization.key &&
      person.relationship_type !== null
  );
  const touchpoints = touchpointsForKey(data, organization.key);
  const title = organization.name ?? organization.domain ?? UNDEFINED_VALUE;

  return (
    <ProfileFrame
      kicker={
        organization.relationship_kind === "customer"
          ? "Подтверждённый заказчик"
          : "Подтверждённая компания"
      }
      title={title}
      tone="confirmed"
    >
      <div
        aria-label={`Разделы профиля ${title}`}
        aria-orientation="horizontal"
        className={styles.tabs}
        role="tablist"
      >
        {ORGANIZATION_TABS.map((tab, index) => (
          <button
            aria-controls={`${tabId}-${tab}-panel`}
            aria-selected={activeTab === tab}
            id={`${tabId}-${tab}-tab`}
            key={tab}
            onClick={() => setActiveTab(tab)}
            onKeyDown={(event) => handleTabKeyDown(event, index)}
            ref={(node) => { tabRefs.current[index] = node; }}
            role="tab"
            tabIndex={activeTab === tab ? 0 : -1}
            type="button"
          >
            {organizationTabLabel(tab)}
          </button>
        ))}
      </div>

      <section
        aria-labelledby={`${tabId}-overview-tab`}
        hidden={activeTab !== "overview"}
        id={`${tabId}-overview-panel`}
        role="tabpanel"
      >
        <FactGrid
          facts={[
            ["Подтверждённая связь", organizationKindLabel(organization.relationship_kind)],
            ["Домен", organization.domain ?? UNDEFINED_VALUE],
            ["Статус", organization.status || UNDEFINED_VALUE],
            ["Люди с подтверждённой связью", String(people.length)],
            [
              "Касания в текущем окне",
              boundedCount(organization.interaction_count, data)
            ]
          ]}
        />
        <p className={styles.honestyNote}>
          Здоровье, обязательства и тон отношений не вычисляются из переписки.
        </p>
      </section>

      <section
        aria-labelledby={`${tabId}-people-tab`}
        hidden={activeTab !== "people"}
        id={`${tabId}-people-panel`}
        role="tabpanel"
      >
        <ConfirmedPeople people={people} />
      </section>

      <section
        aria-labelledby={`${tabId}-history-tab`}
        hidden={activeTab !== "history"}
        id={`${tabId}-history-panel`}
        role="tabpanel"
      >
        <CompactHistory data={data} touchpoints={touchpoints} />
      </section>
      <ReadOnlyBoundary />
    </ProfileFrame>
  );
}

function PersonCandidateProfile({
  data,
  person
}: {
  data: CompanyMapResponse;
  person: CompanyMapExternalCandidate;
}) {
  return (
    <CandidateFrame title={person.display_name ?? person.email}>
      {person.display_name ? <p className={styles.secondary}>{person.email}</p> : null}
      <FactGrid
        facts={[
          ["Статус связи", "Не подтверждено"],
          ["Компания", UNDEFINED_VALUE],
          ["Касания в текущем окне", boundedCount(person.interaction_count, data)],
          ["Последнее касание", formatDate(person.last_interaction_at)]
        ]}
      />
    </CandidateFrame>
  );
}

function OrganizationCandidateProfile({
  data,
  organization
}: {
  data: CompanyMapResponse;
  organization: CompanyMapOrganizationCandidate;
}) {
  return (
    <CandidateFrame title={organization.name ?? organization.domain}>
      <FactGrid
        facts={[
          ["Статус связи", "Не подтверждено"],
          ["Домен", organization.domain],
          ["Люди в текущем окне", boundedCount(organization.people_count, data)],
          ["Касания в текущем окне", boundedCount(organization.interaction_count, data)],
          ["Последнее касание", formatDate(organization.last_interaction_at)]
        ]}
      />
    </CandidateFrame>
  );
}

function CandidateFrame({ children, title }: { children: ReactNode; title: string }) {
  return (
    <ProfileFrame kicker="Кандидат на связь" title={title} tone="candidate">
      <div className={styles.candidateWarning} role="status">
        <strong>Не подтверждено</strong>
        <span>
          FounderOS видит совпадение в текущем окне данных, но не назначает роль,
          компанию или тип отношений без решения человека.
        </span>
      </div>
      {children}
      <ReadOnlyBoundary />
    </ProfileFrame>
  );
}

function ProfileFrame({
  children,
  kicker,
  title,
  tone
}: {
  children: ReactNode;
  kicker: string;
  title: string;
  tone: "candidate" | "company" | "confirmed" | "internal";
}) {
  return (
    <section className={styles.profile} data-tone={tone}>
      <header className={styles.header}>
        <span aria-hidden="true">{profileMark(tone)}</span>
        <div>
          <p className={styles.kicker}>{kicker}</p>
          <h3>{title}</h3>
        </div>
      </header>
      {children}
    </section>
  );
}

function FactGrid({ facts }: { facts: Array<[string, string]> }) {
  return (
    <dl className={styles.facts}>
      {facts.map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function ConfirmedPeople({ people }: { people: CompanyMapConfirmedExternalPerson[] }) {
  if (people.length === 0) {
    return (
      <p className={styles.empty}>
        Людей с подтверждённой принадлежностью к этой компании пока нет.
      </p>
    );
  }
  return (
    <ul className={styles.people}>
      {people.map((person) => (
        <li key={person.person_id}>
          <span aria-hidden="true">{initials(person.display_name ?? person.email)}</span>
          <div>
            <strong>{person.display_name ?? person.email}</strong>
            <small>
              {person.role_title ?? UNDEFINED_VALUE} · {relationshipTypeLabel(person.relationship_type)}
            </small>
          </div>
        </li>
      ))}
    </ul>
  );
}

function CompactHistory({
  data,
  touchpoints
}: {
  data: CompanyMapResponse;
  touchpoints: CompanyMapTouchpoint[];
}) {
  const visible = touchpoints.slice(0, HISTORY_LIMIT);
  return (
    <div className={styles.history}>
      <p className={styles.windowNote} data-truncated={data.window.truncated}>
        Окно истории: {data.window.gmail_messages_considered} из{" "}
        {data.window.gmail_messages_available} сообщений
        {data.window.truncated ? " · окно усечено, количества являются нижней границей" : ""}.
      </p>
      {visible.length > 0 ? (
        <ol>
          {visible.map((touchpoint) => (
            <li key={touchpoint.key}>
              <span>{directionLabel(touchpoint.direction)}</span>
              <strong>{touchpoint.subject}</strong>
              <time dateTime={touchpoint.occurred_at ?? undefined}>
                {formatDate(touchpoint.occurred_at)}
              </time>
            </li>
          ))}
        </ol>
      ) : (
        <p className={styles.empty}>Подтверждённых касаний в текущем окне нет.</p>
      )}
      {touchpoints.length > visible.length ? (
        <p className={styles.windowNote}>
          Показано {visible.length} из {touchpoints.length} касаний текущего окна.
        </p>
      ) : null}
    </div>
  );
}

function ReadOnlyBoundary() {
  return (
    <p className={styles.boundary}>
      Только чтение · текущий снимок · без provider calls, LLM и внешних записей
    </p>
  );
}

function touchpointsForKey(
  data: CompanyMapResponse,
  key: string
): CompanyMapTouchpoint[] {
  return data.touchpoints.filter(
    (touchpoint) =>
      touchpoint.person_keys.includes(key) || touchpoint.organization_keys.includes(key)
  );
}

function boundedCount(value: number, data: CompanyMapResponse): string {
  return `${data.window.truncated ? "≥" : ""}${value}`;
}

function accessRoleLabel(role: CompanyMapInternalPerson["role"]): string {
  const labels: Record<CompanyMapInternalPerson["role"], string> = {
    admin: "Администратор",
    member: "Участник",
    owner: "Владелец",
    viewer: "Только просмотр"
  };
  return labels[role];
}

function relationshipTypeLabel(
  value: CompanyMapConfirmedExternalPerson["relationship_type"]
): string {
  if (!value) return UNDEFINED_VALUE;
  const labels: Record<NonNullable<CompanyMapConfirmedExternalPerson["relationship_type"]>, string> = {
    account_owner: "Ответственный за аккаунт",
    advisor: "Советник",
    contact: "Контакт",
    decision_maker: "Лицо, принимающее решение",
    employee: "Сотрудник",
    other: "Другая подтверждённая связь"
  };
  return labels[value];
}

function organizationKindLabel(
  value: CompanyMapConfirmedOrganization["relationship_kind"]
): string {
  const labels: Record<CompanyMapConfirmedOrganization["relationship_kind"], string> = {
    customer: "Заказчик",
    other: "Другая подтверждённая связь",
    partner: "Партнёр",
    prospect: "Потенциальный заказчик",
    unknown: UNDEFINED_VALUE,
    vendor: "Поставщик"
  };
  return labels[value];
}

function organizationTabLabel(tab: OrganizationTab): string {
  if (tab === "overview") return "Обзор";
  if (tab === "people") return "Люди";
  return "История";
}

function directionLabel(direction: CompanyMapTouchpoint["direction"]): string {
  const labels: Record<CompanyMapTouchpoint["direction"], string> = {
    inbound: "Входящее",
    mixed: "Диалог",
    outbound: "Исходящее",
    unknown: "Направление не определено"
  };
  return labels[direction];
}

function formatDate(value: string | null): string {
  if (!value) return UNDEFINED_VALUE;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return UNDEFINED_VALUE;
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "short",
    year: "numeric"
  }).format(date);
}

function initials(value: string): string {
  const parts = value.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  return parts.slice(0, 2).map((part) => part[0]?.toLocaleUpperCase("ru-RU")).join("");
}

function profileMark(tone: "candidate" | "company" | "confirmed" | "internal") {
  if (tone === "candidate") return "?";
  if (tone === "confirmed") return "✓";
  if (tone === "internal") return "●";
  return "F";
}
