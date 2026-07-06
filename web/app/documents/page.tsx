"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";

import { PageHeader } from "../../components/PageHeader";
import { StatusCard } from "../../components/StatusCard";
import {
  createDocument,
  fetchDocument,
  fetchDocumentVersions,
  fetchDocuments
} from "../../lib/api";
import { M } from "../../lib/messages";
import { useWorkspaceId } from "../../lib/session";
import type {
  DocumentDetail,
  DocumentListResponse,
  DocumentSummary,
  DocumentVersion
} from "../../lib/types";

type PanelStatus = "error" | "loading" | "missing" | "ready";

export default function DocumentsPage() {
  const workspaceId = useWorkspaceId();
  const [data, setData] = useState<DocumentListResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<PanelStatus>("loading");
  const [search, setSearch] = useState("");
  const [activeSearch, setActiveSearch] = useState("");
  const [reloadKey, setReloadKey] = useState(0);
  const [selected, setSelected] = useState<DocumentDetail | null>(null);
  const [selectedVersions, setSelectedVersions] = useState<DocumentVersion[]>([]);
  const [createTitle, setCreateTitle] = useState("");
  const [createBody, setCreateBody] = useState("");
  const [createTags, setCreateTags] = useState("");
  const [createStatusValue, setCreateStatusValue] = useState("draft");
  const [createError, setCreateError] = useState<string | null>(null);
  const [createMessage, setCreateMessage] = useState<string | null>(null);
  const [createPending, setCreatePending] = useState(false);

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
    fetchDocuments(workspaceId, { search: activeSearch || undefined })
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
  }, [workspaceId, activeSearch, reloadKey]);

  const openDocument = useCallback(
    async (documentId: string) => {
      if (!workspaceId) {
        return;
      }
      try {
        const [payload, versions] = await Promise.all([
          fetchDocument(workspaceId, documentId),
          fetchDocumentVersions(workspaceId, documentId)
        ]);
        setSelected(payload.document);
        setSelectedVersions(versions.versions);
      } catch (caught: unknown) {
        setError(caught instanceof Error ? caught.message : M.common.requestFailed);
      }
    },
    [workspaceId]
  );

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspaceId || createPending) {
      return;
    }
    setCreateError(null);
    setCreateMessage(null);
    if (!createTitle.trim()) {
      setCreateError(M.documents.titleRequired);
      return;
    }
    setCreatePending(true);
    try {
      await createDocument(workspaceId, {
        title: createTitle.trim(),
        body_markdown: createBody,
        tags: parseTags(createTags),
        status: createStatusValue
      });
      setCreateTitle("");
      setCreateBody("");
      setCreateTags("");
      setCreateStatusValue("draft");
      setCreateMessage(M.documents.createSuccess);
      setReloadKey((current) => current + 1);
    } catch (caught: unknown) {
      setCreateError(caught instanceof Error ? caught.message : M.common.requestFailed);
    } finally {
      setCreatePending(false);
    }
  }

  return (
    <>
      <PageHeader
        eyebrow={M.documents.eyebrow}
        title={M.documents.title}
        description={M.documents.description}
      />
      <DocumentsPanelView
        createBody={createBody}
        createError={createError}
        createMessage={createMessage}
        createPending={createPending}
        createStatusValue={createStatusValue}
        createTags={createTags}
        createTitle={createTitle}
        data={data}
        error={error}
        onCreate={handleCreate}
        onCreateBodyChange={setCreateBody}
        onCreateStatusChange={setCreateStatusValue}
        onCreateTagsChange={setCreateTags}
        onCreateTitleChange={setCreateTitle}
        onOpenDocument={openDocument}
        onSearchChange={setSearch}
        onSearchClear={() => {
          setSearch("");
          setActiveSearch("");
        }}
        onSearchSubmit={() => setActiveSearch(search.trim())}
        onCloseDetail={() => {
          setSelected(null);
          setSelectedVersions([]);
        }}
        onRetry={() => setReloadKey((current) => current + 1)}
        search={search}
        selected={selected}
        selectedVersions={selectedVersions}
        status={status}
      />
    </>
  );
}

type DocumentsPanelViewProps = {
  createBody: string;
  createError: string | null;
  createMessage: string | null;
  createPending: boolean;
  createStatusValue: string;
  createTags: string;
  createTitle: string;
  data: DocumentListResponse | null;
  error: string | null;
  onCreate?: (event: FormEvent<HTMLFormElement>) => void;
  onCreateBodyChange?: (value: string) => void;
  onCreateStatusChange?: (value: string) => void;
  onCreateTagsChange?: (value: string) => void;
  onCreateTitleChange?: (value: string) => void;
  onOpenDocument?: (documentId: string) => void;
  onSearchChange?: (value: string) => void;
  onSearchClear?: () => void;
  onSearchSubmit?: () => void;
  onCloseDetail?: () => void;
  onRetry?: () => void;
  search: string;
  selected: DocumentDetail | null;
  selectedVersions: DocumentVersion[];
  status: PanelStatus;
};

export function DocumentsPanelView({
  createBody,
  createError,
  createMessage,
  createPending,
  createStatusValue,
  createTags,
  createTitle,
  data,
  error,
  onCreate,
  onCreateBodyChange,
  onCreateStatusChange,
  onCreateTagsChange,
  onCreateTitleChange,
  onOpenDocument,
  onSearchChange,
  onSearchClear,
  onSearchSubmit,
  onCloseDetail,
  onRetry,
  search,
  selected,
  selectedVersions,
  status
}: DocumentsPanelViewProps) {
  const documents = data?.documents ?? [];
  const publishedCount = documents.filter((doc) => doc.status === "published").length;
  const draftCount = documents.filter((doc) => doc.status === "draft").length;

  return (
    <section className="panel documents" aria-labelledby="documents-title">
      <div className="section-header">
        <div>
          <span className="eyebrow">{M.documents.eyebrow}</span>
          <h2 id="documents-title">{M.documents.title}</h2>
        </div>
        <span className="badge">{M.documents.badgeLocalOnly}</span>
      </div>

      {status === "loading" ? (
        <p className="state loading">{M.documents.loading}</p>
      ) : null}

      {status === "missing" ? (
        <p className="muted">{M.documents.noWorkspaceDescription}</p>
      ) : null}

      {status === "error" ? (
        <section className="state error">
          <strong>{M.documents.unavailableTitle}</strong>
          <p>{error ?? M.documents.unavailableDescription}</p>
          {onRetry ? (
            <button className="button secondary" onClick={onRetry} type="button">
              {M.common.retry}
            </button>
          ) : null}
        </section>
      ) : null}

      {data && status === "ready" ? (
        <>
          <section className="grid" aria-label={M.documents.summaryLabel}>
            <StatusCard
              description={M.documents.totalDescription}
              title={M.documents.totalTitle}
              value={String(data.count)}
            />
            <StatusCard
              description={M.documents.publishedDescription}
              title={M.documents.publishedTitle}
              value={String(publishedCount)}
            />
            <StatusCard
              description={M.documents.draftDescription}
              title={M.documents.draftTitle}
              value={String(draftCount)}
            />
          </section>

          <form
            className="stack"
            onSubmit={(event) => {
              event.preventDefault();
              onSearchSubmit?.();
            }}
          >
            <label htmlFor="documents-search">{M.documents.searchLabel}</label>
            <input
              id="documents-search"
              onChange={(event) => onSearchChange?.(event.target.value)}
              placeholder={M.documents.searchPlaceholder}
              value={search}
            />
            <div className="actions-row">
              <button className="button secondary" type="submit">
                {M.documents.searchSubmit}
              </button>
              <button
                className="button secondary"
                onClick={onSearchClear}
                type="button"
              >
                {M.documents.searchClear}
              </button>
            </div>
          </form>

          {documents.length === 0 ? (
            <section className="state empty">
              <strong>{M.documents.emptyTitle}</strong>
              <p>{M.documents.emptyDescription}</p>
            </section>
          ) : (
            <div className="work-list" aria-label={M.documents.listLabel}>
              {documents.map((document) => (
                <DocumentCard
                  document={document}
                  key={document.id}
                  onOpenDocument={onOpenDocument}
                />
              ))}
            </div>
          )}

          {selected ? (
            <DocumentDetailView
              document={selected}
              onCloseDetail={onCloseDetail}
              versions={selectedVersions}
            />
          ) : null}

          <DocumentCreateForm
            createBody={createBody}
            createError={createError}
            createMessage={createMessage}
            createPending={createPending}
            createStatusValue={createStatusValue}
            createTags={createTags}
            createTitle={createTitle}
            onCreate={onCreate}
            onCreateBodyChange={onCreateBodyChange}
            onCreateStatusChange={onCreateStatusChange}
            onCreateTagsChange={onCreateTagsChange}
            onCreateTitleChange={onCreateTitleChange}
          />

          <p className="muted">{M.documents.boundaryNote}</p>
        </>
      ) : null}
    </section>
  );
}

function DocumentCard({
  document,
  onOpenDocument
}: {
  document: DocumentSummary;
  onOpenDocument?: (documentId: string) => void;
}) {
  return (
    <article className="work-item">
      <div className="work-item-main">
        <span className="badge">{document.status}</span>
        <h3>{document.title}</h3>
      </div>
      {document.excerpt ? <p className="muted">{document.excerpt}</p> : null}
      <dl className="work-meta">
        <div>
          <dt>{M.documents.tagsLabel}</dt>
          <dd>{document.tags.length > 0 ? document.tags.join(", ") : M.common.none}</dd>
        </div>
        <div>
          <dt>{M.documents.updatedLabel}</dt>
          <dd>{document.updated_at}</dd>
        </div>
      </dl>
      <div className="actions-row">
        <button
          className="button secondary"
          onClick={() => onOpenDocument?.(document.id)}
          type="button"
        >
          {M.documents.openDocument}
        </button>
      </div>
    </article>
  );
}

function DocumentDetailView({
  document,
  onCloseDetail,
  versions
}: {
  document: DocumentDetail;
  onCloseDetail?: () => void;
  versions: DocumentVersion[];
}) {
  return (
    <section className="callout" aria-label={document.title}>
      <div className="section-header">
        <div>
          <span className="badge">{document.status}</span>
          <h3>{document.title}</h3>
        </div>
        <button className="button secondary" onClick={onCloseDetail} type="button">
          {M.documents.detailBackToList}
        </button>
      </div>
      <h4>{M.documents.detailBodyLabel}</h4>
      <pre className="document-body">{document.body_markdown}</pre>
      <h4>{M.documents.versionHistoryTitle}</h4>
      {versions.length === 0 ? (
        <p className="muted">{M.documents.versionHistoryEmpty}</p>
      ) : (
        <ol className="meta-list">
          {versions.map((version) => (
            <li key={version.id}>
              {M.documents.versionLabel(version.version_number)} · {version.title} ·{" "}
              {version.status} · {version.created_at}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

function DocumentCreateForm({
  createBody,
  createError,
  createMessage,
  createPending,
  createStatusValue,
  createTags,
  createTitle,
  onCreate,
  onCreateBodyChange,
  onCreateStatusChange,
  onCreateTagsChange,
  onCreateTitleChange
}: {
  createBody: string;
  createError: string | null;
  createMessage: string | null;
  createPending: boolean;
  createStatusValue: string;
  createTags: string;
  createTitle: string;
  onCreate?: (event: FormEvent<HTMLFormElement>) => void;
  onCreateBodyChange?: (value: string) => void;
  onCreateStatusChange?: (value: string) => void;
  onCreateTagsChange?: (value: string) => void;
  onCreateTitleChange?: (value: string) => void;
}) {
  return (
    <form className="stack" onSubmit={onCreate}>
      <h3>{M.documents.createTitle}</h3>
      <p className="muted">{M.documents.createDescription}</p>
      <label htmlFor="documents-create-title">{M.documents.fieldTitle}</label>
      <input
        id="documents-create-title"
        onChange={(event) => onCreateTitleChange?.(event.target.value)}
        placeholder={M.documents.fieldTitlePlaceholder}
        value={createTitle}
      />
      <label htmlFor="documents-create-body">{M.documents.fieldBody}</label>
      <textarea
        id="documents-create-body"
        onChange={(event) => onCreateBodyChange?.(event.target.value)}
        placeholder={M.documents.fieldBodyPlaceholder}
        rows={8}
        value={createBody}
      />
      <label htmlFor="documents-create-tags">{M.documents.fieldTags}</label>
      <input
        id="documents-create-tags"
        onChange={(event) => onCreateTagsChange?.(event.target.value)}
        placeholder={M.documents.fieldTagsPlaceholder}
        value={createTags}
      />
      <label htmlFor="documents-create-status">{M.documents.fieldStatus}</label>
      <select
        id="documents-create-status"
        onChange={(event) => onCreateStatusChange?.(event.target.value)}
        value={createStatusValue}
      >
        <option value="draft">{M.documents.statusDraft}</option>
        <option value="published">{M.documents.statusPublished}</option>
        <option value="archived">{M.documents.statusArchived}</option>
      </select>
      {createMessage ? <p className="state success">{createMessage}</p> : null}
      {createError ? <p className="state error">{createError}</p> : null}
      <button className="button" disabled={createPending} type="submit">
        {createPending ? M.documents.creating : M.documents.createSubmit}
      </button>
    </form>
  );
}

export function parseTags(value: string): string[] {
  const tags: string[] = [];
  for (const raw of value.split(",")) {
    const tag = raw.trim();
    if (tag && !tags.includes(tag)) {
      tags.push(tag);
    }
  }
  return tags;
}
