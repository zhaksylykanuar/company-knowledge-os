"use client";

import Link from "next/link";

import {
  deriveLivingHqView,
  type LivingHqChange,
  type LivingHqMission,
  type LivingHqWorldMetric
} from "../lib/living-hq";
import { M } from "../lib/messages";
import type { TodayFacts } from "../lib/today";
import type { ActionProposal, CompanyMapResponse } from "../lib/types";
import { HeadquartersDashboard } from "./HeadquartersDashboard";
import { LivingWorldMiniMap } from "./LivingWorldMiniMap";
import { SourceLink } from "./SourceLink";

type TodayBoardViewProps = {
  actionProposals?: readonly ActionProposal[] | null;
  companyMapState?: CompanyMapLoadState;
  companyMap?: CompanyMapResponse | null;
  facts: TodayFacts;
  isDataPartial?: boolean;
  onRetry?: () => void;
  radarSummary?: RadarSummary;
};

type CompanyMapLoadState = "empty" | "error" | "ready";

type RadarSummary = {
  connectedCount: number | null;
  state: "attention" | "connected" | "empty" | "unknown";
};

/** Compatibility export: every production Today entry now uses the canonical HQ read. */
export function TodayBoard() {
  return <HeadquartersDashboard />;
}

export function TodayBoardView({
  actionProposals = null,
  companyMap = null,
  companyMapState = companyMap ? "ready" : "empty",
  facts,
  isDataPartial = false,
  onRetry,
  radarSummary = unknownRadarSummary()
}: TodayBoardViewProps) {
  const view = deriveLivingHqView({ facts, companyMap, actionProposals });
  const safeCompanyMap =
    companyMap && facts.workspaceId === companyMap.workspace_id ? companyMap : null;
  const resolvedCompanyMapState =
    companyMap && safeCompanyMap === null ? "error" : companyMapState;
  const isPartial = view.isPartial || isDataPartial;

  return (
    <section className="living-hq" aria-labelledby="living-hq-title">
      <header className="living-hq-header">
        <div>
          <span className="eyebrow">{M.livingHq.eyebrow}</span>
          <h1 id="living-hq-title">
            {facts.workspaceName ?? M.livingHq.fallbackCompany}
          </h1>
          <p>{M.livingHq.description}</p>
        </div>
        <div className="living-hq-status" aria-label={M.livingHq.statusLabel}>
          <Link
            className="living-hq-radar"
            data-state={radarSummary.state}
            href="/connectors"
          >
            <span className="living-hq-radar-dot" aria-hidden="true" />
            <span>{M.livingHq.radars}</span>
            <strong>{formatRadarSummary(radarSummary)}</strong>
          </Link>
          <span className="living-hq-snapshot">{M.livingHq.currentSnapshot}</span>
        </div>
      </header>

      <div className="living-hq-command-grid">
        <MissionCard mission={view.mission} onRetry={onRetry} />
        <MissionContext mission={view.mission} />
      </div>

      <LivingWorldMiniMap
        data={safeCompanyMap}
        onRetry={onRetry}
        state={resolvedCompanyMapState}
        workspaceName={facts.workspaceName ?? M.livingHq.fallbackCompany}
      />

      <div className="living-hq-lower-grid">
        <ChangeFeed
          changes={view.changes}
          isPartial={isPartial}
          omittedCount={view.omittedChangeCount}
          unsupportedCount={view.unsupportedSignalCount}
        />
        <WorldPulse availability={view.world.availability} metrics={view.world.metrics} />
      </div>

      <p
        className={
          isPartial
            ? "living-hq-truth-note living-hq-truth-note--partial"
            : "living-hq-truth-note"
        }
      >
        <span aria-hidden="true">{isPartial ? "!" : "✓"}</span>
        {isPartial ? M.livingHq.partial : M.livingHq.complete}
      </p>
    </section>
  );
}

function MissionCard({
  mission,
  onRetry
}: {
  mission: LivingHqMission;
  onRetry?: () => void;
}) {
  const evidenceLabel =
    mission.evidenceState === "direct"
      ? `${mission.evidence.length} ${evidenceWord(mission.evidence.length)}`
      : mission.evidenceState === "referenced"
        ? M.livingHq.referencedBasis(mission.evidence.length)
        : M.livingHq.aggregateBasis;

  return (
    <article className="living-hq-mission" aria-labelledby="living-hq-mission-title">
      <div className="living-hq-mission-topline">
        <span>{M.livingHq.moveNow}</span>
        <span>{evidenceLabel}</span>
      </div>
      <div className="living-hq-mission-copy">
        <h2 id="living-hq-mission-title">{mission.title}</h2>
        <p>{mission.description}</p>
      </div>
      <div className="living-hq-mission-actions">
        {mission.href ? (
          <Link className="living-hq-primary-action" href={mission.href}>
            <span>{mission.actionLabel}</span>
            <span aria-hidden="true">→</span>
          </Link>
        ) : (
          <button
            className="living-hq-primary-action"
            onClick={onRetry}
            type="button"
          >
            <span>{mission.actionLabel}</span>
            <span aria-hidden="true">↻</span>
          </button>
        )}
        {!mission.canAct ? (
          <span className="living-hq-role-note">{M.livingHq.readOnly}</span>
        ) : null}
      </div>
    </article>
  );
}

function MissionContext({ mission }: { mission: LivingHqMission }) {
  return (
    <aside className="living-hq-context" aria-labelledby="living-hq-context-title">
      <span className="eyebrow">{M.livingHq.contextEyebrow}</span>
      <h2 id="living-hq-context-title">{M.livingHq.whyImportant}</h2>
      <p>{mission.why}</p>

      <details className="living-hq-evidence">
        <summary>
          {M.livingHq.whyFounderOs}
          <span>{missionEvidenceBadge(mission)}</span>
        </summary>
        {mission.evidence.length > 0 ? (
          <ul>
            {mission.evidence.map((evidence) => (
              <li key={evidence.key}>
                {evidence.url ? (
                  <SourceLink url={evidence.url}>
                    {evidence.label}
                  </SourceLink>
                ) : (
                  <span>{evidence.label}</span>
                )}
                <small>{evidence.source}</small>
              </li>
            ))}
          </ul>
        ) : (
          <p>{M.livingHq.aggregateExplanation}</p>
        )}
      </details>
    </aside>
  );
}

function ChangeFeed({
  changes,
  isPartial,
  omittedCount,
  unsupportedCount
}: {
  changes: readonly LivingHqChange[];
  isPartial: boolean;
  omittedCount: number;
  unsupportedCount: number;
}) {
  return (
    <section className="living-hq-changes" aria-labelledby="living-hq-changes-title">
      <header>
        <div>
          <span className="eyebrow">{M.livingHq.changesEyebrow}</span>
          <h2 id="living-hq-changes-title">{M.livingHq.changesTitle}</h2>
        </div>
        <span className="living-hq-change-count">{changes.length}</span>
      </header>
      <p className="living-hq-section-note">{M.livingHq.changesBoundary}</p>

      {changes.length > 0 ? (
        <ol className="living-hq-change-list">
          {changes.map((change) => (
            <li key={change.id}>
              <Link href={change.href}>
                <span className="living-hq-change-icon" data-kind={change.kind}>
                  {changeIcon(change.kind)}
                </span>
                <span>
                  <strong>{change.title}</strong>
                  <small>{change.description}</small>
                </span>
                <time dateTime={change.occurredAt ?? undefined}>
                  {formatChangeTime(change.occurredAt)}
                </time>
              </Link>
            </li>
          ))}
        </ol>
      ) : (
        <div className="living-hq-empty-change">
          <strong>
            {isPartial ? M.livingHq.changesUnavailable : M.livingHq.noChanges}
          </strong>
          <span>
            {isPartial
              ? M.livingHq.changesUnavailableHint
              : M.livingHq.noChangesHint}
          </span>
        </div>
      )}

      {omittedCount > 0 || unsupportedCount > 0 ? (
        <p className="living-hq-feed-note">
          {omittedCount > 0 ? `${M.livingHq.moreSignals}: ${omittedCount}. ` : ""}
          {unsupportedCount > 0
            ? `${M.livingHq.withoutEvidence}: ${unsupportedCount}.`
            : ""}
        </p>
      ) : null}
    </section>
  );
}

function WorldPulse({
  availability,
  metrics
}: {
  availability: "partial" | "ready" | "unavailable";
  metrics: readonly LivingHqWorldMetric[];
}) {
  return (
    <aside className="living-hq-pulse" aria-labelledby="living-hq-pulse-title">
      <header>
        <span className="eyebrow">{M.livingHq.pulseEyebrow}</span>
        <h2 id="living-hq-pulse-title">{M.livingHq.pulseTitle}</h2>
      </header>
      {availability === "unavailable" ? (
        <p className="living-hq-pulse-empty">{M.livingHq.pulseUnavailable}</p>
      ) : (
        <dl>
          {metrics.map((metric) => (
            <div key={metric.key}>
              <dt>{metric.label}</dt>
              <dd>{formatMetricValue(metric)}</dd>
            </div>
          ))}
        </dl>
      )}
      <Link className="living-hq-secondary-action" href="/company-brain">
        {M.livingHq.openWorld}
        <span aria-hidden="true">→</span>
      </Link>
    </aside>
  );
}

function unknownRadarSummary(): RadarSummary {
  return { connectedCount: null, state: "unknown" };
}

function formatRadarSummary(summary: RadarSummary): string {
  if (summary.state === "attention") return M.livingHq.radarAttention;
  if (summary.state === "empty") return M.livingHq.radarEmpty;
  if (summary.state === "connected" && summary.connectedCount !== null) {
    return M.livingHq.radarConnected(summary.connectedCount);
  }
  return M.livingHq.radarUnknown;
}

function missionEvidenceBadge(mission: LivingHqMission): string {
  if (mission.evidence.length > 0) {
    return mission.evidenceState === "referenced"
      ? M.livingHq.referencesBadge
      : String(mission.evidence.length);
  }
  if (mission.evidenceState === "unavailable") {
    return M.livingHq.noReferencesBadge;
  }
  return M.livingHq.summaryBadge;
}

function formatMetricValue(metric: LivingHqWorldMetric): string {
  if (metric.value === null) {
    return "—";
  }
  return metric.precision === "at_least" ? `≥${metric.value}` : String(metric.value);
}

function formatChangeTime(value: string | null): string {
  if (!value) {
    return M.livingHq.timeUnknown;
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return M.livingHq.timeUnknown;
  }
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "short"
  }).format(parsed);
}

function changeIcon(kind: LivingHqChange["kind"]): string {
  if (kind === "proposal") return "!";
  if (kind === "touchpoint") return "↔";
  if (kind === "organization_candidate") return "□";
  return "+";
}

function evidenceWord(count: number): string {
  const mod10 = count % 10;
  const mod100 = count % 100;
  if (mod10 === 1 && mod100 !== 11) return "доказательство";
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) {
    return "доказательства";
  }
  return "доказательств";
}
