"use client";

import { useEffect, useState } from "react";
import type { ReactNode } from "react";

import { fetchCompanyMap } from "../lib/api";
import { M } from "../lib/messages";
import { useWorkspaceId } from "../lib/session";
import type {
  CompanyBrainSourceRef,
  CompanyMapExternalCandidate,
  CompanyMapInternalPerson,
  CompanyMapOrganizationCandidate,
  CompanyMapResponse,
  CompanyMapTouchpoint
} from "../lib/types";
import { EmptyState } from "./EmptyState";
import { ErrorState } from "./ErrorState";
import { LoadingState } from "./LoadingState";
import { SourceLink } from "./SourceLink";
import { StatusCard } from "./StatusCard";

export type CompanyWorldStatus =
  | "loading"
  | "ready"
  | "empty"
  | "error"
  | "missing";

type CompanyWorldPanelProps = {
  refreshSignal?: number;
};

type CompanyWorldPanelViewProps = {
  data: CompanyMapResponse | null;
  error: string | null;
  onRetry?: () => void;
  status: CompanyWorldStatus;
};

export function CompanyWorldPanel({ refreshSignal = 0 }: CompanyWorldPanelProps) {
  const workspaceId = useWorkspaceId();
  const [data, setData] = useState<CompanyMapResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [status, setStatus] = useState<CompanyWorldStatus>("loading");

  useEffect(() => {
    if (!workspaceId) {
      setData(null);
      setError(null);
      setStatus("missing");
      return;
    }

    let cancelled = false;
    setStatus("loading");
    setError(null);
    fetchCompanyMap(workspaceId)
      .then((payload) => {
        if (cancelled) {
          return;
        }
        setData(payload);
        setStatus(payload.summary.internal_people > 0 ? "ready" : "empty");
      })
      .catch((caught: unknown) => {
        if (cancelled) {
          return;
        }
        setData(null);
        setError(caught instanceof Error ? caught.message : M.common.requestFailed);
        setStatus("error");
      });

    return () => {
      cancelled = true;
    };
  }, [workspaceId, refreshSignal, reloadKey]);

  return (
    <CompanyWorldPanelView
      data={data}
      error={error}
      onRetry={() => setReloadKey((current) => current + 1)}
      status={status}
    />
  );
}

export function CompanyWorldPanelView({
  data,
  error,
  onRetry,
  status
}: CompanyWorldPanelViewProps) {
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const effectiveSelectedKey = validSelectedKey(data, selectedKey);

  return (
    <section className="panel company-world" aria-labelledby="company-world-title">
      <div className="section-header company-world-header">
        <div>
          <span className="eyebrow">{M.companyWorld.eyebrow}</span>
          <h2 id="company-world-title">{M.companyWorld.title}</h2>
        </div>
        <span className="badge world-badge">{M.companyWorld.badge}</span>
      </div>

      {status === "loading" ? <LoadingState label={M.companyWorld.loading} /> : null}

      {status === "missing" ? (
        <EmptyState
          description={M.companyWorld.noWorkspaceDescription}
          title={M.common.noWorkspaceTitle}
        />
      ) : null}

      {status === "error" ? (
        <>
          <ErrorState
            description={error ?? M.companyWorld.unavailableDescription}
            title={M.companyWorld.unavailableTitle}
          />
          <button className="button secondary" onClick={onRetry} type="button">
            {M.common.retry}
          </button>
        </>
      ) : null}

      {status === "empty" ? (
        <EmptyState
          description={M.companyWorld.emptyDescription}
          title={M.companyWorld.emptyTitle}
        />
      ) : null}

      {data && status === "ready" ? (
        <>
          <p className="muted company-world-intro">{M.companyWorld.intro}</p>
          <section className="grid" aria-label={M.companyWorld.summaryLabel}>
            <StatusCard
              description={M.companyWorld.internalPeopleDescription}
              title={M.companyWorld.internalPeople}
              value={String(data.summary.internal_people)}
            />
            <StatusCard
              description={M.companyWorld.externalPeopleDescription}
              title={M.companyWorld.externalPeople}
              value={String(data.summary.external_contacts_in_window)}
            />
            <StatusCard
              description={M.companyWorld.organizationsDescription}
              title={M.companyWorld.organizations}
              value={String(data.summary.organizations_in_window)}
            />
            <StatusCard
              description={M.companyWorld.touchpointsDescription}
              title={M.companyWorld.touchpoints}
              value={String(data.summary.touchpoints_in_window)}
            />
          </section>

          <div className="company-world-layout">
            <div className="company-world-map">
              <WorldSection title={M.companyWorld.companySection}>
                <WorldNode
                  badge={M.companyWorld.confirmed}
                  isSelected={effectiveSelectedKey === data.company.key}
                  label={data.company.name}
                  meta={data.company.slug}
                  onSelect={() => setSelectedKey(data.company.key)}
                  tone="confirmed"
                />
              </WorldSection>

              <WorldSection title={M.companyWorld.teamSection}>
                <div className="world-node-grid">
                  {data.people.internal.map((person) => (
                    <WorldNode
                      badge={roleLabel(person.role)}
                      isSelected={effectiveSelectedKey === person.key}
                      key={person.key}
                      label={person.name ?? person.email}
                      meta={person.email}
                      onSelect={() => setSelectedKey(person.key)}
                      tone="confirmed"
                    />
                  ))}
                </div>
              </WorldSection>

              <WorldSection title={M.companyWorld.contactsSection}>
                {data.people.external_candidates.length > 0 ? (
                  <div className="world-node-grid">
                    {data.people.external_candidates.map((person) => (
                      <WorldNode
                        badge={M.companyWorld.candidate}
                        isSelected={effectiveSelectedKey === person.key}
                        key={person.key}
                        label={person.display_name ?? person.email}
                        meta={`${person.interaction_count} · ${M.companyWorld.interactions.toLocaleLowerCase()}`}
                        onSelect={() => setSelectedKey(person.key)}
                        tone="candidate"
                      />
                    ))}
                  </div>
                ) : (
                  <p className="muted">{M.companyWorld.noContacts}</p>
                )}
              </WorldSection>

              <WorldSection title={M.companyWorld.organizationsSection}>
                {data.organizations.length > 0 ? (
                  <div className="world-node-grid">
                    {data.organizations.map((organization) => (
                      <WorldNode
                        badge={M.companyWorld.needsConfirmation}
                        isSelected={effectiveSelectedKey === organization.key}
                        key={organization.key}
                        label={organization.name ?? organization.domain}
                        meta={`${organization.people_count} · ${M.companyWorld.people.toLocaleLowerCase()}`}
                        onSelect={() => setSelectedKey(organization.key)}
                        tone="candidate"
                      />
                    ))}
                  </div>
                ) : (
                  <p className="muted">{M.companyWorld.noOrganizations}</p>
                )}
              </WorldSection>
            </div>

            <ProfilePanel data={data} selectedKey={effectiveSelectedKey} />
          </div>

          <TouchpointTimeline
            onSelect={setSelectedKey}
            selectedKey={effectiveSelectedKey}
            touchpoints={data.touchpoints}
          />
          <p className="muted world-window">
            {M.companyWorld.windowLabel}: {data.window.gmail_messages_considered} /{" "}
            {data.window.gmail_messages_available}
            {data.window.truncated ? ` · ${M.companyWorld.windowTruncated}` : ""}
          </p>
          {data.warnings.length > 0 ? (
            <aside className="world-warnings" aria-label={M.common.warnings}>
              <strong>{M.common.warnings}</strong>
              <ul>
                {data.warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            </aside>
          ) : null}
          <div className="world-capabilities" aria-label={M.companyWorld.capabilities}>
            <span>{data.capabilities.read_only ? M.companyWorld.readOnly : ""}</span>
            <span>
              {!data.capabilities.provider_calls ? M.companyWorld.noProviderCalls : ""}
            </span>
            <span>{!data.capabilities.llm_used ? M.companyWorld.noLlm : ""}</span>
            <span>{!data.is_live ? M.companyWorld.localProjection : ""}</span>
          </div>
          <p className="muted world-boundary">{M.companyWorld.boundary}</p>
        </>
      ) : null}
    </section>
  );
}

export function validSelectedKey(
  data: CompanyMapResponse | null,
  selectedKey: string | null
): string | null {
  if (!data) {
    return null;
  }
  const validKeys = new Set([
    data.company.key,
    ...data.people.internal.map((person) => person.key),
    ...data.people.external_candidates.map((person) => person.key),
    ...data.organizations.map((organization) => organization.key),
    ...data.touchpoints.map((touchpoint) => touchpoint.key)
  ]);
  return selectedKey && validKeys.has(selectedKey) ? selectedKey : data.company.key;
}

function WorldSection({ children, title }: { children: ReactNode; title: string }) {
  return (
    <section className="world-section">
      <h3>{title}</h3>
      {children}
    </section>
  );
}

function WorldNode({
  badge,
  isSelected,
  label,
  meta,
  onSelect,
  tone
}: {
  badge: string;
  isSelected: boolean;
  label: string;
  meta: string;
  onSelect: () => void;
  tone: "confirmed" | "candidate";
}) {
  return (
    <button
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
        <span>{meta}</span>
      </span>
      <span className={`world-state world-state--${tone}`}>{badge}</span>
    </button>
  );
}

function ProfilePanel({ data, selectedKey }: { data: CompanyMapResponse; selectedKey: string | null }) {
  const internal = data.people.internal.find((person) => person.key === selectedKey);
  const external = data.people.external_candidates.find(
    (person) => person.key === selectedKey
  );
  const organization = data.organizations.find((item) => item.key === selectedKey);
  const touchpoint = data.touchpoints.find((item) => item.key === selectedKey);

  return (
    <aside className="world-profile" aria-live="polite" aria-label={M.companyWorld.profileTitle}>
      {internal ? <InternalPersonProfile person={internal} /> : null}
      {external ? <ExternalPersonProfile person={external} /> : null}
      {organization ? <OrganizationProfile organization={organization} /> : null}
      {touchpoint ? <TouchpointProfile touchpoint={touchpoint} /> : null}
      {!internal && !external && !organization && !touchpoint ? (
        <>
          <span className="eyebrow">{M.companyWorld.companyProfile}</span>
          <h3>{data.company.name}</h3>
          <dl className="world-profile-meta">
            <ProfileMeta label={M.companyWorld.status} value={data.company.status} />
            <ProfileMeta label={M.companyWorld.workspace} value={data.company.slug} />
          </dl>
          <EvidenceList refs={data.company.source_refs} />
        </>
      ) : null}
    </aside>
  );
}

function InternalPersonProfile({ person }: { person: CompanyMapInternalPerson }) {
  return (
    <>
      <span className="eyebrow">{M.companyWorld.personProfile}</span>
      <h3>{person.name ?? person.email}</h3>
      <span className="world-state world-state--confirmed">{M.companyWorld.confirmed}</span>
      <dl className="world-profile-meta">
        <ProfileMeta label={M.companyWorld.email} value={person.email} />
        <ProfileMeta label={M.companyWorld.role} value={roleLabel(person.role)} />
        <ProfileMeta label={M.companyWorld.status} value={person.status} />
      </dl>
      <EvidenceList refs={person.source_refs} />
    </>
  );
}

function ExternalPersonProfile({ person }: { person: CompanyMapExternalCandidate }) {
  return (
    <>
      <span className="eyebrow">{M.companyWorld.personProfile}</span>
      <h3>{person.display_name ?? person.email}</h3>
      <span className="world-state world-state--candidate">
        {M.companyWorld.needsConfirmation}
      </span>
      <dl className="world-profile-meta">
        <ProfileMeta label={M.companyWorld.email} value={person.email} />
        <ProfileMeta
          label={M.companyWorld.interactions}
          value={String(person.interaction_count)}
        />
        <ProfileMeta
          label={M.companyWorld.lastInteraction}
          value={formatDate(person.last_interaction_at)}
        />
      </dl>
      <EvidenceList refs={person.source_refs} />
    </>
  );
}

function OrganizationProfile({
  organization
}: {
  organization: CompanyMapOrganizationCandidate;
}) {
  return (
    <>
      <span className="eyebrow">{M.companyWorld.organizationProfile}</span>
      <h3>{organization.name ?? organization.domain}</h3>
      <span className="world-state world-state--candidate">
        {M.companyWorld.needsConfirmation}
      </span>
      <dl className="world-profile-meta">
        <ProfileMeta label={M.companyWorld.domain} value={organization.domain} />
        <ProfileMeta label={M.companyWorld.people} value={String(organization.people_count)} />
        <ProfileMeta
          label={M.companyWorld.interactions}
          value={String(organization.interaction_count)}
        />
        <ProfileMeta
          label={M.companyWorld.lastInteraction}
          value={formatDate(organization.last_interaction_at)}
        />
      </dl>
      <EvidenceList refs={organization.source_refs} />
    </>
  );
}

function TouchpointProfile({ touchpoint }: { touchpoint: CompanyMapTouchpoint }) {
  return (
    <>
      <span className="eyebrow">{M.companyWorld.touchpointProfile}</span>
      <h3>{touchpoint.subject}</h3>
      <dl className="world-profile-meta">
        <ProfileMeta
          label={M.companyWorld.direction}
          value={M.companyWorld.directions[touchpoint.direction]}
        />
        <ProfileMeta
          label={M.companyWorld.lastInteraction}
          value={formatDate(touchpoint.occurred_at)}
        />
      </dl>
      <EvidenceList refs={touchpoint.source_refs} />
      {touchpoint.source_url ? (
        <SourceLink url={touchpoint.source_url}>{M.common.openSource}</SourceLink>
      ) : null}
    </>
  );
}

function TouchpointTimeline({
  onSelect,
  selectedKey,
  touchpoints
}: {
  onSelect: (key: string) => void;
  selectedKey: string | null;
  touchpoints: CompanyMapTouchpoint[];
}) {
  return (
    <section className="world-timeline" aria-labelledby="world-timeline-title">
      <h3 id="world-timeline-title">{M.companyWorld.timelineSection}</h3>
      {touchpoints.length > 0 ? (
        <ol>
          {touchpoints.map((touchpoint) => (
            <li key={touchpoint.key}>
              <button
                aria-pressed={selectedKey === touchpoint.key}
                className="timeline-event"
                onClick={() => onSelect(touchpoint.key)}
                type="button"
              >
                <span className="timeline-marker" aria-hidden="true" />
                <span>
                  <strong>{touchpoint.subject}</strong>
                  <small>
                    {M.companyWorld.directions[touchpoint.direction]} · {formatDate(touchpoint.occurred_at)}
                  </small>
                </span>
              </button>
            </li>
          ))}
        </ol>
      ) : (
        <p className="muted">{M.companyWorld.noTouchpoints}</p>
      )}
    </section>
  );
}

function ProfileMeta({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function EvidenceList({ refs }: { refs: CompanyBrainSourceRef[] }) {
  return (
    <section className="world-evidence" aria-label={M.companyWorld.evidence}>
      <h4>{M.companyWorld.evidence}</h4>
      {refs.length > 0 ? (
        <ul>
          {refs.map((ref) => (
            <li key={ref.id}>
              <SourceLink url={ref.url}>{ref.label}</SourceLink>
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted">{M.companyWorld.noEvidence}</p>
      )}
    </section>
  );
}

function roleLabel(role: CompanyMapInternalPerson["role"]): string {
  return M.companyWorld.roles[role];
}

function initials(label: string): string {
  const parts = label
    .replace(/@.*$/, "")
    .split(/[\s._-]+/)
    .filter(Boolean)
    .slice(0, 2);
  return parts.map((part) => part[0]?.toUpperCase()).join("") || "?";
}

function formatDate(value: string | null): string {
  if (!value) {
    return M.common.unknown;
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return M.common.unknown;
  }
  return new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(date);
}
