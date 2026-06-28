"use client";

import type { FormEvent } from "react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { LoginError, login } from "../../lib/auth";
import { M } from "../../lib/messages";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setPending(true);
    try {
      await login(email, password);
      router.replace("/");
    } catch (err) {
      setError(err instanceof LoginError ? err.message : M.auth.loginFailedUnknown);
      setPending(false);
    }
  }

  return (
    <main className="login-view">
      <form className="login-card" onSubmit={onSubmit} aria-label={M.auth.signIn}>
        <h1>{M.auth.title}</h1>
        <p className="muted">{M.auth.subtitle}</p>
        <label>
          {M.auth.email}
          <input
            type="email"
            name="email"
            autoComplete="username"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
          />
        </label>
        <label>
          {M.auth.password}
          <input
            type="password"
            name="password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
          />
        </label>
        {error ? (
          <p className="error" role="alert">
            {error}
          </p>
        ) : null}
        <button type="submit" disabled={pending}>
          {pending ? M.auth.signingIn : M.auth.signIn}
        </button>
      </form>
    </main>
  );
}
