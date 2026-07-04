"use client";

import type { FormEvent } from "react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { setupPassword } from "../../lib/auth";
import { M } from "../../lib/messages";

export default function SetupPasswordPage() {
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null);
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    setToken(params.get("token"));
  }, []);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) {
      setError(M.auth.setupMissingToken);
      return;
    }
    setError(null);
    setPending(true);
    try {
      await setupPassword(token, password);
      router.replace("/");
    } catch {
      setError(M.auth.setupFailed);
      setPending(false);
    }
  }

  return (
    <main className="login-view">
      <form className="login-card" onSubmit={onSubmit} aria-label={M.auth.setupSubmit}>
        <h1>{M.auth.setupTitle}</h1>
        <p className="muted">{M.auth.setupSubtitle}</p>
        {!token ? <p className="error">{M.auth.setupMissingToken}</p> : null}
        <label>
          {M.auth.setupPassword}
          <input
            autoComplete="new-password"
            minLength={8}
            onChange={(event) => setPassword(event.target.value)}
            required
            type="password"
            value={password}
          />
        </label>
        {error ? (
          <p className="error" role="alert">
            {error}
          </p>
        ) : null}
        <button disabled={pending || !token} type="submit">
          {pending ? M.auth.setupSubmitting : M.auth.setupSubmit}
        </button>
      </form>
    </main>
  );
}
