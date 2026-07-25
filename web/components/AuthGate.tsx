"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import type { MeResponse } from "../lib/auth";
import { fetchMe, logout } from "../lib/auth";
import {
  AssistantSnapshotRegistrationContext,
  type AssistantSnapshotSource
} from "../lib/assistant-snapshot";
import { M } from "../lib/messages";
import {
  isWorkspaceSelectionValid,
  needsOnboardingRecovery,
  resolveWorkspaceSelection,
  SessionContext,
  workspaceSelectionStorageKey
} from "../lib/session";
import {
  MobilePrimaryNavigation,
  Sidebar
} from "./Sidebar";
import { CompanyAssistant } from "./CompanyAssistant";
import { WorkspaceChoice, WorkspaceSelector } from "./WorkspaceSelector";
import styles from "./workspace-selector.module.css";

export function AuthGate({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [me, setMe] = useState<MeResponse | null>(null);
  const [resolved, setResolved] = useState(false);
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const [workspaceSelectionResolved, setWorkspaceSelectionResolved] = useState(false);
  const [externalOperationPending, setExternalOperationPending] = useState(false);
  const [assistantSnapshotSource, setAssistantSnapshotSource] =
    useState<AssistantSnapshotSource | null>(null);
  const shellRef = useRef<HTMLDivElement | null>(null);

  const registerAssistantSnapshotSource = useCallback(
    (source: AssistantSnapshotSource) => {
      setAssistantSnapshotSource(source);
      return () => {
        setAssistantSnapshotSource((current) =>
          current === source ? null : current
        );
      };
    },
    []
  );

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
    setAssistantSnapshotSource(null);
  }, [workspaceId]);

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
    if (
      externalOperationPending ||
      me === null ||
      !isWorkspaceSelectionValid(me.workspaces, nextWorkspaceId)
    ) {
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
    externalOperationPending,
    user: me.user,
    workspaces: me.workspaces,
    workspaceId,
    selectWorkspace: onSelectWorkspace,
    setExternalOperationPending
  };

  const workspaceControl = workspaceId ? (
    <WorkspaceSelector
      disabled={externalOperationPending}
      onSelect={onSelectWorkspace}
      workspaceId={workspaceId}
      workspaces={me.workspaces}
    />
  ) : null;

  if (pathname === "/onboarding") {
    return (
      <SessionContext.Provider value={session}>
        <div className={styles.focusedShell}>
          <header className={styles.focusedTopbar} inert={externalOperationPending}>
            <Link
              className={styles.wordmark}
              href="/dashboard"
              aria-label={M.nav.brandHomeLabel}
            >
              <span aria-hidden="true">F</span>
              FounderOS
            </Link>
            <div className={styles.focusedActions}>
              {workspaceControl}
              <ProfileMenu onLogout={onLogout} user={me.user} />
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
      <AssistantSnapshotRegistrationContext.Provider
        value={registerAssistantSnapshotSource}
      >
        <div className="app-shell" ref={shellRef}>
          <Sidebar locked={externalOperationPending} />
          <main className="main">
            <div className="topbar" inert={externalOperationPending}>
              {pathname === "/ask" ? null : (
                <CompanyAssistant
                  backgroundRef={shellRef}
                  disabled={externalOperationPending}
                  snapshotSource={assistantSnapshotSource}
                  workspaceId={workspaceId}
                />
              )}
              {workspaceControl}
              <ProfileMenu onLogout={onLogout} user={me.user} />
            </div>
            <div className="content" key={workspaceId ?? "no-workspace"}>
              {children}
            </div>
          </main>
          <MobilePrimaryNavigation locked={externalOperationPending} />
        </div>
      </AssistantSnapshotRegistrationContext.Provider>
    </SessionContext.Provider>
  );
}

export function ProfileMenu({
  onLogout,
  user
}: {
  onLogout: () => Promise<void>;
  user: MeResponse["user"];
}) {
  const label = user.name?.trim() || user.email;
  const initial = label.slice(0, 1).toLocaleUpperCase("ru-RU") || "F";

  return (
    <details className="profile-menu">
      <summary aria-label="Открыть меню аккаунта">
        <span className="profile-menu-avatar" aria-hidden="true">{initial}</span>
        <span className="profile-menu-label">{label}</span>
        <span className="profile-menu-chevron" aria-hidden="true">⌄</span>
      </summary>
      <div className="profile-menu-popover">
        <div>
          <small>Локальный аккаунт</small>
          <strong>{label}</strong>
          {user.name?.trim() ? <span>{user.email}</span> : null}
        </div>
        <Link className="profile-menu-settings-link" href="/settings">
          {M.nav.settings}
        </Link>
        <button type="button" onClick={() => void onLogout()}>
          {M.common.signOut}
        </button>
      </div>
    </details>
  );
}
