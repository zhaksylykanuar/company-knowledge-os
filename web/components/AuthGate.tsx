"use client";

import type { ReactNode } from "react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import type { MeResponse } from "../lib/auth";
import { fetchMe, logout } from "../lib/auth";
import { M } from "../lib/messages";
import { SessionContext } from "../lib/session";
import { Sidebar } from "./Sidebar";

export function AuthGate({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [me, setMe] = useState<MeResponse | null>(null);
  const [resolved, setResolved] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetchMe()
      .then((result) => {
        if (cancelled) {
          return;
        }
        if (result === null) {
          router.replace("/login");
        } else {
          setMe(result);
        }
        setResolved(true);
      })
      .catch(() => {
        if (!cancelled) {
          router.replace("/login");
          setResolved(true);
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

  if (!resolved || me === null) {
    return (
      <div className="auth-loading" aria-busy="true">
        {M.common.loading}…
      </div>
    );
  }

  const session = {
    user: me.user,
    workspaces: me.workspaces,
    workspaceId: me.workspaces[0]?.id ?? null
  };

  return (
    <SessionContext.Provider value={session}>
      <div className="app-shell">
        <Sidebar />
        <main className="main">
          <div className="topbar">
            <span className="topbar-user">{me.user.email}</span>
            <button type="button" className="logout-button" onClick={onLogout}>
              {M.common.signOut}
            </button>
          </div>
          <div className="content">{children}</div>
        </main>
      </div>
    </SessionContext.Provider>
  );
}
