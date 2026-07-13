import assert from "node:assert/strict";
import test from "node:test";

import {
  deriveOnboardingProgress,
  firstIncompleteRequiredStep,
  onboardingStepFromHash,
  type OnboardingSnapshot
} from "../lib/onboarding";
import type {
  CompanyMapResponse,
  CompanyBrainResponse,
  ConnectorRegistryResponse,
  WorkspaceMembersResponse
} from "../lib/types";

type SnapshotOptions = {
  connected?: number;
  sourceRecords?: number;
  internalPeople?: number;
  externalPeople?: number;
  organizations?: number;
  touchpoints?: number;
  members?: number;
  unavailable?: OnboardingSnapshot["unavailable"];
  missing?: Array<"companyBrain" | "connectors" | "companyMap" | "members">;
};

function snapshot(options: SnapshotOptions = {}): OnboardingSnapshot {
  const missing = new Set(options.missing ?? []);
  return {
    workspaceId: "workspace-1",
    connectors: missing.has("connectors")
      ? null
      : ({ summary: { connected: options.connected ?? 0 } } as ConnectorRegistryResponse),
    companyBrain: missing.has("companyBrain")
      ? null
      : ({
          source_records: {
            total: options.sourceRecords ?? 0,
            by_provider: [],
            by_record_type: []
          }
        } as unknown as CompanyBrainResponse),
    companyMap: missing.has("companyMap")
      ? null
      : ({
          summary: {
            internal_people: options.internalPeople ?? 1,
            confirmed_external_people: options.externalPeople ?? 0,
            confirmed_organizations: options.organizations ?? 0,
            touchpoints_in_window: options.touchpoints ?? 0
          }
        } as CompanyMapResponse),
    members: missing.has("members")
      ? null
      : ({
          members: Array.from({ length: options.members ?? 1 }, (_, index) => ({
            user: {
              id: `user-${index}`,
              email: `user-${index}@example.test`,
              name: null,
              status: "active"
            },
            membership: {
              id: `membership-${index}`,
              role: index === 0 ? "owner" : "member",
              user_id: `user-${index}`,
              workspace_id: "workspace-1"
            }
          }))
        } as WorkspaceMembersResponse),
    unavailable: options.unavailable ?? []
  };
}

test("derives onboarding readiness only from confirmed source and map data", () => {
  const progress = deriveOnboardingProgress(
    snapshot({ connected: 1, internalPeople: 1, members: 2, sourceRecords: 5 })
  );

  assert.equal(progress.checks.company.state, "complete");
  assert.equal(progress.checks.source.state, "complete");
  assert.equal(progress.checks.map.state, "complete");
  assert.equal(progress.checks.team.state, "complete");
  assert.equal(progress.checks.ready.state, "complete");
  assert.equal(progress.completedCount, 4);
  assert.equal(progress.ready, true);
});

test("keeps skipped source and team steps visibly pending", () => {
  const progress = deriveOnboardingProgress(
    snapshot({ connected: 0, internalPeople: 1, members: 1, touchpoints: 0 })
  );

  assert.equal(progress.checks.source.state, "pending");
  assert.equal(progress.checks.team.state, "pending");
  assert.match(progress.checks.source.evidence, /пока нет/i);
  assert.match(progress.checks.team.evidence, /единственный участник/i);
  assert.equal(progress.ready, false);
  assert.equal(progress.completedCount, 2);
});

test("keeps a configured connection pending until canonical records exist", () => {
  const progress = deriveOnboardingProgress(
    snapshot({ connected: 1, internalPeople: 1, members: 1, sourceRecords: 0 })
  );

  assert.equal(progress.checks.source.state, "pending");
  assert.match(progress.checks.source.evidence, /настроено: 1/i);
  assert.match(progress.checks.source.evidence, /записей пока нет/i);
  assert.equal(progress.ready, false);
});

test("treats canonical Company Brain source records as a real first source", () => {
  const progress = deriveOnboardingProgress(
    snapshot({ connected: 0, internalPeople: 1, members: 1, sourceRecords: 3 })
  );

  assert.equal(progress.checks.source.state, "complete");
  assert.match(progress.checks.source.evidence, /записей: 3/i);
  assert.equal(progress.checks.ready.state, "complete");
  assert.equal(progress.ready, true);
  // Inviting a team is optional for initial product readiness and remains pending.
  assert.equal(progress.checks.team.state, "pending");
  assert.equal(progress.completedCount, 3);
});

test("reports unavailable reads as unknown instead of inventing empty state", () => {
  const progress = deriveOnboardingProgress(
    snapshot({
      missing: ["connectors", "companyBrain", "companyMap", "members"],
      unavailable: ["connectors", "company-brain", "company-map", "members"]
    })
  );

  assert.equal(progress.checks.source.state, "unknown");
  assert.equal(progress.checks.map.state, "unknown");
  assert.equal(progress.checks.team.state, "unknown");
  assert.equal(progress.checks.ready.state, "unknown");
  assert.equal(progress.ready, false);
  assert.deepEqual(progress.unavailable, [
    "connectors",
    "company-brain",
    "company-map",
    "members"
  ]);
});

test("restores only known onboarding steps from the URL fragment", () => {
  assert.equal(onboardingStepFromHash("#source"), 2);
  assert.equal(onboardingStepFromHash("#team"), 4);
  assert.equal(onboardingStepFromHash("#unknown"), 0);
  assert.equal(onboardingStepFromHash(""), 0);
});

test("returns the first actual required blocker instead of a completed step", () => {
  const sourcePending = deriveOnboardingProgress(
    snapshot({ internalPeople: 1, sourceRecords: 0 })
  );
  const mapPending = deriveOnboardingProgress(
    snapshot({ internalPeople: 0, sourceRecords: 3 })
  );
  const ready = deriveOnboardingProgress(
    snapshot({ internalPeople: 1, sourceRecords: 3 })
  );

  assert.equal(firstIncompleteRequiredStep(sourcePending), 2);
  assert.equal(firstIncompleteRequiredStep(mapPending), 3);
  assert.equal(firstIncompleteRequiredStep(ready), null);
});
