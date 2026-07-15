import assert from "node:assert/strict";
import test from "node:test";

import { renderToStaticMarkup } from "react-dom/server";

import {
  advanceCompanyWorldResolutionStep,
  beginCompanyWorldResolution,
  buildCompanyWorldResolutionDraft,
  companyWorldResolutionStepForContext,
  companyWorldResolutionSteps,
  companyWorldCandidateRenderKey,
  completedCompanyWorldResolutionRefresh,
  CompanyWorldPanelView,
  createCompanyWorldResolutionGate,
  effectiveCompanyWorldSelectedKey,
  failedCompanyWorldResolution,
  failedCompanyWorldResolutionRefresh,
  finishCompanyWorldResolution,
  isCurrentCompanyWorldResolution,
  nextCompanyWorldCandidateKey,
  pendingCompanyWorldResolution,
  personOrganizationState,
  relatedCompanyWorldTouchpoints,
  resetCompanyWorldResolutionGate,
  splitCompanyWorldProfileTouchpoints,
  successfulCompanyWorldResolution,
  validSelectedKey
} from "../components/CompanyWorldPanel";
import { buildCompanyWorldBoardModel } from "../components/CompanyWorldBoard";
import {
  ApiRequestError,
  buildWorkspaceCompanyMapPath,
  buildWorkspaceCompanyMapResolutionsPath,
  fetchCompanyMap,
  resolveCompanyMapCandidate
} from "../lib/api";
import {
  buildCompanyWorldProfileTarget,
  readCompanyWorldProfileSelector,
  resolveCompanyWorldProfileSelector
} from "../lib/company-world-profile";
import { M } from "../lib/messages";
import type { CompanyMapResponse } from "../lib/types";

const sourceRef = {
  id: "source-1:0",
  kind: "gmail_message",
  source: "gmail",
  label: "message-1",
  url: "https://mail.google.com/mail/u/0/#inbox/message-1",
  record_type: "message",
  record_id: "source-1"
};

const PERSON_CANDIDATE_VERSION = "a".repeat(64);
const ORGANIZATION_CANDIDATE_VERSION = "b".repeat(64);
const STALE_CANDIDATE_VERSION = "c".repeat(64);
const UPDATED_CANDIDATE_VERSION = "d".repeat(64);

const sampleMap: CompanyMapResponse = {
  workspace_id: "workspace-123",
  mode: "evidence_backed_projection",
  source: "workspace_and_company_brain_projection",
  company: {
    key: "workspace:workspace-123",
    workspace_id: "workspace-123",
    name: "Northstar Labs",
    slug: "northstar-labs",
    status: "active",
    source_refs: [
      {
        ...sourceRef,
        id: "workspace:workspace-123",
        kind: "workspace",
        source: "founderos",
        label: "Northstar Labs",
        url: null,
        record_type: "workspace",
        record_id: "workspace-123"
      }
    ]
  },
  summary: {
    internal_people: 1,
    confirmed_external_people: 1,
    confirmed_organizations: 1,
    external_contacts_in_window: 1,
    organizations_in_window: 1,
    touchpoints_in_window: 1
  },
  window: {
    gmail_messages_available: 3,
    gmail_messages_considered: 1,
    message_limit: 1,
    truncated: true,
    order: "newest_first"
  },
  people: {
    internal: [
      {
        key: "user:user-1",
        person_id: null,
        user_id: "user-1",
        name: "Анна",
        email: "anna@northstar.test",
        status: "active",
        role: "owner",
        source_refs: [
          {
            ...sourceRef,
            id: "membership:membership-1",
            kind: "workspace_membership",
            source: "founderos",
            label: "owner",
            url: null,
            record_type: "membership",
            record_id: "membership-1"
          }
        ]
      }
    ],
    confirmed_external: [
      {
        key: "person:confirmed-buyer",
        person_id: "confirmed-buyer",
        email: "confirmed@acme.test",
        display_name: "Confirmed Buyer",
        status: "confirmed",
        organization_id: "confirmed-acme",
        organization_key: "organization:confirmed-acme",
        organization_name: "Acme Confirmed",
        relationship_type: "decision_maker",
        role_title: "Operations Lead",
        interaction_count: 3,
        last_interaction_at: "2026-07-12T12:00:00Z",
        source_refs: [sourceRef]
      }
    ],
    external_candidates: [
      {
        key: "external-person:buyer",
        candidate_version: PERSON_CANDIDATE_VERSION,
        email: "buyer@acme.test",
        display_name: "Buyer Person",
        organization_key: "organization:acme.test",
        last_interaction_at: "2026-07-12T12:00:00Z",
        interaction_count: 2,
        source_refs: [sourceRef],
        needs_founder_confirm: true
      }
    ]
  },
  organizations: [
    {
      key: "organization:acme.test",
      candidate_version: ORGANIZATION_CANDIDATE_VERSION,
      domain: "acme.test",
      name: null,
      kind: "external_candidate",
      people_count: 1,
      interaction_count: 2,
      last_interaction_at: "2026-07-12T12:00:00Z",
      source_refs: [sourceRef],
      needs_founder_confirm: true
    }
  ],
  confirmed_organizations: [
    {
      key: "organization:confirmed-acme",
      organization_id: "confirmed-acme",
      domain: "confirmed.test",
      name: "Acme Confirmed",
      relationship_kind: "customer",
      status: "confirmed",
      people_count: 1,
      interaction_count: 3,
      last_interaction_at: "2026-07-12T12:00:00Z",
      source_refs: [sourceRef]
    }
  ],
  touchpoints: [
    {
      key: "touchpoint:source-1",
      channel: "email",
      source_record_id: "source-1",
      subject: "Kickoff and next steps",
      direction: "inbound",
      occurred_at: "2026-07-12T12:00:00Z",
      person_keys: ["user:user-1", "external-person:buyer"],
      organization_keys: ["organization:acme.test"],
      source_url: "https://mail.google.com/mail/u/0/#inbox/message-1",
      source_refs: [sourceRef]
    }
  ],
  capabilities: {
    read_only: true,
    can_resolve: true,
    required_role: "member",
    provider_calls: false,
    llm_used: false
  },
  warnings: ["Кандидаты требуют подтверждения."],
  is_live: false,
  llm_used: false
};

function mapWithConfirmedCandidateOrganization(): CompanyMapResponse {
  const confirmed = sampleMap.confirmed_organizations[0];
  assert.ok(confirmed);
  return {
    ...sampleMap,
    organizations: [],
    confirmed_organizations: [
      {
        ...confirmed,
        domain: "acme.test",
        key: "organization:durable-acme",
        name: "Acme Confirmed"
      }
    ]
  };
}

function mapWithStandalonePerson(): CompanyMapResponse {
  return {
    ...sampleMap,
    organizations: []
  };
}

function resolutionButton(html: string, action: "confirm" | "dismiss"): string {
  const tag = (html.match(/<button\b[^>]*>/g) ?? []).find((button) =>
    button.includes(`data-resolution-action="${action}"`)
  );
  assert.ok(tag, `missing ${action} resolution button`);
  return tag;
}

function deferred<T>(): {
  promise: Promise<T>;
  resolve: (value: T) => void;
  reject: (reason?: unknown) => void;
} {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, reject, resolve };
}

function renderPanel(
  status: "loading" | "ready" | "empty" | "error" | "missing",
  data: CompanyMapResponse | null = sampleMap,
  initialSelectedKey: string | null = null
): string {
  return renderToStaticMarkup(
    <CompanyWorldPanelView
      data={data}
      error={null}
      initialSelectedKey={initialSelectedKey}
      onResolve={async () => undefined}
      status={status}
    />
  );
}

test("builds opaque workspace-scoped profile links and resolves them safely", () => {
  const cases = [
    [sampleMap.company.key, "v1:company"],
    [sampleMap.people.internal[0]?.key, "v1:member:user-1"],
    [sampleMap.people.confirmed_external[0]?.key, "v1:person:confirmed-buyer"],
    [
      sampleMap.people.external_candidates[0]?.key,
      `v1:person-candidate:${PERSON_CANDIDATE_VERSION}`
    ],
    [
      sampleMap.confirmed_organizations[0]?.key,
      "v1:organization:confirmed-acme"
    ],
    [
      sampleMap.organizations[0]?.key,
      `v1:organization-candidate:${ORGANIZATION_CANDIDATE_VERSION}`
    ]
  ] as const;

  for (const [key, selector] of cases) {
    assert.ok(key);
    const target = buildCompanyWorldProfileTarget(sampleMap, key);
    assert.ok(target);
    assert.equal(target.selector, selector);
    assert.equal(
      target.href,
      `/company-brain?profile=${encodeURIComponent(selector)}#company-world-profile`
    );
    assert.equal(
      resolveCompanyWorldProfileSelector(sampleMap, target.selector),
      key
    );
  }

  const organizationCandidate = buildCompanyWorldProfileTarget(
    sampleMap,
    sampleMap.organizations[0]?.key ?? ""
  );
  assert.ok(organizationCandidate);
  assert.equal(organizationCandidate.href.includes("acme.test"), false);
  assert.equal(organizationCandidate.href.includes("organization%3Aacme"), false);
  assert.equal(
    buildCompanyWorldProfileTarget(
      sampleMap,
      sampleMap.touchpoints[0]?.key ?? ""
    ),
    null
  );
});

test("rejects malformed foreign and stale profile selectors", () => {
  assert.equal(readCompanyWorldProfileSelector("?profile="), null);
  assert.equal(
    readCompanyWorldProfileSelector(`?profile=${"x".repeat(513)}`),
    null
  );
  assert.equal(resolveCompanyWorldProfileSelector(sampleMap, "v1:person:foreign"), null);
  assert.equal(resolveCompanyWorldProfileSelector(sampleMap, "v2:company"), null);

  const oldTarget = buildCompanyWorldProfileTarget(
    sampleMap,
    sampleMap.people.external_candidates[0]?.key ?? ""
  );
  assert.ok(oldTarget);
  const refreshedMap: CompanyMapResponse = {
    ...sampleMap,
    people: {
      ...sampleMap.people,
      external_candidates: sampleMap.people.external_candidates.map((person) => ({
        ...person,
        candidate_version: UPDATED_CANDIDATE_VERSION
      }))
    }
  };
  assert.equal(
    resolveCompanyWorldProfileSelector(refreshedMap, oldTarget.selector),
    null
  );
  assert.equal(
    effectiveCompanyWorldSelectedKey(refreshedMap, null, {
      data: sampleMap,
      key: sampleMap.people.external_candidates[0]?.key ?? null,
      routeKey: sampleMap.people.external_candidates[0]?.key ?? null
    }),
    refreshedMap.company.key
  );
});

test("builds and fetches the workspace company-map endpoint", async () => {
  assert.equal(
    buildWorkspaceCompanyMapPath("workspace-123"),
    "/api/v1/workspaces/workspace-123/company-map"
  );

  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (input) => {
    assert.equal(
      String(input),
      "http://localhost/api/v1/workspaces/workspace-123/company-map"
    );
    return new Response(JSON.stringify(sampleMap), {
      headers: { "Content-Type": "application/json" },
      status: 200
    });
  }) as typeof fetch;

  try {
    const payload = await fetchCompanyMap("workspace-123");
    assert.equal(payload.summary.internal_people, 1);
    assert.equal(payload.people.external_candidates[0]?.needs_founder_confirm, true);
    assert.match(
      payload.people.external_candidates[0]?.candidate_version ?? "",
      /^[0-9a-f]{64}$/
    );
    assert.match(payload.organizations[0]?.candidate_version ?? "", /^[0-9a-f]{64}$/);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("builds and posts the workspace company-map resolution contract", async () => {
  assert.equal(
    buildWorkspaceCompanyMapResolutionsPath("workspace-123"),
    "/api/v1/workspaces/workspace-123/company-map/resolutions"
  );

  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (input, init) => {
    assert.equal(
      String(input),
      "http://localhost/api/v1/workspaces/workspace-123/company-map/resolutions"
    );
    assert.equal(init?.method, "POST");
    assert.deepEqual(JSON.parse(String(init?.body)), {
      candidate_type: "external_person",
      candidate_key: "external-person:buyer",
      candidate_version: PERSON_CANDIDATE_VERSION,
      decision: "confirmed",
      idempotency_key: "resolution-1",
      relationship_type: "decision_maker",
      role_title: "Operations Lead"
    });
    return new Response(
      JSON.stringify({
        resolution: {
          id: "resolution-1",
          candidate_type: "external_person",
          candidate_key: "external-person:buyer",
          decision: "confirmed",
          created_at: "2026-07-13T12:00:00Z"
        },
        person_id: "person-1",
        organization_id: "organization-1",
        affiliation_id: "affiliation-1",
        interaction_count: 2,
        replayed: false,
        capabilities: {
          provider_calls: false,
          external_write: false,
          llm_used: false
        }
      }),
      { headers: { "Content-Type": "application/json" }, status: 200 }
    );
  }) as typeof fetch;

  try {
    const receipt = await resolveCompanyMapCandidate("workspace-123", {
      candidate_type: "external_person",
      candidate_key: "external-person:buyer",
      candidate_version: PERSON_CANDIDATE_VERSION,
      decision: "confirmed",
      idempotency_key: "resolution-1",
      relationship_type: "decision_maker",
      role_title: "Operations Lead"
    });
    assert.equal(receipt.person_id, "person-1");
    assert.equal(receipt.capabilities.external_write, false);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("preserves actionable HTTP statuses for resolution handling", async () => {
  const originalFetch = globalThis.fetch;

  try {
    for (const status of [403, 404, 409, 422]) {
      globalThis.fetch = (async () =>
        new Response(JSON.stringify({ detail: `resolution ${status}` }), {
          headers: { "Content-Type": "application/json" },
          status
        })) as typeof fetch;

      await assert.rejects(
        resolveCompanyMapCandidate("workspace-123", {
          candidate_type: "organization",
          candidate_key: "organization:acme.test",
          candidate_version: STALE_CANDIDATE_VERSION,
          decision: "dismissed",
          idempotency_key: `resolution-${status}`
        }),
        (error: unknown) =>
          error instanceof ApiRequestError &&
          error.status === status &&
          error.message === `resolution ${status}`
      );
    }
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("renders loading, missing, empty, and error states", () => {
  assert.ok(renderPanel("loading", null).includes(M.companyWorld.loading));
  assert.ok(renderPanel("missing", null).includes(M.common.noWorkspaceTitle));
  assert.ok(renderPanel("empty").includes(M.companyWorld.emptyTitle));
  assert.ok(
    renderToStaticMarkup(
      <CompanyWorldPanelView data={null} error="offline" status="error" />
    ).includes("offline")
  );
});

test("renders an evidence-backed company world with provisional candidates", () => {
  const html = renderPanel("ready");
  const candidateCount =
    sampleMap.organizations.length + sampleMap.people.external_candidates.length;

  assert.ok(html.includes("Northstar Labs"));
  assert.ok(html.includes(M.companyWorld.reviewRailTitle(candidateCount, true)));
  assert.match(html, /≥2/);
  assert.ok(html.includes("Анна"));
  assert.ok(html.includes("Buyer Person"));
  assert.ok(html.includes("acme.test"));
  assert.ok(html.includes("Confirmed Buyer"));
  assert.ok(html.includes("Acme Confirmed"));
  assert.ok(html.includes("Kickoff and next steps"));
  assert.ok(html.includes(M.companyWorld.organizationNeedsConfirmation));
  assert.ok(html.includes(M.companyWorld.boundary));
  assert.ok(html.includes(M.companyWorld.windowTruncated));
  assert.ok(html.includes("Кандидаты требуют подтверждения."));
  assert.ok(html.includes(M.companyWorld.resolutionEnabled));
  assert.ok(html.includes(M.companyWorld.noProviderCalls));
  assert.ok(html.includes(M.companyWorld.noExternalWrites));
  assert.ok(html.includes(M.companyWorld.localProjection));
  assert.ok(html.includes(M.companyWorld.statuses.active));
  assert.ok(html.includes(M.companyWorld.organizationRelationshipKinds.customer));
  assert.ok(html.includes('aria-pressed="true"'));
  assert.ok(html.includes('aria-controls="company-world-profile"'));
  assert.ok(html.includes('id="company-world-profile"'));
  assert.ok(html.includes('tabindex="-1"'));
  assert.ok(html.includes('aria-labelledby="company-world-profile-title"'));
  assert.ok(html.includes(M.companyWorld.boardTitle));
  assert.ok(html.includes(M.companyWorld.confirmedContour));
  assert.ok(html.includes(M.companyWorld.needsReview));
  assert.ok(html.includes(M.companyWorld.allContours));
  assert.ok(html.includes(M.companyWorld.openNextCandidate));
  assert.ok(html.includes(M.companyWorld.evidenceDisclosure));
  assert.ok(html.includes(M.companyWorld.technicalDisclosure));
  assert.equal(html.includes('class="mission-strip"'), false);
  assert.equal(html.includes('class="company-world-coach"'), false);
  assert.doesNotMatch(
    html,
    /<aside[^>]*id="company-world-profile"[^>]*aria-live=/
  );
  assert.doesNotMatch(html, /PRIVATE_BODY|raw_body/);
});

test("keeps truncated candidate totals and zero states explicitly partial", () => {
  const zeroCandidateMap: CompanyMapResponse = {
    ...sampleMap,
    organizations: [],
    people: {
      ...sampleMap.people,
      external_candidates: []
    },
    summary: {
      ...sampleMap.summary,
      external_contacts_in_window: 0,
      organizations_in_window: 0
    }
  };
  const html = renderPanel("ready", zeroCandidateMap);

  assert.ok(html.includes(M.companyWorld.reviewRailWindowClearTitle));
  assert.ok(html.includes(M.companyWorld.reviewRailWindowClearDescription));
  assert.ok(html.includes(M.companyWorld.discoveryCompleteInWindow));
  assert.equal(html.includes(M.companyWorld.reviewRailClearDescription), false);
});

test("explains when the only candidate is already open", () => {
  const oneCandidateMap = mapWithStandalonePerson();
  const candidate = oneCandidateMap.people.external_candidates[0];
  assert.ok(candidate);
  const html = renderPanel("ready", oneCandidateMap, candidate.key);

  assert.ok(
    html.includes(
      M.companyWorld.reviewRailCurrent(candidate.display_name ?? candidate.email)
    )
  );
  assert.equal(html.includes(M.companyWorld.reviewRailClearDescription), false);
});

test("builds spatial groups only from explicit durable affiliations", () => {
  const grouped = buildCompanyWorldBoardModel(sampleMap);
  assert.equal(grouped.organizationGroups.length, 1);
  assert.deepEqual(
    grouped.organizationGroups[0]?.people.map((person) => person.key),
    ["person:confirmed-buyer"]
  );
  assert.deepEqual(grouped.standaloneConfirmedPeople, []);

  const domainOnly = buildCompanyWorldBoardModel(
    mapWithConfirmedCandidateOrganization()
  );
  assert.deepEqual(domainOnly.organizationGroups[0]?.people, []);
  assert.deepEqual(
    domainOnly.standaloneConfirmedPeople.map((person) => person.key),
    ["person:confirmed-buyer"]
  );
});

test("filters profile touchpoints only by exact response keys", () => {
  assert.equal(
    relatedCompanyWorldTouchpoints(sampleMap, sampleMap.company.key).length,
    1
  );
  assert.equal(
    relatedCompanyWorldTouchpoints(sampleMap, "external-person:buyer").length,
    1
  );
  assert.equal(
    relatedCompanyWorldTouchpoints(sampleMap, "person:confirmed-buyer").length,
    0
  );
  assert.equal(
    relatedCompanyWorldTouchpoints(sampleMap, "organization:confirmed-acme").length,
    0
  );
  const parentKey = sampleMap.people.external_candidates[0]?.key ?? null;
  const touchpointKey = sampleMap.touchpoints[0]?.key ?? null;
  assert.ok(parentKey);
  assert.ok(touchpointKey);
  assert.equal(
    effectiveCompanyWorldSelectedKey(sampleMap, parentKey, {
      data: sampleMap,
      key: touchpointKey,
      routeKey: parentKey
    }),
    touchpointKey
  );
});

test("offers only explicit unresolved candidates as the next profile", () => {
  const organizationKey = sampleMap.organizations[0]?.key;
  const personKey = sampleMap.people.external_candidates[0]?.key;
  assert.ok(organizationKey);
  assert.ok(personKey);

  assert.equal(
    nextCompanyWorldCandidateKey(sampleMap, sampleMap.company.key),
    organizationKey
  );
  assert.equal(nextCompanyWorldCandidateKey(sampleMap, organizationKey), personKey);
  assert.equal(nextCompanyWorldCandidateKey(sampleMap, personKey), organizationKey);
  const standaloneMap = mapWithStandalonePerson();
  assert.equal(
    nextCompanyWorldCandidateKey(
      standaloneMap,
      standaloneMap.people.external_candidates[0]?.key ?? null
    ),
    null
  );
});

test("keeps the profile timeline compact while preserving the bounded history", () => {
  const sourceTouchpoint = sampleMap.touchpoints[0];
  assert.ok(sourceTouchpoint);
  const touchpoints = Array.from({ length: 9 }, (_, index) => ({
    ...sourceTouchpoint,
    key: `touchpoint:source-${index}`,
    source_record_id: `source-${index}`,
    subject: `Touchpoint ${index}`
  }));

  const split = splitCompanyWorldProfileTouchpoints(touchpoints);
  assert.deepEqual(
    split.visibleTouchpoints.map((touchpoint) => touchpoint.key),
    touchpoints.slice(0, 3).map((touchpoint) => touchpoint.key)
  );
  assert.deepEqual(
    split.remainingTouchpoints.map((touchpoint) => touchpoint.key),
    touchpoints.slice(3).map((touchpoint) => touchpoint.key)
  );
});

test("builds strict person, organization, standalone, and dismissal payloads", () => {
  assert.deepEqual(
    buildCompanyWorldResolutionDraft({
      candidateKey: "external-person:buyer",
      candidateType: "external_person",
      candidateVersion: PERSON_CANDIDATE_VERSION,
      decision: "confirmed",
      displayName: " Buyer Person ",
      organizationName: "must-not-be-sent",
      organizationRelationshipKind: "customer",
      relationshipType: "decision_maker",
      roleTitle: " Operations Lead "
    }),
    {
      candidate_key: "external-person:buyer",
      candidate_type: "external_person",
      candidate_version: PERSON_CANDIDATE_VERSION,
      decision: "confirmed",
      display_name: "Buyer Person",
      relationship_type: "decision_maker",
      role_title: "Operations Lead"
    }
  );

  assert.deepEqual(
    buildCompanyWorldResolutionDraft({
      candidateKey: "external-person:buyer",
      candidateType: "external_person",
      candidateVersion: PERSON_CANDIDATE_VERSION,
      decision: "confirmed",
      relationshipType: "",
      roleTitle: "must-not-be-sent"
    }),
    {
      candidate_key: "external-person:buyer",
      candidate_type: "external_person",
      candidate_version: PERSON_CANDIDATE_VERSION,
      decision: "confirmed"
    }
  );

  assert.deepEqual(
    buildCompanyWorldResolutionDraft({
      candidateKey: "external-person:buyer",
      candidateType: "external_person",
      candidateVersion: PERSON_CANDIDATE_VERSION,
      decision: "confirmed",
      displayName: "Buyer Person",
      relationshipFieldsVisible: false,
      relationshipType: "decision_maker",
      roleTitle: "must-not-be-sent"
    }),
    {
      candidate_key: "external-person:buyer",
      candidate_type: "external_person",
      candidate_version: PERSON_CANDIDATE_VERSION,
      decision: "confirmed",
      display_name: "Buyer Person"
    }
  );

  assert.deepEqual(
    buildCompanyWorldResolutionDraft({
      candidateKey: "organization:acme.test",
      candidateType: "organization",
      candidateVersion: ORGANIZATION_CANDIDATE_VERSION,
      decision: "confirmed",
      organizationName: " Acme ",
      organizationRelationshipKind: "customer"
    }),
    {
      candidate_key: "organization:acme.test",
      candidate_type: "organization",
      candidate_version: ORGANIZATION_CANDIDATE_VERSION,
      decision: "confirmed",
      organization_name: "Acme",
      organization_relationship_kind: "customer"
    }
  );

  assert.deepEqual(
    buildCompanyWorldResolutionDraft({
      candidateKey: "organization:acme.test",
      candidateType: "organization",
      candidateVersion: ORGANIZATION_CANDIDATE_VERSION,
      decision: "dismissed",
      organizationName: "must-not-be-sent",
      organizationRelationshipKind: "customer"
    }),
    {
      candidate_key: "organization:acme.test",
      candidate_type: "organization",
      candidate_version: ORGANIZATION_CANDIDATE_VERSION,
      decision: "dismissed"
    }
  );
});

test("serializes deferred resolutions and ignores a completion from an old sequence", async () => {
  const gate = createCompanyWorldResolutionGate("workspace-123");
  const firstSequence = beginCompanyWorldResolution(gate, "workspace-123");
  assert.equal(typeof firstSequence, "number");
  assert.equal(beginCompanyWorldResolution(gate, "workspace-123"), null);

  const firstResponse = deferred<void>();
  let staleCompletionApplied = false;
  const firstCompletion = (async () => {
    await firstResponse.promise;
    if (
      firstSequence !== null &&
      isCurrentCompanyWorldResolution(gate, "workspace-123", firstSequence)
    ) {
      staleCompletionApplied = true;
      finishCompanyWorldResolution(gate, "workspace-123", firstSequence);
    }
  })();

  resetCompanyWorldResolutionGate(gate, "workspace-456");
  firstResponse.resolve(undefined);
  await firstCompletion;
  assert.equal(staleCompletionApplied, false);

  const secondSequence = beginCompanyWorldResolution(gate, "workspace-456");
  assert.equal(typeof secondSequence, "number");
  assert.ok(secondSequence !== firstSequence);
  assert.ok(
    secondSequence !== null &&
      isCurrentCompanyWorldResolution(gate, "workspace-456", secondSequence)
  );
  if (secondSequence !== null) {
    finishCompanyWorldResolution(gate, "workspace-456", secondSequence);
  }
  assert.equal(gate.inFlight, false);
});

test("blocks person confirmation while its organization candidate is unresolved", () => {
  const person = sampleMap.people.external_candidates[0];
  assert.ok(person);
  assert.equal(personOrganizationState(sampleMap, person).kind, "unresolved");

  const html = renderPanel("ready", sampleMap, person.key);
  assert.ok(html.includes(M.companyWorld.organizationResolutionRequired));
  assert.ok(html.includes(M.companyWorld.openOrganizationProfile));
  assert.ok(html.includes(M.companyWorld.resolutionQuestionHint));
  assert.ok(html.includes(M.companyWorld.resolutionPersonQuestion));
  assert.ok(html.includes('data-resolution-step="decision"'));
  assert.match(resolutionButton(html, "confirm"), /\bdisabled=""/);
  assert.doesNotMatch(resolutionButton(html, "dismiss"), /\bdisabled=/);
  assert.doesNotMatch(html, /<select\b/);
});

test("uses one-question resolution steps and unlocks relationship questions safely", () => {
  const data = mapWithConfirmedCandidateOrganization();
  const person = data.people.external_candidates[0];
  assert.ok(person);
  assert.equal(personOrganizationState(data, person).kind, "confirmed");

  const html = renderPanel("ready", data, person.key);
  assert.ok(html.includes(M.companyWorld.confirmedOrganizationForPerson));
  assert.ok(html.includes(M.companyWorld.confirmedOrganizationForPersonDescription));
  assert.deepEqual(companyWorldResolutionSteps("external_person", true), [
    "decision",
    "name",
    "relationship",
    "role"
  ]);
  assert.ok(html.includes(M.companyWorld.resolutionPersonQuestion));
  assert.doesNotMatch(html, /<select\b/);
  assert.doesNotMatch(resolutionButton(html, "confirm"), /\bdisabled=/);
});

test("keeps a person standalone after its organization is absent or dismissed", () => {
  const data = mapWithStandalonePerson();
  const person = data.people.external_candidates[0];
  assert.ok(person);
  assert.equal(personOrganizationState(data, person).kind, "standalone");

  const html = renderPanel("ready", data, person.key);
  assert.ok(html.includes(M.companyWorld.standalonePerson));
  assert.deepEqual(companyWorldResolutionSteps("external_person", false), [
    "decision",
    "name"
  ]);
  assert.doesNotMatch(resolutionButton(html, "confirm"), /\bdisabled=/);
  assert.doesNotMatch(html, /<select\b/);
});

test("keeps organization classification as a later human-authored question", () => {
  const organization = sampleMap.organizations[0];
  assert.ok(organization);
  const html = renderPanel("ready", sampleMap, organization.key);

  assert.deepEqual(companyWorldResolutionSteps("organization", false), [
    "decision",
    "name",
    "relationship"
  ]);
  assert.equal(M.companyWorld.organizationRelationshipKinds.prospect, "Потенциальный заказчик");
  assert.equal(M.companyWorld.organizationRelationshipKinds.customer, "Заказчик");
  assert.equal(M.companyWorld.organizationRelationshipKinds.vendor, "Поставщик");
  assert.ok(html.includes(M.companyWorld.organizationNeedsConfirmation));
  assert.ok(html.includes(M.companyWorld.resolutionOrganizationQuestion));
  assert.doesNotMatch(html, /<select\b/);
});

test("advances the organization wizard to its terminal submit without context reset", () => {
  const steps = companyWorldResolutionSteps("organization", false);
  assert.equal(
    companyWorldResolutionStepForContext("organization", false, "relationship"),
    "relationship"
  );
  assert.equal(
    companyWorldResolutionStepForContext("external_person", false, "relationship"),
    "name"
  );

  const name = advanceCompanyWorldResolutionStep(steps, "decision");
  assert.deepEqual(name, { nextStep: "name", shouldSubmit: false });
  const relationship = advanceCompanyWorldResolutionStep(steps, name.nextStep);
  assert.deepEqual(relationship, {
    nextStep: "relationship",
    shouldSubmit: false
  });
  assert.deepEqual(
    advanceCompanyWorldResolutionStep(steps, relationship.nextStep),
    { nextStep: "relationship", shouldSubmit: true }
  );
});

test("changes the remount key and form defaults when candidate_version changes", () => {
  const organization = sampleMap.organizations[0];
  assert.ok(organization);
  const updatedMap: CompanyMapResponse = {
    ...sampleMap,
    organizations: [
      {
        ...organization,
        candidate_version: UPDATED_CANDIDATE_VERSION,
        name: "Acme Updated"
      }
    ]
  };

  const firstHtml = renderPanel("ready", sampleMap, organization.key);
  const updatedHtml = renderPanel("ready", updatedMap, organization.key);
  assert.notEqual(
    companyWorldCandidateRenderKey(organization.key, organization.candidate_version),
    companyWorldCandidateRenderKey(organization.key, UPDATED_CANDIDATE_VERSION)
  );
  assert.ok(
    firstHtml.includes(`data-candidate-version="${ORGANIZATION_CANDIDATE_VERSION}"`)
  );
  assert.ok(
    updatedHtml.includes(`data-candidate-version="${UPDATED_CANDIDATE_VERSION}"`)
  );
  assert.ok(updatedHtml.includes("Acme Updated"));
  assert.ok(updatedHtml.includes('data-resolution-step="decision"'));
});

test("maps pending, success, 403, 404, 409, and 422 to visible states", () => {
  const candidateKey = sampleMap.organizations[0]?.key ?? "organization:missing";
  const states = [
    pendingCompanyWorldResolution(candidateKey),
    successfulCompanyWorldResolution(candidateKey, "confirmed"),
    successfulCompanyWorldResolution(candidateKey, "dismissed"),
    failedCompanyWorldResolution(candidateKey, new ApiRequestError("forbidden", 403)).state,
    failedCompanyWorldResolution(candidateKey, new ApiRequestError("missing", 404)).state,
    failedCompanyWorldResolution(candidateKey, new ApiRequestError("conflict", 409)).state,
    failedCompanyWorldResolution(candidateKey, new ApiRequestError("invalid", 422)).state
  ];

  for (const state of states) {
    const html = renderToStaticMarkup(
      <CompanyWorldPanelView
        data={sampleMap}
        error={null}
        initialSelectedKey={candidateKey}
        resolutionState={state}
        status="ready"
      />
    );
    assert.ok(state.message && html.includes(state.message));
    assert.ok(html.includes(`world-resolution-notice--${state.status}`));
  }

  assert.equal(
    failedCompanyWorldResolution(candidateKey, new ApiRequestError("forbidden", 403)).refresh,
    true
  );
  assert.equal(
    failedCompanyWorldResolution(candidateKey, new ApiRequestError("missing", 404)).refresh,
    true
  );
  assert.equal(
    failedCompanyWorldResolution(candidateKey, new ApiRequestError("conflict", 409)).refresh,
    true
  );
  assert.equal(
    failedCompanyWorldResolution(candidateKey, new ApiRequestError("invalid", 422)).refresh,
    false
  );

  const pendingHtml = renderToStaticMarkup(
    <CompanyWorldPanelView
      data={sampleMap}
      error={null}
      initialSelectedKey={candidateKey}
      resolutionState={pendingCompanyWorldResolution(candidateKey)}
      status="ready"
    />
  );
  assert.match(resolutionButton(pendingHtml, "confirm"), /\bdisabled=""/);
  assert.match(resolutionButton(pendingHtml, "dismiss"), /\bdisabled=""/);

  const standaloneMap = mapWithStandalonePerson();
  const personKey = standaloneMap.people.external_candidates[0]?.key;
  assert.ok(personKey);
  const otherCandidatePendingHtml = renderToStaticMarkup(
    <CompanyWorldPanelView
      data={standaloneMap}
      error={null}
      initialSelectedKey={personKey}
      resolutionState={pendingCompanyWorldResolution(candidateKey)}
      status="ready"
    />
  );
  assert.match(resolutionButton(otherCandidatePendingHtml, "confirm"), /\bdisabled=""/);
  assert.match(resolutionButton(otherCandidatePendingHtml, "dismiss"), /\bdisabled=""/);
});

test("keeps a saved receipt visible through reload failure and recovery", () => {
  const candidateKey = sampleMap.organizations[0]?.key ?? "organization:missing";
  const saved = successfulCompanyWorldResolution(candidateKey, "confirmed");
  const refreshFailed = failedCompanyWorldResolutionRefresh(saved);
  const errorHtml = renderToStaticMarkup(
    <CompanyWorldPanelView
      data={null}
      error="offline"
      resolutionState={refreshFailed}
      status="error"
    />
  );
  assert.ok(errorHtml.includes(M.companyWorld.resolutionSavedRefreshFailed));
  assert.ok(errorHtml.includes("offline"));
  assert.match(errorHtml, /world-resolution-notice--success/);

  const loadingHtml = renderToStaticMarkup(
    <CompanyWorldPanelView
      data={sampleMap}
      error={null}
      resolutionState={saved}
      status="loading"
    />
  );
  assert.ok(loadingHtml.includes(M.companyWorld.resolutionConfirmed));

  const recovered = completedCompanyWorldResolutionRefresh(refreshFailed);
  assert.equal(recovered.message, M.companyWorld.resolutionConfirmedRefreshed);
  const readyHtml = renderToStaticMarkup(
    <CompanyWorldPanelView
      data={sampleMap}
      error={null}
      initialSelectedKey={candidateKey}
      resolutionState={recovered}
      status="ready"
    />
  );
  assert.ok(readyHtml.includes(M.companyWorld.resolutionConfirmedRefreshed));
  assert.ok(
    readyHtml.indexOf("world-resolution-announcer") <
      readyHtml.indexOf('id="company-world-profile"')
  );
  assert.ok(
    readyHtml.indexOf('id="company-world-profile"') <
      readyHtml.lastIndexOf("world-resolution-notice--success")
  );
  assert.match(readyHtml, /world-resolution-announcer[^>]*role="status"/);
  assert.equal(
    (readyHtml.match(/world-resolution-notice--success/g) ?? []).length,
    2
  );
});

test("keeps candidate decisions read-only for viewers", () => {
  const viewerMap: CompanyMapResponse = {
    ...sampleMap,
    capabilities: {
      ...sampleMap.capabilities,
      can_resolve: false
    }
  };
  const html = renderPanel(
    "ready",
    viewerMap,
    viewerMap.people.external_candidates[0]?.key ?? null
  );

  assert.ok(html.includes(M.companyWorld.resolutionReadOnly));
  assert.ok(html.includes(M.companyWorld.readOnly));
  assert.ok(html.includes(M.companyWorld.organizationResolutionRequiredDescription));
  assert.doesNotMatch(html, /основател/i);
  assert.ok(!html.includes(`>${M.companyWorld.dismissCandidate}</button>`));
  assert.ok(!html.includes('data-candidate-type="external_person"'));
  assert.ok(!html.includes('data-resolution-action="confirm"'));
});

test("falls back to the company when a selected profile disappears", () => {
  assert.equal(
    validSelectedKey(sampleMap, "external-person:removed"),
    sampleMap.company.key
  );
  assert.equal(
    validSelectedKey(sampleMap, sampleMap.people.external_candidates[0]?.key ?? null),
    sampleMap.people.external_candidates[0]?.key
  );
  assert.equal(
    validSelectedKey(sampleMap, sampleMap.people.confirmed_external[0]?.key ?? null),
    sampleMap.people.confirmed_external[0]?.key
  );
  assert.equal(
    validSelectedKey(sampleMap, sampleMap.confirmed_organizations[0]?.key ?? null),
    sampleMap.confirmed_organizations[0]?.key
  );
});
