"use client";

import { FormEvent, useEffect, useState } from "react";

import { PageHeader } from "../../components/PageHeader";
import { StatusCard } from "../../components/StatusCard";
import { fetchJiraIssues, importJiraIssues } from "../../lib/api";
import { M } from "../../lib/messages";
import { useWorkspaceId } from "../../lib/session";
import type { JiraIssue, JiraIssueListResponse } from "../../lib/types";

type PanelStatus = "error" | "loading" | "missing" | "ready";

type JiraConnectorPanelViewProps = {
  data: JiraIssueListResponse | null;
  error: string | null;
  importError: string | null;
  importMessage: string | null;
  importPending: boolean;
  importText: string;
  onImport?: (event: FormEvent<HTMLFormElement>) => void;
  onImportTextChange?: (value: string) => void;
  onRetry?: () => void;
  status: PanelStatus;
};

export default function JiraPage() {
  const workspaceId = useWorkspaceId();
  const [data, setData] = useState<JiraIssueListResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [importError, setImportError] = useState<string | null>(null);
  const [importMessage, setImportMessage] = useState<string | null>(null);
  const [importPending, setImportPending] = useState(false);
  const [importText, setImportText] = useState("");
  const [reloadKey, setReloadKey] = useState(0);
  const [status, setStatus] = useState<PanelStatus>("loading");

  useEffect(() => {
    if (!workspaceId) {
      setData(null);
      setError(null);
      setStatus("missing");
      return;
    }

    let cancelled = false;
    setStatus("loading");
    setError(null);
    fetchJiraIssues(workspaceId)
      .then((payload) => {
        if (cancelled) {
          return;
        }
        setData(payload);
        setStatus("ready");
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
  }, [workspaceId, reloadKey]);

  async function handleImport(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspaceId || importPending) {
      return;
    }
    setImportError(null);
    setImportMessage(null);
    let issues: Record<string, unknown>[];
    try {
      issues = extractJiraIssuesFromJson(importText);
    } catch (caught: unknown) {
      setImportError(caught instanceof Error ? caught.message : M.jira.importParseError);
      return;
    }

    setImportPending(true);
    try {
      const result = await importJiraIssues(workspaceId, { issues });
      setImportMessage(
        M.jira.importSuccess(result.counts.imported, result.counts.failed)
      );
      setReloadKey((current) => current + 1);
    } catch (caught: unknown) {
      setImportError(caught instanceof Error ? caught.message : M.common.requestFailed);
    } finally {
      setImportPending(false);
    }
  }

  return (
    <>
      <PageHeader
        eyebrow={M.jira.eyebrow}
        title={M.jira.title}
        description={M.jira.description}
      />
      <JiraConnectorPanelView
        data={data}
        error={error}
        importError={importError}
        importMessage={importMessage}
        importPending={importPending}
        importText={importText}
        onImport={handleImport}
        onImportTextChange={setImportText}
        onRetry={() => setReloadKey((current) => current + 1)}
        status={status}
      />
    </>
  );
}

export function JiraConnectorPanelView({
  data,
  error,
  importError,
  importMessage,
  importPending,
  importText,
  onImport,
  onImportTextChange,
  onRetry,
  status
}: JiraConnectorPanelViewProps) {
  return (
    <section className="panel jira" aria-labelledby="jira-title">
      <div className="section-header">
        <div>
          <span className="eyebrow">{M.jira.eyebrow}</span>
          <h2 id="jira-title">{M.jira.title}</h2>
        </div>
        <span className="badge">{M.jira.badgeLocalOnly}</span>
      </div>

      {status === "loading" ? <p className="state loading">{M.jira.loading}</p> : null}

      {status === "missing" ? (
        <p className="muted">{M.jira.noWorkspaceDescription}</p>
      ) : null}

      {status === "error" ? (
        <section className="state error">
          <strong>{M.jira.unavailableTitle}</strong>
          <p>{error ?? M.jira.unavailableDescription}</p>
          {onRetry ? (
            <button className="button secondary" onClick={onRetry} type="button">
              {M.common.retry}
            </button>
          ) : null}
        </section>
      ) : null}

      {data && status === "ready" ? (
        <>
          <section className="grid" aria-label={M.jira.summaryLabel}>
            <StatusCard
              description={M.jira.totalDescription}
              title={M.jira.totalTitle}
              value={String(data.counts.total)}
            />
            <StatusCard
              description={M.jira.notDoneDescription}
              title={M.jira.notDoneTitle}
              value={String(data.counts.not_done)}
            />
            <StatusCard
              description={M.jira.doneDescription}
              title={M.jira.doneTitle}
              value={String(data.counts.done)}
            />
          </section>

          {data.issues.length === 0 ? (
            <section className="state empty">
              <strong>{M.jira.emptyTitle}</strong>
              <p>{M.jira.emptyDescription}</p>
            </section>
          ) : (
            <div className="work-list" aria-label={M.jira.listLabel}>
              {data.issues.map((issue) => (
                <JiraIssueCard issue={issue} key={issue.task_id ?? issue.key} />
              ))}
            </div>
          )}

          {data.warnings.length > 0 ? (
            <section className="callout" aria-label={M.jira.warningsTitle}>
              <strong>{M.jira.warningsTitle}</strong>
              <ul>
                {data.warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            </section>
          ) : null}

          <JiraImportForm
            importError={importError}
            importMessage={importMessage}
            importPending={importPending}
            importText={importText}
            onImport={onImport}
            onImportTextChange={onImportTextChange}
          />

          <p className="muted">{M.jira.boundaryNote}</p>
        </>
      ) : null}
    </section>
  );
}

function JiraIssueCard({ issue }: { issue: JiraIssue }) {
  return (
    <article className="work-item">
      <div className="work-item-main">
        <span className="badge">{issue.key}</span>
        <h3>{issue.title}</h3>
      </div>
      <dl className="work-meta">
        <div>
          <dt>{M.jira.statusLabel}</dt>
          <dd>{issue.status ?? M.common.unknown}</dd>
        </div>
        <div>
          <dt>{M.jira.priorityLabel}</dt>
          <dd>{issue.priority ?? M.common.none}</dd>
        </div>
        <div>
          <dt>{M.jira.dueDateLabel}</dt>
          <dd>{issue.due_date ?? M.common.none}</dd>
        </div>
        <div>
          <dt>{M.jira.evidenceLabel}</dt>
          <dd>{issue.evidence_refs.length}</dd>
        </div>
      </dl>
      {issue.source_url ? (
        <a className="button secondary" href={issue.source_url} rel="noreferrer" target="_blank">
          {M.common.openSource}
        </a>
      ) : null}
    </article>
  );
}

function JiraImportForm({
  importError,
  importMessage,
  importPending,
  importText,
  onImport,
  onImportTextChange
}: {
  importError: string | null;
  importMessage: string | null;
  importPending: boolean;
  importText: string;
  onImport?: (event: FormEvent<HTMLFormElement>) => void;
  onImportTextChange?: (value: string) => void;
}) {
  return (
    <form className="stack" onSubmit={onImport}>
      <h3>{M.jira.importTitle}</h3>
      <p className="muted">{M.jira.importDescription}</p>
      <label htmlFor="jira-import-json">{M.jira.importTextareaLabel}</label>
      <textarea
        id="jira-import-json"
        onChange={(event) => onImportTextChange?.(event.target.value)}
        placeholder={M.jira.importPlaceholder}
        rows={8}
        value={importText}
      />
      {importMessage ? <p className="state success">{importMessage}</p> : null}
      {importError ? <p className="state error">{importError}</p> : null}
      <button className="button" disabled={importPending} type="submit">
        {importPending ? M.jira.importing : M.jira.importSubmit}
      </button>
    </form>
  );
}

export function extractJiraIssuesFromJson(input: string): Record<string, unknown>[] {
  const parsed = JSON.parse(input) as unknown;
  const candidate = Array.isArray(parsed)
    ? parsed
    : isRecord(parsed) && Array.isArray(parsed.issues)
      ? parsed.issues
      : null;
  if (!candidate) {
    throw new Error(M.jira.importParseError);
  }
  const issues = candidate.filter(isRecord);
  if (issues.length === 0) {
    throw new Error(M.jira.importParseError);
  }
  return issues;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
