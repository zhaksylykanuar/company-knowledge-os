import { M } from "./messages";

export type TodayFacts = {
  briefingCount: number | null;
  candidateCount: number | null;
  candidateCountIsLowerBound?: boolean;
  memberCount: number | null;
  proposedDecisionCount: number | null;
  proposedDecisionCountIsLowerBound?: boolean;
  role: string | null;
  sourceRecordCount: number | null;
  workspaceId: string | null;
  workspaceName: string | null;
};

export type TodayMove = {
  description: string;
  href: string | null;
  reason: string;
  title: string;
};

export type TodaySignalTone = "attention" | "calm" | "empty" | "unknown";

export type TodaySignal = {
  description: string;
  label: string;
  tone: TodaySignalTone;
  value: string;
};

export type TodayViewModel = {
  isPartial: boolean;
  move: TodayMove;
  signals: readonly [TodaySignal, TodaySignal, TodaySignal];
};

export function deriveTodayView(facts: TodayFacts): TodayViewModel {
  const canAdmin = facts.role === "owner" || facts.role === "admin";
  const canContribute = canAdmin || facts.role === "member";
  const signals = buildSignals(facts);
  const isPartial = [
    facts.briefingCount,
    facts.candidateCount,
    facts.memberCount,
    facts.proposedDecisionCount,
    facts.sourceRecordCount
  ].some((value) => value === null) || Boolean(facts.candidateCountIsLowerBound);

  if (!facts.workspaceId) {
    return {
      isPartial: true,
      move: {
        title: M.today.moves.createCompanyTitle,
        description: M.today.moves.createCompanyDescription,
        reason: M.today.moves.createCompanyReason,
        href: "/onboarding"
      },
      signals
    };
  }

  if (facts.sourceRecordCount === 0) {
    return {
      isPartial,
      move: canAdmin
        ? {
            title: M.today.moves.addSourceTitle,
            description: M.today.moves.addSourceDescription,
            reason: M.today.moves.addSourceReason,
            href: "/connectors"
          }
        : {
            title: M.today.moves.sourceReadOnlyTitle,
            description: M.today.moves.sourceReadOnlyDescription,
            reason: M.today.moves.sourceReadOnlyReason,
            href: "/connectors"
          },
      signals
    };
  }

  if ((facts.proposedDecisionCount ?? 0) > 0) {
    return {
      isPartial,
      move: {
        title: canAdmin
          ? M.today.moves.reviewDecisionsTitle
          : M.today.moves.observeDecisionsTitle,
        description: canAdmin
          ? M.today.moves.reviewDecisionsDescription
          : M.today.moves.observeDecisionsDescription,
        reason: M.today.moves.reviewDecisionsReason,
        href: "/actions?status=proposed"
      },
      signals
    };
  }

  if ((facts.candidateCount ?? 0) > 0) {
    return {
      isPartial,
      move: {
        title: canContribute
          ? M.today.moves.reviewMapTitle
          : M.today.moves.observeMapTitle,
        description: canContribute
          ? M.today.moves.reviewMapDescription
          : M.today.moves.observeMapDescription,
        reason: M.today.moves.reviewMapReason,
        href: "/company-brain"
      },
      signals
    };
  }

  if (isPartial) {
    return {
      isPartial,
      move: {
        title: M.today.moves.refreshTitle,
        description: M.today.moves.refreshDescription,
        reason: M.today.moves.refreshReason,
        href: null
      },
      signals
    };
  }

  if (facts.briefingCount === 0) {
    return {
      isPartial,
      move: canContribute
        ? {
            title: M.today.moves.createBriefingTitle,
            description: M.today.moves.createBriefingDescription,
            reason: M.today.moves.createBriefingReason,
            href: "/briefings"
          }
        : {
            title: M.today.moves.observeBriefingTitle,
            description: M.today.moves.observeBriefingDescription,
            reason: M.today.moves.observeBriefingReason,
            href: "/briefings"
          },
      signals
    };
  }

  if (facts.memberCount === 1 && canAdmin) {
    return {
      isPartial,
      move: {
        title: M.today.moves.inviteTeamTitle,
        description: M.today.moves.inviteTeamDescription,
        reason: M.today.moves.inviteTeamReason,
        href: "/settings#team"
      },
      signals
    };
  }

  return {
    isPartial,
    move: {
      title: M.today.moves.openBriefingTitle,
      description: M.today.moves.openBriefingDescription,
      reason: M.today.moves.openBriefingReason,
      href: "/briefings"
    },
    signals
  };
}

function buildSignals(
  facts: TodayFacts
): readonly [TodaySignal, TodaySignal, TodaySignal] {
  return [
    countSignal({
      count: facts.sourceRecordCount,
      description: M.today.signalSourcesDescription,
      label: M.today.signalSources,
      zeroTone: "empty"
    }),
    countSignal({
      count: facts.proposedDecisionCount,
      description: M.today.signalDecisionsDescription,
      isLowerBound: facts.proposedDecisionCountIsLowerBound,
      label: M.today.signalDecisions,
      positiveTone: "attention"
    }),
    countSignal({
      count: facts.candidateCount,
      description: M.today.signalMapDescription,
      isLowerBound: facts.candidateCountIsLowerBound,
      label: M.today.signalMap,
      positiveTone: "attention"
    })
  ];
}

function countSignal({
  count,
  description,
  isLowerBound = false,
  label,
  positiveTone = "calm",
  zeroTone = "calm"
}: {
  count: number | null;
  description: string;
  isLowerBound?: boolean;
  label: string;
  positiveTone?: TodaySignalTone;
  zeroTone?: TodaySignalTone;
}): TodaySignal {
  if (count === null) {
    return {
      description,
      label,
      tone: "unknown",
      value: M.today.signalUnavailable
    };
  }

  return {
    description,
    label,
    tone: count > 0 ? positiveTone : zeroTone,
    value: isLowerBound
      ? count > 0
        ? `≥${count}`
        : M.today.signalPartial
      : String(count)
  };
}
