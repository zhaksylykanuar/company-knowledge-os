# founderOS — PROGRESS (live state / single source of truth)

> Это **живой файл состояния**. Его обновляет агент (Claude Code / Codex) после КАЖДОЙ задачи.
> Человек смотрит сюда, чтобы за 5 секунд понять: **где мы и что дальше.**
> Текущая ветка `main`. Локальные коммиты не пушить без явного запроса
> человека.

---

## ▶ СЕЙЧАС

- **Chunk:** первая продуктовая фича за логином — **Briefings**. Chunk 1
  (персистентность) **сделан**; `CHUNK 8` hardening закрыт ранее. Repository
  identity/race debt перед live sync **закрыт** (DEC-050). GitHub App
  product-connect foundation **сделан** (DEC-052). GitHub App polling-only live
  read sync backend foundation **сделан** (DEC-053). `/github` product UI для
  explicit single-repo read-only sync **сделан**. Следующий лучший продуктовый
  шаг — synced evidence/briefing isolation verification и первый real-provider
  read run только после отдельного human approval.
- **GitHub App live read sync backend/UI foundation (НОВОЕ):** DEC-053 фиксирует
  polling-only v0 (webhooks deferred до raw-body signature verification +
  delivery dedupe). Добавлены JIT installation token minting, read-only
  installation repository client, endpoint
  `POST .../github/connections/app-installation/sync`, explicit repository
  scope, issues/PRs provider reads into existing canonical
  normalization/upsert path, and `/github` explicit repo sync control.
  Installation access token не сохраняется, provider writes не выполняются,
  tests/mock UI keep provider calls mocked.
- **GitHub App product-connect foundation (НОВОЕ):** DEC-052 выбирает GitHub App
  installation как product path (не OAuth/PAT в браузере). Добавлены backend
  config/status contract (`FOUNDEROS_GITHUB_APP_*`), workspace-scoped
  app-installation connection endpoint
  `POST .../github/connections/app-installation`, safe status payload без
  секретов, no provider calls, no persisted installation access tokens, no
  external writes. `/github` теперь показывает GitHub App readiness, local repo
  surface count, token persistence boundary, and writes disabled.
- **GitHub local repository surface (НОВОЕ):** `.local/repos.json` (25 repos,
  owner `qtwin-io`, offline/local only) теперь поддержан как fallback GitHub
  discovery snapshot for repo audit / repository inventory. Добавлен скрипт
  `scripts/prepare_github_local_snapshot.py`, который нормализует этот файл в
  `.local/discovery/github/<snapshot>/raw/repos.json` и пишет безопасный
  `.local/github-repositories.env` allowlist snippet без provider calls,
  токенов/секретов или write enablement. Локально подготовлен snapshot
  `.local/discovery/github/local-repos-current/raw/repos.json`. Решение — DEC-051.
- **Repository identity guard:** добавлена миграция `e8f9a0b1c2d3` и уникальный
  guard `uq_repositories_workspace_provider_full_name` (`workspace_id, provider,
  full_name`). `_upsert_repository` теперь race-safe across `external_id` and
  `full_name` paths and не понижает стабильный GitHub id обратно до full_name.
  Это закрывает near-term backlog item перед GitHub App live read sync.
  Решение — DEC-050.
- **Briefings Chunk 1 — персистентные сводки (бэкенд+фронтенд, гейты зелёные):**
  ручная Founder-сводка теперь **сохраняется**. Детерминированная генерация не
  менялась и по-прежнему без LLM — сохраняется только её вывод. Новые модели
  `Briefing` / `BriefingItem` + миграция `e7f8a9b0c1d2` (Briefings head на момент chunk),
  workspace-scoped, `ON DELETE CASCADE`, элементы упорядочены по `position` и
  повторяют форму генератора. `POST .../briefings/manual` запускает генерацию,
  **сохраняет** сводку + элементы и возвращает её с `id`
  (`persistence:"persisted"`); плюс история: `GET .../briefings` (новые сверху)
  и `GET .../briefings/{id}`, обе session/operator-auth и строго workspace-scoped
  (чужой workspace → 404). Фронтенд: «Сформировать сводку» сохраняет и показывает
  сводку, есть список истории с переоткрытием прошлых сводок (русские строки в
  `web/lib/messages.ts`). Бэкенд: `pytest 368 passed`, `ruff` чисто,
  `alembic check` чисто. Фронтенд: `npm test` 90, build/lint/typecheck зелёные.
  Без LLM и без GitHub OAuth/connect. Решение — DEC-048.
- **Что сделано ранее (sync-hardening/auth/русский UI series перед Briefings):**
  - **Sync-layer hardening (FOS-027B2 → далее):** в канонические `tasks` добавлен
    partial unique index `uq_tasks_workspace_provider_external_id`
    (`workspace_id, source_provider, external_id` при `external_id IS NOT NULL`;
    ручные задачи с NULL `external_id` не ограничиваются), дедуп существующих
    дублей в миграции `f7b8c9d0e1a2`, и идемпотентный `ON CONFLICT` upsert для
    `Task` / `PullRequest` / `SourceRecord` / `Repository` в
    `github_normalization_service`. Дрейф alembic по `ingested_events` сведён
    отдельной миграцией `a8c9d0e1f2b3` (только индексы/ограничения, без данных).
    `Task.updated_at` задокументирован как маркер «последней синхронизации»
    (bump на каждый sync), а пользовательская свежесть берётся из
    `source_updated_at`. Усилено шифрование секретов:
    `FOUNDEROS_SECRET_ENCRYPTION_KEY` обязателен вне local — иначе fail-closed,
    без переиспользования API-ключа как материала шифрования. Публичный health
    разделён: `GET /health` — минимальный liveness без auth, `GET /health/detail`
    (флаги app/env/write/llm) — за операторским ключом.
  - **Auth-фаза (email+password, серверные сессии; сейчас один основатель,
    архитектура многопользовательская):** `password_service` (Argon2id),
    `session_service` + таблица `sessions` (в БД хранится только sha256-хэш
    токена, сырой токен только в cookie), эндпоинты
    `/api/v1/auth/login|logout|me|change-password`, зависимость `require_session`
    и резолвер `get_current_actor` (сессия-ИЛИ-операторский ключ; сессия в
    приоритете), DB-throttle логина от перебора (`login_attempts`, по умолчанию
    5 попыток / блок 15 мин, generic 401 без раскрытия существования email),
    same-origin Next.js-прокси для first-party cookie
    (`FOUNDEROS_API_PROXY_TARGET`), фронтенд полностью переведён с
    operator-key/owner-email на сессию (`web/lib/config.ts` удалён, workspace
    берётся из сессии), страница Settings → аккаунт/смена пароля, админ
    создаётся идемпотентно через `scripts/create_admin_user.py`.
  - **Русский UI:** вся пользовательская копия вынесена в центральный каталог
    сообщений `web/lib/messages.ts` (без i18n-фреймворка).
- **Текущее состояние:** детерминированный evidence-first спайн + продуктовый
  логин (email+password, серверные сессии) + **персистентные briefings** поверх
  него + GitHub App product-connect + polling-only live read sync backend/UI
  foundation; операторский API-ключ остаётся для server/CI/админ-скриптов. Один
  alembic head — `e8f9a0b1c2d3`.
- **Дальше:** briefing/evidence isolation verification over GitHub App synced
  data, rate-limit/error observability, и первый real-provider read run только
  после отдельного human approval; затем Briefings Chunk 2 — LLM-нарратив поверх уже персистентной
  модели и реальных evidence-backed данных; провижининг второго
  пользователя/тиммейта (мультиюзер); первый прод-деплой на Railway.
- **Примечание:** Briefings Chunk 1 — это реальный код (модели / миграция /
  эндпоинты / фронтенд) с зелёными гейтами; бэкенд и фронтенд закоммичены
  отдельно, push не делался.

---

## 📊 ПРОГРЕСС

```
Tasks: 22 / 29   ▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▱▱▱▱▱▱▱   71%   (строго DONE)
Chunks: 2 / 9
```

Разбивка: **DONE = 22** · **PARTIAL = 6** · **MISSING = 1**.
FOS-002 закрыт по DEC-028 (spine-subset §6: SourceRecord/EvidenceRef/Repository/PullRequest/Task; остальные §6-модели отложены по чанкам — не «не сделано», а scoped-out).
DONE строго = есть код + проходящий тест/рабочий эндпоинт под acceptance criteria.
`docs/TODO.md` теперь содержит только near-term backlog; завершённые детали
живут в этом файле, `docs/CHANGELOG.md` и git history.

**Легенда статусов задачи:** `[ ]` todo · `[~]` in progress/partial · `[x]` done · `[!]` blocked

---

## 🚦 GATE HEALTH (результат последней проверки — 2026-07-01)

| Gate | Status | Last checked | Evidence |
|---|---|---|---|
| `alembic upgrade head` | ✅ pass | 2026-07-01 | GitHub App live read-sync foundation made no schema change; один линейный head `e8f9a0b1c2d3`; `uv run alembic heads`, `uv run alembic current`, `uv run alembic upgrade head`, and `uv run alembic check` зелёные |
| **Lineage-2 purge** (DEC-029) | ✅ done | 2026-06-24 | ~139 модулей + 27 таблиц + ~150 тестов + 55 скриптов + non-canon доки удалены; leftover static UI artifact/test removed by FOS-PURGE-01; tag `pre-purge-20260624` |
| **CHUNK 1 gate** (model tests + encryption roundtrip) | ✅ pass | 2026-06-24 | `tests/test_canonical_models.py` (9) + `test_integration_models.py` + encryption roundtrip — зелёные |
| backend tests (`pytest`) | ✅ pass | 2026-07-01 | GitHub App live read-sync foundation pass: **390 passed / 0 failed / 1 warning** |
| `ruff` | ✅ pass | 2026-07-01 | GitHub App live read-sync foundation pass: `uv run ruff check .` → `All checks passed!` |
| API namespace `/api/v1` (DEC-023) | ✅ done | 2026-06-24 | 660 `/v1`→`/api/v1`; нет stray `/v1` |
| frontend build | ✅ pass | 2026-07-01 | GitHub App live sync UI pass: `npm test` **98 passed**, `npm run build`, `npm run typecheck`, and `npm run lint` passed |
| docs navigation | ✅ pass | 2026-07-01 | Covered by full pytest; docs/private-beta/hosting/navigation contract tests remain green |
| `alembic check` (retained substrate) | ✅ reconciled | 2026-07-01 | Прежний дрейф (7 операций на `ingested_events`) сведён миграцией `a8c9d0e1f2b3`; GitHub App live read-sync foundation pass: `alembic upgrade head` + `alembic check` зелёные |
| **GitHub E2E (spine)** | ✅ selected-sync pass | 2026-06-26 | FOS-019B created exactly one real GitHub issue; FOS-020 read it back; FOS-021 closed it; FOS-022 selected repo issue sync read the approved smoke repo only; FOS-023 selected PR sync covered with read-only mocks |
| **full main E2E** | ✅ pass | 2026-06-26 | «approved action → real GitHub issue → canonical sync → cleanup close → closed-state sync → selected repository issue sync → selected PR sync» verified locally/mocked where provider reads are not live; execution count stayed single and no extra issues were created |
| prod smoke | ✅ pass | 2026-06-27 | FOS-026C: deployed Railway read-only smoke passed with minimal private-beta workspace/owner context; no provider writes, LLM calls, selected repo sync, or ActionProposal execute |

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
- [~] FOS-007 — GitHub product connect — GitHub App installation выбран и
  foundation реализован (DEC-052): backend config/status, workspace-scoped
  app-installation connection record, `/github` readiness UI. Live provider read
  sync ещё не реализован; PAT bridge остаётся operator/admin bridge.
- [x] FOS-008 — GitHub sync repositories — `normalize-local` при `persist_if_supported=true` пишет canonical `source_records`/`repositories` idempotent-upsert; `persist_if_supported=false` остаётся projection-only. Доказано `tests/test_github_normalization_api.py` + `tests/test_github_first_backend_e2e.py`
- [x] FOS-009 — GitHub sync issues + PRs — local normalization reads local `cursor_before.local_github` issue/PR records, persists issues as canonical `Task`, PRs as canonical `PullRequest` linked to `Repository`, exposes `/api/v1/workspaces/{workspace_id}/github/operational-work`, and repoints repository inventory to canonical `repositories` before retained `source_events` fallback. No live provider execution.
- [x] FOS-010 — Connectors UI page — `web/app/dashboard` has product GitHub local-sync controls over existing backend contracts, and `/github` shows GitHub App product-connect readiness. UI reads connection status, runs canonical local normalization through `/api/v1/workspaces/{workspace_id}/github/local-sync`, reports counts/warnings, refreshes operational work, and keeps live provider execution out of the UI.
- [x] FOS-011 — Dashboard v0 — `web/app/dashboard/page.tsx` fetches canonical GitHub operational work via typed frontend API client, renders issue/task and PR sections, repository labels where present, open/all/closed/merged filters, and loading/empty/error states. No `source_events` direct read and no hardcoded current GitHub work.
- [x] FOS-012 — Brain entity API + UI — workspace-scoped canonical Company Brain read API `GET /api/v1/workspaces/{workspace_id}/company-brain` reads canonical `repositories`/GitHub `tasks`/`pull_requests` + `SourceRecord` refs, and `web/app/dashboard` renders deterministic evidence-backed GitHub state. Legacy founder preview routes remain unchanged; no live provider/AI execution.

### CHUNK 4 — Briefing MVP
*Gate: пользователь генерирует briefing с evidence drawer.*
- [x] FOS-013 — Briefing backend — `app/services/founder_briefing_service.py` детерминированный и без LLM; Chunk 1 добавил `Briefing`/`BriefingItem` persistence + history поверх той же генерации. `tests/test_founder_briefing_api.py` зелёный
- [x] FOS-014 — Briefing UI + evidence drawer — `web/components/BriefingPanel.tsx` + `EvidenceDrawer.tsx`; `web/app/dashboard` and `web/app/briefings` call the deterministic manual briefing endpoint, persist/show the briefing, list/reopen history, render returned briefing items/signals/warnings, and show provided evidence refs without inventing facts

### CHUNK 5 — Action Approval 🎯 full main E2E
*Gate: approved action создаёт реальный GitHub issue.*
- [x] FOS-015 — Action proposal API + UI — `app/api/actions.py` (create/list/get/approve/reject/execute) + модели ActionProposal/ActionExecution + миграция `f5a6b7c8d9e0`; `web/components/ActionProposalsPanel.tsx` wires product list/create/approve/reject, evidence drawer, local audit timestamps, and explicit no-external-execution copy. UI does **not** call execute.
- [x] FOS-016 — GitHub create-issue execution preview/audit — `app/api/actions.py` exposes `/execution-preview` for local approved GitHub issue proposals, preserves evidence refs without inventing them, reports eligibility/capabilities/audit fallback, and blocks `/execute` when `enable_write_actions=false`. `web/components/ActionExecutionControls.tsx` surfaces preview-only state, external-write disabled copy, confirmation UI only when backend says live writes are enabled, and no raw provider payload dumps. GitHub client remains mocked in tests; real external-write proof is still human-gated.
- [x] FOS-017 — Execution audit/receipt hardening — new proposal-scoped `ActionExecutionEvent` model/table + migration `a2b3c4d5e6f7`, idempotent audit append/list service, `/audit` read endpoint, persisted preview/blocked-execute events, and local execution receipt. `web/components/ActionExecutionControls.tsx` reads durable audit events, keeps timestamp fallback when empty, refreshes audit after preview/blocked execute, and continues to state that no external write occurred.
- [x] FOS-018 — Human-gated GitHub issue write path — existing `github_issue_execution_service` can call the GitHub issue client only after `enable_write_actions=true`, approved proposal, supported GitHub issue action, valid payload/connection, non-empty evidence refs, explicit confirmation, target repository in the explicit GitHub write allowlist (`FOS_GITHUB_WRITE_ALLOWED_REPOS` / `FOS_GITHUB_SMOKE_REPO`), and no existing successful receipt. Success/failure/duplicate/block paths persist `ActionExecution` receipts and `ActionExecutionEvent` audit events; duplicate execute returns the existing receipt without another provider call. `web/components/ActionExecutionControls.tsx` shows live execution controls only when backend capabilities allow them, requires explicit confirmation, and renders external issue receipt/link only after backend success. Automated tests still mock provider calls; FOS-019B proved the manual live smoke with exactly one issue against an approved private smoke repository.
- [x] FOS-020 — Post-execution sync verification — `POST /api/v1/workspaces/{workspace_id}/actions/proposals/{proposal_id}/sync-execution-result` validates the executed/succeeded GitHub issue receipt, uses an encrypted GitHub connection for read-only issue fetch, creates a local manual SyncJob, and reuses canonical GitHub normalization to upsert `SourceRecord` + `Task`. Verified against the smoke issue: operational work and Company Brain see the synced issue; deterministic briefing reflects the normalization item; execution rows remain single and no provider write is called.
- [x] FOS-021 — Smoke issue closeout / closed-state sync — after explicit human approval, closed exactly the existing approved smoke issue and nothing else. Closed state was read back and synced through the FOS-020 path; canonical `Task` is closed, operational open work no longer includes it, closed operational work does include it, Company Brain open issues=0/closed issues=1, deterministic briefing remains evidence-backed, and ActionExecution receipt count stayed single.
- [x] FOS-022 — Selected repository issue sync — `POST /api/v1/workspaces/{workspace_id}/github/repositories/issues/sync` reads issues only from explicit read-sync allowlisted repositories, uses encrypted GitHub connection access for provider reads, creates a manual SyncJob, normalizes selected issues into canonical `SourceRecord`/`Task` + repository records, skips PR-shaped issue API records, preserves open/closed state, and keeps external writes disabled. Verified live against the approved smoke repository only; no `/execute` call and no new GitHub issue/write.
- [x] FOS-023 — Selected repository PR sync — `POST /api/v1/workspaces/{workspace_id}/github/repositories/pull-requests/sync` reads PRs only from explicit read-sync allowlisted repositories, validates allowlist before token decrypt/provider reads, creates a manual SyncJob, normalizes selected PRs into canonical `SourceRecord`/`PullRequest` + repository records, preserves open/closed/merged state, avoids duplicate repository rows after selected issue sync, de-dupes PR read models by repository+number, and keeps external writes disabled. Verified with read-only provider mocks for the approved repository scope; no `/execute` call and no GitHub write.

### CHUNK 6 — Remaining Connectors — FROZEN / POST-MVP
*Gate: Jira / Gmail / Drive / Documents видны в Brain.*
- [ ] FOS-JIRA-01 — Jira connector minimal — frozen until GitHub App live read sync proves the ingestion pattern. No active `app/connectors/jira.py` or `web/app/jira` exists after the Lineage-2 purge.
- [ ] FOS-GMAIL-01 — Gmail connector minimal — frozen until after GitHub. No active `app/connectors/gmail.py` or `web/app/gmail` exists.
- [ ] FOS-019 — Drive connector minimal — frozen until after GitHub. No active `app/connectors/google_drive.py` or `web/app/drive` exists.
- [ ] FOS-DOC-01 — Documents module — post-MVP; no canonical Document CRUD (`body_markdown`, §7.11) or `web/app/documents` exists.

### CHUNK 7 — Polish + Repo Audit UI
*Gate: нет dead-end состояний; repo audit виден в UI.*
- [~] FOS-RA-01 — Repo Audit UI — backend `app/services/repo_audit.py` есть; страницы `web/app/repo-audit` нет
- [ ] FOS-P — Polish (errors/retries/empty/filters/evidence UX) — UI на уровне scaffold, не сделано

### CHUNK 8 — Testing Gate + Deploy
*Gate: launch gate зелёный; production URL работает; первый E2E в проде.*
- [x] FOS-025B — Deploy/smoke foundation — explicit backend CORS config, placeholder-only env contract, read-only private-beta smoke script, `make smoke`, local full-stack/private-beta smoke docs, and focused smoke/config/docs tests. No deploy and no external writes.
- [x] FOS-025C — Frontend/full-stack deploy-readiness CI gates — `.github/workflows/ci.yml` now has separate backend and frontend jobs; backend gates are preserved and add explicit docs/smoke/CORS/CI contract tests; frontend gates run `npm ci`, `npm test`, `npm run build`, `npm run typecheck`, and `npm run lint`; CI contains no provider secrets, live smoke command, selected sync, or execute calls.
- [x] FOS-025D — Private-beta deploy runbook/config path — `docs/deploy/private-beta.md` documents the manual split backend/frontend deploy model, managed Postgres/Redis, backend/frontend runtime commands, migration verification, backup/rollback, env names, CORS/API-base setup, GitHub connection limits, and read-only post-deploy smoke procedure. No deploy config that auto-deploys, no cloud secrets, and no deployment was added.
- [x] FOS-025E — Railway hosting target dry-run plan — `docs/deploy/railway-private-beta.md` maps the concrete Railway-only split-service target (backend API, frontend web, managed Postgres, managed/deferred Redis), commands, env names, domain/CORS/API-base, migration, smoke, rollback, operator checklist, and later live-provider-smoke approval boundaries; placeholder-only backend/frontend/smoke env templates and hosting-doc safety tests were added. No provisioning or deploy.
- [x] FOS-026B — Railway private-beta rehearsal — Railway project/backend/frontend/Postgres were provisioned; backend/frontend deployments reached success; Alembic migrated Postgres to head; deployed health/auth-only read-only smoke passed. No provider writes, LLM calls, selected sync, or ActionProposal execute.
- [x] FOS-026C — Private-beta workspace context + full deployed smoke — minimal workspace/owner context was bootstrapped through the supported operator API, then full read-only deployed smoke passed across workspace, GitHub connection status, Company Brain, operational work, and deterministic transient briefing checks. No provider writes, selected repo live sync, ActionProposal execute, or LLM calls.
- [x] FOS-SMOKE-01 — Smoke tests — backend `tests/test_github_first_backend_e2e.py` + `tests/test_external_connector_readonly_smoke.py` зелёные; FOS-025B added `make smoke` + read-only private-beta smoke script; FOS-026C proved the deployed Railway read-only smoke path with minimal private-beta workspace context.
- [x] FOS-T — Full tests + frontend build — FOS-025C local gate: backend full pytest 297 passed / 1 warning; frontend `npm test`, build, typecheck, and lint passed; CI now enforces both backend and frontend gates
- [x] FOS-027B1 — Private-beta blocker hardening pass 1 — API auth is fail-closed outside local via a startup guard; untrusted server-provided URLs render through `safeHref`/`SourceLink` (http(s)-only); stale `app/agents` bytecode and deleted-LLM/agent/boundary-doc references were reconciled. Backend pytest/ruff and frontend test/build/typecheck/lint green. No deploy, push, or provider writes.
- [x] FOS-027B2 — Task uniqueness + idempotent task upsert — partial unique index `uq_tasks_workspace_provider_external_id` (`workspace_id, source_provider, external_id` where `external_id IS NOT NULL`) + dedupe migration `f7b8c9d0e1a2`; the GitHub-issue→`Task` upsert in `github_normalization_service` is now `ON CONFLICT DO UPDATE` (index-matched), bumping `updated_at` per "last synced" semantics. Closes the duplicate-Task-rows blocker.
- [x] Sync-layer idempotency + hardening (post-FOS-027B2) — idempotent `ON CONFLICT` upserts for `PullRequest`/`SourceRecord`/`Repository`; `ingested_events` alembic drift reconciled (migration `a8c9d0e1f2b3`, indexes/constraints only); secret-encryption fail-closed outside local (`FOUNDEROS_SECRET_ENCRYPTION_KEY` required); public health split (`/health` liveness public, `/health/detail` behind operator key).
- [x] Auth phase (email+password, server-side sessions) — `password_service` (Argon2id), `session_service` + `sessions` table (stores only the sha256 token hash), `/api/v1/auth/login|logout|me|change-password`, `require_session` + `get_current_actor` (session-or-operator resolver), DB login brute-force throttle (`login_attempts`), same-origin Next.js proxy for a first-party cookie (`FOUNDEROS_API_PROXY_TARGET`), frontend migrated off operator-key/owner-email to the session (`web/lib/config.ts` removed), Settings→account page, admin seeded via `scripts/create_admin_user.py`. Single founder now, multi-user-capable. No FOS id (feat(auth)/feat(web) commits). See DEC-041…DEC-047.
- [x] Russian UI localization — all user-facing copy centralized in `web/lib/messages.ts` (no i18n framework; second language is a small addition). See DEC-045.
- [~] FOS-D — Deploy (Railway) — private-beta rehearsal environment exists and read-only deployed smoke passes; production auth is now built (email+password sessions), but GitHub App live-sync hardening/custom-domain hardening and the first production deploy of the auth phase remain before broader beta.

---

## ⛔ BLOCKERS

- ~~[CHUNK 0] 4 doc-contract теста красные~~ — **РЕШЕНО (ШАГ A, 2026-06-24).** Починено doc-side (тесты не ослаблялись): вернул CI-секцию в README, lean `docs/playbook.md`, восстановил `docs/ops/jira-target-blueprint.md`, прилинковал guarded-operations, убрал legacy static-UI путь. pytest 1809/0. Коммит `394df7b`.

- ~~[CHUNK 1] Фундамент «вбок» — ОЖИДАЕТ РЕШЕНИЯ A/B~~ — **РЕШЕНО (DEC-028):** ветка A — §6 расширяет спайн (spine-subset готов, FOS-002), knowledge-graph lineage → frozen legacy и удалён (DEC-029). `source_events` repointed to compatibility fallback in FOS-009 (DEC-030); physical drop remains a later migration/cleanup task, not this feature path.

- [SPINE] **GitHub App live sync productization is next.** GitHub App
  product-connect foundation is recorded in DEC-052; polling-only backend live
  read sync is recorded in DEC-053. The next missing piece is product UI,
  observability/hardening, briefing/evidence isolation over synced data, and the
  first real-provider read run after explicit human approval.

---

## 🧾 SESSION LOG (append-only, новое — сверху)

- `2026-07-01` — **GitHub App live sync explicit repo UI.**
  Productized the backend polling-only live read-sync foundation on `/github`:
  typed frontend API for
  `POST .../github/connections/app-installation/sync`, explicit owner/repo input
  (prefilled from repository surface when available), read-only sync action,
  invalid-repo/missing-app/error/success states, synced counts, and visible
  no-write/no-token-persistence copy. No browser secrets/operator key/PAT. Tests
  added for endpoint URL/body, render states, result/warning rendering, and
  no-write boundary. Docs updated (TODO, ROADMAP, CHANGELOG, README, master
  playbook, PROGRESS). Проверки: frontend `npm test` **98 passed**, `npm run
  build`, `npm run typecheck`, `npm run lint`, docs contracts **16 passed**,
  `git diff --check`, tracked secret scan — зелёные. Backend code not changed in
  this UI chunk after previous backend **390 passed**. No real provider calls,
  deploys, production DB/cloud writes, raw storage/Obsidian edits, or push.

- `2026-07-01` — **GitHub App polling-only live read sync backend foundation.**
  Продолжили по плану после GitHub App product-connect foundation. Добавлен
  DEC-053: v0 live read sync is polling-only/admin-triggered/explicit repo
  scoped; webhooks deferred until raw-body signature verification + delivery
  dedupe. Backend: новый `github_app_token_service` builds GitHub App JWT and
  mints short-lived installation tokens just-in-time; `github_repository_client`
  reads installation repositories; `github_app_live_sync_service` validates
  workspace-scoped app-installation connection, requires explicit repositories,
  reads installation repos/issues/PRs, creates manual SyncJob, and persists via
  existing idempotent `normalize_github_sync_job_local`; new endpoint
  `POST .../github/connections/app-installation/sync`. Tests mock all provider
  calls and prove token not persisted, no provider writes, workspace isolation
  before provider read, member/viewer RBAC, repo-not-installed rejection, invalid
  state rejection, and JWT shape without private-key leakage. Docs updated
  (DECISIONS, TODO, ROADMAP, CHANGELOG, README, master playbook, PROGRESS).
  Проверки: focused **46 passed / 1 warning**, full backend `pytest`
  **390 passed / 1 warning**, `uv run ruff check .`, `alembic
  heads/current/upgrade/check` — зелёные. Frontend not touched. No real provider
  calls, deploys, production DB/cloud writes, raw storage/Obsidian edits, or
  push.

- `2026-07-01` — **GitHub App foundation independent verification + test hardening.**
  Независимо перепроверен предыдущий foundation commit (`31566e9`) на ветке
  `feat/github-app-connect-foundation`: backend/frontend gates подтверждены
  зелёными до изменений (**380 / 95**). Найдены и закрыты три реальных test-gap
  на новом admin-gated endpoint `POST .../github/connections/app-installation`
  (сравнение с sibling `provider-token` контрактом): member/viewer RBAC → 403
  `insufficient workspace role`; идемпотентный update того же installation
  in place (одна строка, обновлённые metadata); невалидный
  `repository_selection` → 400. Только тесты, без изменения продакшн-поведения.
  Проверки: `uv run ruff check .` (тест-файл), full backend `pytest`
  **384 passed / 1 warning**, `git diff --check` — зелёные. No provider calls,
  deploys, production writes, or push.

- `2026-07-01` — **GitHub App product-connect foundation.**
  Создана branch `feat/github-app-connect-foundation` от local `main`
  (содержит предыдущий local GitHub repository-surface commit). Добавлен DEC-052:
  product connect uses GitHub App installation, not browser PAT/OAuth; GitHub
  App private key/webhook secret are backend-only; short-lived installation
  tokens are minted just-in-time and not persisted. Backend: new
  `FOUNDEROS_GITHUB_APP_*` config/status contract; redacted
  `/github/connection-status` app block; admin endpoint
  `POST .../github/connections/app-installation` records/updates a
  workspace-scoped installation connection without provider calls, SyncJob
  execution, persisted tokens, or external writes; service rejects binding the
  same installation to another workspace. Frontend: `/github` renders GitHub App
  readiness, local repository-surface count, token persistence boundary, and
  writes disabled via a new product-connect panel. Env templates/runbooks,
  TODO/ROADMAP/CHANGELOG/PROGRESS/master playbook updated. Checks:
  `uv run ruff check .`, `uv run alembic heads/current/upgrade/check`, full
  backend `pytest` **380 passed / 1 warning**, frontend `npm test` **95 passed**
  + build + typecheck + lint, `git diff --check`, and tracked secret scan —
  зелёные. No provider calls, deploys, production DB/cloud writes, raw
  storage/Obsidian edits, or push.

- `2026-06-30` — **GitHub local repository surface prep.**
  Подготовлен offline/local GitHub repository surface из `.local/repos.json`: 25
  repo records (owner `qtwin-io`, mostly private) без provider calls. Repo audit
  и repository inventory теперь принимают `.local/repos.json` как fallback
  discovery snapshot when canonical `.local/discovery/github/<snapshot>/raw/repos.json`
  absent. Добавлен `scripts/prepare_github_local_snapshot.py`: normalizes owner
  string → `owner.login`, adds `visibility`, refuses sensitive-looking keys,
  writes canonical discovery snapshot and safe `.local/github-repositories.env`
  allowlist snippet. Локально создан ignored snapshot
  `.local/discovery/github/local-repos-current/raw/repos.json` + ignored
  `.local/github-repositories.env`. Обновлены DEC-051, README, TODO/ROADMAP,
  CHANGELOG, PROGRESS. Проверки: focused tests **17 passed**, full backend
  **375 passed / 1 warning**, `ruff`, `alembic heads/current/upgrade/check`,
  tracked secret scan, frontend `npm test` **90 passed** + build + typecheck +
  lint — зелёные. No provider calls, deploys, production DB/cloud
  writes, raw storage/Obsidian or secrets edits.

- `2026-06-30` — **Repository identity guard before GitHub live sync.**
  Рабочая ветка `fix/repository-identity-guard`. Закрыт near-term blocker перед
  GitHub product connect/live sync: в `repositories` добавлен DB-level unique
  guard `uq_repositories_workspace_provider_full_name` (`workspace_id, provider,
  full_name`) миграцией `e8f9a0b1c2d3` (новый single head). Миграция
  детерминированно дедупит существующие duplicate rows по full_name, re-points
  `pull_requests.repository_id` на keeper и удаляет loser rows. `_upsert_repository`
  переведён на race-safe `ON CONFLICT DO NOTHING` + select/update by either
  identity; work-item paths no longer downgrade stable GitHub numeric ids back to
  full_name. Добавлены concurrent cross-path, stable-id preservation,
  workspace-isolation and schema-constraint tests. Обновлены DEC-050,
  `docs/TODO.md`, `docs/ROADMAP.md`, `docs/CHANGELOG.md`, `PROGRESS.md`.
  Проверки: focused sync/model tests **19 passed**, full backend **371 passed / 1
  warning**, `ruff`, `alembic heads/current/upgrade/check`, tracked secret scan,
  frontend `npm test` **90 passed** + build + typecheck + lint — зелёные. No push,
  provider calls, deploys, production DB/cloud writes, raw storage/Obsidian or
  secrets edits.

- `2026-06-30` — **Project actualization / continuation checkpoint.**
  Сверены required docs (`docs/README.md`, `AGENTS.md`, `CLAUDE.md`), live
  status, near-term backlog, git state and targeted repository/GitHub sync debt.
  Remote checked with `git fetch origin`: `main` чистый, локальная ветка
  **ahead `origin/main`** (`origin/main` на `016c7e7`), push не делался. Текущий следующий
  инженерный шаг не меняется: перед GitHub product connect/live sync закрыть
  Repository identity/race debt — DB-level guard for workspace-scoped GitHub
  repository `full_name`/identity, then continue GitHub App/product connect
  design. Проверки actualized: `uv run ruff check .`, `uv run alembic heads`,
  `uv run alembic current`, `uv run alembic upgrade head`, `uv run alembic
  check`, `uv run pytest -q` (**368 passed / 1 warning**), tracked secret scan,
  frontend `npm test` (**90 passed**) + build + typecheck + lint — зелёные. No
  provider calls, deploys, production DB/cloud writes, raw storage/Obsidian or
  secrets edits.

- `2026-06-29` — **Project-wide audit / cleanup / docs refresh.**
  Проведена полная инвентаризация tracked/untracked структуры без чтения
  секретов. Удалены 3 obsolete grouped-lifecycle operator scripts
  (`doctor_no_marker_grouped_lifecycle_review.py`,
  `manual_no_marker_grouped_lifecycle_review.py`,
  `manual_no_marker_grouped_lifecycle_review_sweep.py`): они не имели ссылок из
  активного пути и не импортировались из-за уже удалённого report-модуля.
  `docs/TODO.md` сжат из completed-work ledger в near-term backlog; active docs
  обновлены под persisted Briefings и следующий шаг GitHub product connect/live
  sync перед LLM-нарративом. Добавлены doc-maintenance правила в
  `docs/README.md`/`AGENTS.md`, Make check targets, расширен `.gitignore`,
  убран неиспользуемый `session_cookie_secure` config field, а secret scan
  теперь тихо пропускает deleted-but-not-yet-staged files. Проверки: `uv sync
  --frozen`, `ruff`, `alembic upgrade head`, `alembic check`, full pytest
  **368 passed / 1 warning**, frontend `npm test` **90 passed** + build +
  typecheck + lint, docs contract tests **22 passed**, tracked secret scan,
  markdown link sanity, `git diff --check` — зелёные. No push, deploy, provider
  calls, production DB/cloud writes, raw storage/Obsidian/secrets edits.

- `2026-06-29` — **Briefings Chunk 1: персистентные сводки (бэкенд+фронтенд).**
  Ручная Founder-сводка теперь сохраняется. Генерация
  (`founder_briefing_service`) не менялась и без LLM — сохраняется только вывод.
  Бэкенд: новые модели `Briefing`/`BriefingItem` (`app/db/briefing_models.py`),
  миграция `e7f8a9b0c1d2` (новый head; workspace-scoped, `ON DELETE CASCADE`,
  `position`-порядок, форма элементов = форма генератора),
  `briefing_persistence_service`, `POST .../briefings/manual` сохраняет и
  возвращает сводку с `id` (`persistence:"persisted"`), история
  `GET .../briefings` (новые сверху) + `GET .../briefings/{id}` (workspace-scoped,
  чужой → 404). Обновлены transient-ассерты в briefing/e2e/selected-sync тестах.
  Гейты: `pytest 368 passed`, `ruff` чисто, `alembic upgrade head`/`current`/`check`
  зелёные. Фронтенд: api `listBriefings`/`getBriefing`, `BriefingPanel` грузит
  историю, показывает сохранённую сводку и переоткрывает прошлые; русские строки
  в `web/lib/messages.ts`; `npm test` 90, build/lint/typecheck зелёные. Два
  отдельных коммита (бэкенд, фронтенд), затем docs. Без LLM, без GitHub
  OAuth/connect; workspace-изоляция проверена тестом. Решение — DEC-048.
- `2026-06-28` — **Docs reconciliation (docs-only).** Сверил канонические доки с
  реальным кодом/git после auth-фазы: 18 локальных коммитов поверх `82fb52f`
  (последний в `origin/main`) не были отражены в трекинг-доках, т.к. промпты
  фазы запрещали трогать доки. Обновлены `PROGRESS.md`, `docs/TODO.md`,
  `docs/DECISIONS.md` (DEC-041…DEC-047), `docs/ROADMAP.md`, `docs/CHANGELOG.md`,
  `founderOS_MASTER_PLAYBOOK.md` (status-блок), `README.md`, `.env.example`
  (+`FOUNDEROS_API_PROXY_TARGET`), `SECURITY_BASELINE.md`. Никакого кода:
  `app/` / `web/` / `migrations/` не тронуты; факты проверены по коду
  (эндпоинты, таблицы, миграции, env-переменные) и git-истории, ничего не
  выдумано. Тесты в этом проходе заново не прогонялись. Стейл-claim, который
  чинили: ROADMAP «Missing: Login page» и «Missing: Production auth/session
  decision» — логин/сессии теперь построены.
- `2026-06-28` — **Auth-фаза + русский UI (feat(auth)/feat(web)).** Реализован
  продуктовый логин email+password на серверных сессиях: `password_service`
  (Argon2id), `session_service` + таблица `sessions` (в БД только sha256-хэш
  токена), эндпоинты `/api/v1/auth/login|logout|me|change-password`,
  `require_session` + `get_current_actor` (сессия-ИЛИ-операторский ключ),
  DB-throttle логина (`login_attempts`, по умолчанию 5/15 мин), same-origin
  Next.js-прокси для first-party cookie (`FOUNDEROS_API_PROXY_TARGET`).
  Фронтенд переведён с operator-key/owner-email на сессию (`web/lib/config.ts`
  удалён, workspace из сессии), Settings → аккаунт/смена пароля, админ —
  `scripts/create_admin_user.py` (идемпотентно). Вся UI-копия вынесена в
  `web/lib/messages.ts` (русский, без i18n-фреймворка). Один основатель сейчас,
  архитектура многопользовательская. Решения зафиксированы в DEC-041…DEC-047.
- `2026-06-28` — **Sync-layer hardening (FOS-027B2 + далее).** Канонические
  `tasks` получили partial unique index
  `uq_tasks_workspace_provider_external_id` + дедуп-миграцию `f7b8c9d0e1a2`;
  upsert issue→`Task` стал идемпотентным `ON CONFLICT`, как и
  `PullRequest`/`SourceRecord`/`Repository`. Дрейф `ingested_events` сведён
  миграцией `a8c9d0e1f2b3` (индексы/ограничения, без данных). `Task.updated_at`
  задокументирован как «последняя синхронизация». Шифрование секретов
  fail-closed вне local (`FOUNDEROS_SECRET_ENCRYPTION_KEY`). Health разделён на
  публичный liveness и операторский `/health/detail`. Один alembic head —
  `c0e1f2a3b4d5`.
- `2026-06-27` — **FOS-027B1 private-beta blocker hardening pass 1.** Made API
  auth fail-closed outside local: `enforce_fail_closed_auth` (FastAPI lifespan)
  aborts startup when a non-local `APP_ENV` runs with auth disabled or without a
  configured key; the `api_auth_enabled=false` default is kept for local dev.
  Added a shared frontend `safeHref` helper + `SourceLink` component so
  untrusted server-provided URLs (evidence/source URLs, `external_result_url`)
  are clickable only for http(s); `javascript:`/`data:`/`vbscript:`/malformed
  render as non-clickable text. Removed stale `app/agents` bytecode and
  reconciled CLAUDE.md / SECURITY_BASELINE.md / README.md references to deleted
  LLM/agent code and a deleted boundary doc. Checks: backend `pytest`/`ruff`
  green, frontend `npm test` (86) / build / typecheck / lint green. No deploy,
  no push, no Railway change, no provider writes; secrets not printed.

- `2026-06-27` — **FOS-026C private-beta workspace context + full read-only deployed smoke.**
  Bootstrapped the minimal private-beta workspace/owner context in the deployed
  Railway database through the supported operator workspace bootstrap API. Full
  read-only deployed smoke passed across health/auth, workspace read, GitHub
  connection status read, Company Brain read, operational work read, and
  deterministic transient briefing generation. Provider writes, selected repo
  live sync, ActionProposal execute, LLM, and real connectors remained disabled
  or uncalled. Secret values and operational IDs are intentionally omitted.
- `2026-06-27` — **FOS-026B authenticated Railway private-beta setup/rehearsal.**
  Created the Railway rehearsal project with backend, frontend, and managed
  Postgres services; Redis was skipped. Configured backend/frontend env through
  Railway only, with provider writes, LLM, and real connectors disabled. Current
  Railway Railpack required `RAILPACK_BUILD_CMD`/`RAILPACK_START_CMD`, and the
  backend `DATABASE_URL` needed the `postgresql+asyncpg` driver form. Alembic
  migrated Railway Postgres to head. Backend health, frontend load, CORS
  preflight, and API auth behavior were verified. Read-only deployed smoke passed
  in health/auth-only mode; workspace-scoped smoke is blocked until a
  private-beta workspace/owner context is approved. Secret values, DB URLs, API
  keys, Railway IDs, and provider payloads are intentionally omitted. No push,
  GitHub provider write, selected repo live sync, ActionProposal execute, OpenAI
  call, or custom domain setup occurred.

- `2026-06-26` — **FOS-025E Railway private-beta hosting dry-run plan.**
  Added `docs/deploy/railway-private-beta.md` plus placeholder-only backend,
  frontend, and smoke env templates under `docs/deploy/templates/`. The plan
  selects the Railway-only split-service target implied by the master playbook,
  mapping backend API, frontend web, managed Postgres, managed/deferred Redis,
  domain/CORS/API-base, env names, migration, smoke, rollback, and operator
  checklist steps without provisioning anything. Added hosting-doc tests for
  required sections, commands, env names, placeholder-only templates, no
  secret-shaped values, no auto-deploy workflows, and no provider-write/sync
  commands. No deploy, provisioning, external writes, provider calls, GitHub
  issue/PR changes, or push were performed.

- `2026-06-26` — **FOS-025D private-beta deploy runbook/config path.**
  Added `docs/deploy/private-beta.md` and linked it from README/docs/web docs.
  The runbook chooses a manual split deployment baseline (backend API process,
  frontend web process, managed Postgres, managed/deferred Redis), documents
  backend/frontend install/build/start commands, migration head/current
  verification, database backup and restore-as-rollback policy, exact env names,
  CORS/API-base setup, GitHub connection boundaries, and read-only post-deploy
  `make smoke`. Added deploy-doc safety tests that verify required env names,
  smoke/read-only boundaries, no secret-shaped values, and no auto-deploy
  workflow. No deploy, external writes, provider calls, GitHub issue/PR changes,
  or push were performed.

- `2026-06-26` — **FOS-025C frontend/full-stack deploy-readiness CI gates.**
  Extended `.github/workflows/ci.yml` into separate backend and frontend jobs.
  Backend CI keeps the secret scan, `uv sync --frozen`, ruff, Alembic upgrade,
  and full pytest, plus explicit docs/smoke/CORS/CI contract tests. Frontend CI
  runs `npm ci`, `npm test`, `npm run build`, `npm run typecheck`, and
  `npm run lint` from `web/` using pinned actions and no provider secrets. Added
  CI deploy-readiness contract tests proving frontend gates exist and forbidden
  execute/selected-sync/live-smoke/provider-secret strings are absent. No deploy,
  external writes, GitHub issue/PR changes, or push were performed.

- `2026-06-26` — **FOS-025B private-beta deploy/smoke foundation.** Added
  explicit backend CORS settings with local-safe defaults, a read-only
  private-beta smoke script, `make smoke`, placeholder-only `.env.example`,
  local full-stack/private-beta docs, and smoke/config/docs tests. The smoke
  policy forbids ActionProposal execute, selected repository sync, provider-token
  setup, local-sync, normalize-local, post-execution-result sync, provider write
  endpoints, raw response dumps, and secret/env value printing. No deploy, no
  external writes, no GitHub issue/PR changes, and no push were performed.

- `2026-06-26` — **FOS-024 selected repository sync UI controls.** Exposed the
  existing read-only selected repository issue and PR sync backends in the
  product frontend. Added typed API helpers (`syncSelectedRepositoryIssues`,
  `syncSelectedRepositoryPullRequests`, optional combined
  `syncSelectedRepositoryGitHubWork`) plus request/response types, and a new
  `SelectedRepositorySyncControls` dashboard panel near the existing GitHub
  sync/Company Brain/operational-work panels. The panel discovers the GitHub
  `connection_id` from the existing connection-status endpoint (never
  hardcoded), validates explicit `owner/repo` input client-side (non-empty, one
  slash, no spaces), syncs one explicit allowlisted repository at a time, and
  never offers "sync all org repos". It covers missing-settings,
  missing-connection, invalid-input, per-action loading (issues / PRs / both),
  success summaries (repositories synced; issues synced/open/closed; PRs
  synced/open/closed/merged; skipped PR-shaped issue records), allowlist
  (`Repository is not allowlisted for selected sync.`), permission, generic
  error, and empty/no-records states. The UI states read-only / no external
  writes, renders no raw JSON or private IDs/secrets, and refreshes Company
  Brain plus operational work after a successful sync via the existing dashboard
  refresh counter. No backend contract change was needed. No external GitHub
  write was performed. Checks: `git diff --check` passed, selected-sync tests
  **6 passed**, GitHub normalization/inventory **23 passed**, action/execution
  regression **60 passed**, Company Brain + briefing + backend E2E **15
  passed**, docs navigation **2 passed**, full pytest **287 passed / 1
  warning**, `ruff` clean, tracked secret scan clean; frontend `npm test` **79
  passed**, `npm run build` passed, `npm run typecheck` passed, `npm run lint`
  passed. Next: multi-repo selected sync from the UI (after the human approves
  additional repositories) or production/deploy readiness.

- `2026-06-26` — **FOS-023 selected repository PR sync.** Added a
  read-only selected repository PR sync endpoint:
  `POST /api/v1/workspaces/{workspace_id}/github/repositories/pull-requests/sync`.
  The path requires an explicit read-sync allowlist (`FOS_GITHUB_SYNC_ALLOWED_REPOS`
  or existing selected GitHub repo config), validates selected repositories
  before token decrypt/provider calls, fetches GitHub pull requests read-only,
  creates a local manual SyncJob, and reuses canonical GitHub normalization to
  upsert repository `SourceRecord`/`Repository` plus PR `SourceRecord`/
  `PullRequest` rows. Selected PR sync preserves open/closed/merged state, uses
  repository+number identities for PR read-model de-dupe, keeps repository
  identity stable after selected issue sync so duplicate repository rows are not
  created, and performs no issue/PR/comment/merge/close/provider write. Verified
  with read-only provider mocks for the approved repository scope. Checks:
  focused selected PR sync tests **3 passed**, GitHub normalization/inventory/
  selected-sync tests **29 passed**, Company Brain + briefing + backend E2E
  tests **15 passed**, action/proposal tests **60 passed**, docs navigation
  **2 passed**, full pytest **287 passed / 1 warning**, `ruff` clean, tracked
  secret scan clean. Next: FOS-024 selected repository sync UI controls, or
  broader selected issue+PR sync only after the human approves additional
  repositories.

- `2026-06-26` — **FOS-022 selected repository issue sync.** Added a
  read-only selected repository issue sync endpoint:
  `POST /api/v1/workspaces/{workspace_id}/github/repositories/issues/sync`.
  The path requires an explicit read-sync allowlist (`FOS_GITHUB_SYNC_ALLOWED_REPOS`
  or existing selected GitHub repo config), validates selected repositories
  before token decrypt/provider calls, fetches GitHub issues read-only, skips
  PR-shaped issue API records, creates a local manual SyncJob, and reuses
  canonical GitHub normalization to upsert repository `SourceRecord`/`Repository`
  plus issue `SourceRecord`/`Task` rows. Product read models de-dupe GitHub
  issue rows by repository+number so alternate historical identifiers do not
  double-count a real issue. Live verification was limited to the approved
  smoke repository: one closed issue synced, open issue count stayed 0,
  operational work and Company Brain report the issue as closed, deterministic
  briefing remains evidence-backed, and ActionExecution receipt counts stayed
  unchanged. No GitHub issue/comment/PR/release/settings write occurred, and
  private issue URL plus local IDs are intentionally omitted from public docs.
  Checks: `git diff --check` passed, focused selected-sync tests **3 passed**,
  GitHub normalization/inventory/selected-sync tests **26 passed**,
  action/proposal tests **60 passed**, Company Brain + briefing + backend E2E
  tests **15 passed**, docs navigation **2 passed**, full pytest **284 passed /
  1 warning**, `ruff` clean, tracked secret scan clean. Next: FOS-023 selected
  repository PR sync, or broader selected issue sync only after the human
  approves additional repositories.

- `2026-06-26` — **FOS-021 smoke issue closeout / closed-state sync.** After explicit human approval, closed exactly the existing approved smoke issue and performed no other GitHub write. No new issue, comment, PR, release, repo setting change, label/assignee/title/body update, or additional repository modification occurred. Closed state was read back and synced through the post-execution sync path: canonical `Task.status=closed`, operational open work no longer contains the smoke issue, closed/all operational work does contain it, Company Brain reports open_issues=0 and closed_issues=1, deterministic briefing remains evidence-backed, and ActionExecution receipt count stayed single. Private issue URL and local workspace/proposal/connection/evidence/source IDs are intentionally omitted from public docs. Checks: `git diff --check` passed, action/proposal tests **60 passed**, GitHub normalization/inventory **23 passed**, Company Brain **2 passed**, briefing **12 passed**, docs navigation **2 passed**, full pytest **281 passed / 1 warning**, `ruff` clean, tracked secret scan clean. Next: FOS-022 selected repository issue sync.

- `2026-06-26` — **FOS-020 post-execution sync verification.** Added a read-only post-execution sync path for executed GitHub issue `ActionProposal` receipts: `POST /api/v1/workspaces/{workspace_id}/actions/proposals/{proposal_id}/sync-execution-result`. The route validates executed/succeeded receipt state, reads exactly the provider issue through the encrypted GitHub connection, writes no GitHub content, creates a local manual SyncJob, and reuses canonical GitHub normalization to upsert `SourceRecord` + `Task`. Live verification read the approved smoke issue back into canonical records; operational work and Company Brain see it, deterministic briefing reflects the normalization evidence, and execution count stayed single. Private issue URL and local workspace/proposal/connection/evidence IDs are intentionally omitted from public docs. Checks: `git diff --check` passed, targeted backend suite **98 passed**, full pytest **281 passed / 1 warning**, docs navigation **2 passed**, `ruff` clean, tracked secret scan clean. Next: explicit smoke issue closeout/cleanup approval, then broader selected-repository issue sync.

- `2026-06-26` — **FOS-019B manual live GitHub issue smoke proof.** Manual live GitHub issue smoke succeeded against an approved private smoke repository. Exactly one GitHub issue was created through the gated `ActionProposal` execution path after runtime capability, explicit confirmation, evidence, allowlist, and idempotency gates. Receipt and durable audit are stored locally (`execution_preview_generated`, `execution_confirmation_received`, `execution_started`, `execution_succeeded`). External issue URL/id and local workspace/proposal/connection/evidence IDs are intentionally omitted from public docs. No other repositories were modified and no push was performed. Next: FOS-020 post-execution sync verification.

- `2026-06-25` — **FOS-019A.2 live-write repository allowlist gate.** Added an explicit non-secret GitHub write repository allowlist (`FOS_GITHUB_WRITE_ALLOWED_REPOS`, with `FOS_GITHUB_SMOKE_REPO` as a single-repo alias) to the approved GitHub issue executor. No allowlist or a non-matching repository blocks before token decrypt/provider calls, records durable `execution_repository_not_allowed` audit, and returns a clear 409. Broad token scope and variable names such as `READONLY` are not trusted as safety boundaries. An earlier bounded setup against an approved private smoke repository target was blocked by GitHub permissions, so no local smoke candidate was prepared in that run and no live issue was created then.

- `2026-06-25` — **FOS-018 gated live GitHub issue execution path.** Hardened the existing approved GitHub issue executor behind strict gates: `enable_write_actions=true`, explicit confirmation, approved GitHub issue proposal, valid issue payload/connection, non-empty evidence refs for live execution, and no existing successful receipt. Duplicate execute returns the existing `ActionExecution` receipt and records `execution_duplicate_returned_existing_receipt` without calling the provider again. Success/failure/block paths now persist durable `ActionExecutionEvent` audit events (`execution_confirmation_received`, `execution_started`, `execution_succeeded`, `execution_failed`, `execution_blocked`) and frontend-safe receipt fields. `web/app/actions` shows live execution controls only when backend capabilities allow them, requires confirmation, and renders external issue id/url only from backend success. Automated tests mock the GitHub issue client; **no real live GitHub write smoke was run**. Checks: `git diff --check` passed, action/proposal execution backend tests **52 passed**, GitHub-first backend E2E **1 passed**, full pytest **273 passed / 1 warning**, `alembic heads/current/upgrade` passed at `a2b3c4d5e6f7`, `alembic check` expected drift only **7 operations on `ingested_events`**, `ruff` clean, `npm test` **60 passed**, `npm run build` passed, `npm run typecheck` passed, `npm run lint` passed, docs navigation **2 passed**, tracked secret scan clean.
- `2026-06-25` — **FOS-017 persistent execution audit trail.** Added proposal-scoped `action_execution_events` with sanitized metadata, deterministic idempotency keys, and indexes for workspace/proposal/created order. Preview now records/reuses `execution_preview_generated` or blocked/unsupported preview events; blocked execute records/reuses `execution_confirmation_missing` or `execution_confirmation_received_but_disabled`; neither path calls GitHub/provider. Added `GET /api/v1/workspaces/{workspace_id}/actions/proposals/{proposal_id}/audit` with a local execution receipt/readiness view. `web/app/actions` now renders persisted audit events, receipt status, local "audit event recorded" copy, and keeps timestamp fallback when no audit rows exist. No live provider call, OAuth, AI/LLM, `source_events` read, ActionExecution overload, legacy audit_logs overload, or raw provider payload dump was added. Checks: `git diff --check` passed, action/proposal execution backend tests **51 passed**, migration metadata tests **2 passed**, GitHub-first backend E2E **1 passed**, full pytest **272 passed / 1 warning**, `alembic heads/current/upgrade` passed at `a2b3c4d5e6f7`, `alembic check` expected drift only **7 operations on `ingested_events`**, `ruff` clean, `npm test` **59 passed**, `npm run build` passed, `npm run typecheck` passed, `npm run lint` passed, docs navigation **2 passed**, tracked secret scan clean.
- `2026-06-25` — **FOS-016 guarded execution preview/audit surface.** Added `GET /api/v1/workspaces/{workspace_id}/actions/proposals/{proposal_id}/execution-preview` for dry-run GitHub issue execution readiness over approved local `ActionProposal` records. The preview validates proposal state/action/payload, returns provider/action/repository/title/body/labels/assignees, preserves backend evidence refs, exposes capabilities, and never calls GitHub. `/execute` now rejects with `external execution is disabled` when `enable_write_actions=false`; mocked execution tests explicitly opt into write capability. `web/app/actions` and dashboard action panels now show `ActionExecutionControls` with preview-only copy, external-write disabled state, no-evidence warnings, audit/status events, and explicit connection+confirmation UI only if backend capabilities enable live writes. No live provider call, OAuth, AI/LLM, source_events UI read, or raw provider payload dump was added. Checks: `git diff --check` passed, action/proposal execution backend tests **50 passed**, full pytest **271 passed / 1 warning**, `ruff` clean, `npm test` **56 passed**, `npm run build` passed, `npm run typecheck` passed after build-generated Next types, `npm run lint` passed after build-generated Next types, docs navigation **2 passed**, tracked secret scan clean.
- `2026-06-25` — **FOS-015 local ActionProposal approval UI.** `web/app/dashboard` and `web/app/actions` now surface the existing local ActionProposal backend contracts: list/create local proposals, approve locally, reject locally, show status counts, proposal target details, audit timestamps, backend warnings, and evidence refs through `EvidenceDrawer`. Added typed frontend API helpers for `/api/v1/workspaces/{workspace_id}/actions/proposals` list/create/approve/reject. The UI intentionally does not call `/execute`, does not claim GitHub writes occurred, and does not read retained `source_events`. Checks: `git diff --check` passed, ActionProposal backend tests **22 passed**, Founder Briefing backend tests **12 passed**, Company Brain backend tests **2 passed**, GitHub normalization/inventory tests **23 passed**, docs navigation **2 passed**, `ruff` clean, tracked secret scan clean, full pytest **268 passed / 1 warning**, `npm test` **48 passed**, `npm run typecheck` passed, `npm run lint` passed, `npm run build` passed.
- `2026-06-24` — **FOS-014 briefing UI + evidence drawer.** `web/app/dashboard` and `web/app/briefings` now surface the existing deterministic manual Founder Briefing backend through `POST /api/v1/workspaces/{workspace_id}/briefings/manual`. Added typed frontend API helpers, `BriefingPanel`, and `EvidenceDrawer` for loading/missing/empty/unsupported/error/success states, returned item/signals/warnings rendering, evidence ref inspection, source links only when provided, and explicit no-live-provider/no-AI/no-action-execution copy. No backend route/schema change; retained `source_events` is not a primary UI path. Checks: `git diff --check` passed, Founder Briefing backend tests **12 passed**, Company Brain backend tests **2 passed**, GitHub normalization/inventory tests **23 passed**, docs navigation **2 passed**, `ruff` clean, tracked secret scan clean, full pytest **268 passed / 1 warning**, `npm test` **38 passed**, `npm run typecheck` passed, `npm run lint` passed, `npm run build` passed.
- `2026-06-24` — **FOS-012 Company Brain GitHub evidence state.** Added workspace-scoped `GET /api/v1/workspaces/{workspace_id}/company-brain` over canonical GitHub `Repository`/`Task`/`PullRequest` rows and `SourceRecord` source refs. It returns deterministic summary counts, repositories, open issue/task highlights, open PRs, recent work, evidence/source refs, and explicit capabilities (`local_sync=true`, live OAuth/provider sync/AI briefing false). `web/app/dashboard` now shows a Company Brain panel between local sync controls and operational work details, with loading/missing/empty/error states and evidence/source rendering. Retained `source_events` is not a primary read path. Checks: `git diff --check` passed, new Company Brain backend tests **2 passed**, GitHub normalization/inventory tests **23 passed**, docs navigation **2 passed**, `ruff` clean, tracked secret scan clean, full pytest **268 passed / 1 warning**, `npm test` **26 passed**, `npm run typecheck` passed, `npm run lint` passed, `npm run build` passed.
- `2026-06-24` — **FOS-010 product GitHub local-sync controls.** Added `POST /api/v1/workspaces/{workspace_id}/github/local-sync` as an explicit local-normalization wrapper over existing manual SyncJob + `normalize-local` behavior; it does not start live provider execution and returns compact status/counts/warnings. `web/app/dashboard` now shows connection/local-sync state, honest no-live-OAuth copy, missing/unsupported/error/success states, and refreshes the canonical operational-work panel after successful local sync. Tests added for backend route success/no-connection/idempotence/no-live path and frontend URL/action/render states. Checks: `git diff --check` passed, GitHub normalization/inventory tests **23 passed**, docs navigation **2 passed**, `ruff` clean, tracked secret scan clean, full pytest **266 passed / 1 warning**, `npm test` **17 passed**, `npm run typecheck` passed, `npm run lint` passed, `npm run build` passed.
- `2026-06-24` — **FOS-011 dashboard GitHub operational work wiring.** `web/app/dashboard` now reads `GET /api/v1/workspaces/{workspace_id}/github/operational-work` through the existing browser-local API base/key/workspace settings. Added typed frontend operational-work API helper, dashboard panel with open/all/closed/merged filters, separate issue/task and PR sections, repository labels, source links, and loading/empty/error states. Frontend tests cover URL building, response parsing, render success/empty/error/loading/filter states, and absence of old `source_events`/placeholder current truth. Checks: `npm test` 8 passed, `npm run typecheck` passed, `npm run lint` passed, `npm run build` passed, FOS-009 backend tests 20 passed, docs navigation 2 passed, `ruff` clean, tracked secret scan clean, full pytest **263 passed / 1 warning**.
- `2026-06-24` — **FOS-009 canonical GitHub issues/PRs + substrate repoint.** `normalize-local` can persist local GitHub issue records into canonical `Task` rows and PR records into canonical `PullRequest` rows linked to `Repository`, with sanitized `SourceRecord` payloads and idempotent counters. Added backend read model `GET /api/v1/workspaces/{workspace_id}/github/operational-work` for open/all/closed/merged issues+PRs. `repository_source_inventory` now prefers canonical `repositories` for workspace reads; retained `source_events` remains read-only compatibility fallback, not dropped in this feature commit. Checks: focused GitHub/inventory tests 28 passed, docs navigation 2 passed, GitHub-first backend E2E 1 passed, `ruff` clean, tracked secret scan clean, full pytest **263 passed / 1 warning**.
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
