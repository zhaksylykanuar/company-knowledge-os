"use client";

import { useEffect, useState } from "react";

import { generateManualFounderBriefing } from "../lib/api";
import { useWorkspaceId } from "../lib/session";
import type {
  BriefingEvidenceRef,
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
  onGenerate?: () => void;
  onRetry?: () => void;
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
  const [selectedEvidence, setSelectedEvidence] = useState<BriefingEvidenceRef | null>(null);
  const [selectedEvidenceItemTitle, setSelectedEvidenceItemTitle] = useState<string | null>(null);
  const [status, setStatus] = useState<BriefingStatus>("loading");

  useEffect(() => {
    setStatus(workspaceId ? "empty" : "missing");
  }, [workspaceId]);

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
      setStatus(payload.briefing.items.length > 0 ? "success" : "empty");
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "Request failed");
      setStatus("error");
    }
  }

  return (
    <BriefingPanelView
      data={data}
      error={error}
      onCloseEvidence={() => {
        setSelectedEvidence(null);
        setSelectedEvidenceItemTitle(null);
      }}
      onGenerate={generateBriefing}
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
  data,
  error,
  onCloseEvidence,
  onGenerate,
  onRetry,
  onSelectEvidence,
  selectedEvidence,
  selectedEvidenceItemTitle = null,
  status
}: BriefingPanelViewProps) {
  const briefing = data?.briefing ?? null;
  const isGenerating = status === "loading";

  return (
    <section className="panel briefing-panel" aria-labelledby="briefing-title">
      <div className="section-header">
        <div>
          <span className="eyebrow">Briefing</span>
          <h2 id="briefing-title">Manual Founder Briefing</h2>
        </div>
        <button
          className="button"
          disabled={isGenerating || status === "missing" || status === "unsupported"}
          onClick={onGenerate}
          type="button"
        >
          {isGenerating ? "Generating briefing" : briefing ? "Refresh briefing" : "Generate briefing"}
        </button>
      </div>

      {status === "loading" ? <LoadingState label="Generating deterministic briefing" /> : null}

      {status === "missing" ? (
        <EmptyState
          description="Your account has no workspace yet, so there is nothing to brief on."
          title="No workspace available"
        />
      ) : null}

      {status === "unsupported" ? (
        <EmptyState
          description="The backend did not report a supported manual deterministic briefing capability."
          title="Manual briefing unsupported"
        />
      ) : null}

      {status === "error" ? (
        <>
          <ErrorState
            description={error ?? "The manual briefing request failed."}
            title="Briefing unavailable"
          />
          <button className="button secondary" onClick={onRetry} type="button">
            Retry
          </button>
        </>
      ) : null}

      {status === "empty" && !briefing ? (
        <EmptyState
          description="Use the generate button to request the deterministic manual briefing from existing workspace records."
          title="No briefing loaded"
        />
      ) : null}

      {briefing && status !== "error" && status !== "missing" ? (
        <>
          <p className="muted">
            Manual deterministic briefing from evidence-backed company records.
            AI generation, live provider sync, and action execution are not used.
          </p>
          <section className="grid" aria-label="Briefing summary">
            <StatusCard
              description="GitHub repositories in the deterministic briefing signals."
              title="Repositories"
              value={String(briefing.signals.github.repository_count)}
            />
            <StatusCard
              description="Queued local GitHub sync jobs."
              title="Queued sync jobs"
              value={String(briefing.signals.github.queued_sync_jobs)}
            />
            <StatusCard
              description="Latest local GitHub sync job status."
              title="Latest sync"
              value={briefing.signals.github.latest_sync_job_status ?? "None"}
            />
            <StatusCard
              description="Briefing mode."
              title="AI / persistence"
              value={briefing.llm_used ? "AI" : briefing.persistence}
            />
          </section>
          <section className="callout" aria-label="Briefing capability boundary">
            <strong>Current capability mode</strong>
            <p>
              Manual deterministic briefing. AI briefing: {briefing.llm_used ? "enabled" : "not enabled"}.
              Live provider sync: {briefing.is_live ? "enabled" : "not enabled"}.
              External actions: not executed here.
            </p>
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
            <ul className="meta-list" aria-label="Briefing warnings">
              {briefing.warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          ) : null}
        </>
      ) : null}
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
    <section className="work-section" aria-label="Briefing items">
      <h3>Briefing items</h3>
      {items.length === 0 ? (
        <p className="muted">No briefing items returned by the backend.</p>
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
                <dt>Severity</dt>
                <dd>{item.severity}</dd>
              </div>
              <div>
                <dt>Confidence</dt>
                <dd>{Math.round(item.confidence * 100)}%</dd>
              </div>
              <div>
                <dt>Recommended next step</dt>
                <dd>{item.recommended_next_step ?? "No next step returned"}</dd>
              </div>
            </dl>
            <EvidenceButtons
              evidenceRefs={item.evidence_refs}
              itemTitle={item.title}
              onSelectEvidence={onSelectEvidence}
            />
            {item.related_entities.length > 0 ? (
              <p className="muted">Related: {item.related_entities.join(", ")}</p>
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
    return (
      <p className="muted">
        Deterministic system fact; no separate evidence ref returned.
      </p>
    );
  }
  return (
    <div className="actions-row" aria-label={`Evidence for ${itemTitle}`}>
      {evidenceRefs.map((evidence) => (
        <button
          className="button secondary"
          key={`${evidence.kind}-${evidence.ref}`}
          onClick={() => onSelectEvidence?.(evidence, itemTitle)}
          type="button"
        >
          Evidence: {evidence.ref}
        </button>
      ))}
    </div>
  );
}
