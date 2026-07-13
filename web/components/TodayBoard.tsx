"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { fetchActionProposals, listBriefings } from "../lib/api";
import { M } from "../lib/messages";
import {
  loadOnboardingSnapshot,
  type OnboardingSnapshot
} from "../lib/onboarding";
import { useSession } from "../lib/session";
import {
  deriveTodayView,
  type TodayFacts,
  type TodayMove,
  type TodaySignal
} from "../lib/today";

type TodayBoardViewProps = {
  facts: TodayFacts;
  onRetry?: () => void;
};

export function TodayBoard() {
  const session = useSession();
  const workspaceId = session?.workspaceId ?? null;
  const workspace =
    session?.workspaces.find((item) => item.id === workspaceId) ?? null;
  const [facts, setFacts] = useState<TodayFacts | null>(null);
  const [loadingWorkspaceId, setLoadingWorkspaceId] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    if (!workspaceId) {
      setFacts({
        briefingCount: null,
        candidateCount: null,
        candidateCountIsLowerBound: false,
        memberCount: null,
        proposedDecisionCount: null,
        proposedDecisionCountIsLowerBound: false,
        role: null,
        sourceRecordCount: null,
        workspaceId: null,
        workspaceName: null
      });
      setLoadingWorkspaceId(null);
      return;
    }

    let cancelled = false;
    setLoadingWorkspaceId(workspaceId);

    Promise.allSettled([
      loadOnboardingSnapshot(workspaceId),
      listBriefings(workspaceId, { limit: 1 }),
      fetchActionProposals(workspaceId, { status: "proposed", limit: 50 })
    ]).then(([onboardingResult, briefingResult, actionResult]) => {
      if (cancelled) {
        return;
      }

      const snapshot =
        onboardingResult.status === "fulfilled" ? onboardingResult.value : null;
      const nextFacts = factsFromResponses({
        actionCount:
          actionResult.status === "fulfilled"
            ? actionResult.value.proposals.filter(
                (proposal) => proposal.status === "proposed"
              ).length
            : null,
        actionCountIsLowerBound:
          actionResult.status === "fulfilled" && actionResult.value.count >= 50,
        briefingCount:
          briefingResult.status === "fulfilled" ? briefingResult.value.count : null,
        role: workspace?.role ?? null,
        snapshot,
        workspaceId,
        workspaceName: workspace?.name ?? null
      });

      setFacts(nextFacts);
      setLoadingWorkspaceId(null);
    });

    return () => {
      cancelled = true;
    };
  }, [reloadKey, workspace?.name, workspace?.role, workspaceId]);

  if (workspaceId && (facts?.workspaceId !== workspaceId || loadingWorkspaceId)) {
    return <TodayLoading workspaceName={workspace?.name ?? null} />;
  }

  if (!facts) {
    return <TodayLoading workspaceName={workspace?.name ?? null} />;
  }

  return (
    <TodayBoardView
      facts={facts}
      onRetry={() => setReloadKey((current) => current + 1)}
    />
  );
}

export function TodayBoardView({ facts, onRetry }: TodayBoardViewProps) {
  const view = deriveTodayView(facts);
  const activeStage = stageForMove(view.move);

  return (
    <section className="today-board" aria-labelledby="today-title">
      <header className="today-heading">
        <div className="today-heading-copy">
          <span className="eyebrow">{M.today.eyebrow}</span>
          <h1 id="today-title">{M.today.title}</h1>
          <p>{M.today.description}</p>
        </div>
        <div className="today-company-chip">
          <span className="today-live-dot" aria-hidden="true" />
          <span>{M.today.livePicture}</span>
          <strong>{facts.workspaceName ?? M.today.noWorkspace}</strong>
        </div>
      </header>

      <ol className="company-cycle" aria-label={M.today.cycleLabel}>
        {[M.today.cycle.signal, M.today.cycle.decide, M.today.cycle.change].map(
          (label, index) => (
            <li
              aria-current={index === activeStage ? "step" : undefined}
              className={index === activeStage ? "active" : undefined}
              key={label}
            >
              <span aria-hidden="true">{index + 1}</span>
              {label}
            </li>
          )
        )}
      </ol>

      <section className="today-move" aria-labelledby="today-move-title">
        <div className="today-move-main">
          <span className="today-move-label">{M.today.nextMove}</span>
          <h2 id="today-move-title">{view.move.title}</h2>
          <p>{view.move.description}</p>
          {view.move.href ? (
            <Link className="today-primary-action" href={view.move.href}>
              <span>{M.today.openMove}</span>
              <span aria-hidden="true">→</span>
            </Link>
          ) : (
            <button className="today-primary-action" onClick={onRetry} type="button">
              <span>{M.today.retryMove}</span>
              <span aria-hidden="true">↻</span>
            </button>
          )}
        </div>
        <aside className="today-move-reason">
          <span>{M.today.whyNow}</span>
          <p>{view.move.reason}</p>
          <small>{M.today.sourceBoundary}</small>
        </aside>
      </section>

      <section className="today-signal-section" aria-labelledby="today-signals-title">
        <div className="today-signal-heading">
          <span className="eyebrow">{M.today.signalsLabel}</span>
          <h2 id="today-signals-title">{M.today.signalsTitle}</h2>
        </div>
        <div className="today-signals">
          {view.signals.map((signal) => (
            <SignalCard key={signal.label} signal={signal} />
          ))}
        </div>
      </section>

      <p className={view.isPartial ? "today-truth-note warning" : "today-truth-note"}>
        <span aria-hidden="true">{view.isPartial ? "!" : "✓"}</span>
        {view.isPartial ? M.today.picturePartial : M.today.pictureComplete}
      </p>
    </section>
  );
}

function TodayLoading({ workspaceName }: { workspaceName: string | null }) {
  return (
    <section className="today-board" aria-busy="true" aria-live="polite">
      <header className="today-heading">
        <div className="today-heading-copy">
          <span className="eyebrow">{M.today.eyebrow}</span>
          <h1>{M.today.title}</h1>
          <p>{M.today.description}</p>
        </div>
        {workspaceName ? (
          <div className="today-company-chip">
            <span className="today-live-dot" aria-hidden="true" />
            <strong>{workspaceName}</strong>
          </div>
        ) : null}
      </header>
      <div className="today-loading-card">
        <span className="today-loading-mark" aria-hidden="true" />
        <span>{M.today.loading}</span>
      </div>
    </section>
  );
}

function SignalCard({ signal }: { signal: TodaySignal }) {
  return (
    <article className={`today-signal today-signal--${signal.tone}`}>
      <div>
        <span>{signal.label}</span>
        <strong>{signal.value}</strong>
      </div>
      <p>{signal.description}</p>
    </article>
  );
}

function factsFromResponses({
  actionCount,
  actionCountIsLowerBound,
  briefingCount,
  role,
  snapshot,
  workspaceId,
  workspaceName
}: {
  actionCount: number | null;
  actionCountIsLowerBound: boolean;
  briefingCount: number | null;
  role: string | null;
  snapshot: OnboardingSnapshot | null;
  workspaceId: string;
  workspaceName: string | null;
}): TodayFacts {
  const sourceRecordCount =
    snapshot?.companyBrain?.source_records?.total ??
    (snapshot?.companyBrain ? 0 : null);
  const companyMap = snapshot?.companyMap ?? null;

  return {
    briefingCount,
    candidateCount: companyMap
      ? companyMap.people.external_candidates.length + companyMap.organizations.length
      : null,
    candidateCountIsLowerBound: companyMap?.window.truncated ?? false,
    memberCount: snapshot?.members?.members.length ?? null,
    proposedDecisionCount: actionCount,
    proposedDecisionCountIsLowerBound: actionCountIsLowerBound,
    role,
    sourceRecordCount,
    workspaceId,
    workspaceName
  };
}

function stageForMove(move: TodayMove): number {
  if (move.href?.startsWith("/actions") || move.href === "/company-brain") {
    return 1;
  }
  if (move.href?.startsWith("/settings")) {
    return 2;
  }
  return 0;
}
