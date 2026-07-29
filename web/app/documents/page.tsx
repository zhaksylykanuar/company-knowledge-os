"use client";

import { type FormEvent, useCallback, useEffect, useState } from "react";

import { PageHeader } from "../../components/PageHeader";
import { StatusCard } from "../../components/StatusCard";
import {
  createDocument,
  deleteDocument,
  fetchDocument,
  fetchDocumentVersions,
  fetchDocuments,
  updateDocument
} from "../../lib/api";
import { M } from "../../lib/messages";
import { selectedWorkspaceRole, useSession } from "../../lib/session";
import type {
  DocumentDetail,
  DocumentListResponse,
  DocumentSummary,
  DocumentUpdateRequest,
  DocumentVersion
} from "../../lib/types";

type PanelStatus = "error" | "loading" | "missing" | "ready";

export default function DocumentsPage() {
  const session = useSession();
  const workspaceId = session?.workspaceId ?? null;
  const canWrite = canWriteDocuments(
    selectedWorkspaceRole(session?.workspaces ?? [], workspaceId)
  );
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
  const [detailError, setDetailError] = useState<string | null>(null);
  const [detailMessage, setDetailMessage] = useState<string | null>(null);
  const [detailPending, setDetailPending] = useState(false);

  useEffect(() => {
    void reloadKey;
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
      setDetailError(null);
      setDetailMessage(null);
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

  const handleUpdateDocument = useCallback(
    async (documentId: string, request: DocumentUpdateRequest) => {
      if (!workspaceId || detailPending) {
        return;
      }
      setDetailError(null);
      setDetailMessage(null);
      setDetailPending(true);
      try {
        const [payload, versions] = await Promise.all([
          updateDocument(workspaceId, documentId, request),
          fetchDocumentVersions(workspaceId, documentId)
        ]);
        setSelected(payload.document);
        setSelectedVersions(versions.versions);
        setDetailMessage(M.documents.updateSuccess);
        setReloadKey((current) => current + 1);
      } catch (caught: unknown) {
        setDetailError(
          caught instanceof Error ? caught.message : M.common.requestFailed
        );
      } finally {
        setDetailPending(false);
      }
    },
    [workspaceId, detailPending]
  );

  const handleDeleteDocument = useCallback(
    async (documentId: string) => {
      if (!workspaceId || detailPending) {
        return;
      }
      setDetailError(null);
      setDetailMessage(null);
      setDetailPending(true);
      try {
        await deleteDocument(workspaceId, documentId);
        setSelected(null);
        setSelectedVersions([]);
        setReloadKey((current) => current + 1);
      } catch (caught: unknown) {
        setDetailError(
          caught instanceof Error ? caught.message : M.common.requestFailed
        );
      } finally {
        setDetailPending(false);
      }
    },
    [workspaceId, detailPending]
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
        canWrite={canWrite}
        createBody={createBody}
        createError={createError}
        createMessage={createMessage}
        createPending={createPending}
        createStatusValue={createStatusValue}
        createTags={createTags}
        createTitle={createTitle}
        data={data}
        error={error}
        detailError={detailError}
        detailMessage={detailMessage}
        detailPending={detailPending}
        onCreate={canWrite ? handleCreate : undefined}
        onCreateBodyChange={setCreateBody}
        onCreateStatusChange={setCreateStatusValue}
        onCreateTagsChange={setCreateTags}
        onCreateTitleChange={setCreateTitle}
        onDeleteDocument={canWrite ? handleDeleteDocument : undefined}
        onUpdateDocument={canWrite ? handleUpdateDocument : undefined}
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
          setDetailError(null);
          setDetailMessage(null);
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
  canWrite: boolean;
  createBody: string;
  createError: string | null;
  createMessage: string | null;
  createPending: boolean;
  createStatusValue: string;
  createTags: string;
  createTitle: string;
  data: DocumentListResponse | null;
  error: string | null;
  detailError: string | null;
  detailMessage: string | null;
  detailPending: boolean;
  onCreate?: (event: FormEvent<HTMLFormElement>) => void;
  onCreateBodyChange?: (value: string) => void;
  onCreateStatusChange?: (value: string) => void;
  onCreateTagsChange?: (value: string) => void;
  onCreateTitleChange?: (value: string) => void;
  onDeleteDocument?: (documentId: string) => void;
  onUpdateDocument?: (documentId: string, request: DocumentUpdateRequest) => void;
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
  canWrite,
  createBody,
  createError,
  createMessage,
  createPending,
  createStatusValue,
  createTags,
  createTitle,
  data,
  error,
  detailError,
  detailMessage,
  detailPending,
  onCreate,
  onCreateBodyChange,
  onCreateStatusChange,
  onCreateTagsChange,
  onCreateTitleChange,
  onDeleteDocument,
  onUpdateDocument,
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
              <p>
                {canWrite
                  ? M.documents.emptyDescription
                  : M.documents.emptyReadOnlyDescription}
              </p>
            </section>
          ) : (
            <div
              aria-label={M.documents.listLabel}
              className="work-list"
              role="list"
            >
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
              detailError={detailError}
              detailMessage={detailMessage}
              detailPending={detailPending}
              onCloseDetail={onCloseDetail}
              onDeleteDocument={canWrite ? onDeleteDocument : undefined}
              onUpdateDocument={canWrite ? onUpdateDocument : undefined}
              versions={selectedVersions}
            />
          ) : null}

          {canWrite ? (
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
          ) : (
            <p className="callout muted">{M.documents.readOnlyNotice}</p>
          )}

          <p className="muted">{M.documents.boundaryNote}</p>
        </>
      ) : null}
    </section>
  );
}

export function canWriteDocuments(role: string | null): boolean {
  return role === "owner" || role === "admin" || role === "member";
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
  detailError,
  detailMessage,
  detailPending,
  onDeleteDocument,
  onUpdateDocument,
  versions
}: {
  document: DocumentDetail;
  onCloseDetail?: () => void;
  detailError?: string | null;
  detailMessage?: string | null;
  detailPending?: boolean;
  onDeleteDocument?: (documentId: string) => void;
  onUpdateDocument?: (documentId: string, request: DocumentUpdateRequest) => void;
  versions: DocumentVersion[];
}) {
  const [selectedVersionId, setSelectedVersionId] = useState<string | null>(null);
  const selectedVersion =
    versions.find((version) => version.id === selectedVersionId) ?? versions[0] ?? null;
  const [editing, setEditing] = useState(false);
  const [editTitle, setEditTitle] = useState(document.title);
  const [editBody, setEditBody] = useState(document.body_markdown);
  const [editTags, setEditTags] = useState((document.tags ?? []).join(", "));
  const [editStatus, setEditStatus] = useState(document.status);
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  useEffect(() => {
    setEditing(false);
    setConfirmingDelete(false);
    setEditTitle(document.title);
    setEditBody(document.body_markdown);
    setEditTags((document.tags ?? []).join(", "));
    setEditStatus(document.status);
  }, [document]);

  return (
    <section className="callout" aria-label={document.title}>
      <div className="section-header">
        <div>
          <span className="badge">{document.status}</span>
          <h3>{document.title}</h3>
        </div>
        <div className="actions-row">
          {onUpdateDocument && !editing ? (
            <button
              className="button secondary"
              onClick={() => setEditing(true)}
              type="button"
            >
              {M.documents.editDocument}
            </button>
          ) : null}
          <button className="button secondary" onClick={onCloseDetail} type="button">
            {M.documents.detailBackToList}
          </button>
        </div>
      </div>

      {editing && onUpdateDocument ? (
        <form
          className="stack"
          onSubmit={(event) => {
            event.preventDefault();
            onUpdateDocument(document.id, {
              title: editTitle.trim(),
              body_markdown: editBody,
              tags: parseTags(editTags),
              status: editStatus
            });
          }}
        >
          <h4>{M.documents.editTitle}</h4>
          <label htmlFor="documents-edit-title">{M.documents.fieldTitle}</label>
          <input
            id="documents-edit-title"
            onChange={(event) => setEditTitle(event.target.value)}
            value={editTitle}
          />
          <label htmlFor="documents-edit-body">{M.documents.fieldBody}</label>
          <textarea
            id="documents-edit-body"
            onChange={(event) => setEditBody(event.target.value)}
            rows={8}
            value={editBody}
          />
          <label htmlFor="documents-edit-tags">{M.documents.fieldTags}</label>
          <input
            id="documents-edit-tags"
            onChange={(event) => setEditTags(event.target.value)}
            value={editTags}
          />
          <label htmlFor="documents-edit-status">{M.documents.fieldStatus}</label>
          <select
            id="documents-edit-status"
            onChange={(event) => setEditStatus(event.target.value)}
            value={editStatus}
          >
            <option value="draft">{M.documents.statusDraft}</option>
            <option value="published">{M.documents.statusPublished}</option>
            <option value="archived">{M.documents.statusArchived}</option>
          </select>
          {detailMessage ? <p className="state success">{detailMessage}</p> : null}
          {detailError ? <p className="state error">{detailError}</p> : null}
          <div className="actions-row">
            <button className="button" disabled={detailPending} type="submit">
              {detailPending ? M.documents.saving : M.documents.saveChanges}
            </button>
            <button
              className="button secondary"
              onClick={() => setEditing(false)}
              type="button"
            >
              {M.documents.cancelEdit}
            </button>
          </div>
        </form>
      ) : null}

      <h4>{M.documents.detailBodyLabel}</h4>
      <pre className="document-body">{document.body_markdown}</pre>

      {!editing && detailMessage ? (
        <p className="state success">{detailMessage}</p>
      ) : null}
      {!editing && detailError ? (
        <p className="state error">{detailError}</p>
      ) : null}

      {onDeleteDocument ? (
        <div className="actions-row">
          {confirmingDelete ? (
            <>
              <span className="muted">{M.documents.deleteConfirm}</span>
              <button
                className="button secondary"
                disabled={detailPending}
                onClick={() => onDeleteDocument(document.id)}
                type="button"
              >
                {detailPending
                  ? M.documents.deleting
                  : M.documents.deleteConfirmYes}
              </button>
              <button
                className="button secondary"
                onClick={() => setConfirmingDelete(false)}
                type="button"
              >
                {M.documents.cancelEdit}
              </button>
            </>
          ) : (
            <button
              className="button secondary"
              onClick={() => setConfirmingDelete(true)}
              type="button"
            >
              {M.documents.deleteDocument}
            </button>
          )}
        </div>
      ) : null}

      <h4>{M.documents.versionHistoryTitle}</h4>
      {versions.length === 0 ? (
        <p className="muted">{M.documents.versionHistoryEmpty}</p>
      ) : (
        <>
          <ol className="meta-list">
            {versions.map((version) => (
              <li key={version.id}>
                <button
                  className="button secondary"
                  disabled={selectedVersion?.id === version.id}
                  onClick={() => setSelectedVersionId(version.id)}
                  type="button"
                >
                  {M.documents.viewVersion}
                </button>{" "}
                {M.documents.versionLabel(version.version_number)} · {version.title} ·{" "}
                {version.status} · {version.created_at}
                {selectedVersion?.id === version.id ? (
                  <> · {M.documents.selectedVersionBadge}</>
                ) : null}
              </li>
            ))}
          </ol>
          {selectedVersion ? <DocumentVersionSnapshot version={selectedVersion} /> : null}
        </>
      )}
    </section>
  );
}

function DocumentVersionSnapshot({ version }: { version: DocumentVersion }) {
  return (
    <section className="callout" aria-label={M.documents.versionSnapshotTitle}>
      <div className="section-header">
        <div>
          <span className="badge">{version.status}</span>
          <h4>
            {M.documents.versionSnapshotTitle}: {M.documents.versionLabel(version.version_number)}
          </h4>
        </div>
      </div>
      <dl className="work-meta">
        <div>
          <dt>{M.documents.statusLabel}</dt>
          <dd>{version.status}</dd>
        </div>
        <div>
          <dt>{M.documents.tagsLabel}</dt>
          <dd>{version.tags.length > 0 ? version.tags.join(", ") : M.common.none}</dd>
        </div>
        <div>
          <dt>{M.documents.versionCreatedLabel}</dt>
          <dd>{version.created_at}</dd>
        </div>
      </dl>
      <h5>{M.documents.versionSnapshotBodyLabel}</h5>
      <pre className="document-body">{version.body_markdown}</pre>
      <p className="muted">{M.documents.versionSnapshotBoundary}</p>
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
