"use client";

import type { FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { MissionStrip } from "../../components/MissionStrip";
import { PageHeader } from "../../components/PageHeader";
import { fetchWorkspaceMembers, provisionWorkspaceMember } from "../../lib/api";
import type { AuthWorkspace } from "../../lib/auth";
import { changePassword, logout } from "../../lib/auth";
import { M } from "../../lib/messages";
import { useSession } from "../../lib/session";
import type {
  WorkspaceMember,
  WorkspaceMemberProvisionRequest,
  WorkspaceMemberRole
} from "../../lib/types";

type MembersStatus = "error" | "loading" | "missing" | "ready";

type SettingsTeamPanelViewProps = {
  canProvision: boolean;
  error: string | null;
  members: WorkspaceMember[];
  onRetry?: () => void;
  onProvision?: (request: WorkspaceMemberProvisionRequest) => Promise<boolean> | boolean;
  provisionError: string | null;
  provisionMessage: string | null;
  provisionPending: boolean;
  setupLinkExpiresAt: string | null;
  setupLinkUrl: string | null;
  status: MembersStatus;
  workspaceName: string | null;
};

const PROVISION_ROLES: Array<Exclude<WorkspaceMemberRole, "owner">> = [
  "admin",
  "member",
  "viewer"
];

export default function SettingsPage() {
  const router = useRouter();
  const session = useSession();
  const workspaceId = session?.workspaceId ?? null;
  const workspace = resolveSettingsWorkspace(
    session?.workspaces ?? [],
    workspaceId
  );
  const workspaceRole = workspace?.role ?? null;
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [members, setMembers] = useState<WorkspaceMember[]>([]);
  const [membersError, setMembersError] = useState<string | null>(null);
  const [membersReloadKey, setMembersReloadKey] = useState(0);
  const [membersStatus, setMembersStatus] = useState<MembersStatus>("loading");
  const [provisionError, setProvisionError] = useState<string | null>(null);
  const [provisionMessage, setProvisionMessage] = useState<string | null>(null);
  const [provisionPending, setProvisionPending] = useState(false);
  const [setupLinkUrl, setSetupLinkUrl] = useState<string | null>(null);
  const [setupLinkExpiresAt, setSetupLinkExpiresAt] = useState<string | null>(null);

  useEffect(() => {
    void membersReloadKey;
    if (!workspaceId) {
      setMembers([]);
      setMembersError(null);
      setMembersStatus("missing");
      return;
    }

    let cancelled = false;
    setMembersStatus("loading");
    setMembersError(null);
    fetchWorkspaceMembers(workspaceId)
      .then((payload) => {
        if (cancelled) {
          return;
        }
        setMembers(payload.members);
        setMembersStatus("ready");
      })
      .catch((caught: unknown) => {
        if (cancelled) {
          return;
        }
        setMembers([]);
        setMembersError(caught instanceof Error ? caught.message : M.common.requestFailed);
        setMembersStatus("error");
      });

    return () => {
      cancelled = true;
    };
  }, [workspaceId, membersReloadKey]);

  async function onChangePassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage(null);
    setError(null);
    setPending(true);
    try {
      await changePassword(currentPassword, newPassword);
      setMessage(M.settings.changeSuccess);
      setCurrentPassword("");
      setNewPassword("");
    } catch {
      setError(M.settings.changeError);
    } finally {
      setPending(false);
    }
  }

  async function onSignOut() {
    await logout();
    router.replace("/login");
  }

  async function onProvision(request: WorkspaceMemberProvisionRequest): Promise<boolean> {
    if (!workspaceId) {
      return false;
    }
    setProvisionError(null);
    setProvisionMessage(null);
    setSetupLinkUrl(null);
    setSetupLinkExpiresAt(null);
    setProvisionPending(true);
    try {
      const response = await provisionWorkspaceMember(workspaceId, request);
      setMembers((current) => [
        ...current.filter((member) => member.user.id !== response.member.user.id),
        response.member
      ]);
      setMembersStatus("ready");
      setProvisionMessage(
        response.setup_link_generated
          ? M.settings.teamProvisionSetupLinkGenerated
          : M.settings.teamProvisionExistingAccount
      );
      if (response.setup_url_path) {
        const base = typeof window !== "undefined" ? window.location.origin : "";
        setSetupLinkUrl(`${base}${response.setup_url_path}`);
        setSetupLinkExpiresAt(response.setup_token_expires_at);
      }
      return true;
    } catch (caught: unknown) {
      setProvisionError(
        caught instanceof Error ? caught.message : M.settings.teamProvisionError
      );
      return false;
    } finally {
      setProvisionPending(false);
    }
  }

  const teamMission = settingsTeamMission({
    canProvision: workspaceRole === "owner" || workspaceRole === "admin",
    memberCount: members.length,
    status: membersStatus,
    workspaceName: workspace?.name ?? null
  });

  return (
    <>
      <Link className="onboarding-return" href="/onboarding#team">
        <span aria-hidden="true">←</span>
        Открыть шаг настройки команды
      </Link>
      <PageHeader
        eyebrow={M.settings.eyebrow}
        title={M.settings.title}
        description="Управляйте людьми компании, внешними подключениями и безопасностью локального аккаунта."
      />
      <MissionStrip
        action={teamMission.action}
        current={teamMission.current}
        outcome={teamMission.outcome}
        details={
          <p>
            {M.settings.description} Приглашения создаются только локально и не
            отправляются автоматически.
          </p>
        }
      />
      <Link className="settings-integrations-entry" href="/settings/integrations">
        <span className="settings-integrations-entry-icon" aria-hidden="true">
          ↗
        </span>
        <span>
          <strong>Интеграции и API</strong>
          <small>
            Секреты, scopes, проверка чтения и безопасный dry-run записи
          </small>
        </span>
        <span className="settings-integrations-entry-action">Открыть центр</span>
      </Link>
      <Link className="settings-integrations-entry" href="/settings/ai">
        <span className="settings-integrations-entry-icon" aria-hidden="true">
          ✦
        </span>
        <span>
          <strong>AI и приватность</strong>
          <small>
            Модель, зашифрованный ключ, лимиты и проверка без данных компании
          </small>
        </span>
        <span className="settings-integrations-entry-action">Настроить AI</span>
      </Link>
      <div className="settings-hub">
        <SettingsTeamPanelView
          canProvision={workspaceRole === "owner" || workspaceRole === "admin"}
          error={membersError}
          members={members}
          onProvision={onProvision}
          onRetry={() => setMembersReloadKey((current) => current + 1)}
          provisionError={provisionError}
          provisionMessage={provisionMessage}
          provisionPending={provisionPending}
          setupLinkExpiresAt={setupLinkExpiresAt}
          setupLinkUrl={setupLinkUrl}
          status={membersStatus}
          workspaceName={workspace?.name ?? null}
        />
        <section className="panel account-security" aria-labelledby="account-security-title">
          <div className="section-header account-security-header">
            <div>
              <span className="eyebrow">Аккаунт</span>
              <h2 id="account-security-title">Безопасность аккаунта</h2>
            </div>
            <span className="badge">Локальный доступ</span>
          </div>
          <div className="account-identity">
            <span className="account-avatar" aria-hidden="true">
              {accountInitial(session?.user.email ?? "")}
            </span>
            <div>
              <strong>{session?.user.email ?? "…"}</strong>
              <span>{workspace?.name ?? "Компания не выбрана"}</span>
            </div>
          </div>
          <details className="account-security-action">
            <summary>{M.settings.changePasswordTitle}</summary>
            <form className="form account-password-form" onSubmit={onChangePassword}>
              <div className="field">
                <label htmlFor="current-password">{M.settings.currentPassword}</label>
                <input
                  autoComplete="current-password"
                  id="current-password"
                  maxLength={256}
                  onChange={(event) => setCurrentPassword(event.target.value)}
                  type="password"
                  value={currentPassword}
                  required
                />
              </div>
              <div className="field">
                <label htmlFor="new-password">{M.settings.newPassword}</label>
                <input
                  autoComplete="new-password"
                  id="new-password"
                  maxLength={256}
                  minLength={8}
                  onChange={(event) => setNewPassword(event.target.value)}
                  type="password"
                  value={newPassword}
                  required
                />
                <span className="muted">{M.settings.newPasswordHint}</span>
              </div>
              {message ? <p className="success-text">{message}</p> : null}
              {error ? (
                <p className="error-text" role="alert">
                  {error}
                </p>
              ) : null}
              <div className="actions-row">
                <button className="button" disabled={pending} type="submit">
                  {pending ? M.settings.changing : M.settings.changePassword}
                </button>
              </div>
            </form>
          </details>
          <div className="account-signout-row">
            <div>
              <strong>Завершить работу</strong>
              <span>На этом устройстве потребуется войти снова.</span>
            </div>
            <button className="button secondary" type="button" onClick={onSignOut}>
              {M.common.signOut}
            </button>
          </div>
        </section>
      </div>
    </>
  );
}

export function resolveSettingsWorkspace(
  workspaces: AuthWorkspace[],
  workspaceId: string | null
): AuthWorkspace | null {
  if (workspaceId === null) {
    return null;
  }
  return workspaces.find((workspace) => workspace.id === workspaceId) ?? null;
}

export function SettingsTeamPanelView({
  canProvision,
  error,
  members,
  onProvision,
  onRetry,
  provisionError,
  provisionMessage,
  provisionPending,
  setupLinkExpiresAt,
  setupLinkUrl,
  status,
  workspaceName
}: SettingsTeamPanelViewProps) {
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] =
    useState<WorkspaceMemberProvisionRequest["role"]>("member");

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!onProvision || provisionPending) {
      return;
    }
    const succeeded = await onProvision({
      email,
      name: name.trim() ? name : null,
      role
    });
    if (succeeded) {
      setEmail("");
      setName("");
      setRole("member");
    }
  }

  return (
    <section className="panel settings-team" aria-labelledby="settings-team-title">
      <div className="section-header settings-team-header">
        <div>
          <span className="eyebrow">Компания</span>
          <h2 id="settings-team-title">Команда</h2>
        </div>
        <span className="badge">
          {status === "ready"
            ? `${members.length} ${peopleWord(members.length)}`
            : "Состав команды"}
        </span>
      </div>
      <p className="settings-team-intro">
        Люди, которые видят эту компанию и помогают принимать решения.
      </p>
      {workspaceName ? <p className="settings-workspace-name">{workspaceName}</p> : null}

      {status === "loading" ? <p className="state loading">{M.settings.teamLoading}</p> : null}
      {status === "missing" ? <p className="muted">{M.settings.teamNoWorkspace}</p> : null}
      {status === "error" ? (
        <section className="state error">
          <strong>{M.settings.teamUnavailableTitle}</strong>
          <p>{error ?? M.settings.teamUnavailableDescription}</p>
          {onRetry ? (
            <button className="button secondary" onClick={onRetry} type="button">
              {M.common.retry}
            </button>
          ) : null}
        </section>
      ) : null}

      {status === "ready" ? (
        <>
          {members.length === 0 ? <p className="muted">{M.settings.teamEmpty}</p> : null}
          <div aria-label="Состав команды" className="team-roster" role="list">
            {members.map((member) => (
              <article className="team-member-card" key={member.membership.id}>
                <span className="team-member-avatar" aria-hidden="true">
                  {memberInitial(member)}
                </span>
                <div className="team-member-main">
                  <h3>{member.user.name ?? member.user.email}</h3>
                  {member.user.name ? <span>{member.user.email}</span> : null}
                </div>
                <div className="team-member-state">
                  <span className={`team-role team-role--${member.membership.role}`}>
                    {roleLabel(member.membership.role)}
                  </span>
                  <small>{memberStatusLabel(member.user.status)}</small>
                </div>
              </article>
            ))}
          </div>
        </>
      ) : null}

      {canProvision ? (
        <details className="team-invite-disclosure">
          <summary className="team-invite-summary">
            <span aria-hidden="true">＋</span>
            Добавить сотрудника
          </summary>
          <form className="form team-invite-form" onSubmit={onSubmit}>
            <div className="team-invite-heading">
              <h3>Новый участник команды</h3>
              <p>Укажите человека и выберите, что ему будет доступно.</p>
            </div>
            <div className="field">
              <label htmlFor="team-member-email">{M.settings.teamProvisionEmail}</label>
              <input
                id="team-member-email"
                maxLength={320}
                onChange={(event) => setEmail(event.target.value)}
                required
                type="email"
                value={email}
              />
            </div>
            <div className="field">
              <label htmlFor="team-member-name">Имя</label>
              <input
                id="team-member-name"
                onChange={(event) => setName(event.target.value)}
                placeholder="Как показать человека в компании"
                type="text"
                value={name}
              />
            </div>
            <div className="field">
              <label htmlFor="team-member-role">{M.settings.teamProvisionRole}</label>
              <select
                id="team-member-role"
                onChange={(event) =>
                  setRole(event.target.value as WorkspaceMemberProvisionRequest["role"])
                }
                value={role}
              >
                {PROVISION_ROLES.map((option) => (
                  <option key={option} value={option}>
                    {roleLabel(option)}
                  </option>
                ))}
              </select>
              <span className="muted">{roleHint(role)}</span>
            </div>
            <p className="team-invite-note">
              После добавления появится одноразовая ссылка. Передайте её сотруднику
              лично — пароль он задаст сам.
            </p>
            {provisionMessage ? <p className="success-text">{provisionMessage}</p> : null}
            {setupLinkUrl ? (
              <div
                aria-label={M.settings.teamProvisionSetupLinkLabel}
                className="callout setup-link-card"
                role="region"
              >
                <strong>{M.settings.teamProvisionSetupLinkLabel}</strong>
                <p className="setup-link-value">{setupLinkUrl}</p>
                {setupLinkExpiresAt ? (
                  <p className="muted">
                    {M.settings.teamProvisionSetupLinkExpires}: {setupLinkExpiresAt}
                  </p>
                ) : null}
              </div>
            ) : null}
            {provisionError ? (
              <p className="error-text" role="alert">
                {provisionError}
              </p>
            ) : null}
            <div className="actions-row">
              <button className="button" disabled={provisionPending} type="submit">
                {provisionPending ? M.settings.teamProvisioning : "Добавить в команду"}
              </button>
            </div>
          </form>
        </details>
      ) : (
        <p className="settings-permission-note">
          Добавить нового человека может владелец или администратор компании.
        </p>
      )}

      <details className="technical-boundary team-technical-details">
        <summary>Как работает приглашение</summary>
        <div>
          <p>{M.settings.teamProvisionDescription}</p>
          <p>{M.settings.teamProvisionSetupLinkHint}</p>
          <p>{M.settings.teamDescription}</p>
          <p>{M.settings.teamBoundary}</p>
        </div>
      </details>
    </section>
  );
}

function roleLabel(role: WorkspaceMemberRole): string {
  if (role === "owner") {
    return "Владелец";
  }
  if (role === "admin") {
    return "Администратор";
  }
  if (role === "viewer") {
    return "Наблюдатель";
  }
  return "Участник";
}

function roleHint(role: WorkspaceMemberProvisionRequest["role"]): string {
  if (role === "admin") {
    return "Управляет командой, источниками и решениями.";
  }
  if (role === "viewer") {
    return "Смотрит данные, но ничего не меняет.";
  }
  return "Работает с данными и создаёт предложения решений.";
}

function memberStatusLabel(status: string): string {
  return status === "active" ? "Активен" : "Доступ приостановлен";
}

function memberInitial(member: WorkspaceMember): string {
  return accountInitial(member.user.name ?? member.user.email);
}

function accountInitial(value: string): string {
  const normalized = value.trim();
  return normalized ? normalized.slice(0, 1).toUpperCase() : "?";
}

function peopleWord(count: number): string {
  const mod100 = count % 100;
  const mod10 = count % 10;
  if (mod100 >= 11 && mod100 <= 14) {
    return "человек";
  }
  if (mod10 === 1) {
    return "человек";
  }
  if (mod10 >= 2 && mod10 <= 4) {
    return "человека";
  }
  return "человек";
}

export function settingsTeamMission({
  canProvision,
  memberCount,
  status,
  workspaceName
}: {
  canProvision: boolean;
  memberCount: number;
  status: MembersStatus;
  workspaceName: string | null;
}): { action: string; current: string; outcome: string } {
  if (status === "missing") {
    return {
      action: "Откройте настройку компании",
      current: "Компания ещё не выбрана",
      outcome: "Появится пространство для команды"
    };
  }
  if (status === "error") {
    return {
      action: "Нажмите «Повторить» в блоке «Команда»",
      current: "Состав команды сейчас недоступен",
      outcome: "FounderOS попробует загрузить людей снова"
    };
  }
  if (status === "loading") {
    return {
      action: "Откройте безопасность аккаунта",
      current: "Собираем текущий состав команды",
      outcome: "Команда появится здесь после загрузки"
    };
  }
  return {
    action: canProvision
      ? "Откройте «Добавить сотрудника» или безопасность аккаунта"
      : "Проверьте состав команды или безопасность аккаунта",
    current: `${memberCount} ${peopleWord(memberCount)} в команде ${workspaceName ?? "компании"}`,
    outcome: "У каждого человека будет понятная роль и доступ"
  };
}
