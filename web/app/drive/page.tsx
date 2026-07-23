"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";

import { PageHeader } from "../../components/PageHeader";
import { StatusCard } from "../../components/StatusCard";
import { fetchDriveFiles, importDriveFiles } from "../../lib/api";
import { M } from "../../lib/messages";
import {
  canAdministerSelectedWorkspace,
  useSession
} from "../../lib/session";
import type { DriveFile, DriveFileListResponse } from "../../lib/types";

type PanelStatus = "error" | "loading" | "missing" | "ready";

type DriveConnectorPanelViewProps = {
  canImport?: boolean;
  data: DriveFileListResponse | null;
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

export default function DrivePage() {
  const session = useSession();
  const workspaceId = session?.workspaceId ?? null;
  const canImport = canAdministerSelectedWorkspace(
    session?.workspaces ?? [],
    workspaceId
  );
  const [data, setData] = useState<DriveFileListResponse | null>(null);
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
    fetchDriveFiles(workspaceId)
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
    let files: Record<string, unknown>[];
    try {
      files = extractDriveFilesFromJson(importText);
    } catch (caught: unknown) {
      setImportError(caught instanceof Error ? caught.message : M.drive.importParseError);
      return;
    }

    setImportPending(true);
    try {
      const result = await importDriveFiles(workspaceId, { files });
      setImportMessage(
        M.drive.importSuccess(result.counts.imported, result.counts.failed)
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
        title="Google Drive"
        description="Документы и рабочие файлы, которые уже хранит команда."
      />
      <DriveConnectorPanelView
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

export function DriveConnectorPanelView({
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
}: DriveConnectorPanelViewProps) {
  return (
    <section className="panel drive" aria-labelledby="drive-title">
      <div className="section-header">
        <div>
          <span className="eyebrow">Данные Google Drive</span>
          <h2 id="drive-title">Файлы</h2>
        </div>
        <Link className="button secondary" href="/settings/integrations?provider=drive">
          Настроить Drive
        </Link>
      </div>

      {status === "loading" ? <p className="state loading">{M.drive.loading}</p> : null}

      {status === "missing" ? (
        <p className="muted">{M.drive.noWorkspaceDescription}</p>
      ) : null}

      {status === "error" ? (
        <section className="state error">
          <strong>{M.drive.unavailableTitle}</strong>
          <p>{error ?? M.drive.unavailableDescription}</p>
          {onRetry ? (
            <button className="button secondary" onClick={onRetry} type="button">
              {M.common.retry}
            </button>
          ) : null}
        </section>
      ) : null}

      {data && status === "ready" ? (
        <>
          <section className="grid" aria-label={M.drive.summaryLabel}>
            <StatusCard
              description="Сохранено в FounderOS"
              title="Все файлы"
              value={String(data.counts.total)}
            />
            <StatusCard
              description="Доступны команде"
              title="Общие"
              value={String(data.counts.shared)}
            />
            <StatusCard
              description="Доступны только владельцам"
              title="Без общего доступа"
              value={String(data.counts.not_shared)}
            />
          </section>

          {data.files.length === 0 ? (
            <section className="state empty">
              <strong>Файлов Google Drive пока нет</strong>
              <p>Подключите Drive и проверьте доступ. После синхронизации файлы появятся здесь.</p>
              <Link className="button" href="/settings/integrations?provider=drive">
                Подключить Drive
              </Link>
            </section>
          ) : (
            <div className="work-list" aria-label={M.drive.listLabel}>
              {data.files.map((file) => (
                <DriveFileCard file={file} key={file.source_record_id ?? file.file_id} />
              ))}
            </div>
          )}

          {canImport ? (
            <details className="source-developer-import">
              <summary>Импортировать JSON вручную</summary>
              <DriveImportForm
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

function DriveFileCard({ file }: { file: DriveFile }) {
  return (
    <article className="work-item">
      <div className="work-item-main">
        {file.shared ? <span className="badge">{M.drive.sharedBadge}</span> : null}
        <h3>{file.name}</h3>
      </div>
      <dl className="work-meta">
        <div>
          <dt>{M.drive.ownerLabel}</dt>
          <dd>{file.owners.length > 0 ? file.owners.join(", ") : M.common.unknown}</dd>
        </div>
        <div>
          <dt>{M.drive.mimeTypeLabel}</dt>
          <dd>{file.mime_type ?? M.common.none}</dd>
        </div>
        <div>
          <dt>{M.drive.modifiedLabel}</dt>
          <dd>{file.modified_at ?? M.common.none}</dd>
        </div>
        <div>
          <dt>{M.drive.evidenceLabel}</dt>
          <dd>{file.evidence_refs.length}</dd>
        </div>
      </dl>
      {file.source_url ? (
        <a
          className="button secondary"
          href={file.source_url}
          rel="noreferrer"
          target="_blank"
        >
          {M.common.openSource}
        </a>
      ) : null}
    </article>
  );
}

function DriveImportForm({
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
      <h3>{M.drive.importTitle}</h3>
      <p className="muted">{M.drive.importDescription}</p>
      <label htmlFor="drive-import-json">{M.drive.importTextareaLabel}</label>
      <textarea
        id="drive-import-json"
        onChange={(event) => onImportTextChange?.(event.target.value)}
        placeholder={M.drive.importPlaceholder}
        rows={8}
        value={importText}
      />
      {importMessage ? <p className="state success">{importMessage}</p> : null}
      {importError ? <p className="state error">{importError}</p> : null}
      <button className="button" disabled={importPending} type="submit">
        {importPending ? M.drive.importing : M.drive.importSubmit}
      </button>
    </form>
  );
}

export function extractDriveFilesFromJson(input: string): Record<string, unknown>[] {
  const parsed = JSON.parse(input) as unknown;
  const candidate = Array.isArray(parsed)
    ? parsed
    : isRecord(parsed) && Array.isArray(parsed.files)
      ? parsed.files
      : null;
  if (!candidate) {
    throw new Error(M.drive.importParseError);
  }
  const files = candidate.filter(isRecord);
  if (files.length === 0) {
    throw new Error(M.drive.importParseError);
  }
  return files;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
