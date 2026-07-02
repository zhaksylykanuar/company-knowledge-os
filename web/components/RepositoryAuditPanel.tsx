"use client";

import { useCallback, useEffect, useState } from "react";

import { createActionProposal, fetchActionProposals, fetchRepoAudit } from "../lib/api";
import { M, T } from "../lib/messages";
import { useWorkspaceId } from "../lib/session";
import type { ActionProposal, RepoAuditRepoFact, RepoAuditResponse } from "../lib/types";
import { EmptyState } from "./EmptyState";
import { ErrorState } from "./ErrorState";
import { LoadingState } from "./LoadingState";
import { StatusCard } from "./StatusCard";

type PanelStatus = "empty" | "error" | "loading" | "missing" | "ready";
type AuditFocusFilter = "all" | "needs_confirm" | "risks" | "stale";

const ACTIONS_AUDIT_FOCUS_HREF = "/actions?origin=audit&status=proposed";

type RepositoryAuditPanelViewProps = {
  actionError?: string | null;
  actionProposals?: ActionProposal[];
  actionSuccessMessage?: string | null;
  data: RepoAuditResponse | null;
  error: string | null;
  focus?: AuditFocusFilter;
  onCreateAction?: (repo: RepoAuditRepoFact) => void;
  onFocusChange?: (focus: AuditFocusFilter) => void;
  onRetry?: () => void;
  pendingRepo?: string | null;
  status: PanelStatus;
};

export function RepositoryAuditPanel() {
  const workspaceId = useWorkspaceId();
  const [data, setData] = useState<RepoAuditResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [status, setStatus] = useState<PanelStatus>("loading");
  const [focus, setFocus] = useState<AuditFocusFilter>("all");
  const [actionProposals, setActionProposals] = useState<ActionProposal[]>([]);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionSuccessMessage, setActionSuccessMessage] = useState<string | null>(null);
  const [pendingRepo, setPendingRepo] = useState<string | null>(null);

  const refreshActionProposals = useCallback(async (currentWorkspaceId: string) => {
    try {
      const payload = await fetchActionProposals(currentWorkspaceId, { limit: 100 });
      setActionProposals(payload.proposals);
    } catch {
      // Linked-action context is supplementary; keep the audit usable.
      setActionProposals([]);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    setStatus("loading");
    setError(null);
    fetchRepoAudit()
      .then((payload) => {
        if (cancelled) {
          return;
        }
        setData(payload);
        setStatus(payload.repo_facts.length > 0 ? "ready" : "empty");
      })
      .catch((caught: unknown) => {
        if (cancelled) {
          return;
        }
        setData(null);
        setError(caught instanceof Error ? caught.message : M.common.requestFailed);
        setStatus("error");
      });
    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

  useEffect(() => {
    if (!workspaceId) {
      setActionProposals([]);
      return;
    }
    void refreshActionProposals(workspaceId);
  }, [workspaceId, refreshActionProposals, reloadKey]);

  async function createLocalActionFromRepo(repo: RepoAuditRepoFact) {
    if (!workspaceId) {
      return;
    }
    setActionError(null);
    setActionSuccessMessage(null);
    setPendingRepo(repo.full_name);
    try {
      const payload = await createActionProposal(workspaceId, {
        action_type: "internal_todo",
        created_by: "user",
        description: buildAuditActionDescription(repo),
        evidence_refs: repo.evidence_refs.map((ref) => ({
          kind: "repo_audit_fact",
          source: "repo_audit",
          ref,
          url: null
        })),
        payload: {
          source: "repo_audit",
          repository_full_name: repo.full_name,
          area_candidate: repo.area_candidate ?? undefined,
          activity_bucket: repo.activity_bucket,
          related_entities: repo.risks
        },
        target_provider: "internal",
        title: buildAuditActionTitle(repo)
      });
      setActionProposals((current) => [
        payload.proposal,
        ...current.filter((proposal) => proposal.id !== payload.proposal.id)
      ]);
      setActionSuccessMessage(M.repoAudit.createActionSuccess);
    } catch (caught: unknown) {
      setActionError(caught instanceof Error ? caught.message : M.repoAudit.createActionError);
    } finally {
      setPendingRepo(null);
    }
  }

  return (
    <RepositoryAuditPanelView
      actionError={actionError}
      actionProposals={actionProposals}
      actionSuccessMessage={actionSuccessMessage}
      data={data}
      error={error}
      focus={focus}
      onCreateAction={createLocalActionFromRepo}
      onFocusChange={setFocus}
      onRetry={() => setReloadKey((current) => current + 1)}
      pendingRepo={pendingRepo}
      status={status}
    />
  );
}

export function RepositoryAuditPanelView({
  actionError = null,
  actionProposals = [],
  actionSuccessMessage = null,
  data,
  error,
  focus = "all",
  onCreateAction,
  onFocusChange,
  onRetry,
  pendingRepo = null,
  status
}: RepositoryAuditPanelViewProps) {
  const repoFacts = data?.repo_facts ?? [];
  const filteredRepoFacts = filterRepoFactsByFocus(repoFacts, focus);
  const linkedByRepo = auditActionsByRepository(actionProposals);

  return (
    <section className="panel repository-audit" aria-labelledby="repository-audit-title">
      <div className="section-header">
        <div>
          <span className="eyebrow">{M.repoAudit.eyebrow}</span>
          <h2 id="repository-audit-title">{M.repoAudit.title}</h2>
        </div>
        <span className="badge">{M.repoAudit.badgeDeterministic}</span>
      </div>

      {status === "loading" ? <LoadingState label={M.repoAudit.loading} /> : null}

      {status === "missing" ? (
        <EmptyState
          description={M.repoAudit.noWorkspaceDescription}
          title={M.common.noWorkspaceTitle}
        />
      ) : null}

      {status === "error" ? (
        <>
          <ErrorState
            description={error ?? M.repoAudit.unavailableDescription}
            title={M.repoAudit.unavailableTitle}
          />
          <button className="button secondary" onClick={onRetry} type="button">
            {M.common.retry}
          </button>
        </>
      ) : null}

      {status === "empty" ? (
        <EmptyState
          description={M.repoAudit.emptyDescription}
          title={M.repoAudit.emptyTitle}
        />
      ) : null}

      {data && status === "ready" ? (
        <>
          <p className="muted">{M.repoAudit.intro}</p>

          <section className="grid" aria-label={M.repoAudit.summaryLabel}>
            <StatusCard
              description={M.repoAudit.reposDescription}
              title={M.repoAudit.reposTitle}
              value={String(data.repo_count)}
            />
            <StatusCard
              description={M.repoAudit.riskDescription}
              title={M.repoAudit.riskTitle}
              value={String(totalRiskFlags(data.risk_summary))}
            />
            <StatusCard
              description={M.repoAudit.snapshotTitle}
              title={M.repoAudit.snapshotTitle}
              value={
                data.source_snapshot.available
                  ? String(data.source_snapshot.repo_count ?? data.repo_count)
                  : M.common.unavailable
              }
            />
            <StatusCard
              description={M.repoAudit.guardrailsSummary}
              title={M.repoAudit.guardrailsTitle}
              value={data.guardrails.external_writes ? M.common.enabled : M.common.notEnabled}
            />
          </section>

          <p className="muted">{M.repoAudit.boundaryNote}</p>

          {actionSuccessMessage ? (
            <p className="success-text">{actionSuccessMessage}</p>
          ) : null}
          {actionError ? <p className="error-text">{actionError}</p> : null}

          <section className="callout" aria-label={M.repoAudit.linkedActionsTitle}>
            <strong>{M.repoAudit.linkedActionsTitle}</strong>
            <p>
              {linkedByRepo.size > 0
                ? T.repoAuditLinkedActions(
                    countLinkedTotal(linkedByRepo),
                    countLinkedProposed(linkedByRepo),
                    countLinkedDecided(linkedByRepo)
                  )
                : M.repoAudit.linkedActionsEmpty}
            </p>
            <p>
              <a className="button secondary" href={ACTIONS_AUDIT_FOCUS_HREF}>
                {M.repoAudit.openActions}
              </a>
            </p>
          </section>

          <AuditFocusControl activeFilter={focus} onChange={onFocusChange} repoFacts={repoFacts} />

          <RepoAuditList
            linkedByRepo={linkedByRepo}
            onCreateAction={onCreateAction}
            pendingRepo={pendingRepo}
            repoFacts={filteredRepoFacts}
            totalRepoFacts={repoFacts.length}
          />
        </>
      ) : null}
    </section>
  );
}

function AuditFocusControl({
  activeFilter,
  onChange,
  repoFacts
}: {
  activeFilter: AuditFocusFilter;
  onChange?: (focus: AuditFocusFilter) => void;
  repoFacts: RepoAuditRepoFact[];
}) {
  const filters: AuditFocusFilter[] = ["all", "risks", "stale", "needs_confirm"];
  return (
    <section className="work-section" aria-label={M.repoAudit.focusLabel}>
      <h3>{M.repoAudit.focusTitle}</h3>
      <p className="muted">{M.repoAudit.focusDescription}</p>
      <div className="segmented" role="tablist" aria-label={M.repoAudit.focusLabel}>
        {filters.map((filter) => (
          <button
            aria-selected={activeFilter === filter}
            className={`segment${activeFilter === filter ? " active" : ""}`}
            key={filter}
            onClick={() => onChange?.(filter)}
            role="tab"
            type="button"
          >
            {auditFocusLabel(filter)} · {filterRepoFactsByFocus(repoFacts, filter).length}
          </button>
        ))}
      </div>
    </section>
  );
}

function RepoAuditList({
  linkedByRepo,
  onCreateAction,
  pendingRepo,
  repoFacts,
  totalRepoFacts
}: {
  linkedByRepo: Map<string, ActionProposal[]>;
  onCreateAction?: (repo: RepoAuditRepoFact) => void;
  pendingRepo: string | null;
  repoFacts: RepoAuditRepoFact[];
  totalRepoFacts: number;
}) {
  return (
    <section className="work-section" aria-label={M.repoAudit.listLabel}>
      <h3>{M.repoAudit.listTitle}</h3>
      {repoFacts.length === 0 && totalRepoFacts === 0 ? (
        <p className="muted">{M.repoAudit.emptyDescription}</p>
      ) : null}
      {repoFacts.length === 0 && totalRepoFacts > 0 ? (
        <p className="muted">{M.repoAudit.noReposForFilter}</p>
      ) : null}
      <div className="work-list">
        {repoFacts.map((repo) => {
          const linked = linkedByRepo.get(repo.full_name) ?? [];
          const hasOpenAction = linked.some(
            (proposal) => proposal.status === "proposed" || proposal.status === "approved"
          );
          return (
            <article className="work-item" key={repo.full_name}>
              <div className="work-item-main">
                <span className="badge">{repo.activity_bucket}</span>
                {repo.needs_founder_confirm ? (
                  <span className="badge badge-origin">{M.repoAudit.focusNeedsConfirm}</span>
                ) : null}
                <h4>{repo.full_name}</h4>
              </div>
              <dl className="work-meta">
                <div>
                  <dt>{M.repoAudit.metaVisibility}</dt>
                  <dd>{repo.visibility}</dd>
                </div>
                <div>
                  <dt>{M.repoAudit.metaActivity}</dt>
                  <dd>{T.repoAuditActivity(repo.activity_bucket, repo.days_since_last_push)}</dd>
                </div>
                <div>
                  <dt>{M.repoAudit.metaArea}</dt>
                  <dd>{repo.area_candidate ?? M.common.unknown}</dd>
                </div>
                <div>
                  <dt>{M.repoAudit.metaStack}</dt>
                  <dd>{repo.stack_candidate}</dd>
                </div>
                <div>
                  <dt>{M.repoAudit.metaReadme}</dt>
                  <dd>{repo.readme_status}</dd>
                </div>
                <div>
                  <dt>{M.repoAudit.metaTests}</dt>
                  <dd>{repo.tests_detected ? M.common.yes : M.common.no}</dd>
                </div>
                <div>
                  <dt>{M.repoAudit.metaCi}</dt>
                  <dd>{repo.ci_detected ? M.common.yes : M.common.no}</dd>
                </div>
                <div>
                  <dt>{M.repoAudit.metaEvidence}</dt>
                  <dd>{repo.evidence_refs.length}</dd>
                </div>
              </dl>
              {repo.risks.length > 0 ? (
                <p className="muted">
                  {M.repoAudit.risksLabel}: {repo.risks.join(", ")}
                </p>
              ) : (
                <p className="muted">{M.repoAudit.noRisks}</p>
              )}
              {repo.unknowns.length > 0 ? (
                <p className="muted">
                  {M.repoAudit.unknownsLabel}: {repo.unknowns.join(", ")}
                </p>
              ) : null}
              <div className="actions-row">
                <button
                  className="button secondary"
                  disabled={!onCreateAction || pendingRepo === repo.full_name || hasOpenAction}
                  onClick={() => onCreateAction?.(repo)}
                  type="button"
                >
                  {pendingRepo === repo.full_name
                    ? M.repoAudit.creatingAction
                    : hasOpenAction
                      ? M.repoAudit.actionAlreadyCreated
                      : M.repoAudit.createAction}
                </button>
                {linked.length > 0 ? (
                  <a className="button secondary" href={ACTIONS_AUDIT_FOCUS_HREF}>
                    {M.repoAudit.openActions}
                  </a>
                ) : null}
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}

function buildAuditActionTitle(repo: RepoAuditRepoFact): string {
  return `Repo audit follow-up: ${repo.full_name}`;
}

function buildAuditActionDescription(repo: RepoAuditRepoFact): string {
  const risks = repo.risks.length > 0 ? repo.risks.join(", ") : "нет детерминированных риск-флагов";
  return [
    `Репозиторий: ${repo.full_name}`,
    `Активность: ${repo.activity_bucket}`,
    `Область-кандидат: ${repo.area_candidate ?? "unknown"}`,
    `Риски: ${risks}`
  ].join("\n");
}

function filterRepoFactsByFocus(
  repoFacts: RepoAuditRepoFact[],
  focus: AuditFocusFilter
): RepoAuditRepoFact[] {
  switch (focus) {
    case "risks":
      return repoFacts.filter((repo) => repo.risks.length > 0);
    case "stale":
      return repoFacts.filter(
        (repo) => repo.activity_bucket === "stale" || repo.activity_bucket === "dormant"
      );
    case "needs_confirm":
      return repoFacts.filter((repo) => repo.needs_founder_confirm);
    case "all":
    default:
      return repoFacts;
  }
}

function auditFocusLabel(focus: AuditFocusFilter): string {
  switch (focus) {
    case "risks":
      return M.repoAudit.focusRisks;
    case "stale":
      return M.repoAudit.focusStale;
    case "needs_confirm":
      return M.repoAudit.focusNeedsConfirm;
    case "all":
    default:
      return M.repoAudit.focusAll;
  }
}

function totalRiskFlags(riskSummary: Record<string, number>): number {
  return Object.values(riskSummary).reduce((total, value) => total + (value || 0), 0);
}

function auditActionsByRepository(
  proposals: ActionProposal[]
): Map<string, ActionProposal[]> {
  const byRepo = new Map<string, ActionProposal[]>();
  for (const proposal of proposals) {
    if (proposalPayloadString(proposal.payload, "source") !== "repo_audit") {
      continue;
    }
    const repo = proposalPayloadString(proposal.payload, "repository_full_name");
    if (!repo) {
      continue;
    }
    const existing = byRepo.get(repo) ?? [];
    existing.push(proposal);
    byRepo.set(repo, existing);
  }
  return byRepo;
}

function proposalPayloadString(
  payload: Record<string, unknown>,
  key: string
): string | null {
  const value = payload[key];
  return typeof value === "string" && value.trim() ? value : null;
}

function countLinkedTotal(byRepo: Map<string, ActionProposal[]>): number {
  let total = 0;
  for (const proposals of byRepo.values()) {
    total += proposals.length;
  }
  return total;
}

function countLinkedProposed(byRepo: Map<string, ActionProposal[]>): number {
  let total = 0;
  for (const proposals of byRepo.values()) {
    total += proposals.filter((proposal) => proposal.status === "proposed").length;
  }
  return total;
}

function countLinkedDecided(byRepo: Map<string, ActionProposal[]>): number {
  let total = 0;
  for (const proposals of byRepo.values()) {
    total += proposals.filter(
      (proposal) => proposal.status !== "proposed"
    ).length;
  }
  return total;
}
