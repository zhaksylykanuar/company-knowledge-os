"use client";

import { FormEvent, useEffect, useState } from "react";

import { PageHeader } from "../../components/PageHeader";
import { StatusCard } from "../../components/StatusCard";
import { fetchGmailMessages, importGmailMessages } from "../../lib/api";
import { M } from "../../lib/messages";
import {
  canAdministerSelectedWorkspace,
  useSession
} from "../../lib/session";
import type { GmailMessage, GmailMessageListResponse } from "../../lib/types";

type PanelStatus = "error" | "loading" | "missing" | "ready";

type GmailConnectorPanelViewProps = {
  canImport?: boolean;
  data: GmailMessageListResponse | null;
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

export default function GmailPage() {
  const session = useSession();
  const workspaceId = session?.workspaceId ?? null;
  const canImport = canAdministerSelectedWorkspace(
    session?.workspaces ?? [],
    workspaceId
  );
  const [data, setData] = useState<GmailMessageListResponse | null>(null);
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
    fetchGmailMessages(workspaceId)
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
    let messages: Record<string, unknown>[];
    try {
      messages = extractGmailMessagesFromJson(importText);
    } catch (caught: unknown) {
      setImportError(caught instanceof Error ? caught.message : M.gmail.importParseError);
      return;
    }

    setImportPending(true);
    try {
      const result = await importGmailMessages(workspaceId, { messages });
      setImportMessage(
        M.gmail.importSuccess(result.counts.imported, result.counts.failed)
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
        eyebrow={M.gmail.eyebrow}
        title={M.gmail.title}
        description={M.gmail.description}
      />
      <GmailConnectorPanelView
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

export function GmailConnectorPanelView({
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
}: GmailConnectorPanelViewProps) {
  return (
    <section className="panel gmail" aria-labelledby="gmail-title">
      <div className="section-header">
        <div>
          <span className="eyebrow">{M.gmail.eyebrow}</span>
          <h2 id="gmail-title">{M.gmail.title}</h2>
        </div>
        <span className="badge">{M.gmail.badgeLocalOnly}</span>
      </div>

      {status === "loading" ? <p className="state loading">{M.gmail.loading}</p> : null}

      {status === "missing" ? (
        <p className="muted">{M.gmail.noWorkspaceDescription}</p>
      ) : null}

      {status === "error" ? (
        <section className="state error">
          <strong>{M.gmail.unavailableTitle}</strong>
          <p>{error ?? M.gmail.unavailableDescription}</p>
          {onRetry ? (
            <button className="button secondary" onClick={onRetry} type="button">
              {M.common.retry}
            </button>
          ) : null}
        </section>
      ) : null}

      {data && status === "ready" ? (
        <>
          <section className="grid" aria-label={M.gmail.summaryLabel}>
            <StatusCard
              description={M.gmail.totalDescription}
              title={M.gmail.totalTitle}
              value={String(data.counts.total)}
            />
            <StatusCard
              description={M.gmail.unreadDescription}
              title={M.gmail.unreadTitle}
              value={String(data.counts.unread)}
            />
            <StatusCard
              description={M.gmail.readDescription}
              title={M.gmail.readTitle}
              value={String(data.counts.read)}
            />
          </section>

          {data.messages.length === 0 ? (
            <section className="state empty">
              <strong>{M.gmail.emptyTitle}</strong>
              <p>{M.gmail.emptyDescription}</p>
            </section>
          ) : (
            <div className="work-list" aria-label={M.gmail.listLabel}>
              {data.messages.map((message) => (
                <GmailMessageCard
                  key={message.source_record_id ?? message.message_id}
                  message={message}
                />
              ))}
            </div>
          )}

          {data.warnings.length > 0 ? (
            <section className="callout" aria-label={M.gmail.warningsTitle}>
              <strong>{M.gmail.warningsTitle}</strong>
              <ul>
                {data.warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            </section>
          ) : null}

          {canImport ? (
            <GmailImportForm
              importError={importError}
              importMessage={importMessage}
              importPending={importPending}
              importText={importText}
              onImport={onImport}
              onImportTextChange={onImportTextChange}
            />
          ) : (
            <p className="muted">{M.common.sourceAdminOnlyNote}</p>
          )}

          <p className="muted">{M.gmail.boundaryNote}</p>
        </>
      ) : null}
    </section>
  );
}

function GmailMessageCard({ message }: { message: GmailMessage }) {
  return (
    <article className="work-item">
      <div className="work-item-main">
        {message.unread ? <span className="badge">{M.gmail.unreadBadge}</span> : null}
        <h3>{message.subject}</h3>
      </div>
      {message.snippet ? <p className="muted">{message.snippet}</p> : null}
      <dl className="work-meta">
        <div>
          <dt>{M.gmail.fromLabel}</dt>
          <dd>{message.from_address ?? M.common.unknown}</dd>
        </div>
        <div>
          <dt>{M.gmail.labelsLabel}</dt>
          <dd>{message.labels.length > 0 ? message.labels.join(", ") : M.common.none}</dd>
        </div>
        <div>
          <dt>{M.gmail.receivedLabel}</dt>
          <dd>{message.received_at ?? M.common.none}</dd>
        </div>
        <div>
          <dt>{M.gmail.evidenceLabel}</dt>
          <dd>{message.evidence_refs.length}</dd>
        </div>
      </dl>
      {message.source_url ? (
        <a
          className="button secondary"
          href={message.source_url}
          rel="noreferrer"
          target="_blank"
        >
          {M.common.openSource}
        </a>
      ) : null}
    </article>
  );
}

function GmailImportForm({
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
      <h3>{M.gmail.importTitle}</h3>
      <p className="muted">{M.gmail.importDescription}</p>
      <label htmlFor="gmail-import-json">{M.gmail.importTextareaLabel}</label>
      <textarea
        id="gmail-import-json"
        onChange={(event) => onImportTextChange?.(event.target.value)}
        placeholder={M.gmail.importPlaceholder}
        rows={8}
        value={importText}
      />
      {importMessage ? <p className="state success">{importMessage}</p> : null}
      {importError ? <p className="state error">{importError}</p> : null}
      <button className="button" disabled={importPending} type="submit">
        {importPending ? M.gmail.importing : M.gmail.importSubmit}
      </button>
    </form>
  );
}

export function extractGmailMessagesFromJson(input: string): Record<string, unknown>[] {
  const parsed = JSON.parse(input) as unknown;
  const candidate = Array.isArray(parsed)
    ? parsed
    : isRecord(parsed) && Array.isArray(parsed.messages)
      ? parsed.messages
      : null;
  if (!candidate) {
    throw new Error(M.gmail.importParseError);
  }
  const messages = candidate.filter(isRecord);
  if (messages.length === 0) {
    throw new Error(M.gmail.importParseError);
  }
  return messages;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
