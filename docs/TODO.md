# FounderOS TODO

Только ближайшие задачи. Полный продуктовый контракт:
`../founderOS_MASTER_PLAYBOOK.md`. Проверяемый переход:
`AI_FOUNDEROS_ACCEPTANCE.md`.

## Сейчас — Repository Intelligence

1. RI-001–RI-009 merged в `main` через PR #35, #34, #38, #39 и #40.
   Preparation-only L0/L1 portfolio dry-run boundary реализован (DEC-127): он
   валидирует private exact-SHA manifest и выдаёт content-free receipt без
   provider/repository read, job enqueue или persistence. Следующий шаг —
   owner-private manifest validation; actual portfolio read всё ещё требует
   нового explicit founder instruction. Real-repository L2 disabled.

RI-001 завершён: strict `repository_intelligence.v1`, synthetic L0/L1/L2
fixtures, object-shaped evidence, finite confidence, human-only resolution,
directional relationships и contradiction validation реализованы без migration,
persistence, UI, provider/LLM call или чтения company repositories (DEC-115).
RI-002 завершён: workspace-scoped canonical L0 читает только `Repository` +
active identity-matching `SourceRecord`, сохраняет unknown без evidence и не
использует filesystem/provider fallback (DEC-116).
RI-003 завершён: exact-SHA checkout использует внешний ephemeral runtime path,
не выполняет target code, не наследует credentials/network и удаляет run на
каждом exit (DEC-117).
RI-004 завершён: bounded deterministic collector читает только synthetic RI-003
checkout, извлекает sanitized manifests/entrypoints/dependencies/interfaces/
deployment/tests/CI/documentation/migrations с evidence на каждый факт и не
выполняет target code (DEC-118).
RI-005 завершён: trusted synthetic portfolio + RI-004 facts строят directional
observed/inferred candidates, unresolved targets, inverse views, symmetric
normalization, cycle/orphan findings и fail-closed contradiction review без
company read или persistence (DEC-119).
RI-006 merged в `main` 2026-08-02: migration, jobs/runs/facts/relationships/
findings/contradictions, canonical evidence links, complete-only
reconciliation, retry/cancel/idempotency, 30-day artifact refs и explicit
deletion реализованы и проверены только на synthetic DB data (DEC-120).
RI-007 реализован 2026-08-03: bounded workspace-scoped read APIs, Repository
Portfolio/Detail, directional graph, evidence drawer, unknown/confirmation
queue, audit history/freshness и local filters работают только поверх RI-006
PostgreSQL rows; raw source bodies и artifact paths не возвращаются (DEC-124).
RI-008 реализован 2026-08-03: strict versioned source-claim envelopes из
GitHub issues/PRs, Jira tasks и opt-in internal documents exact-сравниваются с
current RI facts; agreements, contradictions и insufficient evidence сохраняют
обе evidence sides, unsupported/free-text/fuzzy claims fail closed (DEC-125).
RI-009 реализован 2026-08-03 как closed hostile-synthetic proof:
fixed probe, minimal env, read-only source, scratch-only writes, network deny и
CPU/file/process/output/wall-time bounds проверяются без company repository
access. Hard RAM и aggregate scratch bounds на текущем macOS backend
доказать нельзя, поэтому self-test fail closed и real-repository L2 disabled
(DEC-126).
Portfolio dry run подготовлен 2026-08-03: strict private manifest требует
canonical identity, exact SHA и L0/L1-only; content-free receipt подтверждает
zero provider/repository reads, jobs, persistence и writes, фиксируя будущие
failure/restart/retention/rollback boundaries (DEC-127).

## Сейчас — завершение FounderOS 2.0 reset

1. Заново внести нужные provider credentials только через
   `Настройки → AI` и `Настройки → Подключения`, выполнить отдельные
   read-only проверки и не возвращать environment fallbacks.
2. Подключить approved external error-reporting/tracing sink без payloads и
   завершить fail-closed hosted topology/RLS gate. Локальные structured logs,
   request IDs, counters и database readiness уже реализованы.
3. Провести разрешённые authenticated session/workspace и desktop/mobile
   browser gates и проверить
   overflow, console и основные состояния.
4. Подтвердить один read-only GitHub App read из рабочей организации с видимым
   canonical результатом.
5. Настроить реальное независимое backup-хранилище и отдельное хранение ключа,
   выполнить первый encrypted export и полный restore drill. Механизм и
   runbook реализованы, но same-machine тест не является внешним proof.
6. В приватном GitHub проверить visibility, branch protection и private
   security-reporting channel; файлы LICENSE/SECURITY/CONTRIBUTING/CODEOWNERS
   уже добавлены локально.
7. Продолжать снижать ratchet для Headquarters, ActionProposalsPanel и global
   CSS только bounded slices с characterization конкретного поведения; broad
   refactor запрещён DEC-110.

## Следом — память и настоящее второе мнение

1. Добавить полные paginated live provider reads для Jira/Gmail/Drive, после
   чего подключить их к `source-reconciliation.v1`. Текущие локальные импорты
   не имеют права объявлять исчезновение.
2. Добавить обязательства клиентов, решения и риски с evidence.
3. Расширять contradiction detection новыми source claim adapters только
   через strict versioned contracts; базовый GitHub/Jira/document RI-008 slice
   реализован (DEC-125).
4. Расширить Memory Control v1 с внутренних документов на provider-backed
   canonical records: exact dependency preview, evidence-safe cascade,
   reconciliation/reimport behavior и честная provider-side deletion boundary.

Workspace AI/privacy control, encrypted key lifecycle, provider-retention
acknowledgement, model/budget controls и synthetic read-only connection check
реализованы. Настоящий credentialed smoke ещё не выполнен.

Memory Control v1 реализован для FounderOS-authored документов: correction
purges prior versions, forget удаляет active row и все версии, stale preview
fail closed. Backups остаются до retention rotation; внешний provider cascade
ещё не реализован.

## Внешний gate

Один founder-approved repository-scoped read из рабочей GitHub-организации с
видимым canonical результатом и безопасной квитанцией. До него не подключать
новые provider-first продуктовые экраны.

Публичный multi-tenant hosting дополнительно заблокирован до полного RLS gate
из DEC-102. Составные tenant FK уже обязательны, но не заменяют RLS.

Disaster recovery operational readiness дополнительно заблокирован до первого
успешного restore drill с физически независимого хранилища и отдельно
восстановленного ключа (DEC-108).
