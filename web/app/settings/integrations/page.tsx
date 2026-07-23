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
      ? "Сохранённый personal access token удалён. Managed GitHub App, canonical данные и история не изменены."
      : "Сохранённый personal access token удалён. Canonical данные и история источника не изменены.";
  }
  return "Сохранённый секрет удалён. Canonical данные и история источника не изменены.";
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
        "Конфигурация зашифрована и сохранена. Теперь запустите проверку чтения."
      );
      return true;
    } catch (caught: unknown) {
      setActionError(
        caught instanceof Error ? caught.message : M.common.requestFailed
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
          ? "Чтение подтверждено реальным ограниченным запросом к провайдеру."
          : checkReceiptMessage(receipt)
      );
    } catch (caught: unknown) {
      setActionError(
        caught instanceof Error ? caught.message : M.common.requestFailed
      );
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
      setActionError(
        caught instanceof Error ? caught.message : M.common.requestFailed
      );
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
      setActionError(
        caught instanceof Error ? caught.message : M.common.requestFailed
      );
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
        eyebrow="Настройки · Интеграции"
        title="Центр интеграций"
        description="Подключайте источники, проверяйте фактическое чтение и контролируйте готовность безопасной записи из одного места."
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
  const selected = useMemo(
    () =>
      data?.connectors.find((connector) => connector.provider === selectedProvider) ??
      null,
    [data, selectedProvider]
  );

  return (
    <section
      className="panel integrations-control-center"
      aria-labelledby="integrations-control-title"
    >
      <div className="section-header integrations-control-header">
        <div>
          <span className="eyebrow">Контур подключений</span>
          <h2 id="integrations-control-title">API и коннекторы</h2>
        </div>
        {data && status === "ready" ? (
          <span className="badge">
            {data.summary.verified} из {data.summary.total} проверено
          </span>
        ) : null}
      </div>

      <div className="integration-safety-strip">
        <span aria-hidden="true">◈</span>
        <p>
          Секрет сохраняется только на backend в зашифрованном виде и никогда не
          возвращается в браузер. Проверка записи — только dry-run без изменения
          внешнего сервиса.
        </p>
      </div>

      {status === "loading" ? (
        <p className="state loading">Загружаем состояние подключений…</p>
      ) : null}
      {status === "missing" ? (
        <p className="muted">Сначала выберите компанию.</p>
      ) : null}
      {status === "error" ? (
        <section className="state error">
          <strong>Центр интеграций недоступен</strong>
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
          <dl className="integration-summary" aria-label="Сводка подключений">
            <div>
              <dt>Сохранено</dt>
              <dd>{data.summary.configured}</dd>
            </div>
            <div>
              <dt>Чтение проверено</dt>
              <dd>{data.summary.verified}</dd>
            </div>
            <div>
              <dt>Требуют внимания</dt>
              <dd>{data.summary.errors}</dd>
            </div>
          </dl>

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
                    onClick={() => setSelectedProvider(provider)}
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
  const [displayName, setDisplayName] = useState(connector.display_name ?? "");
  const [disconnectConfirmed, setDisconnectConfirmed] = useState(false);
  const [scopes, setScopes] = useState(connector.scopes.join(", "));

  useEffect(() => {
    setAccessToken("");
    setAccountEmail("");
    setBaseUrl(connector.base_url ?? "");
    setDisplayName(connector.display_name ?? "");
    setDisconnectConfirmed(false);
    setScopes(connector.scopes.join(", "));
  }, [connector.provider, connector.base_url, connector.display_name, connector.scopes]);

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
      display_name: displayName || null,
      scopes: scopes
        .split(",")
        .map((scope) => scope.trim())
        .filter(Boolean)
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

  return (
    <div className="integration-editor">
      <header className="integration-editor-header">
        <div>
          <span className={`integration-state-pill integration-state-pill--${connector.state}`}>
            {connectorStateLabel(connector)}
          </span>
          <h3>{connector.name}</h3>
          <p>{connectorIntro(connector.provider)}</p>
        </div>
        {connector.last_checked_at ? (
          <small>Последняя проверка: {connector.last_checked_at}</small>
        ) : null}
      </header>

      {connector.account_label ? (
        <p className="integration-account-fact">
          Текущий аккаунт: <strong>{connector.account_label}</strong>
        </p>
      ) : null}

      {connector.warnings.map((warning) => (
        <p className="integration-warning" key={warning}>
          {connectorWarning(warning)}
        </p>
      ))}

      {connector.provider === "github" ? (
        <div className="integration-recommended-path">
          <div>
            <strong>GitHub App — рекомендуемый способ</strong>
            <span>
              Короткоживущие токены, выбор репозиториев и отдельный управляемый
              контур.
            </span>
          </div>
          <Link className="button secondary" href="/github">
            {managedGitHub ? "Управлять GitHub App" : "Подключить GitHub App"}
          </Link>
        </div>
      ) : null}

      {!canManage ? (
        <p className="settings-permission-note">
          Изменять и проверять подключения может владелец или администратор
          компании.
        </p>
      ) : (
        <form className="form integration-config-form" onSubmit={onSubmit}>
          <div className="integration-form-heading">
            <strong>
              {connector.provider === "github"
                ? "Расширенный способ: personal access token"
                : "Параметры подключения"}
            </strong>
            <span>После сохранения прежний секрет будет заменён.</span>
          </div>

          <div className="field">
            <label htmlFor={`${connector.provider}-display-name`}>
              Название подключения
            </label>
            <input
              id={`${connector.provider}-display-name`}
              maxLength={255}
              onChange={(event) => setDisplayName(event.target.value)}
              placeholder={`${connector.name} · основной аккаунт`}
              type="text"
              value={displayName}
            />
          </div>

          {connector.provider === "jira" ? (
            <div className="integration-field-grid">
              <div className="field">
                <label htmlFor="jira-base-url">Jira Cloud site</label>
                <input
                  id="jira-base-url"
                  onChange={(event) => setBaseUrl(event.target.value)}
                  placeholder="https://company.atlassian.net"
                  required
                  type="url"
                  value={baseUrl}
                />
                <span className="muted">Только HTTPS *.atlassian.net без пути.</span>
              </div>
              <div className="field">
                <label htmlFor="jira-account-email">Email аккаунта Atlassian</label>
                <input
                  id="jira-account-email"
                  maxLength={320}
                  onChange={(event) => setAccountEmail(event.target.value)}
                  required
                  type="email"
                  value={accountEmail}
                />
              </div>
            </div>
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
                  ? "Секрет уже сохранён — введите новый только для замены"
                  : "Вставьте секрет"
              }
              required
              type="password"
              value={accessToken}
            />
            <span className="muted">
              Значение существует только в этой форме до отправки и не
              отображается после сохранения.
            </span>
          </div>

          <div className="field">
            <label htmlFor={`${connector.provider}-scopes`}>
              Ожидаемые scopes
            </label>
            <input
              id={`${connector.provider}-scopes`}
              onChange={(event) => setScopes(event.target.value)}
              placeholder={scopePlaceholder(connector.provider)}
              type="text"
              value={scopes}
            />
            <span className="muted">Через запятую; результат чтения уточнит доступ.</span>
          </div>

          <div className="actions-row">
            <button
              className="button"
              disabled={!accessToken || pendingAction !== null}
              type="submit"
            >
              {pendingAction === "apply" ? "Сохраняем…" : "Применить"}
            </button>
          </div>
        </form>
      )}

      {canManage && connector.removable_credential_present ? (
        <details className="integration-disconnect">
          <summary>
            {managedGitHub
              ? "Удалить резервный personal access token"
              : "Отключить сохранённый credential"}
          </summary>
          <div>
            <p>
              {managedGitHub
                ? "Будет удалён только PAT, сохранённый через этот центр. Managed GitHub App останется подключён."
                : "Будут удалены зашифрованный секрет и квитанции проверок. Уже импортированные canonical данные и история останутся."}
            </p>
            <label className="integration-disconnect-confirm">
              <input
                checked={disconnectConfirmed}
                onChange={(event) =>
                  setDisconnectConfirmed(event.target.checked)
                }
                type="checkbox"
              />
              <span>Я понимаю последствие и хочу удалить сохранённый секрет.</span>
            </label>
            <button
              className="button danger"
              disabled={!disconnectConfirmed || pendingAction !== null}
              onClick={disconnectCredential}
              type="button"
            >
              {pendingAction === "disconnect"
                ? "Удаляем секрет…"
                : "Удалить сохранённый секрет"}
            </button>
          </div>
        </details>
      ) : null}

      <section className="integration-checks" aria-labelledby="integration-checks-title">
        <div>
          <span className="eyebrow">Контроль доступа</span>
          <h4 id="integration-checks-title">Проверить подключение</h4>
        </div>
        <div className="integration-check-actions">
          <button
            className="button secondary"
            disabled={!canManage || !connector.configured || pendingAction !== null}
            onClick={() => onReadCheck?.(connector.provider)}
            type="button"
          >
            {pendingAction === "read" ? "Проверяем чтение…" : "Проверить чтение"}
          </button>
          <button
            className="button secondary"
            disabled={!canManage || pendingAction !== null}
            onClick={() => onWriteCheck?.(connector.provider)}
            type="button"
          >
            {pendingAction === "write"
              ? "Проверяем контур…"
              : "Проверить запись · dry-run"}
          </button>
        </div>
        <p className="muted">
          Чтение выполняет один ограниченный GET-запрос; GitHub App перед ним
          получает короткоживущий токен. Проверка записи анализирует feature
          flags, approval и allowlist, но не вызывает API провайдера.
        </p>
        <div className="integration-receipts">
          <CheckReceipt label="Чтение" receipt={connector.read_check} />
          <CheckReceipt label="Запись · dry-run" receipt={connector.write_check} />
        </div>
      </section>

      {actionMessage ? (
        <p className="success-text" role="status">
          {actionMessage}
        </p>
      ) : null}
      {actionError ? (
        <p className="error-text" role="alert">
          {actionError}
        </p>
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
          : "Здесь появится безопасная квитанция без provider payload и секретов."}
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
    return "Чтение проверено";
  }
  if (connector.state === "saved_unverified") {
    return "Сохранено · нужна проверка";
  }
  if (connector.state === "error") {
    return "Требует внимания";
  }
  return "Не настроено";
}

function connectorIntro(provider: ConnectorProvider): string {
  if (provider === "github") {
    return "Репозитории, issues и pull requests.";
  }
  if (provider === "jira") {
    return "Задачи, статусы, приоритеты и сроки из Jira Cloud.";
  }
  if (provider === "gmail") {
    return "Письма и цепочки как фактический источник контекста.";
  }
  return "Документы и файлы Google Drive.";
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
    return "GitHub personal access token";
  }
  if (provider === "jira") {
    return "Atlassian API token";
  }
  return "OAuth access token";
}

function scopePlaceholder(provider: ConnectorProvider): string {
  if (provider === "github") {
    return "repo, read:org";
  }
  if (provider === "jira") {
    return "read:jira-work, read:jira-user";
  }
  if (provider === "gmail") {
    return "gmail.readonly";
  }
  return "drive.metadata.readonly, drive.readonly";
}

function checkStatusLabel(status: ConnectorCheckReceipt["status"]): string {
  if (status === "passed") {
    return "Успешно";
  }
  if (status === "ready") {
    return "Контур готов";
  }
  if (status === "failed") {
    return "Ошибка";
  }
  return "Защищено ограничениями";
}

function checkName(key: string): string {
  const labels: Record<string, string> = {
    approval_required: "Approval обязателен",
    credential_configured: "Секрет настроен",
    provider_write_supported: "Запись провайдера реализована",
    read_verified: "Чтение проверено",
    target_allowlist_configured: "Allowlist целей настроен",
    write_feature_enabled: "Write feature flag включён"
  };
  return labels[key] ?? key;
}

function connectorWarning(warning: string): string {
  if (warning.includes("Manual OAuth access tokens")) {
    return "Ручной OAuth access token может истечь: автоматическое обновление OAuth пока не реализовано.";
  }
  if (warning.includes("managed GitHub App")) {
    return "Рекомендуется управляемый GitHub App; personal access token оставлен как расширенный резервный способ.";
  }
  return warning;
}

function checkReceiptMessage(receipt: ConnectorCheckReceipt): string {
  const messages: Record<string, string> = {
    authorization_failed: "Провайдер отклонил сохранённые учётные данные.",
    credential_missing: "Сначала сохраните учётные данные провайдера.",
    credential_unavailable: "Сохранённый секрет сейчас невозможно расшифровать.",
    invalid_provider_response: "Провайдер вернул неожиданный ответ.",
    provider_rate_limited: "Достигнут лимит запросов провайдера.",
    provider_resource_not_found: "Проверяемый ресурс провайдера не найден.",
    provider_unavailable: "Провайдер временно недоступен.",
    read_verified: "Ограниченное чтение подтверждено.",
    write_guarded:
      "Внешняя запись не выполнялась. Сначала закройте неподготовленные защитные условия.",
    write_ready:
      "Контур записи готов, но реальное действие всё равно требует подтверждённый ActionProposal и точную цель."
  };
  return messages[receipt.code] ?? receipt.message;
}
