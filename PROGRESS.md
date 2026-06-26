# founderOS — PROGRESS (live state / single source of truth)

> Это **живой файл состояния**. Его обновляет агент (Claude Code / Codex) после КАЖДОЙ задачи.
> Человек смотрит сюда, чтобы за 5 секунд понять: **где мы и что дальше.**
> Текущая ветка `main`; cleanup/FOS-008/doc hygiene fast-forward merged locally
> into `main` at `ef22360`. Remote publish is still pending until a human
> explicitly asks to push.

---

## ▶ СЕЙЧАС

- **Chunk:** `CHUNK 8 — Testing Gate + Deploy`.
- **Task:** FOS-025B — private-beta deploy/smoke foundation.
- **State:** ✅ First deploy foundation exists without deploying: explicit backend
  CORS config, placeholder-only env contract, read-only private-beta smoke
  script, `make smoke`, local full-stack docs, and smoke/config/docs tests. The
  smoke path checks health/auth/workspace/read models and deterministic briefing
  only; it must not call ActionProposal execute, selected repository sync,
  provider-token setup, local-sync, normalize-local, post-execution-result sync,
  or provider write endpoints.
- **Next action:** FOS-025C — add frontend/full-stack deploy-readiness gates to
  CI and continue toward a real private-beta deploy runbook.

---

## 📊 ПРОГРЕСС

```
Tasks: 18 / 25   ▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▱▱▱▱▱▱▱   71%   (строго DONE)
Chunks: 2 / 9
```

Разбивка: **DONE = 18** · **PARTIAL = 6** · **MISSING = 1**.
FOS-002 закрыт по DEC-028 (spine-subset §6: SourceRecord/EvidenceRef/Repository/PullRequest/Task; остальные §6-модели отложены по чанкам — не «не сделано», а scoped-out).
DONE строго = есть код + проходящий тест/рабочий эндпоинт под acceptance criteria.
Для сравнения: `docs/TODO.md` помечает «done» ~22 задачи **собственной** схемы (FOS-DB/GH/BRF/ACT/E2E/FE), что создаёт впечатление почти готового backend MVP; против playbook/main-path схемы строго готово 14.

**Легенда статусов задачи:** `[ ]` todo · `[~]` in progress/partial · `[x]` done · `[!]` blocked

---

## 🚦 GATE HEALTH (результат последней проверки — 2026-06-25)

| Gate | Status | Last checked | Evidence |
|---|---|---|---|
| `alembic upgrade head` | ✅ pass | 2026-06-25 | FOS-018 on `main`: one head `a2b3c4d5e6f7`, current==head |
| **Lineage-2 purge** (DEC-029) | ✅ done | 2026-06-24 | ~139 модулей + 27 таблиц + ~150 тестов + 55 скриптов + non-canon доки удалены; leftover static UI artifact/test removed by FOS-PURGE-01; tag `pre-purge-20260624` |
| **CHUNK 1 gate** (model tests + encryption roundtrip) | ✅ pass | 2026-06-24 | `tests/test_canonical_models.py` (9) + `test_integration_models.py` + encryption roundtrip — зелёные |
| backend tests (`pytest`) | ✅ pass | 2026-06-26 | FOS-023 on `main`: **287 passed / 0 failed / 1 warning** |
| `ruff` | ✅ pass | 2026-06-26 | FOS-023 on `main`: `All checks passed!` |
| API namespace `/api/v1` (DEC-023) | ✅ done | 2026-06-24 | 660 `/v1`→`/api/v1`; нет stray `/v1` |
| frontend build | ✅ pass | 2026-06-26 | FOS-024 on `main`: `npm test` 79 passed; `next build`, `typecheck`/`lint` ok (7 routes) |
| docs navigation | ✅ pass | 2026-06-26 | FOS-023 on `main`: `tests/test_docs_navigation_integrity.py` 2 passed |
| `alembic check` (retained substrate) | ⚠️ expected drift | 2026-06-25 | FOS-018: drift **7 operations**, all on `ingested_events`; retained-substrate physical cleanup is later migration work / DEC-030; НЕ про execution gate |
| **GitHub E2E (spine)** | ✅ selected-sync pass | 2026-06-26 | FOS-019B created exactly one real GitHub issue; FOS-020 read it back; FOS-021 closed it; FOS-022 selected repo issue sync read the approved smoke repo only; FOS-023 selected PR sync covered with read-only mocks |
| **full main E2E** | ✅ pass | 2026-06-26 | «approved action → real GitHub issue → canonical sync → cleanup close → closed-state sync → selected repository issue sync → selected PR sync» verified locally/mocked where provider reads are not live; execution count stayed single and no extra issues were created |
| prod smoke | ⚠️ local command only | 2026-06-26 | FOS-025B added `make smoke` and a read-only private-beta smoke script; no deploy smoke has run |

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
- [x] FOS-009 — GitHub sync issues + PRs — local normalization reads local `cursor_before.local_github` issue/PR records, persists issues as canonical `Task`, PRs as canonical `PullRequest` linked to `Repository`, exposes `/api/v1/workspaces/{workspace_id}/github/operational-work`, and repoints repository inventory to canonical `repositories` before retained `source_events` fallback. No live provider execution.
- [x] FOS-010 — Connectors UI page — `web/app/dashboard` has product GitHub local-sync controls over existing backend contracts: reads connection status, runs canonical local normalization through `/api/v1/workspaces/{workspace_id}/github/local-sync`, reports counts/warnings, refreshes operational work, and keeps live OAuth/provider execution out of the UI.
- [x] FOS-011 — Dashboard v0 — `web/app/dashboard/page.tsx` fetches canonical GitHub operational work via typed frontend API client, renders issue/task and PR sections, repository labels where present, open/all/closed/merged filters, and loading/empty/error states. No `source_events` direct read and no hardcoded current GitHub work.
- [x] FOS-012 — Brain entity API + UI — workspace-scoped canonical Company Brain read API `GET /api/v1/workspaces/{workspace_id}/company-brain` reads canonical `repositories`/GitHub `tasks`/`pull_requests` + `SourceRecord` refs, and `web/app/dashboard` renders deterministic evidence-backed GitHub state. Legacy founder preview routes remain unchanged; no live provider/AI execution.

### CHUNK 4 — Briefing MVP
*Gate: пользователь генерирует briefing с evidence drawer.*
- [~] FOS-013 — Briefing backend — `app/services/founder_briefing_service.py` детерминированный, transient (`BRIEFING_PERSISTENCE_TRANSIENT`), без LLM и без таблиц Briefing/BriefingItem. `tests/test_founder_briefing_api.py` зелёный
- [x] FOS-014 — Briefing UI + evidence drawer — `web/components/BriefingPanel.tsx` + `EvidenceDrawer.tsx`; `web/app/dashboard` and `web/app/briefings` call the deterministic manual briefing endpoint, render returned briefing items/signals/warnings, and show provided evidence refs without inventing facts

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

### CHUNK 6 — Remaining Connectors
*Gate: Jira / Gmail / Drive / Documents видны в Brain.*
- [~] FOS-JIRA-01 — Jira connector minimal — `app/connectors/jira.py` + `jira_discovery`/`jira_graph_mapping`; нет `web/app/jira`, не в каноническом Brain
- [~] FOS-GMAIL-01 — Gmail connector minimal — `app/connectors/gmail.py` + gmail-модели + `app/api/gmail.py`; нет `web/app/gmail`
- [~] FOS-019 — Drive connector minimal — `app/connectors/google_drive.py` + `app/api/drive.py`; нет `web/app/drive`
- [~] FOS-DOC-01 — Documents module — есть `source_documents` (RAG-ingestion), но нет канонического Document CRUD (`body_markdown`, §7.11) и `web/app/documents`

### CHUNK 7 — Polish + Repo Audit UI
*Gate: нет dead-end состояний; repo audit виден в UI.*
- [~] FOS-RA-01 — Repo Audit UI — backend `app/services/repo_audit.py` есть; страницы `web/app/repo-audit` нет
- [ ] FOS-P — Polish (errors/retries/empty/filters/evidence UX) — UI на уровне scaffold, не сделано

### CHUNK 8 — Testing Gate + Deploy
*Gate: launch gate зелёный; production URL работает; первый E2E в проде.*
- [x] FOS-025B — Deploy/smoke foundation — explicit backend CORS config, placeholder-only env contract, read-only private-beta smoke script, `make smoke`, local full-stack/private-beta smoke docs, and focused smoke/config/docs tests. No deploy and no external writes.
- [~] FOS-SMOKE-01 — Smoke tests — backend `tests/test_github_first_backend_e2e.py` + `tests/test_external_connector_readonly_smoke.py` зелёные; FOS-025B added `make smoke` + read-only private-beta smoke script; deployed/full-stack smoke is still not run
- [~] FOS-T — Full tests + frontend build — pytest 259/0 (чекап 2026-06-24); web build ✅
- [ ] FOS-D — Deploy (Railway) — не выполнялся

---

## ⛔ BLOCKERS

- ~~[CHUNK 0] 4 doc-contract теста красные~~ — **РЕШЕНО (ШАГ A, 2026-06-24).** Починено doc-side (тесты не ослаблялись): вернул CI-секцию в README, lean `docs/playbook.md`, восстановил `docs/ops/jira-target-blueprint.md`, прилинковал guarded-operations, убрал legacy static-UI путь. pytest 1809/0. Коммит `394df7b`.

- ~~[CHUNK 1] Фундамент «вбок» — ОЖИДАЕТ РЕШЕНИЯ A/B~~ — **РЕШЕНО (DEC-028):** ветка A — §6 расширяет спайн (spine-subset готов, FOS-002), knowledge-graph lineage → frozen legacy и удалён (DEC-029). `source_events` repointed to compatibility fallback in FOS-009 (DEC-030); physical drop remains a later migration/cleanup task, not this feature path.

- [SPINE] **Selected repository sync UI controls are next.** The live
  write/read-back/cleanup loop, selected repository issue sync, and selected
  repository PR sync backend path are verified for the approved scope. Live
  OAuth/provider sync remains outside this path; broader multi-repository sync
  still requires explicit human-approved repository scope.

---

## 🧾 SESSION LOG (append-only, новое — сверху)

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
