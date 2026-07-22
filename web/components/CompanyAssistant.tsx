"use client";

import Link from "next/link";
import type {
  FormEvent,
  RefObject
} from "react";
import { useEffect, useRef, useState } from "react";

import {
  ASSISTANT_QUERY_MAX_CHARS,
  AssistantContractError,
  isSafeAssistantActionTarget,
  type AssistantQueryResponse
} from "../lib/assistant";
import {
  assistantSnapshotForWorkspace,
  type AssistantSnapshotSource
} from "../lib/assistant-snapshot";
import {
  ApiRequestError,
  fetchHeadquarters,
  queryWorkspaceAssistant
} from "../lib/api";
import type { HeadquartersEvidenceRef, HeadquartersSnapshotResponse } from "../lib/headquarters";
import { safeHref } from "../lib/safeHref";
import { OverlayShell } from "./OverlayShell";
import styles from "./company-assistant.module.css";

export type CompanyAssistantStatus =
  | "answer"
  | "error"
  | "loading_snapshot"
  | "querying"
  | "rate_limited"
  | "ready"
  | "stale";

export function canOpenCompanyAssistantShortcut({
  disabled,
  hasOpenDialog,
  target
}: {
  disabled: boolean;
  hasOpenDialog: boolean;
  target: EventTarget | null;
}): boolean {
  return !disabled && !hasOpenDialog && !isEditableTarget(target);
}

export function companyAssistantErrorStatus(error: unknown): CompanyAssistantStatus {
  if (error instanceof ApiRequestError && error.status === 409) return "stale";
  if (error instanceof ApiRequestError && error.status === 429) return "rate_limited";
  return "error";
}

export function CompanyAssistant({
  backgroundRef,
  disabled,
  snapshotSource,
  workspaceId
}: {
  backgroundRef: RefObject<HTMLElement | null>;
  disabled: boolean;
  snapshotSource: AssistantSnapshotSource | null;
  workspaceId: string | null;
}) {
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState<CompanyAssistantStatus>("ready");
  const [snapshot, setSnapshot] = useState<HeadquartersSnapshotResponse | null>(null);
  const [query, setQuery] = useState("");
  const [answer, setAnswer] = useState<AssistantQueryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const requestRef = useRef<AbortController | null>(null);

  useEffect(() => {
    requestRef.current?.abort();
    setOpen(false);
    setSnapshot(null);
    setQuery("");
    setAnswer(null);
    setError(null);
    setStatus("ready");
  }, [workspaceId]);

  useEffect(() => {
    const visibleSnapshot = assistantSnapshotForWorkspace(snapshotSource, workspaceId);
    if (!open || !visibleSnapshot) return;
    setSnapshot(visibleSnapshot);
    setAnswer((current) => {
      if (current && current.snapshot_id !== visibleSnapshot.snapshot.id) {
        setStatus("stale");
        setError("Штаб изменился. Повторите вопрос по обновлённому снимку.");
        return null;
      }
      return current;
    });
  }, [open, snapshotSource, workspaceId]);

  useEffect(() => {
    function onShortcut(event: KeyboardEvent) {
      if (
        !(event.metaKey || event.ctrlKey) ||
        event.key.toLowerCase() !== "k" ||
        !canOpenCompanyAssistantShortcut({
          disabled: disabled || workspaceId === null || open,
          hasOpenDialog: document.querySelector("[role='dialog'][aria-modal='true']") !== null,
          target: event.target
        })
      ) {
        return;
      }
      event.preventDefault();
      void openAssistant();
    }
    window.addEventListener("keydown", onShortcut);
    return () => window.removeEventListener("keydown", onShortcut);
  }, [disabled, open, snapshotSource, workspaceId]);

  async function loadSnapshot(signal: AbortSignal): Promise<HeadquartersSnapshotResponse> {
    if (!workspaceId) throw new Error("Компания не выбрана.");
    const visibleSnapshot = assistantSnapshotForWorkspace(snapshotSource, workspaceId);
    if (visibleSnapshot) return visibleSnapshot;
    return fetchHeadquarters(workspaceId, { signal });
  }

  async function openAssistant() {
    if (disabled || !workspaceId || open) return;
    requestRef.current?.abort();
    const controller = new AbortController();
    requestRef.current = controller;
    setOpen(true);
    setStatus("loading_snapshot");
    setSnapshot(null);
    setAnswer(null);
    setError(null);
    setQuery("");
    try {
      const loaded = await loadSnapshot(controller.signal);
      if (controller.signal.aborted) return;
      setSnapshot(loaded);
      setStatus("ready");
    } catch (caught: unknown) {
      if (controller.signal.aborted) return;
      setStatus("error");
      setError(assistantErrorMessage(caught));
    }
  }

  function closeAssistant() {
    requestRef.current?.abort();
    requestRef.current = null;
    setOpen(false);
    setSnapshot(null);
    setQuery("");
    setAnswer(null);
    setError(null);
    setStatus("ready");
  }

  async function submitAssistantQuery(rawQuery: string) {
    const trimmed = rawQuery.trim();
    if (!workspaceId || !trimmed || trimmed.length > ASSISTANT_QUERY_MAX_CHARS) return;

    requestRef.current?.abort();
    const controller = new AbortController();
    requestRef.current = controller;
    setAnswer(null);
    setError(null);
    setStatus("querying");

    try {
      const baseSnapshot =
        assistantSnapshotForWorkspace(snapshotSource, workspaceId) ??
        snapshot ??
        (await loadSnapshot(controller.signal));
      setSnapshot(baseSnapshot);
      const result = await queryWorkspaceAssistant(
        workspaceId,
        {
          query: trimmed,
          expected_snapshot_id: baseSnapshot.snapshot.id
        },
        { signal: controller.signal }
      );
      if (controller.signal.aborted) return;
      if (result.snapshot_id !== baseSnapshot.snapshot.id) {
        throw new AssistantContractError("assistant snapshot does not match the request");
      }
      setAnswer(result);
      setStatus("answer");
    } catch (caught: unknown) {
      if (controller.signal.aborted) return;
      const nextStatus = companyAssistantErrorStatus(caught);
      setStatus(nextStatus);
      setAnswer(null);
      if (nextStatus === "stale") {
        setError("Штаб изменился. Обновляю снимок — повторите вопрос после обновления.");
        try {
          const refreshed =
            snapshotSource?.workspaceId === workspaceId
              ? await snapshotSource.refresh()
              : await fetchHeadquarters(workspaceId, { signal: controller.signal });
          if (!controller.signal.aborted) setSnapshot(refreshed);
        } catch {
          if (!controller.signal.aborted) {
            setError("Штаб изменился, но обновить снимок не удалось. Закройте ассистента и повторите позже.");
          }
        }
      } else if (nextStatus === "rate_limited") {
        setError("Слишком много вопросов подряд. Подождите немного и повторите запрос.");
      } else {
        setError(assistantErrorMessage(caught));
      }
    }
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void submitAssistantQuery(query);
  }

  return (
    <>
      <button
        aria-haspopup="dialog"
        aria-keyshortcuts="Meta+K Control+K"
        className={styles.launcher}
        disabled={disabled || workspaceId === null}
        onClick={() => void openAssistant()}
        type="button"
      >
        <span aria-hidden="true">✦</span>
        <span>Спросить</span>
        <kbd>⌘K</kbd>
      </button>
      {open ? (
        <OverlayShell
          backgroundRef={backgroundRef}
          label="Спросить FounderOS"
          mode="drawer"
          onClose={closeAssistant}
        >
          <CompanyAssistantPanel
            answer={answer}
            error={error}
            onAction={closeAssistant}
            onQueryChange={setQuery}
            onSubmit={onSubmit}
            onSuggestion={(suggestion) => {
              setQuery(suggestion);
              void submitAssistantQuery(suggestion);
            }}
            query={query}
            status={status}
          />
        </OverlayShell>
      ) : null}
    </>
  );
}

export function CompanyAssistantPanel({
  answer,
  error,
  onAction,
  onQueryChange,
  onSubmit,
  onSuggestion,
  query,
  status
}: {
  answer: AssistantQueryResponse | null;
  error: string | null;
  onAction: () => void;
  onQueryChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onSuggestion: (query: string) => void;
  query: string;
  status: CompanyAssistantStatus;
}) {
  const pending = status === "loading_snapshot" || status === "querying";
  return (
    <div className={styles.panel}>
      <div className={styles.intro}>
        <span className={styles.symbol} aria-hidden="true">✦</span>
        <div>
          <strong>Ответ только по текущей компании</strong>
          <p>Без LLM, провайдеров и действий. Каждый факт ведёт к проверяемому основанию.</p>
        </div>
      </div>

      <form className={styles.form} onSubmit={onSubmit}>
        <label htmlFor="company-assistant-query">Вопрос о текущем снимке</label>
        <textarea
          disabled={pending}
          id="company-assistant-query"
          maxLength={ASSISTANT_QUERY_MAX_CHARS}
          onChange={(event) => onQueryChange(event.target.value)}
          placeholder="Например: почему этот ход главный?"
          rows={3}
          value={query}
        />
        <div className={styles.formFooter}>
          <small>{query.length}/{ASSISTANT_QUERY_MAX_CHARS}</small>
          <button disabled={pending || query.trim().length === 0} type="submit">
            {status === "querying" ? "Проверяю…" : "Спросить"}
          </button>
        </div>
      </form>

      <div aria-live="polite" className={styles.result}>
        {status === "loading_snapshot" ? <p>Сверяю текущий снимок штаба…</p> : null}
        {error ? <p className={styles.error}>{error}</p> : null}
        {answer ? (
          <article className={styles.answer}>
            <span>{intentLabel(answer.intent)}</span>
            <p>{answer.text}</p>
            {answer.citations.length > 0 ? (
              <div className={styles.citations}>
                <strong>Основания</strong>
                <ul>
                  {answer.citations.map((citation) => (
                    <li key={citation.id}>
                      <AssistantCitation citation={citation} onNavigate={onAction} />
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
            {answer.action?.target && isSafeAssistantActionTarget(answer.action.target) ? (
              <Link className={styles.action} href={answer.action.target} onClick={onAction}>
                {answer.action.label}
              </Link>
            ) : null}
            {answer.warnings.length > 0 ? (
              <details className={styles.warnings}>
                <summary>Ограничения снимка ({answer.warnings.length})</summary>
                <ul>
                  {answer.warnings.map((warning) => <li key={warning}>{warning}</li>)}
                </ul>
              </details>
            ) : null}
            <small className={styles.boundary}>
              Снимок {shortSnapshotId(answer.snapshot_id)} · LLM не использовался · действий не выполнено
            </small>
          </article>
        ) : null}
      </div>

      <div className={styles.suggestions} aria-label="Безопасные вопросы">
        {(answer?.suggestions ?? defaultSuggestions()).map((suggestion) => (
          <button
            disabled={pending}
            key={suggestion.id}
            onClick={() => onSuggestion(suggestion.query)}
            type="button"
          >
            {suggestion.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function AssistantCitation({
  citation,
  onNavigate
}: {
  citation: HeadquartersEvidenceRef;
  onNavigate: () => void;
}) {
  const target = citation.target;
  const label = `${citation.label} · ${citation.trust === "verified" ? "проверено" : "агрегат"}`;
  if (isSafeAssistantActionTarget(target)) {
    return <Link href={target} onClick={onNavigate}>{label}</Link>;
  }
  const external = safeHref(target);
  if (external) {
    return <a href={external} rel="noreferrer" target="_blank">{label}</a>;
  }
  return <span>{label}</span>;
}

function assistantErrorMessage(error: unknown): string {
  if (error instanceof AssistantContractError) {
    return "Ответ не прошёл безопасную проверку и поэтому не показан.";
  }
  if (error instanceof ApiRequestError && error.status === 403) {
    return "Для этого вопроса недостаточно прав в текущей компании.";
  }
  if (error instanceof ApiRequestError && error.status === 404) {
    return "Компания больше недоступна. Обновите выбранную компанию.";
  }
  return "Не удалось получить подтверждённый ответ. Повторите попытку позже.";
}

function defaultSuggestions() {
  return [
    { id: "priority", label: "Какой сейчас главный приоритет?", query: "Какой сейчас главный приоритет?" },
    { id: "why", label: "Почему этот ход главный?", query: "Почему этот ход главный?" },
    { id: "sources", label: "Что с источниками?", query: "Что с источниками?" },
    { id: "decisions", label: "Какие решения ждут?", query: "Какие решения ждут?" }
  ];
}

function intentLabel(intent: AssistantQueryResponse["intent"]): string {
  const labels: Record<AssistantQueryResponse["intent"], string> = {
    action_request: "Нужно подтверждение",
    briefing: "Брифинги",
    company_person: "Компания и люди",
    current_priority: "Текущий приоритет",
    decision_status: "Статус решения",
    evidence: "Основания",
    owners: "Ответственные",
    sources: "Радары",
    unsupported: "Безопасная граница",
    waiting_decisions: "Решения",
    why_now: "Почему сейчас"
  };
  return labels[intent];
}

function shortSnapshotId(value: string): string {
  return `${value.slice(0, 10)}…${value.slice(-6)}`;
}

function isEditableTarget(target: EventTarget | null): boolean {
  if (typeof HTMLElement === "undefined" || !(target instanceof HTMLElement)) return false;
  return (
    target.isContentEditable ||
    target instanceof HTMLInputElement ||
    target instanceof HTMLTextAreaElement ||
    target instanceof HTMLSelectElement
  );
}
