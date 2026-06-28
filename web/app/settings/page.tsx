"use client";

import type { FormEvent } from "react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { PageHeader } from "../../components/PageHeader";
import { changePassword, logout } from "../../lib/auth";
import { M } from "../../lib/messages";
import { useSession } from "../../lib/session";

export default function SettingsPage() {
  const router = useRouter();
  const session = useSession();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

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
