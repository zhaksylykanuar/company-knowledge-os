"use client";

import { type FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import {
  createActionProposal,
  fetchActionProposals,
  fetchRepoAudit,
  importRepoAuditFindings
} from "../lib/api";
import { M, T } from "../lib/messages";
import { useWorkspaceId } from "../lib/session";
import type {
  ActionProposal,
  RepoAuditImportPreview,
  RepoAuditImportFindingRequest,
  RepoAuditRepoFact,
  RepoAuditResponse
} from "../lib/types";
import { EmptyState } from "./EmptyState";
import { ErrorState } from "./ErrorState";
import { LoadingState } from "./LoadingState";
import { StatusCard } from "./StatusCard";

type PanelStatus = "empty" | "error" | "loading" | "missing" | "ready";
type AuditFocusFilter = "all" | "needs_confirm" | "risks" | "stale";

const ACTIONS_AUDIT_FOCUS_HREF = "/actions?origin=audit&status=proposed";
const SECRET_TEXT_PATTERN =
  /\b(token|password|secret|api[_-]?key|private[_-]?key)\s*[:=]\s*[^\s,;]+/gi;
const REPO_FULL_NAME_PATTERN = /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/;
const EMPTY_IMPORT_PREVIEW: RepoAuditImportPreview = {
  parseError: null,
  findings: []
};

type RepositoryAuditPanelViewProps = {
  actionError?: string | null;
  actionProposals?: ActionProposal[];
  actionSuccessMessage?: string | null;
  data: RepoAuditResponse | null;
  error: string | null;
  focus?: AuditFocusFilter;
  externalAuditImportError?: string | null;
  externalAuditImportSuccess?: string | null;
  externalAuditText?: string;
  importPreview?: RepoAuditImportPreview;
  importFailuresByKey?: Map<number, string>;
  importSelectedKeys?: Set<number>;
  importValidCount?: number;
  onClearImportSelection?: () => void;
  onSelectAllValidImportFindings?: () => void;
  onToggleImportFinding?: (key: number) => void;
  isImportingExternalAudit?: boolean;
  onExternalAuditTextChange?: (value: string) => void;
  onImportExternalAudit?: (event: FormEvent<HTMLFormElement>) => void;
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
  const [externalAuditImportError, setExternalAuditImportError] = useState<string | null>(null);
  const [externalAuditImportSuccess, setExternalAuditImportSuccess] = useState<string | null>(null);
  const [externalAuditText, setExternalAuditText] = useState("");
  const [isImportingExternalAudit, setIsImportingExternalAudit] = useState(false);
  const [pendingRepo, setPendingRepo] = useState<string | null>(null);
  const [importSelectionOverride, setImportSelectionOverride] = useState<Set<number> | null>(
    null
  );
  const [importFailuresByKey, setImportFailuresByKey] = useState<Map<number, string>>(
    () => new Map()
  );

  const importPreview = useMemo(
    () => buildRepoAuditImportPreview(externalAuditText),
    [externalAuditText]
  );
  const validImportKeys = useMemo(
    () => importPreview.findings.filter((item) => item.valid).map((item) => item.key),
    [importPreview]
  );
  const selectedImportKeys = useMemo(() => {
    if (importSelectionOverride === null) {
      return new Set(validImportKeys);
    }
    return new Set(validImportKeys.filter((key) => importSelectionOverride.has(key)));
  }, [importSelectionOverride, validImportKeys]);

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

  async function importExternalAudit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspaceId) {
      return;
    }

    setExternalAuditImportError(null);
    setExternalAuditImportSuccess(null);
    const selectedFindings = importPreview.findings.filter((item) =>
      selectedImportKeys.has(item.key)
    );
    if (selectedFindings.length === 0) {
      setExternalAuditImportError(M.repoAudit.importNoValidSelected);
      return;
    }
    setIsImportingExternalAudit(true);
    setImportFailuresByKey(new Map());
    try {
      const submittedKeys = selectedFindings.map((item) => item.key);
      const response = await importRepoAuditFindings(workspaceId, {
        findings: selectedFindings.map((item) => item.finding)
      });
      const proposals = response.proposals;
      const failed = response.failed_count;
      if (proposals.length > 0) {
        setActionProposals((current) => [
          ...proposals,
          ...current.filter(
            (proposal) => !proposals.some((created) => created.id === proposal.id)
          )
        ]);
      }
      setExternalAuditImportSuccess(
        T.repoAuditImportResult(proposals.length, failed)
      );
      if (failed > 0) {
        const nextFailures = new Map<number, string>();
        const stillSelected = new Set<number>();
        for (const failure of response.failures) {
          const previewKey = submittedKeys[failure.index];
          if (previewKey === undefined) {
            continue;
          }
          nextFailures.set(previewKey, failure.detail);
          stillSelected.add(previewKey);
        }
        setImportFailuresByKey(nextFailures);
        setImportSelectionOverride(stillSelected);
        setExternalAuditImportError(M.repoAudit.importPartialFailure);
      } else {
        setExternalAuditText("");
        setImportSelectionOverride(null);
        setImportFailuresByKey(new Map());
      }
    } catch (caught: unknown) {
      setExternalAuditImportError(
        caught instanceof Error ? caught.message : M.repoAudit.importFailed
      );
    } finally {
      setIsImportingExternalAudit(false);
    }
  }

  function handleExternalAuditTextChange(value: string) {
    setExternalAuditText(value);
    setImportSelectionOverride(null);
    setImportFailuresByKey(new Map());
    setExternalAuditImportError(null);
    setExternalAuditImportSuccess(null);
  }

  function toggleImportFinding(key: number) {
    setImportSelectionOverride((current) => {
      const base = current ?? new Set(validImportKeys);
      const next = new Set(base);
      if (next.has(key)) {
        next.delete(key);
      } else if (validImportKeys.includes(key)) {
        next.add(key);
      }
      return next;
    });
  }

  function selectAllValidImportFindings() {
    setImportSelectionOverride(new Set(validImportKeys));
  }

  function clearImportSelection() {
    setImportSelectionOverride(new Set());
  }

  return (
    <RepositoryAuditPanelView
      actionError={actionError}
      actionProposals={actionProposals}
      actionSuccessMessage={actionSuccessMessage}
      data={data}
      error={error}
      externalAuditImportError={externalAuditImportError}
      externalAuditImportSuccess={externalAuditImportSuccess}
      externalAuditText={externalAuditText}
      importPreview={importPreview}
      importFailuresByKey={importFailuresByKey}
      importSelectedKeys={selectedImportKeys}
      importValidCount={validImportKeys.length}
      onClearImportSelection={clearImportSelection}
      onSelectAllValidImportFindings={selectAllValidImportFindings}
      onToggleImportFinding={toggleImportFinding}
      focus={focus}
      isImportingExternalAudit={isImportingExternalAudit}
      onCreateAction={createLocalActionFromRepo}
      onExternalAuditTextChange={handleExternalAuditTextChange}
      onFocusChange={setFocus}
      onImportExternalAudit={importExternalAudit}
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
  externalAuditImportError = null,
  externalAuditImportSuccess = null,
  externalAuditText = "",
  importPreview = EMPTY_IMPORT_PREVIEW,
  importFailuresByKey,
  importSelectedKeys,
  importValidCount = 0,
  onClearImportSelection,
  onSelectAllValidImportFindings,
  onToggleImportFinding,
  focus = "all",
  isImportingExternalAudit = false,
  onCreateAction,
  onExternalAuditTextChange,
  onFocusChange,
  onImportExternalAudit,
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

          <ExternalAuditImportForm
            error={externalAuditImportError}
            failuresByKey={importFailuresByKey}
            isImporting={isImportingExternalAudit}
            onChange={onExternalAuditTextChange}
            onClearSelection={onClearImportSelection}
            onSelectAllValid={onSelectAllValidImportFindings}
            onSubmit={onImportExternalAudit}
            onToggleFinding={onToggleImportFinding}
            preview={importPreview}
            selectedKeys={importSelectedKeys}
            successMessage={externalAuditImportSuccess}
            validCount={importValidCount}
            value={externalAuditText}
          />

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

function ExternalAuditImportForm({
  error,
  failuresByKey,
  isImporting,
  onChange,
  onClearSelection,
  onSelectAllValid,
  onSubmit,
  onToggleFinding,
  preview,
  selectedKeys,
  successMessage,
  validCount,
  value
}: {
  error: string | null;
  failuresByKey?: Map<number, string>;
  isImporting: boolean;
  onChange?: (value: string) => void;
  onClearSelection?: () => void;
  onSelectAllValid?: () => void;
  onSubmit?: (event: FormEvent<HTMLFormElement>) => void;
  onToggleFinding?: (key: number) => void;
  preview: RepoAuditImportPreview;
  selectedKeys?: Set<number>;
  successMessage: string | null;
  validCount: number;
  value: string;
}) {
  const selected = selectedKeys ?? new Set<number>();
  const failures = failuresByKey ?? new Map<number, string>();
  const selectedCount = selected.size;
  return (
    <form className="form" onSubmit={onSubmit}>
      <h3>{M.repoAudit.importTitle}</h3>
      <p className="muted">{M.repoAudit.importDescription}</p>
      <div className="field">
        <label htmlFor="external-repo-audit-json">{M.repoAudit.importLabel}</label>
        <textarea
          id="external-repo-audit-json"
          maxLength={20000}
          onChange={(event) => onChange?.(event.target.value)}
          placeholder={M.repoAudit.importPlaceholder}
          value={value}
        />
      </div>
      <ExternalAuditImportPreview
        failures={failures}
        onClearSelection={onClearSelection}
        onSelectAllValid={onSelectAllValid}
        onToggleFinding={onToggleFinding}
        preview={preview}
        selected={selected}
        selectedCount={selectedCount}
        validCount={validCount}
      />
      <button
        className="button"
        disabled={isImporting || selectedCount === 0}
        type="submit"
      >
        {isImporting ? M.repoAudit.importing : M.repoAudit.importSubmit}
      </button>
      <p className="muted">{M.repoAudit.importBoundary}</p>
      {successMessage ? <p className="success-text">{successMessage}</p> : null}
      {error ? <p className="error-text">{error}</p> : null}
    </form>
  );
}

function ExternalAuditImportPreview({
  failures,
  onClearSelection,
  onSelectAllValid,
  onToggleFinding,
  preview,
  selected,
  selectedCount,
  validCount
}: {
  failures: Map<number, string>;
  onClearSelection?: () => void;
  onSelectAllValid?: () => void;
  onToggleFinding?: (key: number) => void;
  preview: RepoAuditImportPreview;
  selected: Set<number>;
  selectedCount: number;
  validCount: number;
}) {
  const hasText = preview.parseError !== null || preview.findings.length > 0;
  return (
    <section className="work-section" aria-label={M.repoAudit.importPreviewTitle}>
      <h4>{M.repoAudit.importPreviewTitle}</h4>
      {!hasText ? <p className="muted">{M.repoAudit.importPreviewEmpty}</p> : null}
      {preview.parseError ? <p className="error-text">{preview.parseError}</p> : null}
      {preview.findings.length > 0 ? (
        <>
          <p className="muted">
            {T.repoAuditImportPreview(
              preview.findings.length,
              validCount,
              selectedCount
            )}
          </p>
          <div className="actions-row">
            <button
              className="button secondary"
              disabled={!onSelectAllValid || validCount === 0}
              onClick={onSelectAllValid}
              type="button"
            >
              {M.repoAudit.importSelectAllValid}
            </button>
            <button
              className="button secondary"
              disabled={!onClearSelection || selectedCount === 0}
              onClick={onClearSelection}
              type="button"
            >
              {M.repoAudit.importClearSelection}
            </button>
          </div>
          <div className="work-list">
            {preview.findings.map((item) => {
              const failureDetail = failures.get(item.key);
              return (
                <article className="work-item" key={item.key}>
                  <div className="work-item-main">
                    <span className={`badge${item.valid ? "" : " badge-origin"}`}>
                      {item.valid
                        ? M.repoAudit.importPreviewValidBadge
                        : M.repoAudit.importPreviewInvalidBadge}
                    </span>
                    <h5>
                      {item.finding.repository_full_name ||
                        item.finding.title ||
                        M.common.unknown}
                    </h5>
                  </div>
                  {item.finding.title ? (
                    <p className="muted">{item.finding.title}</p>
                  ) : null}
                  <p className="muted">
                    {M.repoAudit.metaEvidence}: {item.finding.evidence_refs?.length ?? 0}
                  </p>
                  {item.issues.length > 0 ? (
                    <p className="muted">{item.issues.join(" ")}</p>
                  ) : null}
                  {failureDetail ? (
                    <p className="error-text">
                      {M.repoAudit.importBackendFailureLabel}: {failureDetail}
                    </p>
                  ) : null}
                  <label className="proposal-selection">
                    <input
                      checked={selected.has(item.key)}
                      disabled={!item.valid || !onToggleFinding}
                      onChange={() => onToggleFinding?.(item.key)}
                      type="checkbox"
                    />
                    <span>{M.repoAudit.importSelectFinding}</span>
                  </label>
                </article>
              );
            })}
          </div>
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
    if (!isAuditProposalSource(proposalPayloadString(proposal.payload, "source"))) {
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

function isAuditProposalSource(source: string | null): boolean {
  return source === "repo_audit" || source === "repo_audit_import";
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

export function buildRepoAuditImportPreview(raw: string): RepoAuditImportPreview {
  if (!raw.trim()) {
    return { parseError: null, findings: [] };
  }
  let payload: unknown;
  try {
    payload = JSON.parse(raw);
  } catch {
    return { parseError: M.repoAudit.importInvalidJson, findings: [] };
  }
  const rawFindings = Array.isArray(payload)
    ? payload
    : isRecord(payload) && Array.isArray(payload.findings)
      ? payload.findings
      : null;
  if (rawFindings === null || rawFindings.length === 0) {
    return { parseError: M.repoAudit.importNoFindings, findings: [] };
  }
  const findings = rawFindings.slice(0, 50).map((item, index) => {
    const issues: string[] = [];
    if (!isRecord(item)) {
      return {
        key: index,
        finding: {
          repository_full_name: "",
          evidence_refs: [] as string[]
        },
        valid: false,
        issues: [M.repoAudit.importIssueNotObject]
      };
    }
    const finding = normalizeExternalAuditFinding(item) ?? {
      repository_full_name: "",
      evidence_refs: [] as string[]
    };
    if (!REPO_FULL_NAME_PATTERN.test(finding.repository_full_name)) {
      issues.push(M.repoAudit.importIssueRepoFormat);
    }
    if (!finding.evidence_refs || finding.evidence_refs.length === 0) {
      issues.push(M.repoAudit.importIssueEvidence);
    }
    return {
      key: index,
      finding,
      valid: issues.length === 0,
      issues
    };
  });
  return { parseError: null, findings };
}

export function parseExternalAuditFindings(raw: string): RepoAuditImportFindingRequest[] {
  let payload: unknown;
  try {
    payload = JSON.parse(raw);
  } catch (caught) {
    throw new Error(M.repoAudit.importInvalidJson);
  }
  const rawFindings =
    Array.isArray(payload)
      ? payload
      : isRecord(payload) && Array.isArray(payload.findings)
        ? payload.findings
        : [];
  const findings = rawFindings
    .map((item) => normalizeExternalAuditFinding(item))
    .filter((item): item is RepoAuditImportFindingRequest => item !== null);
  if (findings.length === 0) {
    throw new Error(M.repoAudit.importNoFindings);
  }
  return findings.slice(0, 50);
}

function normalizeExternalAuditFinding(
  value: unknown
): RepoAuditImportFindingRequest | null {
  if (!isRecord(value)) {
    return null;
  }
  const repository = safeImportedText(value.repository_full_name, "", 160);
  const evidenceRefs = importedStringList(value.evidence_refs, 20, 500);
  const title = safeImportedText(
    value.title,
    `External repo audit follow-up: ${repository}`,
    500
  );
  const summary = safeImportedText(value.summary, "External audit finding.", 2000);
  return {
    area_candidate: optionalImportedText(value.area_candidate, 80),
    evidence_refs: evidenceRefs,
    recommended_next_step: optionalImportedText(value.recommended_next_step, 1000),
    repository_full_name: repository,
    risks: importedStringList(value.risks, 20, 120),
    severity: optionalImportedText(value.severity, 40),
    summary,
    title
  };
}

function importedStringList(value: unknown, maxItems: number, limit: number): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .map((item) => safeImportedText(item, "", limit))
    .filter((item) => item.length > 0)
    .slice(0, maxItems);
}

function optionalImportedText(value: unknown, limit: number): string | null {
  const text = safeImportedText(value, "", limit);
  return text.length > 0 ? text : null;
}

function safeImportedText(value: unknown, fallback: string, limit: number): string {
  const raw = typeof value === "string" ? value : fallback;
  return raw
    .replace(SECRET_TEXT_PATTERN, "$1=[redacted]")
    .trim()
    .slice(0, limit);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
