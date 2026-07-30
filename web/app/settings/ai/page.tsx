"use client";

import Link from "next/link";
import type { FormEvent } from "react";
import { useCallback, useEffect, useState } from "react";

import { PageHeader } from "../../../components/PageHeader";
import {
  applyWorkspaceAISettings,
  checkWorkspaceAIConnection,
  fetchWorkspaceAISettings,
  removeWorkspaceAICredential
} from "../../../lib/api";
import { useSession } from "../../../lib/session";
import type {
  AIModel,
  AIReasoningEffort,
  AISettings,
  AISettingsCheckReceipt
} from "../../../lib/types";
import styles from "./ai-settings.module.css";

type PageStatus = "error" | "loading" | "missing" | "ready";

export default function AISettingsPage() {
  const session = useSession();
  const workspaceId = session?.workspaceId ?? null;
  const workspace = session?.workspaces.find((item) => item.id === workspaceId) ?? null;
  const canManage = workspace?.role === "owner" || workspace?.role === "admin";
  const [status, setStatus] = useState<PageStatus>("loading");
  const [settings, setSettings] = useState<AISettings | null>(null);
  const [model, setModel] = useState<AIModel>("gpt-5.6");
  const [effort, setEffort] = useState<AIReasoningEffort>("medium");
  const [maxOutputTokens, setMaxOutputTokens] = useState(1_200);
  const [apiKey, setApiKey] = useState("");
  const [acknowledged, setAcknowledged] = useState(false);
  const [enabled, setEnabled] = useState(false);
  const [pending, setPending] = useState<"apply" | "check" | "remove" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [checkReceipt, setCheckReceipt] = useState<AISettingsCheckReceipt | null>(null);
  const [removeArmed, setRemoveArmed] = useState(false);
  const readiness = settings ? aiSettingsReadiness(settings) : null;

  const applyLoadedSettings = useCallback((payload: AISettings) => {
    setSettings(payload);
    setModel(payload.model);
    setEffort(payload.reasoning_effort);
    setMaxOutputTokens(payload.max_output_tokens);
    setAcknowledged(payload.data_policy.acknowledged);
    setEnabled(payload.enabled);
    setApiKey("");
  }, []);

  const load = useCallback(async () => {
    if (!workspaceId) {
      setStatus("missing");
      setSettings(null);
      return;
    }
    setStatus("loading");
    setError(null);
    try {
      const payload = await fetchWorkspaceAISettings(workspaceId);
      applyLoadedSettings(payload);
      setStatus("ready");
    } catch {
      setStatus("error");
      setError("Не удалось загрузить настройки AI.");
    }
  }, [applyLoadedSettings, workspaceId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function onApply(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspaceId || !canManage || pending) return;
    setPending("apply");
    setError(null);
    setMessage(null);
    setCheckReceipt(null);
    try {
      const payload = await applyWorkspaceAISettings(workspaceId, {
        enabled,
        data_policy_acknowledged: acknowledged,
        model,
        reasoning_effort: effort,
        max_output_tokens: maxOutputTokens,
        ...(apiKey.trim() ? { api_key: apiKey } : {})
      });
      applyLoadedSettings(payload);
      setMessage(
        "Настройки сохранены локально. Внешний AI-вызов при сохранении не выполнялся."
      );
    } catch {
      setError("Не удалось применить настройки. Проверьте обязательные поля.");
    } finally {
      setPending(null);
    }
  }

  async function onCheck() {
    if (!workspaceId || !canManage || pending) return;
    setPending("check");
    setError(null);
    setMessage(null);
    setCheckReceipt(null);
    try {
      const receipt = await checkWorkspaceAIConnection(workspaceId);
      setCheckReceipt(receipt);
      const refreshed = await fetchWorkspaceAISettings(workspaceId);
      applyLoadedSettings(refreshed);
    } catch {
      setError("Проверка не запустилась. Сначала сохраните ключ и согласие.");
    } finally {
      setPending(null);
    }
  }

  async function onRemove() {
    if (!workspaceId || !canManage || pending || !removeArmed) return;
    setPending("remove");
    setError(null);
    setMessage(null);
    try {
      const payload = await removeWorkspaceAICredential(workspaceId);
      applyLoadedSettings(payload);
      setCheckReceipt(null);
      setRemoveArmed(false);
      setMessage("Ключ удалён. AI для этой компании выключен.");
    } catch {
      setError("Не удалось удалить ключ.");
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
        eyebrow="Настройки · AI"
        title="Второе мнение"
        description="Ключ OpenAI хранится только в настройках компании: сохраните его, отдельно проверьте доступ и управляйте передачей данных."
      />

      {status === "loading" ? <p className="state loading">Загружаю настройки…</p> : null}
      {status === "missing" ? <p className="state">Сначала выберите компанию.</p> : null}
      {status === "error" ? (
        <section className="state error">
          <p>{error}</p>
          <button className="button secondary" onClick={() => void load()} type="button">
            Повторить
          </button>
        </section>
      ) : null}

      {status === "ready" && settings ? (
        <div className={styles.layout}>
          <section className={styles.overview} aria-label="Состояние AI">
            <div>
              <span>Ключ</span>
              <strong>{readiness?.key}</strong>
            </div>
            <div>
              <span>Проверка</span>
              <strong>
                {readiness?.check}
              </strong>
            </div>
            <div>
              <span>AI-ответы</span>
              <strong>
                {readiness?.activation}
              </strong>
            </div>
          </section>

          {!settings.server_permitted ? (
            <section className={styles.gate}>
              <strong>Серверный предохранитель выключен</strong>
              <p>
                Настройки можно подготовить, но FounderOS не отправит данные модели,
                пока оператор не разрешит AI-вызовы на сервере.
              </p>
            </section>
          ) : null}

          <form className={styles.form} onSubmit={onApply}>
            <header>
              <div>
                <span>Подключение</span>
                <h2>OpenAI API</h2>
              </div>
              <span className={styles.localBadge}>Секрет остаётся на сервере</span>
            </header>

            <label>
              <span>API key</span>
              <input
                autoComplete="off"
                disabled={!canManage || pending !== null}
                maxLength={512}
                onChange={(event) => setApiKey(event.target.value)}
                placeholder={
                  settings.key_present
                    ? "Ключ уже сохранён — оставьте пустым, чтобы не менять"
                    : "Вставьте новый ключ"
                }
                type="password"
                value={apiKey}
              />
            </label>

            <div className={styles.twoColumns}>
              <label>
                <span>Модель</span>
                <select
                  disabled={!canManage || pending !== null}
                  onChange={(event) => setModel(event.target.value as AIModel)}
                  value={model}
                >
                  {settings.supported_models.map((option) => (
                    <option key={option} value={option}>
                      {modelLabel(option)}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span>Глубина анализа</span>
                <select
                  disabled={!canManage || pending !== null}
                  onChange={(event) =>
                    setEffort(event.target.value as AIReasoningEffort)
                  }
                  value={effort}
                >
                  <option value="low">Быстро</option>
                  <option value="medium">Сбалансированно</option>
                  <option value="high">Глубже</option>
                </select>
              </label>
            </div>

            <label>
              <span>Максимальный объём ответа</span>
              <input
                disabled={!canManage || pending !== null}
                max={4_000}
                min={400}
                onChange={(event) => setMaxOutputTokens(Number(event.target.value))}
                step={100}
                type="number"
                value={maxOutputTokens}
              />
            </label>

            <label className={styles.consent}>
              <input
                checked={acknowledged}
                disabled={!canManage || pending !== null}
                onChange={(event) => {
                  setAcknowledged(event.target.checked);
                  if (!event.target.checked) setEnabled(false);
                }}
                type="checkbox"
              />
              <span>
                Я понимаю: <code>store=false</code> не является Zero Data
                Retention. По стандартной политике провайдера содержимое может
                попасть в abuse-monitoring logs на ограниченный срок.
              </span>
            </label>

            <label className={styles.consent}>
              <input
                checked={enabled}
                disabled={!canManage || pending !== null || !acknowledged}
                onChange={(event) => setEnabled(event.target.checked)}
                type="checkbox"
              />
              <span>
                Разрешить FounderOS отправлять модели только bounded
                нормализованные факты текущего снимка.
              </span>
            </label>

            {message ? <p className="success-text">{message}</p> : null}
            {error ? <p className="error-text">{error}</p> : null}
            {checkReceipt ? (
              <p
                className={
                  checkReceipt.status === "passed" ? "success-text" : "error-text"
                }
              >
                {checkReceipt.message} Данные компании не отправлялись.
              </p>
            ) : null}

            <div className={styles.actions}>
              <button
                className="button"
                disabled={!canManage || pending !== null}
                type="submit"
              >
                {pending === "apply" ? "Применяю…" : "Применить"}
              </button>
              <button
                className="button secondary"
                disabled={
                  !canCheckAISettings({
                    acknowledged,
                    canManage,
                    keyPresent: settings.key_present,
                    pending: pending !== null,
                    serverPermitted: settings.server_permitted
                  })
                }
                onClick={() => void onCheck()}
                type="button"
              >
                {pending === "check" ? "Проверяю…" : "Проверить подключение"}
              </button>
            </div>
          </form>

          <section className={styles.boundary}>
            <strong>Что именно происходит</strong>
            <ul>
              <li>«Применить» только шифрует и сохраняет настройки.</li>
              <li>Проверка отправляет технический факт без данных компании.</li>
              <li>Вопросы и ответы FounderOS не сохраняются как история чата.</li>
              <li>Модель не может выполнить внешнюю запись.</li>
            </ul>
          </section>

          {settings.key_present && canManage ? (
            <section className={styles.remove}>
              <div>
                <strong>Удалить ключ</strong>
                <p>AI выключится; память компании и evidence останутся на месте.</p>
              </div>
              {removeArmed ? (
                <div className={styles.removeActions}>
                  <button
                    className="button secondary"
                    disabled={pending !== null}
                    onClick={() => setRemoveArmed(false)}
                    type="button"
                  >
                    Отмена
                  </button>
                  <button
                    className="button danger"
                    disabled={pending !== null}
                    onClick={() => void onRemove()}
                    type="button"
                  >
                    {pending === "remove" ? "Удаляю…" : "Подтвердить удаление"}
                  </button>
                </div>
              ) : (
                <button
                  className="button secondary"
                  disabled={pending !== null}
                  onClick={() => setRemoveArmed(true)}
                  type="button"
                >
                  Удалить ключ
                </button>
              )}
            </section>
          ) : null}

          {!canManage ? (
            <p className={styles.readOnly}>
              Настройки доступны только для чтения. Изменить их может владелец
              или администратор компании.
            </p>
          ) : null}
        </div>
      ) : null}
    </>
  );
}

export function aiSettingsReadiness(settings: AISettings) {
  return {
    key: settings.key_present ? "Сохранён" : "Не добавлен",
    check:
      settings.last_check?.status === "passed"
        ? "Работает"
        : settings.last_check?.status === "failed"
          ? "Ошибка"
          : "Не проверено",
    activation:
      settings.enabled && settings.server_permitted ? "Включены" : "Выключены"
  };
}

export function canCheckAISettings({
  acknowledged,
  canManage,
  keyPresent,
  pending,
  serverPermitted
}: {
  acknowledged: boolean;
  canManage: boolean;
  keyPresent: boolean;
  pending: boolean;
  serverPermitted: boolean;
}): boolean {
  return canManage && !pending && keyPresent && acknowledged && serverPermitted;
}

export function modelLabel(model: AIModel): string {
  if (model === "gpt-5.6-terra") return "GPT-5.6 Terra · баланс";
  if (model === "gpt-5.6-luna") return "GPT-5.6 Luna · экономно";
  if (model === "gpt-5.6-sol") return "GPT-5.6 Sol · максимум";
  return "GPT-5.6 · рекомендуемый alias";
}
