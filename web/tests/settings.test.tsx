import assert from "node:assert/strict";
import test from "node:test";

import { renderToStaticMarkup } from "react-dom/server";

import { SettingsTeamPanelView } from "../app/settings/page";
import { buildWorkspaceMembersPath } from "../lib/api";
import { M } from "../lib/messages";
import type { WorkspaceMember } from "../lib/types";

const members: WorkspaceMember[] = [
  {
    user: {
      id: "user-owner",
      email: "owner@example.test",
      name: "Owner",
      status: "active"
    },
    membership: {
      id: "membership-owner",
      role: "owner",
      user_id: "user-owner",
      workspace_id: "workspace-1"
    }
  },
  {
    user: {
      id: "user-member",
      email: "member@example.test",
      name: null,
      status: "active"
    },
    membership: {
      id: "membership-member",
      role: "member",
      user_id: "user-member",
      workspace_id: "workspace-1"
    }
  }
];

function renderTeamPanel(
  props: Partial<Parameters<typeof SettingsTeamPanelView>[0]> = {}
): string {
  return renderToStaticMarkup(
    <SettingsTeamPanelView
      canProvision={props.canProvision ?? true}
      error={props.error ?? null}
      members={props.members ?? members}
      onProvision={props.onProvision}
      onRetry={props.onRetry}
      provisionError={props.provisionError ?? null}
      provisionMessage={props.provisionMessage ?? null}
      provisionPending={props.provisionPending ?? false}
      setupLinkExpiresAt={props.setupLinkExpiresAt ?? null}
      setupLinkUrl={props.setupLinkUrl ?? null}
      status={props.status ?? "ready"}
      workspaceName={props.workspaceName ?? "FounderOS"}
    />
  );
}

test("builds the workspace members API path", () => {
  assert.equal(
    buildWorkspaceMembersPath("workspace/with slash"),
    "/api/v1/workspaces/workspace%2Fwith%20slash/members"
  );
});

test("renders local workspace members and provisioning boundary", () => {
  const html = renderTeamPanel({
    provisionMessage: M.settings.teamProvisionSuccess
  });

  assert.ok(html.includes(M.settings.teamTitle));
  assert.ok(html.includes("owner@example.test"));
  assert.ok(html.includes("member@example.test"));
  assert.ok(html.includes(M.settings.roleOwner));
  assert.ok(html.includes(M.settings.roleMember));
  assert.ok(html.includes(M.settings.teamBoundary));
  assert.ok(html.includes(M.settings.teamProvisionDescription));
  assert.ok(html.includes(M.settings.teamProvisionSuccess));
  assert.ok(html.includes(M.settings.teamProvisionSubmit));
  assert.ok(html.includes(`value="admin"`));
  assert.ok(html.includes(`value="member"`));
  assert.ok(html.includes(`value="viewer"`));
  assert.doesNotMatch(html, /value="owner"/);
  assert.doesNotMatch(html, /email invite sent/i);
  assert.doesNotMatch(html, /identity provider write/i);
});

test("exposes an optional initial-password field so a teammate can sign in", () => {
  const html = renderTeamPanel();

  assert.ok(html.includes(M.settings.teamProvisionPassword));
  assert.ok(html.includes(M.settings.teamProvisionPasswordHint));
  assert.ok(html.includes(M.settings.teamProvisionSetupLink));
  assert.ok(html.includes(M.settings.teamProvisionSetupLinkHint));
  assert.ok(html.includes('type="password"'));
  assert.match(html, /minlength="8"/i);
  assert.ok(html.includes('id="team-member-password"'));
});

test("renders generated one-time setup link for manual teammate onboarding", () => {
  const html = renderTeamPanel({
    provisionMessage: M.settings.teamProvisionSetupLinkGenerated,
    setupLinkExpiresAt: "2026-07-12T00:00:00Z",
    setupLinkUrl: "https://founderos.example/setup-password?token=one-time-token"
  });

  assert.ok(html.includes(M.settings.teamProvisionSetupLinkGenerated));
  assert.ok(html.includes(M.settings.teamProvisionSetupLinkLabel));
  assert.ok(html.includes("https://founderos.example/setup-password?token=one-time-token"));
  assert.ok(html.includes(M.settings.teamProvisionSetupLinkExpires));
  assert.ok(html.includes("2026-07-12T00:00:00Z"));
});

test("hides provisioning form for non-admin workspace roles", () => {
  const html = renderTeamPanel({ canProvision: false });

  assert.ok(html.includes(M.settings.teamProvisionForbidden));
  assert.doesNotMatch(html, new RegExp(M.settings.teamProvisionSubmit));
});

test("renders missing loading and error states safely", () => {
  assert.ok(
    renderTeamPanel({ members: [], status: "missing", workspaceName: null }).includes(
      M.settings.teamNoWorkspace
    )
  );
  assert.ok(
    renderTeamPanel({ members: [], status: "loading" }).includes(
      M.settings.teamLoading
    )
  );
  const errorHtml = renderTeamPanel({
    error: "members backend unavailable",
    members: [],
    onRetry: () => undefined,
    status: "error"
  });
  assert.ok(errorHtml.includes(M.settings.teamUnavailableTitle));
  assert.match(errorHtml, /members backend unavailable/);
  assert.ok(errorHtml.includes(M.common.retry));
});
