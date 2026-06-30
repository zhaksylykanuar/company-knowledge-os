"use client";

import { useCallback, useEffect, useState } from "react";

import { generateManualFounderBriefing, getBriefing, listBriefings } from "../lib/api";
import { M, T } from "../lib/messages";
import { useWorkspaceId } from "../lib/session";
import type {
  BriefingEvidenceRef,
  BriefingSummary,
  FounderBriefingItem,
  FounderBriefingResponse
} from "../lib/types";
import { EmptyState } from "./EmptyState";
import { ErrorState } from "./ErrorState";
import { EvidenceDrawer } from "./EvidenceDrawer";
import { LoadingState } from "./LoadingState";
import { StatusCard } from "./StatusCard";

type BriefingStatus =
  | "empty"
  | "error"
  | "loading"
  | "missing"
  | "ready"
  | "success"
  | "unsupported";

type BriefingPanelViewProps = {
  data: FounderBriefingResponse | null;
  error: string | null;
  history?: BriefingSummary[];
  activeBriefingId?: string | null;
  onGenerate?: () => void;
  onRetry?: () => void;
  onOpenBriefing?: (briefingId: string) => void;
  onCloseEvidence?: () => void;
  onSelectEvidence?: (evidence: BriefingEvidenceRef, itemTitle: string) => void;
  selectedEvidence: BriefingEvidenceRef | null;
  selectedEvidenceItemTitle?: string | null;
  status: BriefingStatus;
};

export function BriefingPanel() {
  const workspaceId = useWorkspaceId();
  const [data, setData] = useState<FounderBriefingResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<BriefingSummary[]>([]);
  const [activeBriefingId, setActiveBriefingId] = useState<string | null>(null);
  const [selectedEvidence, setSelectedEvidence] = useState<BriefingEvidenceRef | null>(null);
  const [selectedEvidenceItemTitle, setSelectedEvidenceItemTitle] = useState<string | null>(null);
  const [status, setStatus] = useState<BriefingStatus>("loading");

  const refreshHistory = useCallback(async (currentWorkspaceId: string) => {
    try {
      const payload = await listBriefings(currentWorkspaceId, { limit: 20 });
      setHistory(payload.briefings);
    } catch {
      // History is supplementary; keep the generate flow usable if it fails.
      setHistory([]);
    }
  }, []);

  useEffect(() => {
    if (!workspaceId) {
      setStatus("missing");
      setHistory([]);
      return;
    }
    setStatus("empty");
    void refreshHistory(workspaceId);
  }, [workspaceId, refreshHistory]);

  async function generateBriefing() {
    if (!workspaceId) {
      setStatus("missing");
      return;
    }

    setError(null);
    setSelectedEvidence(null);
    setSelectedEvidenceItemTitle(null);
    setStatus("loading");
    try {
      const payload = await generateManualFounderBriefing(workspaceId);
      setData(payload);
      setActiveBriefingId(payload.briefing.id);
      setStatus(payload.briefing.items.length > 0 ? "success" : "empty");
      // The new briefing is now saved — refresh history so it appears.
      void refreshHistory(workspaceId);
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : M.common.requestFailed);
      setStatus("error");
    }
  }

  async function openBriefing(briefingId: string) {
    if (!workspaceId) {
      setStatus("missing");
      return;
    }

    setError(null);
    setSelectedEvidence(null);
    setSelectedEvidenceItemTitle(null);
    setStatus("loading");
    try {
      const payload = await getBriefing(workspaceId, briefingId);
      setData(payload);
      setActiveBriefingId(payload.briefing.id);
      setStatus(payload.briefing.items.length > 0 ? "success" : "empty");
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : M.common.requestFailed);
      setStatus("error");
    }
  }

  return (
    <BriefingPanelView
      activeBriefingId={activeBriefingId}
      data={data}
      error={error}
      history={history}
      onCloseEvidence={() => {
        setSelectedEvidence(null);
        setSelectedEvidenceItemTitle(null);
      }}
      onGenerate={generateBriefing}
      onOpenBriefing={openBriefing}
      onRetry={generateBriefing}
      onSelectEvidence={(evidence, itemTitle) => {
        setSelectedEvidence(evidence);
        setSelectedEvidenceItemTitle(itemTitle);
      }}
      selectedEvidence={selectedEvidence}
      selectedEvidenceItemTitle={selectedEvidenceItemTitle}
      status={status}
    />
  );
}

export function BriefingPanelView({
  activeBriefingId = null,
  data,
  error,
  history = [],
  onCloseEvidence,
  onGenerate,
  onOpenBriefing,
  onRetry,
  onSelectEvidence,
  selectedEvidence,
  selectedEvidenceItemTitle = null,
  status
}: BriefingPanelViewProps) {
  const briefing = data?.briefing ?? null;
  const isGenerating = status === "loading";
  const showHistory = status !== "missing" && status !== "unsupported";

  return (
    <section className="panel briefing-panel" aria-labelledby="briefing-title">
      <div className="section-header">
        <div>
          <span className="eyebrow">{M.briefingPanel.eyebrow}</span>
          <h2 id="briefing-title">{M.briefingPanel.title}</h2>
        </div>
        <button
          className="button"
          disabled={isGenerating || status === "missing" || status === "unsupported"}
          onClick={onGenerate}
          type="button"
        >
          {isGenerating
            ? M.briefingPanel.generating
            : briefing
              ? M.briefingPanel.refresh
              : M.briefingPanel.generate}
        </button>
      </div>

      {status === "loading" ? <LoadingState label={M.briefingPanel.loadingDeterministic} /> : null}

      {status === "missing" ? (
        <EmptyState
          description={M.briefingPanel.noWorkspaceDescription}
          title={M.common.noWorkspaceTitle}
        />
      ) : null}

      {status === "unsupported" ? (
        <EmptyState
          description={M.briefingPanel.unsupportedDescription}
          title={M.briefingPanel.unsupportedTitle}
        />
      ) : null}

      {status === "error" ? (
        <>
          <ErrorState
            description={error ?? M.briefingPanel.unavailableDescription}
            title={M.briefingPanel.unavailableTitle}
          />
          <button className="button secondary" onClick={onRetry} type="button">
            {M.common.retry}
          </button>
        </>
      ) : null}

      {status === "empty" && !briefing ? (
        <EmptyState
          description={M.briefingPanel.noBriefingDescription}
          title={M.briefingPanel.noBriefingTitle}
        />
      ) : null}

      {briefing && status !== "error" && status !== "missing" ? (
        <>
          <p className="muted">{M.briefingPanel.intro}</p>
          <section className="grid" aria-label={M.briefingPanel.summaryLabel}>
            <StatusCard
              description={M.briefingPanel.reposDescription}
              title={M.briefingPanel.reposTitle}
              value={String(briefing.signals.github.repository_count)}
            />
            <StatusCard
              description={M.briefingPanel.queuedDescription}
              title={M.briefingPanel.queuedTitle}
              value={String(briefing.signals.github.queued_sync_jobs)}
            />
            <StatusCard
              description={M.briefingPanel.latestSyncDescription}
              title={M.briefingPanel.latestSyncTitle}
              value={briefing.signals.github.latest_sync_job_status ?? M.briefingPanel.latestSyncNone}
            />
            <StatusCard
              description={M.briefingPanel.aiDescription}
              title={M.briefingPanel.aiTitle}
              value={briefing.llm_used ? M.briefingPanel.aiValue : M.briefingPanel.storedValue}
            />
          </section>
          <section className="callout" aria-label={M.briefingPanel.capabilityTitle}>
            <strong>{M.briefingPanel.capabilityTitle}</strong>
            <p>{T.briefingCapability(briefing.llm_used, briefing.is_live)}</p>
          </section>
          <section className="work-columns">
            <BriefingItemSection
              items={briefing.items}
              onSelectEvidence={onSelectEvidence}
            />
            <EvidenceDrawer
              evidence={selectedEvidence}
              itemTitle={selectedEvidenceItemTitle}
              onClose={selectedEvidence ? onCloseEvidence : undefined}
            />
          </section>
          {briefing.warnings.length > 0 ? (
            <ul className="meta-list" aria-label={M.common.warnings}>
              {briefing.warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          ) : null}
        </>
      ) : null}

      {showHistory ? (
        <BriefingHistorySection
          activeBriefingId={activeBriefingId}
          history={history}
          onOpenBriefing={onOpenBriefing}
        />
      ) : null}
    </section>
  );
}

function BriefingHistorySection({
  activeBriefingId,
  history,
  onOpenBriefing
}: {
  activeBriefingId: string | null;
  history: BriefingSummary[];
  onOpenBriefing?: (briefingId: string) => void;
}) {
  return (
    <section className="work-section briefing-history" aria-label={M.briefingHistory.title}>
      <h3>{M.briefingHistory.title}</h3>
      <p className="muted">{M.briefingHistory.description}</p>
      {history.length === 0 ? (
        <p className="muted">{M.briefingHistory.empty}</p>
      ) : (
        <div className="work-list">
          {history.map((entry) => (
            <article className="work-item" key={entry.id}>
              <div className="work-item-main">
                <h4>{entry.title}</h4>
              </div>
              <p className="muted">
                {T.briefingHistoryMeta(entry.item_count, entry.created_at)}
              </p>
              <div className="actions-row">
                <button
                  className="button secondary"
                  disabled={!onOpenBriefing || entry.id === activeBriefingId}
                  onClick={() => onOpenBriefing?.(entry.id)}
                  type="button"
                >
                  {entry.id === activeBriefingId
                    ? M.briefingHistory.current
                    : M.briefingHistory.open}
                </button>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

function BriefingItemSection({
  items,
  onSelectEvidence
}: {
  items: FounderBriefingItem[];
  onSelectEvidence?: (evidence: BriefingEvidenceRef, itemTitle: string) => void;
}) {
  return (
    <section className="work-section" aria-label={M.briefingPanel.itemsSectionTitle}>
      <h3>{M.briefingPanel.itemsSectionTitle}</h3>
      {items.length === 0 ? (
        <p className="muted">{M.briefingPanel.noItems}</p>
      ) : null}
      <div className="work-list">
        {items.map((item) => (
          <article className="work-item" key={item.id}>
            <div className="work-item-main">
              <span className="badge">{item.category}</span>
              <h4>{item.title}</h4>
            </div>
            <p className="muted">{item.summary}</p>
            <dl className="work-meta">
              <div>
                <dt>{M.briefingPanel.metaSeverity}</dt>
                <dd>{item.severity}</dd>
              </div>
              <div>
                <dt>{M.briefingPanel.metaConfidence}</dt>
                <dd>{T.confidencePercent(item.confidence)}</dd>
              </div>
              <div>
                <dt>{M.briefingPanel.metaNextStep}</dt>
                <dd>{item.recommended_next_step ?? M.briefingPanel.noNextStep}</dd>
              </div>
            </dl>
            <EvidenceButtons
              evidenceRefs={item.evidence_refs}
              itemTitle={item.title}
              onSelectEvidence={onSelectEvidence}
            />
            {item.related_entities.length > 0 ? (
              <p className="muted">{T.related(item.related_entities.join(", "))}</p>
            ) : null}
            {item.warnings.length > 0 ? (
              <ul className="meta-list">
                {item.warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            ) : null}
          </article>
        ))}
      </div>
    </section>
  );
}

function EvidenceButtons({
  evidenceRefs,
  itemTitle,
  onSelectEvidence
}: {
  evidenceRefs: BriefingEvidenceRef[];
  itemTitle: string;
  onSelectEvidence?: (evidence: BriefingEvidenceRef, itemTitle: string) => void;
}) {
  if (evidenceRefs.length === 0) {
    return <p className="muted">{M.briefingPanel.noEvidenceRef}</p>;
  }
  return (
    <div className="actions-row" aria-label={T.evidenceFor(itemTitle)}>
      {evidenceRefs.map((evidence) => (
        <button
          className="button secondary"
          key={`${evidence.kind}-${evidence.ref}`}
          onClick={() => onSelectEvidence?.(evidence, itemTitle)}
          type="button"
        >
          {T.evidenceButton(evidence.ref)}
        </button>
      ))}
    </div>
  );
}
