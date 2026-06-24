# FounderOS Decisions

Status: current project-level decisions after the alignment audit against
`founderOS_MASTER_PLAYBOOK.md`.

These decisions are durable until explicitly superseded by a later decision
record.

## DEC-001 - Master Playbook Is The Primary Product Source

Decision: `founderOS_MASTER_PLAYBOOK.md` is the main source of truth for product
scope, MVP order, architecture direction, and Definition of Done.

Implication: repo-local docs may describe current implementation, but when
current docs conflict with the master playbook, treat that conflict as an
alignment gap to resolve explicitly.

## DEC-002 - Continue From Current Base

Decision: continue from the current repository base. Do not rewrite from
scratch.

Reason: the backend, evidence model, guards, source tooling, and tests are
valuable. Rewriting would risk losing working logic and safety contracts.

## DEC-003 - Backend Stack Remains Python/FastAPI/Postgres

Decision: keep Python, FastAPI, SQLAlchemy, Alembic, and PostgreSQL as the
backend foundation.

Reason: this matches the master playbook and the existing repository.

## DEC-004 - Static `/ui` Local/Operator UI (Superseded)

Decision: originally keep the static `/ui` as a local/operator interface.

Superseded by DEC-029 and FOS-PURGE-01: the static `/ui` router and its
dedicated HTML artifact are now removed. The product frontend is `web/`; do not
restore or extend `/ui`.

## DEC-005 - Next.js Web App Comes Later As A Separate Slice

Decision: add the master-playbook Next.js frontend separately later.

Implication: do not scaffold or partially implement `web/` during audit/docs
tasks. Plan it under FOS-FE-01 after data-model and GitHub path decisions are
clear.

## DEC-006 - Freeze Post-MVP/Operator Expansion Until GitHub-First E2E

Decision: do not expand post-MVP/operator surfaces until the GitHub-first MVP
E2E is working.

Frozen areas include Telegram/manual pilot, share packs, investor view, Jira
write planning, scheduler/outbox expansion, role agents, advanced diagnostics,
and compliance hardening beyond the baseline.

## DEC-007 - Preserve Evidence-First Product Semantics

Decision: keep evidence-first behavior as a core invariant.

Rules:

- Every extracted task, risk, or decision must have `evidence_refs`.
- Missing evidence returns `null`, an empty array, or insufficient evidence.
- Computed or preview surfaces must show provenance.
- Repositories are components/evidence, not Jira projects by default.

## DEC-008 - AI Does Not Directly Perform External Actions

Decision: AI may draft, classify, summarize, or recommend, but it must not
directly mutate external systems.

Implication: LLM outputs must remain strict JSON and validated before
persistence. Source text is untrusted data.

## DEC-009 - External Writes Require Human Approval

Decision: external writes only happen through human-approved action proposals.

Implication: future GitHub/Jira write paths must pass a human approval boundary
before execution. A live-provider ack alone is not enough to authorize a write.

## DEC-010 - Security Baseline Remains Required, Advanced Compliance Is Later

Decision: maintain the existing security baseline, secret hygiene, auth
boundary, and default-deny guards, but do not let advanced compliance work block
the MVP.

Implication: do not expand compliance programs, enterprise RBAC, SOC2-style
processes, or marketplace security before the GitHub-first MVP E2E.

## DEC-011 - Cleanup Waits For Checkpoint And Scope Split

Decision: no cleanup, deletion, or refactor before the current dirty tree is
checkpointed and split by scope.

Implication: useful but out-of-scope code is marked POST_MVP or FREEZE, not
deleted. Delete candidates are limited to clearly generated/local artifacts.

## DEC-012 - Workspace Auth Starts As Operator-Compatible Contract

Decision: keep the current API-key/operator auth boundary while adding
workspace-aware backend helpers on top of `User`, `Workspace`, and
`Membership`.

Implication: there is no public password login or session UI in the MVP
contract yet. The workspace bootstrap route is operator-protected and MVP-only.
New workspace-aware routes must check `Membership` for access; operator access
requires explicit owner context until session-based user auth is introduced.

## DEC-013 - GitHub MVP Path Uses Hybrid Source Control Bridge

Decision: use a hybrid staged GitHub path for the MVP. Existing Source Control,
repository source inventory, and repo audit remain the bridge/read substrate.
The canonical product path for GitHub connection and sync is
`IntegrationConnection` plus `SyncJob`.

Rationale: existing GitHub/source-control code is guarded, tested, and useful,
but it is not yet the master-playbook OAuth product flow. Starting with a
workspace-scoped repository read API validates the source/evidence layer before
OAuth, sync jobs, and approved writes are added.

Consequences:

- Do not rewrite `source_control` now.
- Do not add GitHub OAuth before the workspace-scoped repository read API.
- Do not expose tokens or raw provider payloads.
- Do not make live provider calls without explicit approval.
- Do not execute external writes before the human-approved action path exists.
- Defer Jira writes, Telegram/share-pack expansion, and new provider modules
  until the GitHub-first E2E is working.

## DEC-014 - GitHub MVP Connection Uses Provider-Token Bridge Before OAuth

Decision: FOS-GH-04 uses an operator-protected manual provider-token bridge to
create or update GitHub `IntegrationConnection` records before the full OAuth
flow exists.

Rationale: workspace auth, the GitHub connection contract, and
`IntegrationConnection` are ready, but the product frontend/session login and
OAuth callback/state machinery are not. A provider-token bridge keeps the next
slice small while moving the product path away from purely local/operator
source inventory.

Consequences:

- GitHub tokens are encrypted before storage and never returned by API
  responses.
- Token records expose only `has_access_token` / `has_refresh_token` booleans.
- FOS-GH-04 does not live-validate the token with GitHub.
- FOS-GH-04 does not create `SyncJob` rows or call GitHub APIs.
- Full GitHub OAuth remains a later task after the manual connection bridge and
  manual sync-job path are stable.

## DEC-015 - GitHub Normalization Starts As Compatibility Projection

Decision: FOS-GH-06 normalizes GitHub data through a compatibility projection
over existing local repository/source/evidence read models. Persistent graph
upsert is deferred until the graph/source substrate is explicitly reconciled.

Rationale: the existing GitHub graph helper is useful, but it maps repositories
to project entities and is not yet a general workspace-scoped canonical
Repository/Issue/PullRequest persistence path. Projection mode lets the MVP
produce normalized founderOS-compatible shapes, preserve available evidence
refs, and update `SyncJob` lifecycle state without creating duplicate source of
truth.

Consequences:

- `normalize-local` does not call GitHub, Source Control execution, workers, or
  external systems.
- `SyncJob` records can track local normalization status and counters.
- Repository normalization can use the existing local repository inventory
  bridge.
- Issues and pull requests remain empty with warnings until local source data is
  reconciled.
- `persist_if_supported=true` is rejected until graph upsert is deliberately
  scoped.

## DEC-016 - Founder Briefing V0 Is Deterministic And Transient

Decision: FOS-BRF-01 adds a deterministic, transient, local-only Founder
Briefing v0. It does not call an LLM and does not persist `Briefing` or
`BriefingItem` rows.

Rationale: the GitHub-first MVP now has workspace auth, connection records,
manual sync jobs, and local normalization projection. A manual briefing can
surface those local signals with evidence refs and warnings before the project
adds persistent briefing tables or AI generation.

Consequences:

- Briefing v0 reads local DB/read-model services only.
- Every factual item includes evidence refs when available.
- Items without evidence refs include explicit warnings.
- `is_live=false`, `llm_used=false`, and `persistence=transient` are part of
  the contract.
- Persistent `Briefing`/`BriefingItem` models and LLM briefing generation are
  deferred.
- Recommendations in the briefing are not `ActionProposal` records.

## DEC-017 - ActionProposal Approval Foundation Is Local-Only

Decision: FOS-ACT-01 adds canonical `ActionProposal` and `ActionExecution`
tables plus a workspace-scoped proposal API, but approval only records a local
human decision. It does not execute provider actions.

Rationale: the GitHub-first MVP needs a clear approval boundary before the
first external write. Existing `AgentProposal` and `SourceRunRequest` tables
remain useful compatibility/operator surfaces, but they are not the canonical
workspace-scoped action proposal contract for this MVP path.

Consequences:

- Existing `AgentProposal` and `SourceRunRequest` behavior remains untouched.
- Approving a proposal does not call GitHub, Jira, Gmail, Drive, Source Control,
  workers, or any live provider.
- `ActionExecution` exists as future execution tracking foundation only.
- `ActionExecution` rows are not created by approval in FOS-ACT-01.
- FOS-ACT-02 must add the separate, guarded execution path for approved GitHub
  issue creation.

## DEC-018 - GitHub Issue Execution Requires Approved Proposal And Confirmation

Decision: FOS-ACT-02 allows one controlled external action: executing an
approved `github/create_github_issue` `ActionProposal` through an owner/admin
workspace route with `confirm_external_write=true` and a connected GitHub
`IntegrationConnection`.

Rationale: GitHub-first MVP needs a real write path, but only after the local
human approval boundary exists. The execution service validates the proposal,
payload, workspace connection, and token record before calling the isolated
GitHub issue client.

Consequences:

- Tests must mock the GitHub issue client; no live GitHub calls are used during
  development verification.
- GitHub tokens are decrypted only immediately before the issue-client call and
  are never returned by API responses.
- Execution creates `ActionExecution` rows and updates proposal status to
  `executed` or `failed`.
- No background execution, Source Control execution, OAuth flow, or Jira/Gmail/
  Drive execution is introduced in this step.

## DEC-019 - GitHub-First Backend E2E Uses Local Mocks

Decision: FOS-E2E-01 covers the GitHub-first backend MVP path with the real
FastAPI app and test database, but with local repository inventory fakes and a
mocked GitHub issue client.

Rationale: the backend contracts can now be tested end to end without making a
live provider call, running workers, invoking an LLM, or depending on the
future product frontend.

Consequences:

- The smoke flow must prove workspace bootstrap, GitHub connection,
  repository read, manual sync, local normalization, manual briefing,
  ActionProposal approval, and approved issue execution work together.
- Tests must fail if Source Control execution, live GitHub connectors, or LLM
  imports are used in the smoke path.
- Plaintext and encrypted token values must not appear in API responses or
  stored provider response payloads.
- Browser/product E2E remains a later frontend task.

## DEC-020 - Frontend Shell Starts As Separate Next.js App

Decision: FOS-FE-01 starts the product frontend as a separate `web/` Next.js
and TypeScript app. At the time of this decision the existing static `/ui`
remained local/operator-only; DEC-029 and FOS-PURGE-01 later removed it.

Rationale: the backend GitHub-first path is now covered, but the product UI
needs a clean shell before wiring live backend panels. A separate `web/` app
keeps the new MVP frontend isolated from the existing static operator surface.

Consequences:

- `web/` owns the new App Shell, sidebar, placeholder MVP pages, API client, and
  browser-local operator settings.
- Static `/ui` is no longer available; local startup points to the backend root,
  and product UI work remains in `web/`.
- The frontend MVP uses local operator API key configuration through
  `X-FounderOS-API-Key`; production session login is deferred.
- FOS-FE-01 does not add OAuth, provider calls, backend routes, migrations, or
  browser E2E tests.

## DEC-021 - Canonical Documentation Set

Decision: the current documentation source of truth is the root canonical trio:
`founderOS_MASTER_PLAYBOOK.md`, `EXECUTION_PLAN.md`, and `PROGRESS.md`, plus the
required control docs in `docs/`: `README.md`, `DECISIONS.md`, `ROADMAP.md`,
`TODO.md`, `POST_MVP.md`, and `CHANGELOG.md`.

Rationale: older playbook, vision, audit, backlog, and ledger documents came
from several rebuild generations and conflicted with the incoming master
playbook's MVP order.

Consequences:

- `docs/README.md` is the single current docs navigation entry.
- `docs/index.md` remains only as a compatibility pointer for older tooling.
- Archived docs under `docs/_archive/` are traceability only.
- Supporting feature/runbook docs must describe current repo behavior or clearly
  mark post-MVP/frozen status; they do not override the root playbook.

## DEC-022 - Archived Playbooks And Ledgers Are Not Current Scope

Decision: archived docs from the v2 playbook, digital-twin playbook, vision,
Telegram/manual-pilot, Jira rebuild, and historical FOS ledger generations do
not define current MVP scope.

Rationale: the incoming master playbook fixes the MVP spine around
GitHub-first UI flow, evidence-backed Company Brain, Founder Briefing, and
human-approved actions.

Consequences:

- New work follows `EXECUTION_PLAN.md` chunk order.
- Telegram, digest, broad second-opinion graph expansion, Jira rebuild/write
  planning, and share/investor surfaces stay frozen/post-MVP unless explicitly
  pulled into a scoped task.
- If a supporting doc conflicts with the master playbook, record the conflict
  here before implementation.

## DEC-023 - Canonical API Namespace Is `/api/v1`

Decision: the canonical REST base path is `/api/v1` per master playbook §7.1.

Drift found (2026-06-24 audit): every router currently mounts under `/v1`, not
`/api/v1`. There is **zero** usage of `/api/v1` anywhere in `app/` or `web/`.

Wrong-namespace files (all of them): `app/main.py` (`/v1/events` mount) and every
`app/api/*.py` declaring a prefix — `digest.py`, `ui.py`, `company_brain.py`,
`gmail.py`, `google.py`, `extraction.py`, `actions.py`, `share_packs.py`,
`briefings.py`, `drive.py`, `dev.py`, `github.py`, `workspaces.py`,
`knowledge.py`. The Next.js shell also referenced the old workspace path.

Consequences:

- `/api/v1` is canonical; `/v1` was the drift.
- New routes must target `/api/v1`.

**Status — DONE (2026-06-24).** Migrated uniformly: 660 `/v1` → `/api/v1`
replacements across 65 files (router prefixes, `inbox.py` inline routes,
`main.py` events mount, link-emitting services, the former static founder UI
page, operator scripts, `web/`, and all test request paths). No external
provider URL contains `/v1`, so none were affected; `/health` stays unversioned.
FOS-PURGE-01 later removed the legacy `/ui` file/test. Verified: `ruff` ✅,
`pytest` 1809 passed ✅, route check shows no active stray `/v1`, web `tsc` ✅.
Done independently of the FOS-002 data decision (A/B).

## DEC-024 - Canonical Source/Entity/Evidence Naming Is SourceRecord / NormalizedEntity / EvidenceRef

Decision: canonical persistence names follow master playbook §6.7/§6.9/§6.8:
`SourceRecord` (`source_records`), `NormalizedEntity` (`normalized_entities`),
and `EvidenceRef` (`evidence_refs`).

Drift found (2026-06-24 audit): none of these canonical tables exist. The repo
instead persists raw source data as `source_events` (`SourceEvent`),
`source_documents` (`SourceDocument`), and `ingested_events`; entities live in
`entities` (`EntityRecord`, knowledge-graph shape, different schema); and
`EvidenceRef` exists only as a Pydantic schema (`app/agents/schemas.py`) plus
denormalized `evidence_refs` JSON arrays inside many services — not a table.
Canonical `Briefing`/`BriefingItem`/`Repository`/`PullRequest`/`Task`/`Project`/
`Document`/`Goal`/`Insight`/`MessageThread`/`DriveFile` tables are likewise
absent. This is why the CHUNK 2 gate (mock connector → SourceRecord +
NormalizedEntity + EvidenceRef) is currently impossible.

Conflict locations: `app/db/event_models.py` (`source_events`,
`normalized_activity_items`), `app/db/graph_models.py` (`entities`),
`app/db/source_models.py` (`source_documents`), `app/db/models.py`
(`ingested_events`); projections in `app/services/github_normalization_service.py`.

Consequences:

- Canonical names per §6 are the target. Existing tables are compatibility
  substrate (consistent with DEC-013/DEC-015), not the canonical contract.
- How to converge is a real fork → see ASK-2 below. Do not silently keep two
  parallel schemas as the source of truth.
- No schema/code change during this audit.

## DEC-025 - Next.js `web/` Is The Product Frontend; Static `/ui` Removed

Decision: per master playbook §8, the product frontend is the Next.js app in
`web/`. The former static founder UI page, previously served at `/ui`, is
removed and must not be restored.

Drift note: this supersedes DEC-004/DEC-020. New product UI work goes only into
`web/`; local/operator helpers should not point users to `/ui`.

Consequences:

- `web/` owns canonical pages (`/login`, `/dashboard`, `/connectors`, `/github`,
  `/jira`, `/gmail`, `/drive`, `/documents`, `/brain`, `/briefings`, `/actions`,
  `/repo-audit`, `/settings`). Currently only `dashboard`, `github`, `briefings`,
  `actions`, `settings` exist as stubs.
- `/ui` is retired and deleted by FOS-PURGE-01.
- `scripts/start_local.py` opens the backend root and notes that product UI
  lives in `web/`.

## DEC-026 - Out-Of-Order Post-MVP Surfaces Are No-Go Until GitHub-First E2E

Decision: backend surfaces that were built before the GitHub-first E2E is green
are explicitly out of current scope (no-go) and must not be developed further,
per master playbook §3.3/§3.4 and EXECUTION_PLAN iron rules #5/#6. This makes
DEC-006/DEC-022 concrete against the code that actually exists.

Out-of-scope code present in the repo (do not extend): Telegram delivery/bot
(`telegram_delivery.py`, `telegram_founder_bot.py`), digests
(`app/api/digest.py`, `digest_*`), share packs (`app/api/share_packs.py`,
`share_packs.py`), second-opinion graph (`second_opinion*.py`), role/sales/
product/team/execution views (`role_views.py`, `sales_view.py`,
`product_view.py`, `team_view.py`, `execution_view.py`), Jira write planning
(`jira_write_readiness.py`, `jira_creation_dry_run.py`, `jira_operating_model.py`),
attention/triage agents, meeting agents, knowledge QA/scoring, Obsidian export,
and operating-rhythm/command-center surfaces.

Consequences:

- These remain frozen and untouched (no deletion now — DEC-011). New ideas go to
  `docs/POST_MVP.md`, not into code.
- Effort goes to the spine: canonical data foundation (CHUNK 1) → connector
  framework (CHUNK 2) → GitHub UI E2E (CHUNK 3).

## DEC-027 - Operational Doc Contracts Are Restored, Not Tests Weakened

Decision: doc-contract tests broken by the docs consolidation are fixed on the
**docs** side, not by weakening the tests. The consolidation archived/slimmed docs
that encode live operational invariants without updating their tests.

Restored / re-created (current supporting docs per DEC-021, distinct from the
archived v2 product playbook/vision per DEC-022):

- `docs/playbook.md` — new lean **dev/CI** playbook (gates, secret hygiene, supply
  chain). Not the archived v2 product playbook.
- `docs/ops/jira-target-blueprint.md` — restored Jira target design (repos stay
  components, not projects — see DEC-007). Archive copy kept for history.
- Root `README.md` — restored the "Development & CI" / dependency-automation
  section (CI parity, Renovate, Scorecard, Dependency Review, uv Dependency
  Submission).
- `docs/index.md` — links the guarded-operations runbook, dev/CI playbook, and
  Jira blueprint.

Also: removed the literal legacy static-UI path from `docs/DECISIONS.md` and
`docs/_audit/DOCS_AUDIT.md` so no doc points users to the obsolete static page.

Consequence: `pytest` is fully green (1809 passed). The fix is docs-only; no test
assertion, app code, migration, or workflow was changed.

## DEC-028 - Spine Lineage Is Canonical; Knowledge-Graph Lineage Is Frozen Legacy

Decision (resolves ASK-2, 2026-06-24): the repo has **two parallel data lineages**
(see `docs/_audit/DOCS_AUDIT.md` → "Load-Bearing Map"). We canonicalize on **Lineage
1 (the GitHub MVP spine)** and freeze Lineage 2.

- **Canonical = Lineage 1:** `users`/`workspaces`/`memberships`,
  `integration_connections`, `sync_jobs`, `action_proposals`, `action_executions`,
  **plus new canonical §6 tables added to this lineage** (this task).
- **Frozen legacy = Lineage 2:** `entities` (+ `entity_aliases`, `entity_links`,
  `entity_source_accounts`, merge layer), `source_events`,
  `normalized_activity_items`, the knowledge-graph/identity services, and the
  founder-views/digest/inbox/telegram surfaces. **Do not develop. Do not delete
  now.** Retirement is a separate post-MVP task, taken only after the canonical
  layer covers what those surfaces need.

Build rules for the canonical layer (FOS-002, incremental — CHUNK 1):

- Add **only the spine-critical §6 subset now**: `SourceRecord` (§6.7),
  `EvidenceRef` (§6.8), `Repository` (§6.12), `PullRequest` (§6.13), `Task`
  (§6.11). All uuid-keyed and workspace-scoped, matching the
  `integration_models`/`action_models` conventions.
- **No two live lines:** the spine persists ONLY into these new canonical tables.
  It must not write to `source_events`/`entities`; those stay touched only by
  frozen Lineage-2 code.
- **`NormalizedEntity` (§6.9) DEFERRED** — decided from the code: no GitHub-only
  spine reader needs a generalized entity. `company_brain_preview` (FOS-012 Brain)
  reads `.local` + `repo_audit` (filesystem), the canonical web dashboard is an
  unwired stub, and the spine reads `Repository`/`PullRequest`/`Task` directly.
  Revisit when the canonical `/api/v1/.../brain/entities` API is actually built.
- **`Project`/`Briefing`/`BriefingItem`/`MessageThread`/`DriveFile`/`Document`/
  `Goal`/`Insight` deferred** to their chunks; `Person` not built (post-MVP, ASK-1).
  `Task.project_id`/`assignee_person_id` and `PullRequest.author_person_id` are
  nullable uuids with no FK yet (forward-compatible).
- **Generic connector framework (FOS-004/005/006) deferred:** no speculative
  abstraction now; extract it at the second connector (Jira/Gmail). The shared §6
  substrate makes that extraction cheap later.

## DEC-029 - Lineage-2 Is Purged (Code, Tables, Docs)

Decision (2026-06-24, branch `chore/purge-legacy`): the frozen Lineage-2
generation is removed from the repo, leaving only the canonical GitHub spine
(Lineage 1) + canonical §6 tables (DEC-028). Classification proof and full lists
are in `docs/_audit/PURGE_AUDIT.md` (import-graph closure from canonical roots).

Removed:

- **Code (~139 modules):** the entities graph + identity satellites
  (`graph_models`, `entity_*`), knowledge-graph/RAG (`knowledge_*`, `chunking`,
  `extraction_processor`, `agents/*`), digest/inbox/telegram/founder-views,
  gmail/drive/google/events/extraction/share-packs connectors+routers,
  second-opinion, attention, jira, obsidian, declarations, status,
  source-control + discovery, the legacy connector layer
  (`connectors.github`, `source_control`), the legacy guard machinery, and the
  static `/ui` router plus its final leftover HTML artifact removed by
  FOS-PURGE-01.
- **Tables (27, migration `e1a2b3c4d5f6`):** the entities graph + the
  knowledge/gmail/attention/second-opinion/share-pack/source-control/declaration/
  status/extraction tables. The migration is intentionally irreversible.
- **Tests (~150)** of the deleted code, plus negative-guard lines trimmed from the
  9 spine API tests (all positive spine assertions kept).
- **Scripts (55)** that imported deleted modules; **docs**: `docs/_archive/**`,
  `docs/features/*`, `docs/runbooks/*`, `docs/ops/*`, `docs/security/*`,
  `docs/decisions/*`, and stray standalone docs (architecture, data-model,
  dev-env, obsidian-bridge, operator_runtime_setup, source-connectors, playbook,
  github-integration-decision, index).

Kept: canonical spine + `canonical_models` + identity/integration/action/audit
models + the temporary substrate (DEC-030), the canonical doc set
(`founderOS_MASTER_PLAYBOOK.md`, `EXECUTION_PLAN.md`, `PROGRESS.md`,
`docs/{README,DECISIONS,ROADMAP,TODO,POST_MVP,CHANGELOG}.md`, `docs/_audit/*`),
`CLAUDE.md`/`AGENTS.md`/`SECURITY_BASELINE.md`, and the Next.js `web/` shell.

Verification: app boots; `alembic upgrade head` clean; `alembic check` has
expected retained-substrate drift. Current FOS-PURGE-01 check reports 7
operations, all on `ingested_events`; this remains intentionally unfixed until
FOS-009. `ruff` clean; full pytest is 258 passed after deleting the 9 static UI
artifact tests (github-first E2E green → spine intact); web `tsc`/`build` clean.

Recovery: git tag **`pre-purge-20260624`** is the full restore point. Recover any
file with `git restore --source pre-purge-20260624 -- <path>`. Historical
migrations are retained.

Supersession: **supersedes DEC-025** — the static `/ui` is retired and the
leftover static HTML/test were removed in FOS-PURGE-01; the product frontend is
`web/`. **Partially supersedes DEC-021** —
`docs/index.md` and the supporting/feature/runbook docs are removed; the
canonical set + `docs/_audit/*` remain the documentation.

## DEC-030 - source_events Is Temporary Substrate, Retires In FOS-009

Decision: `source_events`, `normalized_activity_items`, and `ingested_events`
(`app/db/event_models.py` + `IngestedEvent`), plus the
`repository_source_inventory` / `repository_portfolio` bridge, are **retained as a
temporary read-substrate**, not permanent canon. The canonical Brain/Repo-Audit
(`company_brain_preview` → `repo_audit` → `repository_portfolio` →
`repository_source_inventory`) reads `source_events` today, so dropping it now
would break the spine.

Retirement plan (FOS-009): when GitHub sync persists into the canonical
`repositories`/`source_records` tables AND `repository_source_inventory` is
repointed to read those instead of `source_events`, drop `source_events`,
`normalized_activity_items`, and `ingested_events`. The goal remains a single
lineage; this substrate simply dies one planned step later.

## ASK - Open Questions For The Human (not decided)

These are genuinely ambiguous and are NOT resolved by the playbook alone:

- **ASK-1 — The "23 models" count and the missing `Person` entity.** §6 defines
  22 entity sections (6.2–6.23); EXECUTION_PLAN/FOS-002 say "23 модели". §6.9
  `NormalizedEntity.entity_type` includes `person`, and `Task.assignee_person_id`
  / `PullRequest.author_person_id` reference a Person that §6 never defines. Is
  the 23rd model an intended standalone `Person`, or is the count off by one?
- **ASK-2 — Foundation reconciliation strategy. ✅ RESOLVED → DEC-028** (branch A,
  narrowed: §6 extends the spine lineage, knowledge-graph lineage frozen legacy).
  Original framing kept for context: To close the canonical-naming
  gap (DEC-024), do we (a) rename/migrate existing tables to canonical
  (`source_events`→`source_records`, `entities`→`normalized_entities`, add
  `evidence_refs`), or (b) add canonical tables alongside and keep existing ones
  as compatibility substrate (extends DEC-013/DEC-015 projection mode)? This
  decision gates all of CHUNK 1–3 and the spine; it should be made before more
  FOS-002 work.
  **Shape-equivalence finding (2026-06-24, FOS-002 ШАГ B):** option (a) is **not
  viable by rename** — `source_events` and `entities` are not shape-equivalent to
  §6 `SourceRecord`/`NormalizedEntity` (different grain, Integer vs uuid PK, no
  `workspace_id` tenancy anywhere, payload in a separate `ingested_events` table,
  plus an identity/graph layer). Full comparison tables in
  `docs/_audit/DOCS_AUDIT.md` → "Shape-Equivalence Analysis". A forced rename would
  be destructive. Awaiting human go/no-go on option (b) add-alongside before any
  schema change.
