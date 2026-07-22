"use client";

import { createContext, useContext } from "react";

import type { HeadquartersSnapshotResponse } from "./headquarters";

export type AssistantSnapshotSource = {
  workspaceId: string;
  snapshot: HeadquartersSnapshotResponse;
  refresh: () => Promise<HeadquartersSnapshotResponse>;
};

export type RegisterAssistantSnapshotSource = (
  source: AssistantSnapshotSource
) => () => void;

export function assistantSnapshotForWorkspace(
  source: AssistantSnapshotSource | null,
  workspaceId: string | null
): HeadquartersSnapshotResponse | null {
  return source !== null && workspaceId !== null && source.workspaceId === workspaceId
    ? source.snapshot
    : null;
}

export const AssistantSnapshotRegistrationContext =
  createContext<RegisterAssistantSnapshotSource | null>(null);

export function useAssistantSnapshotRegistration(): RegisterAssistantSnapshotSource | null {
  return useContext(AssistantSnapshotRegistrationContext);
}
