import type { ReactNode } from "react";

import { M } from "../lib/messages";
import type {
  CompanyMapConfirmedExternalPerson,
  CompanyMapConfirmedOrganization,
  CompanyMapResponse
} from "../lib/types";
import styles from "./company-world.module.css";

export type CompanyWorldZone = "all" | "network" | "review" | "team";

export type CompanyWorldOrganizationGroup = {
  organization: CompanyMapConfirmedOrganization;
  people: CompanyMapConfirmedExternalPerson[];
};

export type CompanyWorldBoardModel = {
  organizationGroups: CompanyWorldOrganizationGroup[];
  standaloneConfirmedPeople: CompanyMapConfirmedExternalPerson[];
  pendingCount: number;
};

type CompanyWorldBoardProps = {
  activeZone: CompanyWorldZone;
  data: CompanyMapResponse;
  inspectorId: string;
  onSelect: (key: string) => void;
  onZoneChange: (zone: CompanyWorldZone) => void;
  selectedKey: string | null;
};

/**
 * Build the board without inventing affiliations.
 *
 * A person is rendered inside an organization only when the durable person
 * profile points to that exact durable organization and has a human-authored
 * relationship type. Domain/name similarity and candidate organization keys
 * are deliberately ignored here.
 */
export function buildCompanyWorldBoardModel(
  data: CompanyMapResponse
): CompanyWorldBoardModel {
  const groupedPersonKeys = new Set<string>();
  const organizationGroups = data.confirmed_organizations.map((organization) => {
    const people = data.people.confirmed_external.filter(
      (person) =>
        person.organization_id === organization.organization_id &&
        person.organization_key === organization.key &&
        person.relationship_type !== null
    );
    people.forEach((person) => {
      groupedPersonKeys.add(person.key);
    });
    return { organization, people };
  });

  return {
    organizationGroups,
    pendingCount:
      data.people.external_candidates.length + data.organizations.length,
    standaloneConfirmedPeople: data.people.confirmed_external.filter(
      (person) => !groupedPersonKeys.has(person.key)
    )
  };
}

export function CompanyWorldBoard({
  activeZone,
  data,
  inspectorId,
  onSelect,
  onZoneChange,
  selectedKey
}: CompanyWorldBoardProps) {
  const model = buildCompanyWorldBoardModel(data);
  const confirmedNetworkCount =
    data.confirmed_organizations.length + data.people.confirmed_external.length;

  return (
    <section
      className={`${styles.board} world-board`}
      aria-labelledby="world-board-title"
    >
      <header className={styles.boardHeader}>
        <div>
          <span className="eyebrow">{M.companyWorld.boardEyebrow}</span>
          <h3 id="world-board-title">{M.companyWorld.boardTitle}</h3>
        </div>
        <div
          aria-label={M.companyWorld.zoneFilterLabel}
          className={styles.zoneFilters}
          role="group"
        >
          <ZoneFilter
            active={activeZone === "all"}
            count={
              data.people.internal.length + confirmedNetworkCount + model.pendingCount
            }
            countIsLowerBound={data.window.truncated}
            label={M.companyWorld.allContours}
            onClick={() => onZoneChange("all")}
          />
          <ZoneFilter
            active={activeZone === "team"}
            count={data.people.internal.length}
            label={M.companyWorld.teamSection}
            onClick={() => onZoneChange("team")}
          />
          <ZoneFilter
            active={activeZone === "network"}
            count={confirmedNetworkCount}
            label={M.companyWorld.confirmedNetwork}
            onClick={() => onZoneChange("network")}
          />
          <ZoneFilter
            active={activeZone === "review"}
            count={model.pendingCount}
            countIsLowerBound={data.window.truncated}
            label={M.companyWorld.needsReview}
            onClick={() => onZoneChange("review")}
            tone="candidate"
          />
        </div>
      </header>

      <div className={styles.stage} data-active-zone={activeZone}>
        <BoardZone
          className={styles.teamZone}
          count={data.people.internal.length}
          description={M.companyWorld.teamZoneDescription}
          title={M.companyWorld.teamSection}
        >
          <div className="world-node-stack">
            {data.people.internal.map((person) => (
              <BoardNode
                badge={roleLabel(person.role)}
                inspectorId={inspectorId}
                isSelected={selectedKey === person.key}
                key={person.key}
                label={person.name ?? person.email}
                meta={person.name ? person.email : undefined}
                onSelect={() => onSelect(person.key)}
                tone="team"
              />
            ))}
          </div>
        </BoardZone>

        <section className={styles.core} aria-label={M.companyWorld.companySection}>
          <span className="world-core-orbit world-core-orbit--outer" aria-hidden="true" />
          <span className="world-core-orbit world-core-orbit--inner" aria-hidden="true" />
          <button
            aria-controls={inspectorId}
            aria-label={`${M.companyWorld.openProfile}: ${data.company.name}`}
            aria-pressed={selectedKey === data.company.key}
            className="world-core-node"
            onClick={() => onSelect(data.company.key)}
            type="button"
          >
            <span className="world-core-kicker">{M.companyWorld.operatingCenter}</span>
            <strong>{data.company.name}</strong>
            <span>{data.company.slug}</span>
            <small>{M.companyWorld.companyCoreHint}</small>
          </button>
        </section>

        <BoardZone
          className={styles.networkZone}
          count={confirmedNetworkCount}
          description={M.companyWorld.confirmedNetworkDescription}
          title={M.companyWorld.confirmedNetwork}
        >
          {model.organizationGroups.length > 0 ? (
            <div className="world-organization-stack">
              {model.organizationGroups.map(({ organization, people }) => (
                <article
                  className={`world-organization-card world-organization-card--${organization.relationship_kind}`}
                  key={organization.key}
                >
                  <BoardNode
                    badge={organizationRelationshipKindLabel(
                      organization.relationship_kind
                    )}
                    inspectorId={inspectorId}
                    isSelected={selectedKey === organization.key}
                    label={organization.name ?? organization.domain ?? M.common.unknown}
                    meta={organization.domain ?? M.companyWorld.domainNotSpecified}
                    onSelect={() => onSelect(organization.key)}
                    tone="confirmed"
                  />
                  {people.length > 0 ? (
                    <div
                      className="world-affiliated-people"
                      aria-label={M.companyWorld.confirmedPeopleInOrganization}
                      role="group"
                    >
                      {people.map((person) => (
                        <button
                          aria-controls={inspectorId}
                          aria-label={`${M.companyWorld.openProfile}: ${person.display_name ?? person.email}`}
                          aria-pressed={selectedKey === person.key}
                          className="world-person-chip"
                          key={person.key}
                          onClick={() => onSelect(person.key)}
                          type="button"
                        >
                          <span aria-hidden="true">{initials(person.display_name ?? person.email)}</span>
                          <strong>{person.display_name ?? person.email}</strong>
                          <small>
                            {person.relationship_type
                              ? relationshipTypeLabel(person.relationship_type)
                              : M.companyWorld.relationshipNotSpecified}
                          </small>
                        </button>
                      ))}
                    </div>
                  ) : (
                    <p className="world-organization-empty">
                      {M.companyWorld.noConfirmedPeopleInOrganization}
                    </p>
                  )}
                </article>
              ))}
            </div>
          ) : (
            <p className="world-zone-empty">{M.companyWorld.noConfirmedOrganizations}</p>
          )}

          {model.standaloneConfirmedPeople.length > 0 ? (
            <section className="world-standalone-people">
              <h4>{M.companyWorld.standaloneConfirmedPeople}</h4>
              <div className="world-node-stack">
                {model.standaloneConfirmedPeople.map((person) => (
                  <BoardNode
                    badge={M.companyWorld.confirmed}
                    inspectorId={inspectorId}
                    isSelected={selectedKey === person.key}
                    key={person.key}
                    label={person.display_name ?? person.email}
                    meta={M.companyWorld.noConfirmedAffiliation}
                    onSelect={() => onSelect(person.key)}
                    tone="confirmed"
                  />
                ))}
              </div>
            </section>
          ) : null}
        </BoardZone>

        <BoardZone
          className={styles.reviewZone}
          count={model.pendingCount}
          countIsLowerBound={data.window.truncated}
          description={M.companyWorld.discoveryDescription}
          title={M.companyWorld.discoveryZone}
        >
          {model.pendingCount > 0 ? (
            <div className="world-discovery-grid">
              <section>
                <h4>{M.companyWorld.organizationsSection}</h4>
                <div className="world-node-stack">
                  {data.organizations.map((organization) => (
                    <BoardNode
                      badge={M.companyWorld.organizationNeedsConfirmation}
                      inspectorId={inspectorId}
                      isSelected={selectedKey === organization.key}
                      key={organization.key}
                      label={organization.name ?? organization.domain}
                      meta={`${lowerBoundCount(organization.people_count, data.window.truncated)} · ${M.companyWorld.people.toLocaleLowerCase()} · ${lowerBoundCount(organization.interaction_count, data.window.truncated)} ${M.companyWorld.interactions.toLocaleLowerCase()}`}
                      onSelect={() => onSelect(organization.key)}
                      tone="candidate"
                    />
                  ))}
                  {data.organizations.length === 0 ? (
                    <p className="world-zone-empty">{M.companyWorld.noOrganizations}</p>
                  ) : null}
                </div>
              </section>
              <section>
                <h4>{M.companyWorld.contactsSection}</h4>
                <div className="world-node-stack">
                  {data.people.external_candidates.map((person) => (
                    <BoardNode
                      badge={M.companyWorld.candidate}
                      hint={
                        person.organization_key
                          ? M.companyWorld.domainSignalNotAffiliation
                          : undefined
                      }
                      inspectorId={inspectorId}
                      isSelected={selectedKey === person.key}
                      key={person.key}
                      label={person.display_name ?? person.email}
                      meta={`${lowerBoundCount(person.interaction_count, data.window.truncated)} · ${M.companyWorld.interactions.toLocaleLowerCase()}`}
                      onSelect={() => onSelect(person.key)}
                      tone="candidate"
                    />
                  ))}
                  {data.people.external_candidates.length === 0 ? (
                    <p className="world-zone-empty">{M.companyWorld.noContacts}</p>
                  ) : null}
                </div>
              </section>
            </div>
          ) : (
            <p className="world-zone-empty world-zone-empty--complete">
              {data.window.truncated
                ? M.companyWorld.discoveryCompleteInWindow
                : M.companyWorld.discoveryComplete}
            </p>
          )}
        </BoardZone>
      </div>
    </section>
  );
}

function BoardZone({
  children,
  className,
  count,
  countIsLowerBound = false,
  description,
  title
}: {
  children: ReactNode;
  className: string;
  count: number;
  countIsLowerBound?: boolean;
  description: string;
  title: string;
}) {
  return (
    <section
      className={`${styles.zone} ${className}`}
      data-empty={count === 0 ? "true" : undefined}
    >
      <header>
        <div>
          <h3>{title}</h3>
          <p>{description}</p>
        </div>
        <span
          aria-label={`${title}: ${lowerBoundCount(count, countIsLowerBound)}`}
          role="status"
        >
          {lowerBoundCount(count, countIsLowerBound)}
        </span>
      </header>
      {children}
    </section>
  );
}

function BoardNode({
  badge,
  hint,
  inspectorId,
  isSelected,
  label,
  meta,
  onSelect,
  tone
}: {
  badge: string;
  hint?: string;
  inspectorId: string;
  isSelected: boolean;
  label: string;
  meta?: string;
  onSelect: () => void;
  tone: "candidate" | "confirmed" | "team";
}) {
  return (
    <button
      aria-controls={inspectorId}
      aria-label={`${M.companyWorld.openProfile}: ${label}`}
      aria-pressed={isSelected}
      className={`world-node world-node--${tone}${isSelected ? " selected" : ""}`}
      onClick={onSelect}
      type="button"
    >
      <span className="world-avatar" aria-hidden="true">
        {initials(label)}
      </span>
      <span className="world-node-copy">
        <strong>{label}</strong>
        {meta ? <span>{meta}</span> : null}
        {hint ? <small>{hint}</small> : null}
      </span>
      <span className={`world-state world-state--${tone}`}>{badge}</span>
    </button>
  );
}

function ZoneFilter({
  active,
  count,
  countIsLowerBound = false,
  label,
  onClick,
  tone = "default"
}: {
  active: boolean;
  count: number;
  countIsLowerBound?: boolean;
  label: string;
  onClick: () => void;
  tone?: "candidate" | "default";
}) {
  return (
    <button
      aria-pressed={active}
      data-tone={tone}
      onClick={onClick}
      type="button"
    >
      <span>{label}</span>
      <strong>{lowerBoundCount(count, countIsLowerBound)}</strong>
    </button>
  );
}

function lowerBoundCount(value: number, isLowerBound: boolean): string {
  return `${isLowerBound ? "≥" : ""}${value}`;
}

function roleLabel(role: CompanyMapResponse["people"]["internal"][number]["role"]): string {
  return M.companyWorld.roles[role];
}

function relationshipTypeLabel(
  value: CompanyMapConfirmedExternalPerson["relationship_type"]
): string {
  if (!value || !(value in M.companyWorld.relationshipTypes)) {
    return M.companyWorld.relationshipNotSpecified;
  }
  return M.companyWorld.relationshipTypes[
    value as keyof typeof M.companyWorld.relationshipTypes
  ];
}

function organizationRelationshipKindLabel(
  value: CompanyMapConfirmedOrganization["relationship_kind"]
): string {
  if (!(value in M.companyWorld.organizationRelationshipKinds)) {
    return M.companyWorld.organizationRelationshipKinds.unknown;
  }
  return M.companyWorld.organizationRelationshipKinds[
    value as keyof typeof M.companyWorld.organizationRelationshipKinds
  ];
}

function initials(label: string): string {
  const parts = label
    .replace(/@.*$/, "")
    .split(/[\s._-]+/)
    .filter(Boolean)
    .slice(0, 2);
  return parts.map((part) => part[0]?.toUpperCase()).join("") || "?";
}
