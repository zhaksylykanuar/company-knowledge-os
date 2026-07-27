import {
  parseHeadquartersSnapshotResponse,
  type HeadquartersAction,
  type HeadquartersEvidenceRef,
  type HeadquartersMission,
  type HeadquartersSnapshotResponse,
  type HeadquartersSourceHealth
} from "../../lib/headquarters";

const HEADQUARTERS_TEST_ACTION: HeadquartersAction = {
  kind: "review_proposal",
  label: "Проверить решение",
  target: "/actions?proposal=11111111-1111-4111-8111-111111111111&status=proposed",
  enabled: true,
  disabled_reason: null
};

const HEADQUARTERS_TEST_EVIDENCE: HeadquartersEvidenceRef = {
  id: "evidence_ref:evidence-1",
  kind: "github_issue",
  source_key: "github",
  label: "GitHub issue #42",
  target: "https://github.com/acme/founderos/issues/42",
  provenance: "canonical_evidence_ref",
  trust: "verified",
  reference_type: "evidence_ref",
  reference_id: "evidence-1",
  workspace_scoped: true
};

const HEADQUARTERS_TEST_PRIORITY: HeadquartersMission = {
  id: "mission-priority-1",
  kind: "review_proposal",
  reference_type: "proposal",
  reference_id: "11111111-1111-4111-8111-111111111111",
  title: "Подтвердить план запуска Atlas",
  summary: "Команда подготовила решение по сроку запуска.",
  why_now: "Предложение подтверждено каноническим GitHub evidence и ждёт решения.",
  status: "proposed",
  severity: "high",
  confidence: 0.91,
  confidence_precision: "exact",
  due_at: "2026-07-18T12:00:00Z",
  impact: "Снимает блокировку запуска для ключевого заказчика.",
  next_step: "Проверить evidence и принять либо отклонить решение.",
  owner_person_ids: ["person-owner-1"],
  organization_id: "organization-atlas",
  primary_person_id: "person-customer-1",
  source_keys: ["github"],
  evidence_refs: [HEADQUARTERS_TEST_EVIDENCE],
  proposal_id: "11111111-1111-4111-8111-111111111111",
  proposal_version: "proposal-version-1",
  evidence_state: "verified",
  trust_class: "verified_canonical",
  ranking_reason: "verified_proposal",
  fact_provenance: {
    owner: [HEADQUARTERS_TEST_EVIDENCE],
    customer: [HEADQUARTERS_TEST_EVIDENCE],
    due: [HEADQUARTERS_TEST_EVIDENCE],
    impact: [HEADQUARTERS_TEST_EVIDENCE],
    severity: [HEADQUARTERS_TEST_EVIDENCE],
    confidence: [HEADQUARTERS_TEST_EVIDENCE]
  },
  action: HEADQUARTERS_TEST_ACTION,
  correlation_reason: null,
  correlation_rule_version: null
};

const HEADQUARTERS_TEST_SOURCE: HeadquartersSourceHealth = {
  key: "github",
  name: "GitHub",
  configuration: "configured",
  read: "succeeded",
  data: "available",
  freshness: "fresh",
  primary_state: "healthy",
  attention_reason: null,
  scopes: ["repository:acme/founderos"],
  last_success_at: "2026-07-16T09:58:00Z",
  last_attempt_at: "2026-07-16T09:58:00Z",
  last_data_observed_at: "2026-07-16T09:57:00Z",
  fresh_until: "2026-07-16T10:58:00Z",
  freshness_policy_version: "source-health.v1",
  connection_count: 1,
  connection_count_precision: "exact",
  record_count: 42,
  record_count_precision: "exact",
  blocker: null,
  safe_debug_id: null,
  next_action: {
    kind: "open_source",
    label: "Открыть GitHub",
    target: "/settings/integrations?provider=github",
    enabled: true,
    disabled_reason: null
  }
};

const BASE_HEADQUARTERS_FIXTURE = {
  contract_version: "headquarters.v3",
  ranking_version: "headquarters-ranking.v1",
  snapshot: {
    id: "hqs1_workspace-1_20260716",
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
        watermark: "company-world-1",
        warning: null
      },
      {
        key: "memory",
        status: "complete",
        watermark: "memory-1",
        warning: null
      }
    ]
  },
  workspace: {
    id: "workspace-1",
    name: "Acme Systems",
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
        benefit: "У FounderOS есть рабочее пространство.",
        evidence: [
          {
            key: "workspace",
            label: "Компания доступна текущему аккаунту",
            state: "complete",
            value: 1,
            precision: "exact"
          }
        ],
        action: {
          kind: "open_settings",
          label: "Открыть компанию",
          target: "/settings",
          enabled: true,
          disabled_reason: null
        }
      },
      {
        key: "source",
        state: "complete",
        requirement: "recommended",
        label: "Выбран первый источник",
        benefit: "Понятно, откуда FounderOS получает контекст.",
        evidence: [
          {
            key: "configured_sources",
            label: "Настроенные источники",
            state: "complete",
            value: 1,
            precision: "exact"
          }
        ],
        action: {
          kind: "open_sources",
          label: "Открыть источники",
          target: "/settings/integrations",
          enabled: true,
          disabled_reason: null
        }
      },
      {
        key: "canonical_data",
        state: "complete",
        requirement: "required",
        label: "Первые данные подтверждены",
        benefit: "FounderOS видит подтверждённые факты.",
        evidence: [
          {
            key: "canonical_records",
            label: "Канонические записи",
            state: "complete",
            value: 42,
            precision: "exact"
          }
        ],
        action: {
          kind: "open_sources",
          label: "Открыть источники",
          target: "/settings/integrations",
          enabled: true,
          disabled_reason: null
        }
      },
      {
        key: "context",
        state: "complete",
        requirement: "recommended",
        label: "Контекст компании появился",
        benefit: "Команда, карта и решения делают картину полезнее.",
        evidence: [
          {
            key: "context_signals",
            label: "Подтверждённые элементы контекста",
            state: "complete",
            value: 3,
            precision: "exact"
          }
        ],
        action: {
          kind: "open_company_world",
          label: "Открыть карту",
          target: "/company-brain",
          enabled: true,
          disabled_reason: null
        }
      },
      {
        key: "headquarters",
        state: "complete",
        requirement: "required",
        label: "Первый снимок рассчитан",
        benefit: "Компания видна как единая система.",
        evidence: [
          {
            key: "snapshot",
            label: "Согласованная картина компании",
            state: "complete",
            value: 1,
            precision: "exact"
          }
        ],
        action: {
          kind: "open_headquarters",
          label: "Открыть FounderOS",
          target: "/dashboard",
          enabled: true,
          disabled_reason: null
        }
      }
    ],
    next_action: null
  },
  sources: {
    healthy: 1,
    total: 1,
    configured_count: 1,
    data_ready_count: 1,
    attention_count: 0,
    count_precision: "exact",
    items: [HEADQUARTERS_TEST_SOURCE]
  },
  priority: HEADQUARTERS_TEST_PRIORITY,
  pulse: [
    {
      key: "waiting_decisions",
      label: "Ждут решения",
      value: 1,
      precision: "exact",
      empty_state: "Решений не требуется",
      target: "/actions?status=proposed",
      action: {
        kind: "open_decisions",
        label: "Открыть решения",
        target: "/actions?status=proposed",
        enabled: true,
        disabled_reason: null
      }
    },
    {
      key: "sources_attention",
      label: "Источники требуют внимания",
      value: 0,
      precision: "exact",
      empty_state: "Все источники в порядке",
      target: "/settings/integrations",
      action: {
        kind: "open_sources",
        label: "Открыть источники",
        target: "/settings/integrations",
        enabled: true,
        disabled_reason: null
      }
    },
    {
      key: "pending_relationships",
      label: "Связи ждут проверки",
      value: 1,
      precision: "exact",
      empty_state: "Новых связей нет",
      target: "/company-brain",
      action: {
        kind: "open_company_world",
        label: "Открыть связи",
        target: "/company-brain",
        enabled: true,
        disabled_reason: null
      }
    }
  ],
  queue: [
    {
      ...HEADQUARTERS_TEST_PRIORITY,
      id: "mission-world-1",
      kind: "review_world",
      reference_type: "world",
      reference_id: "world-candidate-1",
      title: "Проверить связь с заказчиком Atlas",
      summary: "Найден новый кандидат связи человека и компании.",
      why_now: "Связь влияет на контекст ключевого заказчика.",
      severity: "medium",
      due_at: null,
      impact: "Уточняет карту ключевых лиц заказчика.",
      next_step: "Проверить кандидата связи.",
      proposal_id: null,
      proposal_version: null,
      ranking_reason: "evidence_backed_relationship",
      action: {
        kind: "review_world",
        label: "Проверить связь",
        target: "/company-brain",
        enabled: true,
        disabled_reason: null
      },
      correlation_reason: "matched_email_domain",
      correlation_rule_version: "company-world.v1"
    }
  ],
  changes: {
    contract_version: "temporal-memory.v1",
    items: [
      {
        id: "change-proposal-1",
        kind: "proposal",
        change_type: "current",
        title: "Появилось решение по запуску Atlas",
        summary: "Предложение добавлено в очередь решений.",
        event_time: "2026-07-16T09:59:00Z",
        observed_at: "2026-07-16T10:00:00Z",
        confidence: 0.91,
        confidence_precision: "exact",
        source_keys: ["github"],
        evidence_refs: [HEADQUARTERS_TEST_EVIDENCE],
        target: "/actions?proposal=11111111-1111-4111-8111-111111111111&status=proposed",
        access_scope: "workspace",
        retention: "source_bound"
      }
    ],
    basis: "current_snapshot",
    cursor: null,
    checkpointed_at: null,
    since_checkpoint: false,
    total_count: 1,
    count_precision: "exact",
    has_more: false
  },
  capabilities: {
    can_manage_team: true,
    can_manage_source: true,
    can_import_source: true,
    can_start_source_read: true,
    can_generate_briefing: true,
    can_create_proposal: true,
    can_review_proposal: true,
    can_execute_external: false,
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
} satisfies HeadquartersSnapshotResponse;

export type HeadquartersFixtureMutator = (
  fixture: HeadquartersSnapshotResponse
) => void;

/**
 * Returns a fresh fixture and validates every mutation through the same strict
 * runtime parser used by the browser. Invalid test setup therefore fails at
 * fixture construction instead of silently weakening a UI assertion.
 */
export function makeHeadquartersFixture(
  mutate?: HeadquartersFixtureMutator
): HeadquartersSnapshotResponse {
  const fixture = structuredClone(BASE_HEADQUARTERS_FIXTURE);
  mutate?.(fixture);
  return parseHeadquartersSnapshotResponse(fixture);
}
