"use client";

import { useCallback, useEffect, useState } from "react";

import {
  createActionProposal,
  fetchActionProposals,
  generateManualFounderBriefing,
  getBriefing,
  listBriefings
} from "../lib/api";
import { M, T } from "../lib/messages";
import { useWorkspaceId } from "../lib/session";
import type {
  ActionProposal,
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
type BriefingCategoryFilter = "all" | string;
type BriefingEvidenceSelection = {
  evidence: BriefingEvidenceRef;
  title: string;
  count: number;
};
type BriefingHistoryReference = {
  id: string;
  itemCount: number;
  evidenceRefs: number;
};
type BriefingActionSummary = {
  approved: number;
  executed: number;
  failed: number;
  proposed: number;
  rejected: number;
  total: number;
};

const ACTIONS_BRIEFING_FOCUS_HREF = "/actions?origin=briefing&status=proposed";

type BriefingPanelViewProps = {
  actionError?: string | null;
  actionLoadError?: string | null;
  actionProposals?: ActionProposal[];
  actionSuccessMessage?: string | null;
  data: FounderBriefingResponse | null;
  error: string | null;
  history?: BriefingSummary[];
  activeBriefingId?: string | null;
  pendingActionItemId?: string | null;
  onGenerate?: () => void;
  onRetry?: () => void;
  onCategoryFilterChange?: (filter: BriefingCategoryFilter) => void;
  onOpenBriefing?: (briefingId: string) => void;
  onCloseEvidence?: () => void;
  onCreateActionFromItem?: (item: FounderBriefingItem) => void;
  onSelectEvidence?: (
    evidence: BriefingEvidenceRef,
    itemTitle: string,
    count?: number
  ) => void;
  categoryFilter?: BriefingCategoryFilter;
  selectedEvidence: BriefingEvidenceRef | null;
  selectedEvidenceItemTitle?: string | null;
  selectedEvidenceCount?: number | null;
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
  const [selectedEvidenceCount, setSelectedEvidenceCount] = useState<number | null>(null);
  const [status, setStatus] = useState<BriefingStatus>("loading");
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionLoadError, setActionLoadError] = useState<string | null>(null);
  const [actionProposals, setActionProposals] = useState<ActionProposal[]>([]);
  const [actionSuccessMessage, setActionSuccessMessage] = useState<string | null>(null);
  const [pendingActionItemId, setPendingActionItemId] = useState<string | null>(null);
  const [categoryFilter, setCategoryFilter] = useState<BriefingCategoryFilter>("all");

  const refreshHistory = useCallback(async (currentWorkspaceId: string) => {
    try {
      const payload = await listBriefings(currentWorkspaceId, { limit: 20 });
      setHistory(payload.briefings);
    } catch {
      // History is supplementary; keep the generate flow usable if it fails.
      setHistory([]);
    }
  }, []);

  const refreshActionProposals = useCallback(async (currentWorkspaceId: string) => {
    try {
      const payload = await fetchActionProposals(currentWorkspaceId, { limit: 100 });
      setActionProposals(payload.proposals);
      setActionLoadError(null);
    } catch (caught: unknown) {
      setActionProposals([]);
      setActionLoadError(caught instanceof Error ? caught.message : M.common.requestFailed);
    }
  }, []);

  useEffect(() => {
    if (!workspaceId) {
      setStatus("missing");
      setHistory([]);
      setActionProposals([]);
      setActionLoadError(null);
      return;
    }
    setStatus("empty");
    void refreshHistory(workspaceId);
    void refreshActionProposals(workspaceId);
  }, [workspaceId, refreshActionProposals, refreshHistory]);

  async function generateBriefing() {
    if (!workspaceId) {
      setStatus("missing");
      return;
    }

    setError(null);
    setActionError(null);
    setActionSuccessMessage(null);
    setSelectedEvidence(null);
    setSelectedEvidenceItemTitle(null);
    setSelectedEvidenceCount(null);
    setCategoryFilter("all");
    setStatus("loading");
    try {
      const payload = await generateManualFounderBriefing(workspaceId);
      setData(payload);
      setActiveBriefingId(payload.briefing.id);
      setStatus(payload.briefing.items.length > 0 ? "success" : "empty");
      // The new briefing is now saved — refresh history so it appears.
      void refreshHistory(workspaceId);
      void refreshActionProposals(workspaceId);
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
    setActionError(null);
    setActionSuccessMessage(null);
    setSelectedEvidence(null);
    setSelectedEvidenceItemTitle(null);
    setSelectedEvidenceCount(null);
    setCategoryFilter("all");
    setStatus("loading");
    try {
      const payload = await getBriefing(workspaceId, briefingId);
      setData(payload);
      setActiveBriefingId(payload.briefing.id);
      setStatus(payload.briefing.items.length > 0 ? "success" : "empty");
      void refreshActionProposals(workspaceId);
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : M.common.requestFailed);
      setStatus("error");
    }
  }

  async function createLocalActionFromItem(item: FounderBriefingItem) {
    if (!workspaceId) {
      setStatus("missing");
      return;
    }

    setActionError(null);
    setActionSuccessMessage(null);
    setPendingActionItemId(item.id);
    try {
      const payload = await createActionProposal(workspaceId, {
        action_type: "internal_todo",
        created_by: "user",
        description: [item.title, item.summary].filter(Boolean).join("\n\n"),
        evidence_refs: item.evidence_refs,
        payload: {
          briefing_id: activeBriefingId,
          briefing_item_key: item.id,
          category: item.category,
          recommended_next_step: item.recommended_next_step,
          related_entities: item.related_entities,
          severity: item.severity,
          source: "briefing_item"
        },
        target_provider: "internal",
        title: item.recommended_next_step ?? item.title
      });
      setActionProposals((current) => [
        payload.proposal,
        ...current.filter((proposal) => proposal.id !== payload.proposal.id)
      ]);
      setActionSuccessMessage(M.briefingPanel.actionCreateSuccess);
    } catch (caught: unknown) {
      setActionError(caught instanceof Error ? caught.message : M.common.requestFailed);
    } finally {
      setPendingActionItemId(null);
    }
  }

  return (
    <BriefingPanelView
      actionError={actionError}
      actionLoadError={actionLoadError}
      actionProposals={actionProposals}
      actionSuccessMessage={actionSuccessMessage}
      activeBriefingId={activeBriefingId}
      data={data}
      error={error}
      history={history}
      onCloseEvidence={() => {
        setSelectedEvidence(null);
        setSelectedEvidenceItemTitle(null);
        setSelectedEvidenceCount(null);
      }}
      onCategoryFilterChange={setCategoryFilter}
      onCreateActionFromItem={createLocalActionFromItem}
      onGenerate={generateBriefing}
      onOpenBriefing={openBriefing}
      onRetry={generateBriefing}
      onSelectEvidence={(evidence, itemTitle, count) => {
        setSelectedEvidence(evidence);
        setSelectedEvidenceItemTitle(itemTitle);
        setSelectedEvidenceCount(typeof count === "number" ? count : null);
      }}
      categoryFilter={categoryFilter}
      pendingActionItemId={pendingActionItemId}
      selectedEvidence={selectedEvidence}
      selectedEvidenceItemTitle={selectedEvidenceItemTitle}
      selectedEvidenceCount={selectedEvidenceCount}
      status={status}
    />
  );
}

export function BriefingPanelView({
  actionError = null,
  actionLoadError = null,
  actionProposals = [],
  actionSuccessMessage = null,
  activeBriefingId = null,
  categoryFilter = "all",
  data,
  error,
  history = [],
  onCategoryFilterChange,
  onCloseEvidence,
  onCreateActionFromItem,
  onGenerate,
  onOpenBriefing,
  onRetry,
  onSelectEvidence,
  pendingActionItemId = null,
  selectedEvidence,
  selectedEvidenceItemTitle = null,
  selectedEvidenceCount = null,
  status
}: BriefingPanelViewProps) {
  const briefing = data?.briefing ?? null;
  const coverage = briefing?.signals.coverage ?? null;
  const items = briefing?.items ?? [];
  const filteredItems = filterBriefingItemsByCategory(items, categoryFilter);
  const actionSummaries = summarizeBriefingActions(actionProposals, items);
  const totalLinkedActions = Array.from(actionSummaries.values()).reduce(
    (total, summary) => total + summary.total,
    0
  );
  const defaultEvidenceSelection = firstBriefingEvidenceSelection(filteredItems);
  const drawerEvidence = selectedEvidence ?? defaultEvidenceSelection?.evidence ?? null;
  const drawerTitle = selectedEvidence
    ? selectedEvidenceItemTitle
    : defaultEvidenceSelection?.title ?? null;
  const drawerCount = selectedEvidence
    ? selectedEvidenceCount
    : defaultEvidenceSelection?.count ?? null;
  const drawerSelectionMode: "default" | "manual" | null = drawerEvidence
    ? selectedEvidence
      ? "manual"
      : "default"
    : null;
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
              value={String(
                coverage?.canonical_repositories ?? briefing.signals.github.repository_count
              )}
            />
            <StatusCard
              description={M.briefingPanel.workDescription}
              title={M.briefingPanel.workTitle}
              value={T.briefingCoverageWork(
                coverage?.open_issues ?? 0,
                coverage?.open_pull_requests ?? 0
              )}
            />
            <StatusCard
              description={M.briefingPanel.evidenceDescription}
              title={M.briefingPanel.evidenceTitle}
              value={String(coverage?.evidence_refs ?? 0)}
            />
            <StatusCard
              description={M.briefingPanel.modeDescription}
              title={M.briefingPanel.modeTitle}
              value={coverage?.is_live ? M.briefingPanel.modeLive : M.briefingPanel.modeLocal}
            />
          </section>
          <section className="callout" aria-label={M.briefingPanel.capabilityTitle}>
            <strong>{M.briefingPanel.capabilityTitle}</strong>
            <p>{T.briefingCapability(briefing.llm_used, briefing.is_live)}</p>
          </section>
          {actionSuccessMessage ? (
            <p className="success-text">{actionSuccessMessage}</p>
          ) : null}
          {actionError ? <p className="error-text">{actionError}</p> : null}
          <BriefingActionSummaryPanel
            actionLoadError={actionLoadError}
            summaries={actionSummaries}
            totalLinkedActions={totalLinkedActions}
          />
          <BriefingCategoryFilterControl
            activeFilter={categoryFilter}
            items={items}
            onChange={onCategoryFilterChange}
          />
          <section className="work-columns">
            <BriefingItemSection
              items={filteredItems}
              actionSummaries={actionSummaries}
              onCreateActionFromItem={onCreateActionFromItem}
              onSelectEvidence={onSelectEvidence}
              pendingActionItemId={pendingActionItemId}
              totalItems={items.length}
            />
            <EvidenceDrawer
              evidence={drawerEvidence}
              evidenceCount={drawerCount}
              itemTitle={drawerTitle}
              onClose={selectedEvidence ? onCloseEvidence : undefined}
              selectionDescription={
                drawerSelectionMode === "manual"
                  ? M.briefingPanel.evidenceManualContext
                  : drawerSelectionMode === "default"
                    ? M.briefingPanel.evidenceDefaultContext
                    : null
              }
              selectionMode={drawerSelectionMode}
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
          reference={briefing ? briefingHistoryReferenceFromBriefing(briefing) : null}
        />
      ) : null}
    </section>
  );
}

function BriefingActionSummaryPanel({
  actionLoadError,
  summaries,
  totalLinkedActions
}: {
  actionLoadError: string | null;
  summaries: Map<string, BriefingActionSummary>;
  totalLinkedActions: number;
}) {
  const totals = Array.from(summaries.values()).reduce(
    (accumulator, summary) => ({
      approved: accumulator.approved + summary.approved,
      executed: accumulator.executed + summary.executed,
      failed: accumulator.failed + summary.failed,
      proposed: accumulator.proposed + summary.proposed,
      rejected: accumulator.rejected + summary.rejected,
      total: accumulator.total + summary.total
    }),
    {
      approved: 0,
      executed: 0,
      failed: 0,
      proposed: 0,
      rejected: 0,
      total: 0
    }
  );

  return (
    <section className="callout" aria-label={M.briefingPanel.actionSummaryTitle}>
      <strong>{M.briefingPanel.actionSummaryTitle}</strong>
      <p>
        {totalLinkedActions > 0
          ? T.briefingActionSummary(
              totals.total,
              totals.proposed,
              totals.approved,
              totals.rejected,
              totals.executed,
              totals.failed
            )
          : M.briefingPanel.actionSummaryEmpty}
      </p>
      <p className="muted">{M.briefingPanel.actionSummaryDescription}</p>
      {actionLoadError ? <p className="error-text">{actionLoadError}</p> : null}
      <p>
        <a className="button secondary" href={ACTIONS_BRIEFING_FOCUS_HREF}>
          {M.briefingPanel.openActions}
        </a>
      </p>
    </section>
  );
}

function BriefingHistorySection({
  activeBriefingId,
  history,
  onOpenBriefing,
  reference
}: {
  activeBriefingId: string | null;
  history: BriefingSummary[];
  onOpenBriefing?: (briefingId: string) => void;
  reference?: BriefingHistoryReference | null;
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
              <dl className="work-meta">
                <div>
                  <dt>{M.briefingHistory.coverageLabel}</dt>
                  <dd>
                    {T.briefingHistoryCoverage(
                      entry.signals.coverage.canonical_repositories,
                      entry.signals.coverage.open_issues,
                      entry.signals.coverage.open_pull_requests,
                      entry.signals.coverage.evidence_refs,
                      entry.signals.coverage.is_live
                        ? M.briefingPanel.modeLive
                        : M.briefingPanel.modeLocal
                    )}
                  </dd>
                </div>
                <div>
                  <dt>{M.briefingHistory.deltaLabel}</dt>
                  <dd>{briefingHistoryDeltaText(entry, reference)}</dd>
                </div>
              </dl>
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

function BriefingCategoryFilterControl({
  activeFilter,
  items,
  onChange
}: {
  activeFilter: BriefingCategoryFilter;
  items: FounderBriefingItem[];
  onChange?: (filter: BriefingCategoryFilter) => void;
}) {
  const filters = briefingCategoryFilters(items);
  if (items.length === 0) {
    return null;
  }
  return (
    <section className="work-section" aria-label={M.briefingPanel.itemFilterLabel}>
      <h3>{M.briefingPanel.itemFilterTitle}</h3>
      <p className="muted">{M.briefingPanel.itemFilterDescription}</p>
      <div className="segmented" role="tablist" aria-label={M.briefingPanel.itemFilterLabel}>
        {filters.map((filter) => (
          <button
            aria-selected={activeFilter === filter}
            className={`segment${activeFilter === filter ? " active" : ""}`}
            key={filter}
            onClick={() => onChange?.(filter)}
            role="tab"
            type="button"
          >
            {briefingCategoryFilterLabel(filter)} · {briefingCategoryFilterCount(items, filter)}
          </button>
        ))}
      </div>
    </section>
  );
}

function briefingHistoryReferenceFromBriefing(
  briefing: FounderBriefingResponse["briefing"]
): BriefingHistoryReference {
  return {
    evidenceRefs: briefing.signals.coverage.evidence_refs,
    id: briefing.id,
    itemCount: briefing.items.length
  };
}

function briefingHistoryDeltaText(
  entry: BriefingSummary,
  reference?: BriefingHistoryReference | null
): string {
  if (!reference) {
    return M.briefingHistory.noDelta;
  }
  return T.briefingHistoryDelta(
    entry.item_count - reference.itemCount,
    entry.signals.coverage.evidence_refs - reference.evidenceRefs
  );
}

function BriefingItemSection({
  actionSummaries,
  items,
  onCreateActionFromItem,
  onSelectEvidence,
  pendingActionItemId,
  totalItems
}: {
  actionSummaries: Map<string, BriefingActionSummary>;
  items: FounderBriefingItem[];
  onCreateActionFromItem?: (item: FounderBriefingItem) => void;
  onSelectEvidence?: (
    evidence: BriefingEvidenceRef,
    itemTitle: string,
    count?: number
  ) => void;
  pendingActionItemId?: string | null;
  totalItems: number;
}) {
  return (
    <section className="work-section" aria-label={M.briefingPanel.itemsSectionTitle}>
      <h3>{M.briefingPanel.itemsSectionTitle}</h3>
      {items.length === 0 && totalItems === 0 ? (
        <p className="muted">{M.briefingPanel.noItems}</p>
      ) : null}
      {items.length === 0 && totalItems > 0 ? (
        <p className="muted">{M.briefingPanel.noItemsForFilter}</p>
      ) : null}
      <div className="work-list">
        {items.map((item) => {
          const actionSummary = actionSummaries.get(item.id) ?? null;
          const actionAlreadyOpen = hasOpenBriefingAction(actionSummary);
          return (
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
              {actionSummary ? (
                <p className="muted">
                  {T.briefingItemActionSummary(
                    actionSummary.total,
                    actionSummary.proposed,
                    actionSummary.approved,
                    actionSummary.rejected,
                    actionSummary.executed,
                    actionSummary.failed
                  )}
                </p>
              ) : null}
              <EvidenceButtons
                evidenceRefs={item.evidence_refs}
                itemTitle={item.title}
                onSelectEvidence={onSelectEvidence}
              />
              <div className="actions-row">
                <button
                  className="button secondary"
                  disabled={
                    !onCreateActionFromItem ||
                    pendingActionItemId === item.id ||
                    actionAlreadyOpen
                  }
                  onClick={() => onCreateActionFromItem?.(item)}
                  type="button"
                >
                  {pendingActionItemId === item.id
                    ? M.briefingPanel.actionCreating
                    : actionAlreadyOpen
                      ? M.briefingPanel.actionAlreadyCreated
                      : M.briefingPanel.actionCreate}
                </button>
                {actionSummary ? (
                  <a className="button secondary" href={ACTIONS_BRIEFING_FOCUS_HREF}>
                    {M.briefingPanel.openActions}
                  </a>
                ) : null}
              </div>
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
          );
        })}
      </div>
    </section>
  );
}

function summarizeBriefingActions(
  proposals: ActionProposal[],
  items: FounderBriefingItem[]
): Map<string, BriefingActionSummary> {
  const itemIds = new Set(items.map((item) => item.id));
  const summaries = new Map<string, BriefingActionSummary>();
  for (const proposal of proposals) {
    const itemId = briefingItemKeyFromProposal(proposal);
    if (!itemId || !itemIds.has(itemId)) {
      continue;
    }
    const summary = summaries.get(itemId) ?? {
      approved: 0,
      executed: 0,
      failed: 0,
      proposed: 0,
      rejected: 0,
      total: 0
    };
    summary.total += 1;
    switch (proposal.status) {
      case "approved":
        summary.approved += 1;
        break;
      case "executed":
        summary.executed += 1;
        break;
      case "failed":
        summary.failed += 1;
        break;
      case "rejected":
        summary.rejected += 1;
        break;
      case "proposed":
      default:
        summary.proposed += 1;
        break;
    }
    summaries.set(itemId, summary);
  }
  return summaries;
}

function briefingItemKeyFromProposal(proposal: ActionProposal): string | null {
  const payloadKey = proposal.payload.briefing_item_key;
  if (typeof payloadKey === "string" && payloadKey.trim().length > 0) {
    return payloadKey;
  }
  return proposal.briefing_item_id;
}

function hasOpenBriefingAction(summary: BriefingActionSummary | null): boolean {
  if (!summary) {
    return false;
  }
  return summary.proposed + summary.approved + summary.executed > 0;
}

function EvidenceButtons({
  evidenceRefs,
  itemTitle,
  onSelectEvidence
}: {
  evidenceRefs: BriefingEvidenceRef[];
  itemTitle: string;
  onSelectEvidence?: (
    evidence: BriefingEvidenceRef,
    itemTitle: string,
    count?: number
  ) => void;
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
          onClick={() => onSelectEvidence?.(evidence, itemTitle, evidenceRefs.length)}
          type="button"
        >
          {T.evidenceButton(evidence.ref)}
        </button>
      ))}
    </div>
  );
}

function briefingCategoryFilters(items: FounderBriefingItem[]): BriefingCategoryFilter[] {
  const categories = Array.from(
    new Set(
      items
        .map((item) => item.category.trim())
        .filter((category) => category.length > 0)
    )
  );
  return ["all", ...categories];
}

function briefingCategoryFilterLabel(filter: BriefingCategoryFilter): string {
  return filter === "all" ? M.briefingPanel.itemFilterAll : filter;
}

function briefingCategoryFilterCount(
  items: FounderBriefingItem[],
  filter: BriefingCategoryFilter
): number {
  return filter === "all"
    ? items.length
    : items.filter((item) => item.category === filter).length;
}

function filterBriefingItemsByCategory(
  items: FounderBriefingItem[],
  filter: BriefingCategoryFilter
): FounderBriefingItem[] {
  if (filter === "all") {
    return items;
  }
  return items.filter((item) => item.category === filter);
}

function firstBriefingEvidenceSelection(
  items: FounderBriefingItem[]
): BriefingEvidenceSelection | null {
  for (const item of items) {
    const evidence = item.evidence_refs[0];
    if (evidence) {
      return {
        count: item.evidence_refs.length,
        evidence,
        title: item.title
      };
    }
  }
  return null;
}
