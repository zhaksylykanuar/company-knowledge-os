import type {
  HeadquartersAction,
  HeadquartersEvidenceRef
} from "./headquarters";
import { safeHref } from "./safeHref";

export const ASSISTANT_QUERY_MAX_CHARS = 500;

export const ASSISTANT_INTENTS = [
  "action_request",
  "briefing",
  "company_person",
  "current_priority",
  "decision_status",
  "evidence",
  "owners",
  "sources",
  "unsupported",
  "waiting_decisions",
  "why_now"
] as const;

export type AssistantIntent = (typeof ASSISTANT_INTENTS)[number];

export type AssistantQueryRequest = {
  query: string;
  expected_snapshot_id: string;
};

export type AssistantSuggestion = {
  id: string;
  label: string;
  query: string;
};

export type AssistantQueryResponse = {
  contract_version: "assistant.v1";
  intent: AssistantIntent;
  text: string;
  citations: HeadquartersEvidenceRef[];
  suggestions: AssistantSuggestion[];
  action: HeadquartersAction | null;
  snapshot_id: string;
  as_of: string;
  partial: boolean;
  warnings: string[];
  is_live: true;
  llm_used: false;
};

export class AssistantContractError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "AssistantContractError";
  }
}

const SAFE_ASSISTANT_ACTION_PREFIXES = [
  "/actions",
  "/briefings",
  "/company-brain",
  "/connectors",
  "/dashboard",
  "/documents",
  "/drive",
  "/github",
  "/gmail",
  "/jira"
] as const;

const SENSITIVE_CITATION_QUERY_KEYS = new Set([
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

export function parseAssistantQueryResponse(value: unknown): AssistantQueryResponse {
  const response = expectRecord(value, "assistant");
  expectKeys(
    response,
    [
      "contract_version",
      "intent",
      "text",
      "citations",
      "suggestions",
      "action",
      "snapshot_id",
      "as_of",
      "partial",
      "warnings",
      "is_live",
      "llm_used"
    ],
    "assistant"
  );
  expectLiteral(response.contract_version, "assistant.v1", "contract_version");
  expectEnum(response.intent, ASSISTANT_INTENTS, "intent");
  expectBoundedString(response.text, "text", 1, 600);
  validateCitations(response.citations);
  validateSuggestions(response.suggestions);
  if (response.action !== null) validateAction(response.action);
  const snapshotId = expectBoundedString(response.snapshot_id, "snapshot_id", 69, 69);
  if (!/^hqs1_[0-9a-f]{64}$/.test(snapshotId)) {
    contractError("snapshot_id", "must be an hqs1 content id");
  }
  const asOf = expectBoundedString(response.as_of, "as_of", 1, 80);
  if (!Number.isFinite(Date.parse(asOf))) {
    contractError("as_of", "must be an ISO datetime");
  }
  expectBoolean(response.partial, "partial");
  validateWarnings(response.warnings);
  expectLiteral(response.is_live, true, "is_live");
  expectLiteral(response.llm_used, false, "llm_used");
  return value as AssistantQueryResponse;
}

function validateCitations(value: unknown): void {
  if (!Array.isArray(value) || value.length > 8) {
    contractError("citations", "must be an array with at most 8 items");
  }
  value.forEach((rawCitation, index) => {
    const path = `citations[${index}]`;
    const citation = expectRecord(rawCitation, path);
    expectKeys(
      citation,
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
    expectBoundedString(citation.id, `${path}.id`, 1, 180);
    expectBoundedString(citation.kind, `${path}.kind`, 1, 80);
    expectEnum(
      citation.source_key,
      ["drive", "github", "gmail", "internal", "jira"] as const,
      `${path}.source_key`
    );
    expectBoundedString(citation.label, `${path}.label`, 1, 180);
    validateCitationTarget(citation.target, `${path}.target`);
    expectEnum(
      citation.provenance,
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
    expectEnum(citation.trust, ["aggregate", "verified"] as const, `${path}.trust`);
    expectEnum(
      citation.reference_type,
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
    expectBoundedString(citation.reference_id, `${path}.reference_id`, 1, 180);
    expectLiteral(citation.workspace_scoped, true, `${path}.workspace_scoped`);
  });
}

function validateSuggestions(value: unknown): void {
  if (!Array.isArray(value) || value.length > 4) {
    contractError("suggestions", "must be an array with at most 4 items");
  }
  const ids = new Set<string>();
  value.forEach((rawSuggestion, index) => {
    const path = `suggestions[${index}]`;
    const suggestion = expectRecord(rawSuggestion, path);
    expectKeys(suggestion, ["id", "label", "query"], path);
    const id = expectBoundedString(suggestion.id, `${path}.id`, 1, 40);
    if (ids.has(id)) contractError(`${path}.id`, "must be unique");
    ids.add(id);
    expectBoundedString(suggestion.label, `${path}.label`, 1, 120);
    expectBoundedString(
      suggestion.query,
      `${path}.query`,
      1,
      ASSISTANT_QUERY_MAX_CHARS
    );
  });
}

function validateAction(value: unknown): void {
  const action = expectRecord(value, "action");
  expectKeys(action, ["kind", "label", "target", "enabled", "disabled_reason"], "action");
  expectLiteral(action.kind, "navigate", "action.kind");
  expectBoundedString(action.label, "action.label", 1, 100);
  if (!isSafeAssistantActionTarget(action.target)) {
    contractError("action.target", "must be a safe internal path");
  }
  expectLiteral(action.enabled, true, "action.enabled");
  expectLiteral(action.disabled_reason, null, "action.disabled_reason");
}

function validateCitationTarget(value: unknown, path: string): void {
  if (value === null) return;
  if (typeof value !== "string") contractError(path, "must be a string or null");
  if (isSafeAssistantActionTarget(value) || isSafeExternalCitationTarget(value)) return;
  contractError(path, "must be a safe internal or http(s) target");
}

export function isSafeInternalTarget(value: unknown): value is string {
  if (
    typeof value !== "string" ||
    !value.startsWith("/") ||
    value.startsWith("//") ||
    value.includes("\\") ||
    /\s|[\u0000-\u001f\u007f]/u.test(value)
  ) {
    return false;
  }
  try {
    const parsed = new URL(value, "http://founderos.local");
    return parsed.origin === "http://founderos.local" && parsed.pathname.startsWith("/");
  } catch {
    return false;
  }
}

export function isSafeAssistantActionTarget(value: unknown): value is string {
  if (!isSafeInternalTarget(value)) return false;
  return SAFE_ASSISTANT_ACTION_PREFIXES.some(
    (prefix) =>
      value === prefix ||
      value.startsWith(`${prefix}/`) ||
      value.startsWith(`${prefix}?`)
  );
}

function isSafeExternalCitationTarget(value: string): boolean {
  if (
    value.length > 1_000 ||
    value.includes("\\") ||
    /\s|[\u0000-\u001f\u007f]/u.test(value) ||
    safeHref(value) !== value
  ) {
    return false;
  }
  const parsed = new URL(value);
  if (parsed.username || parsed.password) return false;
  return ![...parsed.searchParams.keys()].some((key) =>
    SENSITIVE_CITATION_QUERY_KEYS.has(
      key.toLocaleLowerCase("en-US").replaceAll("-", "_")
    )
  );
}

function validateWarnings(value: unknown): void {
  if (!Array.isArray(value) || value.length > 8) {
    contractError("warnings", "must be an array with at most 8 items");
  }
  value.forEach((warning, index) => {
    expectBoundedString(warning, `warnings[${index}]`, 1, 160);
  });
}

function expectRecord(value: unknown, path: string): Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    contractError(path, "must be an object");
  }
  return value as Record<string, unknown>;
}

function expectKeys(
  value: Record<string, unknown>,
  expected: readonly string[],
  path: string
): void {
  const actual = Object.keys(value).sort();
  const wanted = [...expected].sort();
  if (actual.length !== wanted.length || actual.some((key, index) => key !== wanted[index])) {
    contractError(path, "contains unexpected or missing keys");
  }
}

function expectBoundedString(
  value: unknown,
  path: string,
  min: number,
  max: number
): string {
  if (typeof value !== "string" || value.length < min || value.length > max) {
    contractError(path, `must be a string between ${min} and ${max} characters`);
  }
  return value;
}

function expectBoolean(value: unknown, path: string): boolean {
  if (typeof value !== "boolean") contractError(path, "must be a boolean");
  return value;
}

function expectLiteral<T>(value: unknown, expected: T, path: string): T {
  if (value !== expected) contractError(path, `must equal ${String(expected)}`);
  return expected;
}

function expectEnum<T extends string>(
  value: unknown,
  allowed: readonly T[],
  path: string
): T {
  if (typeof value !== "string" || !allowed.includes(value as T)) {
    contractError(path, "contains an unsupported value");
  }
  return value as T;
}

function contractError(path: string, message: string): never {
  throw new AssistantContractError(`${path}: ${message}`);
}
