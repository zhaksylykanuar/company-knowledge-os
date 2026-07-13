import assert from "node:assert/strict";
import test from "node:test";

import { renderToStaticMarkup } from "react-dom/server";

import { isPublicShellPath } from "../components/AppShell";
import { TodayBoardView } from "../components/TodayBoard";
import { M } from "../lib/messages";
import { deriveTodayView, type TodayFacts } from "../lib/today";

const readyFacts: TodayFacts = {
  briefingCount: 2,
  candidateCount: 0,
  memberCount: 3,
  proposedDecisionCount: 0,
  role: "owner",
  sourceRecordCount: 4,
  workspaceId: "workspace-1",
  workspaceName: "Acme"
};

test("invite enrollment is public while onboarding stays session-protected", () => {
  assert.equal(isPublicShellPath("/start"), true);
  assert.equal(isPublicShellPath("/login"), true);
  assert.equal(isPublicShellPath("/onboarding"), false);
});

test("Today prioritizes real gaps before routine navigation", () => {
  const withoutSources = deriveTodayView({ ...readyFacts, sourceRecordCount: 0 });
  assert.equal(withoutSources.move.title, M.today.moves.addSourceTitle);
  assert.equal(withoutSources.move.href, "/connectors");

  const withDecision = deriveTodayView({
    ...readyFacts,
    proposedDecisionCount: 2
  });
  assert.equal(withDecision.move.title, M.today.moves.reviewDecisionsTitle);
  assert.equal(withDecision.move.href, "/actions?status=proposed");

  const withCandidates = deriveTodayView({ ...readyFacts, candidateCount: 3 });
  assert.equal(withCandidates.move.title, M.today.moves.reviewMapTitle);
  assert.equal(withCandidates.move.href, "/company-brain");
});

test("Today honors backend role boundaries", () => {
  const memberDecision = deriveTodayView({
    ...readyFacts,
    proposedDecisionCount: 1,
    role: "member"
  });
  assert.equal(memberDecision.move.title, M.today.moves.observeDecisionsTitle);

  const memberMap = deriveTodayView({
    ...readyFacts,
    candidateCount: 1,
    role: "member"
  });
  assert.equal(memberMap.move.title, M.today.moves.reviewMapTitle);

  const viewerMap = deriveTodayView({
    ...readyFacts,
    candidateCount: 1,
    role: "viewer"
  });
  assert.equal(viewerMap.move.title, M.today.moves.observeMapTitle);

  const viewerWithoutBriefing = deriveTodayView({
    ...readyFacts,
    briefingCount: 0,
    role: "viewer"
  });
  assert.equal(
    viewerWithoutBriefing.move.title,
    M.today.moves.observeBriefingTitle
  );
  assert.equal(viewerWithoutBriefing.move.href, "/briefings");
  assert.notEqual(
    viewerWithoutBriefing.move.description,
    M.today.moves.createBriefingDescription
  );

  const memberWithoutBriefing = deriveTodayView({
    ...readyFacts,
    briefingCount: 0,
    role: "member"
  });
  assert.equal(
    memberWithoutBriefing.move.title,
    M.today.moves.createBriefingTitle
  );
});

test("Today does not invent a move when required facts are unavailable", () => {
  const partial = deriveTodayView({
    ...readyFacts,
    briefingCount: null,
    candidateCount: null,
    proposedDecisionCount: null
  });
  assert.equal(partial.isPartial, true);
  assert.equal(partial.move.title, M.today.moves.refreshTitle);
  assert.equal(partial.move.href, null);
  assert.equal(partial.signals.length, 3);
  assert.equal(partial.signals[1].value, M.today.signalUnavailable);

  const unknownSourcesWithoutBriefing = deriveTodayView({
    ...readyFacts,
    briefingCount: 0,
    sourceRecordCount: null
  });
  assert.equal(unknownSourcesWithoutBriefing.move.title, M.today.moves.refreshTitle);
  assert.equal(unknownSourcesWithoutBriefing.move.href, null);

  const unknownTeam = deriveTodayView({
    ...readyFacts,
    memberCount: null
  });
  assert.equal(unknownTeam.isPartial, true);
  assert.equal(unknownTeam.move.title, M.today.moves.refreshTitle);
});

test("Today renders one main move and exactly three secondary signals", () => {
  const html = renderToStaticMarkup(
    <TodayBoardView facts={{ ...readyFacts, proposedDecisionCount: 2 }} />
  );

  assert.ok(html.includes(M.today.title));
  assert.ok(html.includes("Acme"));
  assert.ok(html.includes(M.today.moves.reviewDecisionsTitle));
  assert.equal((html.match(/class="today-primary-action"/g) ?? []).length, 1);
  assert.equal((html.match(/class="today-signal today-signal--/g) ?? []).length, 3);
  assert.ok(html.includes(M.today.sourceBoundary));
});

test("Today marks a capped decision count as a lower bound", () => {
  const view = deriveTodayView({
    ...readyFacts,
    proposedDecisionCount: 50,
    proposedDecisionCountIsLowerBound: true
  });

  assert.equal(view.signals[1].value, "≥50");
});

test("Today treats a truncated Company Map window as partial", () => {
  const withVisibleCandidates = deriveTodayView({
    ...readyFacts,
    candidateCount: 3,
    candidateCountIsLowerBound: true
  });
  assert.equal(withVisibleCandidates.isPartial, true);
  assert.equal(withVisibleCandidates.signals[2].value, "≥3");

  const withoutVisibleCandidates = deriveTodayView({
    ...readyFacts,
    candidateCount: 0,
    candidateCountIsLowerBound: true
  });
  assert.equal(withoutVisibleCandidates.isPartial, true);
  assert.equal(withoutVisibleCandidates.signals[2].value, M.today.signalPartial);
  assert.equal(withoutVisibleCandidates.move.title, M.today.moves.refreshTitle);
});
