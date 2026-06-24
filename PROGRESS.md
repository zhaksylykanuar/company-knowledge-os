# founderOS — PROGRESS (live state / single source of truth)

> Это **живой файл состояния**. Его обновляет агент (Claude Code / Codex) после КАЖДОЙ задачи.
> Человек смотрит сюда, чтобы за 5 секунд понять: **где мы и что дальше.**
> Текущая ветка `main`; cleanup/FOS-008/doc hygiene fast-forward merged locally
> into `main` at `ef22360`. Remote publish is still pending (`main` ahead
> `origin/main` by 43 commits) until a human explicitly asks to push.

---

## ▶ СЕЙЧАС

- **Chunk:** `CHUNK 1 — Data Foundation` ✅ закрыт (gate зелёный). Следующая реальная работа спайна — CHUNK 3.
- **Task:** CHUNK 3 / FOS-009 — сократить retained-substrate tail после того, как FOS-008 начал писать GitHub repositories в канонические `source_records`/`repositories`.
- **State:** ✅ FOS-002 (spine-subset §6) готов: добавлены `source_records`, `evidence_refs`, `repositories`, `pull_requests`, `tasks` (uuid, workspace-scoped) — DEC-028, ветка A. `NormalizedEntity` отложен (нет GitHub-only читателя обобщённой сущности). Линия 2 (entities-граф+source_events+frozen) — frozen legacy.
- **Next action:** CHUNK 3 / FOS-009: оставить `source_events`/`normalized_activity_items`/`ingested_events` нетронутыми до отдельного retirement/repointing шага; issues/PR persistence тоже не входит в FOS-008.

---

## 📊 ПРОГРЕСС

```
Tasks:  5 / 23   ▰▰▰▰▰▱▱▱▱▱▱▱▱▱▱▱▱▱▱▱▱▱▱   22%   (строго DONE)
Chunks: 2 / 9
```

Разбивка: **DONE = 5** · **PARTIAL = 15** · **MISSING = 3**.
FOS-002 закрыт по DEC-028 (spine-subset §6: SourceRecord/EvidenceRef/Repository/PullRequest/Task; остальные §6-модели отложены по чанкам — не «не сделано», а scoped-out).
DONE строго = есть код + проходящий тест/рабочий эндпоинт под acceptance criteria.
Для сравнения: `docs/TODO.md` помечает «done» ~15 задач **собственной** схемы (FOS-DB/GH/BRF/ACT/E2E/FE), что создаёт впечатление почти готового backend MVP; против playbook-схемы FOS-000..022 строго готово 5.

**Легенда статусов задачи:** `[ ]` todo · `[~]` in progress/partial · `[x]` done · `[!]` blocked

---

## 🚦 GATE HEALTH (результат последней проверки — 2026-06-24)

| Gate | Status | Last checked | Evidence |
|---|---|---|---|
| `alembic upgrade head` | ✅ pass | 2026-06-24 | post-merge on `main`: one head `e1a2b3c4d5f6`, current==head |
| **Lineage-2 purge** (DEC-029) | ✅ done | 2026-06-24 | ~139 модулей + 27 таблиц + ~150 тестов + 55 скриптов + non-canon доки удалены; leftover static UI artifact/test removed by FOS-PURGE-01; tag `pre-purge-20260624` |
| **CHUNK 1 gate** (model tests + encryption roundtrip) | ✅ pass | 2026-06-24 | `tests/test_canonical_models.py` (9) + `test_integration_models.py` + encryption roundtrip — зелёные |
| backend tests (`pytest`) | ✅ pass | 2026-06-24 | post-merge on `main`: **259 passed / 0 failed / 1 warning** |
| `ruff` | ✅ pass | 2026-06-24 | `All checks passed!` (ruff 0.15.16) |
| API namespace `/api/v1` (DEC-023) | ✅ done | 2026-06-24 | 660 `/v1`→`/api/v1`; нет stray `/v1` |
| frontend build | ✅ pass | 2026-06-24 | post-merge on `main`: `typecheck`, `lint`, `next build` ok (7 routes) |
| docs navigation | ✅ pass | 2026-06-24 | `tests/test_docs_navigation_integrity.py` 2 passed |
| `alembic check` (retained substrate) | ⚠️ expected drift | 2026-06-24 | drift **7 operations**, all on `ingested_events`; retained-substrate, retire/fix in FOS-009 / DEC-030; НЕ про канон |
| **GitHub E2E (spine)** | ⚠️ backend smoke pass | 2026-06-24 | `test_github_first_backend_e2e` зелёный (спайн цел), но `is_live=false`; нет product UI-flow; страниц `/connectors`,`/brain` нет |
| **full main E2E** | ❌ fail | 2026-06-24 | «approved action → реальный GitHub issue» не доказан (issue-client замокан) |
| prod smoke | ❓ unknown | — | деплой не выполнялся; Makefile/`make smoke` отсутствует |

Статусы: ✅ pass · ❌ fail · ❓ unknown

---

## ✅ CHUNKS

### CHUNK 0 — Audit & Docs ✅
*Gate: PROGRESS.md заполнен реальным состоянием; `docs/` создан.*
- [x] FOS-000 — Repository baseline audit — этот аудит, код не менялся; PROGRESS/DECISIONS/_audit обновлены
- [x] FOS-001 — Project docs — `docs/{DECISIONS,ROADMAP,TODO,POST_MVP,CHANGELOG}.md` существуют (⚠ 4 doc-contract теста красные — см. BLOCKERS)

### CHUNK 1 — Data Foundation ✅
*Gate: `alembic upgrade head` ✅ · model tests ✅ · encryption roundtrip test ✅.*
- [x] FOS-002 — Core DB models (spine-subset §6, DEC-028) — `app/db/canonical_models.py`: `SourceRecord`/`EvidenceRef`/`Repository`/`PullRequest`/`Task` (uuid, workspace-scoped) + миграция `f6b7c8d9e0a1` + `tests/test_canonical_models.py` (9 зелёных). `NormalizedEntity`/`Project`/`Briefing`/… отложены по чанкам; `Person` post-MVP.
- [x] FOS-003 — Encryption utility — `app/services/secret_encryption.py` (Fernet `encrypt_secret`/`decrypt_secret`); roundtrip доказан в `tests/test_github_provider_token_connection.py` (plaintext/`fernet:v1:` не утекают)

### CHUNK 2 — Connector Framework — ОТЛОЖЕН по DEC-028
*Не строим generic-абстракцию вперёд; выделим при 2-м коннекторе (Jira/Gmail). Общая §6-подложка делает это дёшево потом.*
- [ ] FOS-004 — Base connector interface — отложено (DEC-028): no speculative framework
- [ ] FOS-005 — Sync service — отложено (DEC-028); канонический `SourceRecord` теперь существует для будущего generic sync
- [ ] FOS-006 — Normalization service (+EvidenceRef) — отложено (DEC-028); `SourceRecord`/`EvidenceRef` существуют, `NormalizedEntity` deferred до FOS-012

### CHUNK 3 — GitHub E2E (SPINE) 🎯 критический milestone
*Gate: пользователь подключает GitHub через UI → sync → данные в Dashboard и Brain.*
- [~] FOS-007 — GitHub OAuth — нет OAuth start/callback (§7.5); соединение через PAT-bridge, токен шифруется. `tests/test_github_provider_token_connection.py` зелёный
- [x] FOS-008 — GitHub sync repositories — `normalize-local` при `persist_if_supported=true` пишет canonical `source_records`/`repositories` idempotent-upsert; `persist_if_supported=false` остаётся projection-only. Доказано `tests/test_github_normalization_api.py` + `tests/test_github_first_backend_e2e.py`
- [~] FOS-009 — GitHub sync issues + PRs — PR-проекция есть; issues возвращаются пустыми с warning (`github_normalization_service.py:26-27`)
- [ ] FOS-010 — Connectors UI page — нет `web/app/connectors/page.tsx`; есть только stub `web/app/github/page.tsx` (41 строка)
- [~] FOS-011 — Dashboard v0 — backend `app/services/founder_overview.py`; `web/app/dashboard/page.tsx` — stub (62 строки), не подключён к live-данным
- [~] FOS-012 — Brain entity API + UI — API `app/api/company_brain.py` (`/api/v1/founder/company-brain`); страницы `web/app/brain` нет

### CHUNK 4 — Briefing MVP
*Gate: пользователь генерирует briefing с evidence drawer.*
- [~] FOS-013 — Briefing backend — `app/services/founder_briefing_service.py` детерминированный, transient (`BRIEFING_PERSISTENCE_TRANSIENT`), без LLM и без таблиц Briefing/BriefingItem. `tests/test_founder_briefing_api.py` зелёный
- [ ] FOS-014 — Briefing UI + evidence drawer — `web/app/briefings/page.tsx` — stub (23 строки), drawer нет

### CHUNK 5 — Action Approval 🎯 full main E2E
*Gate: approved action создаёт реальный GitHub issue.*
- [~] FOS-015 — Action proposal API — `app/api/actions.py` (create/list/get/approve/reject/execute) + модели ActionProposal/ActionExecution + миграция `f5a6b7c8d9e0`. `tests/test_action_proposals_api.py` зелёный. Нет async-worker/enqueue (исполнение inline)
- [~] FOS-016 — GitHub create-issue action — `app/services/github_issue_execution_service.py` + `github_issue_client.py`; `tests/test_github_issue_execution_api.py` зелёный, но GitHub-клиент замокан (нет реального external write)

### CHUNK 6 — Remaining Connectors
*Gate: Jira / Gmail / Drive / Documents видны в Brain.*
- [~] FOS-017 — Jira connector minimal — `app/connectors/jira.py` + `jira_discovery`/`jira_graph_mapping`; нет `web/app/jira`, не в каноническом Brain
- [~] FOS-018 — Gmail connector minimal — `app/connectors/gmail.py` + gmail-модели + `app/api/gmail.py`; нет `web/app/gmail`
- [~] FOS-019 — Drive connector minimal — `app/connectors/google_drive.py` + `app/api/drive.py`; нет `web/app/drive`
- [~] FOS-020 — Documents module — есть `source_documents` (RAG-ingestion), но нет канонического Document CRUD (`body_markdown`, §7.11) и `web/app/documents`

### CHUNK 7 — Polish + Repo Audit UI
*Gate: нет dead-end состояний; repo audit виден в UI.*
- [~] FOS-021 — Repo Audit UI — backend `app/services/repo_audit.py` есть; страницы `web/app/repo-audit` нет
- [ ] FOS-P — Polish (errors/retries/empty/filters/evidence UX) — UI на уровне scaffold, не сделано

### CHUNK 8 — Testing Gate + Deploy
*Gate: launch gate зелёный; production URL работает; первый E2E в проде.*
- [~] FOS-022 — Smoke tests — backend `tests/test_github_first_backend_e2e.py` + `tests/test_external_connector_readonly_smoke.py` зелёные; нет `make smoke`/Makefile и full-stack/prod smoke
- [~] FOS-T — Full tests + frontend build — pytest 259/0 (чекап 2026-06-24); web build ✅
- [ ] FOS-D — Deploy (Railway) — не выполнялся

---

## ⛔ BLOCKERS

- ~~[CHUNK 0] 4 doc-contract теста красные~~ — **РЕШЕНО (ШАГ A, 2026-06-24).** Починено doc-side (тесты не ослаблялись): вернул CI-секцию в README, lean `docs/playbook.md`, восстановил `docs/ops/jira-target-blueprint.md`, прилинковал guarded-operations, убрал legacy static-UI путь. pytest 1809/0. Коммит `394df7b`.

- ~~[CHUNK 1] Фундамент «вбок» — ОЖИДАЕТ РЕШЕНИЯ A/B~~ — **РЕШЕНО (DEC-028):** ветка A — §6 расширяет спайн (spine-subset готов, FOS-002), knowledge-graph lineage → frozen legacy и удалён (DEC-029). source_events удержан до FOS-009 (DEC-030).

- [SPINE] **GitHub E2E не закрыт по-настоящему.** Backend-smoke зелёный, но `is_live=false`, UI — scaffold. Рефакторинг по §21.4 ещё **запрещён** (gate CHUNK 3 не пройден).

---

## 🧾 SESSION LOG (append-only, новое — сверху)

- `2026-06-24` — **Post-merge main order check + docs alignment.** `feat/platform-part2-computed-repo-brain` fast-forward merged into local `main` (`ef22360`); worktree clean; `main` ahead `origin/main` by 43 commits, push intentionally not done without explicit human command. Rechecked gates on `main`: docs navigation ✅, local markdown links ✅, `ruff` ✅, `pytest 259/0` ✅, web `typecheck/lint/build` ✅, `alembic head/current/upgrade` ✅, `alembic check` expected drift **7 ops on `ingested_events`**. Docs-control cleanup completed in canonical set only: PLAYBOOK(what)+PROGRESS(where)+DECISIONS(why), plus ROADMAP/TODO/POST_MVP/CHANGELOG as planning layer.
- `2026-06-24` — **Read-only чекап + doc-гигиена (новая сессия).** Ветка `feat/platform-part2` (purge влит, 40 ahead of main / 0 behind), app/ 39 модулей, `canonical_models` + `/api/v1` на месте. Гейт перепрогнан на дереве с FOS-008: alembic head чист, ruff ✅, **pytest 259/0**, drift 6 (`ingested_events`), github-first E2E зелёный → FOS-008 закоммичен (`fc6b55d`). Установлено правило гигиены доков (DEC-031); `EXECUTION_PLAN.md` свёрнут (дубль chunk-map + неиспользуемые driver-промпты, частично устарел vs DEC-028). Канон управления = PLAYBOOK(что)+PROGRESS(где)+DECISIONS(почему). Аномалий нет; substrate `source_events` удержан до FOS-009.
- `2026-06-24` — **FOS-008 canonical GitHub repository persistence.** `POST /api/v1/workspaces/{workspace_id}/github/sync-jobs/{sync_job_id}/normalize-local` сохраняет projection-only режим при `persist_if_supported=false`, а при `true` пишет GitHub repositories в canonical `SourceRecord`/`Repository` с idempotent upsert, sanitized payload, SyncJob counters/logs. `EvidenceRef`/issues/PRs не пишутся; retained substrate не тронут.
- `2026-06-24` — **FOS-PURGE-01 final purge consistency cleanup.** Удалены leftover static UI HTML artifact и dedicated static UI test; local starter теперь открывает backend root, не `/ui`. Удержанный substrate `source_events`/`normalized_activity_items`/`ingested_events` остаётся до FOS-009. Актуальный `alembic check` drift: 7 operations, all on `ingested_events`; не чинить в этой задаче. Runtime namespace остаётся `/api/v1`.
- `2026-06-24` — **Lineage-2 retired (purge, DEC-029).** Удалены entities-граф + identity-слой + knowledge-graph/RAG + digest/inbox/telegram/gmail/drive/extraction/share-packs/second-opinion/attention/jira/obsidian/source-control + legacy-коннекторы (`connectors.github`, `source_control`) + статичный `/ui` + их тесты/скрипты + non-canon доки. Дропнуто 27 таблиц (миграция `e1a2b3c4d5f6`, необратима). Удержан substrate `source_events`/`normalized_activity_items`/`ingested_events` (DEC-030, retire в FOS-009). Гейт: app boots, alembic head чист, drift now 7 operations on `ingested_events`, ruff ✅, pytest green, web build ✅, github-first E2E зелёный (спайн цел). Recovery tag `pre-purge-20260624`. Коммиты: eadd7d8 (код), 1d281e3 (таблицы), e83e5d2 (доки).
- `2026-06-24` — **FOS-002 готов (spine-subset §6, ветка A / DEC-028).** Добавлены канонические `source_records`/`evidence_refs`/`repositories`/`pull_requests`/`tasks` (`app/db/canonical_models.py`, uuid+workspace-scoped) + миграция `f6b7c8d9e0a1` + `tests/test_canonical_models.py` (9). `NormalizedEntity` отложен (решено по коду: нет GitHub-only читателя обобщённой сущности). CHUNK 1 gate зелёный: alembic upgrade head ✅, model tests ✅, encryption roundtrip ✅. pytest 1818/0, ruff ✅. `alembic check` ругается на pre-existing legacy drift (Линия 2), не на канон-таблицы. DONE 5/23, chunks 2/9.
- `2026-06-24` — **FOS-002 диагностика (read-only): две параллельные линии.** Спайн (github sync/normalize/action/briefing/brain) НЕ читает/пишет `entities`-граф и `source_events` — идёт мимо, на `integration_models`+`action_models`+проекциях. Граф+identity-слой+`source_events` нагружают ТОЛЬКО старую Graphiti/knowledge-graph генерацию + frozen founder-views/digest/inbox (DEC-026). Карта «что чем нагружено» — `docs/_audit/DOCS_AUDIT.md` → «Load-Bearing Map». Случай «две генерации» → СТОП, вопрос человеку (ветка A: §6 расширяет спайн, граф→legacy / ветка B). Схема не менялась.
- `2026-06-24` — **FOS-002 ШАГ A+B + namespace.** ШАГ A: 4 doc-contract теста починены doc-side → pytest 1809/0 (`394df7b`). Namespace `/v1`→`/api/v1` (DEC-023) выполнен: 660 замен в 65 файлах, ruff/pytest/tsc зелёные (`fix(api)` коммит). ШАГ B (shape-equivalence) gate: `source_events`/`entities` **НЕ эквивалентны** §6 по форме → СТОП перед rename, finding в DECISIONS/DOCS_AUDIT (`d757835`). Канонизация данных ждёт решения A/B (диагностика «что чем нагружено» → ветка). Код-модель пока не менялась.
- `2026-06-24` — **Audit (Prompt A) выполнен.** Сверено с реальным кодом: строго DONE 4/23 (FOS-000/001/003/008), PARTIAL 16, MISSING 3. Gate: alembic ✅, ruff ✅, frontend build ✅, pytest 1805✅/4❌ (doc-contract), GitHub-E2E ❌ (mocked/`is_live=false`), prod ❓. Дрейф зафиксирован в DECISIONS.md (DEC-023..026) и `docs/_audit/DOCS_AUDIT.md`. Канонический namespace = `/api/v1` (код везде `/v1`), канон. имя = `SourceRecord` (код — `source_events`/`entities`), продуктовый фронт = Next.js `web/` (`/ui` — legacy). ASK-1 (23-я модель / Person), ASK-2 (rename vs add-alongside) — человеку.
- `INIT` — template создан, состояние не проверено. Запусти Prompt A.
