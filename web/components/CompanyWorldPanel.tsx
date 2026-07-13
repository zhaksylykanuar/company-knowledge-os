"use client";

import { useEffect, useRef, useState } from "react";
import type { ReactNode, RefObject } from "react";

import {
  ApiRequestError,
  fetchCompanyMap,
  resolveCompanyMapCandidate
} from "../lib/api";
import { M } from "../lib/messages";
import { useWorkspaceId } from "../lib/session";
import type {
  CompanyBrainSourceRef,
  CompanyMapConfirmedExternalPerson,
  CompanyMapConfirmedOrganization,
  CompanyMapExternalCandidate,
  CompanyMapInternalPerson,
  CompanyMapOrganizationRelationshipKind,
  CompanyMapOrganizationCandidate,
  CompanyMapRelationshipType,
  CompanyMapResolutionDecision,
  CompanyMapResolutionRequest,
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
  initialSelectedKey?: string | null;
  onResolve?: (request: CompanyWorldResolutionDraft) => Promise<void>;
  onRetry?: () => void;
  resolutionState?: CompanyWorldResolutionState;
  status: CompanyWorldStatus;
};

export type CompanyWorldResolutionStatus =
  | "idle"
  | "pending"
  | "success"
  | "conflict"
  | "not_found"
  | "forbidden"
  | "validation"
  | "error";

export type CompanyWorldResolutionState = {
  candidateKey: string | null;
  decision?: CompanyMapResolutionDecision;
  message: string | null;
  status: CompanyWorldResolutionStatus;
};

export type CompanyWorldResolutionGate = {
  inFlight: boolean;
  sequence: number;
  workspaceId: string | null;
};

type WithoutIdempotencyKey<T> = T extends unknown
  ? Omit<T, "idempotency_key">
  : never;

export type CompanyWorldResolutionDraft = WithoutIdempotencyKey<
  CompanyMapResolutionRequest
>;

export type CompanyWorldResolutionFailureEffect = {
  clearAttempt: boolean;
  refresh: boolean;
  state: CompanyWorldResolutionState;
};

const INITIAL_RESOLUTION_STATE: CompanyWorldResolutionState = {
  candidateKey: null,
  message: null,
  status: "idle"
};

const COMPANY_WORLD_PROFILE_ID = "company-world-profile";

export function createCompanyWorldResolutionGate(
  workspaceId: string | null
): CompanyWorldResolutionGate {
  return {
    inFlight: false,
    sequence: 0,
    workspaceId
  };
}

export function resetCompanyWorldResolutionGate(
  gate: CompanyWorldResolutionGate,
  workspaceId: string | null
): void {
  gate.inFlight = false;
  gate.sequence += 1;
  gate.workspaceId = workspaceId;
}

export function beginCompanyWorldResolution(
  gate: CompanyWorldResolutionGate,
  workspaceId: string
): number | null {
  if (gate.inFlight || gate.workspaceId !== workspaceId) {
    return null;
  }
  gate.inFlight = true;
  gate.sequence += 1;
  return gate.sequence;
}

export function isCurrentCompanyWorldResolution(
  gate: CompanyWorldResolutionGate,
  workspaceId: string,
  sequence: number
): boolean {
  return (
    gate.inFlight &&
    gate.workspaceId === workspaceId &&
    gate.sequence === sequence
  );
}

export function finishCompanyWorldResolution(
  gate: CompanyWorldResolutionGate,
  workspaceId: string,
  sequence: number
): void {
  if (isCurrentCompanyWorldResolution(gate, workspaceId, sequence)) {
    gate.inFlight = false;
  }
}

export function pendingCompanyWorldResolution(
  candidateKey: string
): CompanyWorldResolutionState {
  return {
    candidateKey,
    message: M.companyWorld.resolutionPending,
    status: "pending"
  };
}

export function successfulCompanyWorldResolution(
  candidateKey: string,
  decision: CompanyMapResolutionDecision
): CompanyWorldResolutionState {
  return {
    candidateKey,
    decision,
    message:
      decision === "confirmed"
        ? M.companyWorld.resolutionConfirmed
        : M.companyWorld.resolutionDismissed,
    status: "success"
  };
}

export function completedCompanyWorldResolutionRefresh(
  state: CompanyWorldResolutionState
): CompanyWorldResolutionState {
  if (state.status !== "success" || !state.decision) {
    return state;
  }
  return {
    ...state,
    message:
      state.decision === "confirmed"
        ? M.companyWorld.resolutionConfirmedRefreshed
        : M.companyWorld.resolutionDismissedRefreshed
  };
}

export function failedCompanyWorldResolutionRefresh(
  state: CompanyWorldResolutionState
): CompanyWorldResolutionState {
  if (state.status !== "success") {
    return state;
  }
  return {
    ...state,
    message: M.companyWorld.resolutionSavedRefreshFailed
  };
}

export function failedCompanyWorldResolution(
  candidateKey: string,
  caught: unknown
): CompanyWorldResolutionFailureEffect {
  if (caught instanceof ApiRequestError) {
    const httpFailures: Record<
      number,
      Pick<CompanyWorldResolutionFailureEffect, "refresh" | "state">
    > = {
      403: {
        refresh: true,
        state: {
          candidateKey,
          message: M.companyWorld.resolutionForbidden,
          status: "forbidden"
        }
      },
      404: {
        refresh: true,
        state: {
          candidateKey,
          message: M.companyWorld.resolutionNotFound,
          status: "not_found"
        }
      },
      409: {
        refresh: true,
        state: {
          candidateKey,
          message: M.companyWorld.resolutionConflict,
          status: "conflict"
        }
      },
      422: {
        refresh: false,
        state: {
          candidateKey,
          message: M.companyWorld.resolutionValidation,
          status: "validation"
        }
      }
    };
    const matched = httpFailures[caught.status];
    if (matched) {
      return { clearAttempt: true, ...matched };
    }
  }

  return {
    clearAttempt: false,
    refresh: false,
    state: {
      candidateKey,
      message: M.companyWorld.resolutionError,
      status: "error"
    }
  };
}

export function CompanyWorldPanel({ refreshSignal = 0 }: CompanyWorldPanelProps) {
  const workspaceId = useWorkspaceId();
  const [data, setData] = useState<CompanyMapResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [resolutionState, setResolutionState] = useState<CompanyWorldResolutionState>(
    INITIAL_RESOLUTION_STATE
  );
  const [status, setStatus] = useState<CompanyWorldStatus>("loading");
  const resolutionAttempts = useRef(new Map<string, string>());
  const resolutionGate = useRef(createCompanyWorldResolutionGate(null));

  useEffect(() => {
    resetCompanyWorldResolutionGate(resolutionGate.current, workspaceId);
    resolutionAttempts.current.clear();
    setResolutionState(INITIAL_RESOLUTION_STATE);

    return () => {
      resetCompanyWorldResolutionGate(resolutionGate.current, null);
    };
  }, [workspaceId]);

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
        setResolutionState(completedCompanyWorldResolutionRefresh);
      })
      .catch((caught: unknown) => {
        if (cancelled) {
          return;
        }
        setData(null);
        setError(caught instanceof Error ? caught.message : M.common.requestFailed);
        setStatus("error");
        setResolutionState(failedCompanyWorldResolutionRefresh);
      });

    return () => {
      cancelled = true;
    };
  }, [workspaceId, refreshSignal, reloadKey]);

  async function handleResolution(request: CompanyWorldResolutionDraft): Promise<void> {
    if (!workspaceId) {
      return;
    }
    const sequence = beginCompanyWorldResolution(resolutionGate.current, workspaceId);
    if (sequence === null) {
      return;
    }
    const attemptKey = JSON.stringify(request);
    const idempotencyKey =
      resolutionAttempts.current.get(attemptKey) ?? createResolutionIdempotencyKey();
    resolutionAttempts.current.set(attemptKey, idempotencyKey);
    setResolutionState(pendingCompanyWorldResolution(request.candidate_key));

    try {
      const receipt = await resolveCompanyMapCandidate(workspaceId, {
        ...request,
        idempotency_key: idempotencyKey
      });
      if (!isCurrentCompanyWorldResolution(resolutionGate.current, workspaceId, sequence)) {
        return;
      }
      resolutionAttempts.current.delete(attemptKey);
      setResolutionState(
        successfulCompanyWorldResolution(
          request.candidate_key,
          receipt.resolution.decision
        )
      );
      setReloadKey((current) => current + 1);
    } catch (caught: unknown) {
      if (!isCurrentCompanyWorldResolution(resolutionGate.current, workspaceId, sequence)) {
        return;
      }
      const effect = failedCompanyWorldResolution(request.candidate_key, caught);
      if (effect.clearAttempt) {
        resolutionAttempts.current.delete(attemptKey);
      }
      setResolutionState(effect.state);
      if (effect.refresh) {
        setReloadKey((current) => current + 1);
      }
    } finally {
      finishCompanyWorldResolution(resolutionGate.current, workspaceId, sequence);
    }
  }

  return (
    <CompanyWorldPanelView
      data={data}
      error={error}
      onResolve={handleResolution}
      onRetry={() => setReloadKey((current) => current + 1)}
      resolutionState={resolutionState}
      status={status}
    />
  );
}

export function CompanyWorldPanelView({
  data,
  error,
  initialSelectedKey = null,
  onResolve,
  onRetry,
  resolutionState = INITIAL_RESOLUTION_STATE,
  status
}: CompanyWorldPanelViewProps) {
  const [selectedKey, setSelectedKey] = useState<string | null>(initialSelectedKey);
  const [selectionRevision, setSelectionRevision] = useState(0);
  const profileRef = useRef<HTMLElement>(null);
  const effectiveSelectedKey = validSelectedKey(data, selectedKey);

  useEffect(() => {
    if (selectionRevision === 0) {
      return;
    }
    focusCompanyWorldProfileOnMobile(profileRef.current);
  }, [selectionRevision]);

  function selectProfile(key: string): void {
    setSelectedKey(key);
    setSelectionRevision((current) => current + 1);
  }

  return (
    <section className="panel company-world" aria-labelledby="company-world-title">
      <div className="section-header company-world-header">
        <div>
          <span className="eyebrow">{M.companyWorld.eyebrow}</span>
          <h2 id="company-world-title">{M.companyWorld.title}</h2>
        </div>
        <span className="badge world-badge">{M.companyWorld.badge}</span>
      </div>

      {status !== "ready" ? <ResolutionNotice state={resolutionState} /> : null}

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
              description={M.companyWorld.confirmedExternalPeopleDescription}
              title={M.companyWorld.confirmedExternalPeople}
              value={String(data.summary.confirmed_external_people)}
            />
            <StatusCard
              description={M.companyWorld.confirmedOrganizationsDescription}
              title={M.companyWorld.confirmedOrganizations}
              value={String(data.summary.confirmed_organizations)}
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
                  onSelect={() => selectProfile(data.company.key)}
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
                      onSelect={() => selectProfile(person.key)}
                      tone="confirmed"
                    />
                  ))}
                </div>
              </WorldSection>

              <WorldSection title={M.companyWorld.confirmedContactsSection}>
                {data.people.confirmed_external.length > 0 ? (
                  <div className="world-node-grid">
                    {data.people.confirmed_external.map((person) => (
                      <WorldNode
                        badge={M.companyWorld.confirmed}
                        isSelected={effectiveSelectedKey === person.key}
                        key={person.key}
                        label={person.display_name ?? person.email}
                        meta={person.organization_name ?? person.email}
                        onSelect={() => selectProfile(person.key)}
                        tone="confirmed"
                      />
                    ))}
                  </div>
                ) : (
                  <p className="muted">{M.companyWorld.noConfirmedContacts}</p>
                )}
              </WorldSection>

              <WorldSection title={M.companyWorld.confirmedOrganizationsSection}>
                {data.confirmed_organizations.length > 0 ? (
                  <div className="world-node-grid">
                    {data.confirmed_organizations.map((organization) => (
                      <WorldNode
                        badge={M.companyWorld.confirmed}
                        isSelected={effectiveSelectedKey === organization.key}
                        key={organization.key}
                        label={organization.name ?? organization.domain ?? M.common.unknown}
                        meta={organizationRelationshipKindLabel(
                          organization.relationship_kind
                        )}
                        onSelect={() => selectProfile(organization.key)}
                        tone="confirmed"
                      />
                    ))}
                  </div>
                ) : (
                  <p className="muted">{M.companyWorld.noConfirmedOrganizations}</p>
                )}
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
                        onSelect={() => selectProfile(person.key)}
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
                        badge={M.companyWorld.organizationNeedsConfirmation}
                        isSelected={effectiveSelectedKey === organization.key}
                        key={organization.key}
                        label={organization.name ?? organization.domain}
                        meta={`${organization.people_count} · ${M.companyWorld.people.toLocaleLowerCase()}`}
                        onSelect={() => selectProfile(organization.key)}
                        tone="candidate"
                      />
                    ))}
                  </div>
                ) : (
                  <p className="muted">{M.companyWorld.noOrganizations}</p>
                )}
              </WorldSection>
            </div>

            <ProfilePanel
              data={data}
              onResolve={onResolve}
              onSelect={selectProfile}
              profileRef={profileRef}
              resolutionState={resolutionState}
              selectedKey={effectiveSelectedKey}
            />
          </div>

          <TouchpointTimeline
            onSelect={selectProfile}
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
            <span>
              {data.capabilities.can_resolve
                ? M.companyWorld.resolutionEnabled
                : M.companyWorld.readOnly}
            </span>
            <span>
              {!data.capabilities.provider_calls ? M.companyWorld.noProviderCalls : ""}
            </span>
            <span>{M.companyWorld.noExternalWrites}</span>
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
    ...data.people.confirmed_external.map((person) => person.key),
    ...data.people.external_candidates.map((person) => person.key),
    ...data.confirmed_organizations.map((organization) => organization.key),
    ...data.organizations.map((organization) => organization.key),
    ...data.touchpoints.map((touchpoint) => touchpoint.key)
  ]);
  return selectedKey && validKeys.has(selectedKey) ? selectedKey : data.company.key;
}

export function companyWorldCandidateRenderKey(
  candidateKey: string,
  candidateVersion: string
): string {
  return `${candidateKey}:${candidateVersion}`;
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
      aria-controls={COMPANY_WORLD_PROFILE_ID}
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

export type CompanyWorldPersonOrganizationState =
  | {
      kind: "confirmed";
      organization: CompanyMapConfirmedOrganization;
    }
  | {
      kind: "unresolved";
      organization: CompanyMapOrganizationCandidate;
    }
  | {
      kind: "standalone";
    };

export function personOrganizationState(
  data: CompanyMapResponse,
  person: CompanyMapExternalCandidate
): CompanyWorldPersonOrganizationState {
  if (!person.organization_key) {
    return { kind: "standalone" };
  }

  const confirmed = data.confirmed_organizations.find(
    (organization) =>
      organization.key === person.organization_key ||
      (organization.domain
        ? organizationCandidateKey(organization.domain) === person.organization_key
        : false)
  );
  if (confirmed) {
    return { kind: "confirmed", organization: confirmed };
  }

  const unresolved = data.organizations.find(
    (organization) => organization.key === person.organization_key
  );
  if (unresolved) {
    return { kind: "unresolved", organization: unresolved };
  }

  return { kind: "standalone" };
}

function ProfilePanel({
  data,
  onResolve,
  onSelect,
  profileRef,
  resolutionState,
  selectedKey
}: {
  data: CompanyMapResponse;
  onResolve?: (request: CompanyWorldResolutionDraft) => Promise<void>;
  onSelect: (key: string) => void;
  profileRef: RefObject<HTMLElement | null>;
  resolutionState: CompanyWorldResolutionState;
  selectedKey: string | null;
}) {
  const internal = data.people.internal.find((person) => person.key === selectedKey);
  const confirmedExternal = data.people.confirmed_external.find(
    (person) => person.key === selectedKey
  );
  const external = data.people.external_candidates.find(
    (person) => person.key === selectedKey
  );
  const confirmedOrganization = data.confirmed_organizations.find(
    (item) => item.key === selectedKey
  );
  const organization = data.organizations.find((item) => item.key === selectedKey);
  const touchpoint = data.touchpoints.find((item) => item.key === selectedKey);
  const externalOrganizationState = external
    ? personOrganizationState(data, external)
    : null;

  return (
    <aside
      aria-label={M.companyWorld.profileTitle}
      aria-live="polite"
      className="world-profile"
      id={COMPANY_WORLD_PROFILE_ID}
      ref={profileRef}
      tabIndex={-1}
    >
      <ResolutionNotice announce={false} state={resolutionState} />
      {internal ? <InternalPersonProfile person={internal} /> : null}
      {confirmedExternal ? (
        <ConfirmedExternalPersonProfile person={confirmedExternal} />
      ) : null}
      {external ? (
        <ExternalPersonProfile
          canResolve={data.capabilities.can_resolve}
          key={companyWorldCandidateRenderKey(
            external.key,
            external.candidate_version
          )}
          onResolve={onResolve}
          onSelect={onSelect}
          organizationState={externalOrganizationState ?? { kind: "standalone" }}
          person={external}
          resolutionState={resolutionState}
        />
      ) : null}
      {confirmedOrganization ? (
        <ConfirmedOrganizationProfile organization={confirmedOrganization} />
      ) : null}
      {organization ? (
        <OrganizationProfile
          canResolve={data.capabilities.can_resolve}
          key={companyWorldCandidateRenderKey(
            organization.key,
            organization.candidate_version
          )}
          onResolve={onResolve}
          organization={organization}
          resolutionState={resolutionState}
        />
      ) : null}
      {touchpoint ? <TouchpointProfile touchpoint={touchpoint} /> : null}
      {!internal &&
      !confirmedExternal &&
      !external &&
      !confirmedOrganization &&
      !organization &&
      !touchpoint ? (
        <>
          <span className="eyebrow">{M.companyWorld.companyProfile}</span>
          <h3>{data.company.name}</h3>
          <dl className="world-profile-meta">
            <ProfileMeta
              label={M.companyWorld.status}
              value={profileStatus(data.company.status)}
            />
            <ProfileMeta label={M.companyWorld.workspace} value={data.company.slug} />
          </dl>
          <EvidenceList refs={data.company.source_refs} />
        </>
      ) : null}
    </aside>
  );
}

function ConfirmedExternalPersonProfile({
  person
}: {
  person: CompanyMapConfirmedExternalPerson;
}) {
  return (
    <>
      <span className="eyebrow">{M.companyWorld.personProfile}</span>
      <h3>{person.display_name ?? person.email}</h3>
      <span className="world-state world-state--confirmed">{M.companyWorld.confirmed}</span>
      <dl className="world-profile-meta">
        <ProfileMeta label={M.companyWorld.email} value={person.email} />
        <ProfileMeta label={M.companyWorld.status} value={profileStatus(person.status)} />
        {person.organization_name ? (
          <ProfileMeta
            label={M.companyWorld.organizationName}
            value={person.organization_name}
          />
        ) : null}
        {person.relationship_type ? (
          <ProfileMeta
            label={M.companyWorld.relationshipType}
            value={relationshipTypeLabel(person.relationship_type)}
          />
        ) : null}
        {person.role_title ? (
          <ProfileMeta label={M.companyWorld.roleTitle} value={person.role_title} />
        ) : null}
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

function InternalPersonProfile({ person }: { person: CompanyMapInternalPerson }) {
  return (
    <>
      <span className="eyebrow">{M.companyWorld.personProfile}</span>
      <h3>{person.name ?? person.email}</h3>
      <span className="world-state world-state--confirmed">{M.companyWorld.confirmed}</span>
      <dl className="world-profile-meta">
        <ProfileMeta label={M.companyWorld.email} value={person.email} />
        <ProfileMeta label={M.companyWorld.role} value={roleLabel(person.role)} />
        <ProfileMeta
          label={M.companyWorld.status}
          value={profileStatus(person.status)}
        />
      </dl>
      <EvidenceList refs={person.source_refs} />
    </>
  );
}

function ExternalPersonProfile({
  canResolve,
  onResolve,
  onSelect,
  organizationState,
  person,
  resolutionState
}: {
  canResolve: boolean;
  onResolve?: (request: CompanyWorldResolutionDraft) => Promise<void>;
  onSelect: (key: string) => void;
  organizationState: CompanyWorldPersonOrganizationState;
  person: CompanyMapExternalCandidate;
  resolutionState: CompanyWorldResolutionState;
}) {
  const organizationBlockerId = `world-person-organization-${person.key.replace(
    /[^a-zA-Z0-9_-]/g,
    "-"
  )}`;

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
      <PersonOrganizationContext
        calloutId={organizationBlockerId}
        onSelect={onSelect}
        state={organizationState}
      />
      <CandidateResolutionControls
        canResolve={canResolve}
        candidateKey={person.key}
        candidateType="external_person"
        candidateVersion={person.candidate_version}
        confirmationBlocked={organizationState.kind === "unresolved"}
        confirmationDescriptionId={
          organizationState.kind === "unresolved" ? organizationBlockerId : undefined
        }
        defaultDisplayName={person.display_name ?? ""}
        onResolve={onResolve}
        resolutionState={resolutionState}
        showRelationshipFields={organizationState.kind === "confirmed"}
      />
    </>
  );
}

function PersonOrganizationContext({
  calloutId,
  onSelect,
  state
}: {
  calloutId: string;
  onSelect: (key: string) => void;
  state: CompanyWorldPersonOrganizationState;
}) {
  if (state.kind === "unresolved") {
    return (
      <aside className="world-resolution-callout world-resolution-callout--warning" id={calloutId}>
        <strong>{M.companyWorld.organizationResolutionRequired}</strong>
        <span>{state.organization.name ?? state.organization.domain}</span>
        <p>{M.companyWorld.organizationResolutionRequiredDescription}</p>
        <button
          aria-controls={COMPANY_WORLD_PROFILE_ID}
          className="button secondary"
          onClick={() => onSelect(state.organization.key)}
          type="button"
        >
          {M.companyWorld.openOrganizationProfile}
        </button>
      </aside>
    );
  }

  if (state.kind === "confirmed") {
    return (
      <aside className="world-resolution-callout world-resolution-callout--confirmed">
        <strong>{M.companyWorld.confirmedOrganizationForPerson}</strong>
        <span>
          {state.organization.name ?? state.organization.domain ?? M.common.unknown}
        </span>
        <small>
          {organizationRelationshipKindLabel(state.organization.relationship_kind)}
        </small>
      </aside>
    );
  }

  return <p className="world-resolution-callout">{M.companyWorld.standalonePerson}</p>;
}

function ConfirmedOrganizationProfile({
  organization
}: {
  organization: CompanyMapConfirmedOrganization;
}) {
  return (
    <>
      <span className="eyebrow">{M.companyWorld.organizationProfile}</span>
      <h3>{organization.name ?? organization.domain ?? M.common.unknown}</h3>
      <span className="world-state world-state--confirmed">{M.companyWorld.confirmed}</span>
      <dl className="world-profile-meta">
        {organization.domain ? (
          <ProfileMeta label={M.companyWorld.domain} value={organization.domain} />
        ) : null}
        <ProfileMeta
          label={M.companyWorld.status}
          value={profileStatus(organization.status)}
        />
        <ProfileMeta
          label={M.companyWorld.organizationRelationshipKind}
          value={organizationRelationshipKindLabel(
            organization.relationship_kind
          )}
        />
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

function OrganizationProfile({
  canResolve,
  onResolve,
  organization,
  resolutionState
}: {
  canResolve: boolean;
  onResolve?: (request: CompanyWorldResolutionDraft) => Promise<void>;
  organization: CompanyMapOrganizationCandidate;
  resolutionState: CompanyWorldResolutionState;
}) {
  return (
    <>
      <span className="eyebrow">{M.companyWorld.organizationProfile}</span>
      <h3>{organization.name ?? organization.domain}</h3>
      <span className="world-state world-state--candidate">
        {M.companyWorld.organizationNeedsConfirmation}
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
      <CandidateResolutionControls
        canResolve={canResolve}
        candidateKey={organization.key}
        candidateType="organization"
        candidateVersion={organization.candidate_version}
        defaultOrganizationName={organization.name ?? ""}
        onResolve={onResolve}
        resolutionState={resolutionState}
      />
    </>
  );
}

const RELATIONSHIP_TYPES: readonly CompanyMapRelationshipType[] = [
  "contact",
  "employee",
  "decision_maker",
  "account_owner",
  "advisor",
  "other"
];

const ORGANIZATION_RELATIONSHIP_KINDS: readonly CompanyMapOrganizationRelationshipKind[] = [
  "unknown",
  "prospect",
  "customer",
  "partner",
  "vendor",
  "other"
];

type CompanyWorldResolutionFormValues = {
  candidateKey: string;
  candidateType: "external_person" | "organization";
  candidateVersion: string;
  decision: CompanyMapResolutionDecision;
  displayName?: string;
  organizationName?: string;
  organizationRelationshipKind?: CompanyMapOrganizationRelationshipKind | "";
  relationshipFieldsVisible?: boolean;
  relationshipType?: CompanyMapRelationshipType | "";
  roleTitle?: string;
};

export function buildCompanyWorldResolutionDraft({
  candidateKey,
  candidateType,
  candidateVersion,
  decision,
  displayName = "",
  organizationName = "",
  organizationRelationshipKind = "",
  relationshipFieldsVisible = true,
  relationshipType = "",
  roleTitle = ""
}: CompanyWorldResolutionFormValues): CompanyWorldResolutionDraft {
  const identity = {
    candidate_key: candidateKey,
    candidate_type: candidateType,
    candidate_version: candidateVersion
  };

  if (decision === "dismissed") {
    return { ...identity, decision };
  }

  if (candidateType === "external_person") {
    const normalizedDisplayName = optionalText(displayName);
    const allowedRelationshipType = relationshipFieldsVisible ? relationshipType : "";
    const normalizedRoleTitle = allowedRelationshipType
      ? optionalText(roleTitle)
      : undefined;
    if (allowedRelationshipType) {
      return {
        ...identity,
        candidate_type: "external_person",
        decision,
        ...(normalizedDisplayName ? { display_name: normalizedDisplayName } : {}),
        relationship_type: allowedRelationshipType,
        ...(normalizedRoleTitle ? { role_title: normalizedRoleTitle } : {})
      };
    }
    return {
      ...identity,
      candidate_type: "external_person",
      decision,
      ...(normalizedDisplayName ? { display_name: normalizedDisplayName } : {})
    };
  }

  const normalizedOrganizationName = optionalText(organizationName);
  return {
    ...identity,
    candidate_type: "organization",
    decision,
    ...(normalizedOrganizationName
      ? { organization_name: normalizedOrganizationName }
      : {}),
    ...(organizationRelationshipKind
      ? { organization_relationship_kind: organizationRelationshipKind }
      : {})
  };
}

function CandidateResolutionControls({
  canResolve,
  candidateKey,
  candidateType,
  candidateVersion,
  confirmationBlocked = false,
  confirmationDescriptionId,
  defaultDisplayName = "",
  defaultOrganizationName = "",
  onResolve,
  resolutionState,
  showRelationshipFields = false
}: {
  canResolve: boolean;
  candidateKey: string;
  candidateType: "external_person" | "organization";
  candidateVersion: string;
  confirmationBlocked?: boolean;
  confirmationDescriptionId?: string;
  defaultDisplayName?: string;
  defaultOrganizationName?: string;
  onResolve?: (request: CompanyWorldResolutionDraft) => Promise<void>;
  resolutionState: CompanyWorldResolutionState;
  showRelationshipFields?: boolean;
}) {
  const [displayName, setDisplayName] = useState(defaultDisplayName);
  const [organizationName, setOrganizationName] = useState(defaultOrganizationName);
  const [relationshipType, setRelationshipType] =
    useState<CompanyMapRelationshipType | "">("");
  const [organizationRelationshipKind, setOrganizationRelationshipKind] =
    useState<CompanyMapOrganizationRelationshipKind | "">("");
  const [roleTitle, setRoleTitle] = useState("");
  const resolutionInFlight = resolutionState.status === "pending";
  const pendingForCandidate =
    resolutionState.candidateKey === candidateKey &&
    resolutionState.status === "pending";
  const idPrefix = `world-resolution-${candidateKey.replace(/[^a-zA-Z0-9_-]/g, "-")}`;

  useEffect(() => {
    if (!showRelationshipFields) {
      setRelationshipType("");
      setRoleTitle("");
    }
  }, [showRelationshipFields]);

  if (!canResolve) {
    return <p className="world-resolution-read-only">{M.companyWorld.resolutionReadOnly}</p>;
  }

  function submit(decision: "confirmed" | "dismissed"): void {
    if (
      !onResolve ||
      resolutionInFlight ||
      (decision === "confirmed" && confirmationBlocked)
    ) {
      return;
    }
    void onResolve(
      buildCompanyWorldResolutionDraft({
        candidateKey,
        candidateType,
        candidateVersion,
        displayName,
        organizationName,
        organizationRelationshipKind,
        relationshipFieldsVisible: showRelationshipFields,
        relationshipType,
        roleTitle,
        decision
      })
    );
  }

  return (
    <form
      className="world-resolution"
      data-candidate-type={candidateType}
      data-candidate-version={candidateVersion}
      onSubmit={(event) => {
        event.preventDefault();
        submit("confirmed");
      }}
    >
      <div className="world-resolution-heading">
        <strong>{M.companyWorld.confirmCandidate}</strong>
        <span>{M.companyWorld.classificationOptional}</span>
      </div>
      <p className="world-resolution-boundary">
        {M.companyWorld.humanClassificationBoundary}
      </p>

      {candidateType === "external_person" ? (
        <>
          <label htmlFor={`${idPrefix}-display-name`}>{M.companyWorld.displayName}</label>
          <input
            id={`${idPrefix}-display-name`}
            onChange={(event) => setDisplayName(event.target.value)}
            type="text"
            value={displayName}
          />
          {showRelationshipFields ? (
            <>
              <label htmlFor={`${idPrefix}-relationship-type`}>
                {M.companyWorld.relationshipType}
              </label>
              <select
                id={`${idPrefix}-relationship-type`}
                onChange={(event) => {
                  const value = event.target.value as CompanyMapRelationshipType | "";
                  setRelationshipType(value);
                  if (!value) {
                    setRoleTitle("");
                  }
                }}
                value={relationshipType}
              >
                <option value="">{M.companyWorld.selectClassification}</option>
                {RELATIONSHIP_TYPES.map((value) => (
                  <option key={value} value={value}>
                    {relationshipTypeLabel(value)}
                  </option>
                ))}
              </select>
              <label htmlFor={`${idPrefix}-role-title`}>
                {M.companyWorld.roleTitle}
              </label>
              <input
                aria-describedby={
                  relationshipType ? undefined : `${idPrefix}-role-title-help`
                }
                disabled={!relationshipType}
                id={`${idPrefix}-role-title`}
                onChange={(event) => setRoleTitle(event.target.value)}
                type="text"
                value={roleTitle}
              />
              {!relationshipType ? (
                <span className="world-resolution-help" id={`${idPrefix}-role-title-help`}>
                  {M.companyWorld.roleRequiresRelationship}
                </span>
              ) : null}
            </>
          ) : null}
        </>
      ) : (
        <>
          <label htmlFor={`${idPrefix}-organization-name`}>
            {M.companyWorld.organizationName}
          </label>
          <input
            id={`${idPrefix}-organization-name`}
            onChange={(event) => setOrganizationName(event.target.value)}
            type="text"
            value={organizationName}
          />
          <label htmlFor={`${idPrefix}-relationship-kind`}>
            {M.companyWorld.organizationRelationshipKind}
          </label>
          <select
            id={`${idPrefix}-relationship-kind`}
            onChange={(event) =>
              setOrganizationRelationshipKind(
                event.target.value as CompanyMapOrganizationRelationshipKind | ""
              )
            }
            value={organizationRelationshipKind}
          >
            <option value="">{M.companyWorld.selectClassification}</option>
            {ORGANIZATION_RELATIONSHIP_KINDS.map((value) => (
              <option key={value} value={value}>
                {organizationRelationshipKindLabel(value)}
              </option>
            ))}
          </select>
        </>
      )}

      <div className="world-resolution-actions">
        <button
          aria-describedby={confirmationDescriptionId}
          className="button"
          data-resolution-action="confirm"
          disabled={resolutionInFlight || !onResolve || confirmationBlocked}
          type="submit"
        >
          {pendingForCandidate
            ? M.companyWorld.resolvingCandidate
            : M.companyWorld.confirmCandidate}
        </button>
        <button
          className="button secondary"
          data-resolution-action="dismiss"
          disabled={resolutionInFlight || !onResolve}
          onClick={() => submit("dismissed")}
          type="button"
        >
          {M.companyWorld.dismissCandidate}
        </button>
      </div>
    </form>
  );
}

function ResolutionNotice({
  announce = true,
  state
}: {
  announce?: boolean;
  state: CompanyWorldResolutionState;
}) {
  if (state.status === "idle" || !state.message) {
    return null;
  }
  return (
    <div
      aria-label={M.companyWorld.resolutionStatusLabel}
      aria-live={announce ? "polite" : undefined}
      className={`world-resolution-notice world-resolution-notice--${state.status}`}
      role={
        announce
          ? state.status === "pending" || state.status === "success"
            ? "status"
            : "alert"
          : undefined
      }
    >
      {state.message}
    </div>
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
                aria-controls={COMPANY_WORLD_PROFILE_ID}
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

function optionalText(value: string): string | undefined {
  const normalized = value.trim();
  return normalized || undefined;
}

function createResolutionIdempotencyKey(): string {
  if (typeof globalThis.crypto?.randomUUID === "function") {
    return `company-world:${globalThis.crypto.randomUUID()}`;
  }
  return `company-world:${Date.now()}:${Math.random().toString(36).slice(2)}`;
}

function profileStatus(value: string): string {
  if (value in M.companyWorld.statuses) {
    return M.companyWorld.statuses[
      value as keyof typeof M.companyWorld.statuses
    ];
  }
  return value;
}

function relationshipTypeLabel(value: CompanyMapRelationshipType): string {
  return M.companyWorld.relationshipTypes[value];
}

function organizationRelationshipKindLabel(
  value: CompanyMapOrganizationRelationshipKind
): string {
  return M.companyWorld.organizationRelationshipKinds[value];
}

function organizationCandidateKey(domain: string): string {
  return `organization:${domain.trim().toLowerCase().replace(/\.$/, "")}`;
}

function focusCompanyWorldProfileOnMobile(profile: HTMLElement | null): void {
  if (
    !profile ||
    typeof window === "undefined" ||
    typeof window.matchMedia !== "function" ||
    !window.matchMedia("(max-width: 960px)").matches
  ) {
    return;
  }
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  profile.focus({ preventScroll: true });
  profile.scrollIntoView({
    behavior: reduceMotion ? "auto" : "smooth",
    block: "start"
  });
}
