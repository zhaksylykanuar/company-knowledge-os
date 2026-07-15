"use client";

import { createContext, useContext } from "react";

import type { AuthUser, AuthWorkspace } from "./auth";

// Session state provided by AuthGate from /api/v1/auth/me. The workspace id is
// derived from the session (no manual entry, no localStorage operator config).
export type SessionState = {
  externalOperationPending: boolean;
  user: AuthUser;
  workspaces: AuthWorkspace[];
  workspaceId: string | null;
  selectWorkspace: (workspaceId: string) => void;
  setExternalOperationPending: (pending: boolean) => void;
};

export const SessionContext = createContext<SessionState | null>(null);

export function useSession(): SessionState | null {
  return useContext(SessionContext);
}

// The current workspace id derived from the session, or null while resolving /
// when the account has no workspace yet.
export function useWorkspaceId(): string | null {
  return useContext(SessionContext)?.workspaceId ?? null;
}

export function workspaceSelectionStorageKey(userId: string): string {
  return `founderos.workspace.${userId}`;
}

// A single workspace is unambiguous. With several workspaces we never silently
// pick the first one: a persisted id must still belong to the current session,
// otherwise the user chooses explicitly.
export function resolveWorkspaceSelection(
  workspaces: AuthWorkspace[],
  persistedWorkspaceId: string | null
): string | null {
  if (workspaces.length === 0) {
    return null;
  }
  if (workspaces.length === 1) {
    return workspaces[0]?.id ?? null;
  }
  return workspaces.some((workspace) => workspace.id === persistedWorkspaceId)
    ? persistedWorkspaceId
    : null;
}

export function isWorkspaceSelectionValid(
  workspaces: AuthWorkspace[],
  workspaceId: string
): boolean {
  return workspaces.some((workspace) => workspace.id === workspaceId);
}

export function selectedWorkspaceRole(
  workspaces: AuthWorkspace[],
  workspaceId: string | null
): string | null {
  if (!workspaceId) {
    return null;
  }
  return workspaces.find((workspace) => workspace.id === workspaceId)?.role ?? null;
}

export function canAdministerSelectedWorkspace(
  workspaces: AuthWorkspace[],
  workspaceId: string | null
): boolean {
  const role = selectedWorkspaceRole(workspaces, workspaceId);
  return role === "owner" || role === "admin";
}

export function needsOnboardingRecovery(
  workspaceCount: number,
  pathname: string
): boolean {
  return workspaceCount === 0 && pathname !== "/onboarding";
}
