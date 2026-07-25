"use client";

import Link from "next/link";
import type {
  FormEvent,
  RefObject
} from "react";
import { useCallback, useEffect, useRef, useState } from "react";

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
import { useSession } from "../lib/session";
import { OverlayShell } from "./OverlayShell";
import styles from "./company-assistant.module.css";

export const OPEN_COMPANY_ASSISTANT_EVENT = "founderos:open-assistant";

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

function useCompanyAssistantConversation({
  active,
  snapshotSource,
  workspaceId
}: {
  active: boolean;
  snapshotSource: AssistantSnapshotSource | null;
  workspaceId: string | null;
}) {
  const [status, setStatus] = useState<CompanyAssistantStatus>("ready");
  const [snapshot, setSnapshot] = useState<HeadquartersSnapshotResponse | null>(null);
  const [query, setQuery] = useState("");
  const [answer, setAnswer] = useState<AssistantQueryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const requestRef = useRef<AbortController | null>(null);

  const reset = useCallback(() => {
    requestRef.current?.abort();
    requestRef.current = null;
    setSnapshot(null);
    setQuery("");
    setAnswer(null);
    setError(null);
    setStatus("ready");
  }, []);

  useEffect(() => {
    reset();
  }, [reset, workspaceId]);

  useEffect(() => () => requestRef.current?.abort(), []);

  useEffect(() => {
    const visibleSnapshot = assistantSnapshotForWorkspace(snapshotSource, workspaceId);
    if (!active || !visibleSnapshot) return;
    setSnapshot(visibleSnapshot);
    setAnswer((current) => {
      if (current && current.snapshot_id !== visibleSnapshot.snapshot.id) {
        setStatus("stale");
        setError("Картина компании изменилась. Повторите вопрос по новому снимку.");
        return null;
      }
      return current;
    });
  }, [active, snapshotSource, workspaceId]);

  const loadSnapshot = useCallback(
    async (signal: AbortSignal): Promise<HeadquartersSnapshotResponse> => {
      if (!workspaceId) throw new Error("Компания не выбрана.");
      const visibleSnapshot = assistantSnapshotForWorkspace(snapshotSource, workspaceId);
      if (visibleSnapshot) return visibleSnapshot;
      return fetchHeadquarters(workspaceId, { signal });
    },
    [snapshotSource, workspaceId]
  );

  const prepare = useCallback(async () => {
    if (!workspaceId) return;
    requestRef.current?.abort();
    const controller = new AbortController();
    requestRef.current = controller;
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
  }, [loadSnapshot, workspaceId]);

  const submit = useCallback(
    async (rawQuery: string) => {
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
          setError("Картина компании изменилась. Обновляю её — затем повторите вопрос.");
          try {
            const refreshed =
              snapshotSource?.workspaceId === workspaceId
                ? await snapshotSource.refresh()
                : await fetchHeadquarters(workspaceId, { signal: controller.signal });
            if (!controller.signal.aborted) setSnapshot(refreshed);
          } catch {
            if (!controller.signal.aborted) {
              setError("Картина изменилась, но обновить её не удалось. Повторите позже.");
            }
          }
        } else if (nextStatus === "rate_limited") {
          setError("Слишком много вопросов подряд. Подождите немного и повторите.");
        } else {
          setError(assistantErrorMessage(caught));
        }
      }
    },
    [loadSnapshot, snapshot, snapshotSource, workspaceId]
  );

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void submit(query);
  }

  return {
    answer,
    error,
    onSubmit,
    prepare,
    query,
    reset,
    setQuery,
    status,
    submit
  };
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
  const conversation = useCompanyAssistantConversation({
    active: open,
    snapshotSource,
    workspaceId
  });

  useEffect(() => {
    setOpen(false);
  }, [workspaceId]);

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
    function onOpenRequest() {
      void openAssistant();
    }
    window.addEventListener("keydown", onShortcut);
    window.addEventListener(OPEN_COMPANY_ASSISTANT_EVENT, onOpenRequest);
    return () => {
      window.removeEventListener("keydown", onShortcut);
      window.removeEventListener(OPEN_COMPANY_ASSISTANT_EVENT, onOpenRequest);
    };
  }, [conversation.prepare, disabled, open, workspaceId]);

  async function openAssistant() {
    if (disabled || !workspaceId || open) return;
    setOpen(true);
    await conversation.prepare();
  }

  function closeAssistant() {
    setOpen(false);
    conversation.reset();
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
            answer={conversation.answer}
            error={conversation.error}
            onAction={closeAssistant}
            onQueryChange={conversation.setQuery}
            onSubmit={conversation.onSubmit}
            onSuggestion={(suggestion) => {
              conversation.setQuery(suggestion);
              void conversation.submit(suggestion);
            }}
            query={conversation.query}
            status={conversation.status}
          />
        </OverlayShell>
      ) : null}
    </>
  );
}

export function CompanyAssistantWorkspace() {
  const session = useSession();
  const workspaceId = session?.workspaceId ?? null;
  const conversation = useCompanyAssistantConversation({
    active: true,
    snapshotSource: null,
    workspaceId
  });

  useEffect(() => {
    void conversation.prepare();
  }, [conversation.prepare]);

  return (
    <section className={styles.workspace} aria-labelledby="ask-founder-title">
      <header className={styles.workspaceHeader}>
        <span aria-hidden="true">✦</span>
        <div>
          <p>Ваше второе мнение</p>
          <h1 id="ask-founder-title">Спросить FounderOS</h1>
          <span>
            Задайте вопрос о компании. Ответ будет ограничен текущими
            подтверждёнными данными.
          </span>
        </div>
      </header>
      <CompanyAssistantPanel
        answer={conversation.answer}
        error={conversation.error}
        fieldId="company-assistant-page-query"
        onAction={() => undefined}
        onQueryChange={conversation.setQuery}
        onSubmit={conversation.onSubmit}
        onSuggestion={(suggestion) => {
          conversation.setQuery(suggestion);
          void conversation.submit(suggestion);
        }}
        query={conversation.query}
        status={conversation.status}
      />
    </section>
  );
}

export function CompanyAssistantPanel({
  answer,
  error,
  fieldId = "company-assistant-query",
  onAction,
  onQueryChange,
  onSubmit,
  onSuggestion,
  query,
  status
}: {
  answer: AssistantQueryResponse | null;
  error: string | null;
  fieldId?: string;
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
          <strong>Ответ по памяти текущей компании</strong>
          <p>FounderOS не додумывает отсутствующие факты и показывает проверяемые основания.</p>
        </div>
      </div>

      <form className={styles.form} onSubmit={onSubmit}>
        <label htmlFor={fieldId}>Ваш вопрос</label>
        <textarea
          disabled={pending}
          id={fieldId}
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
        {status === "loading_snapshot" ? <p>Сверяю текущую картину компании…</p> : null}
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
              Картина {shortSnapshotId(answer.snapshot_id)} · только чтение · действий не выполнено
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
    sources: "Источники",
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
