# FounderOS Roadmap

Roadmap подчинён `../founderOS_MASTER_PLAYBOOK.md`. Живое состояние находится в
`../PROGRESS.md`, проверяемый ledger — в `AI_FOUNDEROS_ACCEPTANCE.md`.

## Фаза 0 — Safety gates

Цель: разработка и проверки не могут повредить рабочие данные.

- pytest fail-closed до импорта приложения;
- отдельная test-marked PostgreSQL БД локально и в CI;
- migration metadata drift проверяется через `alembic check`;
- atomic execution claim, DB-idempotency, actual actor, uncertain state и
  provider reconciliation реализованы;
- строгая evidence_ref.v1 schema, canonical same-workspace resolution,
  relevance check, pre-provider revalidation, exact AI/system snapshot и
  versioned/idempotent bulk decisions реализованы;
- пять workspace-owned отношений защищены составными PostgreSQL foreign keys,
  а operational GitHub reads явно scoped по workspace;
- backend static typing (`mypy app`) и настоящий frontend Biome lint являются
  локальными и CI quality gates;
- liveness отделена от database readiness; structured request events,
  correlation IDs, bounded process metrics, Origin enforcement, hosted browser
  headers и local-only OpenAPI реализованы;
- public Argon2 endpoints разделяют admission policy; Redis backend, trusted
  proxy resolution, auth-artifact cleanup и throttled session activity
  реализованы;
- smoke gates явно разделены на liveness, session, workspace и desktop/mobile
  browser E2E;
- прямые runtime dependencies объявлены, неиспользуемые provider SDK и legacy
  config удалены, Python/frontend vulnerability audits обязательны, а local
  datastore images закреплены digest и обслуживаются Renovate;
- GitHub provider reads выполняются через durable PostgreSQL jobs с
  lease/retry/resume/progress/cancel, bounded workers, shared HTTP pool и
  короткими repository-scoped транзакциями;
- Repository Intelligence RI-001–RI-006 реализован на synthetic data:
  strict contracts, canonical L0, exact-SHA checkout, bounded static
  collectors, directional graph candidates и durable
  jobs/runs/facts/relationships/findings/contradictions с complete-only
  reconciliation. RI-007 UI и реальный portfolio run остаются approval-gated;
- локальный rollback дополнен AES-256-GCM off-device export, проверкой после
  шифрования, full restore drill и explicit 7/4/12 retention; первый реальный
  независимый export/drill остаётся owner-operated gate;
- private-source license, security/contribution policies, owner CODEOWNERS и
  repository pre-commit quality/secret hook реализованы;
- для крупнейших модулей действует line-budget ratchet, Headquarters имеет
  deterministic query-scaling test, action API schemas вынесены bounded slice,
  а два obsolete synchronous GitHub sync path удалены (DEC-110);
- внешние записи остаются выключенными до завершения остальных high-priority
  remediation;
- публичный multi-tenant hosting заблокирован до полного RLS gate из DEC-102.

Все четыре high-priority замечания аудита и medium findings M2–M15, M17 и M18
получили локально проверяемые controls либо сведены к явно записанному внешнему
gate. Distributed tracing/error reporting, первый реальный off-device
restore proof и полный RLS ещё не объявлены готовыми. M16 переведён в
проверяемую incremental policy: дальнейшее уменьшение больших UI/CSS/read-model
модулей выполняется только bounded slices с отдельными тестами.

## Фаза 1 — Product reset

Цель: заменить Command Center на простой AI-first продукт.

- «Сейчас / Компания / Спросить / Настройки»;
- один главный вывод и максимум три сигнала;
- progressive disclosure до evidence;
- провайдеры и диагностика только в настройках;
- удаление старых маршрутов, demo и дублирующего UI.

Готово, когда разделы B, C, D, E, H и I acceptance-ledger закрыты.

## Фаза 2 — Temporal company memory

Цель: FounderOS понимает историю, а не только текущий снимок.

- unified entities/events/relationships;
- event time и observed time;
- решения, обязательства и риски;
- checkpoint и «что изменилось» — Temporal Memory v2 реализован;
- append-only lifecycle ledger для Action Proposal и Company World реализован;
- GitHub issue/PR reconciliation/tombstones реализованы для полных
  server-attested repository snapshots; Jira/Gmail/Drive ждут полных live
  provider reads;
- contradiction detection;
- исправление, забывание и retention controls — реализованы для внутренних
  документов; provider-backed cascade остаётся отдельным gate.

Готово, когда FounderOS может доказательно ответить «что изменилось, почему и
что мы обещали».

## Фаза 3 — AI second opinion

Цель: generative reasoning поверх проверяемой памяти.

- workspace/permission-scoped retrieval;
- strict schemas — `assistant.v2` реализован;
- fact / interpretation / objection / recommendation — реализовано;
- evidence critic и unsupported-claim rejection — реализовано для bounded
  snapshot facts;
- model/privacy/budget controls в `/settings/ai` — реализованы;
- chat memory только после явного opt-in.

Готово, когда AI даёт полезное второе мнение и каждый значимый вывод ведёт к
evidence.

## Фаза 4 — Controlled action

Цель: безопасно завершать управленческий цикл.

- evidence-backed draft;
- preview последствий;
- human approval;
- idempotent provider execution;
- read-back receipt;
- обновление company memory.

Готово, когда полный сценарий GitHub проходит от сигнала до проверенного
результата без прямой LLM-мутации.

## Фаза 5 — Более широкая картина

Источники добавляются только по доказанной ценности:

1. рабочий GitHub + Jira/Linear;
2. communications + calendar;
3. documents;
4. CRM + support;
5. production analytics;
6. finance.

Каждый новый источник обязан определить scopes, retention, deletion, evidence,
read check и write boundary до реализации.
