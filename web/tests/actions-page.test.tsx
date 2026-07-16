import assert from "node:assert/strict";
import test from "node:test";

import ActionsPage from "../app/actions/page";
import { ActionProposalsPanel } from "../components/ActionProposalsPanel";

const PROPOSAL_ID = "11111111-1111-4111-8111-111111111111";

test("actions route forwards an exact proposal deep link to the mission panel", async () => {
  const page = await ActionsPage({
    searchParams: Promise.resolve({
      proposal: PROPOSAL_ID,
      status: "proposed"
    })
  });

  assert.equal(page.type, ActionProposalsPanel);
  assert.equal(page.props.initialProposalId, PROPOSAL_ID);
  assert.equal(page.props.initialStatusFilter, "proposed");
});

test("actions route rejects a malformed proposal selector", async () => {
  const page = await ActionsPage({
    searchParams: Promise.resolve({ proposal: `${PROPOSAL_ID}\u0000` })
  });

  assert.equal(page.type, ActionProposalsPanel);
  assert.equal(page.props.initialProposalId, null);
});
