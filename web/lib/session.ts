"use client";

import { createContext, useContext } from "react";

import type { AuthUser, AuthWorkspace } from "./auth";

// Session state provided by AuthGate from /api/v1/auth/me. The workspace id is
// derived from the session (no manual entry, no localStorage operator config).
export type SessionState = {
  user: AuthUser;
  workspaces: AuthWorkspace[];
  workspaceId: string | null;
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
