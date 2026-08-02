import assert from "node:assert/strict";
import test from "node:test";

import { renderToStaticMarkup } from "react-dom/server";

import {
  resolveSettingsWorkspace,
  settingsTeamMission,
  SettingsTeamPanelView
} from "../app/settings/page";
import type { AuthWorkspace } from "../lib/auth";
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

test("settings resolves the explicitly selected company instead of the first membership", () => {
  const workspaces: AuthWorkspace[] = [
    { id: "workspace-a", name: "Atlas", role: "owner", slug: "atlas" },
    { id: "workspace-b", name: "Boreal", role: "member", slug: "boreal" }
  ];

  assert.equal(
    resolveSettingsWorkspace(workspaces, "workspace-b")?.name,
    "Boreal"
  );
  assert.equal(resolveSettingsWorkspace(workspaces, "outside-memberships"), null);
  assert.equal(resolveSettingsWorkspace(workspaces, null), null);
});

test("settings mission reports loading failures and missing company honestly", () => {
  assert.equal(
    settingsTeamMission({
      canProvision: true,
      memberCount: 0,
      status: "error",
      workspaceName: "FounderOS"
    }).current,
    "Состав команды сейчас недоступен"
  );
  assert.equal(
    settingsTeamMission({
      canProvision: false,
      memberCount: 0,
      status: "missing",
      workspaceName: null
    }).current,
    "Компания ещё не выбрана"
  );
});

test("renders a roster-first team with Russian roles and collapsed provisioning", () => {
  const html = renderTeamPanel({
    provisionMessage: M.settings.teamProvisionSuccess
  });

  assert.ok(html.includes("Команда"));
  assert.ok(html.includes("2 человека"));
  assert.ok(html.includes("owner@example.test"));
  assert.ok(html.includes("member@example.test"));
  assert.ok(html.includes("Владелец"));
  assert.ok(html.includes("Участник"));
  assert.ok(html.includes("Активен"));
  assert.ok(html.includes("team-roster"));
  assert.ok(html.includes("team-invite-disclosure"));
  assert.ok(html.indexOf("team-roster") < html.indexOf("team-invite-disclosure"));
  assert.ok(html.includes(M.settings.teamBoundary));
  assert.ok(html.includes(M.settings.teamProvisionDescription));
  assert.ok(html.includes(M.settings.teamProvisionSuccess));
  assert.ok(html.includes("Добавить сотрудника"));
  assert.ok(html.includes("Добавить в команду"));
  assert.ok(html.includes(`value="admin"`));
  assert.ok(html.includes(`value="member"`));
  assert.ok(html.includes(`value="viewer"`));
  assert.doesNotMatch(html, /value="owner"/);
  assert.doesNotMatch(html, /email invite sent/i);
  assert.doesNotMatch(html, /identity provider write/i);
});

test("new teammate onboarding always uses a one-time self-setup link", () => {
  const html = renderTeamPanel();

  assert.ok(html.includes(M.settings.teamProvisionSetupLinkHint));
  assert.doesNotMatch(html, /id="team-member-password"/);
  assert.doesNotMatch(html, /initial.password/i);
});

test("renders generated one-time setup link for manual teammate onboarding", () => {
  const html = renderTeamPanel({
    provisionMessage: M.settings.teamProvisionSetupLinkGenerated,
    setupLinkExpiresAt: "2026-07-12T00:00:00Z",
    setupLinkUrl: "https://founderos.example/setup-password#token=one-time-token"
  });

  assert.ok(html.includes(M.settings.teamProvisionSetupLinkGenerated));
  assert.ok(html.includes(M.settings.teamProvisionSetupLinkLabel));
  assert.ok(html.includes("https://founderos.example/setup-password#token=one-time-token"));
  assert.ok(html.includes(M.settings.teamProvisionSetupLinkExpires));
  assert.ok(html.includes("2026-07-12T00:00:00Z"));
});

test("hides provisioning form for non-admin workspace roles", () => {
  const html = renderTeamPanel({ canProvision: false });

  assert.ok(
    html.includes("Добавить нового человека может владелец или администратор компании")
  );
  assert.doesNotMatch(html, /team-invite-disclosure/);
  assert.doesNotMatch(html, /Добавить в команду/);
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
