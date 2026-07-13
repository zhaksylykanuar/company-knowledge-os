"use client";

import { useEffect, useState } from "react";

import { fetchActionProposals, fetchRepoAudit } from "../lib/api";
import { M, T } from "../lib/messages";
import { useWorkspaceId } from "../lib/session";
import type { ActionProposal, RepoAuditResponse } from "../lib/types";
import { EmptyState } from "./EmptyState";
import { ErrorState } from "./ErrorState";
import { LoadingState } from "./LoadingState";
import { StatusCard } from "./StatusCard";

type PanelStatus = "error" | "loading" | "missing" | "ready";

type RepositoryAuditOverviewPanelProps = {
  refreshSignal?: number;
};

type AuditActionCounts = {
  total: number;
  deterministic: number;
  imported: number;
  proposed: number;
};

type RepositoryAuditOverviewPanelViewProps = {
  audit: RepoAuditResponse | null;
  counts: AuditActionCounts;
  error: string | null;
  onRetry?: () => void;
  status: PanelStatus;
};

const AUDIT_HREF = "/audit";
const AUDIT_ACTIONS_HREF = "/actions?origin=audit&status=proposed";
const AUDIT_ACTIONS_DETERMINISTIC_HREF =
  "/actions?origin=audit&status=proposed&audit_source=deterministic";
const AUDIT_ACTIONS_IMPORTED_HREF =
  "/actions?origin=audit&status=proposed&audit_source=imported";

export function RepositoryAuditOverviewPanel({
  refreshSignal = 0
}: RepositoryAuditOverviewPanelProps) {
  const workspaceId = useWorkspaceId();
  const [audit, setAudit] = useState<RepoAuditResponse | null>(null);
  const [counts, setCounts] = useState<AuditActionCounts>(EMPTY_COUNTS);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [status, setStatus] = useState<PanelStatus>("loading");

  useEffect(() => {
    if (!workspaceId) {
      setAudit(null);
      setCounts(EMPTY_COUNTS);
      setError(null);
      setStatus("missing");
      return;
    }

    let cancelled = false;
    setStatus("loading");
    setError(null);

    // The deterministic repo audit is required; the action-proposal counts are
    // supplementary context and must never break the overview if they fail.
    fetchRepoAudit()
      .then(async (auditPayload) => {
        if (cancelled) {
          return;
        }
        setAudit(auditPayload);
        const auditCounts = await loadAuditActionCounts(workspaceId);
        if (cancelled) {
          return;
        }
        setCounts(auditCounts);
        setStatus("ready");
      })
      .catch((caught: unknown) => {
        if (cancelled) {
          return;
        }
        setAudit(null);
        setCounts(EMPTY_COUNTS);
        setError(caught instanceof Error ? caught.message : M.common.requestFailed);
        setStatus("error");
      });

    return () => {
      cancelled = true;
    };
  }, [workspaceId, refreshSignal, reloadKey]);

  return (
    <RepositoryAuditOverviewPanelView
      audit={audit}
      counts={counts}
      error={error}
      onRetry={() => setReloadKey((current) => current + 1)}
      status={status}
    />
  );
}

export function RepositoryAuditOverviewPanelView({
  audit,
  counts,
  error,
  onRetry,
  status
}: RepositoryAuditOverviewPanelViewProps) {
  return (
    <section
      className="panel repository-audit-overview"
      aria-labelledby="repository-audit-overview-title"
    >
      <div className="section-header">
        <div>
          <span className="eyebrow">{M.repoAuditOverview.eyebrow}</span>
          <h2 id="repository-audit-overview-title">{M.repoAuditOverview.title}</h2>
        </div>
        <span className="badge">{M.repoAuditOverview.badge}</span>
      </div>

      {status === "loading" ? (
        <LoadingState label={M.repoAuditOverview.loading} />
      ) : null}

      {status === "missing" ? (
        <EmptyState
          description={M.repoAuditOverview.noWorkspaceDescription}
          title={M.common.noWorkspaceTitle}
        />
      ) : null}

      {status === "error" ? (
        <>
          <ErrorState
            description={error ?? M.repoAuditOverview.unavailableDescription}
            title={M.repoAuditOverview.unavailableTitle}
          />
          <button className="button secondary" onClick={onRetry} type="button">
            {M.common.retry}
          </button>
        </>
      ) : null}

      {status === "ready" && audit ? (
        <>
          <p className="muted">{M.repoAuditOverview.intro}</p>

          <section className="grid" aria-label={M.repoAuditOverview.summaryLabel}>
            <StatusCard
              description={M.repoAuditOverview.reposDescription}
              title={M.repoAuditOverview.reposTitle}
              value={String(audit.repo_count)}
            />
            <StatusCard
              description={M.repoAuditOverview.riskDescription}
              title={M.repoAuditOverview.riskTitle}
              value={String(totalRiskFlags(audit.risk_summary))}
            />
            <StatusCard
              description={M.repoAuditOverview.snapshotDescription}
              title={M.repoAuditOverview.snapshotTitle}
              value={
                audit.source_snapshot.available
                  ? String(audit.source_snapshot.repo_count ?? audit.repo_count)
                  : M.common.unavailable
              }
            />
            <StatusCard
              description={M.repoAuditOverview.actionsDescription}
              title={M.repoAuditOverview.actionsTitle}
              value={String(counts.total)}
            />
          </section>

          <section
            className="grid"
            aria-label={M.repoAuditOverview.actionsBreakdownLabel}
          >
            <StatusCard
              description={M.repoAuditOverview.actionsDeterministicDescription}
              title={M.repoAuditOverview.actionsDeterministicTitle}
              value={String(counts.deterministic)}
            />
            <StatusCard
              description={M.repoAuditOverview.actionsImportedDescription}
              title={M.repoAuditOverview.actionsImportedTitle}
              value={String(counts.imported)}
            />
            <StatusCard
              description={M.repoAuditOverview.actionsProposedDescription}
              title={M.repoAuditOverview.actionsProposedTitle}
              value={String(counts.proposed)}
            />
          </section>

          <p className="muted">
            {T.repoAuditOverviewActions(
              counts.total,
              counts.deterministic,
              counts.imported,
              counts.proposed
            )}
          </p>
          {counts.total === 0 ? (
            <p className="muted">{M.repoAuditOverview.emptyActionsHint}</p>
          ) : null}

          <p className="muted">{M.repoAuditOverview.boundaryNote}</p>

          <div className="actions-row">
            <a className="button" href={AUDIT_HREF}>
              {M.repoAuditOverview.openAudit}
            </a>
            <a className="button secondary" href={AUDIT_ACTIONS_HREF}>
              {M.repoAuditOverview.openAuditActions}
            </a>
            {counts.deterministic > 0 ? (
              <a
                className="button secondary"
                href={AUDIT_ACTIONS_DETERMINISTIC_HREF}
              >
                {M.repoAuditOverview.openDeterministicActions}
              </a>
            ) : null}
            {counts.imported > 0 ? (
              <a className="button secondary" href={AUDIT_ACTIONS_IMPORTED_HREF}>
                {M.repoAuditOverview.openImportedActions}
              </a>
            ) : null}
          </div>
        </>
      ) : null}
    </section>
  );
}

const EMPTY_COUNTS: AuditActionCounts = {
  total: 0,
  deterministic: 0,
  imported: 0,
  proposed: 0
};

async function loadAuditActionCounts(
  workspaceId: string
): Promise<AuditActionCounts> {
  try {
    const payload = await fetchActionProposals(workspaceId, { limit: 100 });
    return countAuditActionProposals(payload.proposals);
  } catch {
    // Supplementary context only; keep the deterministic audit overview usable.
    return EMPTY_COUNTS;
  }
}

export function countAuditActionProposals(
  proposals: ActionProposal[]
): AuditActionCounts {
  const counts: AuditActionCounts = { ...EMPTY_COUNTS };
  for (const proposal of proposals) {
    const source = auditProposalSource(proposal);
    if (source === null) {
      continue;
    }
    counts.total += 1;
    if (source === "deterministic") {
      counts.deterministic += 1;
    } else {
      counts.imported += 1;
    }
    if (proposal.status === "proposed") {
      counts.proposed += 1;
    }
  }
  return counts;
}

function auditProposalSource(
  proposal: ActionProposal
): "deterministic" | "imported" | null {
  const source = proposal.payload["source"];
  if (source === "repo_audit") {
    return "deterministic";
  }
  if (source === "repo_audit_import") {
    return "imported";
  }
  return null;
}

function totalRiskFlags(riskSummary: Record<string, number>): number {
  return Object.values(riskSummary).reduce(
    (total, value) => total + (value || 0),
    0
  );
}
