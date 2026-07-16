/**
 * Browser contract for the real FounderOS headquarters read model.
 *
 * It defines the browser types and validates every response at runtime. The
 * browser must not recreate ranking or RBAC from this read model.
 */

export const HEADQUARTERS_PULSE_KEYS = [
  "waiting_decisions",
  "sources_attention",
  "pending_relationships"
] as const;

export const HEADQUARTERS_ONBOARDING_STEP_KEYS = [
  "company",
  "source",
  "canonical_data",
  "context",
  "headquarters"
] as const;

const HEADQUARTERS_COVERAGE_KEYS = [
  "identity",
  "sources",
  "decisions",
  "company_world"
] as const;

const HEADQUARTERS_EVIDENCE_URL_MAX_LENGTH = 1000;
const SENSITIVE_EVIDENCE_URL_QUERY_KEYS = new Set([
  "access_token",
  "api_key",
  "code",
  "key",
  "password",
  "private_key",
  "refresh_token",
  "secret",
  "sig",
  "signature",
  "token",
  "x_amz_signature",
  "x_goog_signature"
]);

export type HeadquartersPulseKey =
  (typeof HEADQUARTERS_PULSE_KEYS)[number];
export type HeadquartersPrecision = "at_least" | "exact" | "unavailable";
export type HeadquartersRole = "admin" | "member" | "owner" | "viewer";
export type HeadquartersSourceKey = "drive" | "github" | "gmail" | "jira";
export type HeadquartersOnboardingState = "complete" | "pending" | "unknown";
export type HeadquartersOnboardingStepKey =
  (typeof HEADQUARTERS_ONBOARDING_STEP_KEYS)[number];

export type HeadquartersAction = {
  kind: string;
  label: string;
  target: string | null;
  enabled: boolean;
  disabled_reason: string | null;
};

export type HeadquartersEvidenceRef = {
  id: string;
  kind: string;
  source_key: HeadquartersSourceKey | "internal";
  label: string;
  target: string | null;
  provenance:
    | "briefing_item"
    | "canonical_evidence_ref"
    | "canonical_source_record"
    | "canonical_repository"
    | "integration_connection"
    | "company_world_projection"
    | "headquarters_aggregate";
  trust: "aggregate" | "verified";
  reference_type:
    | "briefing_item"
    | "company_world_candidate"
    | "evidence_ref"
    | "headquarters_snapshot"
    | "integration_connection"
    | "repository"
    | "source_record"
    | "sync_job";
  reference_id: string;
  workspace_scoped: true;
};

export type HeadquartersFactProvenance = {
  owner: HeadquartersEvidenceRef[];
  customer: HeadquartersEvidenceRef[];
  due: HeadquartersEvidenceRef[];
  impact: HeadquartersEvidenceRef[];
  severity: HeadquartersEvidenceRef[];
  confidence: HeadquartersEvidenceRef[];
};

export type HeadquartersMission = {
  id: string;
  kind:
    | "connect_source"
    | "create_briefing"
    | "review_proposal"
    | "review_world"
    | "source_attention";
  reference_type: "proposal" | "setup" | "source" | "world";
  reference_id: string;
  title: string;
  summary: string;
  why_now: string;
  status: string;
  severity: "critical" | "high" | "info" | "low" | "medium" | "unknown";
  confidence: number | null;
  confidence_precision: "exact" | "unavailable";
  due_at: string | null;
  impact: string | null;
  next_step: string;
  owner_person_ids: string[];
  organization_id: string | null;
  primary_person_id: string | null;
  source_keys: string[];
  evidence_refs: HeadquartersEvidenceRef[];
  proposal_id: string | null;
  proposal_version: string | null;
  evidence_state: "aggregate" | "verified";
  trust_class: "aggregate" | "verified_canonical";
  ranking_reason:
    | "briefing_setup_gap"
    | "configured_source_attention"
    | "evidence_backed_relationship"
    | "source_setup_gap"
    | "verified_proposal";
  fact_provenance: HeadquartersFactProvenance;
  action: HeadquartersAction;
  correlation_reason: string | null;
  correlation_rule_version: string | null;
};

export type HeadquartersPulseMetric = {
  key: HeadquartersPulseKey;
  label: string;
  value: number | null;
  precision: HeadquartersPrecision;
  empty_state: string;
  target: string;
  action: HeadquartersAction;
};

export type HeadquartersSourceHealth = {
  key: HeadquartersSourceKey;
  name: string;
  configuration: "configured" | "disconnected";
  read: "failed" | "idle" | "running" | "succeeded";
  data: "available" | "empty" | "partial";
  freshness: "fresh" | "stale" | "unknown";
  primary_state:
    | "failed"
    | "healthy"
    | "no_data"
    | "partial"
    | "setup"
    | "stale";
  attention_reason: string | null;
  scopes: string[];
  last_success_at: string | null;
  last_attempt_at: string | null;
  last_data_observed_at: string | null;
  fresh_until: string | null;
  freshness_policy_version: "source-health.v1";
  connection_count: number;
  connection_count_precision: "exact";
  record_count: number;
  record_count_precision: "exact";
  blocker: string | null;
  safe_debug_id: string | null;
  next_action: HeadquartersAction;
};

export type HeadquartersCapabilitySet = {
  can_manage_team: boolean;
  can_manage_source: boolean;
  can_import_source: boolean;
  can_start_source_read: boolean;
  can_generate_briefing: boolean;
  can_create_proposal: boolean;
  can_review_proposal: boolean;
  can_execute_external: boolean;
  can_resolve_world: boolean;
  can_acknowledge_changes: boolean;
};

export type HeadquartersOnboardingEvidence = {
  key: string;
  label: string;
  state: HeadquartersOnboardingState;
  value: number | null;
  precision: "exact" | "unavailable";
};

export type HeadquartersOnboardingStep = {
  key: HeadquartersOnboardingStepKey;
  state: HeadquartersOnboardingState;
  requirement: "recommended" | "required";
  label: string;
  benefit: string;
  evidence: HeadquartersOnboardingEvidence[];
  action: HeadquartersAction;
};

export type HeadquartersOnboarding = {
  contract_version: "onboarding.v1";
  readiness_version: "onboarding-readiness.v1";
  ready: boolean;
  completed_count: number;
  total_count: 5;
  completed_required: number;
  required_total: 3;
  current_step_key: HeadquartersOnboardingStepKey | null;
  steps: [
    HeadquartersOnboardingStep,
    HeadquartersOnboardingStep,
    HeadquartersOnboardingStep,
    HeadquartersOnboardingStep,
    HeadquartersOnboardingStep
  ];
  next_action: HeadquartersAction | null;
};

export type HeadquartersSnapshotResponse = {
  contract_version: "headquarters.v2";
  ranking_version: "headquarters-ranking.v1";
  snapshot: {
    id: string;
    as_of: string;
    partial: boolean;
    warnings: string[];
    coverage: Array<{
      key: "company_world" | "decisions" | "identity" | "sources";
      status: "complete" | "partial" | "unavailable";
      watermark: string;
      warning: string | null;
    }>;
  };
  workspace: { id: string; name: string; role: HeadquartersRole };
  onboarding: HeadquartersOnboarding;
  sources: {
    healthy: number;
    total: number;
    configured_count: number;
    data_ready_count: number;
    attention_count: number;
    count_precision: "exact";
    items: HeadquartersSourceHealth[];
  };
  priority: HeadquartersMission | null;
  pulse: [
    HeadquartersPulseMetric,
    HeadquartersPulseMetric,
    HeadquartersPulseMetric
  ];
  queue: HeadquartersMission[];
  changes: {
    items: Array<{
      id: string;
      kind: "proposal" | "relationship" | "source";
      title: string;
      summary: string;
      occurred_at: string | null;
      source_keys: string[];
      evidence_refs: HeadquartersEvidenceRef[];
      target: string;
    }>;
    basis: "current_snapshot";
    cursor: null;
    since_checkpoint: false;
  };
  capabilities: HeadquartersCapabilitySet;
  boundary: {
    provider_calls: false;
    external_writes: false;
    llm: false;
    reads_secrets: false;
    transaction: "repeatable_read_read_only";
  };
};

export type HeadquartersOnboardingDetailResponse = Pick<
  HeadquartersSnapshotResponse,
  "boundary" | "capabilities" | "contract_version" | "onboarding" | "snapshot" | "workspace"
>;

type HeadquartersRecord = Record<string, unknown>;

export class HeadquartersContractError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "HeadquartersContractError";
  }
}

export function parseHeadquartersSnapshotResponse(
  value: unknown
): HeadquartersSnapshotResponse {
  const response = expectRecord(value, "headquarters");
  expectKeys(
    response,
    [
      "contract_version",
      "ranking_version",
      "snapshot",
      "workspace",
      "onboarding",
      "sources",
      "priority",
      "pulse",
      "queue",
      "changes",
      "capabilities",
      "boundary"
    ],
    "headquarters"
  );
  expectEnum(response.contract_version, ["headquarters.v2"] as const, "contract_version");
  expectEnum(
    response.ranking_version,
    ["headquarters-ranking.v1"] as const,
    "ranking_version"
  );
  validateSnapshot(response.snapshot, "snapshot");
  validateWorkspace(response.workspace, "workspace");
  validateOnboarding(response.onboarding, "onboarding");
  validateSources(response.sources, "sources");
  if (response.priority !== null) {
    validateMission(response.priority, "priority");
  }

  const pulse = expectArray(response.pulse, "pulse");
  if (pulse.length !== HEADQUARTERS_PULSE_KEYS.length) {
    contractError("pulse", "exactly three metrics");
  }
  pulse.forEach((metric, index) => {
    validatePulseMetric(metric, `pulse[${index}]`);
    const record = metric as HeadquartersRecord;
    if (record.key !== HEADQUARTERS_PULSE_KEYS[index]) {
      contractError(`pulse[${index}].key`, HEADQUARTERS_PULSE_KEYS[index]);
    }
  });

  const queue = expectArray(response.queue, "queue");
  if (queue.length > 2) {
    contractError("queue", "at most two missions");
  }
  queue.forEach((mission, index) => validateMission(mission, `queue[${index}]`));
  if (response.priority !== null) {
    const priorityId = (response.priority as HeadquartersRecord).id;
    if (queue.some((mission) => (mission as HeadquartersRecord).id === priorityId)) {
      contractError("queue", "must not repeat priority");
    }
  }

  validateChanges(response.changes, "changes");
  validateCapabilities(response.capabilities, "capabilities");
  validateBoundary(response.boundary, "boundary");

  const snapshot = response.snapshot as HeadquartersRecord;
  const coverage = snapshot.coverage as unknown[];
  const expectedPartial = coverage.some(
    (item) => (item as HeadquartersRecord).status !== "complete"
  );
  if (snapshot.partial !== expectedPartial) {
    contractError("snapshot.partial", "must match coverage status");
  }

  return value as HeadquartersSnapshotResponse;
}

export function parseHeadquartersOnboardingDetailResponse(
  value: unknown
): HeadquartersOnboardingDetailResponse {
  const response = expectRecord(value, "headquarters_onboarding");
  expectKeys(
    response,
    [
      "contract_version",
      "snapshot",
      "workspace",
      "onboarding",
      "capabilities",
      "boundary"
    ],
    "headquarters_onboarding"
  );
  expectEnum(
    response.contract_version,
    ["headquarters.v2"] as const,
    "headquarters_onboarding.contract_version"
  );
  validateSnapshot(response.snapshot, "headquarters_onboarding.snapshot");
  validateWorkspace(response.workspace, "headquarters_onboarding.workspace");
  validateOnboarding(response.onboarding, "headquarters_onboarding.onboarding");
  validateCapabilities(
    response.capabilities,
    "headquarters_onboarding.capabilities"
  );
  validateBoundary(response.boundary, "headquarters_onboarding.boundary");

  const snapshot = response.snapshot as HeadquartersRecord;
  const coverage = snapshot.coverage as unknown[];
  const expectedPartial = coverage.some(
    (item) => (item as HeadquartersRecord).status !== "complete"
  );
  if (snapshot.partial !== expectedPartial) {
    contractError(
      "headquarters_onboarding.snapshot.partial",
      "must match coverage status"
    );
  }

  return value as HeadquartersOnboardingDetailResponse;
}

function validateAction(value: unknown, path: string): void {
  const action = expectRecord(value, path);
  expectKeys(action, ["kind", "label", "target", "enabled", "disabled_reason"], path);
  expectString(action.kind, `${path}.kind`);
  expectString(action.label, `${path}.label`);
  const target = expectNullableString(action.target, `${path}.target`);
  if (target !== null) {
    validateInternalActionTarget(target, `${path}.target`);
  }
  const enabled = expectBoolean(action.enabled, `${path}.enabled`);
  const disabledReason = expectNullableString(
    action.disabled_reason,
    `${path}.disabled_reason`
  );
  if (enabled && disabledReason !== null) {
    contractError(path, "enabled action without disabled_reason");
  }
  if (!enabled && !disabledReason) {
    contractError(path, "disabled action with disabled_reason");
  }
}

function validateEvidence(value: unknown, path: string): void {
  const evidence = expectRecord(value, path);
  expectKeys(
    evidence,
    [
      "id",
      "kind",
      "source_key",
      "label",
      "target",
      "provenance",
      "trust",
      "reference_type",
      "reference_id",
      "workspace_scoped"
    ],
    path
  );
  expectString(evidence.id, `${path}.id`);
  expectString(evidence.kind, `${path}.kind`);
  expectEnum(
    evidence.source_key,
    ["drive", "github", "gmail", "jira", "internal"] as const,
    `${path}.source_key`
  );
  expectString(evidence.label, `${path}.label`);
  const target = expectNullableString(evidence.target, `${path}.target`);
  if (target !== null) {
    validateEvidenceTarget(target, `${path}.target`);
  }
  expectEnum(
    evidence.provenance,
    [
      "briefing_item",
      "canonical_evidence_ref",
      "canonical_source_record",
      "canonical_repository",
      "integration_connection",
      "company_world_projection",
      "headquarters_aggregate"
    ] as const,
    `${path}.provenance`
  );
  expectEnum(evidence.trust, ["aggregate", "verified"] as const, `${path}.trust`);
  expectEnum(
    evidence.reference_type,
    [
      "briefing_item",
      "company_world_candidate",
      "evidence_ref",
      "headquarters_snapshot",
      "integration_connection",
      "repository",
      "source_record",
      "sync_job"
    ] as const,
    `${path}.reference_type`
  );
  expectString(evidence.reference_id, `${path}.reference_id`);
  expectLiteral(evidence.workspace_scoped, true, `${path}.workspace_scoped`);
}

function validateFactProvenance(value: unknown, path: string): void {
  const provenance = expectRecord(value, path);
  expectKeys(
    provenance,
    ["owner", "customer", "due", "impact", "severity", "confidence"],
    path
  );
  for (const key of ["owner", "customer", "due", "impact", "severity", "confidence"]) {
    const refs = expectArray(provenance[key], `${path}.${key}`);
    refs.forEach((ref, index) => validateEvidence(ref, `${path}.${key}[${index}]`));
  }
}

function validateMission(value: unknown, path: string): void {
  const mission = expectRecord(value, path);
  expectKeys(
    mission,
    [
      "id",
      "kind",
      "reference_type",
      "reference_id",
      "title",
      "summary",
      "why_now",
      "status",
      "severity",
      "confidence",
      "confidence_precision",
      "due_at",
      "impact",
      "next_step",
      "owner_person_ids",
      "organization_id",
      "primary_person_id",
      "source_keys",
      "evidence_refs",
      "proposal_id",
      "proposal_version",
      "evidence_state",
      "trust_class",
      "ranking_reason",
      "fact_provenance",
      "action",
      "correlation_reason",
      "correlation_rule_version"
    ],
    path
  );
  expectString(mission.id, `${path}.id`);
  expectEnum(
    mission.kind,
    [
      "connect_source",
      "create_briefing",
      "review_proposal",
      "review_world",
      "source_attention"
    ] as const,
    `${path}.kind`
  );
  expectEnum(
    mission.reference_type,
    ["proposal", "setup", "source", "world"] as const,
    `${path}.reference_type`
  );
  for (const key of ["reference_id", "title", "summary", "why_now", "status", "next_step"]) {
    expectString(mission[key], `${path}.${key}`);
  }
  expectEnum(
    mission.severity,
    ["critical", "high", "info", "low", "medium", "unknown"] as const,
    `${path}.severity`
  );
  const confidence = expectNullableNumber(mission.confidence, `${path}.confidence`);
  if (confidence !== null && (confidence < 0 || confidence > 1)) {
    contractError(`${path}.confidence`, "number between 0 and 1");
  }
  const confidencePrecision = expectEnum(
    mission.confidence_precision,
    ["exact", "unavailable"] as const,
    `${path}.confidence_precision`
  );
  if ((confidence === null) !== (confidencePrecision === "unavailable")) {
    contractError(`${path}.confidence_precision`, "must match confidence availability");
  }
  expectNullableDateString(mission.due_at, `${path}.due_at`);
  expectNullableString(mission.impact, `${path}.impact`);
  expectStringArray(mission.owner_person_ids, `${path}.owner_person_ids`);
  expectNullableString(mission.organization_id, `${path}.organization_id`);
  expectNullableString(mission.primary_person_id, `${path}.primary_person_id`);
  expectStringArray(mission.source_keys, `${path}.source_keys`);
  const evidence = expectArray(mission.evidence_refs, `${path}.evidence_refs`);
  evidence.forEach((ref, index) => validateEvidence(ref, `${path}.evidence_refs[${index}]`));
  expectNullableString(mission.proposal_id, `${path}.proposal_id`);
  expectNullableString(mission.proposal_version, `${path}.proposal_version`);
  expectEnum(
    mission.evidence_state,
    ["aggregate", "verified"] as const,
    `${path}.evidence_state`
  );
  expectEnum(
    mission.trust_class,
    ["aggregate", "verified_canonical"] as const,
    `${path}.trust_class`
  );
  expectEnum(
    mission.ranking_reason,
    [
      "briefing_setup_gap",
      "configured_source_attention",
      "evidence_backed_relationship",
      "source_setup_gap",
      "verified_proposal"
    ] as const,
    `${path}.ranking_reason`
  );
  validateFactProvenance(mission.fact_provenance, `${path}.fact_provenance`);
  validateAction(mission.action, `${path}.action`);
  expectNullableString(mission.correlation_reason, `${path}.correlation_reason`);
  expectNullableString(
    mission.correlation_rule_version,
    `${path}.correlation_rule_version`
  );
}

function validatePulseMetric(value: unknown, path: string): void {
  const metric = expectRecord(value, path);
  expectKeys(metric, ["key", "label", "value", "precision", "empty_state", "target", "action"], path);
  expectEnum(metric.key, HEADQUARTERS_PULSE_KEYS, `${path}.key`);
  expectString(metric.label, `${path}.label`);
  const count = expectNullableNonNegativeInteger(metric.value, `${path}.value`);
  const precision = expectEnum(
    metric.precision,
    ["at_least", "exact", "unavailable"] as const,
    `${path}.precision`
  );
  if ((count === null) !== (precision === "unavailable")) {
    contractError(`${path}.precision`, "must match metric value availability");
  }
  expectString(metric.empty_state, `${path}.empty_state`);
  validateInternalActionTarget(
    expectString(metric.target, `${path}.target`),
    `${path}.target`
  );
  validateAction(metric.action, `${path}.action`);
}

function validateSource(value: unknown, path: string): void {
  const source = expectRecord(value, path);
  expectKeys(
    source,
    [
      "key",
      "name",
      "configuration",
      "read",
      "data",
      "freshness",
      "primary_state",
      "attention_reason",
      "scopes",
      "last_success_at",
      "last_attempt_at",
      "last_data_observed_at",
      "fresh_until",
      "freshness_policy_version",
      "connection_count",
      "connection_count_precision",
      "record_count",
      "record_count_precision",
      "blocker",
      "safe_debug_id",
      "next_action"
    ],
    path
  );
  expectEnum(source.key, ["drive", "github", "gmail", "jira"] as const, `${path}.key`);
  expectString(source.name, `${path}.name`);
  expectEnum(
    source.configuration,
    ["configured", "disconnected"] as const,
    `${path}.configuration`
  );
  expectEnum(source.read, ["failed", "idle", "running", "succeeded"] as const, `${path}.read`);
  expectEnum(source.data, ["available", "empty", "partial"] as const, `${path}.data`);
  expectEnum(source.freshness, ["fresh", "stale", "unknown"] as const, `${path}.freshness`);
  expectEnum(
    source.primary_state,
    ["failed", "healthy", "no_data", "partial", "setup", "stale"] as const,
    `${path}.primary_state`
  );
  expectNullableString(source.attention_reason, `${path}.attention_reason`);
  expectStringArray(source.scopes, `${path}.scopes`);
  for (const key of ["last_success_at", "last_attempt_at", "last_data_observed_at", "fresh_until"]) {
    expectNullableDateString(source[key], `${path}.${key}`);
  }
  expectEnum(
    source.freshness_policy_version,
    ["source-health.v1"] as const,
    `${path}.freshness_policy_version`
  );
  expectNonNegativeInteger(source.connection_count, `${path}.connection_count`);
  expectEnum(
    source.connection_count_precision,
    ["exact"] as const,
    `${path}.connection_count_precision`
  );
  expectNonNegativeInteger(source.record_count, `${path}.record_count`);
  expectEnum(
    source.record_count_precision,
    ["exact"] as const,
    `${path}.record_count_precision`
  );
  expectNullableString(source.blocker, `${path}.blocker`);
  expectNullableString(source.safe_debug_id, `${path}.safe_debug_id`);
  validateAction(source.next_action, `${path}.next_action`);
}

function validateSources(value: unknown, path: string): void {
  const sources = expectRecord(value, path);
  expectKeys(
    sources,
    [
      "healthy",
      "total",
      "configured_count",
      "data_ready_count",
      "attention_count",
      "count_precision",
      "items"
    ],
    path
  );
  for (const key of [
    "healthy",
    "total",
    "configured_count",
    "data_ready_count",
    "attention_count"
  ]) {
    expectNonNegativeInteger(sources[key], `${path}.${key}`);
  }
  expectEnum(sources.count_precision, ["exact"] as const, `${path}.count_precision`);
  const items = expectArray(sources.items, `${path}.items`);
  items.forEach((source, index) => validateSource(source, `${path}.items[${index}]`));
}

function validateChanges(value: unknown, path: string): void {
  const changes = expectRecord(value, path);
  expectKeys(changes, ["items", "basis", "cursor", "since_checkpoint"], path);
  const items = expectArray(changes.items, `${path}.items`);
  if (items.length > 3) {
    contractError(`${path}.items`, "at most three items");
  }
  items.forEach((value, index) => {
    const itemPath = `${path}.items[${index}]`;
    const item = expectRecord(value, itemPath);
    expectKeys(
      item,
      ["id", "kind", "title", "summary", "occurred_at", "source_keys", "evidence_refs", "target"],
      itemPath
    );
    for (const key of ["id", "title", "summary"]) {
      expectString(item[key], `${itemPath}.${key}`);
    }
    validateInternalActionTarget(
      expectString(item.target, `${itemPath}.target`),
      `${itemPath}.target`
    );
    expectEnum(item.kind, ["proposal", "relationship", "source"] as const, `${itemPath}.kind`);
    expectNullableDateString(item.occurred_at, `${itemPath}.occurred_at`);
    expectStringArray(item.source_keys, `${itemPath}.source_keys`);
    const refs = expectArray(item.evidence_refs, `${itemPath}.evidence_refs`);
    refs.forEach((ref, refIndex) => validateEvidence(ref, `${itemPath}.evidence_refs[${refIndex}]`));
  });
  expectEnum(changes.basis, ["current_snapshot"] as const, `${path}.basis`);
  expectLiteral(changes.cursor, null, `${path}.cursor`);
  expectLiteral(changes.since_checkpoint, false, `${path}.since_checkpoint`);
}

function validateCapabilities(value: unknown, path: string): void {
  const capabilities = expectRecord(value, path);
  const keys = [
    "can_manage_team",
    "can_manage_source",
    "can_import_source",
    "can_start_source_read",
    "can_generate_briefing",
    "can_create_proposal",
    "can_review_proposal",
    "can_execute_external",
    "can_resolve_world",
    "can_acknowledge_changes"
  ];
  expectKeys(capabilities, keys, path);
  keys.forEach((key) => expectBoolean(capabilities[key], `${path}.${key}`));
}

function validateOnboarding(value: unknown, path: string): void {
  const onboarding = expectRecord(value, path);
  expectKeys(
    onboarding,
    [
      "contract_version",
      "readiness_version",
      "ready",
      "completed_count",
      "total_count",
      "completed_required",
      "required_total",
      "current_step_key",
      "steps",
      "next_action"
    ],
    path
  );
  expectEnum(
    onboarding.contract_version,
    ["onboarding.v1"] as const,
    `${path}.contract_version`
  );
  expectEnum(
    onboarding.readiness_version,
    ["onboarding-readiness.v1"] as const,
    `${path}.readiness_version`
  );
  const ready = expectBoolean(onboarding.ready, `${path}.ready`);
  const completedCount = expectNonNegativeInteger(
    onboarding.completed_count,
    `${path}.completed_count`
  );
  const totalCount = expectNonNegativeInteger(
    onboarding.total_count,
    `${path}.total_count`
  );
  const completedRequired = expectNonNegativeInteger(
    onboarding.completed_required,
    `${path}.completed_required`
  );
  const requiredTotal = expectNonNegativeInteger(
    onboarding.required_total,
    `${path}.required_total`
  );
  if (totalCount !== HEADQUARTERS_ONBOARDING_STEP_KEYS.length) {
    contractError(`${path}.total_count`, "exactly five onboarding steps");
  }
  if (requiredTotal !== 3) {
    contractError(`${path}.required_total`, "exactly three required steps");
  }

  const steps = expectArray(onboarding.steps, `${path}.steps`);
  if (steps.length !== HEADQUARTERS_ONBOARDING_STEP_KEYS.length) {
    contractError(`${path}.steps`, "exactly five ordered onboarding steps");
  }
  const stepRecords: HeadquartersRecord[] = [];
  steps.forEach((value, index) => {
    const stepPath = `${path}.steps[${index}]`;
    const step = expectRecord(value, stepPath);
    stepRecords.push(step);
    expectKeys(
      step,
      ["key", "state", "requirement", "label", "benefit", "evidence", "action"],
      stepPath
    );
    const key = expectEnum(
      step.key,
      HEADQUARTERS_ONBOARDING_STEP_KEYS,
      `${stepPath}.key`
    );
    if (key !== HEADQUARTERS_ONBOARDING_STEP_KEYS[index]) {
      contractError(
        `${stepPath}.key`,
        HEADQUARTERS_ONBOARDING_STEP_KEYS[index] ?? "known onboarding step"
      );
    }
    const stepState = expectEnum(
      step.state,
      ["complete", "pending", "unknown"] as const,
      `${stepPath}.state`
    );
    const requirement = expectEnum(
      step.requirement,
      ["recommended", "required"] as const,
      `${stepPath}.requirement`
    );
    const expectedRequirement = [
      "required",
      "recommended",
      "required",
      "recommended",
      "required"
    ][index];
    if (requirement !== expectedRequirement) {
      contractError(
        `${stepPath}.requirement`,
        expectedRequirement ?? "known onboarding requirement"
      );
    }
    expectString(step.label, `${stepPath}.label`);
    expectString(step.benefit, `${stepPath}.benefit`);
    const evidence = expectArray(step.evidence, `${stepPath}.evidence`);
    if (evidence.length === 0) {
      contractError(`${stepPath}.evidence`, "at least one evidence fact");
    }
    const evidenceStates: HeadquartersOnboardingState[] = [];
    evidence.forEach((value, evidenceIndex) => {
      const evidencePath = `${stepPath}.evidence[${evidenceIndex}]`;
      const item = expectRecord(value, evidencePath);
      expectKeys(
        item,
        ["key", "label", "state", "value", "precision"],
        evidencePath
      );
      expectString(item.key, `${evidencePath}.key`);
      expectString(item.label, `${evidencePath}.label`);
      const state = expectEnum(
        item.state,
        ["complete", "pending", "unknown"] as const,
        `${evidencePath}.state`
      );
      evidenceStates.push(state);
      const precision = expectEnum(
        item.precision,
        ["exact", "unavailable"] as const,
        `${evidencePath}.precision`
      );
      const evidenceValue = expectNullableNonNegativeInteger(
        item.value,
        `${evidencePath}.value`
      );
      if (
        precision === "unavailable" &&
        (evidenceValue !== null || state !== "unknown")
      ) {
        contractError(evidencePath, "unavailable evidence must be unknown without a value");
      }
      if (
        precision === "exact" &&
        (evidenceValue === null || state === "unknown")
      ) {
        contractError(evidencePath, "exact evidence requires a known value and state");
      }
    });
    const expectedStepState: HeadquartersOnboardingState = evidenceStates.includes(
      "complete"
    )
      ? "complete"
      : evidenceStates.includes("unknown")
        ? "unknown"
        : "pending";
    if (stepState !== expectedStepState) {
      contractError(`${stepPath}.state`, "must match onboarding evidence");
    }
    validateAction(step.action, `${stepPath}.action`);
  });

  const completeCount = stepRecords.filter((step) => step.state === "complete").length;
  if (completedCount !== completeCount) {
    contractError(`${path}.completed_count`, "must match completed steps");
  }
  const requiredSteps = stepRecords.filter((step) => step.requirement === "required");
  if (requiredSteps.length !== requiredTotal) {
    contractError(`${path}.required_total`, "must match required steps");
  }
  const requiredCompleteCount = requiredSteps.filter(
    (step) => step.state === "complete"
  ).length;
  if (completedRequired !== requiredCompleteCount) {
    contractError(`${path}.completed_required`, "must match completed required steps");
  }
  const expectedReady = requiredCompleteCount === requiredTotal;
  if (ready !== expectedReady) {
    contractError(`${path}.ready`, "must match required step states");
  }

  const expectedCurrent = requiredSteps.find((step) => step.state !== "complete")?.key ?? null;
  if (onboarding.current_step_key !== null) {
    expectEnum(
      onboarding.current_step_key,
      HEADQUARTERS_ONBOARDING_STEP_KEYS,
      `${path}.current_step_key`
    );
  }
  if (onboarding.current_step_key !== expectedCurrent) {
    contractError(`${path}.current_step_key`, "first incomplete required step or null");
  }
  if (onboarding.next_action !== null) {
    validateAction(onboarding.next_action, `${path}.next_action`);
  }
  if (ready && onboarding.next_action !== null) {
    contractError(`${path}.next_action`, "null when onboarding is ready");
  }
  if (!ready && onboarding.next_action === null) {
    contractError(`${path}.next_action`, "the first required blocker action");
  }
  if (
    !ready &&
    onboarding.next_action !== null &&
    expectedCurrent !== null
  ) {
    const currentStep = stepRecords.find((step) => step.key === expectedCurrent);
    if (
      !currentStep ||
      !sameHeadquartersAction(
        expectRecord(onboarding.next_action, `${path}.next_action`),
        expectRecord(currentStep.action, `${path}.steps.current.action`)
      )
    ) {
      contractError(`${path}.next_action`, "must match the current required step");
    }
  }
}

function sameHeadquartersAction(
  first: HeadquartersRecord,
  second: HeadquartersRecord
): boolean {
  return ["disabled_reason", "enabled", "kind", "label", "target"].every(
    (key) => first[key] === second[key]
  );
}

function validateSnapshot(value: unknown, path: string): void {
  const snapshot = expectRecord(value, path);
  expectKeys(snapshot, ["id", "as_of", "partial", "warnings", "coverage"], path);
  expectString(snapshot.id, `${path}.id`);
  expectDateString(snapshot.as_of, `${path}.as_of`);
  expectBoolean(snapshot.partial, `${path}.partial`);
  expectStringArray(snapshot.warnings, `${path}.warnings`);
  const coverage = expectArray(snapshot.coverage, `${path}.coverage`);
  if (coverage.length !== HEADQUARTERS_COVERAGE_KEYS.length) {
    contractError(`${path}.coverage`, "exactly four projections");
  }
  coverage.forEach((value, index) => {
    const coveragePath = `${path}.coverage[${index}]`;
    const item = expectRecord(value, coveragePath);
    expectKeys(item, ["key", "status", "watermark", "warning"], coveragePath);
    expectEnum(
      item.key,
      ["company_world", "decisions", "identity", "sources"] as const,
      `${coveragePath}.key`
    );
    const status = expectEnum(
      item.status,
      ["complete", "partial", "unavailable"] as const,
      `${coveragePath}.status`
    );
    expectString(item.watermark, `${coveragePath}.watermark`);
    const warning = expectNullableString(item.warning, `${coveragePath}.warning`);
    if (status === "complete" && warning !== null) {
      contractError(`${coveragePath}.warning`, "null for complete coverage");
    }
    if (status !== "complete" && !warning) {
      contractError(
        `${coveragePath}.warning`,
        "non-empty warning for incomplete coverage"
      );
    }
    if (item.key !== HEADQUARTERS_COVERAGE_KEYS[index]) {
      contractError(
        `${coveragePath}.key`,
        HEADQUARTERS_COVERAGE_KEYS[index]
      );
    }
  });
}

function validateWorkspace(value: unknown, path: string): void {
  const workspace = expectRecord(value, path);
  expectKeys(workspace, ["id", "name", "role"], path);
  expectString(workspace.id, `${path}.id`);
  expectString(workspace.name, `${path}.name`);
  expectEnum(workspace.role, ["admin", "member", "owner", "viewer"] as const, `${path}.role`);
}

function validateBoundary(value: unknown, path: string): void {
  const boundary = expectRecord(value, path);
  expectKeys(
    boundary,
    ["provider_calls", "external_writes", "llm", "reads_secrets", "transaction"],
    path
  );
  expectLiteral(boundary.provider_calls, false, `${path}.provider_calls`);
  expectLiteral(boundary.external_writes, false, `${path}.external_writes`);
  expectLiteral(boundary.llm, false, `${path}.llm`);
  expectLiteral(boundary.reads_secrets, false, `${path}.reads_secrets`);
  expectEnum(
    boundary.transaction,
    ["repeatable_read_read_only"] as const,
    `${path}.transaction`
  );
}

function expectRecord(value: unknown, path: string): HeadquartersRecord {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    contractError(path, "object");
  }
  return value as HeadquartersRecord;
}

function expectKeys(record: HeadquartersRecord, keys: string[], path: string): void {
  const expected = new Set(keys);
  for (const key of keys) {
    if (!(key in record)) {
      contractError(`${path}.${key}`, "required field");
    }
  }
  for (const key of Object.keys(record)) {
    if (!expected.has(key)) {
      contractError(`${path}.${key}`, "unexpected field");
    }
  }
}

function expectArray(value: unknown, path: string): unknown[] {
  if (!Array.isArray(value)) {
    contractError(path, "array");
  }
  return value;
}

function expectString(value: unknown, path: string): string {
  if (typeof value !== "string") {
    contractError(path, "string");
  }
  return value;
}

function expectNullableString(value: unknown, path: string): string | null {
  if (value === null) {
    return null;
  }
  return expectString(value, path);
}

function expectStringArray(value: unknown, path: string): string[] {
  const values = expectArray(value, path);
  return values.map((item, index) => expectString(item, `${path}[${index}]`));
}

function expectBoolean(value: unknown, path: string): boolean {
  if (typeof value !== "boolean") {
    contractError(path, "boolean");
  }
  return value;
}

function expectNullableNumber(value: unknown, path: string): number | null {
  if (value === null) {
    return null;
  }
  if (typeof value !== "number" || !Number.isFinite(value)) {
    contractError(path, "finite number or null");
  }
  return value;
}

function expectNonNegativeInteger(value: unknown, path: string): number {
  if (typeof value !== "number" || !Number.isInteger(value) || value < 0) {
    contractError(path, "non-negative integer");
  }
  return value;
}

function expectNullableNonNegativeInteger(value: unknown, path: string): number | null {
  if (value === null) {
    return null;
  }
  return expectNonNegativeInteger(value, path);
}

function expectDateString(value: unknown, path: string): string {
  const date = expectString(value, path);
  if (Number.isNaN(Date.parse(date))) {
    contractError(path, "ISO date string");
  }
  return date;
}

function expectNullableDateString(value: unknown, path: string): string | null {
  if (value === null) {
    return null;
  }
  return expectDateString(value, path);
}

function expectEnum<const T extends readonly string[]>(
  value: unknown,
  allowed: T,
  path: string
): T[number] {
  const candidate = expectString(value, path);
  if (!allowed.includes(candidate as T[number])) {
    contractError(path, allowed.join(" | "));
  }
  return candidate as T[number];
}

function expectLiteral<T>(value: unknown, expected: T, path: string): T {
  if (value !== expected) {
    contractError(path, JSON.stringify(expected));
  }
  return expected;
}

function validateInternalActionTarget(value: string, path: string): void {
  if (
    !value.startsWith("/") ||
    value.startsWith("//") ||
    hasUnsafeTargetCharacter(value)
  ) {
    contractError(path, "safe internal path");
  }
}

function validateEvidenceTarget(value: string, path: string): void {
  if (value.startsWith("/")) {
    validateInternalActionTarget(value, path);
    return;
  }
  if (hasUnsafeTargetCharacter(value)) {
    contractError(path, "safe internal path or http(s) URL");
  }
  if (value.length > HEADQUARTERS_EVIDENCE_URL_MAX_LENGTH) {
    contractError(path, "safe internal path or http(s) URL");
  }
  try {
    const parsed = new URL(value);
    if (
      (parsed.protocol !== "http:" && parsed.protocol !== "https:") ||
      !parsed.hostname ||
      parsed.username ||
      parsed.password
    ) {
      contractError(path, "safe internal path or http(s) URL");
    }
    if (
      Array.from(parsed.searchParams.keys()).some((key) =>
        SENSITIVE_EVIDENCE_URL_QUERY_KEYS.has(
          key.toLowerCase().replaceAll("-", "_")
        )
      )
    ) {
      contractError(path, "safe internal path or http(s) URL");
    }
  } catch (error) {
    if (error instanceof HeadquartersContractError) {
      throw error;
    }
    contractError(path, "safe internal path or http(s) URL");
  }
}

function hasUnsafeTargetCharacter(value: string): boolean {
  return value.includes("\\") || /[\s\u0000-\u001f\u007f]/u.test(value);
}

function contractError(path: string, expected: string): never {
  throw new HeadquartersContractError(`${path}: expected ${expected}`);
}
