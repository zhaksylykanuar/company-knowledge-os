"use client";

import Link from "next/link";
import type { FormEvent } from "react";
import { useCallback, useEffect, useState } from "react";

import { PageHeader } from "../../../components/PageHeader";
import {
  correctDocumentMemory,
  fetchDocument,
  fetchDocumentMemoryPreview,
  fetchDocuments,
  forgetDocumentMemory
} from "../../../lib/api";
import { useSession } from "../../../lib/session";
import type {
  DocumentDetail,
  DocumentMemoryPreview,
  DocumentSummary
} from "../../../lib/types";
import styles from "./memory-settings.module.css";

type PageStatus = "error" | "loading" | "missing" | "ready";

export default function MemorySettingsPage() {
  const session = useSession();
  const workspaceId = session?.workspaceId ?? null;
  const workspace = session?.workspaces.find((item) => item.id === workspaceId) ?? null;
  const canManage = workspace?.role === "owner" || workspace?.role === "admin";
  const [status, setStatus] = useState<PageStatus>("loading");
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [selected, setSelected] = useState<DocumentDetail | null>(null);
  const [preview, setPreview] = useState<DocumentMemoryPreview | null>(null);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [tags, setTags] = useState("");
  const [documentStatus, setDocumentStatus] = useState("draft");
  const [pending, setPending] = useState<"correct" | "forget" | "open" | null>(null);
  const [correctionArmed, setCorrectionArmed] = useState(false);
  const [forgetArmed, setForgetArmed] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  const load = useCallback(async () => {
    if (!workspaceId) {
      setStatus("missing");
      setDocuments([]);
      return;
    }
    setStatus("loading");
    setError(null);
    try {
      const response = await fetchDocuments(workspaceId, { limit: 200 });
      setDocuments(response.documents);
      setStatus("ready");
    } catch {
      setStatus("error");
      setError("Не удалось загрузить память компании.");
    }
  }, [workspaceId]);

  useEffect(() => {
    void reloadKey;
    void load();
  }, [load, reloadKey]);

  async function openDocument(documentId: string) {
    if (!workspaceId || pending) return;
    setPending("open");
    setError(null);
    setMessage(null);
    setCorrectionArmed(false);
    setForgetArmed(false);
    try {
      const [documentResponse, memoryPreview] = await Promise.all([
        fetchDocument(workspaceId, documentId),
        fetchDocumentMemoryPreview(workspaceId, documentId)
      ]);
      const document = documentResponse.document;
      setSelected(document);
      setPreview(memoryPreview);
      setTitle(document.title);
      setBody(document.body_markdown);
      setTags(document.tags.join(", "));
      setDocumentStatus(document.status);
    } catch {
      setError("Не удалось открыть выбранную запись памяти.");
    } finally {
      setPending(null);
    }
  }

  async function correctMemory(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspaceId || !selected || !preview || !canManage || pending) return;
    if (!correctionArmed) {
      setCorrectionArmed(true);
      setForgetArmed(false);
      return;
    }
    setPending("correct");
    setError(null);
    setMessage(null);
    try {
      const response = await correctDocumentMemory(workspaceId, selected.id, {
        title: title.trim(),
        body_markdown: body,
        tags: parseMemoryTags(tags),
        status: documentStatus,
        expected_updated_at: preview.updated_at,
        expected_version_count: preview.version_count,
        confirmation: "purge_document_history"
      });
      const refreshedPreview = await fetchDocumentMemoryPreview(
        workspaceId,
        selected.id
      );
      setSelected(response.document);
      setPreview(refreshedPreview);
      setTitle(response.document.title);
      setBody(response.document.body_markdown);
      setTags(response.document.tags.join(", "));
      setCorrectionArmed(false);
      setMessage(
        `Исправлено. Удалено старых версий: ${response.prior_versions_deleted}.`
      );
      setReloadKey((value) => value + 1);
    } catch {
      setError("Запись изменилась или исправление не применилось. Откройте её заново.");
    } finally {
      setPending(null);
    }
  }

  async function forgetMemory() {
    if (!workspaceId || !selected || !preview || !canManage || pending) return;
    if (!forgetArmed) {
      setForgetArmed(true);
      setCorrectionArmed(false);
      return;
    }
    setPending("forget");
    setError(null);
    setMessage(null);
    try {
      const receipt = await forgetDocumentMemory(workspaceId, selected.id, {
        expected_updated_at: preview.updated_at,
        expected_version_count: preview.version_count,
        confirmation: "forget_document"
      });
      setSelected(null);
      setPreview(null);
      setTitle("");
      setBody("");
      setTags("");
      setForgetArmed(false);
      setMessage(
        `Удалено из активной памяти: документ и ${receipt.versions_deleted} версий.`
      );
      setReloadKey((value) => value + 1);
    } catch {
      setError("Запись изменилась или удаление не применилось. Откройте её заново.");
    } finally {
      setPending(null);
    }
  }

  return (
    <>
      <Link className="onboarding-return" href="/settings">
        <span aria-hidden="true">←</span>
        Все настройки
      </Link>
      <PageHeader
        eyebrow="Настройки · Память"
        title="Что FounderOS помнит"
        description="Исправляйте локальную память и удаляйте ненужное без скрытого архива старого текста."
      />

      <div className={styles.layout}>
        <section className={styles.scope}>
          <div>
            <span>Активная память FounderOS</span>
            <strong>{documents.length} внутренних документов</strong>
          </div>
          <div>
            <span>Внешние источники</span>
            <strong>Только через источник</strong>
          </div>
          <div>
            <span>История чата</span>
            <strong>Не сохраняется</strong>
          </div>
        </section>

        <section className={styles.notice}>
          <strong>Честная граница удаления</strong>
          <p>
            Операция ниже удаляет данные из активной PostgreSQL-базы FounderOS.
            Зашифрованные резервные копии могут хранить их до окончания настроенной
            ротации. Данные в GitHub, Jira, Gmail или Drive здесь не удаляются.
          </p>
        </section>

        {status === "loading" ? <p className="state loading">Загружаю…</p> : null}
        {status === "missing" ? <p className="state">Сначала выберите компанию.</p> : null}
        {status === "error" ? (
          <section className="state error">
            <p>{error}</p>
            <button className="button secondary" onClick={() => void load()} type="button">
              Повторить
            </button>
          </section>
        ) : null}

        {status === "ready" ? (
          <section className={styles.workspace}>
            <div className={styles.list}>
              <header>
                <span>Локальная память</span>
                <h2>Внутренние документы</h2>
              </header>
              {documents.length === 0 ? (
                <p className={styles.empty}>Внутренних документов пока нет.</p>
              ) : (
                documents.map((document) => (
                  <button
                    className={
                      selected?.id === document.id
                        ? `${styles.document} ${styles.active}`
                        : styles.document
                    }
                    disabled={pending !== null}
                    key={document.id}
                    onClick={() => void openDocument(document.id)}
                    type="button"
                  >
                    <span>{document.status}</span>
                    <strong>{document.title}</strong>
                    <small>{memoryDate(document.updated_at)}</small>
                  </button>
                ))
              )}
            </div>

            <div className={styles.detail}>
              {selected && preview ? (
                <>
                  <header>
                    <div>
                      <span>Точный preview</span>
                      <h2>{selected.title}</h2>
                    </div>
                    <strong>{preview.version_count} версий</strong>
                  </header>

                  <form className={styles.form} onSubmit={correctMemory}>
                    <label>
                      <span>Название</span>
                      <input
                        disabled={!canManage || pending !== null}
                        onChange={(event) => setTitle(event.target.value)}
                        value={title}
                      />
                    </label>
                    <label>
                      <span>Исправленный текст</span>
                      <textarea
                        disabled={!canManage || pending !== null}
                        onChange={(event) => setBody(event.target.value)}
                        rows={8}
                        value={body}
                      />
                    </label>
                    <div className={styles.twoColumns}>
                      <label>
                        <span>Теги</span>
                        <input
                          disabled={!canManage || pending !== null}
                          onChange={(event) => setTags(event.target.value)}
                          value={tags}
                        />
                      </label>
                      <label>
                        <span>Статус</span>
                        <select
                          disabled={!canManage || pending !== null}
                          onChange={(event) => setDocumentStatus(event.target.value)}
                          value={documentStatus}
                        >
                          <option value="draft">Черновик</option>
                          <option value="published">Опубликован</option>
                          <option value="archived">Архив</option>
                        </select>
                      </label>
                    </div>
                    <p className={styles.effect}>
                      Исправление заменит активный документ, удалит все{" "}
                      {preview.version_count} старых версий и оставит одну новую.
                    </p>
                    <div className={styles.actions}>
                      <button
                        className={correctionArmed ? "button danger" : "button"}
                        disabled={!canManage || pending !== null || !title.trim()}
                        type="submit"
                      >
                        {pending === "correct"
                          ? "Исправляю…"
                          : correctionArmed
                            ? "Подтвердить исправление"
                            : "Исправить и забыть старое"}
                      </button>
                      {correctionArmed ? (
                        <button
                          className="button secondary"
                          onClick={() => setCorrectionArmed(false)}
                          type="button"
                        >
                          Отмена
                        </button>
                      ) : null}
                    </div>
                  </form>

                  <section className={styles.forget}>
                    <div>
                      <strong>Забыть документ полностью</strong>
                      <p>
                        Из активной базы будут удалены документ и все{" "}
                        {preview.version_count} версий.
                      </p>
                    </div>
                    <div className={styles.actions}>
                      <button
                        className="button danger"
                        disabled={!canManage || pending !== null}
                        onClick={() => void forgetMemory()}
                        type="button"
                      >
                        {pending === "forget"
                          ? "Удаляю…"
                          : forgetArmed
                            ? "Подтвердить удаление"
                            : "Забыть документ"}
                      </button>
                      {forgetArmed ? (
                        <button
                          className="button secondary"
                          onClick={() => setForgetArmed(false)}
                          type="button"
                        >
                          Отмена
                        </button>
                      ) : null}
                    </div>
                  </section>
                </>
              ) : (
                <p className={styles.empty}>
                  Выберите документ, чтобы увидеть точный объём исправления или удаления.
                </p>
              )}
            </div>
          </section>
        ) : null}

        {message ? <p className="success-text">{message}</p> : null}
        {error && status === "ready" ? <p className="error-text">{error}</p> : null}
        {!canManage && status === "ready" ? (
          <p className={styles.readOnly}>
            Просмотр доступен, но исправление и удаление выполняет только владелец
            или администратор компании.
          </p>
        ) : null}

        <section className={styles.external}>
          <span>Provider memory</span>
          <h2>GitHub, Jira, Gmail и Drive</h2>
          <p>
            FounderOS не показывает ложную кнопку «удалено»: исходные данные остаются
            у провайдера, а canonical evidence связано с решениями. Управляемое
            каскадное забывание внешней записи ещё заблокировано до отдельного
            evidence-safe контракта.
          </p>
        </section>
      </div>
    </>
  );
}

export function parseMemoryTags(value: string): string[] {
  return Array.from(
    new Set(value.split(",").map((tag) => tag.trim()).filter(Boolean))
  ).slice(0, 25);
}

export function memoryDate(value: string): string {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? "время неизвестно"
    : parsed.toLocaleString("ru-RU");
}
