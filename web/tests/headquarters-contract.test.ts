import assert from "node:assert/strict";
import test from "node:test";

import {
  buildWorkspaceHeadquartersOnboardingPath,
  buildWorkspaceHeadquartersPath,
  fetchHeadquarters,
  fetchHeadquartersOnboarding
} from "../lib/api";
import {
  HEADQUARTERS_PULSE_KEYS,
  HeadquartersContractError,
  parseHeadquartersSnapshotResponse,
  type HeadquartersEvidenceRef,
  type HeadquartersSnapshotResponse
} from "../lib/headquarters";

const ENABLED_ACTION = {
  kind: "navigate",
  label: "Открыть",
  target: "/actions",
  enabled: true,
  disabled_reason: null
};

const VALID_EVIDENCE: HeadquartersEvidenceRef = {
  id: "evidence_ref:evidence-1",
  kind: "repository",
  source_key: "github",
  label: "Canonical field evidence",
  target: "https://github.com/acme/repository/issues/1",
  provenance: "canonical_evidence_ref",
  trust: "verified",
  reference_type: "evidence_ref",
  reference_id: "evidence-1",
  workspace_scoped: true
};

const VALID_HEADQUARTERS_FIXTURE: HeadquartersSnapshotResponse = {
  contract_version: "headquarters.v2",
  ranking_version: "headquarters-ranking.v1",
  snapshot: {
    id: "hqs1_test",
    as_of: "2026-07-16T10:00:00Z",
    partial: false,
    warnings: [],
    coverage: [
      {
        key: "identity",
        status: "complete",
        watermark: "identity-1",
        warning: null
      },
      {
        key: "sources",
        status: "complete",
        watermark: "sources-1",
        warning: null
      },
      {
        key: "decisions",
        status: "complete",
        watermark: "decisions-1",
        warning: null
      },
      {
        key: "company_world",
        status: "complete",
        watermark: "world-1",
        warning: null
      }
    ]
  },
  workspace: {
    id: "workspace-123",
    name: "Acme",
    role: "owner"
  },
  onboarding: {
    contract_version: "onboarding.v1",
    readiness_version: "onboarding-readiness.v1",
    ready: true,
    completed_count: 5,
    total_count: 5,
    completed_required: 3,
    required_total: 3,
    current_step_key: null,
    steps: [
      {
        key: "company",
        state: "complete",
        requirement: "required",
        label: "Компания создана",
        benefit: "Данные изолированы внутри компании.",
        evidence: [
          {
            key: "workspace",
            label: "Компания доступна",
            state: "complete",
            value: 1,
            precision: "exact"
          }
        ],
        action: ENABLED_ACTION
      },
      {
        key: "source",
        state: "complete",
        requirement: "recommended",
        label: "Первый источник выбран",
        benefit: "Понятно, откуда поступают данные.",
        evidence: [
          {
            key: "configured_sources",
            label: "Настроенные источники",
            state: "complete",
            value: 1,
            precision: "exact"
          }
        ],
        action: ENABLED_ACTION
      },
      {
        key: "canonical_data",
        state: "complete",
        requirement: "required",
        label: "Первые данные подтверждены",
        benefit: "Штаб видит канонические факты.",
        evidence: [
          {
            key: "canonical_records",
            label: "Канонические записи",
            state: "complete",
            value: 1,
            precision: "exact"
          }
        ],
        action: ENABLED_ACTION
      },
      {
        key: "context",
        state: "complete",
        requirement: "recommended",
        label: "Контекст компании появился",
        benefit: "Карта, команда и решения делают картину полезнее.",
        evidence: [
          {
            key: "context_signals",
            label: "Элементы контекста",
            state: "complete",
            value: 1,
            precision: "exact"
          }
        ],
        action: ENABLED_ACTION
      },
      {
        key: "headquarters",
        state: "complete",
        requirement: "required",
        label: "Первый снимок штаба рассчитан",
        benefit: "Компания уже видна как единая система.",
        evidence: [
          {
            key: "snapshot",
            label: "Снимок штаба",
            state: "complete",
            value: 1,
            precision: "exact"
          }
        ],
        action: ENABLED_ACTION
      }
    ],
    next_action: null
  },
  sources: {
    healthy: 0,
    total: 0,
    configured_count: 0,
    data_ready_count: 0,
    attention_count: 0,
    count_precision: "exact",
    items: []
  },
  priority: null,
  pulse: [
    {
      key: "waiting_decisions",
      label: "Ждут решения",
      value: 0,
      precision: "exact",
      empty_state: "Решений не требуется",
      target: "/actions?status=proposed",
      action: ENABLED_ACTION
    },
    {
      key: "sources_attention",
      label: "Источники требуют внимания",
      value: 0,
      precision: "exact",
      empty_state: "Все источники в порядке",
      target: "/connectors",
      action: ENABLED_ACTION
    },
    {
      key: "pending_relationships",
      label: "Связи ждут проверки",
      value: 0,
      precision: "exact",
      empty_state: "Новых связей нет",
      target: "/company-brain",
      action: ENABLED_ACTION
    }
  ],
  queue: [],
  changes: {
    items: [],
    basis: "current_snapshot",
    cursor: null,
    since_checkpoint: false
  },
  capabilities: {
    can_manage_team: true,
    can_manage_source: true,
    can_import_source: true,
    can_start_source_read: true,
    can_generate_briefing: true,
    can_create_proposal: true,
    can_review_proposal: true,
    can_execute_external: true,
    can_resolve_world: true,
    can_acknowledge_changes: true
  },
  boundary: {
    provider_calls: false,
    external_writes: false,
    llm: false,
    reads_secrets: false,
    transaction: "repeatable_read_read_only"
  }
};

const VALID_ONBOARDING_DETAIL = {
  contract_version: VALID_HEADQUARTERS_FIXTURE.contract_version,
  snapshot: VALID_HEADQUARTERS_FIXTURE.snapshot,
  workspace: VALID_HEADQUARTERS_FIXTURE.workspace,
  onboarding: VALID_HEADQUARTERS_FIXTURE.onboarding,
  capabilities: VALID_HEADQUARTERS_FIXTURE.capabilities,
  boundary: VALID_HEADQUARTERS_FIXTURE.boundary
};

test("exposes the fixed v2 headquarters paths and pulse order", () => {
  assert.equal(
    buildWorkspaceHeadquartersPath("workspace/with slash"),
    "/api/v1/workspaces/workspace%2Fwith%20slash/headquarters"
  );
  assert.equal(
    buildWorkspaceHeadquartersOnboardingPath("workspace/with slash"),
    "/api/v1/workspaces/workspace%2Fwith%20slash/headquarters/onboarding"
  );
  assert.deepEqual(HEADQUARTERS_PULSE_KEYS, [
    "waiting_decisions",
    "sources_attention",
    "pending_relationships"
  ]);
});

test("fetches and validates the full headquarters contract", async () => {
  const originalFetch = globalThis.fetch;
  const controller = new AbortController();
  let requestCount = 0;
  globalThis.fetch = mockHeadquartersResponse(VALID_HEADQUARTERS_FIXTURE, (input, init) => {
    requestCount += 1;
    assert.equal(
      String(input),
      "http://localhost/api/v1/workspaces/workspace-123/headquarters"
    );
    assert.equal(init?.credentials, "include");
    assert.equal(init?.signal, controller.signal);
    assert.equal(new Headers(init?.headers).get("Accept"), "application/json");
  });

  try {
    const payload = await fetchHeadquarters("workspace-123", {
      signal: controller.signal
    });
    assert.deepEqual(payload, VALID_HEADQUARTERS_FIXTURE);
    assert.equal(requestCount, 1);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("fetches the detailed onboarding projection from the versioned headquarters path", async () => {
  const originalFetch = globalThis.fetch;
  const controller = new AbortController();
  globalThis.fetch = mockHeadquartersResponse(VALID_ONBOARDING_DETAIL, (input, init) => {
    assert.equal(
      String(input),
      "http://localhost/api/v1/workspaces/workspace-123/headquarters/onboarding"
    );
    assert.equal(init?.credentials, "include");
    assert.equal(init?.signal, controller.signal);
  });

  try {
    const payload = await fetchHeadquartersOnboarding("workspace-123", {
      signal: controller.signal
    });
    assert.deepEqual(payload, VALID_ONBOARDING_DETAIL);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("fails closed when a required onboarding step is unknown but ready is claimed", () => {
  const malformed = structuredClone(VALID_HEADQUARTERS_FIXTURE);
  const canonical = malformed.onboarding.steps[2];
  assert.equal(canonical?.key, "canonical_data");
  if (!canonical) return;
  canonical.state = "unknown";
  canonical.evidence[0] = {
    ...canonical.evidence[0]!,
    state: "unknown",
    value: null,
    precision: "unavailable"
  };

  assert.throws(
    () => parseHeadquartersSnapshotResponse(malformed),
    contractFailure(/onboarding\.completed_count: expected must match completed steps/)
  );
});

test("rejects unavailable onboarding evidence that claims a known state", () => {
  const malformed = structuredClone(VALID_HEADQUARTERS_FIXTURE);
  const evidence = malformed.onboarding.steps[3]?.evidence[0];
  assert.ok(evidence);
  evidence.state = "pending";
  evidence.value = null;
  evidence.precision = "unavailable";

  assert.throws(
    () => parseHeadquartersSnapshotResponse(malformed),
    contractFailure(/unavailable evidence must be unknown without a value/)
  );
});

test("rejects a completed onboarding step backed only by unknown evidence", () => {
  const malformed = structuredClone(VALID_HEADQUARTERS_FIXTURE);
  const canonical = malformed.onboarding.steps[2];
  assert.equal(canonical?.key, "canonical_data");
  if (!canonical) return;
  canonical.evidence[0] = {
    ...canonical.evidence[0]!,
    state: "unknown",
    value: null,
    precision: "unavailable"
  };

  assert.throws(
    () => parseHeadquartersSnapshotResponse(malformed),
    contractFailure(/onboarding\.steps\[2\]\.state: expected must match onboarding evidence/)
  );
});

test("rejects reordered or incomplete onboarding milestones", () => {
  const reordered = structuredClone(VALID_HEADQUARTERS_FIXTURE);
  [reordered.onboarding.steps[0], reordered.onboarding.steps[1]] = [
    reordered.onboarding.steps[1],
    reordered.onboarding.steps[0]
  ];
  const missing = structuredClone(VALID_HEADQUARTERS_FIXTURE);
  missing.onboarding.steps.pop();

  assert.throws(
    () => parseHeadquartersSnapshotResponse(reordered),
    contractFailure(/onboarding\.steps\[0\]\.key: expected company/)
  );
  assert.throws(
    () => parseHeadquartersSnapshotResponse(missing),
    contractFailure(/onboarding\.steps: expected exactly five ordered onboarding steps/)
  );
});

test("rejects a headquarters payload with a missing contract section", async () => {
  const originalFetch = globalThis.fetch;
  const malformed = structuredClone(VALID_HEADQUARTERS_FIXTURE) as Record<
    string,
    unknown
  >;
  delete malformed.capabilities;
  globalThis.fetch = mockHeadquartersResponse(malformed);

  try {
    await assert.rejects(
      () => fetchHeadquarters("workspace-123"),
      contractFailure(/headquarters\.capabilities: expected required field/)
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("rejects a headquarters payload that changes the fixed pulse order", async () => {
  const originalFetch = globalThis.fetch;
  const malformed = structuredClone(VALID_HEADQUARTERS_FIXTURE);
  [malformed.pulse[0], malformed.pulse[1]] = [
    malformed.pulse[1],
    malformed.pulse[0]
  ];
  globalThis.fetch = mockHeadquartersResponse(malformed);

  try {
    await assert.rejects(
      () => fetchHeadquarters("workspace-123"),
      contractFailure(/pulse\[0\]\.key: expected waiting_decisions/)
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("rejects duplicate or omitted fixed coverage projections", () => {
  const duplicate = structuredClone(VALID_HEADQUARTERS_FIXTURE);
  duplicate.snapshot.coverage[3] = {
    ...duplicate.snapshot.coverage[0],
    watermark: "duplicate-identity"
  };

  const omitted = structuredClone(VALID_HEADQUARTERS_FIXTURE);
  omitted.snapshot.coverage.pop();

  assert.throws(
    () => parseHeadquartersSnapshotResponse(duplicate),
    contractFailure(
      /snapshot\.coverage\[3\]\.key: expected company_world/
    )
  );
  assert.throws(
    () => parseHeadquartersSnapshotResponse(omitted),
    contractFailure(/snapshot\.coverage: expected exactly four projections/)
  );
});

test("requires coverage warnings to match completion status", () => {
  const warnedComplete = structuredClone(VALID_HEADQUARTERS_FIXTURE);
  warnedComplete.snapshot.coverage[0].warning = "Unexpected warning";

  const silentPartial = structuredClone(VALID_HEADQUARTERS_FIXTURE);
  silentPartial.snapshot.coverage[1].status = "partial";
  silentPartial.snapshot.partial = true;

  assert.throws(
    () => parseHeadquartersSnapshotResponse(warnedComplete),
    contractFailure(
      /snapshot\.coverage\[0\]\.warning: expected null for complete coverage/
    )
  );
  assert.throws(
    () => parseHeadquartersSnapshotResponse(silentPartial),
    contractFailure(
      /snapshot\.coverage\[1\]\.warning: expected non-empty warning for incomplete coverage/
    )
  );
});

test("rejects an external headquarters action target", async () => {
  const originalFetch = globalThis.fetch;
  const malformed = structuredClone(VALID_HEADQUARTERS_FIXTURE);
  malformed.pulse[0].action = {
    ...malformed.pulse[0].action,
    target: "https://example.test/actions"
  };
  globalThis.fetch = mockHeadquartersResponse(malformed);

  try {
    await assert.rejects(
      () => fetchHeadquarters("workspace-123"),
      contractFailure(/pulse\[0\]\.action\.target: expected safe internal path/)
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("rejects unsafe standalone pulse and change targets", () => {
  const externalPulseTarget = structuredClone(VALID_HEADQUARTERS_FIXTURE);
  externalPulseTarget.pulse[0].target = "https://example.test/actions";

  const protocolRelativeChangeTarget = structuredClone(VALID_HEADQUARTERS_FIXTURE);
  protocolRelativeChangeTarget.changes.items.push({
    id: "change-1",
    kind: "proposal",
    title: "Changed mission",
    summary: "One mission changed.",
    occurred_at: "2026-07-16T10:00:00Z",
    source_keys: ["github"],
    evidence_refs: [VALID_EVIDENCE],
    target: "//example.test/actions"
  });

  assert.throws(
    () => parseHeadquartersSnapshotResponse(externalPulseTarget),
    contractFailure(/pulse\[0\]\.target: expected safe internal path/)
  );
  assert.throws(
    () => parseHeadquartersSnapshotResponse(protocolRelativeChangeTarget),
    contractFailure(/changes\.items\[0\]\.target: expected safe internal path/)
  );
});

test("rejects unsafe evidence URLs, secret queries, invalid ports, and oversize values", () => {
  for (const target of [
    "javascript:alert(1)",
    "https://user:password@example.test/private",
    "https://example.test:99999/private",
    "https://example.test/private?access%5Ftoken=do-not-render",
    `https://example.test/${"x".repeat(1000)}`
  ]) {
    const malformed = structuredClone(VALID_HEADQUARTERS_FIXTURE);
    malformed.changes.items.push({
      id: "change-1",
      kind: "proposal",
      title: "Changed mission",
      summary: "One mission changed.",
      occurred_at: "2026-07-16T10:00:00Z",
      source_keys: ["github"],
      evidence_refs: [{ ...VALID_EVIDENCE, target }],
      target: "/actions"
    });

    assert.throws(
      () => parseHeadquartersSnapshotResponse(malformed),
      contractFailure(
        /changes\.items\[0\]\.evidence_refs\[0\]\.target: expected safe internal path or http\(s\) URL/
      )
    );
  }
});

function mockHeadquartersResponse(
  payload: unknown,
  onRequest?: (input: string | URL | Request, init?: RequestInit) => void
): typeof fetch {
  return (async (input, init) => {
    onRequest?.(input, init);
    return new Response(JSON.stringify(payload), {
      headers: { "Content-Type": "application/json" },
      status: 200
    });
  }) as typeof fetch;
}

function contractFailure(
  messagePattern: RegExp
): (error: unknown) => boolean {
  return (error) => {
    assert.ok(error instanceof HeadquartersContractError);
    assert.match(error.message, messagePattern);
    return true;
  };
}
