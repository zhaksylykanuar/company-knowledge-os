"use client";

import type { FormEvent } from "react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { PageHeader } from "../../components/PageHeader";
import { fetchWorkspaceMembers, provisionWorkspaceMember } from "../../lib/api";
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
  const workspace = session?.workspaces[0] ?? null;
  const workspaceId = workspace?.id ?? null;
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

  useEffect(() => {
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
    setProvisionPending(true);
    try {
      const response = await provisionWorkspaceMember(workspaceId, request);
      setMembers((current) => [
        ...current.filter((member) => member.user.id !== response.member.user.id),
        response.member
      ]);
      setMembersStatus("ready");
      setProvisionMessage(
        response.login_credential_set
          ? M.settings.teamProvisionSuccessWithLogin
          : M.settings.teamProvisionSuccessNoLogin
      );
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

  return (
    <>
      <PageHeader
        eyebrow={M.settings.eyebrow}
        title={M.settings.title}
        description={M.settings.description}
      />
      <section className="panel">
        <ul className="meta-list">
          <li>{M.settings.signedInAs} {session?.user.email ?? "…"}</li>
          <li>{M.settings.workspace} {session?.workspaces[0]?.name ?? M.settings.workspaceNone}</li>
        </ul>
        <div className="actions-row">
          <button className="button secondary" type="button" onClick={onSignOut}>
            {M.common.signOut}
          </button>
        </div>
      </section>
      <SettingsTeamPanelView
        canProvision={workspaceRole === "owner" || workspaceRole === "admin"}
        error={membersError}
        members={members}
        onProvision={onProvision}
        onRetry={() => setMembersReloadKey((current) => current + 1)}
        provisionError={provisionError}
        provisionMessage={provisionMessage}
        provisionPending={provisionPending}
        status={membersStatus}
        workspaceName={workspace?.name ?? null}
      />
      <form className="form panel" onSubmit={onChangePassword}>
        <h2>{M.settings.changePasswordTitle}</h2>
        <div className="field">
          <label htmlFor="current-password">{M.settings.currentPassword}</label>
          <input
            autoComplete="current-password"
            id="current-password"
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
            onChange={(event) => setNewPassword(event.target.value)}
            type="password"
            value={newPassword}
            required
          />
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
    </>
  );
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
  status,
  workspaceName
}: SettingsTeamPanelViewProps) {
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] =
    useState<WorkspaceMemberProvisionRequest["role"]>("member");
  const [initialPassword, setInitialPassword] = useState("");

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!onProvision || provisionPending) {
      return;
    }
    const succeeded = await onProvision({
      email,
      name: name.trim() ? name : null,
      role,
      initialPassword: initialPassword.trim() ? initialPassword : null
    });
    if (succeeded) {
      setEmail("");
      setName("");
      setRole("member");
      setInitialPassword("");
    }
  }

  return (
    <section className="panel" aria-labelledby="settings-team-title">
      <div className="section-header">
        <div>
          <span className="eyebrow">{M.settings.workspace}</span>
          <h2 id="settings-team-title">{M.settings.teamTitle}</h2>
        </div>
        <span className="badge">{M.settings.teamBoundary}</span>
      </div>
      <p className="muted">{M.settings.teamDescription}</p>
      {workspaceName ? <p className="muted">{workspaceName}</p> : null}

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
          <div className="work-list">
            {members.map((member) => (
              <article className="work-item" key={member.membership.id}>
                <div className="work-item-main">
                  <span className="badge">{roleLabel(member.membership.role)}</span>
                  <h3>{member.user.email}</h3>
                </div>
                <dl className="work-meta">
                  <div>
                    <dt>{M.settings.teamMemberRole}</dt>
                    <dd>{roleLabel(member.membership.role)}</dd>
                  </div>
                  <div>
                    <dt>{M.settings.teamMemberStatus}</dt>
                    <dd>{member.user.status}</dd>
                  </div>
                </dl>
                {member.user.name ? <p className="muted">{member.user.name}</p> : null}
              </article>
            ))}
          </div>
        </>
      ) : null}

      {canProvision ? (
        <form className="form" onSubmit={onSubmit}>
          <h3>{M.settings.teamProvisionTitle}</h3>
          <p className="muted">{M.settings.teamProvisionDescription}</p>
          <div className="field">
            <label htmlFor="team-member-email">{M.settings.teamProvisionEmail}</label>
            <input
              id="team-member-email"
              onChange={(event) => setEmail(event.target.value)}
              required
              type="email"
              value={email}
            />
          </div>
          <div className="field">
            <label htmlFor="team-member-name">{M.settings.teamProvisionName}</label>
            <input
              id="team-member-name"
              onChange={(event) => setName(event.target.value)}
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
          </div>
          <div className="field">
            <label htmlFor="team-member-password">
              {M.settings.teamProvisionPassword}
            </label>
            <input
              autoComplete="new-password"
              id="team-member-password"
              minLength={8}
              onChange={(event) => setInitialPassword(event.target.value)}
              type="password"
              value={initialPassword}
            />
            <p className="muted">{M.settings.teamProvisionPasswordHint}</p>
          </div>
          {provisionMessage ? <p className="success-text">{provisionMessage}</p> : null}
          {provisionError ? (
            <p className="error-text" role="alert">
              {provisionError}
            </p>
          ) : null}
          <div className="actions-row">
            <button className="button" disabled={provisionPending} type="submit">
              {provisionPending ? M.settings.teamProvisioning : M.settings.teamProvisionSubmit}
            </button>
          </div>
        </form>
      ) : (
        <p className="muted">{M.settings.teamProvisionForbidden}</p>
      )}
    </section>
  );
}

function roleLabel(role: WorkspaceMemberRole): string {
  if (role === "owner") {
    return M.settings.roleOwner;
  }
  if (role === "admin") {
    return M.settings.roleAdmin;
  }
  if (role === "viewer") {
    return M.settings.roleViewer;
  }
  return M.settings.roleMember;
}
