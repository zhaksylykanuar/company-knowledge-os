import assert from "node:assert/strict";
import test from "node:test";

import type { AuthWorkspace } from "../lib/auth";
import {
  isWorkspaceSelectionValid,
  needsOnboardingRecovery,
  resolveWorkspaceSelection,
  workspaceSelectionStorageKey
} from "../lib/session";

const workspaces: AuthWorkspace[] = [
  { id: "workspace-a", name: "Atlas", slug: "atlas", role: "owner" },
  { id: "workspace-b", name: "Boreal", slug: "boreal", role: "member" }
];

test("selects the only workspace without asking an unnecessary question", () => {
  assert.equal(resolveWorkspaceSelection([workspaces[0]!], null), "workspace-a");
  assert.equal(resolveWorkspaceSelection([workspaces[0]!], "stale"), "workspace-a");
});

test("requires an explicit choice for several workspaces without valid persistence", () => {
  assert.equal(resolveWorkspaceSelection(workspaces, null), null);
  assert.equal(resolveWorkspaceSelection(workspaces, "workspace-from-another-user"), null);
  assert.equal(resolveWorkspaceSelection(workspaces, "workspace-b"), "workspace-b");
});

test("validates every workspace switch against the current session memberships", () => {
  assert.equal(isWorkspaceSelectionValid(workspaces, "workspace-a"), true);
  assert.equal(isWorkspaceSelectionValid(workspaces, "workspace-outside-session"), false);
  assert.equal(workspaceSelectionStorageKey("user-42"), "founderos.workspace.user-42");
});

test("routes a workspace-less account to recovery without looping onboarding", () => {
  assert.equal(needsOnboardingRecovery(0, "/dashboard"), true);
  assert.equal(needsOnboardingRecovery(0, "/settings"), true);
  assert.equal(needsOnboardingRecovery(0, "/onboarding"), false);
  assert.equal(needsOnboardingRecovery(1, "/dashboard"), false);
});

test("returns no selection for an account without a workspace", () => {
  assert.equal(resolveWorkspaceSelection([], null), null);
});
