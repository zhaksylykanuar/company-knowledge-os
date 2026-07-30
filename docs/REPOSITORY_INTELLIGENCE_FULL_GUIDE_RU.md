# FounderOS Repository Intelligence — полное руководство по подготовке и запуску

Статус: RI-001 и RI-002 реализованы; следующий approval-gated этап — RI-003
Дата подготовки: 2026-07-30
Основной проект: `company-knowledge-os`
Подробный архитектурный план:
[`REPOSITORY_INTELLIGENCE_IMPLEMENTATION_PLAN.md`](REPOSITORY_INTELLIGENCE_IMPLEMENTATION_PLAN.md)

## 1. Цель

FounderOS должен уметь:

1. определить, что делает каждый репозиторий компании;
2. определить его назначение, обязанности, интерфейсы и зависимости;
3. понять, как репозитории связаны между собой;
4. отличить доказанный факт от гипотезы и человеческого подтверждения;
5. найти технические, архитектурные, операционные и организационные риски;
6. связать результаты с GitHub PR/issues, Jira, документами, людьми,
   продуктами и другими источниками компании;
7. хранить результаты как структурированные данные с evidence;
8. отслеживать, когда проблема появилась, была исправлена или вернулась;
9. предлагать действия через `ActionProposal`;
10. выполнять внешние действия только после подтверждения человека.

Repository Intelligence — это не только security/code audit. Результат должен
отвечать минимум на следующие вопросы:

- что делает репозиторий;
- какую функцию компании или продукта он обеспечивает;
- является ли он приложением, сервисом, библиотекой, инфраструктурой,
  data pipeline, test harness, документацией, экспериментом или legacy;
- какие API, пакеты, очереди, события, базы, схемы, storage и images он
  предоставляет;
- какие сервисы, пакеты и ресурсы он потребляет;
- какие другие репозитории от него зависят;
- кто является подтверждённым владельцем;
- какие документы или задачи противоречат фактическому коду;
- что изменилось между двумя аудитами.

## 2. Главная граница: сначала подготовить всё

До достижения milestone:

```text
Repository Intelligence Prepared
```

запрещено:

- открывать рабочие репозитории компании;
- читать их исходный код, README, manifests и Git history;
- клонировать их для аудита;
- обращаться к GitHub/Jira за их содержимым;
- выполнять их команды;
- определять их реальные назначения и связи;
- создавать реальные GitHub/Jira задачи;
- использовать production/company data как fixtures.

Во время подготовки разрешены только:

- код самого FounderOS;
- синтетические fixture-репозитории;
- отдельная test-marked PostgreSQL;
- временные директории;
- искусственные GitHub/Jira/document records;
- mock provider clients без реальных API-вызовов.

Readiness receipt должен подтвердить:

```text
company repositories read: 0
company repositories cloned: 0
company repository code executed: 0
provider content calls: 0
external tasks created: 0
```

Важно: полностью подготовить механизм можно заранее, но реальное описание
репозиториев и полную карту связей невозможно получить до их последующего
read-only анализа.

## 3. Какие папки нужны

Рекомендуемая структура:

```text
/Users/anuarzh/Developer/personal/
├── company-knowledge-os/
│   └── текущая рабочая папка FounderOS
│
├── company-knowledge-os-ri-prep/
│   └── отдельный Git worktree для подготовки Repository Intelligence
│
├── founderos-ri-data/
│   └── private runtime/staging/artifacts, не Git-репозиторий
│
└── <существующие рабочие репозитории>/
    ├── repo-a/
    ├── repo-b/
    └── ...
```

### 3.1 `company-knowledge-os-ri-prep`

Это отдельная папка, но не новый Git-репозиторий. Это sibling worktree того же
FounderOS.

В этой папке разрабатываются:

- contracts;
- database models и migrations;
- workers и jobs;
- analyzers;
- reconciliation;
- read models и UI;
- readiness tooling;
- tests и synthetic fixtures.

Преимущества:

- текущая рабочая папка FounderOS остаётся нетронутой;
- незакоммиченные изменения не смешиваются с Repository Intelligence;
- RI получает отдельную ветку;
- commits остаются локальными до отдельного разрешения на push.

### 3.2 `founderos-ri-data`

Это не Git-репозиторий и не место для исходного кода FounderOS.

Назначение:

```text
founderos-ri-data/
├── readiness/
├── manifests/
├── worktrees/
├── runs/
├── artifacts/
├── receipts/
└── cache/
```

Во время подготовки там находятся только synthetic artifacts.

После отдельного разрешения там могут появиться результаты реальных
репозиториев до их validation/import в FounderOS.

Окончательными источниками истины остаются:

```text
PostgreSQL + approved raw storage
```

Markdown, PDF и Obsidian остаются rebuildable exports.

## 4. Текущее состояние

Проверенное состояние на 2026-07-30:

```text
current directory:
  /Users/anuarzh/Developer/personal/company-knowledge-os-ri-prep

current branch:
  codex/repository-intelligence-prep

RI-001:
  implemented and verified on synthetic fixtures

next slice:
  RI-003 after separate approval
```

Это снимок состояния, а не вечная константа. Перед каждым новым тикетом агент
обязан снова выполнить:

```bash
git status --short
git branch --show-current
git rev-parse --short HEAD
git log -1 --oneline
```

Запрещены:

```text
git reset
git stash
git clean
удаление незнакомых файлов
перезапись unrelated work
```

## 5. Как создать отдельный worktree

Сначала нужно определить утверждённую базу.

Предпочтительный вариант:

- актуальный `main`, если он содержит нужные commits;
- либо конкретный commit, явно подтверждённый человеком.

Не следует автоматически использовать старый hash, если состояние репозитория
изменилось.

Пример после проверки базы:

```bash
cd /Users/anuarzh/Developer/personal/company-knowledge-os

git worktree add \
  ../company-knowledge-os-ri-prep \
  -b codex/repository-intelligence-prep \
  <approved-base-commit>
```

Затем переносится только implementation plan:

```bash
cp \
  docs/REPOSITORY_INTELLIGENCE_IMPLEMENTATION_PLAN.md \
  ../company-knowledge-os-ri-prep/docs/
```

Не переносить:

```text
.env.local
.local/
raw storage
credentials
provider payloads
company data
web/next-env.d.ts
другие незакоммиченные файлы
```

Далее:

```bash
cd /Users/anuarzh/Developer/personal/company-knowledge-os-ri-prep
git status --short
```

Ожидаемый новый файл:

```text
?? docs/REPOSITORY_INTELLIGENCE_IMPLEMENTATION_PLAN.md
```

Сохранить plan отдельным локальным commit:

```bash
git add docs/REPOSITORY_INTELLIGENCE_IMPLEMENTATION_PLAN.md
bash scripts/check_no_secrets.sh --staged
git diff --cached --check
git commit -m "docs: add repository intelligence implementation plan"
```

Ничего не пушить.

Если sandbox запрещает создать sibling worktree, агент должен запросить
разрешение на `git worktree add`, а не искать обходной путь.

## 6. Как должен работать агент

Общая цель — завершить весь preparation track. Но реализация выполняется по
одному reviewable тикету.

Правильный цикл:

```text
RI-001
  -> focused tests
  -> Ruff
  -> guarded backend-check
  -> secret scans
  -> scoped local commit
  -> отчёт
  -> human review
  -> RI-002
  -> ...
```

Нельзя реализовывать RI-001–RI-009 одним большим изменением.

Агент останавливается, если:

- требуется новое архитектурное решение;
- требуется migration/persistence approval;
- требуется опасная операция;
- нужно читать рабочий репозиторий;
- нужен реальный provider API;
- нужен доступ к секрету;
- проверки требуют production/company data.

При этом конечной целью подготовки остаётся полный milestone
`Repository Intelligence Prepared`, а не только RI-001.

## 7. Что брать из текущего FounderOS

### 7.1 Канонические модели

Источник:

```text
app/db/canonical_models.py
```

| Модель | Использование |
|---|---|
| `SourceRecord` | Санитизированная запись исходного audit run |
| `EvidenceRef` | Связь claim с SourceRecord |
| `Repository` | Каноническая repository identity |
| `PullRequest` | Связь с фактической разработкой |
| `Task` | Связь с GitHub/Jira work items |

Текущий `Repository` содержит:

- `workspace_id`;
- `provider`;
- `external_id`;
- `name`;
- `full_name`;
- `default_branch`;
- `visibility`;
- `archived`;
- metadata;
- activity timestamps.

Текущий `Repository` не хранит commit SHA. Поэтому SHA нельзя безусловно
требовать для L0.

### 7.2 Repository inventory

Источник:

```text
app/services/repository_source_inventory.py
```

Использовать:

- workspace-scoped canonical reads;
- приоритет канонических `Repository`;
- fail-closed workspace behavior;
- нормализацию repository identity.

Не использовать как product truth:

- unscoped filesystem snapshot;
- legacy seed;
- local compatibility fallback без workspace identity.

### 7.3 Текущий metadata-аудит

Источник:

```text
app/services/repo_audit.py
```

Можно переиспользовать идеи:

- manifests detection;
- languages;
- CI hints;
- tests hints;
- deployment hints;
- activity buckets;
- owner candidates;
- базовые metadata risks.

Нельзя переносить как канонический RI-контракт:

- filesystem-first architecture;
- `list[str]` evidence;
- статичный legacy catalog;
- guesses об owner/area как подтверждённые факты.

Текущий `repo_audit.py` — L0 compatibility projection.

### 7.4 Evidence

Текущий строгий валидатор:

```text
app/services/action_proposal_service.py
```

Новый RI использует object-shaped `evidence_ref.v1`:

```json
{
  "kind": "repository_file",
  "source": "github",
  "ref": "owner/repo@<sha>:path/file.py:120",
  "url": null
}
```

Если используются:

```text
evidence_ref_id
source_record_id
record_id
```

они обязаны быть UUID.

Legacy-строки:

```text
github_discovery_snapshot:...
```

не должны становиться новым каноническим форматом.

Если service-level validator создаёт неправильную зависимость, его можно
вынести в нейтральный общий contract-модуль, но только с characterization
tests, доказывающими отсутствие изменения текущего ActionProposal behavior.

### 7.5 Durable jobs

Использовать паттерны из:

```text
app/services/github_sync_worker_service.py
```

Нужны:

- PostgreSQL-backed job;
- lease;
- retries;
- resume;
- progress;
- cancellation;
- короткие транзакции;
- failure isolation;
- отсутствие credentials/raw payload в durable cursor.

Повторно использовать `SyncJob` или создать отдельный
`RepositoryAnalysisJob` — durable решение перед RI-006.

### 7.6 Reconciliation

Использовать принцип из:

```text
app/services/source_reconciliation_service.py
```

Главное правило:

> Отсутствие имеет значение только после полного доверенного наблюдения.

Partial, failed или cancelled run не может:

- закрыть finding;
- объявить finding исправленным;
- пометить edge stale;
- удалить факт;
- объявить dependency исчезнувшей.

### 7.7 Human confirmation

Использовать provenance pattern из:

```text
app/db/company_world_models.py
```

```text
confirmed_by_user_id
confirmed_at
```

Analyzer/LLM не имеет права самостоятельно установить:

```text
confirmed
rejected
accepted_risk
false_positive
```

### 7.8 Controlled actions

Существующий repo-audit import — слой действия, но не источник истины.

Правильный поток:

```text
Finding
  -> ActionProposal
  -> human approval
  -> GitHub/Jira write
  -> receipt
  -> последующий audit verification
```

## 8. Что создавать внутри FounderOS

Целевая структура:

```text
app/
├── services/
│   └── repository_intelligence/
│       ├── __init__.py
│       ├── contracts.py
│       ├── taxonomy.py
│       ├── evidence.py
│       ├── fingerprints.py
│       ├── sanitizer.py
│       ├── checkout.py
│       ├── jobs.py
│       ├── persistence.py
│       ├── reconciliation.py
│       ├── relationships.py
│       ├── read_models.py
│       ├── readiness.py
│       └── collectors/
│           ├── manifests.py
│           ├── entrypoints.py
│           ├── dependencies.py
│           ├── interfaces.py
│           ├── deployment.py
│           ├── tests.py
│           └── documentation.py
│
├── db/
│   └── repository_intelligence_models.py
│
└── api/
    └── repository_intelligence.py
```

Scripts:

```text
scripts/
├── repository_intelligence_readiness.py
├── repository_intelligence_worker.py
└── repository_intelligence_portfolio.py
```

Tests:

```text
tests/
├── test_repository_intelligence_contracts.py
├── test_repository_intelligence_checkout.py
├── test_repository_intelligence_collectors.py
├── test_repository_intelligence_relationships.py
├── test_repository_intelligence_persistence.py
├── test_repository_intelligence_reconciliation.py
├── test_repository_intelligence_readiness.py
└── fixtures/
    └── repository_intelligence/
        ├── frontend/
        ├── backend/
        ├── infrastructure/
        └── hostile/
```

Не нужно создавать все файлы сразу. Структура заполняется по тикетам.

## 9. Контракт Repository Intelligence

Контракт разделяется на trusted FounderOS context и untrusted analyzer result.

### 9.1 Trusted FounderOS envelope

Формируется FounderOS:

```text
schema_version
workspace_id
repository_id
repository.provider
repository.external_id
repository.full_name
audit_level
analysis_target
profile
policy_hash
engine_version
```

### 9.2 Analyzer result

Analyzer может вернуть:

```text
purpose
responsibilities
interfaces_provided
dependencies_consumed
deployment_units
ownership_candidates
relationship_candidates
finding_candidates
claims
contradictions
unknowns
limitations
```

Analyzer не выбирает:

- workspace;
- canonical repository ID;
- human confirmation;
- reconciliation result;
- persistence IDs;
- ActionProposal;
- внешнее действие.

Перед сохранением FounderOS повторно проверяет:

- workspace;
- repository identity;
- evidence;
- target SHA;
- allowed enums;
- payload bounds.

## 10. Binding requirements RI-001

### 10.1 Workspace

Trusted envelope содержит:

```text
workspace_id
repository_id
```

Facts, relationships и findings обязаны принадлежать тому же workspace.

Analyzer не задаёт workspace самостоятельно.

### 10.2 Repository identity

Обязательны:

```text
provider
external_id
full_name
```

Одного `owner/repo` недостаточно.

Для v1:

```text
provider = github
```

Другие Git-провайдеры потребуют новой версии контракта или отдельного
расширения канонической модели.

### 10.3 Commit SHA

Для L0:

```text
target_status: unavailable
commit_sha: null
commit_algorithm: null
```

либо:

```text
target_status: exact
commit_algorithm: sha1
commit_sha: <40 lowercase hex>
```

Для L1/L2:

```text
target_status: exact
commit_algorithm: sha1
commit_sha: <40 lowercase hex>
```

Short SHA, non-hex SHA и отсутствующий SHA для L1/L2 отклоняются.

### 10.4 Evidence

Observed/inferred fact, relationship или finding требует evidence.

Пустой `evidence_refs` разрешён только для:

```text
insufficient_evidence
```

RI-001 проверяет структуру.

При persistence дополнительно проверяются:

- тот же workspace;
- тот же repository;
- тот же SHA для L1/L2;
- существующий SourceRecord;
- SourceRecord не tombstoned;
- разрешённые `kind` и `source`;
- отсутствие дубликатов;
- отсутствие secret values.

Для persistent `EvidenceRef` сначала должен существовать реальный
`SourceRecord`.

### 10.5 Confidence

Только конечное число:

```text
0.0 <= confidence <= 1.0
```

Отклонять:

```text
NaN
Infinity
-Infinity
negative values
values above 1
```

### 10.6 Статусы

Analyzer claim:

```text
observed
inferred
insufficient_evidence
```

Human resolution:

```text
pending
confirmed
rejected
```

Для human resolution:

```text
resolved_by_user_id
resolved_at
```

Reconciliation:

```text
current
stale
```

Finding lifecycle:

```text
new
open
resolved
regressed
accepted_risk
false_positive
insufficient_evidence
```

Analyzer не выдаёт human-only и reconciliation-only статусы.

### 10.7 Relationships

Структура:

```text
from_repository
to_repository
relationship_type
confidence
evidence_refs
```

Свободное поле `direction` не используется.

Правила:

- self-edge запрещён;
- cross-workspace edge запрещён;
- unknown type запрещён;
- inverse duplicates запрещены;
- symmetric edges нормализуются;
- unresolved repository остаётся candidate;
- `unknown` не является relationship type.

Рекомендуемые канонические типы:

```text
calls_api_of
imports_package_from
consumes_event_from
deployed_by
uses_image_from
generates_client_for
tests
documents
replaces
forked_from
duplicate_candidate_of
operationally_coupled_with
shares_schema_with
shares_database_with
owns_migrations_for
```

Обратные представления вычисляются при чтении:

```text
calls_api_of          -> provides_api_to
imports_package_from  -> publishes_package_consumed_by
consumes_event_from   -> produces_event_for
deployed_by           -> deploys
```

`part_of_same_product` до Product/Component лучше хранить как
`product_candidate` fact, а не repo-to-repo edge.

### 10.8 Contradictions

Оба evidence-backed claims сохраняются:

```text
claim A + evidence A
claim B + evidence B
contradiction(A, B)
```

Проверять:

- stable claim IDs;
- обе стороны существуют;
- обе стороны имеют evidence;
- no self-contradiction;
- no dangling references;
- no duplicate contradiction pair.

FounderOS не выбирает победителя автоматически.

### 10.9 Bounds

Использовать:

```python
ConfigDict(extra="forbid")
```

Нужны:

- closed enums;
- string length limits;
- item count limits;
- total serialized byte limit;
- запрет secret-like fields;
- rejection unsupported fields.

Лимит RI payload фиксируется отдельно. Нельзя без обоснования копировать
ActionProposal limit на весь RI result.

## 11. Tests RI-001

Обязательные tests:

- valid L0;
- valid L1/L2;
- unknown field;
- missing workspace;
- malformed UUID;
- incomplete repository identity;
- L0 с `commit_sha=null`;
- L1/L2 без SHA;
- malformed SHA;
- invalid evidence object;
- factual claim without evidence;
- `insufficient_evidence` without evidence;
- NaN/Infinity/out-of-range confidence;
- unknown status;
- analyzer uses human-only status;
- analyzer uses stale;
- self-edge;
- cross-workspace edge;
- unknown relationship type;
- inverse duplicate;
- symmetric normalization;
- unresolved repository remains candidate;
- two contradictory claims are preserved;
- dangling contradiction;
- self-contradiction;
- item/byte limits;
- secret-like fields are rejected.

RI-001 обязательно обновляет:

```text
docs/DECISIONS.md
PROGRESS.md
docs/TODO.md
docs/CHANGELOG.md
```

`docs/README.md` обновляется, только если добавляется/удаляется/переименовывается
документ.

## 12. Этапы подготовки

### RI-001 — Contracts and fixtures

Статус: **завершён 2026-07-30** (DEC-115).

Реализовано:

- versioned contracts;
- trusted envelope;
- analyzer result;
- enums;
- evidence rules;
- SHA rules;
- relationships;
- contradictions;
- bounds;
- synthetic valid/invalid fixtures;
- contract tests;
- decision entry.

Проверено на synthetic frontend L0, backend L1, infrastructure L2,
contradiction и invalid fixtures. Не создано:

- migrations;
- persistence;
- UI;
- checkout;
- provider integrations.

### RI-002 — Canonical synthetic L0

Статус: **завершён 2026-07-30** (DEC-116).

Реализован read-only L0 projection на:

- synthetic `Repository`;
- synthetic `SourceRecord`;
- dedicated test DB.

Он не читает реальные connected repositories, filesystem discovery,
SourceEvent/legacy catalog и provider API.

### RI-003 — Safe checkout manager

Создать:

- отдельный runtime data setting;
- запрет checkout внутри FounderOS;
- exact-SHA checkout;
- path validation;
- timeout;
- disk/output limits;
- cleanup на success/failure/cancel;
- synthetic checkout tests.

Текущий `founderos_local_workspace_path` по умолчанию указывает на `.local/`
внутри FounderOS и не подходит для untrusted checkout.

Предлагаемое имя новой настройки:

```text
FOUNDEROS_REPOSITORY_INTELLIGENCE_DATA_PATH
```

Окончательное имя фиксируется в `docs/DECISIONS.md`.

Реальный `.env.local` агент не меняет.

### RI-004 — Static collectors

Только synthetic fixtures:

- frontend;
- backend;
- infrastructure;
- hostile/pathological structures.

Collectors:

- manifests;
- entrypoints;
- dependencies;
- APIs/interfaces;
- events/queues;
- schemas;
- deployment;
- tests/CI;
- documentation;
- migrations/data ownership.

Fixture code не выполнять.

### RI-005 — Relationship candidates

Создать:

- directed edges;
- inverse rules;
- symmetric normalization;
- unresolved targets;
- cycle detection;
- orphan detection;
- graph validation;
- contradiction fixtures.

### RI-006 — Persistence and migrations

Требует отдельного подтверждения, ветки/PR workflow и reviewed migration.

Создать:

- DB models;
- Alembic migration;
- jobs;
- runs;
- facts;
- relationships;
- findings;
- evidence integration;
- contradictions;
- idempotency;
- reconciliation;
- workspace isolation;
- retention/deletion contract.

Только test database и synthetic data.

### RI-007 — Read models and UI

Создать:

- Repository Portfolio;
- Repository Detail;
- directional graph;
- evidence drawer;
- unknown/confirmation queue;
- audit history;
- freshness;
- filters.

Пока только synthetic data.

### RI-008 — Cross-source intelligence

На synthetic GitHub/Jira/document fixtures:

- links to work items;
- bounded contradictions;
- briefing signals;
- `Спросить`;
- unsupported-claim rejection.

Без provider API.

### RI-009 — L2 isolation

Варианты:

1. доказать isolation на hostile synthetic fixtures;
2. зафиксировать:

```text
L2 disabled for first portfolio run
```

Для первого реального запуска рекомендуется оставить L2 выключенным.

## 13. Persistence entities

### `RepositoryAnalysisJob`

```text
queued
running
completed
partially_completed
failed
cancelled
```

### `RepositoryAuditRun`

```text
workspace_id
repository_id
source_record_id
audit_level
commit_sha
metadata_snapshot_id
profile
policy_hash
engine_version
coverage
limitations
started_at
completed_at
status
```

### `RepositoryFact`

```text
fact_type
value
claim_status
confidence
first_seen_run_id
last_seen_run_id
evidence_refs
contradicting_evidence_refs
human resolution provenance
```

### `RepositoryRelationship`

```text
from_repository_id
to_repository_id
relationship_type
confidence
first_seen_run_id
last_seen_run_id
evidence
human resolution
reconciliation state
```

### `RepositoryAuditFinding`

```text
fingerprint
rule_id
category
severity
confidence
status
title
summary
first_seen_run_id
last_seen_run_id
resolved_at
recommended_next_step
evidence
```

### Contradiction persistence

До RI-006 выбрать:

- отдельную `RepositoryContradiction`;
- либо versioned links между facts.

## 14. Raw storage recommendation

Рекомендуемый default:

1. один санитизированный internal `SourceRecord` на audit run;
2. большие artifacts в approved raw storage;
3. PostgreSQL хранит:
   - run metadata;
   - facts;
   - relationships;
   - findings;
   - fingerprints;
   - evidence links;
   - reconciliation status;
4. PostgreSQL не хранит:
   - полный checkout;
   - большие scanner dumps;
   - dependency caches;
   - полный private source;
   - secret matches.

Решение фиксируется до RI-006.

## 15. Repository Intelligence Prepared

Статус `prepared` разрешён только если:

- implementation plan committed;
- durable decisions committed;
- contracts versioned;
- synthetic L0/L1 проходят;
- migrations проходят на test DB;
- jobs/retry/resume/cancel проверены;
- failure одного repo не ломает остальные jobs;
- workspace isolation проверена;
- evidence validation проверена;
- graph aggregation работает;
- findings reconciliation работает;
- checkout cleanup доказан;
- hostile synthetic isolation доказан или L2 выключен;
- dry-run import детерминирован;
- UI/read models работают на synthetic data;
- portfolio manifest schema готова;
- per-repository prompt готов;
- restart/recovery runbook готов;
- retention/deletion contract готов;
- synthetic portfolio из 20+ entries проходит;
- secret scans зелёные;
- Ruff зелёный;
- guarded backend-check зелёный;
- migration checks зелёные;
- frontend checks зелёные для UI-stage;
- sanitized readiness receipt подтверждает нулевой доступ к company
  repositories.

Если хотя бы один пункт отсутствует:

```text
status = preparing
```

## 16. Readiness receipt

Пример:

```json
{
  "schema_version": "repository-intelligence-readiness.v1",
  "status": "prepared",
  "company_repositories_read": 0,
  "company_repositories_cloned": 0,
  "company_repository_code_executed": 0,
  "provider_content_calls": 0,
  "external_tasks_created": 0,
  "l2_enabled_for_first_portfolio_run": false
}
```

Receipt не содержит:

- DB URL;
- credentials;
- provider payload;
- source bodies;
- secret values;
- чувствительные local paths.

## 17. Перед первым реальным запуском

После readiness требуется отдельное подтверждение человека.

Перед запуском:

1. просмотреть local commits;
2. при необходимости согласовать PR/merge;
3. применить migrations только после backup и approval;
4. настроить runtime data path;
5. создать private portfolio manifest;
6. оставить L2 выключенным, если нет отдельного разрешения;
7. подтвердить список репозиториев и разрешённые audit levels.

## 18. Portfolio manifest

Пример:

```json
{
  "schema_version": "repository-portfolio.v1",
  "workspace_id": "<uuid>",
  "repositories": [
    {
      "repository_id": "<canonical-uuid>",
      "provider": "github",
      "external_id": "<stable-provider-id>",
      "full_name": "owner/repo",
      "local_path": "/path/to/repository",
      "audit_levels": ["L0", "L1"],
      "enabled": true
    }
  ]
}
```

Manifest:

- не содержит credentials;
- не коммитится в target repositories;
- подтверждается человеком;
- хранится в private central workspace;
- использует stable provider identity;
- не превращает unresolved repository в canonical record.

## 19. Что читать в каждом репозитории после readiness

### Identity

- provider ID;
- owner/name;
- default branch;
- exact SHA;
- visibility;
- archived/fork/template;
- timestamps.

### Purpose

- description;
- README;
- topics;
- manifests;
- entrypoints;
- package metadata;
- API schemas;
- CI;
- deployment definitions;
- directory structure.

README — evidence, но не безусловная истина.

### Responsibilities

- business capabilities;
- user-facing surfaces;
- workers;
- data processing;
- libraries;
- integrations;
- authentication;
- infrastructure;
- observability;
- scheduled jobs;
- migrations/data ownership.

### Interfaces provided

- HTTP/REST/GraphQL/gRPC/WebSocket;
- packages;
- CLI;
- events;
- queues/topics;
- schemas;
- webhooks;
- container images;
- storage formats;
- Terraform/Helm modules.

### Dependencies consumed

- internal packages;
- external packages;
- APIs;
- queues/topics;
- databases;
- storage;
- images;
- generated clients;
- shared schemas.

### Ownership candidates

- CODEOWNERS;
- maintainers;
- reviews;
- package owners;
- Jira components;
- linked documents.

Автоматически найденный owner остаётся candidate до human confirmation.

### Quality and risk

- tests;
- CI;
- lint/typecheck;
- dependency locks;
- vulnerability signals;
- deployment safety;
- migrations;
- health/readiness;
- observability;
- stale code;
- missing/outdated documentation;
- secret finding locations без secret values.

## 20. Что никогда не собирать

- `.env` contents;
- tokens;
- API keys;
- credentials;
- secret matches;
- raw provider payloads;
- полные email/document bodies;
- полный checkout в отчёте;
- весь source tree в PostgreSQL;
- dependency/build caches;
- unbounded logs.

Для secret finding сохраняются только:

```text
sanitized path
line или symbol
scanner rule
severity
evidence reference
```

Matched secret value не сохраняется и не выводится.

## 21. Запуск агента в каждом репозитории

Только после readiness и отдельного подтверждения.

Каждый агент:

1. читает локальный `AGENTS.md`;
2. проверяет `git status --short`;
3. работает read-only;
4. выполняет L0/L1;
5. не запускает repository code;
6. не делает commit;
7. не создаёт отчёт внутри target repository;
8. пишет output в central audit workspace;
9. возвращает JSON, report, limitations и relationship candidates.

Промпт:

```text
Goal: Run the approved read-only FounderOS Repository Intelligence L0/L1 analysis for this repository.
Context: Use repository_intelligence.v1 and the approved portfolio manifest entry.
Constraints: Read-only; do not modify or commit; do not execute repository code; do not read secret values; write output only to the central audit workspace; every observed or inferred claim requires evidence.
Done when: Schema-valid JSON, sanitized report, limitations, unknowns, and relationship candidates are produced for the exact repository identity and SHA.
```

Если sandbox не разрешает запись в central workspace:

- добавить central workspace как отдельный writable root;
- либо вернуть artifact центральному coordinator.

Нельзя писать report в target repository как обходной путь.

## 22. Структура результатов

```text
founderos-ri-data/
└── runs/
    └── <workspace-id>/
        └── <repository-external-id>/
            └── <run-id>/
                ├── repository_intelligence.v1.json
                ├── report.md
                ├── artifact-manifest.json
                └── receipt.json
```

`run-id` учитывает:

```text
workspace
repository
SHA или metadata snapshot
audit level
profile
policy hash
engine version
```

Одного SHA для run identity недостаточно.

## 23. Central reconciliation

После всех per-repository runs FounderOS:

1. валидирует contract;
2. проверяет workspace;
3. разрешает repository identities;
4. проверяет evidence;
5. импортирует runs;
6. сопоставляет relationship candidates;
7. нормализует inverse edges;
8. удаляет duplicates;
9. сохраняет unresolved targets отдельно;
10. строит directional graph;
11. ищет:
    - orphan repositories;
    - cycles;
    - shared database coupling;
    - archived dependencies;
    - duplicate capabilities;
    - conflicting schemas;
    - ownerless critical repositories;
    - stale dependencies;
    - code/docs/Jira contradictions;
12. просит человека подтвердить:
    - owners;
    - products/components;
    - inferred edges;
    - accepted risks.

Per-repository agent создаёт candidates. Полная карта появляется только после
центрального прохода по всем одобренным репозиториям.

## 24. Проверки каждого тикета

Перед commit:

```bash
git diff --check
git diff --cached --name-only
bash scripts/check_no_secrets.sh --staged
make secret-scan
uv run ruff check .
```

Backend gate:

```bash
APP_ENV=test \
FOUNDEROS_TEST_DATABASE_URL=<dedicated-test-marked-postgres-url> \
make backend-check
```

Bare `pytest` запрещён.

Для migrations:

```text
upgrade
downgrade
upgrade again
alembic check
same-workspace tests
cross-workspace denial tests
```

Для frontend:

```bash
cd web
npm test
npm run typecheck
npm run lint
npm run build
```

Если PostgreSQL недоступен, DB-backed gate честно отмечается как blocked.

## 25. Решения до RI-006

Обязательно зафиксировать:

1. один SourceRecord на run или manifest + raw artifacts;
2. новая job table или reuse `SyncJob`;
3. точное имя runtime data setting;
4. artifact storage;
5. retention для checkout/logs/artifacts/facts/findings;
6. связь `EvidenceRef` с RI facts;
7. contradiction table или fact links;
8. complete coverage criteria;
9. Product/Component сейчас или после первого portfolio run;
10. L2 network policy.

Рекомендуемые defaults:

- один sanitized `SourceRecord` на run;
- отдельный `RepositoryAnalysisJob` с reuse worker patterns;
- checkout удаляется сразу;
- network выключен;
- L2 выключен для первого portfolio run;
- большие artifacts хранятся в raw storage;
- Product/Component пока является confirmed candidate relation.

## 26. Готовый промпт следующему агенту

```text
Goal: Implement RI-003 — safe Repository Intelligence checkout manager.

Context: Work only in the separate company-knowledge-os-ri-prep worktree. Read AGENTS.md, CLAUDE.md, docs/README.md, docs/REPOSITORY_INTELLIGENCE_IMPLEMENTATION_PLAN.md, and docs/REPOSITORY_INTELLIGENCE_FULL_GUIDE_RU.md. The hard gate prohibits reading, cloning, or executing any company repository during preparation.

Constraints:
- Only RI-003.
- Use only synthetic repository fixtures.
- Add a dedicated runtime data path outside the FounderOS repository tree.
- Materialize only an exact approved SHA.
- Do not execute target repository commands or expose FounderOS credentials.
- Bound path, time, disk and output and clean up on every exit.
- No migration, persistence model, UI, portfolio provider read or LLM call.
- Do not touch .env.local, .local, credentials, company data or existing connections.
- Update PROGRESS.md, docs/TODO.md, and docs/CHANGELOG.md.
- Nothing may be pushed.

Done when:
- Synthetic path, exact-SHA, cleanup, timeout and failure tests pass.
- Checkout cannot resolve inside the FounderOS repository tree.
- No fixture code is executed.
- git diff --check passes.
- Staged and tracked secret scans pass.
- uv run ruff check . passes.
- Guarded make backend-check passes against an explicit test-marked PostgreSQL URL, or DB-backed checks are honestly reported blocked.
- A scoped local RI-003 commit is created.
- Report the result and wait for approval before RI-004.
```

## 27. Краткий финальный checklist

### Сейчас

- [x] проверить Git state и approved base;
- [x] создать `company-knowledge-os-ri-prep`;
- [x] сохранить RI handoff docs;
- [x] реализовать RI-001 только на synthetic fixtures;
- [x] зафиксировать DEC-115;
- [x] реализовать RI-002 только на synthetic canonical rows;
- [x] зафиксировать DEC-116;
- [ ] начать RI-003 только после отдельного approval.

### Во время подготовки

- [ ] только synthetic fixtures;
- [ ] zero company repository reads;
- [ ] один тикет за раз;
- [ ] focused tests;
- [ ] Ruff;
- [ ] guarded backend-check;
- [ ] secret scans;
- [ ] local commits;
- [ ] никакого push.

### Перед реальным portfolio run

- [ ] milestone `Repository Intelligence Prepared`;
- [ ] readiness receipt;
- [ ] approved portfolio manifest;
- [ ] migrations/backup approved;
- [ ] L2 disabled или отдельно approved;
- [ ] human instruction на запуск.

### Реальный запуск

- [ ] read-only L0/L1;
- [ ] no target repo modifications;
- [ ] no commits;
- [ ] central results;
- [ ] schema/evidence validation;
- [ ] portfolio reconciliation;
- [ ] human confirmations;
- [ ] ActionProposal только после выбора человека.

## 28. Итог

Создаются две отдельные папки:

```text
company-knowledge-os-ri-prep/
  Git worktree для подготовки системы

founderos-ri-data/
  private runtime/staging workspace, не Git
```

Repository Intelligence полностью подготавливается на synthetic data, но по
одному проверяемому тикету.

После milestone `Repository Intelligence Prepared` и отдельного подтверждения
запускается read-only L0/L1 по всем 20+ репозиториям.

FounderOS затем:

- импортирует только schema-valid/evidence-valid результаты;
- строит общую directional repository graph;
- показывает назначение каждого репозитория;
- находит risks, contradictions, duplicates и orphan repositories;
- связывает информацию с GitHub, Jira, документами и людьми;
- предлагает действия только через human-approved workflow.
