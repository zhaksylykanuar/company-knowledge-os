import type { TodayFacts } from "./today";
import { M } from "./messages";
import { buildCompanyWorldProfileTarget } from "./company-world-profile";
import type {
  ActionProposal,
  ActionProposalEvidenceRef,
  CompanyBrainSourceRef,
  CompanyMapResponse
} from "./types";

const MAX_VISIBLE_CHANGES = 6;
const MAX_WORLD_EVIDENCE_PREVIEW = 8;
const COPY = M.livingHq.viewModel;

export type LivingHqEvidenceState =
  | "aggregate"
  | "direct"
  | "referenced"
  | "unavailable";

export type LivingHqEvidenceRef = {
  key: string;
  kind: string;
  source: string;
  label: string;
  url: string | null;
};

export type LivingHqMissionKind =
  | "connect_source"
  | "create_briefing"
  | "create_workspace"
  | "open_briefing"
  | "refresh"
  | "review_proposal"
  | "review_world";

export type LivingHqMission = {
  id: string;
  kind: LivingHqMissionKind;
  title: string;
  description: string;
  why: string;
  href: string | null;
  actionLabel: string;
  canAct: boolean;
  proposalId: string | null;
  evidenceState: LivingHqEvidenceState;
  evidence: LivingHqEvidenceRef[];
};

export type LivingHqChangeKind =
  | "organization_candidate"
  | "person_candidate"
  | "proposal"
  | "touchpoint";

export type LivingHqChange = {
  id: string;
  kind: LivingHqChangeKind;
  title: string;
  description: string;
  occurredAt: string | null;
  href: string;
  evidenceState: "direct" | "referenced";
  evidence: LivingHqEvidenceRef[];
};

export type LivingHqMetricPrecision = "at_least" | "exact" | "unavailable";

export type LivingHqWorldMetricKey =
  | "confirmed_external_people"
  | "confirmed_organizations"
  | "internal_people"
  | "pending_confirmations"
  | "source_records"
  | "touchpoints";

export type LivingHqWorldMetric = {
  key: LivingHqWorldMetricKey;
  label: string;
  value: number | null;
  precision: LivingHqMetricPrecision;
};

export type LivingHqWorldSummary = {
  availability: "partial" | "ready" | "unavailable";
  companyName: string | null;
  metrics: readonly LivingHqWorldMetric[];
  evidenceCount: number;
  evidencePreview: LivingHqEvidenceRef[];
  isLive: false | null;
  warnings: string[];
};

export type LivingHqInputIssue =
  | "company_map_workspace_mismatch"
  | "proposal_workspace_mismatch";

export type LivingHqViewModel = {
  isPartial: boolean;
  mission: LivingHqMission;
  changes: LivingHqChange[];
  changeBasis: "current_evidence_snapshot";
  changesAreSinceLastVisit: false;
  omittedChangeCount: number;
  unsupportedSignalCount: number;
  world: LivingHqWorldSummary;
  inputIssues: LivingHqInputIssue[];
};

export type LivingHqInput = {
  facts: TodayFacts;
  companyMap?: CompanyMapResponse | null;
  actionProposals?: readonly ActionProposal[] | null;
};

/**
 * Builds the Living HQ screen from already loaded, workspace-scoped facts.
 * It performs no reads or writes and never upgrades an aggregate count into a
 * specific claim without direct evidence refs.
 */
export function deriveLivingHqView({
  facts,
  companyMap = null,
  actionProposals = null
}: LivingHqInput): LivingHqViewModel {
  const inputIssues: LivingHqInputIssue[] = [];
  const scopedMap = scopeCompanyMap(facts, companyMap, inputIssues);
  const scopedProposals = scopeActionProposals(
    facts,
    actionProposals,
    inputIssues
  );
  const changeCandidates = buildChangeCandidates(scopedMap, scopedProposals);
  const supportedChanges = changeCandidates
    .filter((candidate) => candidate.change !== null)
    .map((candidate) => candidate.change as LivingHqChange)
    .sort(compareChanges);
  const changes = supportedChanges.slice(0, MAX_VISIBLE_CHANGES);
  const world = buildWorldSummary(facts, scopedMap);

  return {
    isPartial:
      factsArePartial(facts) ||
      companyMap === null ||
      actionProposals === null ||
      scopedMap?.window.truncated === true ||
      inputIssues.length > 0,
    mission: buildMission(facts, scopedMap, scopedProposals),
    changes,
    changeBasis: "current_evidence_snapshot",
    changesAreSinceLastVisit: false,
    omittedChangeCount: Math.max(0, supportedChanges.length - changes.length),
    unsupportedSignalCount: changeCandidates.filter(
      (candidate) => candidate.change === null
    ).length,
    world,
    inputIssues
  };
}

function scopeCompanyMap(
  facts: TodayFacts,
  companyMap: CompanyMapResponse | null,
  inputIssues: LivingHqInputIssue[]
): CompanyMapResponse | null {
  if (!companyMap) {
    return null;
  }
  if (!facts.workspaceId || companyMap.workspace_id !== facts.workspaceId) {
    inputIssues.push("company_map_workspace_mismatch");
    return null;
  }
  return companyMap;
}

function scopeActionProposals(
  facts: TodayFacts,
  actionProposals: readonly ActionProposal[] | null,
  inputIssues: LivingHqInputIssue[]
): ActionProposal[] {
  if (!actionProposals) {
    return [];
  }
  const scoped = facts.workspaceId
    ? actionProposals.filter(
        (proposal) => proposal.workspace_id === facts.workspaceId
      )
    : [];
  if (scoped.length !== actionProposals.length) {
    inputIssues.push("proposal_workspace_mismatch");
  }
  return scoped;
}

function buildMission(
  facts: TodayFacts,
  companyMap: CompanyMapResponse | null,
  actionProposals: readonly ActionProposal[]
): LivingHqMission {
  const canReviewProposals = facts.role === "owner" || facts.role === "admin";

  if (!facts.workspaceId) {
    return aggregateMission({
      id: "create-workspace",
      kind: "create_workspace",
      title: COPY.missions.createWorkspaceTitle,
      description: COPY.missions.createWorkspaceDescription,
      why: COPY.missions.createWorkspaceWhy,
      href: "/onboarding",
      actionLabel: COPY.missions.start,
      canAct: true
    });
  }

  const supportedProposal = [...actionProposals]
    .filter(
      (proposal) =>
        proposal.status === "proposed" &&
        normalizeActionEvidence(proposal.evidence_refs).length > 0
    )
    .sort(compareProposals)[0];
  if (supportedProposal) {
    return {
      id: `proposal:${supportedProposal.id}`,
      kind: "review_proposal",
      title: supportedProposal.title,
      description:
        cleanText(supportedProposal.description) ??
        COPY.missions.proposalFallbackDescription,
      why: COPY.missions.proposalWhy,
      href: "/actions?status=proposed",
      actionLabel: canReviewProposals
        ? COPY.missions.reviewMission
        : COPY.missions.viewMission,
      canAct: canReviewProposals,
      proposalId: supportedProposal.id,
      evidenceState: "referenced",
      evidence: normalizeActionEvidence(supportedProposal.evidence_refs)
    };
  }

  if (facts.sourceRecordCount === 0) {
    const canManageSources = facts.role === "owner" || facts.role === "admin";
    return aggregateMission({
      id: "connect-source",
      kind: "connect_source",
      title: COPY.missions.connectSourceTitle,
      description: canManageSources
        ? COPY.missions.connectSourceDescription
        : COPY.missions.connectSourceReadOnlyDescription,
      why: COPY.missions.connectSourceWhy,
      href: canManageSources ? "/github" : "/connectors",
      actionLabel: canManageSources
        ? COPY.missions.connectGithub
        : COPY.missions.viewRadars,
      canAct: canManageSources
    });
  }

  const proposedCount = actionProposals.filter(
    (proposal) => proposal.status === "proposed"
  ).length;
  if (proposedCount > 0 || (facts.proposedDecisionCount ?? 0) > 0) {
    const visibleCount = Math.max(
      proposedCount,
      facts.proposedDecisionCount ?? 0
    );
    return {
      ...aggregateMission({
        id: "review-proposals",
        kind: "review_proposal",
        title: COPY.missions.reviewProposalsTitle,
        description: COPY.missions.reviewProposalsDescription(visibleCount),
        why: COPY.missions.reviewProposalsWhy,
        href: "/actions?status=proposed",
        actionLabel: canReviewProposals
          ? COPY.missions.reviewQueue
          : COPY.missions.viewQueue,
        canAct: canReviewProposals
      }),
      evidenceState: "unavailable"
    };
  }

  const worldCandidate = firstSupportedWorldCandidate(companyMap);
  if (worldCandidate) {
    const canResolve = companyMap?.capabilities.can_resolve === true;
    return {
      id: `world:${worldCandidate.id}`,
      kind: "review_world",
      title: worldCandidate.title,
      description: COPY.missions.reviewWorldDescription,
      why: COPY.missions.reviewWorldWhy,
      href: worldCandidate.href,
      actionLabel: canResolve
        ? COPY.missions.reviewRelationship
        : COPY.missions.viewRelationship,
      canAct: canResolve,
      proposalId: null,
      evidenceState: "direct",
      evidence: worldCandidate.evidence
    };
  }

  const candidateCount = companyMap
    ? companyMap.people.external_candidates.length +
      companyMap.organizations.length
    : facts.candidateCount ?? 0;
  if (candidateCount > 0) {
    return {
      ...aggregateMission({
        id: "review-world",
        kind: "review_world",
        title: COPY.missions.reviewCandidatesTitle,
        description: COPY.missions.reviewCandidatesDescription(candidateCount),
        why: COPY.missions.reviewCandidatesWhy,
        href: "/company-brain",
        actionLabel: COPY.missions.openWorld,
        canAct: companyMap?.capabilities.can_resolve === true
      }),
      evidenceState: "unavailable"
    };
  }

  if (factsArePartial(facts)) {
    return {
      ...aggregateMission({
        id: "refresh-facts",
        kind: "refresh",
        title: COPY.missions.refreshTitle,
        description: COPY.missions.refreshDescription,
        why: COPY.missions.refreshWhy,
        href: null,
        actionLabel: COPY.missions.refreshAction,
        canAct: true
      }),
      evidenceState: "unavailable"
    };
  }

  if (facts.briefingCount === 0) {
    const canCreate = facts.role !== "viewer";
    return aggregateMission({
      id: "create-briefing",
      kind: "create_briefing",
      title: COPY.missions.createBriefingTitle,
      description: COPY.missions.createBriefingDescription,
      why: COPY.missions.createBriefingWhy,
      href: "/briefings",
      actionLabel: canCreate
        ? COPY.missions.createBriefing
        : COPY.missions.viewBriefings,
      canAct: canCreate
    });
  }

  return aggregateMission({
    id: "open-briefing",
    kind: "open_briefing",
    title: COPY.missions.openBriefingTitle,
    description: COPY.missions.openBriefingDescription,
    why: COPY.missions.openBriefingWhy,
    href: "/briefings",
    actionLabel: COPY.missions.openBriefing,
    canAct: true
  });
}

function aggregateMission(
  mission: Omit<
    LivingHqMission,
    "evidence" | "evidenceState" | "proposalId"
  >
): LivingHqMission {
  return {
    ...mission,
    proposalId: null,
    evidenceState: "aggregate",
    evidence: []
  };
}

type SupportedWorldCandidate = {
  href: string;
  id: string;
  title: string;
  occurredAt: string | null;
  evidence: LivingHqEvidenceRef[];
};

function firstSupportedWorldCandidate(
  companyMap: CompanyMapResponse | null
): SupportedWorldCandidate | null {
  if (!companyMap) {
    return null;
  }
  const candidates: SupportedWorldCandidate[] = [
    ...companyMap.people.external_candidates.map((person) => ({
      href:
        buildCompanyWorldProfileTarget(companyMap, person.key)?.href ??
        "/company-brain",
      id: person.key,
      title: COPY.missions.reviewWorldPersonTitle(
        person.display_name || person.email
      ),
      occurredAt: person.last_interaction_at,
      evidence: normalizeCompanyEvidence(person.source_refs)
    })),
    ...companyMap.organizations.map((organization) => ({
      href:
        buildCompanyWorldProfileTarget(companyMap, organization.key)?.href ??
        "/company-brain",
      id: organization.key,
      title: COPY.missions.reviewWorldOrganizationTitle(
        organization.name || organization.domain
      ),
      occurredAt: organization.last_interaction_at,
      evidence: normalizeCompanyEvidence(organization.source_refs)
    }))
  ].filter((candidate) => candidate.evidence.length > 0);

  return candidates.sort((left, right) =>
    compareLatest(left.occurredAt, right.occurredAt, left.id, right.id)
  )[0] ?? null;
}

type ChangeCandidate = {
  change: LivingHqChange | null;
};

function buildChangeCandidates(
  companyMap: CompanyMapResponse | null,
  actionProposals: readonly ActionProposal[]
): ChangeCandidate[] {
  const candidates: ChangeCandidate[] = actionProposals.map((proposal) => {
    const evidence = normalizeActionEvidence(proposal.evidence_refs);
    return {
      change:
        evidence.length === 0
          ? null
          : {
              id: `proposal:${proposal.id}`,
              kind: "proposal",
              title: proposalChangeTitle(proposal),
              description:
                cleanText(proposal.description) ??
                COPY.changes.proposalFallbackDescription,
              occurredAt: proposal.updated_at,
              href: "/actions",
              evidenceState: "referenced",
              evidence
            }
    };
  });

  if (!companyMap) {
    return candidates;
  }

  for (const touchpoint of companyMap.touchpoints) {
    const evidence = normalizeCompanyEvidence(touchpoint.source_refs);
    candidates.push({
      change:
        evidence.length === 0
          ? null
          : {
              id: `touchpoint:${touchpoint.key}`,
              kind: "touchpoint",
              title: touchpoint.subject || COPY.changes.touchpointFallbackTitle,
              description: touchpointDescription(touchpoint.direction),
              occurredAt: touchpoint.occurred_at,
              href: "/company-brain",
              evidenceState: "direct",
              evidence
            }
    });
  }

  for (const person of companyMap.people.external_candidates) {
    const evidence = normalizeCompanyEvidence(person.source_refs);
    candidates.push({
      change:
        evidence.length === 0
          ? null
          : {
              id: `person:${person.key}`,
              kind: "person_candidate",
              title: person.display_name || person.email,
              description: COPY.changes.personCandidateDescription,
              occurredAt: person.last_interaction_at,
              href:
                buildCompanyWorldProfileTarget(companyMap, person.key)?.href ??
                "/company-brain",
              evidenceState: "direct",
              evidence
            }
    });
  }

  for (const organization of companyMap.organizations) {
    const evidence = normalizeCompanyEvidence(organization.source_refs);
    candidates.push({
      change:
        evidence.length === 0
          ? null
          : {
              id: `organization:${organization.key}`,
              kind: "organization_candidate",
              title: organization.name || organization.domain,
              description: COPY.changes.organizationCandidateDescription,
              occurredAt: organization.last_interaction_at,
              href:
                buildCompanyWorldProfileTarget(companyMap, organization.key)?.href ??
                "/company-brain",
              evidenceState: "direct",
              evidence
            }
    });
  }

  return candidates;
}

function proposalChangeTitle(proposal: ActionProposal): string {
  const prefix: Record<string, string> = {
    approved: COPY.changes.proposalStatus.approved,
    executed: COPY.changes.proposalStatus.executed,
    failed: COPY.changes.proposalStatus.failed,
    proposed: COPY.changes.proposalStatus.proposed,
    rejected: COPY.changes.proposalStatus.rejected
  };
  return `${prefix[proposal.status] ?? COPY.changes.proposalStatus.fallback}: ${
    proposal.title
  }`;
}

function touchpointDescription(direction: string): string {
  const directionLabel: Record<string, string> = {
    inbound: COPY.changes.touchpointDirection.inbound,
    mixed: COPY.changes.touchpointDirection.mixed,
    outbound: COPY.changes.touchpointDirection.outbound,
    unknown: COPY.changes.touchpointDirection.unknown
  };
  return COPY.changes.touchpointDescription(
    directionLabel[direction] ?? directionLabel.unknown
  );
}

function compareChanges(left: LivingHqChange, right: LivingHqChange): number {
  return compareLatest(left.occurredAt, right.occurredAt, left.id, right.id);
}

function compareProposals(left: ActionProposal, right: ActionProposal): number {
  const severityDifference =
    proposalSeverityRank(right) - proposalSeverityRank(left);
  if (severityDifference !== 0) {
    return severityDifference;
  }
  return compareLatest(left.updated_at, right.updated_at, left.id, right.id);
}

function proposalSeverityRank(proposal: ActionProposal): number {
  const severity = cleanText(proposal.payload.severity);
  const rank: Record<string, number> = {
    critical: 4,
    high: 3,
    medium: 2,
    low: 1,
    info: 0
  };
  return severity ? rank[severity.toLowerCase()] ?? 0 : 0;
}

function compareLatest(
  leftDate: string | null,
  rightDate: string | null,
  leftId: string,
  rightId: string
): number {
  const dateDifference = timestamp(rightDate) - timestamp(leftDate);
  return dateDifference !== 0 ? dateDifference : leftId.localeCompare(rightId);
}

function timestamp(value: string | null): number {
  if (!value) {
    return Number.NEGATIVE_INFINITY;
  }
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? Number.NEGATIVE_INFINITY : parsed;
}

function buildWorldSummary(
  facts: TodayFacts,
  companyMap: CompanyMapResponse | null
): LivingHqWorldSummary {
  if (!companyMap) {
    return {
      availability: "unavailable",
      companyName: facts.workspaceName,
      metrics: [
        metric("internal_people", COPY.metrics.internalPeople, facts.memberCount),
        metric(
          "confirmed_external_people",
          COPY.metrics.confirmedExternalPeople,
          null
        ),
        metric(
          "confirmed_organizations",
          COPY.metrics.confirmedOrganizations,
          null
        ),
        metric(
          "pending_confirmations",
          COPY.metrics.pendingConfirmations,
          facts.candidateCount,
          { atLeast: facts.candidateCountIsLowerBound }
        ),
        metric("touchpoints", COPY.metrics.touchpoints, null),
        metric("source_records", COPY.metrics.sourceRecords, facts.sourceRecordCount)
      ],
      evidenceCount: 0,
      evidencePreview: [],
      isLive: null,
      warnings: []
    };
  }

  const allEvidence = normalizeCompanyEvidence([
    ...companyMap.company.source_refs,
    ...companyMap.people.internal.flatMap((person) => person.source_refs),
    ...companyMap.people.confirmed_external.flatMap(
      (person) => person.source_refs
    ),
    ...companyMap.people.external_candidates.flatMap(
      (person) => person.source_refs
    ),
    ...companyMap.confirmed_organizations.flatMap(
      (organization) => organization.source_refs
    ),
    ...companyMap.organizations.flatMap(
      (organization) => organization.source_refs
    ),
    ...companyMap.touchpoints.flatMap((touchpoint) => touchpoint.source_refs)
  ]);
  const windowIsPartial = companyMap.window.truncated;

  return {
    availability: windowIsPartial ? "partial" : "ready",
    companyName: companyMap.company.name || facts.workspaceName,
    metrics: [
      metric(
        "internal_people",
        COPY.metrics.internalPeople,
        companyMap.summary.internal_people
      ),
      metric(
        "confirmed_external_people",
        COPY.metrics.confirmedExternalPeople,
        companyMap.summary.confirmed_external_people
      ),
      metric(
        "confirmed_organizations",
        COPY.metrics.confirmedOrganizations,
        companyMap.summary.confirmed_organizations
      ),
      metric(
        "pending_confirmations",
        COPY.metrics.pendingConfirmations,
        companyMap.people.external_candidates.length +
          companyMap.organizations.length,
        { atLeast: windowIsPartial }
      ),
      metric(
        "touchpoints",
        COPY.metrics.touchpoints,
        companyMap.summary.touchpoints_in_window,
        { atLeast: windowIsPartial }
      ),
      metric("source_records", COPY.metrics.sourceRecords, facts.sourceRecordCount)
    ],
    evidenceCount: allEvidence.length,
    evidencePreview: allEvidence.slice(0, MAX_WORLD_EVIDENCE_PREVIEW),
    isLive: false,
    warnings: [...companyMap.warnings]
  };
}

function metric(
  key: LivingHqWorldMetricKey,
  label: string,
  value: number | null,
  { atLeast = false }: { atLeast?: boolean } = {}
): LivingHqWorldMetric {
  return {
    key,
    label,
    value,
    precision: value === null ? "unavailable" : atLeast ? "at_least" : "exact"
  };
}

function normalizeActionEvidence(
  evidenceRefs: readonly ActionProposalEvidenceRef[]
): LivingHqEvidenceRef[] {
  return dedupeEvidence(
    evidenceRefs.flatMap((evidence) => {
      const source = cleanText(evidence.source);
      const kind = cleanText(evidence.kind);
      const ref = cleanText(evidence.ref);
      if (!source || !kind || !ref) {
        return [];
      }
      return [
        {
          key: `${source}:${kind}:${ref}`,
          kind,
          source,
          label: ref,
          url: cleanText(evidence.url) ?? null
        }
      ];
    })
  );
}

function normalizeCompanyEvidence(
  evidenceRefs: readonly CompanyBrainSourceRef[]
): LivingHqEvidenceRef[] {
  return dedupeEvidence(
    evidenceRefs.flatMap((evidence) => {
      const source = cleanText(evidence.source);
      const kind = cleanText(evidence.kind);
      const id = cleanText(evidence.id);
      if (!source || !kind || !id) {
        return [];
      }
      return [
        {
          key: `${source}:${kind}:${id}`,
          kind,
          source,
          label: cleanText(evidence.label) ?? id,
          url: cleanText(evidence.url) ?? null
        }
      ];
    })
  );
}

function dedupeEvidence(
  evidenceRefs: readonly LivingHqEvidenceRef[]
): LivingHqEvidenceRef[] {
  const unique = new Map<string, LivingHqEvidenceRef>();
  for (const evidence of evidenceRefs) {
    if (!unique.has(evidence.key)) {
      unique.set(evidence.key, evidence);
    }
  }
  return [...unique.values()].sort((left, right) =>
    left.key.localeCompare(right.key)
  );
}

function factsArePartial(facts: TodayFacts): boolean {
  return (
    [
      facts.briefingCount,
      facts.candidateCount,
      facts.memberCount,
      facts.proposedDecisionCount,
      facts.sourceRecordCount
    ].some((value) => value === null) ||
    facts.candidateCountIsLowerBound === true ||
    facts.proposedDecisionCountIsLowerBound === true
  );
}

function cleanText(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}
