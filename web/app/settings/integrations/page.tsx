"use client";

import type { FormEvent } from "react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { PageHeader } from "../../../components/PageHeader";
import {
  applyConnectorConfiguration,
  checkConnectorReadAccess,
  checkConnectorWriteReadiness,
  disconnectConnectorConfiguration,
  fetchConnectorControlCenter
} from "../../../lib/api";
import { M } from "../../../lib/messages";
import { useSession } from "../../../lib/session";
import type {
  ConnectorCheckReceipt,
  ConnectorConfigurationApplyRequest,
  ConnectorControl,
  ConnectorControlCenterResponse,
  ConnectorProvider
} from "../../../lib/types";

type PanelStatus = "error" | "loading" | "missing" | "ready";
type PendingAction = "apply" | "disconnect" | "read" | "write" | null;

type IntegrationsControlCenterViewProps = {
  actionError?: string | null;
  actionMessage?: string | null;
  canManage: boolean;
  data: ConnectorControlCenterResponse | null;
  error: string | null;
  onApply?: (
    provider: ConnectorProvider,
    request: ConnectorConfigurationApplyRequest
  ) => Promise<boolean> | boolean;
  onDisconnect?: (provider: ConnectorProvider) => Promise<void> | void;
  onReadCheck?: (provider: ConnectorProvider) => Promise<void> | void;
  onRetry?: () => void;
  onWriteCheck?: (provider: ConnectorProvider) => Promise<void> | void;
  pendingAction?: PendingAction;
  status: PanelStatus;
};

const PROVIDER_ORDER: ConnectorProvider[] = ["github", "jira", "gmail", "drive"];

export function connectorDisconnectSuccessMessage(
  provider: ConnectorProvider,
  managedGitHub: boolean
): string {
  if (provider === "github") {
    return managedGitHub
      ? "Резервный GitHub token удалён. GitHub App продолжает работать."
      : "GitHub token удалён. Уже загруженные данные сохранены.";
  }
  return "Подключение удалено. Уже загруженные данные сохранены.";
}

export default function IntegrationsSettingsPage() {
  const session = useSession();
  const workspaceId = session?.workspaceId ?? null;
  const workspaceRole =
    session?.workspaces.find((workspace) => workspace.id === workspaceId)?.role ?? null;
  const canManage = workspaceRole === "owner" || workspaceRole === "admin";
  const [data, setData] = useState<ConnectorControlCenterResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [pendingAction, setPendingAction] = useState<PendingAction>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [status, setStatus] = useState<PanelStatus>("loading");

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
    fetchConnectorControlCenter(workspaceId)
      .then((payload) => {
        if (!cancelled) {
          setData(payload);
          setStatus("ready");
        }
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setData(null);
          setError(caught instanceof Error ? caught.message : M.common.requestFailed);
          setStatus("error");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceId, reloadKey]);

  async function refreshControlCenter(): Promise<void> {
    if (!workspaceId) {
      return;
    }
    setData(await fetchConnectorControlCenter(workspaceId));
    setStatus("ready");
  }

  async function onApply(
    provider: ConnectorProvider,
    request: ConnectorConfigurationApplyRequest
  ): Promise<boolean> {
    if (!workspaceId || pendingAction) {
      return false;
    }
    setPendingAction("apply");
    setActionError(null);
    setActionMessage(null);
    try {
      await applyConnectorConfiguration(workspaceId, provider, request);
      await refreshControlCenter();
      setActionMessage(
        "Доступ сохранён. Теперь проверьте подключение."
      );
      return true;
    } catch (caught: unknown) {
      setActionError(
        connectorActionError(caught)
      );
      return false;
    } finally {
      setPendingAction(null);
    }
  }

  async function onReadCheck(provider: ConnectorProvider): Promise<void> {
    if (!workspaceId || pendingAction) {
      return;
    }
    setPendingAction("read");
    setActionError(null);
    setActionMessage(null);
    try {
      const receipt = await checkConnectorReadAccess(workspaceId, provider);
      await refreshControlCenter();
      setActionMessage(
        receipt.status === "passed"
          ? "Подключение работает. FounderOS получил доступ на чтение."
          : checkReceiptMessage(receipt)
      );
    } catch (caught: unknown) {
      setActionError(connectorActionError(caught));
    } finally {
      setPendingAction(null);
    }
  }

  async function onDisconnect(provider: ConnectorProvider): Promise<void> {
    if (!workspaceId || pendingAction) {
      return;
    }
    const managedGitHub =
      provider === "github" &&
      data?.connectors.find((connector) => connector.provider === provider)
        ?.auth_method === "github_app_installation";
    setPendingAction("disconnect");
    setActionError(null);
    setActionMessage(null);
    try {
      await disconnectConnectorConfiguration(workspaceId, provider);
      await refreshControlCenter();
      setActionMessage(
        connectorDisconnectSuccessMessage(provider, managedGitHub)
      );
    } catch (caught: unknown) {
      setActionError(connectorActionError(caught));
    } finally {
      setPendingAction(null);
    }
  }

  async function onWriteCheck(provider: ConnectorProvider): Promise<void> {
    if (!workspaceId || pendingAction) {
      return;
    }
    setPendingAction("write");
    setActionError(null);
    setActionMessage(null);
    try {
      const receipt = await checkConnectorWriteReadiness(workspaceId, provider);
      await refreshControlCenter();
      setActionMessage(checkReceiptMessage(receipt));
    } catch (caught: unknown) {
      setActionError(connectorActionError(caught));
    } finally {
      setPendingAction(null);
    }
  }

  return (
    <>
      <Link className="onboarding-return" href="/settings">
        <span aria-hidden="true">←</span>
        Вернуться в настройки
      </Link>
      <PageHeader
        eyebrow="Настройки"
        title="Подключения"
        description="Ключи источников вводятся только здесь: FounderOS зашифрует доступ, а отдельная проверка подтвердит чтение."
      />
      <IntegrationsControlCenterView
        actionError={actionError}
        actionMessage={actionMessage}
        canManage={canManage}
        data={data}
        error={error}
        onApply={onApply}
        onDisconnect={onDisconnect}
        onReadCheck={onReadCheck}
        onRetry={() => setReloadKey((current) => current + 1)}
        onWriteCheck={onWriteCheck}
        pendingAction={pendingAction}
        status={status}
      />
    </>
  );
}

export function IntegrationsControlCenterView({
  actionError = null,
  actionMessage = null,
  canManage,
  data,
  error,
  onApply,
  onDisconnect,
  onReadCheck,
  onRetry,
  onWriteCheck,
  pendingAction = null,
  status
}: IntegrationsControlCenterViewProps) {
  const [selectedProvider, setSelectedProvider] =
    useState<ConnectorProvider>("github");
  useEffect(() => {
    const requested = new URLSearchParams(window.location.search).get("provider");
    if (PROVIDER_ORDER.includes(requested as ConnectorProvider)) {
      setSelectedProvider(requested as ConnectorProvider);
    }
  }, []);
  const selected = useMemo(
    () =>
      data?.connectors.find((connector) => connector.provider === selectedProvider) ??
      null,
    [data, selectedProvider]
  );

  return (
    <section
      className="integrations-control-center"
      aria-label="Источники данных"
    >
      {status === "loading" ? (
        <p className="state loading">Загружаем подключения…</p>
      ) : null}
      {status === "missing" ? (
        <p className="muted">Сначала выберите компанию.</p>
      ) : null}
      {status === "error" ? (
        <section className="state error">
          <strong>Не удалось загрузить подключения</strong>
          <p>{error ?? M.common.requestFailed}</p>
          {onRetry ? (
            <button className="button secondary" onClick={onRetry} type="button">
              {M.common.retry}
            </button>
          ) : null}
        </section>
      ) : null}

      {data && status === "ready" ? (
        <>
          <header className="connections-overview">
            <div>
              <h2>Источники данных</h2>
              <p>Начните с одного. Остальные можно подключить позже.</p>
            </div>
            <span>
              {data.summary.verified} из {data.summary.total} работают
            </span>
          </header>

          <div className="integration-workbench">
            <nav className="integration-provider-nav" aria-label="Провайдеры">
              {PROVIDER_ORDER.map((provider) => {
                const connector = data.connectors.find(
                  (item) => item.provider === provider
                );
                if (!connector) {
                  return null;
                }
                return (
                  <button
                    aria-current={selectedProvider === provider ? "page" : undefined}
                    className={`integration-provider-tab${
                      selectedProvider === provider ? " is-active" : ""
                    }`}
                    key={provider}
                    onClick={() => {
                      setSelectedProvider(provider);
                      const url = new URL(window.location.href);
                      url.searchParams.set("provider", provider);
                      window.history.replaceState(null, "", url);
                    }}
                    type="button"
                  >
                    <span
                      className={`integration-provider-icon integration-provider-icon--${provider}`}
                      aria-hidden="true"
                    >
                      {connector.name.slice(0, 1)}
                    </span>
                    <span>
                      <strong>{connector.name}</strong>
                      <small>{connectorStateLabel(connector)}</small>
                    </span>
                    <i
                      aria-hidden="true"
                      className={`integration-status-dot integration-status-dot--${connector.state}`}
                    />
                  </button>
                );
              })}
            </nav>

            {selected ? (
              <ConnectorConfigurationPanel
                actionError={actionError}
                actionMessage={actionMessage}
                canManage={canManage}
                connector={selected}
                key={selected.provider}
                onApply={onApply}
                onDisconnect={onDisconnect}
                onReadCheck={onReadCheck}
                onWriteCheck={onWriteCheck}
                pendingAction={pendingAction}
              />
            ) : null}
          </div>
        </>
      ) : null}
    </section>
  );
}

function ConnectorConfigurationPanel({
  actionError,
  actionMessage,
  canManage,
  connector,
  onApply,
  onDisconnect,
  onReadCheck,
  onWriteCheck,
  pendingAction
}: {
  actionError: string | null;
  actionMessage: string | null;
  canManage: boolean;
  connector: ConnectorControl;
  onApply?: IntegrationsControlCenterViewProps["onApply"];
  onDisconnect?: IntegrationsControlCenterViewProps["onDisconnect"];
  onReadCheck?: IntegrationsControlCenterViewProps["onReadCheck"];
  onWriteCheck?: IntegrationsControlCenterViewProps["onWriteCheck"];
  pendingAction: PendingAction;
}) {
  const [accessToken, setAccessToken] = useState("");
  const [accountEmail, setAccountEmail] = useState("");
  const [baseUrl, setBaseUrl] = useState(connector.base_url ?? "");
  const [disconnectConfirmed, setDisconnectConfirmed] = useState(false);

  useEffect(() => {
    void connector.provider;
    setAccessToken("");
    setAccountEmail("");
    setBaseUrl(connector.base_url ?? "");
    setDisconnectConfirmed(false);
  }, [connector.provider, connector.base_url]);

  const managedGitHub =
    connector.provider === "github" &&
    connector.auth_method === "github_app_installation";
  const editableCredentialPresent =
    connector.provider === "github"
      ? connector.removable_credential_present
      : connector.credential_present;

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!onApply || !canManage || !accessToken || pendingAction) {
      return;
    }
    const succeeded = await onApply(connector.provider, {
      access_token: accessToken,
      account_email: connector.provider === "jira" ? accountEmail : null,
      auth_method: authMethod(connector.provider),
      base_url: connector.provider === "jira" ? baseUrl : null,
      display_name: null,
      scopes: []
    });
    if (succeeded) {
      setAccessToken("");
    }
  }

  async function disconnectCredential() {
    if (
      !disconnectConfirmed ||
      !onDisconnect ||
      !canManage ||
      pendingAction
    ) {
      return;
    }
    await onDisconnect(connector.provider);
    setDisconnectConfirmed(false);
  }

  const configurationForm = (
    <form className="form integration-config-form" onSubmit={onSubmit}>
      {connector.provider === "jira" ? (
        <>
          <div className="field">
            <label htmlFor="jira-base-url">Адрес Jira Cloud</label>
            <input
              id="jira-base-url"
              onChange={(event) => setBaseUrl(event.target.value)}
              placeholder="https://company.atlassian.net"
              required
              type="url"
              value={baseUrl}
            />
          </div>
          <div className="field">
            <label htmlFor="jira-account-email">Email аккаунта Atlassian</label>
            <input
              id="jira-account-email"
              maxLength={320}
              onChange={(event) => setAccountEmail(event.target.value)}
              placeholder="you@company.com"
              required
              type="email"
              value={accountEmail}
            />
          </div>
        </>
      ) : null}

      <div className="field">
        <label htmlFor={`${connector.provider}-access-token`}>
          {credentialLabel(connector.provider)}
        </label>
        <input
          autoComplete="new-password"
          id={`${connector.provider}-access-token`}
          maxLength={8192}
          onChange={(event) => setAccessToken(event.target.value)}
          placeholder={
            editableCredentialPresent
              ? "Введите новый токен для замены"
              : "Вставьте токен"
          }
          required
          type="password"
          value={accessToken}
        />
      </div>

      <p className="integration-secure-note">
        <span aria-hidden="true">⌁</span>
        Токен шифруется и больше не показывается в браузере.
      </p>

      <button
        className="button"
        disabled={!accessToken || pendingAction !== null}
        type="submit"
      >
        {pendingAction === "apply"
          ? "Сохраняем…"
          : connector.configured
            ? "Заменить токен"
            : "Сохранить подключение"}
      </button>
    </form>
  );

  return (
    <div className="integration-editor">
      <header className="integration-editor-header">
        <span
          className={`integration-provider-icon integration-provider-icon--${connector.provider}`}
          aria-hidden="true"
        >
          {connector.name.slice(0, 1)}
        </span>
        <div className="integration-editor-title">
          <span className={`integration-state-pill integration-state-pill--${connector.state}`}>
            {connectorStateLabel(connector)}
          </span>
          <h3>{connector.name}</h3>
          <p>{connectorIntro(connector.provider)}</p>
        </div>
      </header>

      {actionMessage ? (
        <p className="state success" role="status">
          {actionMessage}
        </p>
      ) : null}
      {actionError ? (
        <p className="state error" role="alert">
          {actionError}
        </p>
      ) : null}

      {connector.account_label ? (
        <p className="integration-account-fact">
          Аккаунт: <strong>{connector.account_label}</strong>
        </p>
      ) : null}

      <section className="integration-step" aria-labelledby="integration-connect-step">
        <div className="integration-step-heading">
          <span aria-hidden="true">1</span>
          <div>
            <h4 id="integration-connect-step">Подключение</h4>
            <p>
              {connector.configured
                ? "Доступ сохранён. При необходимости его можно заменить."
                : "Добавьте доступ к источнику."}
            </p>
          </div>
        </div>

        {!canManage ? (
          <p className="settings-permission-note">
            Подключения меняет владелец или администратор компании.
          </p>
        ) : connector.provider === "github" ? (
          <>
            <div className="integration-recommended-path">
              <div>
                <strong>GitHub App</strong>
                <span>Безопасный способ с выбором конкретных репозиториев.</span>
              </div>
              <Link className="button" href="/settings/integrations/github">
                {managedGitHub ? "Открыть GitHub" : "Подключить GitHub"}
              </Link>
            </div>
            <details className="integration-advanced">
              <summary>
                {editableCredentialPresent
                  ? "Заменить резервный personal access token"
                  : "Другой способ: personal access token"}
              </summary>
              {configurationForm}
            </details>
          </>
        ) : connector.configured ? (
          <details className="integration-advanced">
            <summary>Заменить данные подключения</summary>
            {configurationForm}
          </details>
        ) : (
          configurationForm
        )}
      </section>

      <section
        className={`integration-step integration-step--${connector.state}`}
        aria-labelledby="integration-check-step"
      >
        <div className="integration-step-heading">
          <span aria-hidden="true">2</span>
          <div>
            <h4 id="integration-check-step">{readStepTitle(connector)}</h4>
            <p>{readStepDescription(connector)}</p>
          </div>
        </div>
        <button
          className="button"
          disabled={!canManage || !connector.configured || pendingAction !== null}
          onClick={() => onReadCheck?.(connector.provider)}
          type="button"
        >
          {pendingAction === "read"
            ? "Проверяем…"
            : connector.state === "read_verified"
              ? "Проверить ещё раз"
              : "Проверить подключение"}
        </button>
        {connector.read_check ? (
          <CheckReceipt label="Результат проверки" receipt={connector.read_check} />
        ) : null}
      </section>

      {connector.configured ? (
        <details className="integration-technical">
          <summary>Дополнительные настройки</summary>
          <div>
            {connector.warnings.map((warning) => (
              <p className="integration-warning" key={warning}>
                {connectorWarning(warning)}
              </p>
            ))}
            <section>
              <h4>Готовность записи</h4>
              <p>
                Локальная проверка защитных условий. Она ничего не меняет во
                внешнем сервисе.
              </p>
              <button
                className="button secondary"
                disabled={!canManage || pendingAction !== null}
                onClick={() => onWriteCheck?.(connector.provider)}
                type="button"
              >
                {pendingAction === "write"
                  ? "Проверяем…"
                  : "Проверить готовность записи"}
              </button>
              {connector.write_check ? (
                <CheckReceipt
                  label="Результат проверки записи"
                  receipt={connector.write_check}
                />
              ) : null}
            </section>

            {canManage && connector.removable_credential_present ? (
              <details className="integration-disconnect">
                <summary>
                  {managedGitHub
                    ? "Удалить резервный token"
                    : "Удалить подключение"}
                </summary>
                <div>
                  <p>
                    Секрет и результаты проверок будут удалены. Уже загруженные
                    данные останутся.
                  </p>
                  <label className="integration-disconnect-confirm">
                    <input
                      checked={disconnectConfirmed}
                      onChange={(event) =>
                        setDisconnectConfirmed(event.target.checked)
                      }
                      type="checkbox"
                    />
                    <span>Подтверждаю удаление сохранённого доступа.</span>
                  </label>
                  <button
                    className="button danger"
                    disabled={!disconnectConfirmed || pendingAction !== null}
                    onClick={disconnectCredential}
                    type="button"
                  >
                    {pendingAction === "disconnect"
                      ? "Удаляем…"
                      : "Удалить подключение"}
                  </button>
                </div>
              </details>
            ) : null}
          </div>
        </details>
      ) : null}
    </div>
  );
}

function CheckReceipt({
  label,
  receipt
}: {
  label: string;
  receipt: ConnectorCheckReceipt | null;
}) {
  return (
    <article className="integration-receipt">
      <span>{label}</span>
      <strong>{receipt ? checkStatusLabel(receipt.status) : "Не запускалась"}</strong>
      <small>
        {receipt
          ? checkReceiptMessage(receipt)
          : "Результат появится после проверки."}
      </small>
      {receipt?.checks ? (
        <ul>
          {Object.entries(receipt.checks).map(([key, passed]) => (
            <li key={key}>
              <i aria-hidden="true">{passed ? "✓" : "·"}</i>
              {checkName(key)}
            </li>
          ))}
        </ul>
      ) : null}
    </article>
  );
}

function connectorStateLabel(connector: ConnectorControl): string {
  if (connector.state === "read_verified") {
    return "Работает";
  }
  if (connector.state === "saved_unverified") {
    return "Нужно проверить";
  }
  if (connector.state === "error") {
    return "Ошибка подключения";
  }
  return "Не подключено";
}

function connectorIntro(provider: ConnectorProvider): string {
  if (provider === "github") {
    return "Репозитории, задачи и pull requests.";
  }
  if (provider === "jira") {
    return "Задачи, статусы и сроки.";
  }
  if (provider === "gmail") {
    return "Письма и переписка с людьми и компаниями.";
  }
  return "Документы и рабочие файлы.";
}

function authMethod(provider: ConnectorProvider): string {
  if (provider === "github") {
    return "manual_provider_token";
  }
  if (provider === "jira") {
    return "jira_cloud_api_token";
  }
  return "oauth_access_token";
}

function credentialLabel(provider: ConnectorProvider): string {
  if (provider === "github") {
    return "Personal access token";
  }
  if (provider === "jira") {
    return "Atlassian API token";
  }
  return "Временный OAuth access token";
}

function checkStatusLabel(status: ConnectorCheckReceipt["status"]): string {
  if (status === "passed") {
    return "Успешно";
  }
  if (status === "ready") {
    return "Готово";
  }
  if (status === "failed") {
    return "Ошибка";
  }
  return "Пока не готово";
}

function checkName(key: string): string {
  const labels: Record<string, string> = {
    approval_required: "Действия требуют подтверждения",
    credential_configured: "Доступ сохранён",
    provider_write_supported: "Запись поддерживается",
    read_verified: "Чтение проверено",
    target_allowlist_configured: "Разрешённые цели настроены",
    write_feature_enabled: "Запись включена"
  };
  return labels[key] ?? "Защитное условие";
}

function connectorWarning(warning: string): string {
  if (warning.includes("Manual OAuth access tokens")) {
    return "Сейчас используется временный token. После истечения его потребуется заменить.";
  }
  if (warning.includes("managed GitHub App")) {
    return "Для постоянной работы лучше использовать GitHub App.";
  }
  return "Проверьте настройки этого подключения.";
}

function checkReceiptMessage(receipt: ConnectorCheckReceipt): string {
  const messages: Record<string, string> = {
    authorization_failed: "Сервис не принял сохранённый доступ. Проверьте token.",
    credential_missing: "Сначала сохраните доступ.",
    credential_unavailable: "Сохранённый доступ невозможно открыть. Замените token.",
    invalid_provider_response: "Сервис вернул неожиданный ответ. Повторите позже.",
    provider_rate_limited: "Сервис временно ограничил запросы. Повторите позже.",
    provider_resource_not_found: "Аккаунт или ресурс не найден.",
    provider_unavailable: "Сервис сейчас недоступен. Повторите позже.",
    read_verified: "FounderOS получил доступ на чтение.",
    write_guarded:
      "Запись не выполнялась. Не все защитные условия готовы.",
    write_ready:
      "Защитные условия готовы. Любое реальное действие всё равно потребует подтверждения."
  };
  return messages[receipt.code] ?? "Проверка завершена.";
}

function readStepTitle(connector: ConnectorControl): string {
  if (connector.state === "read_verified") {
    return "Подключение работает";
  }
  if (connector.state === "error") {
    return "Проверка не пройдена";
  }
  if (connector.configured) {
    return "Проверьте подключение";
  }
  return "Проверка подключения";
}

function readStepDescription(connector: ConnectorControl): string {
  if (connector.state === "read_verified") {
    return "FounderOS подтвердил доступ на чтение.";
  }
  if (connector.state === "error") {
    return connector.read_check
      ? checkReceiptMessage(connector.read_check)
      : "Проверьте сохранённый доступ и повторите.";
  }
  if (connector.configured) {
    return "Один безопасный запрос покажет, работает ли доступ.";
  }
  return "Станет доступна после сохранения подключения.";
}

function connectorActionError(caught: unknown): string {
  const message = caught instanceof Error ? caught.message : "";
  if (message.includes("insufficient workspace role")) {
    return "Недостаточно прав для изменения подключения.";
  }
  if (message.includes("secure connector credential storage")) {
    return "Безопасное хранилище недоступно. Проверьте настройки сервера.";
  }
  if (message.includes("atlassian.net")) {
    return "Укажите адрес Jira Cloud вида https://company.atlassian.net.";
  }
  if (message.includes("account email")) {
    return "Укажите email аккаунта Atlassian.";
  }
  if (message.includes("credential")) {
    return "Проверьте token и повторите.";
  }
  return M.common.requestFailed;
}
