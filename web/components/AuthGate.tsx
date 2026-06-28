"use client";

import type { ReactNode } from "react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { fetchMe, logout } from "../lib/auth";
import { readOperatorConfig, writeOperatorConfig } from "../lib/config";
import { Sidebar } from "./Sidebar";

type GateState = "loading" | "authed" | "unauthenticated";

export function AuthGate({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [state, setState] = useState<GateState>("loading");

  useEffect(() => {
    let cancelled = false;
    fetchMe()
      .then((me) => {
        if (cancelled) {
          return;
        }
        if (me === null) {
          setState("unauthenticated");
          router.replace("/login");
          return;
        }
        // Bridge the session identity into the existing browser config so
        // current pages (which read config.workspaceId) keep working without a
        // rewrite. The operator API key is cleared — auth is the session cookie.
        const current = readOperatorConfig();
        const workspace = me.workspaces[0];
        writeOperatorConfig({
          ...current,
          apiKey: "",
          ownerEmail: me.user.email,
          workspaceId: workspace ? workspace.id : current.workspaceId
        });
        setState("authed");
      })
      .catch(() => {
        if (!cancelled) {
          setState("unauthenticated");
          router.replace("/login");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [router]);

  async function onLogout() {
    await logout();
    router.replace("/login");
  }

  if (state !== "authed") {
    return (
      <div className="auth-loading" aria-busy="true">
        Loading…
      </div>
    );
  }

  return (
    <div className="app-shell">
      <Sidebar />
      <main className="main">
        <div className="topbar">
          <button type="button" className="logout-button" onClick={onLogout}>
            Sign out
          </button>
        </div>
        <div className="content">{children}</div>
      </main>
    </div>
  );
}
