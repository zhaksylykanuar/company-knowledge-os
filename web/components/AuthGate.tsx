"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import type { MeResponse } from "../lib/auth";
import { fetchMe, logout } from "../lib/auth";
import { M } from "../lib/messages";
import {
  isWorkspaceSelectionValid,
  needsOnboardingRecovery,
  resolveWorkspaceSelection,
  SessionContext,
  workspaceSelectionStorageKey
} from "../lib/session";
import { ContextNavigation, Sidebar } from "./Sidebar";
import { WorkspaceChoice, WorkspaceSelector } from "./WorkspaceSelector";
import styles from "./workspace-selector.module.css";

export function AuthGate({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [me, setMe] = useState<MeResponse | null>(null);
  const [resolved, setResolved] = useState(false);
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const [workspaceSelectionResolved, setWorkspaceSelectionResolved] = useState(false);

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

  useEffect(() => {
    if (me === null) {
      return;
    }

    const storageKey = workspaceSelectionStorageKey(me.user.id);
    let persistedWorkspaceId: string | null = null;
    try {
      persistedWorkspaceId = window.localStorage.getItem(storageKey);
    } catch {
      // A blocked browser store must not block sign-in. Multi-workspace users
      // simply choose again for this session.
    }

    const selection = resolveWorkspaceSelection(me.workspaces, persistedWorkspaceId);
    setWorkspaceId(selection);
    setWorkspaceSelectionResolved(true);

    if (persistedWorkspaceId !== null && selection !== persistedWorkspaceId) {
      try {
        window.localStorage.removeItem(storageKey);
      } catch {
        // Storage is optional; the validated in-memory selection is authoritative.
      }
    }
  }, [me]);

  useEffect(() => {
    if (
      resolved &&
      me !== null &&
      needsOnboardingRecovery(me.workspaces.length, pathname)
    ) {
      router.replace("/onboarding");
    }
  }, [me, pathname, resolved, router]);

  async function onLogout() {
    await logout();
    router.replace("/login");
  }

  function onSelectWorkspace(nextWorkspaceId: string) {
    if (me === null || !isWorkspaceSelectionValid(me.workspaces, nextWorkspaceId)) {
      return;
    }
    setWorkspaceId(nextWorkspaceId);
    try {
      window.localStorage.setItem(
        workspaceSelectionStorageKey(me.user.id),
        nextWorkspaceId
      );
    } catch {
      // The selector still works for this page load when browser storage is blocked.
    }
  }

  if (!resolved || me === null || !workspaceSelectionResolved) {
    return (
      <div className="auth-loading" aria-busy="true">
        {M.common.loading}…
      </div>
    );
  }

  if (needsOnboardingRecovery(me.workspaces.length, pathname)) {
    return (
      <div className="auth-loading" aria-busy="true">
        Открываем настройку компании…
      </div>
    );
  }

  if (me.workspaces.length > 1 && workspaceId === null) {
    return (
      <WorkspaceChoice
        onLogout={() => void onLogout()}
        onSelect={onSelectWorkspace}
        workspaces={me.workspaces}
      />
    );
  }

  const session = {
    user: me.user,
    workspaces: me.workspaces,
    workspaceId,
    selectWorkspace: onSelectWorkspace
  };

  const workspaceControl = workspaceId ? (
    <WorkspaceSelector
      onSelect={onSelectWorkspace}
      workspaceId={workspaceId}
      workspaces={me.workspaces}
    />
  ) : null;

  if (pathname === "/onboarding") {
    return (
      <SessionContext.Provider value={session}>
        <div className={styles.focusedShell}>
          <header className={styles.focusedTopbar}>
            <Link className={styles.wordmark} href="/dashboard" aria-label="FounderOS — Сегодня">
              <span aria-hidden="true">F</span>
              FounderOS
            </Link>
            <div className={styles.focusedActions}>
              {workspaceControl}
              <span className={styles.focusedUser}>{me.user.email}</span>
              <button type="button" className={styles.signOut} onClick={onLogout}>
                {M.common.signOut}
              </button>
            </div>
          </header>
          <main className={styles.focusedMain} key={workspaceId ?? "no-workspace"}>
            {children}
          </main>
        </div>
      </SessionContext.Provider>
    );
  }

  return (
    <SessionContext.Provider value={session}>
      <div className="app-shell">
        <Sidebar />
        <main className="main">
          <div className="topbar">
            {workspaceControl}
            <span className="topbar-user">{me.user.email}</span>
            <button type="button" className="logout-button" onClick={onLogout}>
              {M.common.signOut}
            </button>
          </div>
          <ContextNavigation />
          <div className="content" key={workspaceId ?? "no-workspace"}>
            {children}
          </div>
        </main>
      </div>
    </SessionContext.Provider>
  );
}
