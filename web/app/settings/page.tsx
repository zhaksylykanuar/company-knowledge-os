"use client";

import type { FormEvent } from "react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { PageHeader } from "../../components/PageHeader";
import { changePassword, logout } from "../../lib/auth";
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
      setMessage("Password changed. Your other devices were signed out.");
      setCurrentPassword("");
      setNewPassword("");
    } catch {
      setError("Could not change the password. Check your current password.");
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
        eyebrow="Account"
        title="Your account"
        description="You are signed in with a session cookie. No operator API key is used in the browser."
      />
      <section className="panel">
        <ul className="meta-list">
          <li>Signed in as: {session?.user.email ?? "…"}</li>
          <li>Workspace: {session?.workspaces[0]?.name ?? "None"}</li>
        </ul>
        <div className="actions-row">
          <button className="button secondary" type="button" onClick={onSignOut}>
            Sign out
          </button>
        </div>
      </section>
      <form className="form panel" onSubmit={onChangePassword}>
        <h2>Change password</h2>
        <div className="field">
          <label htmlFor="current-password">Current password</label>
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
          <label htmlFor="new-password">New password</label>
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
            {pending ? "Changing…" : "Change password"}
          </button>
        </div>
      </form>
    </>
  );
}
