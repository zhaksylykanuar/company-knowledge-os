"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import type { RefObject } from "react";

import {
  ApiRequestError,
  fetchCompanyMap,
  resolveCompanyMapCandidate
} from "../lib/api";
import {
  buildCompanyWorldProfileTarget,
  resolveCompanyWorldProfileRequest
} from "../lib/company-world-profile";
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
import {
  CompanyWorldBoard,
  type CompanyWorldZone
} from "./CompanyWorldBoard";
import { SourceLink } from "./SourceLink";
import styles from "./company-world.module.css";

export type CompanyWorldStatus =
  | "loading"
  | "ready"
  | "empty"
  | "error"
  | "missing";

type CompanyWorldPanelProps = {
  onRefresh?: () => void;
  profileSelector?: string | null;
  profileSelectorRequested?: boolean;
  refreshSignal?: number;
};

type CompanyWorldPanelViewProps = {
  data: CompanyMapResponse | null;
  error: string | null;
  initialSelectedKey?: string | null;
  onProfileNavigate?: (key: string) => void;
  onRefresh?: () => void;
  onResolve?: (request: CompanyWorldResolutionDraft) => Promise<void>;
  onRetry?: () => void;
  profileUnavailable?: boolean;
  resolutionState?: CompanyWorldResolutionState;
  status: CompanyWorldStatus;
};

export type CompanyWorldLocalSelection = {
  data: CompanyMapResponse | null;
  key: string | null;
  routeKey: string | null;
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

export function CompanyWorldPanel({
  onRefresh,
  profileSelector = null,
  profileSelectorRequested = profileSelector !== null,
  refreshSignal = 0
}: CompanyWorldPanelProps) {
  const router = useRouter();
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

  function navigateToProfile(key: string): void {
    if (!data) {
      return;
    }
    const target = buildCompanyWorldProfileTarget(data, key);
    // Touchpoints are local history of the currently routed profile. They do
    // not get a selector of their own and must not clear the parent URL.
    if (target) {
      router.replace(target.href, { scroll: false });
    }
  }

  const profileRequest = data
    ? resolveCompanyWorldProfileRequest(
        data,
        profileSelector,
        profileSelectorRequested
      )
    : null;

  return (
    <CompanyWorldPanelView
      data={data}
      error={error}
      initialSelectedKey={profileRequest?.selectedKey ?? null}
      onProfileNavigate={navigateToProfile}
      onResolve={handleResolution}
      onRefresh={onRefresh ?? (() => setReloadKey((current) => current + 1))}
      onRetry={() => setReloadKey((current) => current + 1)}
      profileUnavailable={profileRequest?.state === "unavailable"}
      resolutionState={resolutionState}
      status={status}
    />
  );
}

export function CompanyWorldPanelView({
  data,
  error,
  initialSelectedKey = null,
  onProfileNavigate,
  onRefresh,
  onResolve,
  onRetry,
  profileUnavailable = false,
  resolutionState = INITIAL_RESOLUTION_STATE,
  status
}: CompanyWorldPanelViewProps) {
  const [localSelection, setLocalSelection] = useState<CompanyWorldLocalSelection>({
    data,
    key: initialSelectedKey,
    routeKey: initialSelectedKey
  });
  const [selectionRevision, setSelectionRevision] = useState(0);
  const [activeZone, setActiveZone] = useState<CompanyWorldZone>("all");
  const previousRouteKey = useRef(initialSelectedKey);
  const previousProfileUnavailable = useRef(profileUnavailable);
  const profileRef = useRef<HTMLElement>(null);
  const localSelectionIsCurrent =
    localSelection.data === data && localSelection.routeKey === initialSelectedKey;
  const explicitLocalSelection =
    localSelectionIsCurrent && localSelection.key !== null;
  const unavailableProfileVisible = profileUnavailable && !explicitLocalSelection;
  const effectiveSelectedKey = unavailableProfileVisible
    ? null
    : effectiveCompanyWorldSelectedKey(data, initialSelectedKey, localSelection);
  const nextCandidateKey = data
    ? nextCompanyWorldCandidateKey(data, effectiveSelectedKey)
    : null;

  useEffect(() => {
    if (
      previousRouteKey.current === initialSelectedKey &&
      previousProfileUnavailable.current === profileUnavailable
    ) {
      return;
    }
    previousRouteKey.current = initialSelectedKey;
    previousProfileUnavailable.current = profileUnavailable;
    if (!data) {
      return;
    }
    setLocalSelection({ data, key: initialSelectedKey, routeKey: initialSelectedKey });
    const nextRouteKey = validSelectedKey(data, initialSelectedKey);
    setActiveZone(
      companyWorldZoneForKey(data, nextRouteKey ?? data.company.key)
    );
    if (
      profileUnavailable ||
      (initialSelectedKey && localSelection.key !== initialSelectedKey)
    ) {
      setSelectionRevision((current) => current + 1);
    }
  }, [data, initialSelectedKey, localSelection.key, profileUnavailable]);

  useEffect(() => {
    if (selectionRevision === 0) {
      return;
    }
    focusCompanyWorldProfile(profileRef.current);
  }, [effectiveSelectedKey, selectionRevision]);

  function selectProfile(key: string): void {
    setLocalSelection({ data, key, routeKey: initialSelectedKey });
    onProfileNavigate?.(key);
    setSelectionRevision((current) => current + 1);
  }

  const candidateCount = data ? companyWorldCandidateCount(data) : 0;
  const candidatesAreLowerBound = Boolean(data?.window.truncated);
  const nextCandidateLabel =
    data && nextCandidateKey ? companyWorldProfileLabel(data, nextCandidateKey) : null;
  const currentCandidateLabel =
    data && candidateCount > 0 && !nextCandidateKey
      ? companyWorldProfileLabel(data, effectiveSelectedKey ?? data.company.key)
      : null;

  return (
    <section className={styles.shell} aria-labelledby="company-world-title">
      <header className={styles.commandBar} data-state={status}>
        <div className={styles.commandIdentity}>
          <span className={styles.commandEyebrow}>{M.companyWorld.worldEyebrow}</span>
          <h1 id="company-world-title">
            {data?.company.name ?? M.companyWorld.title}
          </h1>
          <p>{M.companyWorld.worldDescription}</p>
        </div>
        {data && status === "ready" ? (
          <dl className={styles.commandMetrics} aria-label={M.companyWorld.summaryLabel}>
            <WorldMetric
              label={M.companyWorld.teamSection}
              value={String(data.people.internal.length)}
            />
            <WorldMetric
              label={M.companyWorld.confirmedContour}
              value={String(
                data.people.confirmed_external.length +
                  data.confirmed_organizations.length
              )}
            />
            <WorldMetric
              label={M.companyWorld.needsReview}
              tone={candidateCount > 0 ? "attention" : "calm"}
              value={`${candidatesAreLowerBound ? "≥" : ""}${candidateCount}`}
            />
            <WorldMetric
              label={M.companyWorld.touchpoints}
              value={`${data.window.truncated ? "≥" : ""}${data.summary.touchpoints_in_window}`}
            />
          </dl>
        ) : null}
        <button
          aria-disabled={status === "loading"}
          aria-label={M.companyWorld.refreshWorld}
          className={styles.refreshButton}
          onClick={status === "loading" ? undefined : onRefresh ?? onRetry}
          type="button"
        >
          <span aria-hidden="true">↻</span>
          {M.companyWorld.refreshWorld}
        </button>
      </header>

      {status === "ready" ? (
        <ResolutionNotice state={resolutionState} visuallyHidden />
      ) : (
        <ResolutionNotice state={resolutionState} />
      )}

      {status === "loading" ? (
        <div className={styles.stateCard}>
          <LoadingState label={M.companyWorld.loading} />
        </div>
      ) : null}

      {status === "missing" ? (
        <div className={styles.stateCard}>
          <EmptyState
            description={M.companyWorld.noWorkspaceDescription}
            title={M.common.noWorkspaceTitle}
          />
        </div>
      ) : null}

      {status === "error" ? (
        <div className={styles.stateCard}>
          <ErrorState
            description={error ?? M.companyWorld.unavailableDescription}
            title={M.companyWorld.unavailableTitle}
          />
          <button className="button secondary" onClick={onRetry} type="button">
            {M.common.retry}
          </button>
        </div>
      ) : null}

      {status === "empty" ? (
        <div className={styles.stateCard}>
          <EmptyState
            description={M.companyWorld.emptyDescription}
            title={M.companyWorld.emptyTitle}
          />
        </div>
      ) : null}

      {data && status === "ready" ? (
        <>
          <aside
            className={styles.reviewRail}
            data-state={candidateCount > 0 ? "attention" : "clear"}
          >
            <span className={styles.reviewMark} aria-hidden="true">
              {candidateCount > 0
                ? `${candidatesAreLowerBound ? "≥" : ""}${candidateCount}`
                : "✓"}
            </span>
            <div className={styles.reviewCopy}>
              <strong>
                {candidateCount > 0
                  ? M.companyWorld.reviewRailTitle(
                      candidateCount,
                      candidatesAreLowerBound
                    )
                  : candidatesAreLowerBound
                    ? M.companyWorld.reviewRailWindowClearTitle
                    : M.companyWorld.reviewRailClearTitle}
              </strong>
              <span>
                {candidateCount > 0 && nextCandidateLabel
                  ? M.companyWorld.reviewRailNext(nextCandidateLabel)
                  : candidateCount > 0 && currentCandidateLabel
                    ? M.companyWorld.reviewRailCurrent(currentCandidateLabel)
                    : candidatesAreLowerBound
                      ? M.companyWorld.reviewRailWindowClearDescription
                      : M.companyWorld.reviewRailClearDescription}
              </span>
            </div>
            {nextCandidateKey ? (
              <button
                aria-controls={COMPANY_WORLD_PROFILE_ID}
                className={styles.reviewButton}
                disabled={resolutionState.status === "pending"}
                onClick={() => {
                  setActiveZone("review");
                  selectProfile(nextCandidateKey);
                }}
                type="button"
              >
                {M.companyWorld.openNextCandidate} <span aria-hidden="true">→</span>
              </button>
            ) : null}
          </aside>
          <div className={styles.workspace}>
            <CompanyWorldBoard
              activeZone={activeZone}
              data={data}
              inspectorId={COMPANY_WORLD_PROFILE_ID}
              onSelect={selectProfile}
              onZoneChange={setActiveZone}
              selectedKey={effectiveSelectedKey}
            />

            <ProfilePanel
              data={data}
              onResolve={onResolve}
              onSelect={selectProfile}
              profileUnavailable={unavailableProfileVisible}
              profileRef={profileRef}
              resolutionState={resolutionState}
              selectedKey={effectiveSelectedKey}
            />
          </div>

          <CompanyWorldTechnicalBoundary data={data} />
        </>
      ) : null}
    </section>
  );
}

function WorldMetric({
  label,
  tone = "default",
  value
}: {
  label: string;
  tone?: "attention" | "calm" | "default";
  value: string;
}) {
  return (
    <div data-tone={tone}>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

export function companyWorldZoneForKey(
  data: CompanyMapResponse,
  selectedKey: string
): CompanyWorldZone {
  if (data.people.internal.some((person) => person.key === selectedKey)) {
    return "team";
  }
  if (
    data.people.confirmed_external.some((person) => person.key === selectedKey) ||
    data.confirmed_organizations.some(
      (organization) => organization.key === selectedKey
    )
  ) {
    return "network";
  }
  if (
    data.people.external_candidates.some((person) => person.key === selectedKey) ||
    data.organizations.some((organization) => organization.key === selectedKey)
  ) {
    return "review";
  }
  return "all";
}

function companyWorldProfileLabel(
  data: CompanyMapResponse,
  selectedKey: string
): string {
  if (selectedKey === data.company.key) {
    return data.company.name;
  }
  const internal = data.people.internal.find((person) => person.key === selectedKey);
  if (internal) {
    return internal.name ?? internal.email;
  }
  const confirmedPerson = data.people.confirmed_external.find(
    (person) => person.key === selectedKey
  );
  if (confirmedPerson) {
    return confirmedPerson.display_name ?? confirmedPerson.email;
  }
  const candidatePerson = data.people.external_candidates.find(
    (person) => person.key === selectedKey
  );
  if (candidatePerson) {
    return candidatePerson.display_name ?? candidatePerson.email;
  }
  const confirmedOrganization = data.confirmed_organizations.find(
    (organization) => organization.key === selectedKey
  );
  if (confirmedOrganization) {
    return (
      confirmedOrganization.name ??
      confirmedOrganization.domain ??
      M.common.unknown
    );
  }
  const candidateOrganization = data.organizations.find(
    (organization) => organization.key === selectedKey
  );
  return candidateOrganization?.name ?? candidateOrganization?.domain ?? M.common.unknown;
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

export function effectiveCompanyWorldSelectedKey(
  data: CompanyMapResponse | null,
  routeSelectedKey: string | null,
  localSelection: CompanyWorldLocalSelection
): string | null {
  const routeKey = validSelectedKey(data, routeSelectedKey);
  const localSelectionIsCurrent =
    localSelection.data === data && localSelection.routeKey === routeSelectedKey;
  return validSelectedKey(
    data,
    localSelectionIsCurrent ? localSelection.key : routeKey
  );
}

export function nextCompanyWorldCandidateKey(
  data: CompanyMapResponse,
  selectedKey: string | null
): string | null {
  const candidateKeys = [
    ...data.organizations.map((organization) => organization.key),
    ...data.people.external_candidates.map((person) => person.key)
  ];
  if (candidateKeys.length === 0) {
    return null;
  }

  const selectedIndex = selectedKey ? candidateKeys.indexOf(selectedKey) : -1;
  if (selectedIndex < 0) {
    return candidateKeys[0] ?? null;
  }
  if (candidateKeys.length === 1) {
    return null;
  }
  return candidateKeys[(selectedIndex + 1) % candidateKeys.length] ?? null;
}

function companyWorldCandidateCount(data: CompanyMapResponse): number {
  return data.organizations.length + data.people.external_candidates.length;
}

export function companyWorldCandidateRenderKey(
  candidateKey: string,
  candidateVersion: string
): string {
  return `${candidateKey}:${candidateVersion}`;
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
  profileUnavailable,
  profileRef,
  resolutionState,
  selectedKey
}: {
  data: CompanyMapResponse;
  onResolve?: (request: CompanyWorldResolutionDraft) => Promise<void>;
  onSelect: (key: string) => void;
  profileUnavailable: boolean;
  profileRef: RefObject<HTMLElement | null>;
  resolutionState: CompanyWorldResolutionState;
  selectedKey: string | null;
}) {
  if (profileUnavailable) {
    return (
      <aside
        aria-labelledby="company-world-profile-title"
        className={`${styles.profile} world-profile`}
        data-state="unavailable"
        id={COMPANY_WORLD_PROFILE_ID}
        ref={profileRef}
        tabIndex={-1}
      >
        <span className="eyebrow">Профиль</span>
        <h3 id="company-world-profile-title">
          Профиль больше недоступен в текущем снимке
        </h3>
        <p>
          Выберите актуального человека или компанию в Мире. FounderOS не
          подменяет устаревшую ссылку профилем компании.
        </p>
      </aside>
    );
  }

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
  const isCompanyProfile =
    !internal &&
    !confirmedExternal &&
    !external &&
    !confirmedOrganization &&
    !organization &&
    !touchpoint;
  const profileTouchpoints = relatedCompanyWorldTouchpoints(
    data,
    selectedKey ?? data.company.key
  );
  const evidenceRefs =
    internal?.source_refs ??
    confirmedExternal?.source_refs ??
    external?.source_refs ??
    confirmedOrganization?.source_refs ??
    organization?.source_refs ??
    touchpoint?.source_refs ??
    data.company.source_refs;

  return (
    <aside
      aria-labelledby="company-world-profile-title"
      className={`${styles.profile} world-profile`}
      id={COMPANY_WORLD_PROFILE_ID}
      ref={profileRef}
      tabIndex={-1}
    >
      <ResolutionNotice announce={false} state={resolutionState} />
      {internal ? (
        <InternalPersonProfile headingId="company-world-profile-title" person={internal} />
      ) : null}
      {confirmedExternal ? (
        <ConfirmedExternalPersonProfile
          headingId="company-world-profile-title"
          person={confirmedExternal}
        />
      ) : null}
      {external ? (
        <ExternalPersonProfile
          headingId="company-world-profile-title"
          interactionsAreLowerBound={data.window.truncated}
          onSelect={onSelect}
          organizationState={externalOrganizationState ?? { kind: "standalone" }}
          person={external}
        />
      ) : null}
      {confirmedOrganization ? (
        <ConfirmedOrganizationProfile
          headingId="company-world-profile-title"
          organization={confirmedOrganization}
        />
      ) : null}
      {organization ? (
        <OrganizationProfile
          headingId="company-world-profile-title"
          interactionsAreLowerBound={data.window.truncated}
          organization={organization}
        />
      ) : null}
      {touchpoint ? (
        <TouchpointProfile
          headingId="company-world-profile-title"
          touchpoint={touchpoint}
        />
      ) : null}
      {isCompanyProfile ? (
        <>
          <span className="eyebrow">{M.companyWorld.companyProfile}</span>
          <h3 id="company-world-profile-title">{data.company.name}</h3>
          <dl className="world-profile-meta">
            <ProfileMeta
              label={M.companyWorld.status}
              value={profileStatus(data.company.status)}
            />
            <ProfileMeta label={M.companyWorld.workspace} value={data.company.slug} />
          </dl>
        </>
      ) : null}
      {!touchpoint ? (
        <ProfileTouchpointHistory
          isCompanyProfile={isCompanyProfile}
          key={selectedKey ?? data.company.key}
          onSelect={onSelect}
          selectedKey={selectedKey}
          touchpoints={profileTouchpoints}
        />
      ) : null}
      {external ? (
        <CandidateResolutionControls
          canResolve={data.capabilities.can_resolve}
          candidateKey={external.key}
          candidateType="external_person"
          candidateVersion={external.candidate_version}
          confirmationBlocked={externalOrganizationState?.kind === "unresolved"}
          confirmationDescriptionId={
            externalOrganizationState?.kind === "unresolved"
              ? `world-person-organization-${external.key.replace(
                  /[^a-zA-Z0-9_-]/g,
                  "-"
                )}`
              : undefined
          }
          defaultDisplayName={external.display_name ?? ""}
          key={companyWorldCandidateRenderKey(
            external.key,
            external.candidate_version
          )}
          onResolve={onResolve}
          resolutionState={resolutionState}
          showRelationshipFields={externalOrganizationState?.kind === "confirmed"}
        />
      ) : null}
      {organization ? (
        <CandidateResolutionControls
          canResolve={data.capabilities.can_resolve}
          candidateKey={organization.key}
          candidateType="organization"
          candidateVersion={organization.candidate_version}
          defaultOrganizationName={organization.name ?? ""}
          key={companyWorldCandidateRenderKey(
            organization.key,
            organization.candidate_version
          )}
          onResolve={onResolve}
          resolutionState={resolutionState}
        />
      ) : null}
      <EvidenceList refs={evidenceRefs} />
    </aside>
  );
}

function ConfirmedExternalPersonProfile({
  headingId,
  person
}: {
  headingId: string;
  person: CompanyMapConfirmedExternalPerson;
}) {
  return (
    <>
      <span className="eyebrow">{M.companyWorld.personProfile}</span>
      <h3 id={headingId}>{person.display_name ?? person.email}</h3>
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
    </>
  );
}

function InternalPersonProfile({
  headingId,
  person
}: {
  headingId: string;
  person: CompanyMapInternalPerson;
}) {
  return (
    <>
      <span className="eyebrow">{M.companyWorld.personProfile}</span>
      <h3 id={headingId}>{person.name ?? person.email}</h3>
      <span className="world-state world-state--confirmed">{M.companyWorld.confirmed}</span>
      <dl className="world-profile-meta">
        <ProfileMeta label={M.companyWorld.email} value={person.email} />
        <ProfileMeta label={M.companyWorld.role} value={roleLabel(person.role)} />
        <ProfileMeta
          label={M.companyWorld.status}
          value={profileStatus(person.status)}
        />
      </dl>
    </>
  );
}

function ExternalPersonProfile({
  headingId,
  interactionsAreLowerBound,
  onSelect,
  organizationState,
  person
}: {
  headingId: string;
  interactionsAreLowerBound: boolean;
  onSelect: (key: string) => void;
  organizationState: CompanyWorldPersonOrganizationState;
  person: CompanyMapExternalCandidate;
}) {
  const organizationBlockerId = `world-person-organization-${person.key.replace(
    /[^a-zA-Z0-9_-]/g,
    "-"
  )}`;

  return (
    <>
      <span className="eyebrow">{M.companyWorld.personProfile}</span>
      <h3 id={headingId}>{person.display_name ?? person.email}</h3>
      <span className="world-state world-state--candidate">
        {M.companyWorld.needsConfirmation}
      </span>
      <dl className="world-profile-meta">
        <ProfileMeta label={M.companyWorld.email} value={person.email} />
        <ProfileMeta
          label={M.companyWorld.interactions}
          value={formatWindowCount(
            person.interaction_count,
            interactionsAreLowerBound
          )}
        />
        <ProfileMeta
          label={M.companyWorld.lastInteraction}
          value={formatDate(person.last_interaction_at)}
        />
      </dl>
      <PersonOrganizationContext
        calloutId={organizationBlockerId}
        onSelect={onSelect}
        state={organizationState}
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
        <p>{M.companyWorld.confirmedOrganizationForPersonDescription}</p>
      </aside>
    );
  }

  return <p className="world-resolution-callout">{M.companyWorld.standalonePerson}</p>;
}

function ConfirmedOrganizationProfile({
  headingId,
  organization
}: {
  headingId: string;
  organization: CompanyMapConfirmedOrganization;
}) {
  return (
    <>
      <span className="eyebrow">{M.companyWorld.organizationProfile}</span>
      <h3 id={headingId}>
        {organization.name ?? organization.domain ?? M.common.unknown}
      </h3>
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
    </>
  );
}

function OrganizationProfile({
  headingId,
  interactionsAreLowerBound,
  organization
}: {
  headingId: string;
  interactionsAreLowerBound: boolean;
  organization: CompanyMapOrganizationCandidate;
}) {
  return (
    <>
      <span className="eyebrow">{M.companyWorld.organizationProfile}</span>
      <h3 id={headingId}>{organization.name ?? organization.domain}</h3>
      <span className="world-state world-state--candidate">
        {M.companyWorld.organizationNeedsConfirmation}
      </span>
      <dl className="world-profile-meta">
        <ProfileMeta label={M.companyWorld.domain} value={organization.domain} />
        <ProfileMeta
          label={M.companyWorld.people}
          value={formatWindowCount(
            organization.people_count,
            interactionsAreLowerBound
          )}
        />
        <ProfileMeta
          label={M.companyWorld.interactions}
          value={formatWindowCount(
            organization.interaction_count,
            interactionsAreLowerBound
          )}
        />
        <ProfileMeta
          label={M.companyWorld.lastInteraction}
          value={formatDate(organization.last_interaction_at)}
        />
      </dl>
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

export type CompanyWorldResolutionStep =
  | "decision"
  | "name"
  | "relationship"
  | "role";

export function companyWorldResolutionSteps(
  candidateType: "external_person" | "organization",
  showRelationshipFields: boolean
): readonly CompanyWorldResolutionStep[] {
  if (candidateType === "organization") {
    return ["decision", "name", "relationship"];
  }
  return showRelationshipFields
    ? ["decision", "name", "relationship", "role"]
    : ["decision", "name"];
}

export function companyWorldResolutionStepForContext(
  candidateType: "external_person" | "organization",
  showRelationshipFields: boolean,
  step: CompanyWorldResolutionStep
): CompanyWorldResolutionStep {
  if (
    candidateType === "external_person" &&
    !showRelationshipFields &&
    (step === "relationship" || step === "role")
  ) {
    return "name";
  }
  return step;
}

export function advanceCompanyWorldResolutionStep(
  steps: readonly CompanyWorldResolutionStep[],
  step: CompanyWorldResolutionStep
): { nextStep: CompanyWorldResolutionStep; shouldSubmit: boolean } {
  const stepIndex = Math.max(0, steps.indexOf(step));
  if (stepIndex === steps.length - 1) {
    return { nextStep: step, shouldSubmit: true };
  }
  return {
    nextStep: steps[stepIndex + 1] ?? step,
    shouldSubmit: false
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
  const [step, setStep] = useState<CompanyWorldResolutionStep>("decision");
  const previousStepRef = useRef<CompanyWorldResolutionStep>("decision");
  const questionRef = useRef<HTMLElement>(null);
  const resolutionInFlight = resolutionState.status === "pending";
  const pendingForCandidate =
    resolutionState.candidateKey === candidateKey &&
    resolutionState.status === "pending";
  const idPrefix = `world-resolution-${candidateKey.replace(/[^a-zA-Z0-9_-]/g, "-")}`;
  const steps = companyWorldResolutionSteps(candidateType, showRelationshipFields);
  const stepIndex = Math.max(0, steps.indexOf(step));
  const isFinalStep = stepIndex === steps.length - 1;

  useEffect(() => {
    if (candidateType === "external_person" && !showRelationshipFields) {
      setRelationshipType("");
      setRoleTitle("");
    }
    const contextualStep = companyWorldResolutionStepForContext(
      candidateType,
      showRelationshipFields,
      step
    );
    if (contextualStep !== step) {
      setStep(contextualStep);
    }
  }, [candidateType, showRelationshipFields, step]);

  useEffect(() => {
    if (previousStepRef.current !== step) {
      previousStepRef.current = step;
      questionRef.current?.focus();
    }
  }, [step]);

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

  function moveForward(): void {
    if (
      resolutionInFlight ||
      !onResolve ||
      (step === "decision" && confirmationBlocked)
    ) {
      return;
    }
    const advance = advanceCompanyWorldResolutionStep(steps, step);
    if (advance.shouldSubmit) {
      submit("confirmed");
      return;
    }
    setStep(advance.nextStep);
  }

  function moveBack(): void {
    if (stepIndex === 0 || resolutionInFlight) {
      return;
    }
    setStep(steps[stepIndex - 1] ?? "decision");
  }

  const question =
    step === "decision"
      ? candidateType === "external_person"
        ? M.companyWorld.resolutionPersonQuestion
        : M.companyWorld.resolutionOrganizationQuestion
      : step === "name"
        ? candidateType === "external_person"
          ? M.companyWorld.resolutionNamePersonQuestion
          : M.companyWorld.resolutionNameOrganizationQuestion
        : step === "relationship"
          ? candidateType === "external_person"
            ? M.companyWorld.resolutionPersonRelationshipQuestion
            : M.companyWorld.resolutionOrganizationRelationshipQuestion
          : M.companyWorld.resolutionRoleTitleQuestion;

  return (
    <form
      aria-labelledby={`${idPrefix}-question`}
      className="world-resolution"
      data-candidate-type={candidateType}
      data-candidate-version={candidateVersion}
      data-resolution-step={step}
      onSubmit={(event) => {
        event.preventDefault();
        moveForward();
      }}
    >
      <div className="world-resolution-heading">
        <span>
          {M.companyWorld.resolutionStepLabel} {stepIndex + 1} / {steps.length}
        </span>
        <strong id={`${idPrefix}-question`} ref={questionRef} tabIndex={-1}>
          {question}
        </strong>
      </div>
      <p className="world-resolution-boundary">
        {step === "decision"
          ? M.companyWorld.resolutionQuestionHint
          : M.companyWorld.resolutionOptionalAnswer}
      </p>

      {step === "name" && candidateType === "external_person" ? (
        <label className="world-resolution-answer" htmlFor={`${idPrefix}-display-name`}>
          <span>{M.companyWorld.displayName}</span>
          <input
            id={`${idPrefix}-display-name`}
            maxLength={255}
            onChange={(event) => setDisplayName(event.target.value)}
            type="text"
            value={displayName}
          />
        </label>
      ) : null}

      {step === "name" && candidateType === "organization" ? (
        <label className="world-resolution-answer" htmlFor={`${idPrefix}-organization-name`}>
          <span>{M.companyWorld.organizationName}</span>
          <input
            id={`${idPrefix}-organization-name`}
            maxLength={255}
            onChange={(event) => setOrganizationName(event.target.value)}
            type="text"
            value={organizationName}
          />
        </label>
      ) : null}

      {step === "relationship" && candidateType === "external_person" ? (
        <label className="world-resolution-answer" htmlFor={`${idPrefix}-relationship-type`}>
          <span>{M.companyWorld.relationshipType}</span>
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
        </label>
      ) : null}

      {step === "relationship" && candidateType === "organization" ? (
        <label className="world-resolution-answer" htmlFor={`${idPrefix}-relationship-kind`}>
          <span>{M.companyWorld.organizationRelationshipKind}</span>
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
        </label>
      ) : null}

      {step === "role" ? (
        <label className="world-resolution-answer" htmlFor={`${idPrefix}-role-title`}>
          <span>{M.companyWorld.roleTitle}</span>
          <input
            aria-describedby={
              relationshipType ? undefined : `${idPrefix}-role-title-help`
            }
            disabled={!relationshipType}
            id={`${idPrefix}-role-title`}
            maxLength={255}
            onChange={(event) => setRoleTitle(event.target.value)}
            type="text"
            value={roleTitle}
          />
          {!relationshipType ? (
            <small className="world-resolution-help" id={`${idPrefix}-role-title-help`}>
              {M.companyWorld.roleRequiresRelationship}
            </small>
          ) : null}
        </label>
      ) : null}

      <div className="world-resolution-actions">
        {step === "decision" ? (
          <>
            <button
              aria-describedby={confirmationDescriptionId}
              className="button"
              data-resolution-action="confirm"
              disabled={resolutionInFlight || !onResolve || confirmationBlocked}
              type="submit"
            >
              {candidateType === "external_person"
                ? M.companyWorld.resolutionKeepPerson
                : M.companyWorld.resolutionKeepOrganization}
            </button>
            <button
              className="button secondary"
              data-resolution-action="dismiss"
              disabled={resolutionInFlight || !onResolve}
              onClick={() => submit("dismissed")}
              type="button"
            >
              {pendingForCandidate
                ? M.companyWorld.resolvingCandidate
                : M.companyWorld.dismissCandidate}
            </button>
          </>
        ) : (
          <>
            <button
              className="button secondary"
              disabled={resolutionInFlight}
              onClick={moveBack}
              type="button"
            >
              {M.companyWorld.resolutionBack}
            </button>
            <button
              className="button"
              data-resolution-action="confirm"
              disabled={resolutionInFlight || !onResolve}
              type="submit"
            >
              {pendingForCandidate
                ? M.companyWorld.resolvingCandidate
                : isFinalStep
                  ? M.companyWorld.resolutionSave
                  : M.companyWorld.resolutionContinue}
            </button>
          </>
        )}
      </div>
    </form>
  );
}

function ResolutionNotice({
  announce = true,
  state,
  visuallyHidden = false
}: {
  announce?: boolean;
  state: CompanyWorldResolutionState;
  visuallyHidden?: boolean;
}) {
  if (state.status === "idle" || !state.message) {
    return null;
  }
  return (
    <div
      aria-label={M.companyWorld.resolutionStatusLabel}
      aria-live={announce ? "polite" : undefined}
      className={`world-resolution-notice world-resolution-notice--${state.status}${
        visuallyHidden ? " world-resolution-announcer" : ""
      }`}
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

function TouchpointProfile({
  headingId,
  touchpoint
}: {
  headingId: string;
  touchpoint: CompanyMapTouchpoint;
}) {
  return (
    <>
      <span className="eyebrow">{M.companyWorld.touchpointProfile}</span>
      <h3 id={headingId}>{touchpoint.subject}</h3>
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
      {touchpoint.source_url ? (
        <SourceLink url={touchpoint.source_url}>{M.common.openSource}</SourceLink>
      ) : null}
    </>
  );
}

function ProfileTouchpointHistory({
  isCompanyProfile,
  onSelect,
  selectedKey,
  touchpoints
}: {
  isCompanyProfile: boolean;
  onSelect: (key: string) => void;
  selectedKey: string | null;
  touchpoints: CompanyMapTouchpoint[];
}) {
  const { remainingTouchpoints, visibleTouchpoints } =
    splitCompanyWorldProfileTouchpoints(touchpoints);

  return (
    <section className="world-timeline world-profile-timeline">
      <h4>
        {isCompanyProfile
          ? M.companyWorld.allCompanyTouchpoints
          : M.companyWorld.profileTimeline}
      </h4>
      {touchpoints.length > 0 ? (
        <>
          <ProfileTouchpointList
            onSelect={onSelect}
            selectedKey={selectedKey}
            touchpoints={visibleTouchpoints}
          />
          {remainingTouchpoints.length > 0 ? (
            <details className="world-profile-timeline-more">
              <summary>
                {M.companyWorld.showMoreTouchpoints} ({remainingTouchpoints.length})
              </summary>
              <ProfileTouchpointList
                onSelect={onSelect}
                selectedKey={selectedKey}
                touchpoints={remainingTouchpoints}
              />
            </details>
          ) : null}
        </>
      ) : (
        <p className="muted">{M.companyWorld.noProfileTouchpoints}</p>
      )}
    </section>
  );
}

export function splitCompanyWorldProfileTouchpoints(
  touchpoints: CompanyMapTouchpoint[]
): {
  remainingTouchpoints: CompanyMapTouchpoint[];
  visibleTouchpoints: CompanyMapTouchpoint[];
} {
  return {
    visibleTouchpoints: touchpoints.slice(0, 3),
    remainingTouchpoints: touchpoints.slice(3)
  };
}

function ProfileTouchpointList({
  onSelect,
  selectedKey,
  touchpoints
}: {
  onSelect: (key: string) => void;
  selectedKey: string | null;
  touchpoints: CompanyMapTouchpoint[];
}) {
  return (
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
  );
}

export function relatedCompanyWorldTouchpoints(
  data: CompanyMapResponse,
  selectedKey: string
): CompanyMapTouchpoint[] {
  if (selectedKey === data.company.key) {
    return data.touchpoints;
  }
  const selectedTouchpoint = data.touchpoints.find(
    (touchpoint) => touchpoint.key === selectedKey
  );
  if (selectedTouchpoint) {
    return [selectedTouchpoint];
  }
  return data.touchpoints.filter(
    (touchpoint) =>
      touchpoint.person_keys.includes(selectedKey) ||
      touchpoint.organization_keys.includes(selectedKey)
  );
}

function CompanyWorldTechnicalBoundary({ data }: { data: CompanyMapResponse }) {
  return (
    <details className="world-technical-boundary">
      <summary>{M.companyWorld.technicalDisclosure}</summary>
      <div className="world-technical-boundary-body">
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
      </div>
    </details>
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
    <details className="world-evidence">
      <summary>
        <span>{M.companyWorld.evidenceDisclosure}</span>
        <small>{refs.length}</small>
      </summary>
      <div>
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
      </div>
    </details>
  );
}

function roleLabel(role: CompanyMapInternalPerson["role"]): string {
  return M.companyWorld.roles[role];
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

function formatWindowCount(value: number, isLowerBound: boolean): string {
  return `${isLowerBound ? "≥" : ""}${value}${
    isLowerBound ? ` · ${M.companyWorld.inShownWindow}` : ""
  }`;
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

function focusCompanyWorldProfile(profile: HTMLElement | null): void {
  if (!profile || typeof window === "undefined") {
    return;
  }
  profile.focus({ preventScroll: true });
  if (
    typeof window.matchMedia !== "function" ||
    !window.matchMedia("(max-width: 1320px)").matches
  ) {
    return;
  }
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  profile.scrollIntoView({
    behavior: reduceMotion ? "auto" : "smooth",
    block: "start"
  });
}
