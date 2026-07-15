"use client";

import Link from "next/link";
import { useId, useState } from "react";

import {
  buildCompanyWorldProfileTarget,
  type CompanyWorldProfileTarget
} from "../lib/company-world-profile";
import { M } from "../lib/messages";
import type { CompanyMapResponse } from "../lib/types";
import styles from "./living-world-mini-map.module.css";

const COPY = M.livingHq.miniMap;

type LivingWorldNodeTone = "candidate" | "company" | "confirmed" | "team";

export type LivingWorldNode = {
  detail: string;
  evidenceCount: number;
  key: string;
  label: string;
  profileTarget: CompanyWorldProfileTarget | null;
  statusLabel: string;
  tone: LivingWorldNodeTone;
  typeLabel: string;
};

export type LivingWorldMiniMapModel = {
  candidates: LivingWorldNode[];
  company: LivingWorldNode;
  confirmedNetwork: LivingWorldNode[];
  internalPeople: LivingWorldNode[];
};

type LivingWorldMiniMapProps = {
  data: CompanyMapResponse | null;
  onRetry?: () => void;
  state?: LivingWorldMiniMapState;
  workspaceName: string;
};

export type LivingWorldMiniMapState = "empty" | "error" | "ready";

export function buildLivingWorldMiniMapModel(
  data: CompanyMapResponse | null,
  workspaceName: string
): LivingWorldMiniMapModel {
  if (!data) {
    return {
      candidates: [],
      company: {
        detail: COPY.emptyDetail,
        evidenceCount: 0,
        key: "workspace:empty",
        label: workspaceName || COPY.companyFallback,
        profileTarget: null,
        statusLabel: COPY.waitingData,
        tone: "company",
        typeLabel: COPY.companyCenter
      },
      confirmedNetwork: [],
      internalPeople: []
    };
  }

  const confirmedOrganizations = new Map(
    data.confirmed_organizations.map((organization) => [organization.key, organization])
  );
  const internalPeople: LivingWorldNode[] = data.people.internal.map((person) => ({
    detail: person.email,
    evidenceCount: person.source_refs.length,
    key: person.key,
    label: person.name ?? person.email,
    profileTarget: buildCompanyWorldProfileTarget(data, person.key),
    statusLabel: roleLabel(person.role),
    tone: "team",
    typeLabel: COPY.employee
  }));

  const confirmedOrganizationsNodes: LivingWorldNode[] =
    data.confirmed_organizations.map((organization) => ({
      detail: interactionLabel(
        organization.interaction_count,
        data.window.truncated
      ),
      evidenceCount: organization.source_refs.length,
      key: organization.key,
      label: organization.name ?? organization.domain ?? COPY.organizationFallback,
      profileTarget: buildCompanyWorldProfileTarget(data, organization.key),
      statusLabel: organizationRelationshipLabel(organization.relationship_kind),
      tone: "confirmed",
      typeLabel: COPY.confirmedOrganization
    }));

  const confirmedPeople: LivingWorldNode[] = data.people.confirmed_external.map(
    (person) => {
      const organization = person.organization_key
        ? confirmedOrganizations.get(person.organization_key)
        : undefined;
      const hasDurableAffiliation = Boolean(
        organization &&
          person.organization_id === organization.organization_id &&
          person.relationship_type !== null
      );
      const relationship = person.relationship_type
        ? relationshipLabel(person.relationship_type)
        : COPY.unspecifiedRole;
      const organizationLabel = hasDurableAffiliation
        ? organization?.name ?? organization?.domain ?? null
        : null;

      return {
        detail: [
          relationship,
          organizationLabel,
          interactionLabel(person.interaction_count, data.window.truncated)
        ]
          .filter((part): part is string => Boolean(part))
          .join(" · "),
        evidenceCount: person.source_refs.length,
        key: person.key,
        label: person.display_name ?? person.email,
        profileTarget: buildCompanyWorldProfileTarget(data, person.key),
        statusLabel: COPY.confirmed,
        tone: "confirmed",
        typeLabel: COPY.externalContact
      };
    }
  );

  const candidateOrganizations: LivingWorldNode[] = data.organizations.map(
    (organization) => ({
      detail: `${peopleLabel(
        organization.people_count,
        data.window.truncated
      )} · ${interactionLabel(
        organization.interaction_count,
        data.window.truncated
      )}`,
      evidenceCount: organization.source_refs.length,
      key: organization.key,
      label: organization.name ?? organization.domain,
      profileTarget: buildCompanyWorldProfileTarget(data, organization.key),
      statusLabel: COPY.needsConfirmation,
      tone: "candidate",
      typeLabel: COPY.possibleOrganization
    })
  );
  const candidatePeople: LivingWorldNode[] = data.people.external_candidates.map(
    (person) => ({
      detail: interactionLabel(person.interaction_count, data.window.truncated),
      evidenceCount: person.source_refs.length,
      key: person.key,
      label: person.display_name ?? person.email,
      profileTarget: buildCompanyWorldProfileTarget(data, person.key),
      statusLabel: COPY.needsConfirmation,
      tone: "candidate",
      typeLabel: COPY.possibleContact
    })
  );

  return {
    candidates: [...candidateOrganizations, ...candidatePeople],
    company: {
      detail: COPY.companyDetail(
        data.summary.internal_people,
        data.summary.touchpoints_in_window,
        data.window.truncated
      ),
      evidenceCount: data.company.source_refs.length,
      key: data.company.key,
      label: data.company.name || workspaceName || COPY.companyFallback,
      profileTarget: buildCompanyWorldProfileTarget(data, data.company.key),
      statusLabel: COPY.activeContour,
      tone: "company",
      typeLabel: COPY.companyCenter
    },
    confirmedNetwork: [...confirmedOrganizationsNodes, ...confirmedPeople],
    internalPeople
  };
}

export function LivingWorldMiniMap({
  data,
  onRetry,
  state = data ? "ready" : "empty",
  workspaceName
}: LivingWorldMiniMapProps) {
  const model = buildLivingWorldMiniMapModel(data, workspaceName);
  const visibleInternalPeople = model.internalPeople.slice(0, 4);
  const visibleConfirmedNetwork = model.confirmedNetwork.slice(0, 5);
  const visibleCandidates = model.candidates.slice(0, 6);
  const inspectorId = useId();
  const allNodes = [
    model.company,
    ...model.internalPeople,
    ...model.confirmedNetwork,
    ...model.candidates
  ];
  const [selectedKey, setSelectedKey] = useState(model.company.key);
  const selectedNode =
    allNodes.find((node) => node.key === selectedKey) ?? model.company;

  if (!data) {
    const isError = state === "error";
    return (
      <section className={styles.root} aria-labelledby={`${inspectorId}-title`}>
        <header className={styles.header}>
          <div>
            <span className={styles.eyebrow}>{COPY.eyebrow}</span>
            <h2 id={`${inspectorId}-title`}>{COPY.title}</h2>
            <p>{COPY.description}</p>
          </div>
        </header>
        <div
          className={styles.unavailable}
          data-state={isError ? "error" : "empty"}
          role={isError ? "alert" : "status"}
        >
          <span className={styles.unavailableMark} aria-hidden="true">
            {isError ? "!" : "+"}
          </span>
          <div>
            <h3>{isError ? COPY.errorTitle : COPY.emptyTitle}</h3>
            <p>{isError ? COPY.errorDescription : COPY.emptyDescription}</p>
          </div>
          {isError && onRetry ? (
            <button type="button" onClick={onRetry}>
              {COPY.retry}
            </button>
          ) : null}
        </div>
      </section>
    );
  }

  return (
    <section className={styles.root} aria-labelledby={`${inspectorId}-title`}>
      <header className={styles.header}>
        <div>
          <span className={styles.eyebrow}>{COPY.eyebrow}</span>
          <h2 id={`${inspectorId}-title`}>{COPY.title}</h2>
          <p>{COPY.description}</p>
        </div>
        <div className={styles.legend} aria-label={COPY.legendLabel}>
          <span data-tone="confirmed">{COPY.legendConfirmed}</span>
          <span data-tone="candidate">{COPY.legendCandidate}</span>
        </div>
      </header>

      <div className={styles.layout}>
        <div className={styles.stage}>
          <MapZone
            emptyLabel={COPY.teamEmpty}
            label={COPY.team}
            nodes={visibleInternalPeople}
            onSelect={setSelectedKey}
            selectedKey={selectedNode.key}
            inspectorId={inspectorId}
            totalCount={model.internalPeople.length}
          />

          <div className={styles.core}>
            <span className={styles.orbit} aria-hidden="true" />
            <MapNodeButton
              inspectorId={inspectorId}
              node={model.company}
              onSelect={setSelectedKey}
              selected={selectedNode.key === model.company.key}
            />
          </div>

          <MapZone
            emptyLabel={COPY.confirmedNetworkEmpty}
            label={COPY.confirmedNetwork}
            nodes={visibleConfirmedNetwork}
            onSelect={setSelectedKey}
            selectedKey={selectedNode.key}
            inspectorId={inspectorId}
            totalCount={model.confirmedNetwork.length}
          />

          <MapZone
            className={styles.candidateZone}
            emptyLabel={
              data.window.truncated
                ? COPY.candidatesEmptyInWindow
                : COPY.candidatesEmpty
            }
            label={COPY.unknownZone}
            nodes={visibleCandidates}
            onSelect={setSelectedKey}
            selectedKey={selectedNode.key}
            inspectorId={inspectorId}
            totalCount={model.candidates.length}
            totalIsLowerBound={data.window.truncated}
          />
        </div>

        <aside
          aria-live="polite"
          aria-labelledby={`${inspectorId}-inspector-title`}
          className={styles.inspector}
          id={inspectorId}
        >
          <span className={styles.inspectorType}>{selectedNode.typeLabel}</span>
          <h3 id={`${inspectorId}-inspector-title`}>{selectedNode.label}</h3>
          <span className={styles.status} data-tone={selectedNode.tone}>
            {selectedNode.statusLabel}
          </span>
          <p>{selectedNode.detail}</p>
          <small>
            {selectedNode.evidenceCount > 0
              ? `${selectedNode.evidenceCount} ${evidenceWord(
                  selectedNode.evidenceCount
                )}`
              : COPY.noEvidence}
          </small>
          {selectedNode.profileTarget ? (
            <Link
              className={styles.inspectorAction}
              href={selectedNode.profileTarget.href}
            >
              {COPY.openFullProfile}
              <span aria-hidden="true">→</span>
            </Link>
          ) : null}
        </aside>
      </div>
    </section>
  );
}

function MapZone({
  className,
  emptyLabel,
  inspectorId,
  label,
  nodes,
  onSelect,
  selectedKey,
  totalCount,
  totalIsLowerBound = false
}: {
  className?: string;
  emptyLabel: string;
  inspectorId: string;
  label: string;
  nodes: LivingWorldNode[];
  onSelect: (key: string) => void;
  selectedKey: string;
  totalCount: number;
  totalIsLowerBound?: boolean;
}) {
  const displayedCount = `${totalIsLowerBound ? "≥" : ""}${totalCount}`;
  return (
    <section
      className={[styles.zone, className].filter(Boolean).join(" ")}
      data-empty={nodes.length === 0 ? "true" : undefined}
    >
      <header>
        <h3>{label}</h3>
        <span aria-label={`${label}: ${displayedCount}`}>{displayedCount}</span>
      </header>
      {nodes.length > 0 ? (
        <div className={styles.nodes}>
          {nodes.map((node) => (
            <MapNodeButton
              inspectorId={inspectorId}
              key={node.key}
              node={node}
              onSelect={onSelect}
              selected={selectedKey === node.key}
            />
          ))}
        </div>
      ) : (
        <p className={styles.empty}>{emptyLabel}</p>
      )}
      {totalCount > nodes.length ? (
        <p className={styles.more}>
          {COPY.moreNodes(totalCount - nodes.length, totalIsLowerBound)}
        </p>
      ) : null}
    </section>
  );
}

function MapNodeButton({
  inspectorId,
  node,
  onSelect,
  selected
}: {
  inspectorId: string;
  node: LivingWorldNode;
  onSelect: (key: string) => void;
  selected: boolean;
}) {
  return (
    <button
      aria-controls={inspectorId}
      aria-label={COPY.openProfile(node.label)}
      aria-pressed={selected}
      className={styles.node}
      data-tone={node.tone}
      onClick={() => onSelect(node.key)}
      type="button"
    >
      <span className={styles.avatar} aria-hidden="true">
        {initials(node.label)}
      </span>
      <span className={styles.nodeCopy}>
        <strong>{node.label}</strong>
        <small>{node.statusLabel}</small>
      </span>
    </button>
  );
}

function initials(value: string): string {
  const words = value.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) {
    return "?";
  }
  return words
    .slice(0, 2)
    .map((word) => word[0]?.toLocaleUpperCase("ru-RU") ?? "")
    .join("");
}

function roleLabel(role: string): string {
  if (role === "owner") return COPY.roles.owner;
  if (role === "admin") return COPY.roles.admin;
  if (role === "viewer") return COPY.roles.viewer;
  return COPY.roles.member;
}

function relationshipLabel(relationship: string): string {
  const labels: Record<string, string> = {
    account_owner: COPY.relationships.account_owner,
    advisor: COPY.relationships.advisor,
    contact: COPY.relationships.contact,
    decision_maker: COPY.relationships.decision_maker,
    employee: COPY.relationships.employee,
    other: COPY.relationships.other
  };
  return labels[relationship] ?? COPY.relationships.fallback;
}

function organizationRelationshipLabel(relationship: string): string {
  const labels: Record<string, string> = {
    customer: COPY.organizationRelationships.customer,
    other: COPY.organizationRelationships.other,
    partner: COPY.organizationRelationships.partner,
    prospect: COPY.organizationRelationships.prospect,
    unknown: COPY.organizationRelationships.unknown,
    vendor: COPY.organizationRelationships.vendor
  };
  return labels[relationship] ?? COPY.organizationRelationships.fallback;
}

function interactionLabel(count: number, isLowerBound = false): string {
  return COPY.interactionLabel(count, isLowerBound);
}

function peopleLabel(count: number, isLowerBound = false): string {
  return COPY.peopleLabel(count, isLowerBound);
}

function evidenceWord(count: number): string {
  return COPY.evidenceWord(count);
}
