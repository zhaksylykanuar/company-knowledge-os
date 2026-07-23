"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";

import { PageHeader } from "../../components/PageHeader";
import { StatusCard } from "../../components/StatusCard";
import { fetchJiraIssues, importJiraIssues } from "../../lib/api";
import { M } from "../../lib/messages";
import {
  canAdministerSelectedWorkspace,
  useSession
} from "../../lib/session";
import type { JiraIssue, JiraIssueListResponse } from "../../lib/types";

type PanelStatus = "error" | "loading" | "missing" | "ready";

type JiraConnectorPanelViewProps = {
  canImport?: boolean;
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
  const session = useSession();
  const workspaceId = session?.workspaceId ?? null;
  const canImport = canAdministerSelectedWorkspace(
    session?.workspaces ?? [],
    workspaceId
  );
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
    if (!workspaceId || !canImport || importPending) {
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
        eyebrow="Источники"
        title="Jira"
        description="Задачи, ответственные, сроки и статусы работы."
      />
      <JiraConnectorPanelView
        canImport={canImport}
        data={data}
        error={error}
        importError={importError}
        importMessage={importMessage}
        importPending={importPending}
        importText={importText}
        onImport={canImport ? handleImport : undefined}
        onImportTextChange={canImport ? setImportText : undefined}
        onRetry={() => setReloadKey((current) => current + 1)}
        status={status}
      />
    </>
  );
}

export function JiraConnectorPanelView({
  canImport = true,
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
          <span className="eyebrow">Данные Jira</span>
          <h2 id="jira-title">Задачи</h2>
        </div>
        <Link className="button secondary" href="/settings/integrations?provider=jira">
          Настроить Jira
        </Link>
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
              description="Сохранено в FounderOS"
              title="Все задачи"
              value={String(data.counts.total)}
            />
            <StatusCard
              description="Требуют дальнейшей работы"
              title="В работе"
              value={String(data.counts.not_done)}
            />
            <StatusCard
              description="Завершённые задачи"
              title="Готово"
              value={String(data.counts.done)}
            />
          </section>

          {data.issues.length === 0 ? (
            <section className="state empty">
              <strong>Задач Jira пока нет</strong>
              <p>Подключите Jira и проверьте доступ. После синхронизации задачи появятся здесь.</p>
              <Link className="button" href="/settings/integrations?provider=jira">
                Подключить Jira
              </Link>
            </section>
          ) : (
            <div className="work-list" aria-label={M.jira.listLabel}>
              {data.issues.map((issue) => (
                <JiraIssueCard issue={issue} key={issue.task_id ?? issue.key} />
              ))}
            </div>
          )}

          {canImport ? (
            <details className="source-developer-import">
              <summary>Импортировать JSON вручную</summary>
              <JiraImportForm
                importError={importError}
                importMessage={importMessage}
                importPending={importPending}
                importText={importText}
                onImport={onImport}
                onImportTextChange={onImportTextChange}
              />
            </details>
          ) : (
            <p className="muted">{M.common.sourceAdminOnlyNote}</p>
          )}
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
