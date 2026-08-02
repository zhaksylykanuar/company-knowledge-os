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

Status: superseded by DEC-041/DEC-043 — the founder web app now has
email+password session login; the operator API key coexists for
machine/CI/admin use. The "no public password login or session UI yet" stance
below is historical.

Decision: keep the current API-key/operator auth boundary while adding
workspace-aware backend helpers on top of `User`, `Workspace`, and
`Membership`.

Implication: there is no public password login or session UI in the MVP
contract yet. The workspace bootstrap route is operator-protected and MVP-only.
New workspace-aware routes must check `Membership` for access; operator access
requires explicit owner context until session-based user auth is introduced.

## DEC-013 - GitHub MVP Path Uses Hybrid Repository Bridge

Decision: use a hybrid staged GitHub path for the MVP. The canonical product
path for GitHub connection and sync is `IntegrationConnection` plus `SyncJob`.
Repository source inventory and repo audit use a staged local read substrate;
after FOS-009 workspace repository reads prefer canonical `repositories` and
retain `source_events` only as compatibility fallback.

Rationale: the first MVP slice needs a small, testable path before the full
master-playbook OAuth product flow. Starting with a workspace-scoped repository
read API validates the source/evidence layer before OAuth, sync jobs, and
approved writes are fully productized. DEC-029 later removed the old
`source_control` implementation; DEC-030 keeps only the temporary repository
read substrate until the FOS-009 repoint.

Consequences:

- Do not restore or extend `source_control`; use the canonical GitHub services
  and keep retained repository inventory substrate only as fallback after the
  FOS-009 repoint.
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
over existing local repository/source/evidence read models. FOS-008 keeps that
projection behavior for `persist_if_supported=false` and adds explicit
canonical repository persistence for `persist_if_supported=true`.

Rationale: the existing GitHub graph helper is useful, but it maps repositories
to project entities and is not yet a general workspace-scoped canonical
Repository/Issue/PullRequest persistence path. Projection mode lets the MVP
produce normalized founderOS-compatible shapes, preserve available evidence
refs, and update `SyncJob` lifecycle state. FOS-008 narrows persistence to the
canonical `SourceRecord`/`Repository` tables that already exist. FOS-009 later
adds supported issue/PR persistence and repoints repository inventory to
canonical repositories first.

Consequences:

- `normalize-local` does not call GitHub, Source Control execution, workers, or
  external systems.
- `SyncJob` records can track local normalization status and counters.
- Repository normalization can use the existing local repository inventory
  bridge.
- `persist_if_supported=false` remains projection-only.
- `persist_if_supported=true` persists only repository `SourceRecord` and
  `Repository` rows with sanitized payloads and idempotent upsert semantics.
- Issues, pull requests, and canonical `EvidenceRef` rows remain deferred until
  deliberately scoped.

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
- FOS-016 adds a dry-run execution preview/product surface that validates the
  proposal and returns execution readiness without calling GitHub.
- The execute route is additionally blocked when `enable_write_actions=false`;
  tests that exercise mocked writes must opt into this runtime capability.
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

Status: partially superseded by DEC-042/DEC-043 — the `web/lib/config.ts`
browser-local operator settings were removed; the frontend now derives the
workspace from the session and sends no operator key/owner email. The
"browser-local operator settings" / "production session login is deferred"
consequences below are historical.

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

Decision: the current documentation source of truth is the control set:
`founderOS_MASTER_PLAYBOOK.md`, `PROGRESS.md`, and `docs/DECISIONS.md`, plus the
planning/navigation docs in `docs/`: `README.md`, `ROADMAP.md`, `TODO.md`,
`POST_MVP.md`, and `CHANGELOG.md`.

Status: amended by DEC-031. `EXECUTION_PLAN.md` and `docs/_archive/**` are no
longer part of the current documentation set.

Rationale: older playbook, vision, audit, backlog, and ledger documents came
from several rebuild generations and conflicted with the incoming master
playbook's MVP order.

Consequences:

- `docs/README.md` is the single current docs navigation entry.
- Deleted historical docs are traceability through git history / tag
  `pre-purge-20260624`, not through a live archive tree.
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

- New work follows the chunk order and live next-task pointer in `PROGRESS.md`.
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
per master playbook §3.3/§3.4. This makes DEC-006/DEC-022 concrete against the
code that existed at audit time.

Status: DEC-029 removed the Lineage-2/post-MVP implementation bulk. Remaining
post-MVP ideas live in `docs/POST_MVP.md`; do not restore deleted Telegram,
digest, share-pack, second-opinion, broad Jira/Drive/Gmail, Obsidian, or
knowledge-graph/RAG code unless a later scoped decision pulls it back.

Consequences:

- New ideas go to `docs/POST_MVP.md`, not into code.
- Effort goes to the spine in `PROGRESS.md`, currently CHUNK 3 / FOS-010/FOS-011.

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
- **Scripts (55)** that imported deleted modules; **docs**:
  `docs/features/*`, `docs/runbooks/*`, `docs/ops/*`, `docs/security/*`,
  `docs/decisions/*`, and stray standalone docs (architecture, data-model,
  dev-env, obsidian-bridge, operator_runtime_setup, source-connectors, playbook,
  github-integration-decision, index).

Kept: canonical spine + `canonical_models` + identity/integration/action/audit
models + the temporary substrate (DEC-030), the canonical doc set
(`founderOS_MASTER_PLAYBOOK.md`, `PROGRESS.md`,
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

FOS-009 implementation note (2026-06-24): workspace repository reads are now
repointed to prefer canonical `repositories` and use `source_events` only as a
read-only compatibility fallback. Supported local GitHub issue/PR records now
persist into canonical `tasks`/`pull_requests` through `source_records`.

Remaining retirement plan: physical drop of `source_events`,
`normalized_activity_items`, and `ingested_events` requires a later focused
migration/cleanup task after the canonical read path stays stable. The goal
remains a single lineage; the retained substrate is no longer the first
workspace repository source, but it is not deleted in FOS-009.

## DEC-031 - Documentation Hygiene Rule

Decision (2026-06-24): no stale control docs accumulate.

- When a plan/status/instruction changes, the outdated version is **DELETED in the
  same commit** — never kept "just in case".
- **Exception — `docs/DECISIONS.md`:** decisions are not deleted, only marked
  "Superseded by DEC-NNN" (history, not clutter).
- **Canonical doc-set is fixed:** `founderOS_MASTER_PLAYBOOK.md`, `PROGRESS.md`,
  `docs/DECISIONS.md`, `docs/ROADMAP.md`, `docs/TODO.md`, `docs/POST_MVP.md`,
  `docs/CHANGELOG.md`, `docs/README.md`, `docs/_audit/*`. Anything outside this set
  and not matching the playbook is a deletion candidate, not a co-resident.
- New ideas outside current scope → one line in `docs/POST_MVP.md`, not a new file
  and not code.

Doc-role map (do not blur): `founderOS_MASTER_PLAYBOOK.md` = **what** to build
(content canon, rare changes); `PROGRESS.md` = **where** we are (live status,
updated every task); `docs/DECISIONS.md` = **why** (decision history). Playbook and
PROGRESS must not contradict each other — divergence is a signal, not normal.

Amends **DEC-029** "kept canonical set": `EXECUTION_PLAN.md` is removed from the
canonical set and collapsed (it duplicated the chunk map now in `PROGRESS.md`, its
driver-prompts are unused, and its rules were partly stale vs DEC-028). The
canonical control trio is **PLAYBOOK + PROGRESS + DECISIONS**.

## DEC-032 - Action Execution Audit Is Durable And Proposal-Scoped

Decision (2026-06-25): approval, preview, execution attempt, and provider result
are separate states. Preview and blocked execution attempts are recorded as
proposal-scoped `ActionExecutionEvent` rows, not as legacy `audit_logs`, retained
`source_events`, or `ActionExecution` rows.

Rationale: before any live GitHub write proof, the system needs an inspectable
local audit/receipt trail that proves what was previewed or blocked without
pretending an external provider action happened.

Consequences:

- Approval is still local approval only; it never executes provider writes.
- External writes require all three gates: runtime capability, explicit user
  confirmation, and the existing approved proposal validation.
- Preview and blocked execute paths must be auditable and idempotent enough to
  avoid noisy duplicate records on refresh/retry.
- Audit event metadata is sanitized and compact. It must not contain tokens,
  secrets, environment/config dumps, raw provider payloads, or raw request bodies.
- `ActionExecution` remains for actual execution attempts/results. External
  result IDs/URLs remain empty until a real provider result exists.
- UI may show persisted audit events and a local receipt/readiness view, but
  must not say a GitHub issue/comment/PR was created unless the backend returns
  a real executed provider result.

## DEC-033 - Live GitHub Writes Require Explicit Repository Allowlist

Decision (2026-06-25): even when `enable_write_actions=true` and an approved
GitHub issue `ActionProposal` has explicit confirmation, live GitHub issue
execution is allowed only for repositories listed in the non-secret write
allowlist (`FOS_GITHUB_WRITE_ALLOWED_REPOS`, or `FOS_GITHUB_SMOKE_REPO` for the
single approved smoke target).

Rationale: local env tokens may have broader scopes than the current smoke
test needs, and variable names such as `READONLY` are not permission boundaries.
The final safety boundary must be explicit target scoping before token decrypt
or provider execution.

Consequences:

- Missing or non-matching repository allowlists block execution with a clear 409
  before token decrypt/provider calls.
- Blocked allowlist cases record durable `execution_repository_not_allowed`
  audit events.
- Tests may opt into mocked provider execution only by setting an explicit
  allowed repository.
- The approved live smoke target is a private repository; concrete repository
  details, external issue URL/id, and local workspace/proposal/connection/
  evidence identifiers are intentionally omitted from public docs.
- FOS-019B later proved the gated path with exactly one issue against that
  approved private smoke repository; local receipt and audit remain the source
  of truth for the private execution details.

## DEC-034 - Executed Provider Results Sync Back Through Read-Only Canonical Normalization

Decision (2026-06-26): post-execution provider receipt sync is a read-only
provider-read path that validates an executed/succeeded `ActionProposal`
receipt, fetches only the specific provider result referenced by that receipt,
creates a local manual SyncJob, and reuses canonical GitHub normalization to
upsert product read records.

Rationale: the product needs a closed loop from local approval to provider
write proof and back into canonical FounderOS state, but this must not become a
second execution path or a generic provider framework.

Consequences:

- Syncing an executed GitHub issue result must not call `/execute`, create a
  second issue, close/comment/update the issue, or perform any provider write.
- The sync path writes local canonical records (`SourceRecord` + `Task`) and
  audit events only.
- Retained `source_events` is not the primary path for post-execution sync.
- Private issue URL/id and local workspace/proposal/connection/evidence IDs are
  omitted from public docs; local receipt/audit/DB rows remain the source of
  truth for private details.
- Broader repository issue sync is a later chunk; FOS-020 proves only the
  executed issue read-back loop.

## DEC-035 - Selected GitHub Read Sync Requires Explicit Repository Allowlist

Decision (2026-06-26): selected repository GitHub read sync is allowed only for
repositories listed in an explicit non-secret read-sync allowlist
(`FOS_GITHUB_SYNC_ALLOWED_REPOS`, with existing selected GitHub repo config as a
compatibility fallback). This read allowlist is separate from the live write
allowlist.

Rationale: read-only sync can still expose private repository metadata and
issue state. Broad organization sync must not happen by default or because a
token has broad scope.

Consequences:

- Missing or non-matching read-sync allowlists block before token decrypt or
  provider reads.
- Selected issue sync may fetch and normalize only explicitly approved
  repositories.
- Selected issue sync must not create, update, close, comment on, or otherwise
  write GitHub content.
- GitHub issue API records that are actually pull requests are skipped or routed
  through a dedicated PR path in a later chunk; they are not double-counted as
  issues.
- Public docs may say selected sync was verified against an approved smoke
  repository, but must omit private issue URLs and local workspace/connection/
  proposal/source/evidence identifiers.


## DEC-036 - Private-Beta Smoke Is Read-Only And CORS Is Explicit

Decision (2026-06-26): the first deploy/private-beta foundation uses explicit
backend CORS configuration and a smoke command that is read-only or deterministic
local-only. CORS origins are configured by env-name contract and default only to
local frontend origins when `APP_ENV` is local; production must configure exact
allowed origins.

Rationale: FOS-025A found that the GitHub-first loop is live-proven locally, but
private beta was blocked by missing deploy smoke, incomplete frontend/backend
connection policy, and no production CORS contract. The first smoke path must
prove deploy wiring without creating provider side effects.

Consequences:

- `make smoke` runs the private-beta smoke script and must not call
  ActionProposal execute, selected repository sync, provider-token setup,
  local-sync, normalize-local, post-execution-result sync, or provider write
  endpoints.
- Smoke output reports step names and HTTP status only; it must not print API
  keys, environment values, response bodies, provider payloads, tokens, encrypted
  secrets, or credential fields.
- Deterministic manual briefing generation is allowed in smoke because it reads
  existing workspace state and does not call providers, LLMs, or external writes.
- Production CORS must list exact frontend origins through explicit env names;
  wildcard origins are ignored by the config resolver.
- This does not deploy FounderOS and does not replace the future production auth,
  GitHub OAuth/onboarding, backup, deploy, and post-deploy runbook work.


## DEC-037 - CI Deploy-Readiness Gates Are Offline And Provider-Free

Decision (2026-06-26): CI deploy-readiness gates include both backend and
frontend checks, but they remain offline/provider-free. Backend CI may run local
Postgres migrations, lint, docs/smoke/CORS/CI contract tests, and full pytest.
Frontend CI may run package install, tests, build, typecheck, and lint. CI must
not call live smoke, provider APIs, selected repository sync, ActionProposal
execute, provider-token setup, or external-write endpoints.

Rationale: FOS-025B created the local private-beta smoke foundation; FOS-025C
turns frontend/full-stack readiness into an enforced gate without depending on
live credentials or causing side effects. Live provider smoke remains a separate
human-approved operation after deployment.

Consequences:

- `.github/workflows/ci.yml` has separate backend and frontend jobs.
- Frontend `npm test`, build, typecheck, and lint are required deploy-readiness
  gates.
- CI contract tests must fail if forbidden live/write/sync commands are added to
  CI.
- No real provider token, API key, encrypted secret, or credential value belongs
  in workflow files.
- Passing CI does not mean the app has been deployed or live-provider-smoked.


## DEC-038 - Private-Beta Deploy Runbook Is Manual, Smoke-Gated, And Write-Disabled

Status: superseded by DEC-077 as the active operational path. Its default-deny,
human-approval, and backup-before-migration principles remain durable for any
future hosted target.

Decision (2026-06-26): the private-beta deployment path is documented as a
manual split-service runbook, not as an automatic deploy workflow. The baseline
uses a backend API process, a frontend web process, managed Postgres, and
managed/deferred Redis. Provider writes remain disabled by default, and the
post-deploy smoke gate uses the existing read-only smoke script.

Rationale: FOS-025A through FOS-025C made local runtime, smoke, and CI readiness
credible, but an automatic cloud deploy would be premature without production
auth, GitHub OAuth/onboarding, backup/restore confirmation, and human approval.
A manual runbook gives the team a concrete path without creating side effects.

Consequences:

- No GitHub Actions workflow may auto-deploy FounderOS without a future explicit
  approval task.
- Deploy docs may mention env variable names and placeholder labels only; no real
  secret, token, database URL, encrypted secret, or credential value belongs in
  docs or config templates.
- `ENABLE_WRITE_ACTIONS` stays disabled for private-beta deploy unless a human
  explicitly approves a bounded live-write smoke with allowlists and rollback.
- Database backup is the rollback boundary for migrations, including historical
  irreversible migrations.
- Passing `make smoke` after deploy proves only read-only/private-beta wiring; it
  does not prove live provider writes, GitHub OAuth, production auth, or LLM
  behavior.


## DEC-039 - Railway Is The Private-Beta Hosting Dry-Run Target

Status: superseded by DEC-077. The Railway rehearsal remains historical
evidence only; it is not the active FounderOS operational target.

Decision (2026-06-26): the concrete private-beta hosting dry-run target is a
manual Railway-only split-service baseline: backend API service, frontend web
service, managed Postgres, and managed/deferred Redis. The target mapping is
documented as dry-run preparation only and does not create resources, deploy, or
add auto-deploy workflows.

Rationale: the master playbook already names Railway as the MVP deployment
target, and the current repo has no competing Render/Fly/Vercel/Docker
production config. A single-vendor split-service plan is the smallest concrete
path that matches the current backend/frontend architecture while preserving the
manual, smoke-gated, provider-write-disabled policy from DEC-038.

Consequences:

- `docs/deploy/railway-private-beta.md` was the target-specific dry-run plan; it
  was removed from the active tree by DEC-077 and remains recoverable from git.
- `docs/deploy/templates/` may contain placeholder-only env templates, but never
  real cloud project IDs, domains, database URLs, API keys, tokens, encrypted
  secrets, or credential values.
- Railway setup remains manual and requires future human approval before any
  project, service, database, domain, or deploy is created.
- No auto-deploy-on-push workflow is allowed by this decision.
- Redis is documented as managed/deferred until an approved worker/job runtime
  makes it mandatory.
- Live provider smoke remains separate, explicitly approved, allowlisted, and
  disabled again after the bounded test.

## DEC-040 - API Auth Is Fail-Closed Outside Local

Decision (2026-06-27): the backend must not run fail-open in a hosted
environment. `enforce_fail_closed_auth` runs at startup (FastAPI lifespan) and
aborts boot when `APP_ENV` is non-local (anything other than
local/dev/development/test/testing) and either `API_AUTH_ENABLED` is false or no
API key (`API_AUTH_KEY` / `FOUNDEROS_API_KEYS`) is configured. The default of
`api_auth_enabled=false` is retained so local developer workflows keep working
without a key.

Rationale: the app uses a single all-powerful operator identity, so a single
forgotten auth flag in a hosted deploy would expose the full operator surface to
anonymous callers. Making that misconfiguration a loud startup failure — rather
than relying on operator memory — is the smallest durable guardrail. Flipping
the default `api_auth_enabled` to true was rejected because it would break the
documented non-breaking local default and force a key on local dev; the startup
guard closes the security hole without that cost.

Consequences:

- Non-local deploys must set `API_AUTH_ENABLED=true` plus a configured key, or
  the service refuses to start.
- Auth may remain disabled only when `APP_ENV` is local/dev/test.
- Startup errors reference env-var names only, never key values.

## DEC-041 - Founder Login Uses Server-Side Revocable Sessions, Not JWT

Decision (2026-06-28): the email+password web login uses server-side sessions,
not stateless JWTs. `password_service` hashes passwords with **Argon2id**
(argon2-cffi default params). `session_service` mints a high-entropy random
token (`secrets.token_urlsafe(32)`), stores **only its sha256 hash** in the
`sessions` table (ORM class `UserSession`), and returns the raw token to the
caller solely to set an **httpOnly** cookie. `POST /api/v1/auth/login|logout`,
`GET /api/v1/auth/me`, and `POST /api/v1/auth/change-password` are the auth
surface; `require_session` is the session dependency.

Rationale: server-side sessions are individually revocable (logout,
change-password revokes other sessions, future admin "sign out everywhere")
without a token-blocklist; a stolen DB row cannot be replayed because only the
hash is stored, and an httpOnly cookie keeps the token out of JS. A stateless
JWT would have been simpler to mint but not revocable and harder to keep out of
the browser safely.

Consequences:

- The raw session token never persists; the DB stores only `token_hash`.
- Validation hashes the incoming cookie token and matches it to `token_hash`,
  rejecting unknown/revoked/expired rows.
- Session lifetime/cookie are env-tunable: `FOUNDEROS_SESSION_TTL_DAYS` (14),
  `FOUNDEROS_SESSION_COOKIE_NAME` (`founderos_session`),
  `FOUNDEROS_SESSION_COOKIE_SAMESITE` (`lax`). The cookie's `Secure` flag is
  driven by `APP_ENV` (set unless the env is local/dev/test).
- Password hashes are never returned by any API; login returns a generic error.

## DEC-042 - First-Party Session Cookie via Same-Origin Proxy (Not SameSite=None)

Status: deployment-specific wording superseded by DEC-077. The durable security
property remains: the browser uses the Next.js same-origin proxy and the cookie
stays first-party. The active topology is now loopback-local rather than two
hosted Railway origins.

Decision (2026-06-28): the frontend and backend deploy as two Railway origins,
but the session cookie stays **first-party**. The Next.js app proxies `/api/*`
(and `/health`) to the backend via `rewrites()` in `web/next.config.mjs`, so the
browser only ever talks to the frontend origin and the cookie is same-origin.
The proxy target is `FOUNDEROS_API_PROXY_TARGET` (server-only; falls back to
`NEXT_PUBLIC_API_BASE_URL`, then `http://localhost:8000`).

Rationale: a cross-site `SameSite=None` cookie would be required if the browser
called the backend origin directly, which is more exposed (CSRF surface,
third-party-cookie restrictions). Routing through a same-origin proxy lets the
cookie remain `SameSite=Lax` and first-party with no cross-site exposure.

Consequences:

- The browser sends no operator API key and no `owner_email`; `apiFetch` is
  always same-origin with `credentials: "include"`.
- `FOUNDEROS_API_PROXY_TARGET` must point at the backend in any split deploy.
- Cookie stays `SameSite=Lax`; `SameSite=None` is intentionally avoided.

## DEC-043 - Session Auth Coexists With Operator API-Key Auth

Decision (2026-06-28): the new session auth does not replace the operator
API-key boundary; they coexist. `get_current_actor` resolves a request from
**either** a valid session cookie (preferred) **or** the operator API key
(`require_api_key`). The operator key is for server/CI/admin tooling
(`scripts/`, smoke, bootstrap); humans use the web login.

Rationale: the operator key is still the right boundary for headless tooling and
existing operator routes, while interactive users should not hold a
broad operator key. One resolver keeps both paths first-class without forking
every route. This supersedes the "no public password login yet" stance of
DEC-012 for the founder-facing web app.

Consequences:

- Endpoints can require a session (`require_session`), the operator key
  (`require_api_key`), or either actor (`get_current_actor`).
- The operator key is no longer the only authenticated identity; it remains
  valid for machine/admin/CI use only.
- Fail-closed operator-auth posture (DEC-040) is unchanged.

## DEC-044 - Account-Active State Reuses User.status (No New is_active)

Decision (2026-06-28): "is this account allowed to log in" reuses the existing
`User.status` column (`active` / `disabled`, guarded by a CHECK constraint)
rather than adding a new `is_active` boolean. The `sessions` migration relies on
`User.status` / `User.password_hash` already existing, so the users table did
not change.

Rationale: a second active/disabled flag would be redundant and could drift out
of sync with `status`. One canonical column avoids ambiguity.

Consequences:

- Disabling an account is `status = 'disabled'`; no boolean to keep in sync.
- New code must read `User.status`, not invent an `is_active` field.

## DEC-045 - Russian UI via a Single Message Catalog (No i18n Framework)

Decision (2026-06-28): all user-facing frontend copy lives in one central
catalog, `web/lib/messages.ts` (a const `M` map of Russian strings plus `T`
interpolation helpers). No i18n framework (next-intl, react-i18next, etc.) is
introduced.

Rationale: the product is founder-facing and Russian-first (see the
founder-facing-russian rule); a single catalog gives one place to edit copy and
keeps components free of inline strings. A full i18n framework is unjustified
overhead for one locale — and if a second language is ever needed, it is a small
addition (swap the catalog for a keyed lookup) rather than a rewrite.

Consequences:

- Components import from `messages.ts`; no inline user-facing strings.
- Adding a second locale = a second keyed catalog, not a framework migration.

## DEC-046 - Canonical Task Uniqueness, Idempotent Upserts, and "Last Synced" updated_at

Decision (2026-06-28): canonical `tasks` enforce identity with a **partial
unique index** `uq_tasks_workspace_provider_external_id` over
(`workspace_id`, `source_provider`, `external_id`) scoped to
`external_id IS NOT NULL` (manual/internal NULL-external_id tasks are exempt).
GitHub normalization upserts `Task`/`PullRequest`/`SourceRecord`/`Repository`
with PostgreSQL `INSERT ... ON CONFLICT DO UPDATE` so re-syncs are idempotent.
`Task.updated_at` is a **"last synced" marker** — bumped on every sync write —
while user-facing recency comes from `source_updated_at`.

Rationale: re-running a sync was creating duplicate `Task` rows. A DB-enforced
identity plus race-safe `ON CONFLICT` upsert makes the spine idempotent under
retries/concurrency. `updated_at` is bumped unconditionally because the sync
cannot cheaply diff a record for "did anything change" — the source payload is
stored in a JSON column, and JSON has no Postgres equality operator to gate the
write on — so `updated_at` reflects sync activity, not content change, and is
only a secondary `ORDER BY` tiebreak.

Consequences:

- Duplicate provider-keyed task rows are deleted in migration `f7b8c9d0e1a2`
  (irreversible DELETE) before the unique index is created.
- Repository idempotency additionally uses app-level cross-path dedup
  (external_id then full_name) ahead of the race-safe `ON CONFLICT` insert.
  Known debt: the full_name path is a SELECT, not a DB constraint (the unique
  constraint is only on `workspace_id`+`external_id`), so a different
  `external_id` with the same `full_name` could still duplicate under
  concurrency. Tracked in `docs/TODO.md`; the durable fix is a DB-level guard.
- Do not treat `Task.updated_at` as a content-change timestamp; use
  `source_updated_at` for user-facing recency.

## DEC-047 - Dedicated Secret-Encryption Key Required Outside Local

Decision (2026-06-28): connector-token encryption requires a dedicated
`FOUNDEROS_SECRET_ENCRYPTION_KEY` whenever `APP_ENV` is non-local. Outside
local/dev, if the dedicated key is unset the backend **fails closed** rather
than reusing the API auth key as encryption material. Local/dev may fall back to
the API auth key as a convenience; if even that is absent it still errors.

Rationale: reusing the API auth key as encryption material couples two
unrelated secrets — rotating the auth key would silently invalidate stored
tokens, and one leaked value would compromise both. A dedicated key with a loud
non-local failure is the smallest durable guardrail. This mirrors the
fail-closed auth posture of DEC-040.

Consequences:

- Non-local deploys must set `FOUNDEROS_SECRET_ENCRYPTION_KEY` or refuse to
  decrypt/encrypt tokens.
- Rotating the key invalidates previously stored encrypted tokens (documented in
  `.env.example`).
- The public health endpoint was also split this phase: `GET /health` returns a
  minimal no-auth liveness probe, while env/feature-flag detail moved to
  `GET /health/detail` behind the operator key.

## DEC-048 - Founder Briefings Are Persisted; Generation Stays Deterministic (Chunk 1)

Decision (2026-06-29): the Founder Briefing becomes durable. The deterministic,
LLM-free generator (`founder_briefing_service.generate_manual_founder_briefing`)
is unchanged; a new persistence layer SAVES its output as `Briefing` +
`BriefingItem` rows so the founder has history. `POST .../briefings/manual` now
runs generation, persists, and returns the saved briefing (with `id`,
`persistence:"persisted"`); `GET .../briefings` and `GET .../briefings/{id}`
read history. The LLM-generated narrative is a later chunk (Chunk 2).

Rationale: persistence and generation are separable. Saving first — without
touching generation and without adding an LLM — gives revisitable history now
and a stable store to layer LLM generation onto later, keeping `generated_by`
(`deterministic_v0`) as the discriminator for which generator produced a row.

Consequences:

- `Briefing` is workspace-scoped (FK `ON DELETE CASCADE`); `BriefingItem` is
  ordered by `position` and mirrors the generator's item shape verbatim
  (category/title/summary/severity/confidence/recommended_next_step/
  evidence_refs/related_entities/warnings) so a persisted briefing re-renders
  identically. `created_by_user_id` is nullable (`ON DELETE SET NULL`).
- Migration `e7f8a9b0c1d2` was the then-new single head for Briefings Chunk 1;
  later heads are tracked by newer decisions.
- Read endpoints are workspace-scoped: a briefing is fetched only within its
  workspace, so a valid id from another workspace is a 404 — isolation is a query
  predicate, not an assumption.
- The response `persistence` marker moved from `"transient"` to `"persisted"`;
  callers/tests that asserted the transient value were updated.
- No LLM and no GitHub OAuth/connect were added in this chunk.
- Known follow-up: Chunk 2 adds LLM narrative generation on top of this store,
  still strict-JSON-validated and evidence-backed per the LLM boundary rules.

## DEC-049 - Active Docs Stay Lean; Broken Operator Artifacts Are Removed

Decision (2026-06-29): the active documentation set remains the small canonical
set navigated by `docs/README.md`, and `docs/TODO.md` is a near-term backlog
rather than a long completed-work ledger. Completed-work detail lives in
`PROGRESS.md`, `docs/CHANGELOG.md`, and git history. Future agents must update
source-of-truth docs in the same task as behavior changes and must not paste
secrets, raw provider payloads, production smoke outputs, or private source
bodies into docs.

The cleanup also removes obsolete grouped-lifecycle operator scripts that were
not referenced by the active product path and failed import because their
required report module had already been removed. These scripts belonged to an
operator workflow outside the retained GitHub-first spine.

Rationale: stale task ledgers and broken operator artifacts make the repository
harder for humans and agents to understand. The project should bias toward fewer
accurate docs and runnable scripts, preserving uncertain or historical material
only when it is still useful or explicitly audit-only.

Consequences:

- `docs/README.md` now includes the source-of-truth matrix and documentation
  maintenance rules. `AGENTS.md` mirrors the agent-facing subset.
- `docs/TODO.md` is concise and points next work at GitHub product connect/live
  sync before LLM briefing narrative, because an empty workspace gives the LLM
  little real evidence to summarize.
- Removed scripts are recoverable from git history if a future scoped task
  deliberately revives that operator workflow.
- Generated/cache/build outputs stay ignored; real secrets and source-of-truth
  raw storage remain untouched.

## DEC-050 - GitHub Repository Identity Uses Workspace/Provider/Full Name Guard

Decision (2026-06-30): canonical GitHub repository identity is protected by two
workspace-scoped database identities:

1. `(workspace_id, external_id)` remains the stable provider-object identity
   when GitHub numeric ids are known.
2. `(workspace_id, provider, full_name)` is a second unique guard for the
   repository's GitHub `owner/repo` full name, so work-item sync paths that first
   know only `full_name` converge with later repository sync paths that know the
   stable GitHub id.

The normalization upsert now inserts with `ON CONFLICT DO NOTHING` without an
explicit conflict target, letting either unique guard catch a concurrent insert.
On conflict it reads the existing row by either identity and updates it in place.
If a stable GitHub id is already known, later work-item paths must not downgrade
`external_id` back to `full_name`.

Rationale: before GitHub product connect/live sync, repository identity must be
race-safe at the database layer. The prior app-level fallback lookup by
`full_name` was enough for sequential selected-sync paths but could race when
polling/webhooks or multiple live sync paths observe the same repository through
different identities.

Consequences:

- Migration `e8f9a0b1c2d3` de-duplicates existing duplicate repository rows by
  `(workspace_id, provider, full_name)`, preferring rows with stable external ids,
  re-points `pull_requests.repository_id` to the keeper, deletes loser rows, and
  adds `uq_repositories_workspace_provider_full_name`.
- The Alembic head moves from `e7f8a9b0c1d2` to `e8f9a0b1c2d3`.
- Same `full_name` remains allowed across different workspaces; workspace scope
  is part of both identities.
- This closes the known Repository cross-path dedupe race that blocked safe
  concurrent GitHub live sync work. GitHub App/product connect design remains
  the next product step.

## DEC-051 - Local GitHub Repository Surface Boots From `.local/repos.json`

Decision (2026-06-30): before GitHub App product connect is implemented, the
local GitHub repository surface can be bootstrapped from `.local/repos.json`.
Repo audit and repository inventory now treat that file as a valid offline
GitHub discovery snapshot when no canonical
`.local/discovery/github/<snapshot>/raw/repos.json` snapshot exists. The
canonical discovery layout remains preferred when present.

The helper `scripts/prepare_github_local_snapshot.py` normalizes the root local
repo list into the canonical discovery layout and writes a safe local repository
env snippet (`.local/github-repositories.env`) with repo allowlists only. It does
not call GitHub, does not handle tokens, and refuses sensitive-looking keys in
input JSON.

Rationale: the founder already has a local repository surface at
`.local/repos.json`. Supporting it directly lets GitHub dashboard/repo-audit
surfaces show real repository context immediately, while keeping product GitHub
connect/live sync as a separate GitHub App installation path.

Consequences:

- `.local/repos.json` is treated as local, offline evidence only; it is not a
  provider credential source and is not committed.
- The generated `.local/discovery/github/<snapshot>/raw/repos.json` and
  `.local/github-repositories.env` are local ignored artifacts.
- Repository allowlist snippets contain repo names only. Provider writes remain
  disabled by default; write allowlists still require explicit human approval.
- GitHub App product connect/live sync remains the next product slice.

## DEC-052 - GitHub Product Connect Uses GitHub App Installation

Decision (2026-07-01): the product GitHub connect path uses a GitHub App
installation, not user OAuth/PAT as the primary product path. The existing
manual provider-token bridge remains an operator/admin bridge for controlled
tests; it is not the browser product onboarding model.

The foundation records a workspace-scoped GitHub App installation in
`IntegrationConnection` using `provider_metadata.connection_method =
"github_app_installation"`. The installation id is carried in metadata and in a
non-secret external account key (`github_app_installation:<installation_id>`).
An installation may not be bound to a different workspace through the service.

Token and secret model:

- GitHub App private key and webhook secret are backend-only env/config values.
  They are exposed to status payloads only as configured/missing booleans and
  safe setup/callback URLs.
- Short-lived installation access tokens should be minted just-in-time for
  provider reads and are not persisted in `IntegrationConnection`.
- The app-installation connection endpoint records connection state only; it
  does not call GitHub, start sync, persist installation tokens, or perform
  provider writes.
- Provider writes remain disabled by default and require the existing separate
  approval/write path and explicit allowlists.

Rationale: a GitHub App installation gives founderOS the right future unit of
workspace-scoped repository access, supports selected-repository permissions,
and avoids browser-shipped tokens/PATs. Keeping installation tokens ephemeral
matches the existing secret-encryption posture and reduces stored credential
surface.

Consequences:

- GitHub connection status now includes a redacted GitHub App config block:
  configured/missing env names, setup/callback URLs, webhook/private-key boolean
  readiness, and explicit `installation_tokens_persisted: false`.
- `/api/v1/workspaces/{workspace_id}/github/connections/app-installation`
  records/updates an installation connection for admins without provider calls.
- `/github` now shows GitHub App readiness, repository-surface count, no
  persisted installation tokens, and external writes disabled.
- The next slice is live read sync using just-in-time installation tokens,
  strict repository scope, and the existing idempotent normalization/upsert path.

## DEC-053 - GitHub App Live Read Sync Starts Polling-Only and Explicitly Scoped

Decision (2026-07-01): the first GitHub App live read sync is an explicit,
admin-triggered polling/read endpoint, not webhook-driven automation. The
endpoint requires an existing workspace-scoped GitHub App installation
connection and an explicit list of repository `owner/repo` names. It mints a
short-lived installation access token just-in-time, reads only installation
repositories/issues/PRs for the requested repositories, and persists through the
existing idempotent GitHub normalization/upsert path. The installation token is
not persisted.

Webhooks are intentionally deferred from this v0. Rationale: a safe webhook path
needs raw-body signature verification, delivery dedupe/replay handling, event
type filtering, retry semantics, and observability. The polling-only endpoint
gets real GitHub data flowing while keeping execution human/admin triggered,
repository-scoped, and easier to test without provider calls in CI.

Consequences:

- `POST .../github/connections/app-installation/sync` performs read-only live
  sync for explicit repositories and returns `external_write_performed: false`.
- The endpoint does not sync all organization repositories by default; requested
  repositories must also be visible to the installation.
- Provider writes remain outside this path. Action execution still requires the
  existing separate approval/write controls and allowlists.
- A future webhook slice must add raw-body signature verification and delivery
  dedupe before any webhook payload mutates local canonical state.

## DEC-054 - First GitHub App Real Read Run Is Gated By An Offline Readiness Preflight

Decision (2026-07-03): the first approved GitHub App real-provider read run is
gated by a deterministic, offline readiness check before any provider call. A
pure function `github_app_real_read_run_readiness()` composes the existing
`github_app_config_status()` env-presence check with the recorded
installation-connection state and the already-loaded local repository surface,
and returns a status (`ready`/`blocked`), a concrete blocker list, and the exact
next human step. A companion CLI, `scripts/github_app_real_read_run_preflight.py`,
and the runbook `docs/deploy/github-app-first-real-read-run.md` let a human
confirm the run is executable and then perform it manually.

Rationale: the authoritative MVP milestone
(`founderOS_MASTER_PLAYBOOK.md` §1.4) is real GitHub data flowing end-to-end, and
ROADMAP Phases 2/3/4 all name this same next step. The run itself is externally
gated on GitHub App credentials and network that are not present in every
environment, so the aligned, verifiable work is a safe readiness gate rather than
more fixture-only dashboard polish (which Phase 5 explicitly warns against).

Consequences:

- The readiness function and preflight perform no provider calls, open no
  network connection, and never emit secret values — only presence booleans,
  blocker codes, and the next step.
- The real read run remains the existing human-approved, repository-scoped
  `POST .../github/connections/app-installation/sync` (DEC-053); this decision
  adds a gate, not a new write or automation path.
- Provider writes, auto-deploy, and LLM remain out of scope for this path.

Superseded (2026-07-30) by DEC-114: the env-presence function and companion CLI
were removed. Current readiness is verified against the managed workspace
credential and installation state inside the product.

## DEC-055 - Teammate Provisioning Uses Local One-Time Setup Links

Decision (2026-07-03, hardened 2026-07-13): the first
teammate-provisioning slice creates and lists local workspace memberships only.
Workspace owners/admins may create a local
`User` row and `Membership` row through `POST
/api/v1/workspaces/{workspace_id}/members` with role `admin`, `member`, or
`viewer`; listing is available through `GET
/api/v1/workspaces/{workspace_id}/members`. The endpoint does not send email,
does not call an identity provider, does not create external accounts, and does
not grant `owner` (owner remains bootstrap-only).

Rationale: the MVP needs multi-user/team readiness, but email invites,
password-reset flows, SSO, and external identity-provider writes are bigger
security/product slices. A local membership foundation lets the product
represent teammates and enforce workspace role gates without adding external
writes or new migrations.

Consequences:

- Provisioning returns `external_invite_sent: false` and
  `provider_write_performed: false` explicitly.
- Provisioning does not accept `initial_password`; the request model rejects it.
  An inviter therefore cannot choose, establish, or overwrite another user's
  credential.
- Provisioning a brand-new local user always creates a one-time setup link. The
  `account_setup_tokens` table stores only `sha256(raw_token)`, purpose,
  expiration, and consumed timestamp; the raw token is returned once in the API
  response as a fragment-only `/setup-password#token=...` path and is never
  persisted or sent in the initial HTTP request. The browser clears it after
  capture. The public setup endpoint locks the token and user, hashes only after
  validation, consumes exactly once, creates exactly one teammate browser
  session under concurrent submission, and rejects invalid/reused/expired
  tokens generically. The default lifetime is seven days.
- No email or provider write is performed, and this slice does not verify the
  recipient. The response exposes the setup link to the inviter exactly once for
  manual transfer over a trusted direct channel; both parties must treat it like
  a credential. Automated secure delivery remains deferred.
- An existing active account with no membership may be attached without
  changing its password and without minting a setup link. If the account already
  has a membership in any other workspace, provisioning returns 409
  (`existing account must accept a workspace invitation`) and creates no new
  membership. Cross-workspace attachment therefore cannot happen silently; a
  future self-accepted invitation flow owns that case.
- Duplicate memberships are rejected, disabled users cannot be provisioned, and
  viewers/members cannot provision others because the endpoint requires admin
  workspace role.
- Email delivery, self-accepted cross-workspace invitations, password-reset
  email delivery, and SSO remain later slices.

## DEC-056 - Connector Framework Registry Is The MVP Connector Spine

Decision (2026-07-06): FounderOS now has a deterministic connector framework
registry as the canonical product spine for MVP connectors. The static connector
catalog lives in `app/connectors/registry.py`, the workspace read model lives in
`app/services/connector_registry_service.py`, and the product surface is
`GET /api/v1/workspaces/{workspace_id}/connectors` plus the `/connectors`
frontend page. It exposes the MVP provider set (`github`, `jira`, `gmail`,
`drive`) and reads existing `integration_connections` status/counts plus static
connector descriptors only.

Rationale: `founderOS_MASTER_PLAYBOOK.md` requires a connector framework plus
minimal GitHub/Jira/Gmail/Drive connector coverage. `app/connectors/` was empty
while provider constants already existed in the database model, so the safest
next step is a single read-only registry surface that GitHub and future
Jira/Gmail/Drive implementations plug into rather than a new parallel connector
architecture.

Consequences:

- The registry is read-only: it performs no provider calls, starts no sync,
  makes no external writes, runs no LLM, and does not read or emit encrypted
  token fields.
- At introduction, GitHub is marked `available` with `/github` as its manage
  path; Jira, Gmail, and Google Drive are marked `planned` but explicitly in MVP
  scope. DEC-057/058/059 later make Jira/Gmail/Drive locally available.
- Future connector implementations should extend this registry and keep
  workspace-scoped status visible on `/connectors`.


## DEC-057 - Jira Connector Starts As Local Read-Only Issue Import

Decision (2026-07-06): the first non-GitHub connector implementation is a
local-only Jira issue import and read surface. The backend exposes `GET
/api/v1/workspaces/{workspace_id}/jira/issues` and admin-only `POST
/api/v1/workspaces/{workspace_id}/jira/issues/import`; the frontend adds `/jira`
and the connector registry now marks Jira `available` with `/jira` as its manage
path. The import accepts a pasted/exported JSON array (or object with
`issues`) and persists a sanitized normalized projection into canonical
`SourceRecord(provider='jira', record_type='issue')` and
`Task(source_provider='jira')` rows using idempotent upserts.

Rationale: GitHub real-provider reads remain externally blocked by missing
GitHub App credentials/installation, while the MVP playbook requires minimal
Jira/Gmail/Drive connector coverage. A local Jira import slice advances the
connector framework without introducing OAuth, API-token handling, live provider
reads, provider writes, or LLM behavior. It also reuses the canonical
SourceRecord/Task spine instead of creating a parallel Jira data model.

Consequences:

- Jira import is local DB-only: it performs no Jira API calls, starts no sync,
  makes no external writes, invokes no LLM, and does not read or emit encrypted
  token fields.
- Imported issue entries must include a valid Jira key such as `FOS-123`; invalid
  entries are reported as per-entry failures while valid entries can still be
  imported.
- Persisted source payloads are normalized and sanitized: secret-like keys are
  dropped, evidence refs are always present (provided or synthesized from the
  Jira key/source URL), and raw provider credentials are not stored.
- The import endpoint requires owner/admin workspace role; listing local Jira
  issues is available to workspace members with normal workspace access.
- Live Jira OAuth/API-token connection, background sync, webhooks, Jira writes,
  and Company Brain aggregation across Jira/Gmail/Drive remain later slices.

## DEC-058 - Gmail Connector Starts As Local Read-Only Message Import

Decision (2026-07-06): the second non-GitHub connector implementation is a
local-only Gmail message import and read surface, mirroring the DEC-057 Jira
slice. The backend exposes `GET
/api/v1/workspaces/{workspace_id}/gmail/messages` and admin-only `POST
/api/v1/workspaces/{workspace_id}/gmail/messages/import`; the frontend adds
`/gmail` and the connector registry now marks Gmail `available` with `/gmail` as
its manage path. The import accepts a pasted/exported JSON array (or object with
`messages`) and persists a sanitized normalized projection into canonical
`SourceRecord(provider='gmail', record_type='message')` rows using idempotent
upserts.

Rationale: GitHub real-provider reads remain externally blocked by missing
GitHub App credentials/installation, while the MVP playbook (§1.5) requires
minimal Jira/Gmail/Drive connector coverage. Extending the connector framework
with Gmail after Jira advances MVP scope without introducing OAuth, API-token
handling, live provider reads, provider writes, or LLM behavior, and it proves
the framework generalizes beyond task-shaped providers.

Consequences:

- Gmail import is local DB-only: it performs no Gmail API calls, starts no sync,
  makes no external writes, invokes no LLM, and does not read or emit encrypted
  token fields.
- Gmail messages are not tasks, so they persist to `SourceRecord` only (no
  `Task` row), unlike the Jira slice. This keeps the canonical `Task` table
  provider-scoped to `github`/`jira`/`internal`.
- Raw email bodies are intentionally not persisted; only a narrow evidence-
  backed projection (subject, participants, labels, dates, and a bounded
  provider-supplied snippet) is stored. Secret-like keys are dropped and
  evidence refs are always present (provided or synthesized from the message
  id/source URL).
- Imported message entries must include a message id; invalid entries are
  reported as per-entry failures while valid entries can still be imported.
- The import endpoint requires owner/admin workspace role; listing local Gmail
  messages is available to workspace members with normal workspace access.
- Live Gmail OAuth/API-token connection, background sync, thread aggregation,
  Gmail writes, and Company Brain aggregation across Jira/Gmail/Drive remain
  later slices.

## DEC-059 - Google Drive Connector Starts As Local Read-Only File Metadata Import

Decision (2026-07-06): the third non-GitHub connector implementation is a
local-only Google Drive file metadata import and read surface, completing the
MVP connector-set local surfaces started by DEC-056/057/058. The backend exposes
`GET /api/v1/workspaces/{workspace_id}/drive/files` and admin-only `POST
/api/v1/workspaces/{workspace_id}/drive/files/import`; the frontend adds
`/drive` and the connector registry now marks Google Drive `available` with
`/drive` as its manage path. The import accepts a pasted/exported JSON array (or
object with `files`) and persists a sanitized normalized metadata projection into
canonical `SourceRecord(provider='drive', record_type='file')` rows using
idempotent upserts.

Rationale: GitHub real-provider reads remain externally blocked by missing
GitHub App credentials/installation, while the MVP playbook (§1.5) requires
minimal Jira/Gmail/Drive connector coverage. Adding Drive after Jira and Gmail
closes the MVP provider registry's local product surface without introducing
OAuth, API-token handling, live provider reads, provider writes, or LLM behavior.

Consequences:

- Drive import is local DB-only: it performs no Google Drive API calls, starts no
  sync, makes no external writes, invokes no LLM, and does not read or emit
  encrypted token fields.
- Drive files are not tasks, so they persist to `SourceRecord` only (no `Task`
  row), like Gmail and unlike Jira.
- Raw document bodies/content are intentionally not persisted; only a narrow
  evidence-backed metadata projection (name, MIME type, owners, folder/path,
  sharing flag, modified timestamp, source URL) is stored. Secret-like keys are
  dropped and evidence refs are always present (provided or synthesized from the
  file id/source URL).
- Imported file entries must include a file id; invalid entries are reported as
  per-entry failures while valid entries can still be imported.
- The import endpoint requires owner/admin workspace role; listing local Drive
  files is available to workspace members with normal workspace access.
- Live Google Drive OAuth/API-token connection, background sync, document body
  extraction, Drive writes, and Company Brain aggregation across Jira/Gmail/Drive
  remain later slices.

## DEC-060 - Company Brain Exposes Local Connector SourceRecord Coverage

Decision (2026-07-06): the workspace Company Brain read model now includes an
additive `source_records` coverage block that summarizes all canonical
`SourceRecord` rows for the workspace across providers and record types. The
existing GitHub-first fields (`summary`, `repositories`, `work`, `evidence`)
remain unchanged, while `source_records.total`, `source_records.by_provider`,
and `source_records.by_record_type` make local Jira/Gmail/Drive connector
imports visible in founder-facing dashboard coverage.

Rationale: DEC-057/058/059 added local-only Jira/Gmail/Drive connector import
surfaces, but those records were not visible in Company Brain/Dashboard coverage
unless they were GitHub-shaped repositories/issues/PRs. A compact SourceRecord
coverage summary advances MVP visibility without pretending Gmail messages or
Drive files are tasks, without changing the canonical `Task` table, and without
adding provider calls, sync, writes, or LLM behavior.

Consequences:

- The `source_records` block is aggregate-only: it exposes counts by provider
  and record type, not raw source payloads, snippets, email bodies, document
  contents, secrets, tokens, or provider responses.
- The existing GitHub-first Company Brain work/repository/evidence contract
  remains backward-compatible for current consumers.
- Dashboard Source Coverage now renders SourceRecord totals and provider/type
  breakdowns from the already-loaded Company Brain payload. It still performs no
  provider calls, starts no sync, makes no external writes, and invokes no LLM.
- Full entity normalization and richer Company Brain semantics for Jira/Gmail/
  Drive remain later slices; this decision is a visibility bridge, not a full
  cross-provider reasoning model.

## DEC-061 - Founder Briefing Surfaces Connector SourceRecord Coverage

Decision (2026-07-06): the deterministic Founder Briefing now includes a
`connector-source-coverage` item derived from the additive Company Brain
`source_records` aggregate (DEC-060). It summarizes local canonical
`SourceRecord` coverage across GitHub/Jira/Gmail/Drive (total, by provider, by
record type) so imported Jira/Gmail/Drive records are visible in the primary
founder-facing briefing flow, not only on the dashboard coverage panel. The
briefing now fetches Company Brain once per generation and feeds both the
existing GitHub-first `source-coverage` item and the new connector item.

Rationale: DEC-057/058/059 added local connector imports and DEC-060 surfaced
their aggregate on the dashboard, but a founder generating a briefing still saw
only GitHub-shaped coverage, leaving non-GitHub connector data invisible in the
briefing itself. Adding a deterministic connector-coverage item advances MVP
founder-facing visibility without provider calls, sync, external writes, or LLM.

Consequences:

- The item is aggregate-only: it reports counts by provider and record type, not
  raw source payloads, snippets, email bodies, document contents, secrets, or
  provider responses.
- When no connector SourceRecord rows exist, the item is a `next_step` with a
  "connector source coverage empty" warning; otherwise it is a `status` item
  with evidence refs keyed on `provider:count`.
- Company Brain is now queried once per briefing generation and shared between
  the GitHub-first coverage item and the connector item, avoiding a duplicate
  read; the existing briefing item ids/shape remain backward-compatible and the
  new item is additive.
- Full cross-provider normalization into Company Brain work items and richer
  briefing narrative remain later slices; this is a deterministic visibility
  bridge, not an LLM briefing pipeline. DEC-062 later promotes the task-shaped
  Jira subset into Company Brain work items.

## DEC-062 - Company Brain Promotes Local Jira Issues Into Work Items

Decision (2026-07-06): workspace Company Brain now treats local canonical Jira
`Task(source_provider='jira')` rows as first-class issue work items. Jira issues
appear in `work.issues`, `work.recent`, source evidence, and open/closed issue
summary counts alongside GitHub issues. The response adds optional
`source_provider` and `project_key` fields on work items so the UI can render
Jira project scope without pretending the item belongs to a GitHub repository.

Rationale: DEC-057 made Jira issue import write canonical `Task` rows, while
DEC-060/061 exposed non-GitHub records only as aggregate SourceRecord coverage.
Jira issues are task-shaped and already satisfy the canonical Task contract, so
promoting them into Company Brain work items advances the MVP goal of seeing
work from multiple connectors in one founder-facing view. Gmail messages and
Drive files are not task-shaped, so they remain SourceRecord coverage until a
separate first-class model is introduced.

Consequences:

- Jira work-item promotion is local/deterministic only: no Jira provider calls,
  sync, external writes, LLM, raw payload rendering, or secret reads are added.
- GitHub issue semantics remain stable: only GitHub tasks with status `open`
  count as open, while closed GitHub tasks count as closed. Jira tasks count as
  closed/done when their metadata `status_category` is `done` (or status is
  closed/done/resolved); otherwise they are visible as open work.
- Company Brain `work.issues` can now contain both GitHub and Jira rows. Current
  UI labels each work item with provider and scope (`repository_full_name` for
  GitHub, `project_key` for Jira).
- Gmail and Drive first-class entity/read models remain later slices; they must
  not be forced into `Task` or work-item semantics without an explicit model
  decision.

## DEC-063 - Company Brain Exposes Gmail Messages And Drive Files As First-Class Read Sections

Decision (2026-07-06): workspace Company Brain now exposes local Gmail message
and Google Drive file records as first-class read sections without coercing them
into tasks. Gmail `SourceRecord(provider='gmail', record_type='message')` rows
appear under `communications.messages`; Drive
`SourceRecord(provider='drive', record_type='file')` rows appear under
`documents.files`. Both sections are built only from the sanitized normalized
payloads already stored by DEC-058/059 and include source refs/evidence.

Rationale: DEC-060/061 made Gmail/Drive visible as aggregate SourceRecord
coverage, while DEC-062 promoted only Jira because Jira issues are task-shaped.
Gmail messages and Drive files are not tasks, but they still need first-class
founder-facing read models to satisfy the MVP direction of seeing emails and
documents in one Company Brain surface. Separate `communications` and
`documents` sections preserve semantics without polluting `Task`.

Consequences:

- This is local/deterministic only: no Gmail/Drive provider calls, sync, external
  writes, LLM, raw body/content rendering, or secret reads are added.
- Raw email bodies and Drive document contents remain excluded. The read model
  renders bounded normalized fields such as subject/snippet, sender/labels,
  file name/MIME type/owners/shared flag, source URL, and source refs.
- Company Brain can now contain GitHub/Jira work items plus Gmail messages and
  Drive files in separate typed sections. Existing GitHub/Jira work contracts are
  kept backward-compatible, with `communications` and `documents` additive.
- Future work can enrich these sections into richer thread/document entities,
  but such enrichment needs separate model decisions and evidence contracts.

## DEC-064 - Founder Briefing Summarizes Local Jira, Gmail, And Drive Read Models

Decision (2026-07-06): the deterministic Founder Briefing now adds first-class
local connector items from the Company Brain read model: `jira-work-items` for
Jira issue-shaped work, `gmail-message-signals` for Gmail messages, and
`drive-file-signals` for Drive file metadata. These items are additive to the
existing GitHub-first and connector coverage items, and are generated only from
already-normalized local Company Brain sections (`work.issues`,
`communications.messages`, and `documents.files`) plus their source refs.

Rationale: DEC-062/063 made Jira/Gmail/Drive visible in Company Brain, but the
Founder Briefing still only surfaced non-GitHub data as aggregate SourceRecord
coverage. The briefing should guide founder review from the first-class local
read models without waiting for the LLM narrative pipeline or real provider
reads.

Consequences:

- This remains local/deterministic only: no Jira/Gmail/Drive provider calls,
  sync, external writes, secret reads, raw payload rendering, or LLM are added.
- Jira issues are summarized as work because they already live in canonical
  `Task(source_provider='jira')`; Gmail messages and Drive files remain separate
  communication/document read models and are not coerced into tasks.
- Each item carries evidence refs converted from Company Brain `source_refs`;
  if refs are missing, the item is still emitted with an explicit warning so the
  absence is visible before anyone creates a local follow-up action.
- Briefing summaries use bounded normalized fields (issue key/title, message
  subject, file name, counts) and intentionally ignore raw email bodies,
  snippets-as-body, document content, provider payload dumps, and secret-like
  data.
- Counts are truthful under truncation: Company Brain `work`/`communications`/
  `documents` sections are capped to a display limit, so the imported total is
  taken from the unlimited `source_records.by_provider` aggregate (DEC-060) and
  reported as "N shown of M imported". Visible-only signals (unread/shared) are
  explicitly scoped with "in view" so a truncated slice never implies a false
  workspace-wide total.

## DEC-065 - Persisted Briefings Can Generate Local Non-GitHub Action Proposals

Decision (2026-07-06): persisted Founder Briefings now have a local-only action
proposal generation endpoint:
`POST /api/v1/workspaces/{workspace_id}/briefings/{briefing_id}/action-proposals`.
The endpoint creates local `ActionProposal(target_provider='internal',
action_type='internal_todo')` rows for the DEC-064 non-GitHub briefing items
(`jira-work-items`, `gmail-message-signals`, and `drive-file-signals`) when
those items have evidence refs. The Briefing UI exposes this as a bulk local
action generation control next to the existing per-item local action button.

Rationale: the MVP path requires a founder to go from Company Brain/Briefing
signals to human-reviewed action proposals. Before this decision, the UI could
manually create one local action per visible briefing item, but there was no
backend deterministic bridge from a saved briefing to evidence-backed local
proposals for the new Jira/Gmail/Drive read-model signals. A backend endpoint
makes the flow reproducible, testable, and workspace-scoped without waiting for
LLM generation or provider execution.

Consequences:

- Generation is local DB-only: it reads persisted `Briefing` / `BriefingItem`
  rows and writes only local `ActionProposal` rows. It performs no provider
  calls, starts no sync, makes no external writes, reads no secrets, and invokes
  no LLM.
- Items without `evidence_refs` are skipped with `missing_evidence_refs`; local
  proposals are created only from evidence-backed briefing items.
- Existing open actions for the same `briefing_id + briefing_item_key` are
  skipped with `open_action_exists`, including actions previously created by the
  older per-item UI path (`source='briefing_item'`). This prevents blind
  duplicates while allowing a rejected/failed action to be regenerated later.
- Generated proposals are `created_by='system'`, carry the persisted
  `briefing_item_id`, preserve the stable `briefing_item_key` in payload for UI
  cross-linking, and include only sanitized summary/category/severity/
  related-entity metadata plus copied evidence refs.
- The endpoint requires member-or-higher workspace role. Viewers can still read
  briefings but cannot create local proposals.

## DEC-066 - Internal Documents Are A First-Class Workspace Module

Decision (2026-07-06): the MVP "internal documents" module (playbook §1.5, flow
§4.7, model §6.16, endpoints §7.11) is implemented as its own canonical,
workspace-scoped ``documents`` table with member-gated CRUD, search, and Company
Brain integration. Unlike the read-only connector slices (Jira/Gmail/Drive) that
ingest external provider snapshots into ``SourceRecord``, an internal document is
authored inside founderOS, so it is a first-class internal entity rather than a
``SourceRecord`` projection.

Backend: ``app/db/document_models.py`` (``Document``), migration
``f1a2b3c4d5e6``, ``app/services/document_service.py`` (CRUD + deterministic
``markdown_to_text`` projection + search), and ``app/api/documents.py``
(``GET/POST /workspaces/{id}/documents``, ``GET/PATCH/DELETE
/workspaces/{id}/documents/{document_id}``). Company Brain now exposes
non-archived documents under ``documents.notes`` with internal-document source
refs that flow into the aggregate ``evidence`` list. Frontend: ``/documents``
page (list, search, create, detail) plus a sidebar entry.

Rationale: every other MVP §1.5 connector (GitHub/Jira/Gmail/Drive) already had
a local product surface, but internal documents — a required "must have" and the
subject of flow §4.7 — had no model, endpoint, or UI. Adding it advances the MVP
end state (see a document in one UI and in Company Brain) without provider calls,
external writes, or LLM.

Consequences:

- ``body_markdown`` is the authored source of truth; ``body_text`` is a
  deterministic offline markdown-strip used for search and Company Brain context.
  Both are stored (spec requires both). No renderer, network, or LLM is invoked.
- ``status`` is constrained to ``draft | published | archived``. Company Brain
  surfaces draft + published documents and excludes archived ones from the brain
  view; archived documents remain retrievable through the documents API.
- Create/update/delete require member-or-higher role; viewers get read-only
  list/detail. All access is workspace-scoped (cross-workspace ids 404).
- Tags are sanitized (trimmed, de-duplicated, capped); title is required and
  bounded; body size is bounded. Documents are additive: existing Company Brain
  consumers keep working because ``documents.notes`` is a new optional field
  alongside the existing ``documents.files``.
- ``DocumentVersion`` history and NormalizedEntity linkage (mentioned in §4.7)
  remain later slices; this decision delivers the CRUD + search + Brain surface
  the MVP acceptance criteria require ("Docs appear in Company Brain").

## DEC-067 - Founder Briefing Surfaces Internal Document Context

Decision (2026-07-06): the deterministic Founder Briefing now adds an
`internal-document-context` item when workspace Company Brain contains internal
documents under `documents.notes` (DEC-066). The item summarizes the visible
internal document context (count, top titles, statuses, tags) and carries
evidence refs converted from the Company Brain `source_refs` for those document
rows.

Rationale: DEC-066 made internal documents first-class and visible in Company
Brain, but the playbook Documents flow (§4.7) also says "Briefing can use
document as context." Adding a deterministic briefing item closes that local MVP
loop without waiting for an LLM narrative pipeline.

Consequences:

- The item reads only the already-normalized Company Brain `documents.notes`
  slice; it does not query raw `body_markdown`, call providers, start sync,
  create actions, read secrets, or invoke an LLM.
- The item does not copy raw markdown or body text into the briefing payload.
  It uses bounded normalized metadata (titles, statuses, tags) plus
  evidence refs; full document reading remains in `/documents` and Company
  Brain.
- If document source refs are missing, the item is emitted with an explicit
  warning so evidence gaps remain visible.
- The item is context, not a task/follow-up signal, so the DEC-065 bulk action
  generation whitelist remains limited to Jira/Gmail/Drive signal items.

## DEC-068 - Internal Documents Keep Local Version History

Decision (2026-07-07): internal Documents now append immutable local
``DocumentVersion`` snapshots on create and every successful update. The
workspace-scoped ``document_versions`` table (migration ``f2b3c4d5e6f7``)
stores version number, title, body markdown, deterministic body text, status,
tags, author, and created timestamp. The Documents API exposes read-only version
history at
``GET /api/v1/workspaces/{workspace_id}/documents/{document_id}/versions``, and
the ``/documents`` detail view displays a compact version list.

Rationale: the playbook Documents flow (§4.7) names ``DocumentVersion`` as part
of the document data path. DEC-066 intentionally deferred version history to
ship CRUD/search/Brain first; adding immutable snapshots now closes that
document-lineage gap while keeping the current editable ``Document`` row as the
source of truth.

Consequences:

- Version history is local DB-only: it does not call providers, does not perform
  external writes, reads no secrets, and invokes no LLM.
- Version 1 is written at document creation; version N+1 is written after each
  successful update. Versions are ordered newest-first by ``version_number`` in
  the read API.
- The latest ``Document`` row remains the editable canonical state. Versions are
  immutable snapshots for review/audit/history and are deleted by database
  cascade when the document or workspace is deleted.
- Viewers may read version history through the same workspace access boundary
  used for document detail, while create/update/delete remain member-gated.
- NormalizedEntity linkage remains a later slice; this decision only adds the
  first local document history layer required by §4.7.

## DEC-069 - Internal Document Context Can Generate Local Action Proposals

Decision (2026-07-07): the persisted Founder Briefing → local ActionProposal
bridge now treats `internal-document-context` as an actionable evidence-backed
briefing item, alongside the Jira/Gmail/Drive read-model signal items from
DEC-065. When the item has evidence refs, the existing
`POST /api/v1/workspaces/{workspace_id}/briefings/{briefing_id}/action-proposals`
endpoint may create a local `ActionProposal(target_provider='internal',
action_type='internal_todo')` for it. Duplicate detection remains scoped to the
same persisted briefing and briefing item key, so repeated generation skips an
existing open document-context action instead of creating blind duplicates.

Rationale: DEC-067 originally made internal documents briefing context only, but
after DEC-066/068 made documents editable, versioned, and visible in the product,
the founder still had no one-click way to route evidence-backed document context
into the existing local action review queue. Extending the existing deterministic
bridge closes that local MVP loop without adding a new action system or waiting
for an LLM narrative.

Consequences:

- This supersedes the DEC-067 consequence that the bulk action generation
  whitelist is limited to Jira/Gmail/Drive signal items.
- The generated proposal is local-only: no provider call, sync, external write,
  secret read, or LLM is started, and approval/execution remains in the existing
  local ActionProposal review flow.
- Missing evidence still skips the item. The action uses the persisted
  `BriefingItem.evidence_refs`; it does not copy raw document markdown/body text
  into the proposal.
- The proposal payload keeps the existing briefing-derived shape
  (`source='briefing_non_github_signal'`, `briefing_id`, `briefing_item_key`,
  category/severity/related_entities), so the current `/actions` review UI and
  duplicate handling continue to work.

## DEC-070 - Normalized Entities Ship As A Read-Only Canonical Projection

Decision (2026-07-07): the MVP "normalized entities" surface (§1.5, §6.9) is
delivered as a deterministic **read-only projection API** over the existing
canonical Company Brain rows, not as a new physical `NormalizedEntity` table.
A new service `app/services/company_brain_entities_read_service.py` reuses
`build_workspace_company_brain` and flattens repositories, issues, pull
requests, Gmail messages, Drive files, and internal documents into a single
`entities` list (each with `entity_type`, a stable `key`, `source_provider`,
`status`, `source_url`, `updated_at`, and evidence `source_refs`), plus a
`summary` counting by entity type and provider. It is exposed at
`GET /api/v1/workspaces/{workspace_id}/company-brain/entities`.

Rationale: DEC-028 deferred the physical `NormalizedEntity` table and said to
revisit "when the canonical `/api/v1/.../brain/entities` API is actually built".
That API is now the missing MVP acceptance surface ("See Company Brain
entities"), while the durable-table design is still blocked by ASK-1 (the
undefined `Person` entity and the "23 models" count). Projecting from
already-canonical rows delivers the required entity view now, keeps a single
source of truth, and stays fully reversible if/when a physical table is chosen.

Consequences:

- Read-only and local-only: no new table, no migration, no provider calls, no
  sync, no external writes, no secret reads, and no LLM. The projection inherits
  the Company Brain workspace scope, sanitized fields, and evidence refs, so raw
  provider payloads/bodies do not leak.
- The `Person` entity type (§6.9) is intentionally not produced (post-MVP,
  ASK-1). Entity `key`s are `"{provider}:{entity_type}:{external_id}"` and the
  `recent` work overlap is de-duplicated so each work item appears once.
- Because it is a projection, the entity list changes only when the underlying
  canonical rows change; there is no separate write path to keep in sync.
- The dashboard `NormalizedEntitiesPanel` is the first product surface over the
  endpoint, so the MVP "See Company Brain entities" path is reachable without
  terminal/API use.
- A future physical `NormalizedEntity` table (if ASK-1 is resolved) can replace
  the projection behind the same endpoint without breaking the response shape.

## DEC-071 - Company Brain Is A Dedicated Navigable View

Decision (2026-07-07): the MVP "Company Brain view" (§1.5) and the main-flow step
"See Company Brain entities" (§1.4) are delivered as a dedicated navigable
`/company-brain` page with its own sidebar entry, not only as panels embedded in
`/dashboard`. The page composes the existing read-only `CompanyBrainPanel` and
`NormalizedEntitiesPanel` (DEC-070) plus a manual refresh control; it introduces
no new data path.

Rationale: the playbook flow lists "See Company Brain entities" as a distinct
step and §1.5 lists "Company Brain view" separately from "Founder Dashboard",
while §1.1/§1.7 require a UI-first product (no mandatory terminal use). Company
Brain and normalized entities previously existed only as dashboard panels with
no direct route, so a founder could not navigate to a Company Brain view. Adding
a first-class route closes that acceptance-flow gap by reusing existing panels.

Consequences:

- Read-only and local-only: the page reuses the existing Company Brain and
  normalized-entities endpoints and starts no provider calls, sync, external
  writes, secret reads, or LLM.
- No duplication of rendering/data logic: the page mounts the existing panel
  components; the dashboard keeps its own panels for the at-a-glance view.
- `Sidebar` now exports `NAV_LINKS` so navigation is unit-testable; the nav order
  places Company Brain right after the dashboard.

## DEC-072 - Basic Logging Is Sanitized Request Logging

Decision (2026-07-07): the MVP "basic logging" requirement (§1.5) is delivered as
application-level request logging, not only as domain audit rows. `app/core/logging.py`
adds `configure_logging()` (an idempotent, level-configurable handler on a
dedicated `founderos` logger) and `RequestLoggingMiddleware`, an ASGI middleware
that logs one line per HTTP request. The level is env-driven via
`FOUNDEROS_LOG_LEVEL` / `LOG_LEVEL` (default `INFO`). `app/main.py` configures
logging at import and startup and installs the middleware.

Rationale: before this change the app had no `getLogger`/logging configuration
and no request logging at all; the only "logging" was persisted domain audit
trails (`AuditLog`, `ActionExecutionEvent`). §1.5 lists "basic logging" as a
distinct MVP must-have, and every local or future hosted runtime needs
operational request visibility. This closes that gap with a minimal, dependency-
free standard-library logger.

Consequences:

- Sanitization boundary (AGENTS.md / SECURITY_BASELINE.md): the request logger
  records only HTTP method, URL path, status code, and duration in ms. It never
  logs query-string values, headers, cookies, request/response bodies, tokens,
  API keys, or provider payloads, so no secret-bearing data can leak into logs.
- The `founderos` logger sets `propagate = False` and owns its handler, so
  configuration is deterministic across app startups and test runs and does not
  mutate the root logger. `configure_logging` is idempotent (no duplicate
  handlers) and falls back to `INFO` for unknown level names.
- This is local/in-process only: it adds no provider calls, external writes,
  secret reads, or LLM, and introduces no new dependency, table, or migration.

## DEC-073 - Company World Is An Evidence-Backed Operating Map

Decision (2026-07-13): founderOS presents the company as an operating strategy
surface, not as a flat collection of technical panels and not as artificial
gamification. `/dashboard` is the company command center (daily move, decisions,
company map, operational perimeter); `/company-brain` is the first-class
**Company World**. The new workspace-membership-gated endpoint (including the
read-only `viewer` role)
`GET /api/v1/workspaces/{workspace_id}/company-map` projects only existing
workspace memberships and sanitized Company Brain Gmail metadata into company,
internal-person, external-person-candidate, organization-candidate, and email
touchpoint read models with evidence refs and inspectable profiles.

Rationale: founders need to manage people, companies, relationships, signals,
and actions in one coherent mental model. Fake points, levels, customer labels,
or decision-maker claims would violate the evidence-first invariants. A bounded,
read-only projection makes the product useful now while preserving honest
uncertainty until durable identity and confirmation models are designed.

Consequences:

- Workspace members are confirmed internal people. External mailboxes are only
  contact candidates. Non-generic email domains are only organization
  candidates; they are never called customers or employers automatically. All
  candidates carry `needs_founder_confirm=true`.
- Email subjects, participants, timestamps, directions, source URLs, and source
  refs may appear in authenticated profiles; raw bodies and snippets do not.
  The existing RBAC meaning is preserved: every authenticated workspace role,
  including read-only `viewer`, may read workspace data; confirmation and
  future relationship writes require `member` or higher. Cross-workspace access
  remains hidden as 404.
- The Gmail projection is explicitly bounded to the newest 100 messages. The
  response exposes available/considered counts, limit, order, and `truncated`;
  external-person, organization, and touchpoint summary fields are named
  `*_in_window` and the UI renders the window and backend warnings.
- This slice is read-only and local-only: no new table or migration, provider
  call, sync, external write, secret read, or LLM. Its source is honestly named
  `workspace_and_company_brain_projection`, not a nonexistent canonical map.
- Primary navigation is grouped by command center, management, sources, and
  system. The global repository-audit overview is no longer mounted in the
  workspace dashboard because its scope does not match the workspace company
  map. The legacy `/audit` page is removed, and non-workspace filesystem
  Company Brain preview APIs require the operator API key; a browser session is
  explicitly rejected. Workspace product reads remain under workspace-scoped
  routes.
- The product purpose of `Person` is now resolved: founderOS needs durable
  internal/external profiles, organizations, affiliations, confirmation state,
  and interactions. The physical `Person`/`Organization`/`Affiliation`/
  `Interaction` schema and confirmation write flow remain a separate migration
  chunk and must preserve source provenance and workspace isolation.

## DEC-074 - Durable Company Profiles Use Explicit Human Resolution

Decision (2026-07-13): Company World gains a canonical, workspace-owned profile
layer with `Person`, `Organization`, `Affiliation`, and `Interaction` models,
plus a terminal `CompanyWorldResolution` receipt for candidate decisions.
The existing `Workspace` remains the founder's own company; an `Organization`
represents an external counterparty and does not duplicate workspace identity.

Identity and relationship rules:

- A `Person` has one normalized email identity inside a workspace and may link
  to one local `User`. Membership-backed people and founder-confirmed external
  people share the same model; `origin` records how the row first became
  canonical rather than declaring an immutable internal/external nature.
- An `Organization` has a workspace-unique canonical key and an optional
  normalized domain. Its relationship to the founder's company (`unknown`,
  `prospect`, `customer`, `partner`, `vendor`, or `other`) is always selected by
  a human; a mail domain alone never assigns it.
- An `Affiliation` is one active person-to-organization relationship in v1.
  `contact`, `employee`, `decision_maker`, `account_owner`, `advisor`, or
  `other` is founder-authored, never inferred by an LLM or provider metadata.
- `Interaction` is deliberately contact-centric: one sanitized row per
  `(workspace, source record, person)`, with an optional organization. One
  email with several participants therefore produces several linked rows
  without storing participant UUID arrays in JSON. Product timelines may group
  them by source record. Raw message bodies and snippets are not copied.
- `CompanyWorldResolution` records `confirmed` or `dismissed`, actor, time,
  candidate identity/version, request hash, idempotency key, primary source
  record, and resulting durable IDs. Decisions are terminal in v1; correction
  requires a later explicit audited flow rather than silent overwrite.
  The current service/API is insert-only; the database does not claim a general
  immutable-row mechanism for out-of-band SQL writers.
- Person and organization candidates are separate terminal decisions. Confirming
  a person never silently confirms an organization from the email domain. A
  corporate-domain person may be affiliated only after that organization was
  explicitly confirmed; a dismissed organization leaves the person standalone.

Tenant and evidence rules:

- Every profile row carries `workspace_id`. Composite foreign keys include the
  workspace so a person, organization, interaction, affiliation, source record,
  or resolution result from another tenant cannot be linked at database level.
- Membership-backed people and all confirming actors are bound to a membership
  in the same workspace. Founder confirmation provenance is mandatory, and
  durable resolution result IDs must describe one internally consistent
  person/organization/affiliation tuple.
- Confirmation is allowed to `owner`, `admin`, and `member`; `viewer` remains
  read-only. Non-members and cross-workspace candidates remain hidden as 404.
- The server re-resolves candidate identity and provenance from the current
  workspace projection. Client-supplied canonical email, domain, or evidence
  IDs are not accepted. Confirmation without a workspace-owned source record
  is rejected as insufficient evidence.
- Candidate versions cover visible identity/classification fields plus the
  payload hash of every source record in the displayed evidence snapshot. The
  server locks those records, re-resolves the candidate, and writes interactions
  only from that same snapshot; stale evidence fails closed.
- The generic `EvidenceRef.entity_id` is not reused for these four tables: it
  has neither entity type nor a foreign key. Provenance is instead explicit via
  source-record-backed interactions, affiliations, and resolution receipts.

Migration and backfill rules:

- The Alembic revision is schema-only. It never parses private payloads or
  performs a data backfill during deploy.
- Backfill is a separate deterministic command: aggregate-only dry-run by
  default, explicit apply, idempotent database constraints, no provider calls,
  no external writes, no LLM, and no raw-body output. It materializes current
  memberships and interactions only for already confirmed external profiles;
  projected candidates do not become canonical automatically.
- Confirmation writes only the confirmed newest-100 evidence snapshot. The
  explicit backfill may inspect all local Gmail `SourceRecord` metadata to add
  historical interactions for already confirmed people. Company World keeps
  the projection fallback during rollout.
- Confirmation and apply-backfill share a workspace-level transaction lock;
  candidate/idempotency constraints remain the durable replay boundary.
- Migration downgrade refuses to drop non-empty Company World tables. A backup
  and explicit data export/removal are required before a destructive rollback.
- Deferred nullable `Task.assignee_person_id` and
  `PullRequest.author_person_id` receive no foreign keys or backfill in this
  chunk. The deleted Lineage-2 `entities` graph remains deleted.

## DEC-075 - Guided Founder Enrollment Uses Real Readiness, Not An Admin Shell

Decision (2026-07-13): the normal private-beta founder path is invite-only
product enrollment, followed by a computed onboarding journey and a five-zone
company shell. The operator creates one short-lived URL; `/start` atomically
creates the active `User`, `Workspace`, owner `Membership`, and `UserSession`,
then opens `/onboarding`. Public signup remains closed.

Security and identity rules:

- `founder_enrollment_invites` stores only a SHA-256 token digest, expiry, and
  optional consumption/revocation receipts. Lifetime is limited to 1–168 hours
  (72 by default); a leaked or misdirected unconsumed invite can be revoked by
  its non-secret UUID with `scripts/revoke_founder_invite.py`. The raw token is
  shown once by `scripts/create_founder_invite.py` inside a URL fragment (never
  an HTTP query or request log) and must be handled like a credential. Remote
  origins require HTTPS; loopback HTTP remains available for local development.
- Consumption locks the invite row, rejects unknown/expired/used tokens with one
  generic response, checks normalized email/workspace-slug conflicts, performs
  Argon2 only after those cheap checks, and commits identity rows, consumption,
  and the browser session together. A failed or concurrent losing request leaves
  no partial founder or workspace.
- Teammate password setup follows the same fragment-only bearer rule at
  `/setup-password#token=...`; query-token fallback is forbidden and the browser
  clears the address immediately. Token and user rows are locked before Argon2,
  so concurrent/reused links create exactly one password/session and invalid
  public requests cannot amplify password-hash work. Public token/password
  lengths are capped. Per DEC-055, an inviter cannot set `initial_password`;
  every brand-new teammate receives one manual, unverified setup link that must
  travel over a trusted direct channel, while cross-workspace accounts fail with
  409 until a self-accepted invitation flow exists.
- Login admission caps per-IP and global request windows plus
  concurrent login work before Argon2. It complements the durable per-email DB
  lockout, whose stale rows are opportunistically deleted after 24 hours by
  failed-login recording. The admission controller is process-local and only
  satisfies the current single-Uvicorn-process loopback runtime. Before adding
  public workers or replicas, a shared edge/Redis limiter is required because
  process-local counters do not aggregate. The per-IP key is
  `request.client.host`; any future public proxy topology requires a new
  trusted-client-address verification before exposure.
- Password inputs are bounded before hashing: login accepts 1–256 characters;
  founder enrollment, teammate setup, and password change require 8–256.
- A disabled user cannot log in, and validation of an already-issued session for
  a now-disabled user persists revocation before returning unauthenticated.
- Login, teammate setup, and founder enrollment sanitize session User-Agent
  metadata to printable text and cap it at 512 characters.
- The former `scripts/create_admin_user.py` recovery path was removed by
  DEC-114. Founder creation uses the invite-only interface; email delivery,
  public registration, password reset, and SSO are not implied by this slice.
- An account with no workspace is routed to an honest recovery screen. With one
  workspace the context is unambiguous; with several, the user must choose one.
  A browser-persisted choice is accepted only while it still belongs to the
  current `/auth/me` membership list, and switching remounts workspace content.

Product and readiness rules:

- `/onboarding` is a focused journey: company, first source, first map, team,
  then start. A skipped step remains pending. There is no persisted decorative
  `onboarding_completed` flag. The active step lives in the URL hash; leaving for
  `/connectors` or `/settings` preserves continuity, and both destinations offer
  explicit return links to `#source` or `#team`.
- Source readiness requires actual canonical
  `CompanyBrain.source_records.total > 0`. A configured connection without
  loaded records is still pending. Company-map readiness comes from the
  evidence-backed workspace Company Map; team state comes from memberships.
  Failed reads are `unknown`, never silently converted into empty or complete.
- The primary navigation is «Сегодня / Компания / Решения / Источники /
  Настройки». GitHub, Jira, Gmail, and Drive remain real routes but are nested
  under «Источники» rather than competing as separate products. Desktop uses a
  compact rail; mobile uses a five-item bottom navigation.
- `/dashboard` is «Сегодня»: exactly one deterministic next move plus three
  secondary signals. Its priority is source gap, known pending decisions, known
  Company World candidates, incomplete reads, first briefing, team, then the
  latest briefing. UI controls mirror backend RBAC exactly: source
  setup/import/sync is owner/admin; briefing generation and local
  ActionProposal creation are member+; action review/approve/reject/preview/
  execute is owner/admin; Company World resolution is member+; viewer retains
  evidence-backed reads only.
- Technical capability boundaries remain inspectable but do not dominate the
  main task. This slice starts no provider call, provider write, external
  action, deploy, secret read, or LLM inference by itself. Existing
  human-triggered provider-read and approval-gated external-write paths remain
  explicit separate controls.

Consequence: UX-01 removes the first-founder terminal handoff after the operator
issues the link and replaces the dashboard panel wall with a guided operating
loop. UX-02 subsequently completes the spatial Company World frontend under
DEC-076. The next product boundary is release handoff and the human-gated deploy
path, not another local UX expansion.

## DEC-076 - Company World Board Draws Only Durable Relationships

Decision (2026-07-13): `/company-brain` presents the existing DEC-073/DEC-074
Company Map as a spatial operating board rather than stacked registries. The
founder's company is the center; workspace team, confirmed external network,
and unresolved discovery candidates occupy separate, plainly labelled
contours. This is a frontend projection over the existing response: it adds no
backend API, migration, provider call/write, external action, secret read, or
LLM path.

Relationship and placement rules:

- A confirmed external person is nested under a confirmed organization only
  when `organization_id` and `organization_key` both match that organization's
  durable identity and `relationship_type` is non-null. The relationship label
  therefore comes from a human-authored durable affiliation.
- Name/domain similarity and candidate organization keys never establish a
  confirmed relationship. A person without the exact durable affiliation stays
  standalone in the confirmed network; unresolved organizations and people
  stay in the discovery contour.
- Selecting a person or organization opens one focused, labelled inspector.
  Human-readable profile context comes first, profile-local touchpoints are
  matched only by exact durable keys, and evidence provenance is available in a
  collapsed disclosure.
- Technical capability, evidence-window, warning, and boundary details remain
  inspectable in a separate collapsed disclosure instead of dominating the
  primary company-management task.

Resolution and access rules:

- Candidate resolution asks one plain-language question at a time. The first
  question is the terminal decision; confirmation then asks only the labels and
  relationship/role fields permitted by the existing candidate type and
  confirmed-organization state.
- The final request preserves the existing DEC-074 contract: member+ may
  confirm/dismiss, viewer is read-only, candidate versions and idempotency keys
  remain mandatory, and canonical identity/evidence stays server-resolved. An
  unresolved organization cannot be silently converted into a person's
  confirmed affiliation.
- Board items use native buttons and expose selection state/controlled inspector
  relationships. The inspector is labelled and focusable; compact/mobile layout
  and reduced-motion preferences are first-class presentation constraints.

Consequence: the Company World interface can feel like a company strategy game
without inventing organizational facts or weakening provenance/RBAC. UX-02
local acceptance passed frontend/backend/static and desktop/mobile browser
gates. With UX-01 and UX-02 complete locally, DEC-077 defines the verified
one-command local lifecycle. LOCAL-01 has now closed that operational gate; the
first human-approved GitHub App scoped read is next. Provider writes and LLM
remain separate human-approved operations.

## DEC-077 - Local Runtime Is The Active MVP Operational Target

Decision (2026-07-14): FounderOS operates as a complete local-first product on
the founder's machine. The canonical operational entrypoint is `make local`,
with `make local-doctor`, `make local-smoke`, `make local-backup`, and
`make local-stop` as the supported diagnose, acceptance, backup, and shutdown
commands. `docs/operations/local-runtime.md` is the active runbook. A future
hosted target requires a new explicit decision; Railway is retired from the
active path.

Rationale: the current product loop, guided onboarding, Company World, local
connector imports, deterministic briefings, and approval review are usable on a
single machine. The hosted rehearsal predates the current auth/onboarding build,
has no managed backup entitlement, and adds operational risk without helping the
founder finish and use the product now. A single local entrypoint removes that
handoff while preserving the evidence, auth, and external-action boundaries.

Consequences:

- PostgreSQL remains the canonical structured store. Raw evidence remains in
  configured gitignored `RAW_STORAGE_DIR` (legacy `raw_storage/` is preserved;
  fresh installs use `.local/raw_storage/`); other local evidence stays under
  `.local/`. Obsidian remains export-only.
- Compose PostgreSQL 16 is the managed fallback baseline; a compatible reachable
  loopback PostgreSQL may be reused. Redis may be available for future jobs but
  is not required by the current synchronous runtime.
- The backend and frontend bind to loopback. Next.js continues to proxy API and
  health requests so the session cookie stays first-party; this preserves the
  security property of DEC-042 without a hosted split-origin topology.
- `make local` must preserve existing `.local/` contents and database volumes,
  fail clearly when prerequisites are missing, apply migrations only after the
  local database is reachable, require a verified full backup before migrating
  behind/unknown non-empty state, and keep provider reads, external writes, and
  LLM execution disabled by default.
- The supported backup boundary is one private bundle: logical PostgreSQL dump,
  raw-storage snapshot, checksums, aggregate-only manifest, and an isolated
  matching-major restore receipt. The stable encryption key is preserved
  separately from encrypted database data. Database files are never copied
  across major versions, and Alembic downgrade is not treated as a backup.
- Restore verification binds only to a private Unix socket with TCP disabled,
  rescans raw storage to detect concurrent changes, and proves decryptability
  only for real stored manual credentials; explicit test fixtures are reported
  separately and never count as credential proof.
- The supervisor owns children by verified process signatures. `SIGHUP`
  performs graceful cleanup; after supervisor death, `make local-stop` reclaims
  only verified recorded orphans and otherwise fails closed without touching
  data.
- Startup and diagnosis distinguish owned runtime processes from arbitrary
  occupied ports. Repeating `make local` against the exact verified supervisor
  and both verified children is an idempotent success that reopens or reports
  the existing product URL. `make local-doctor` reports those owned ports as
  healthy. A missing/mismatched child, stale identity, or unowned occupied port
  remains a failure and is never stopped implicitly.
- DEC-039 and the Railway-specific part of DEC-042 are superseded. Historical
  Railway rehearsal facts stay in the changelog, session log, and git history;
  target-specific active runbooks/templates are removed.
- A verified local stack is the prerequisite for the separately human-approved
  first real provider read and one-action external-result smoke. Local startup
  alone never authorizes either action.
- Stopping hosted services, removing domains, deleting a database/volume, or
  deleting a hosted project remains an external state change. Each retirement
  phase requires separate explicit human approval after a logical archive has
  passed a matching-major restore drill. "Use FounderOS locally" is not deletion
  approval.

Acceptance record (2026-07-14): LOCAL-01 passed doctor/start/same-origin smoke,
authenticated onboarding and all five product zones without overflow or console
errors, verified restore of 31 tables / 7 265 rows plus 51 raw files / 72
directories / 1 353 141 bytes, real credential proof 1/1 with 3 fixtures
excluded, graceful `SIGHUP` cleanup, and verified orphan recovery after simulated
supervisor `SIGKILL`. Ephemeral QA data and temporary restore state were removed.
The next gate is a separately approved, repository-scoped GitHub App read-only
sync; no provider read/write, LLM execution, or hosted deletion was authorized
by this acceptance.

## DEC-078 - Post-Auth Product Uses Command Mode, Not An Admin Console

Decision (2026-07-14): the five authenticated product zones use one
mission-first interaction grammar. Each primary view answers three questions
before showing secondary controls: «Сейчас», «Нажмите», «Результат». The next
useful action and its expected outcome appear before catalogs, creation forms,
filters, readiness matrices, and technical diagnostics.

Product rules:

- `/dashboard` leads with one current move and compact signals.
- `/company-brain` teaches the first click and points to the next unresolved
  candidate without changing the evidence-backed Company World projection.
- `/actions` leads with the decision queue and the next available review or
  preview step. Creation, readiness, filters, evidence, and bulk/technical
  tooling remain available through progressive disclosure; bulk actions become
  prominent only after selection.
- `/connectors` recommends the next useful source and explains the product
  result before showing registry and capability details. Connected, inactive
  existing connections, and role-limited setup remain visually distinct.
- `/settings` leads with the team and human-readable roles. Member creation and
  account/security operations stay contextual instead of dominating the page.
- Small contextual hints explain what a control does and what the founder gets
  after using it. Required actions must never be hidden only inside a technical
  disclosure.
- Technical boundaries, provenance, and evidence remain inspectable. The UI
  must not invent progress, relationships, provider connectivity, or completed
  execution.

Consequences:

- Future founder-facing screens should follow the same mission-first,
  progressive-disclosure pattern unless a later decision explicitly changes it.
- The product may feel game-like through focus, clear next moves, and visible
  outcomes, but it must not use fictional stages, points, or inferred company
  facts.
- UX-03 is frontend-only. Existing routes, backend APIs, persisted state, RBAC,
  evidence contracts, provider-read gates, external-write approval, and LLM
  boundaries remain unchanged. No migration, provider call, external write, or
  LLM path is added.

## DEC-079 - Provider Detail Pages Use A Source Command Center

Decision (2026-07-14): a provider detail page should explain and operate one
source through a small command-center grammar rather than expose backend
readiness as the product. `/github` is the first implementation and the
reference for later Jira, Gmail, and Drive detail-page redesigns.

The reference layout is:

- one role-aware mission with the current state, one next action, and its
  expected result;
- one short visual path from provider access through an explicitly selected
  source object into FounderOS;
- no more than four metrics, derived only from the typed response currently
  loaded and visibly scoped when the API returns a bounded sample;
- one promoted operation, followed by a human-readable success/partial/error
  receipt; a partial read refreshes the records that were available without
  being labelled as complete success;
- operational records below the source controls so the result of a successful
  load is visible without navigating elsewhere; and
- readiness matrices, env names, token policy, provenance, warnings, and raw
  technical causes behind accessible disclosures.

Honesty and access rules:

- local connection state is not presented as a live provider health check;
- repository and work counts are labelled as the loaded bounded sample, never
  as organization-wide totals;
- viewer guidance never promises setup or synchronization it cannot perform;
- provider setup and read controls remain role-gated, one repository at a
  time, and disabled unless the exact backend capability state is ready;
- visuals must not invent trends, completion percentages, CI health, team
  velocity, or other metrics absent from the response; and
- color is supplementary. Text labels, native controls, focus states, compact
  mobile layout, and reduced-motion behavior remain required.

Consequence: later provider pages may reuse the interaction grammar and visual
primitives but should not be forced through a generic configuration engine.
UX-04 changes frontend composition and presentation only; existing backend API,
database, RBAC, provider-read approval, external-write, evidence, and LLM
boundaries remain unchanged.

## DEC-080 - GitHub App Setup Is Workspace-Managed Self-Service

Decision (2026-07-14): the primary GitHub onboarding path is an owner/admin
wizard inside `/github`, not terminal env configuration or an operator-created
installation row. The wizard creates a private GitHub App from a manifest,
installs it, verifies the installation twice, and requires an explicit non-empty
repository selection before enabling reads.

Security and persistence rules:

- Setup mutations require an authenticated browser session with workspace
  owner/admin access. The operator API key cannot create or advance a managed
  setup; viewer/member access remains read-only.
- The manifest requests only repository `issues: read` and
  `pull_requests: read`; GitHub's implicit `metadata: read` is accepted. Any
  write permission or extra read permission fails closed. Events and webhooks
  are not enabled.
- App ID/slug/client ID and safe ownership metadata are workspace scoped.
  Private key, client secret, optional webhook secret, and PKCE verifier are
  encrypted with the existing application encryption boundary. Raw OAuth state
  is never stored; only SHA-256 is persisted.
- The `installation_id` returned to the setup URL is untrusted. FounderOS first
  verifies it with an App JWT, then uses OAuth + PKCE and `/user/installations`
  to prove the logged-in GitHub user can see the same installation and App.
  OAuth denial clears the verifier and produces a recoverable cancelled state.
- OAuth user tokens and just-in-time installation tokens are never persisted.
  Secret-bearing dataclasses are non-representable so routine diagnostics do not
  stringify their values.
- A verified installation creates a disabled connection. It becomes connected
  only after a non-expired setup saves one or more provider-returned
  repositories. The durable setup inventory is narrowed to that saved subset;
  an active credential/installation/connection relation is rechecked at
  finalization. After connection, any owner/admin may refresh the provider
  inventory and revise the subset; the existing connected selection remains
  active until the replacement is atomically saved, so abandoning a draft does
  not interrupt current reads.
- Managed live reads are restricted to the saved subset. A browser-session
  owner/admin may explicitly run that read without the legacy global
  `FOUNDEROS_ENABLE_REAL_CONNECTORS` gate because the managed setup and current
  click provide the scoped consent. Operator/CI calls remain behind the global
  gate. There is no background or bulk sync.
- The environment/manual compatibility path described in the original
  decision was removed by DEC-114. Missing or inactive managed credentials now
  disable verified status and live reads without fallback.

Schema consequence: migration `c5d6e7f8a9b0` adds encrypted workspace App
credentials, verified installation facts, and one resumable setup session per
workspace. It must be applied before the new backend starts.

Non-goals: this decision does not enable provider writes, webhooks, automatic
sync, LLM execution, hosted deployment, or removal of legacy compatibility
code. The real GitHub creation/installation and first scoped read remain
human/external acceptance gates until proven live.

## DEC-081 - FounderOS Uses A Living Headquarters, Not A Dashboard

Decision (2026-07-14): the founder-facing product model is a living company
headquarters. The default screen is not a collection of counters or setup
panels; it is one evidence-aware operating loop:

`signal → change in the company world → mission → human decision → action → receipt`.

The first frontend slice establishes this model as follows:

- the primary shell has three everyday zones: `Штаб`, `Мир`, and `Миссии`;
  providers and system configuration move backstage under `Радары` and
  `Настройки` without becoming unreachable on mobile;
- `Штаб` promotes exactly one current mission, explains why it was selected,
  renders a compact real-data Company World, and keeps signals plus a small
  world pulse below the primary action;
- people, organizations, affiliations, touchpoints, proposals, and source
  coverage keep their existing canonical meanings; visual placement must not
  invent a customer, employee, decision maker, health score, trend, or causal
  relationship;
- Company Map refs may be presented as direct read-model evidence. Local action
  proposal refs are labelled as declared source references until the backend
  supplies workspace-resolved verification; they must not be upgraded to
  verified evidence by presentation code;
- a current snapshot is not called a delta from the last visit. A true change
  timeline requires a future persisted snapshot/event boundary; until then the
  UI says explicitly that it shows the current evidence snapshot; and
- empty, unavailable, partial, role-limited, and truncated states remain
  distinct. Counts from truncated windows use lower-bound notation.

This is deliberate product language, not decorative gamification. FounderOS
does not add XP, streaks, invented company health, fake urgency, or autonomous
execution. The "game" quality comes from a legible world, bounded missions,
visible consequences, and human-controlled moves.

Consequence: later screens should migrate one at a time to this loop. `Мир`
becomes the full profile-and-relationship surface, `Миссии` becomes the human
decision queue, and each provider becomes a radar with setup and receipts.
Existing routes remain available during migration. This first slice is
frontend-only: it adds no schema, provider call, external write, LLM execution,
or authorization change.

## DEC-082 - Living World Links Resolve Opaque Selectors Against Current Evidence

Decision (2026-07-15): the full `/company-brain` surface is the operational
Living World for a workspace. It leads with one compact command bar, one current
review rail, a zone-filtered world scene, and one contextual profile inspector.
The canonical Company Brain and normalized-entity panels remain available as a
collapsed technical layer, but are mounted only after that layer is opened so
they do not compete with the primary task or start unrelated reads by default.

Profile navigation uses
`/company-brain?profile=<opaque-selector>#company-world-profile`. A selector may
refer to the company, a workspace member, a durable person/organization, or the
current evidence-version of a person/organization candidate. It never contains
the raw `CompanyMap.key`: candidate keys may include an email domain and must not
enter browser history or logs. Candidate selectors use `candidate_version`, so a
changed evidence snapshot safely invalidates an old link. Every selector is
resolved only against the current workspace-scoped `CompanyMapResponse`; an
unknown, malformed, stale, or foreign selector resolves to no entity and the UI
falls back to the current company profile.

Consequences:

- mini-map nodes, evidence-backed world missions, and candidate signal items can
  open the exact full profile without creating a second entity registry;
- query data never grants a role, relationship, evidence state, or mutation
  capability. Those continue to come exclusively from the current Company Map
  response and `capabilities.can_resolve`;
- team membership, durable affiliation, candidate resolution, idempotency,
  evidence, local receipts, and viewer/member RBAC retain their existing
  contracts. Every window-derived candidate total and candidate-organization
  people count is a lower bound when the source window is truncated, including
  explicit partial-zero copy;
- touchpoints remain profile-local history in this slice rather than a new URL
  entity type: selecting one does not replace or clear the routed parent
  profile;
- a changed candidate evidence version invalidates the selector before the
  refreshed profile is painted; and
- this decision is frontend-only. It adds no API, schema, provider call/write,
  external action, LLM execution, or authorization change.

## DEC-083 - Missions Uses One Active Human Decision Console

Decision (2026-07-15): `/actions` is the human decision room for the Living
Headquarters. It must not present every ActionProposal control at equal visual
weight. The primary loop is a compact queue plus exactly one active mission
console:

`why now → consequence → evidence → human decision → explicit action → receipt`.

The frontend applies these rules:

- it loads one mixed-status ActionProposal window with `limit=100`, then applies
  status/origin/audit-source filters locally. The pulse therefore describes the
  loaded window, not a workspace total, and must remain stable when a local
  filter changes. A true total or pagination requires a future backend contract;
- the initial active mission is chosen deterministically: failed, proposed,
  approved and previewable, approved, executed, then rejected. A direct current
  selection wins while it remains in the loaded window;
- the flat queue provides short origin/status context; why-now, consequences,
  evidence, approve/reject, preview, and history render for the active mission
  only. Changing the active proposal remounts execution controls so preview,
  connection, confirmation, error, and receipt state cannot cross proposals.
  While preview, history, or confirmed execution is pending, mission switching,
  local filters, workspace selection, and the global navigation shell are
  locked. Stale mutation responses from a previous workspace are ignored. The
  active console remains visible until the request settles; after successful
  execution, its sanitized outcome and receipt status stay pinned through the
  background refresh. A failure of the separate audit-history refresh is shown
  as a history warning and must never downgrade a confirmed execution into a
  retryable action error;
- approve and reject remain explicit local decisions. Execution preview also
  remains explicit and is never prefetched: the existing GET records an audit
  event, so it is not a side-effect-free read;
- bulk review is secondary and appears only after the user opens a consequence
  disclosure. Filters use pressed-button semantics, selection moves focus to the
  active console, mutation errors remain next to the failed action, and status
  changes are announced through live regions; and
- authorization is unchanged: owner/admin can review and execute, member can
  create local proposals, and viewer is read-only. Evidence refs, local decision
  audit events, execution receipts, and the external-write confirmation gate
  retain their existing backend meaning.

This replaces the earlier DEC-081 implementation note that the Missions page
should repeat one active status in the server request. A mixed loaded window is
required for one coherent queue and honest cross-status pulse; this does not
claim complete workspace totals.

Non-goals: no backend endpoint, schema, database behavior, provider call/write,
LLM path, or autonomous execution changes in this decision. A real total/
pagination contract and a connection picker richer than the existing controls
remain separate future work.

## DEC-084 - The Desktop Demo Is A Synthetic Product Contract, Not Runtime Evidence

Decision (2026-07-15): FounderOS has a separate desktop-only `/demo` simulation
that acts as the reference interaction contract for the intended completed
product. It tells one 12-scene causal story:

`onboarding → radars → connected signal → headquarters → relationships → people → knowledge → briefing → human decision → preview → receipt → updated headquarters`.

The reference surface follows these rules:

- all company, people, source, mission, evidence, preview, and receipt values are
  deterministic synthetic fixtures. The route permanently says that data is
  invented and that no external action occurs; it must never be cited as proof
  that a provider is connected, a real read ran, or the authenticated product is
  complete;
- the story is stateful enough to prove its own causal model. Direct navigation
  to the final scene shows an unsaved preview. Only explicit demo confirmation
  creates the synthetic receipt, changes waiting/completed counts, removes the
  Atlas mission from the waiting queue, promotes the next mission, and changes
  the headquarters. A completed decision cannot be simulated twice without an
  explicit restart;
- the implementation is isolated from runtime data: no API client, fetch,
  provider call, form submission, cookie/local-storage persistence, external URL,
  or provider write is used. The exit link disables framework prefetch so the
  public demo does not speculatively read the protected dashboard;
- public access is exact-path only. Development enables `/demo` locally.
  Production returns not-found unless `FOUNDEROS_DEMO_ENABLED` is exactly
  `true`; `/demo/*` remains under the normal authenticated shell boundary;
- this contract targets desktop browsers at 1280×720 or larger. It intentionally
  does not define or claim mobile/tablet behavior. Autoplay, presenter mode,
  hints, keyboard navigation, deep links, and visited progress are presentation
  aids, not persisted product state; and
- future production work may reuse the information hierarchy and interaction
  grammar, but every real completion, metric, relationship, signal, decision,
  and receipt must be derived from the existing workspace-scoped backend and
  evidence contracts. Demo fixtures must never become an authenticated fallback.

Consequence: the next local product slice is not another broad visual redesign.
It is the smallest real-data promotion of this contract: computed onboarding as
a short prologue to the Living Headquarters, followed by one screen at a time.
The first real GitHub App read, any external write, LLM narrative, hosted change,
or mobile product contract remains a separate explicitly approved scope.

## DEC-085 - The Demo Uses One Command Center With Progressive Disclosure

Decision (2026-07-16): the presentation grammar of DEC-084 is superseded. The
desktop `/demo` reference is one Living Command Center, not a tour through many
screens. The causal fixtures, exact-path gate, synthetic-data honesty, and
external-write boundary from DEC-084 remain authoritative.

The interaction contract is:

- the default surface spends attention on one main priority and one primary
  action. It may additionally show three compact pulse metrics, at most two next
  decisions, and three recent signals. Profiles, source coverage, documents,
  timelines, queue logic, and evidence do not render on the surface;
- clicking a tile opens one right-side drawer with the relevant card. A drawer
  may use short `Overview / People / History` tabs, but it must not become a
  hidden second application or stack another drawer. Only one overlay exists at
  a time. A selected mission carries its own id, owner, consequence, requested
  decision, evidence count, and exact source set; a specific row must never open
  an unrelated generic queue;
- a consequential decision uses one focused modal that keeps why-now context,
  owners, evidence, the exact synthetic preview, explicit confirmation, and the
  receipt together. The dimmed command center remains visually present so the
  decision feels like a temporary command mode, not navigation to another page;
- motion and expressive shape are reserved for orientation, focus, and state
  change. They may reinforce the game-like feeling of managing a living system,
  but decorative gauges, scores, points, streaks, resource clutter, and copied
  game visual identities are not part of FounderOS;
- the assistant is a persistent entry point inside the headquarters context,
  opened by the command field or `Cmd/Ctrl+K`. In the demo it is a deterministic
  intent resolver over synthetic fixtures, with short answers, citation chips,
  and explicit navigation/actions. Its local form prevents network submission;
  it has no API/fetch/provider call, persistence, free-form LLM execution, or
  direct mutation path;
- assistant suggestions can open a profile, evidence, team, source detail, or
  decision preview. A human still confirms the decision separately. Completing
  the demo decision changes the derived queue, primary mission, counts, and
  receipt together; the primary action follows the promoted mission while the
  old receipt becomes secondary. Refresh/reset discards the whole synthetic
  session, including assistant transcript. Overlay replacement preserves the
  original opener, completion moves focus to the receipt heading, and meaningful
  desktop text uses a 10 px floor with core facts/actions at 11–12 px or larger;
  and
- a future real assistant must be a separate workspace-scoped, read-only backend
  contract over Company Brain, Company Map, Briefing, and ActionProposal reads.
  It must normalize citations, expose `is_live`/`llm_used`/warnings, respect
  current RBAC, and remain unable to persist or execute a suggestion implicitly.
  Chat history, retrieval/LLM generation, and any write capability require their
  own schema, privacy, retention, validation, and approval decisions.

Rationale: current 2025–2026 management interfaces increasingly use overview
tiles that reveal deeper cards, temporary command-focus layers for consequential
choices, and agents embedded into the workspace that owns the context. These are
durable hierarchy patterns rather than a short-lived visual trend. FounderOS
adopts the patterns while preserving readable typography, evidence visibility,
human accountability, and product honesty.

Consequence: the old scene outline, autoplay/tempo controls, transport, guide
rail, browser-window frame, deep-link scene model, and scene-specific CSS/tests
are deleted. DEC-084 remains the source for the synthetic/runtime boundary but
must no longer be used as the visual or navigation reference.

## DEC-086 - The Real Headquarters Uses One Server-Side Read Projection

Decision (2026-07-16): promoting the DEC-085 command-center grammar into the
authenticated product starts with one workspace-scoped, read-only headquarters
projection. The recommended contract is
`GET /api/v1/workspaces/{workspace_id}/headquarters`. It composes existing
Company Brain, Company Map, Briefing, ActionProposal, connector, and membership
data and returns one timestamped/partial-aware snapshot: one priority, at most
two next missions, three pulse metrics, up to three current signals, source
health, onboarding state, capabilities, evidence, and warnings.

The first implementation is a projection, not a new durable `Mission` table.
Stable mission ids derive from existing canonical references such as an action
proposal, briefing item, Company Map candidate, or setup gap. A durable Mission
schema remains gated until real use proves a need for persistent assignment,
composite cross-source decisions, closure, and lifecycle history. A real
since-last-visit feed remains a separate schema/data decision because it needs
server snapshots, dedupe, a per-user checkpoint, and restore-safe persistence.
Company Map mission references use existing opaque selectors rather than raw
candidate keys that may contain email/domain data. Snapshot ids are immutable
state/version references built from a consistent transaction or explicit input
watermarks; assistant reads bind to the screen snapshot. Any later confirmation
must bind to the exact proposal version and preview digest and fail stale with
`409`.

The same headquarters service must feed the UI, the first deterministic
read-only assistant, and the refresh after a decision receipt. An ordinary
headquarters read cannot call providers, run an LLM, acknowledge a visit, or
mutate canonical data. Every specific claim remains evidence-backed; every
count declares exact/lower-bound/unavailable precision; partial inputs remain
visible as warnings. The synthetic `/demo` remains a UI reference only and is
never an authenticated fallback.

The current browser ranking policy is not copied blindly. Before a proposal can
become evidence-backed priority, the backend resolves its reference ids inside
the workspace and assigns a provenance/trust class. Caller-declared refs,
caller-supplied severity, or a caller-supplied system/AI origin do not become
verified facts. Missing or foreign refs are excluded from specific ranking and
surface only through an honest unsupported/aggregate state.

Rationale: the current dashboard composes several independent reads and ranks
the main mission in browser code. That is useful foundation work but cannot
guarantee that the screen, assistant, decision modal, and receipt refer to the
same ordered company state. A single server projection creates one reproducible
truth boundary without prematurely adding a migration or duplicating canonical
models.

Consequence: `docs/LIVING_COMMAND_CENTER_CHECKLIST.md` is the execution and
acceptance ledger for this product slice. The first implementation ticket is
the headquarters schema/service/endpoint plus contract tests, with no migration,
provider call, LLM, or write. UI promotion follows only after that read contract
is proven.

Implementation receipt (2026-07-16): the first read slice now exists at
`GET /api/v1/workspaces/{workspace_id}/headquarters`. It revalidates membership
inside one PostgreSQL `REPEATABLE READ, READ ONLY` transaction, returns a
content-addressed `hqs1_*` snapshot/ETag, fixed three-metric pulse, one ranked
priority plus a two-item queue, source axes, current-snapshot signals and
backend capabilities. Proposal ranking resolves references in the workspace,
ignores caller payload severity, and trusts Briefing severity only for an
internal system proposal linked to the exact same persisted BriefingItem
evidence. The public proposal endpoint now fixes caller origin to `user`;
internal services retain the reviewed system path. The read does not add a
migration, provider call, LLM, acknowledgement, or write. Source and decision
inputs are bounded: connection/job/record history is aggregated, Company World
uses only the newest 100 Gmail records plus matching resolution keys, proposal
ranking scans at most 100 rows, and legacy oversized proposal JSON is counted
but excluded before ORM materialization with `partial/at_least` precision. A
five-second statement timeout and DB-level READ ONLY guard bound the read;
outside the explicitly isolated Company World timeout, failures remain
fail-closed.
`proposal_version` binds the complete current action plus raw refs and resolved
current evidence identity/hash/field/URL state plus trusted Briefing severity
and confidence; EvidenceRef provenance remains at its exact row grain. Explicit
selectors never fall back to a looser ref and must match the canonical provider.
Source-health missions use derived aggregate provenance rather than an
unrelated latest row, payload-declared Gmail evidence cannot invent a second
provider, and malformed source URLs are omitted before response validation. A
Company World SQLSTATE `57014` inside its savepoint becomes typed partial;
unknown DB/invariant failures still fail the request. Immutable historical
observations still require the SourceObservation/Foundry schema gate below, and
exact preview confirmation digest remains LC-08 rather than being simulated by
this read model.

## DEC-087 - Source Foundry Is One Promotion Pipeline, Not One Server Per Source

Decision (2026-07-16): future intake and preprocessing use one logical
workspace-scoped **Source Foundry**. GitHub, Jira, Gmail, Drive, document and
later source integrations provide allowlisted adapter/parser/mapper modules to
one orchestrator; they do not become separately deployed source servers. The
first topology stays inside the current FastAPI application with one bounded
runner. If volume later requires asynchronous work, one shared worker pool uses
database leases, heartbeat, idempotency and single-flight rather than a service
fleet per provider.

The pipeline boundary is:

`scoped acquisition -> immutable raw envelope + PostgreSQL manifest -> schema,
privacy and security validation -> quarantine or versioned normalization ->
entity/relationship candidates -> deterministic or human resolution -> atomic
promotion receipt -> existing canonical FounderOS tables`.

Only the acquisition adapter may use provider network access and short-lived
credentials. Parser, normalizer, resolver and promoter have no provider access.
Unknown schemas, unsafe files, secret-like fields outside an allowlist, malformed
or oversized inputs, parser failures, ambiguous identity matches and hash
mismatches remain quarantined and cannot become product facts. Dynamic
third-party plugin loading is not part of the first version. An LLM may later
propose a typed candidate, but it can never promote or mutate canonical data
directly.

FounderOS product reads — including Headquarters, Company Brain and the future
assistant — consume only atomically promoted canonical state. Raw, quarantined,
rejected, merely normalized and unresolved staging records never participate in
priority, pulse, relationships or assistant answers. Promotion rechecks
workspace/RBAC, immutable hashes, pipeline versions, evidence and required
human decisions; it is idempotent, creates canonical rows/lineage/receipt in one
transaction, performs no provider/LLM/external write, and then emits only an
internal refresh signal.

Внешний provider остаётся источником истины о своём состоянии. Локально
immutable raw envelope в raw storage вместе с PostgreSQL manifest, canonical
rows, lineage и promotion receipts образуют authoritative replay/audit state;
Obsidian остаётся только export-проекцией. Текущий `SourceRecord` — sanitized
current projection, а не raw envelope и не immutable historical observation.

This extends rather than replaces DEC-028/DEC-070/DEC-074/DEC-086. There is no
second authoritative graph: the knowledge graph is a read projection over
canonical `Person`, `Organization`, `Affiliation`, `Interaction`, `Task`,
`Repository` and evidence-backed edges. Similar names, text, embeddings, email
addresses or domains may create a review candidate but cannot prove an
employment, customer, decision-maker or cross-source relationship.

The present `SourceRecord` remains the sanitized current logical object used by
the product. Before Source Foundry persistence is implemented, a separate
schema review must add immutable observation/lineage grain (preferred:
`SourceObservation` revisions linked to exact raw-envelope and payload hashes),
quarantine lifecycle and promotion receipts. This decision adds no migration or
runtime ingestion path now. Promotion receipt обязан связывать workspace,
input/envelope hash, adapter/parser/mapper versions, candidate version,
deterministic либо human decision, canonical row ids/versions и idempotency key.
Broken/hash-mismatched lineage закрывается fail-closed; receipt не содержит raw
body или secret values. SF-00 contracts/threat model и fixture-only shadow
pipeline следуют только после приёмки реального headquarters UI slice.

## DEC-088 - Onboarding Is A Server-Computed Headquarters State, Not A Browser Journey

Decision (2026-07-16): workspace onboarding is part of the unified Headquarters
read projection. `headquarters.v2` embeds `onboarding.v1` with five ordered
steps — company, source, canonical data, context and headquarters — and the
same service exposes the detailed read-only slice at
`GET /api/v1/workspaces/{workspace_id}/headquarters/onboarding`. Both endpoints
return the same content-addressed snapshot, evidence, capabilities, role-aware
actions, `next_action`, ETag and private/no-store boundary; the detailed route
does not compose another readiness model.

Three steps are required: the workspace/company exists, at least one canonical
`SourceRecord` exists, and the Headquarters snapshot was computed successfully.
Source configuration and context from team, Company World, briefings or prior
decisions are recommended. They improve the product but do not block a single
founder. `priority=null` remains a valid calm Headquarters state. Every step is
derived from evidence; `unknown`, unavailable and partial inputs never become
complete. Step state and evidence state are validated together at the Python
and browser contract boundaries.

For a session with a workspace, `/onboarding` redirects into the real
`/dashboard` and opens one compact modal over the Headquarters. It shows only
the current required blocker, benefit, evidence disclosure and one backend
action. The modal has priority over drawers and the assistant, supports resume
after reload, clears explicit route intent after dismissal, and refetches the
same Headquarters after completion. Browser-side source/map/team fan-out and
manual completion flags are removed. An account with no workspace remains on a
separate honest recovery surface and does not call workspace endpoints.

This partially supersedes the separate hash-driven workspace journey in
DEC-075 while preserving its private invite, fragment-only bearer, explicit
workspace selection, one-time teammate setup and closed public-signup
boundaries. The slice adds no migration, provider call, LLM, canonical write,
acknowledgement or external action. Source setup continues through the existing
role-gated product routes; later public company creation requires a separate
security/product decision.

## DEC-089 - Headquarters Local Decisions Are Version-Bound And Receipt-First

Decision (2026-07-17): a local approve/reject from Headquarters is a distinct
human command, not a shortened external execute path. The command is bound to
the exact persisted `ActionProposal` row through a deterministic `ap1_*`
`proposal_version`; Headquarters additionally sends its visible `hqs1_*`
`expected_snapshot_id`. The server re-checks active user, workspace membership
and admin-or-owner authority inside the write session, locks the exact proposal
row, validates the proposal version and, when supplied, recomputes the current
Headquarters context before changing status.

Every single local decision requires a client idempotency key. The audit event
stores a stable request fingerprint and the pre-decision proposal version.
Replaying the same key and input returns the original durable receipt; reusing
the key with different decision input, a stale proposal/snapshot or an invalid
transition fails with `409`. The receipt names the proposal, decision, audit
event, recorded time and version and always states
`external_write_performed=false`. The command creates no `ActionExecution` and
cannot call a provider. Existing bulk review remains a separate compatibility
path and is not presented as this exact receipt-first Headquarters flow.

The Headquarters modal first re-reads the exact workspace proposal and requires
its version to match the mission. Pending submission locks overlay dismissal,
workspace/mission navigation and duplicate submit. An ambiguous response gets
at most one identical POST retry with the same idempotency key; only the command
endpoint's validated authoritative receipt can complete the UI. Audit read-back
must not fabricate or infer a receipt. Exhausted network/5xx failure keeps the
same key for a manual retry; 4xx and response-contract failures fail closed.
After a persisted result, Headquarters refetches the same server projection. A
refetch failure preserves both the receipt and previous confirmed snapshot and
offers a separate retry; it never relabels a saved decision as failed.

Exact mission/profile disclosure follows the same rule. Opaque Company Map
selectors may resolve only the requested current-snapshot entity; malformed,
foreign and stale selectors have no generic company fallback. Mission fields
without their own provenance display `Не определено`. Employee access role is
not a business title, and customer people/history is derived only from durable
relations and exact bounded touchpoints. This slice adds no business-profile
write, inferred role, customer health, migration, provider call, LLM call or
external execution preview. External LC-08 confirmation remains gated on a
separate exact preview digest, current actor/RBAC re-check and explicit human
permission before any provider write.
The drawer renderers are implemented, but the production Headquarters mission
projection still leaves confirmed owner, primary-person and organization IDs
empty; confirmed employee/customer navigation therefore remains an explicit
schema/data gate rather than a claimed end-to-end flow.

## DEC-090 - Frontend Runtime Dependency Risk Is A CI Gate

Decision (2026-07-22): the committed frontend lockfile must resolve without any
moderate-or-higher npm advisory in runtime dependencies. CI enforces this with
`npm audit --omit=dev --audit-level=moderate` after a clean `npm ci`. CodeQL
must analyze JavaScript/TypeScript alongside Python and GitHub Actions, and
Renovate must track the `web/package.json` npm manifest as well as Python
dependencies with a minimum release age.

The immediate remediation updates Next to `16.2.11` and constrains its
transitive PostCSS and Sharp packages to patched `8.5.21` and `0.35.3` through
npm overrides. These overrides are an explicit lock-level compatibility guard,
not permission for broad or forced dependency rewrites. Future routine updates
may remove an override only after the direct dependency resolves a non-vulnerable
version and clean install, audit, tests, typecheck and production build pass.
`npm audit fix --force` is not an accepted remediation because it may replace a
supported framework with an unrelated breaking version.

This extends DEC-027/DEC-037 and does not change the provider-free CI boundary.
Dependency metadata may be queried during install/audit, but CI gains no
provider credential, product data, runtime API call or external-write ability.
Dependency Review remains the pull-request diff guard; npm audit protects the
resolved runtime tree, while CodeQL and Renovate cover different static-analysis
and update-discovery roles. Passing these gates does not prove deployed or live
provider behavior.

## DEC-091 - The Company Assistant Is A Deterministic View Of One HQ Snapshot

Decision (2026-07-22): the first real company assistant is a workspace-scoped,
read-only projection over the same `read_workspace_headquarters` service used
by the authenticated Headquarters screen. Every query must carry the exact
visible content-addressed `hqs1_*` snapshot. If the current projection differs,
the server returns `409 snapshot_changed` and no answer; the browser clears the
old result, refreshes the snapshot and requires a deliberate retry. The screen
and assistant therefore cannot silently name priorities from different
versions.

Version `assistant.v1` is deterministic and allowlisted. It classifies only
priority, why-now, owners, company/person, sources, briefing, waiting decisions,
evidence, decision status and explicit action-request boundaries. The response
contains bounded text, normalized workspace-scoped citations, safe suggestions,
optional capability-filtered navigation, snapshot/as-of/partial/warnings,
`is_live=true` and `llm_used=false`. Missing evidence returns
`Недостаточно подтверждённых данных.` Unsafe instructions are ignored without
echoing the query, and unsafe URLs, credentials or sensitive query parameters
never become clickable citations.

The endpoint persists no chat, reads no raw/private provider body, invokes no
provider or LLM and calls no mutation service. Query length, execution time,
response bytes, citation/suggestion counts, per-user/workspace request rate and
identical-query single-flight are backend invariants. Request logging records
method/path/status only, never the full question or citation contents. The
process-local limiter is sufficient for the current single-process local
runtime; any multi-worker/hosted topology must replace it with a shared bounded
store before claiming equivalent enforcement.

There is one launcher in the authenticated shell, including non-HQ product
zones. Headquarters registers its exact visible snapshot; other zones fetch the
same server projection before asking. `Cmd/Ctrl+K`, overlay focus restoration
and normalized citation navigation use the shared production overlay contract.
«Сделай сам» never creates, approves, rejects or executes a proposal: an
authorized reviewer may only navigate to the existing human confirmation
screen, while a viewer receives no confirmation action. A future generative
assistant requires a separate privacy/retention, retrieval, model/schema,
budget and persistence decision and may never mutate production data directly.

## DEC-092 - Connector Configuration Is Encrypted, Fixed-Host, And Receipt-First

Decision (2026-07-23): workspace connector configuration belongs in one
owner/admin product control surface at `/settings/integrations`, backed by the
existing `IntegrationConnection` table. A submitted credential is encrypted
before the ORM row is populated, is never returned to the browser, and is
represented in reads only by safe configured/status booleans. Applying a
configuration performs no provider call and resets prior verification.
Successful verification requires a separate explicit bounded read and stores a
versioned safe receipt in `provider_metadata.control_center`; no schema
migration or parallel secret store is introduced.
Every control response is private/no-store. A check may report
`provider_call_performed=true` only after the provider network boundary was
attempted; local credential/configuration failures report false.

The first contract supports only GitHub, Jira Cloud, Gmail and Google Drive.
GitHub App is the recommended GitHub method and remains independent from the
advanced personal-token fallback. Jira URLs must be exact HTTPS
`*.atlassian.net` origins; every other probe uses a fixed official provider
host. Arbitrary APIs, private hosts, redirect targets, provider response bodies,
opaque installation/connection IDs and token hints are not accepted or
returned. The status projection does not decrypt secrets. Explicit
session-authenticated owner/admin read checks may make their one requested
provider GET; operator/API-key calls remain behind
`FOUNDEROS_ENABLE_REAL_CONNECTORS`.

“Check write” is deliberately a local readiness dry-run. It reads feature,
approval, read-verification and allowlist gates but does not decrypt a secret,
call a provider or mutate external state. A real GitHub write still requires
the existing exact approved ActionProposal execution path with evidence, target
allowlist, idempotency and read-back receipt. Jira/Gmail/Drive writes are not
implemented. Manual Gmail/Drive OAuth access tokens are an honest first slice:
authorization-code consent, refresh-token rotation and automatic renewal remain
future work and the UI must not imply otherwise. PostgreSQL and raw storage
remain authoritative; Obsidian remains export-only.

A credential created through the control center can be removed only by an
owner/admin after a second explicit UI confirmation. Removal clears encrypted
secret fields, account label, scopes and verification receipts but retains the
durable connection row, imported canonical facts and sync history. This avoids
breaking foreign-key/audit lineage. Managed GitHub App material remains owned
by the separate GitHub App setup flow; the control-center removal can clear
only its separately stored PAT fallback.

The default product interaction is intentionally narrower than the full API
contract: select a provider, save access, then check reading. A missing
configuration disables the check and renders no empty receipt. Write readiness,
removal and PAT fallback are progressive details. Unconfigured Radar cards
deep-link into the exact provider tab; source data pages do not expose raw JSON
import as their primary workflow.

## DEC-093 - Workspace Repository Inventory Fails Closed

Decision (2026-07-23): any product read that supplies a `workspace_id` may load
GitHub repository inventory only from canonical `Repository` rows belonging to
that exact workspace. When the workspace has no canonical repository rows, the
correct product result is an empty inventory.

The retained `SourceEvent` table has no workspace identity. Local discovery
snapshots and legacy inventory files are also unscoped. They may remain as
compatibility inputs for explicit operator/script reads that omit
`workspace_id`, but they must never be a fallback for `/github`, workspace API,
Company Brain, or another tenant-visible product surface. This is a tenancy
boundary, not a ranking preference: an unscoped record cannot be shown and
labelled as though it belonged to the current company. Regression coverage must
combine an empty workspace with populated global events/discovery state and
prove the result stays empty.

## DEC-094 - GitHub Product UI Has One State And One Primary Action

Decision (2026-07-23): `/github` is a state-driven product workspace, not an
operator command center. The visible state is exactly one of loading,
unavailable, disconnected, connection-attention, connected-without-repositories,
or connected-ready. Each actionable state exposes one primary next step.
Setup progress, repository selection, synchronization readiness, metrics and
operational work must not render as competing journeys.

Disconnected and connection-attention states expose an explicit
connect/continue action. The managed GitHub App wizard stays mounted only when
needed for its current product interaction and becomes visible inside one setup
panel; while that panel is open, the original CTA and benefit cards are hidden.
A ready connection exposes one repository selector and one explicit
repository-scoped read action. Operational data is then shown as one tabbed
list for issues or pull requests and is filtered in the browser to the exact
selected repository. Empty repository access leads back to management instead
of rendering an empty dashboard.

This is a presentation and orchestration decision. It does not change the
workspace-scoped backend API, GitHub App credential lifecycle, selected
repository allowlist, just-in-time installation tokens, RBAC, canonical
persistence or external-write boundary. Technical facts and provider warnings
remain available through progressive disclosure. A viewer may inspect already
available facts but receives no setup or sync controls.

## DEC-095 - FounderOS Is An AI Partner With Evidence-Backed Company Memory

Decision (2026-07-25): FounderOS is no longer defined by the Living Command
Center mental model. Its product contract is an AI partner that observes
workspace-scoped sources, builds temporal company memory, gives a bounded
evidence-backed second opinion and prepares human-approved actions. The primary
user zones are `Сейчас`, `Компания`, `Спросить` and `Настройки`.

The daily surface shows one main conclusion, at most three attention signals
and one next step. Provider names, source diagnostics, scopes, credentials,
manual import and operational controls belong to Settings. Users may drill down
from conclusion to situation, domain, entity/history and exact evidence. A
generative answer must distinguish fact, interpretation, objection and
recommendation; unsupported claims remain absent.

The personal GitHub repository containing FounderOS is product infrastructure,
not company memory. A work GitHub organization is a workspace-scoped source
whose exact installation and repositories must be selected explicitly. These
planes may not share unscoped repository inventory or appear as one connection.

Existing evidence, tenancy, RBAC, raw/Postgres truth, Company Brain/World,
Headquarters projection, ActionProposal, approval, idempotency and receipt
foundations are retained. `Штаб / Мир / Миссии / Радары`, provider-first product
routes, synthetic Command Center demo, duplicate briefing/dashboard surfaces
and their unused code/docs/tests are superseded and must be removed after their
replacement path is verified. This decision does not authorize deletion of
secrets, `.env`, raw storage, migrations, production data or unrelated
uncommitted work.

Company memory must carry evidence, event/observation time, confidence, access
and retention. Secrets, duplicate raw text and chat history are not memory.
Chat persistence remains disabled until a separate privacy/retention decision.
External writes always require preview, explicit approval and an authoritative
receipt; an LLM never mutates production data directly.

DEC-081 through DEC-085 and DEC-094 remain historical implementation evidence
but are superseded where they define Living Command Center or provider-first UX
as the target product. Security and persistence boundaries in those decisions
remain active unless explicitly reversed.

## DEC-096 - Temporal Comparison Stores A Minimal Personal Checkpoint

Decision (2026-07-27): the first temporal-memory slice compares deterministic
workspace-scoped signals against an explicit per-membership checkpoint. The
checkpoint persists only its version, exact source `hqs1_*` snapshot, observation
time and a bounded set of opaque SHA-256 signal fingerprints. It does not copy
signal titles, summaries, evidence bodies, documents, messages, provider
payloads or chat.

The `headquarters.v3` read model exposes `event_time` separately from
`observed_at`, requires evidence for each temporal event, carries confidence,
declares workspace access and source-bound retention, and distinguishes
`current_snapshot` from an actual `checkpoint` comparison. A checkpoint write
requires the exact visible snapshot and fails with `409` if the company picture
changed. It is available to every active workspace role because it mutates only
that user's membership state, not shared company facts. Removing the membership
cascade-deletes the checkpoint.

This is a minimal comparison read model, not the final canonical event ledger.
It can prove which currently visible evidence-backed signals are new or changed
relative to the saved fingerprints. It does not yet claim a complete history of
resolved/disappeared signals, commitments, decisions or risks. Those require
the later canonical memory model, contradiction handling, correction,
forgetting and retention controls. Raw storage and PostgreSQL remain the source
of truth; no LLM or provider call participates in checkpoint reads or writes.

## DEC-097 - Lifecycle Memory Is A Content-Free Append-Only Projection

Decision (2026-07-27): FounderOS persists lifecycle memory in the append-only
`company_memory_events` projection. Each event has a transactional monotonic
sequence inside its exact workspace, controlled event/subject type, event and
observation time,
canonical evidence identifiers, SHA-256 material fingerprint, confidence,
workspace access, internal sensitivity and `workspace_canonical` retention.
It never stores proposal titles/descriptions/payloads, rendered UI summaries,
message/document bodies, provider payloads, chat history or secret material.
Read-time UI copy is resolved from the canonical subject or generated from the
controlled event type.

The first producer set is deliberately bounded: Action Proposal creation,
approval and rejection, plus Company World confirmation and dismissal. Each
producer appends in the same database transaction as the canonical mutation
and uses deterministic idempotency material. Existing proposal audit events and
Company World resolutions remain their domain authorities; the lifecycle
ledger is a temporal memory index over those facts, not a competing raw or
audit store. Replaying supported exact commands may materialize a missing
ledger row idempotently, but no automatic historical backfill scans old data.

Temporal Checkpoint v2 combines the existing bounded fingerprints of current
signals with `last_event_sequence`. Headquarters Temporal Memory v2 therefore
shows current facts before the first checkpoint, new/changed current signals
after it, and supported terminal events as `resolved`. A later acknowledgement
advances both parts of the checkpoint without copying source text. The
membership checkpoint remains personal and cascade-deletes with membership;
shared lifecycle events cascade only with the workspace.

The checkpoint cursor uses a transactional per-workspace stream counter rather
than a PostgreSQL identity value. Identity numbers are allocated before commit,
so a slow transaction could otherwise commit below an already acknowledged
maximum and never be observed. The stream counter is incremented in the same
savepoint as the event and serializes cursor allocation per workspace; rollback
does not publish an event or cursor advance.

At adoption this decision did not claim disappearance detection for provider
objects. DEC-098 now adds that bounded capability for complete GitHub issue/PR
repository snapshots only. Jira/Gmail/Drive reconciliation, user correction
and forgetting controls, and broader commitment/decision/risk event types
remain separate explicit work. PostgreSQL and raw storage remain authoritative,
and no LLM participates in lifecycle ledger writes.

## DEC-098 - Provider Absence Is A Fact Only After An Authoritative Snapshot

Decision (2026-07-27): FounderOS may mark an external object disappeared only
after a successful, server-attested and complete provider snapshot of one
explicit scope. `source-reconciliation.v1` initially supports GitHub issues and
pull requests inside selected repositories. The provider read must cover every
state and every page. GitHub pagination fails the entire read when its bounded
page limit is reached, so truncated data never reaches reconciliation as a
successful snapshot.

Client-authored SyncJob metadata, `normalize-local`, local JSON imports,
single-result compatibility normalization, filtered state reads, failed calls
and partial responses cannot infer deletion. A server-performed partial or
single-object GitHub read may restore that exact object when it is observed,
but it cannot tombstone anything absent from its result. Jira, Gmail and Drive
remain ineligible until they have complete paginated live provider reads;
their current local imports are untrusted partial inputs.

`SourceRecord` is the lifecycle authority. A tombstone is reversible and stores
the provider snapshot time, persistence time, observing SyncJob and a controlled
reason. Provider snapshot time, not database write time, orders concurrent
reads: an older snapshot cannot overwrite, tombstone or falsely restore state
already established by a newer one. Restoration clears current tombstone
provenance only after a trusted provider observation. Historical disappearance
and restoration remain in the append-only memory ledger.

Tombstoning does not hard-delete provider payloads, evidence or derived
history. Current-state GitHub reads exclude Task/PullRequest projections linked
to a tombstoned SourceRecord; `PullRequest.source_record_id` makes that lineage
explicit. Disappearance and restoration append content-free lifecycle events
in the same database transaction, containing canonical identifiers rather than
source text. This is lifecycle reconciliation, not a retention/erasure
mechanism. Raw storage and PostgreSQL remain authoritative; no LLM or external
write participates.

## DEC-099 - Pytest Must Prove A Dedicated Database Before App Import

Decision (2026-07-29): every pytest process fails closed before importing the
application database engine unless `APP_ENV=test` and
`FOUNDEROS_TEST_DATABASE_URL` explicitly identify a loopback PostgreSQL
database whose name contains a standalone test marker. The target is compared
with product endpoints found in `.env`, `.env.local`, and the ambient
environment without printing URLs or credentials.

The guard then makes that validated target the runtime `DATABASE_URL`, disables
dotenv loading, LLM execution, real connectors and external writes. The
existing `make backend-check` wrapper remains the canonical local entrypoint
and passes the same validated target into pytest. CI uses the dedicated
`ckdos_test` database, applies migrations, and runs `alembic check` before its
test gates.

A test-like database name is necessary but not sufficient proof that data is
disposable; provisioning and lifecycle remain operator responsibilities. There
is no bypass for ordinary product database names. This decision supersedes
active guidance that treated bare `uv run pytest` as an acceptable default.

## DEC-100 - External Writes Require A Committed Claim And Reconciled Outcome

Decision (2026-07-29): every GitHub issue execution must acquire the proposal
row lock, persist an `ActionExecution` claim and commit it before any provider
request. The claim contains the proposal and workspace identity, authenticated
requesting user, exact connection, mandatory workspace-scoped client
idempotency key, SHA-256 request hash and claim timestamp. A second commit marks
the provider request `running` before network I/O begins.

PostgreSQL enforces one use of a client key per workspace and at most one
`claimed`, `running`, `succeeded` or `uncertain` execution per proposal. Legacy
running rows become `uncertain` during migration because their external outcome
cannot be inferred safely. Legacy actor and connection fields remain nullable;
new execution paths always populate them. User deletion may remove the actor
reference with `SET NULL` without removing the durable receipt.

Every GitHub issue body receives a hidden, non-secret marker derived from the
execution UUID and request hash. A provider exception after the request begins
does not become a definitive failure: the execution remains `uncertain`, the
proposal cannot execute again, and read-only reconciliation lists a complete
all-state provider snapshot and searches for that exact marker. One match
records the execution as succeeded and continues canonical normalization;
multiple matches fail closed. A missing marker during the first 60 seconds
keeps reconciliation pending to avoid an eventual-consistency duplicate. Only
a later complete snapshot with no marker records `write_not_observed`, returns
the proposal to approved and permits a human-approved retry with a new
idempotency key. A claimed row may be failed immediately because the provider
request's `running` transition was never committed and therefore network I/O
did not begin.

Pre-provider failures such as an undecryptable credential are definitive for
that attempt but leave the proposal approved for an explicitly new-key retry.
Successful, uncertain, reconciled, blocked and preview audit events record the
authenticated user rather than a generic workspace role. Provider responses
remain sanitized, reconciliation performs no external write, and an LLM still
cannot execute actions. Acceptance requires two simultaneous execute requests
to produce exactly one provider call, one `ActionExecution` and one external
issue.

## DEC-101 - Approval And Execution Share One Canonical Evidence Gate

Decision (2026-07-29): an ActionProposal may be created only with bounded
`evidence_ref.v1` objects. Every object has a controlled set of fields, a
non-empty kind/source, one supported selector and an optional safe HTTP(S)
source URL. Arbitrary nested JSON and unknown evidence fields are rejected
before persistence. Empty evidence may remain on an unapproved draft so the
user can correct it, but it can never pass approval or external execution.

Approval resolves every reference against active canonical rows in the exact
workspace. Missing, deleted/tombstoned, archived, unsupported or foreign rows
fail the entire decision; partial evidence is never accepted. A GitHub issue
proposal must cite the exact canonical repository named by its payload, so a
real but unrelated repository is also insufficient. The same resolver powers
Headquarters visibility, approval and execution. External execution validates
once before creating its durable claim and again after the committed
`running` transition immediately before provider I/O. If evidence becomes
invalid between those points, the attempt becomes a definitive pre-provider
failure, the proposal returns to approved and no provider call occurs.

AI/system approval additionally requires the exact visible
`headquarters.v3` snapshot and exact proposal version. Such proposals are
reviewed from Headquarters; the generic Actions screen does not fabricate a
snapshot. User rejection remains possible without valid evidence because
discarding an unsafe proposal is not an assertion that its evidence is true.

Bulk approval and rejection use the same `decide_action_proposal` service as a
single decision. Each item supplies its proposal UUID, exact `ap1_*` version,
client idempotency key and optional `hqs1_*` snapshot. Duplicate proposal IDs
are invalid input. Each successful item gets its own durable decision receipt
and audit event with the authenticated user; partial failures do not weaken
the successful items' contracts. Repo-audit import retains its bounded finding
summary but discards arbitrary external evidence strings and stores only a
canonical repository selector.

This gate proves referential existence, workspace scope, lifecycle state and
machine-checkable target relevance. It does not claim semantic truth for
free-form prose or replace the future generative AI critic. PostgreSQL/raw
storage remain authoritative, and no LLM may approve or execute a proposal.

## DEC-102 - Workspace-Owned References Use Composite Database Keys

Decision (2026-07-29): PostgreSQL, not only application services, must reject a
child row whose workspace differs from its workspace-owned parent.
`EvidenceRef→SourceRecord`, `PullRequest→Repository`,
`PullRequest→SourceRecord`, `Task→SourceRecord` and
`DocumentVersion→Document` therefore use composite
`(workspace_id, referenced_id) → (workspace_id, id)` foreign keys. Referenced
Repository and Document rows gain the required `(workspace_id, id)` uniqueness;
SourceRecord already has it.

The migration performs a read-only preflight and fails closed if any existing
cross-workspace relationship is present. It does not silently rewrite, delete
or reassign evidence or product records. Every relationship has a negative
database test that attempts the invalid commit. GitHub operational reads also
join SourceRecord and hydrate Repository with an explicit workspace predicate,
so query scoping remains visible even though corrupt relationships are now
unrepresentable through these keys.

PostgreSQL row-level security was evaluated but is not enabled piecemeal in the
current local/operator deployment. Correct hosted RLS requires a dedicated
least-privileged application role without owner or `BYPASSRLS`, transaction-
local workspace/user context on every request and background job, `FORCE ROW
LEVEL SECURITY` policies across all workspace-owned and join tables, verified
pool context reset, a separate migration/administration role and cross-tenant
integration tests. A partial policy set would create a misleading security
claim and can break maintenance paths while leaving uncovered tables readable.
Public multi-tenant hosting is therefore blocked until that complete gate is
implemented and startup fails closed when the hosted mode requires it.

## DEC-103 - Static Typing And Frontend Lint Are Executable Quality Gates

Decision (2026-07-29): `mypy app` is a required backend check locally and in
CI. The repository configuration checks function bodies even when their
signatures are not yet fully annotated, rejects implicit Optional ambiguity
and reports unreachable code, redundant casts and stale ignores. The initial
gate is clean across all application modules; future changes may not suppress
errors broadly or replace runtime validation with type assertions.

Frontend lint must be independent from TypeScript compilation. Next.js no
longer supplies `next lint`, so FounderOS uses a pinned Biome CLI and runs it
with warnings treated as failures over application, component, library and
test sources. Next/React, correctness, accessibility and security rules are
enabled. Narrow rule exceptions require an adjacent reason tied to the exact
line; project-wide weakening for a single legacy pattern is not accepted.
Formatting remains outside this gate to avoid unrelated mechanical rewrites.

Dependency selection is part of the gate. The committed lockfile must resolve
with `npm ci`, and both full and production package audits must be clean at the
time of verification. Typecheck, lint, tests and production build remain
separate commands so one passing tool cannot masquerade as another.

## DEC-104 - Runtime Health And Browser Smoke Are Separate Evidence Layers

Decision (2026-07-29): `/health` remains an unauthenticated, dependency-free
liveness probe. `/health/ready` is a separate minimal public readiness probe
that executes a timeout-bounded PostgreSQL `SELECT 1` and returns 503 without
database detail on failure. Operator-only `/health/metrics` exposes only
process uptime, in-flight, total, 4xx and 5xx counters; it has no route, user,
workspace or provider labels.

Request completion is an active structlog JSON event with a server-generated
opaque request ID, method, path-only, status and duration. The same ID is
returned in `X-Request-ID`. Queries, headers, cookies, bodies, credentials,
identities, source text and provider payloads remain outside logs and metrics.
These counters and IDs improve local/private operation but are not a claim of
distributed tracing or external error reporting; a hosted release still
requires an approved privacy-bounded telemetry sink.

Backend API responses and Next.js pages apply CSP, frame, referrer,
permissions, nosniff and opener policies; non-local responses add HSTS.
FastAPI OpenAPI, Swagger and ReDoc are reachable only in local-like
environments. Cookie-authenticated mutations and the three public
cookie-issuing auth endpoints require an exact allowed Origin or Referer outside
local-like environments.

Smoke evidence is split instead of overstated. Public liveness performs no
login. Session smoke performs a real login, checks the same cookie twice and
logs out. Workspace smoke additionally reads exact Workspace, Headquarters,
Company Brain and provider connection state. Playwright runs the real product
on desktop and mobile Chromium, reloads the session, opens the four primary
zones and rejects console warnings/errors or horizontal overflow. It disables
screenshots, video and traces so private company UI is not retained as a test
artifact.

## DEC-105 - Public Argon2 Work Uses One Shared Admission Boundary

Decision (2026-07-29): login, founder invite consumption and teammate password
setup must acquire admission before Argon2. The existing per-email PostgreSQL
lockout remains credential protection; admission separately bounds per-client,
global and concurrent expensive work. The process backend is valid only for
the documented single-process runtime. An approved multi-worker topology must
select the Redis backend, which atomically checks and increments all three
budgets in one Lua script. Raw client addresses are SHA-256 bucket keys, not
Redis keys or logs. Redis unavailability returns a generic 503 and performs no
Argon2 work; abandoned in-flight leases expire automatically.

`X-Forwarded-For` is ignored by default. When proxy forwarding is enabled, the
direct peer must be an IP inside an explicit trusted CIDR before the first
forwarded IP can become the limiter/session metadata address; malformed or
untrusted forwarding falls back to the direct peer. SameSite is constrained to
a typed set, and non-local startup rejects `none` because FounderOS is a
first-party same-origin product.

A bounded background task removes expired sessions, expired teammate setup
token hashes and expired founder invite hashes. Revoked sessions have a short
configured retention before removal. Session validation updates
`last_seen_at` only after a configured minimum interval, eliminating the
previous write on every authenticated request. Cleanup and admission never
read or log bearer values.

## DEC-106 - Runtime Dependencies Must Be Used, Audited And Reproducible

Decision (2026-07-29): every imported third-party Python package is declared
directly. `cryptography`, `starlette` and `python-dotenv` are therefore
explicit runtime dependencies instead of accidental transitive dependencies.
SDKs with no runtime path are not retained as speculative capability: the unused OpenAI,
Google API/OAuth and retry packages, their lock graph, obsolete provider
settings, placeholder operator variables and the legacy Google/Telegram
launcher were removed. The reserved LLM feature gate and key names remain
configuration contract only; they do not imply that a provider SDK or
generative execution path exists.

The guarded backend checker and CI audit the installed Python environment with
`pip-audit`; CI audits both runtime and development frontend dependencies.
Known vulnerabilities are fixed by dependency upgrades, not ignored. The
minimum supported `pydantic-settings` and direct `starlette` versions exclude
the advisories found when this gate was introduced. Lockfiles remain required
and vulnerability results are current-state evidence, not a permanent
security claim.

Local PostgreSQL and Redis images retain readable major-version tags but are
also pinned to exact multi-platform manifest digests. Renovate's
`docker-compose` manager updates tag and digest together with a release-age
delay. CI container images remain digest-pinned. A human still reviews and
tests image and dependency updates before they are merged.

## DEC-107 - GitHub Provider Reads Use Durable Leased Jobs

Decision (2026-07-29): a GitHub App live-read API request may validate the
workspace, role, connection and requested repository scope, then persist one
queued `SyncJob` and return `202`. It must not mint a provider token, call
GitHub or normalize provider data while the request transaction is open.

PostgreSQL is the queue source of truth. Workers claim eligible jobs with
`FOR UPDATE SKIP LOCKED`, a unique lease owner, expiry and bounded attempt
count. Concurrency is explicitly limited to one through four workers and all
workers in a process share one bounded HTTP connection pool. A stale lease is
recoverable; already completed repository names and cumulative counts are
durable progress, so a resumed job does not re-read or re-normalize completed
repositories.

Provider I/O happens without an open SQL transaction. Each successfully read
repository is normalized and committed in its own short transaction. Complete
all-state reads retain the authoritative reconciliation rules from DEC-098.
Transient provider failures use bounded exponential retry; invalid
configuration fails terminally. Durable errors and logs use controlled generic
messages/codes and never persist provider exception detail.

Installation access tokens exist only in worker memory. Durable request and
progress cursors contain selected repository names, safe scope flags, counts
and repository summaries, but no token or raw provider response. Cancellation
is owner/admin-only, immediately marks the job terminal and revokes its lease;
a worker holding an in-flight response then loses the lease and discards that
result instead of committing it.

The product polls the workspace-scoped job endpoint until `succeeded`,
`partial`, `failed` or `cancelled`, keeps duplicate launch controls locked,
renders cumulative progress and offers an explicit cancel action. Process
restart does not lose queued work because claim, retry and resume state remains
in PostgreSQL.

## DEC-108 - Disaster Recovery Requires An Independent Encrypted Copy

Decision (2026-07-29): a restore-proven bundle under `.local/backups/` is a
same-machine rollback boundary, not disaster recovery. FounderOS disaster
recovery requires an exact verified local bundle encrypted with AES-256-GCM on
founder-controlled storage that is physically independent from the application
machine. The encryption key must stay outside both the repository and backup
target, with a separately recoverable founder-owned copy.

The exporter validates exact bundle membership, checksums, raw-storage
inventory and the existing full-restore receipt, then decrypts and validates
its new artifact before promotion. A restore drill must decrypt the artifact,
repeat the isolated matching-major PostgreSQL restore, compare sanitized schema
and counts, verify connector-credential decryptability and remove the temporary
cluster. Decryption without this proof is not a successful drill.

The operating target is a 24-hour RPO, four-hour RTO, daily exports, weekly
restore drills and 7 daily / 4 weekly / 12 monthly recovery points. Retention is
dry-run by default and destructive pruning is always explicit. The repository
does not select or create real independent storage, escrow a key, replace
production state or delete old resources. Until the founder configures the
external target and records the first real drill, disaster-recovery
implementation is complete but operational readiness remains an external gate.

## DEC-109 - Repository Governance Is Private And Owner Controlled

Decision (2026-07-29): FounderOS remains private proprietary source with no
implicit right to use or redistribute it. The repository carries an explicit
private-source license notice, private vulnerability-reporting policy,
contribution workflow and CODEOWNERS rule for the repository owner.

The repository-owned pre-commit hook checks staged secrets and whitespace,
Ruff, application mypy, frontend typecheck and frontend lint. Hook installation
is explicit through `make hooks-install`; CI and guarded test commands remain
the authoritative shared gates. Hosted branch protection, private reporting
channel configuration and repository visibility are owner-controlled GitHub
settings and must be verified separately rather than inferred from files.

## DEC-110 - Large Modules Use Tested Ratchets And Bounded Extraction

Decision (2026-07-29): M16 is handled as a continuous maintainability control,
not a one-shot broad rewrite. The audited Headquarters, action, GitHub, CSS and
large frontend modules have explicit line-count ceilings. Crossing a ceiling
requires a reviewed budget decision or a smaller module; the budget is a
ratchet against further decline, not evidence that every current file is
already ideally sized.

Characterization remains the full backend/frontend suite. Concurrency is
explicitly proven for durable GitHub job claims and canonical upserts. A
Headquarters query-budget test compares one versus one hundred SourceRecords
and rejects per-row SQL growth without relying on flaky wall-clock timing.

The first bounded extraction moves action API request/response contracts into a
dedicated schema module. The superseded selected-issue and selected-PR live
sync endpoints, services and endpoint tests are deleted: they were unused by
the product, duplicated about a thousand implementation lines and still
performed provider I/O inside an API-owned SQL session. The unified GitHub App
`202` durable job is the only live repository-read route. Historical normalized
source labels remain readable so removing the execution path does not erase
canonical company memory.

Further work must lower budgets through characterized slices. Large
Headquarters, ActionProposalsPanel and global CSS refactors remain inappropriate
without focused behavior/performance coverage for the exact slice being moved.

## DEC-111 - Generative Second Opinion Is Snapshot-Bound And Evidence-Criticized

Decision (2026-07-29): `assistant.v2` retains the deterministic `assistant.v1`
fallback and adds an optional read-only generative path over the exact visible
`hqs1_*` Headquarters snapshot. Generative execution requires all three
server-side gates: `ENABLE_LLM=true`, a secret OpenAI API key and explicit
acknowledgement of the provider data policy. A missing gate, provider error,
refusal, timeout, incomplete result, invalid schema or failed evidence check
returns the deterministic answer with a controlled warning; provider details
and response bodies are not exposed.

The runtime uses the fixed HTTPS OpenAI Responses endpoint directly through the
already-audited HTTP client. It sends no raw provider payload, source body,
credential, chat history or database identifier. The request contains only the
current question, at most sixteen bounded normalized facts derived from the
workspace-scoped Headquarters projection, an opaque SHA-256 safety identifier
and a strict JSON schema. `store=false`, `reasoning.context=current_turn`, a
bounded output budget, no tools and no continuation response ID prevent
FounderOS application state or cross-turn reasoning from being created through
this path. The API key is a `SecretStr`, remains server-only and is never
returned to the browser.

Every response has explicit fact, interpretation, objection and recommendation
sections. The model may select only retrieval fact IDs. The local critic rejects
unknown IDs, duplicate or absent support, unresolved citations, extra schema
fields and any factual sentence that is not an exact retrieved fact. Derived
sections must resolve through their cited facts to canonical evidence in the
same response. This validation proves evidence linkage and strict shape; it does
not prove that every interpretation is strategically correct, so the UI labels
the result as a second opinion and keeps exact evidence and snapshot boundaries
visible.

The LLM cannot create, approve, reject or execute an ActionProposal. Explicit
action requests continue through the deterministic human-confirmation boundary
without a model call. Neither the question, prompt, provider response, response
ID nor generated answer is persisted or logged by FounderOS.

`store=false` disables Responses application-state persistence but is not, by
itself, a Zero Data Retention agreement. Under the provider's documented
default, abuse-monitoring logs may retain customer content for a limited period;
eligible organizations require separately approved Modified Abuse Monitoring
or Zero Data Retention controls. The dedicated acknowledgement gate makes that
external policy an explicit operator decision. A real credentialed call,
cost/latency evaluation, organization retention verification and product
settings control remain operational acceptance gates rather than simulated
evidence.

Provider contract references:
[Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs),
[current model guidance](https://developers.openai.com/api/docs/guides/latest-model?model=gpt-5.6)
and [data controls](https://developers.openai.com/api/docs/guides/your-data).

## DEC-112 - Workspace AI Control Is Encrypted, Explicit And Fail-Closed

Decision (2026-07-29): the primary product control for generative AI lives at
`/settings/ai` and is owned by one workspace. Owner/admin users may save an
OpenAI API key, choose an allowlisted model, reasoning effort and output budget,
acknowledge the current provider data policy, enable the optional path, run a
read-only connection check and remove the credential. Workspace members may
read only safe status. The API never returns the stored credential or encrypted
value, and every response is private/no-store.

The key is encrypted with the existing server-managed secret-encryption
boundary before PostgreSQL persistence. Applying settings performs no provider
call. The explicit check closes its SQL session before provider I/O and sends
only one synthetic statement that contains no company fact, workspace name,
email, raw source body or database identifier. Only a safe status/code/model
receipt is persisted. A configuration version prevents a result from an older
key or model being accepted after settings change.

The generative assistant may use workspace settings only when the server
`ENABLE_LLM` emergency kill switch is open, the workspace explicitly enables
AI, the current provider policy was acknowledged, an encrypted key exists and
the latest check passed. A saved workspace row is authoritative and never
silently falls back to an environment credential. The original compatibility
fallback for a workspace without a row was removed by DEC-114. Removing the
credential clears the encrypted value, policy acknowledgement and check receipt
and disables AI; it does not remove canonical company memory or evidence.

The check validates network authorization plus the same strict response and
evidence contract used by `assistant.v2`; it does not prove commercial quota,
future provider availability, strategic answer quality or Zero Data Retention.
A real founder-approved credentialed smoke and provider retention verification
remain external operational gates.

## DEC-113 - Memory Correction Deletes Superseded Local Versions

Decision (2026-07-29): Memory Control v1 begins with content authored inside
FounderOS because its complete storage boundary is known. `/settings/memory`
lists internal documents without loading every body, then opens one exact
document plus a content-free memory preview. Owners/admins may either replace
the document and purge every prior `DocumentVersion`, leaving one new canonical
version, or forget the document and all versions. Ordinary edits continue to
append history; only the explicitly destructive memory paths purge it.

Both operations bind to the previewed `updated_at` and exact version count,
lock the document row and fail with a conflict if anything changed. They use a
second explicit UI confirmation and fixed request confirmation code, make no
provider call, external write or LLM call, and persist no deletion request,
reason, old body or receipt. The legacy direct DELETE route is removed so an
unguarded API call cannot bypass the preview. Workspace viewers may inspect the
safe preview; only owner/admin may correct-and-purge or forget.

The response states only what can be proved. Active PostgreSQL rows are removed,
but dead tuples, WAL and encrypted backups are not claimed to disappear
immediately; backup retention applies until the configured rotation removes
them. Provider-backed GitHub/Jira/Gmail/Drive records are not supported by this
operation. Their canonical evidence and provider source cannot be called
forgotten until a separate dependency-aware cascade, reconciliation behavior
and provider-side deletion boundary are designed and tested.

## DEC-114 - Provider Credentials Are Workspace-Owned And UI-Only

Decision (2026-07-30): provider credentials are product data, not deployment
configuration. OpenAI, GitHub, Jira, Gmail and Google Drive credentials may be
created, replaced, checked and removed only through authenticated workspace
Settings. They are encrypted before PostgreSQL persistence, are never returned
to the browser, and have no environment fallback.

The OpenAI environment key/model/policy defaults and the GitHub App
id/slug/private-key/webhook environment path are removed. GitHub token minting
requires an active decrypted workspace credential. The manual GitHub App
installation-record endpoint and its offline env-presence preflight are
removed; the verified self-service manifest/install/OAuth/repository-selection
flow is the only GitHub App onboarding path. The legacy local organization
snapshot promotion script and password-through-env admin creation script are
also removed because they bypass the product-owned identity or connector
lifecycle.

`.env.local` is the only dotenv file loaded by the local runtime. It is reserved
for prerequisites that must exist before the UI can run: database/Redis
topology, raw-storage paths, the master credential-encryption key, recovery
material references, public origins, process controls, kill switches and
bounded worker/timeout settings. `.env.example` is a placeholder-only
bootstrap/deployment reference. Hosted operation must move root encryption and
recovery material to an infrastructure secret manager or KMS boundary; putting
the key inside the encrypted database would be circular.

`ENABLE_LLM` and connector/write flags remain emergency runtime gates. They can
disable capability but cannot supply a provider credential or override
workspace model/policy settings. If workspace AI is absent, disabled,
unacknowledged, missing a key or not successfully checked, the assistant remains
deterministic. If a managed GitHub credential or installation relation is
missing, live reads fail closed.

This boundary deliberately does not claim that every secret can be entered in
the browser. Database credentials, the master encryption key, cookie/operator
bootstrap material and disaster-recovery keys cannot depend on the database/UI
they are required to start or recover.

## DEC-115 - Repository Intelligence Begins With One Strict Synthetic Contract

Decision (2026-07-30): Repository Intelligence v1 begins with a validation-only
boundary before any repository checkout, provider read, database migration,
runtime worker, UI, LLM analysis or external action. The versioned
`repository_intelligence.v1` payload separates a trusted FounderOS envelope
from the untrusted analyzer result. FounderOS supplies `workspace_id`,
`repository_id`, stable provider identity, audit level, analysis target,
profile, policy hash and engine version; an analyzer cannot choose tenancy,
canonical persistence identity, human decisions, reconciliation state or
actions.

Repository identity requires GitHub provider, stable provider `external_id` and
current `full_name`; owner/name alone is not identity. L0 may explicitly report
an unavailable commit target because current canonical Repository rows do not
store a SHA. L1 and L2 require an exact lowercase full SHA-1. Analyzer claims
use only `observed`, `inferred` or `insufficient_evidence`. Human
`confirmed`/`rejected` outcomes require a separate actor-and-timestamp contract,
and stale state belongs only to future reconciliation. Analyzer findings may
start only as `new` or `insufficient_evidence`; persisted lifecycle values such
as open, resolved, regressed, accepted risk and false positive are not analyzer
authority.

Repository Intelligence reuses the existing object-shaped
`evidence_ref.v1` validation rather than promoting legacy repo-audit
`list[str]` evidence or creating a fourth evidence format. Observed and inferred
facts, relationships and findings require evidence; an explicit
`insufficient_evidence` result may remain empty. Confidence is finite and
bounded to `[0.0, 1.0]`. Every model rejects unknown fields, strings and
collections are bounded, and the complete serialized payload is capped at
64 KiB.

Relationships use canonical directional types without a free-form direction
field. Self-edges, cross-workspace edges, unknown or inverse-view relationship
types and duplicate normalized edges fail closed. Symmetric edge endpoints are
normalized deterministically. Unresolved targets remain candidates without a
canonical repository UUID. Contradictions preserve both evidence-backed claims
through stable claim references; dangling, self or duplicate contradiction
pairs are rejected rather than silently repaired.

RI-001 is proven only with repository-owned synthetic L0/L1/L2 fixtures. It
does not read, clone or execute any company repository and adds no persistence,
migration, API or UI. The next bounded slice is RI-002: a read-only,
workspace-scoped L0 projection from synthetic canonical Repository and
SourceRecord data. Durable storage remains RI-006.

## DEC-116 - Repository Intelligence L0 Reads Canonical Workspace Rows Only

Decision (2026-07-30): RI-002 is a read-only projection over canonical
`Repository` rows and active repository `SourceRecord` rows for one explicit
workspace. The SQL join includes workspace, provider, external ID, record type
and active-state predicates. A workspace-scoped RI read never falls back to
filesystem discovery, retained legacy `SourceEvent`, the static repository
portfolio or a provider call. An empty canonical workspace returns an empty
result rather than unrelated compatibility data.

L0 validates the joined SourceRecord again before using it as evidence:
`normalized_repository.external_id` and `full_name` must match the canonical
Repository identity exactly. Tombstoned, malformed or identity-mismatched
records are ignored. Evidence uses the SourceRecord UUID through the RI-001
`evidence_ref.v1` contract. Unsafe or credential-bearing URLs are removed rather
than copied into the result.

The current canonical Repository model has no exact commit SHA, so every RI-002
result uses `target_status=unavailable` and explicitly records exact SHA as an
unknown. Repository purpose is not inferred from a name. It remains
`insufficient_evidence` unless identity-matching canonical SourceRecord metadata
contains an allowlisted `repository_type_candidate`; that candidate is labelled
`inferred`, never confirmed. The only L0 lifecycle finding currently emitted is
an archived-repository fact, and it requires matching canonical evidence.

RI-002 makes no database write and adds no migration, API, UI, checkout,
provider network path, LLM call or target execution. It is verified only with
synthetic frontend, backend and infrastructure rows in the dedicated test
database, including cross-workspace, tombstone, identity mismatch, unsafe URL,
unknown-state, deterministic and no-mutation tests. The next bounded slice is
RI-003 safe checkout management, which still requires separate approval.

## DEC-117 - Repository Checkouts Are Exact, External, Read-Only And Ephemeral

Decision (2026-07-30): RI-003 materializes an approved full lowercase SHA-1
from a synthetic local standalone Git repository into
`FOUNDEROS_REPOSITORY_INTELLIGENCE_DATA_PATH`. The setting defaults to the
`founderos-ri-data` sibling of the FounderOS repository and must resolve outside
the FounderOS tree and outside the source repository. The source must itself be
outside FounderOS, cannot be a symlink, linked worktree or subdirectory, and its
git metadata cannot use symlinks, include files or external alternates.

The manager does not call `clone`, `fetch`, `checkout` or `worktree`. It uses
only trusted git object-reading commands with a minimal credential-free
environment, terminal prompting disabled and protocols denied. It resolves the
exact commit, validates a bounded `ls-tree` manifest and materializes allowed
regular blobs with `cat-file`. Symlinks, gitlinks, unsupported objects, `.git`
paths, traversal, portable case/Unicode collisions and file-directory
collisions fail closed. Target repository files and hooks are never executed.

Checkout policy bounds total wall time, git command output, file count, total
bytes, per-file bytes, path bytes and path depth. Materialized files and
directories become read-only. Each run gets one private external directory,
and cleanup is verified and attempted on success, validation failure, consumer
exception and cancellation. Errors are sanitized and never return git stderr,
source paths or file content.

RI-003 does not add a migration, persistence model, API, UI, provider portfolio
read, network dependency, scanner, LLM call or real company-repository access.
It is proved only with locally created synthetic repositories, including exact
historical SHA, path, bound, timeout, output, failure, cancellation, cleanup,
symlink, gitlink, alternates and no-execution tests. The next bounded slice is
RI-004 static collectors and still requires separate approval.

## DEC-118 - Static Repository Facts Are Bounded, Sanitized And Non-Executable

Decision (2026-07-31): RI-004 reads only a materialized RI-003 exact-SHA
checkout that declares read-only files, no target execution and no network use.
It performs deterministic static inspection for recognized manifests,
entrypoints, dependencies, HTTP/schema interfaces, deployment definitions,
tests/CI, documentation and migrations/data objects. It never imports source
modules, invokes a target command, loads a provider credential, follows a link,
persists a result or emits a source-file body.

The collector validates its policy, checkout boundary and immutable
file-count/byte manifest before inspection. File count, total bytes, per-file
bytes, path bytes, path depth, wall time, dependencies per manifest and items
per output category are explicit fail-closed bounds. Only recognized bounded
UTF-8 files are parsed. Oversized recognized files may be recorded as skipped;
invalid recognized JSON/TOML manifests fail with sanitized errors rather than
being repaired or copied.

Output uses strict `repository_static_collection.v1`. Each fact contains a
stable category/type, sanitized identifier or relative path and one
object-shaped `evidence_ref.v1` selector bound to repository identity, exact
SHA and path. File bodies, dependency versions, script commands, environment
values and infrastructure contents are not retained. Facts can be projected
into the existing strict RI-001 `RepositoryClaimV1` boundary, and stable sorted
JSON proves deterministic output.

RI-004 is verified only with local synthetic frontend, backend, infrastructure
and pathological repositories. It adds no migration, persistence model, API,
UI, provider/company repository read, relationship inference, LLM call or
target execution. RI-005 directional relationship candidates remain a separate
approval-gated slice.

## DEC-119 - Repository Relationships Are Directional Candidates Before Persistence

Decision (2026-07-31): RI-005 consumes only strict synthetic RI-004 collections
and a trusted workspace-scoped `repository_portfolio.v1` manifest. The manifest
supplies canonical repository IDs plus explicit unique selectors for packages,
APIs, events, images, deployment targets, tests and documentation. Repository
name similarity, shared language, shared framework or same organization never
creates an edge by itself.

Only explicit relationship-bearing facts or strict evidence-backed signals may
create `RepositoryRelationshipV1` candidates. Machine-readable clues remain
`observed`; weaker explicitly supplied clues remain `inferred`; both keep
human resolution pending. Every edge requires object-shaped evidence. A target
that does not resolve uniquely remains an unresolved candidate reference and
cannot claim a canonical repository UUID. Ambiguous selectors, cross-workspace
inputs, self-edges and evidence-free signals fail closed.

Directional relationship types retain one canonical durable direction.
Inverse wording is a deterministic view, not a second edge. Symmetric types
normalize endpoint order and merge evidence deterministically. Duplicate edges
are collapsed only after exact stable-identity normalization. Opposing
directional candidates between the same repositories are not silently accepted
or selected; RI-005 fails closed and requires a later explicit contradiction
review.

The graph pass is bounded by repository, signal, edge, evidence, cycle depth,
finding and serialized-output limits. It reports strongly connected components
as cycles, repositories with no candidate edges as orphans, and unresolved
targets as findings. These are analyzer outputs, not persisted lifecycle state
or human confirmation.

RI-005 is verified only with synthetic package, API, event, deployment,
unresolved, symmetric, cycle, orphan, ambiguity, workspace and pathological
fixtures. It performs no repository read, target execution, provider call,
network operation, persistence, migration, API, UI or LLM call. RI-006
persistence remains separately approval-gated and requires a branch/PR plus
reviewed migration.

## DEC-120 - Repository Intelligence Persistence Is Coverage-Gated And Workspace-Safe

Decision (2026-07-31): RI-006 runs on the dedicated
`codex/repository-intelligence-persistence` branch and adds review-ready migration
`11c7b724c929`. It persists separate `RepositoryAnalysisJob`,
`RepositoryAuditRun`, `RepositoryFact`, directional
`RepositoryRelationship`, `RepositoryAuditFinding`,
`RepositoryContradiction` and `RepositoryEvidenceLink` rows. PostgreSQL and the
approved raw-storage boundary remain sources of truth; no graph database,
full checkout, source body or unbounded scanner payload is stored in PostgreSQL.

Each run creates exactly one sanitized internal `SourceRecord` manifest plus a
bounded artifact manifest. Large sanitized artifacts belong in approved raw
storage and PostgreSQL stores only opaque
`repository-intelligence/...` references, SHA-256, type and byte size. Checkout
retention is zero after the RI-003 context exits. Artifact refs expire after
30 days and are cleared only after external deletion succeeds. Jobs, run
headers, facts, relationships, findings, contradictions, canonical evidence
and human decisions remain workspace-canonical until explicit
repository/workspace deletion or a later approved retention change. Backups
remain subject to the existing backup retention boundary.

Jobs are a dedicated `RepositoryAnalysisJob`, not reused `SyncJob`, because
their exact SHA/profile/policy/engine identity and retries are independent of a
provider connection. Owner/admin membership is required to enqueue or delete;
workers use bounded leases, sanitized error codes, retry limits and
cancellation. The idempotency key is workspace-scoped and bound to a request
hash. One job accepts one immutable result; replay is allowed only when result,
coverage and artifact hashes match exactly. A new job may intentionally
reanalyze the same SHA/policy/engine and creates a new historical run.

One run is `complete` only when its audit-level coverage set contains every
required check and no required check failed or was skipped. L0 requires
canonical metadata. L1 requires manifests, entrypoints, dependencies,
interfaces, deployment, tests/CI, documentation, migrations and relationships.
L2 additionally requires the separately approved isolated-execution check.
Only a succeeded complete run may reconcile absence. Partial, failed and
cancelled runs never stale facts/edges or resolve findings/contradictions.

Complete reconciliation matches stable fingerprints, updates `last_seen`,
stales absent facts and relationships, resolves absent findings and
contradictions, marks reappearing resolved findings `regressed`, and preserves
human `accepted_risk`/`false_positive` plus fact/relationship
confirmed/rejected provenance. Policy/profile/engine are part of the
reconciliation cohort, so a rule-engine change cannot masquerade as a code
fix.

Repository Intelligence reuses the canonical `EvidenceRef` table. RI-006 adds
nullable strict object-shape metadata (`evidence_key`, kind, source and
selector) without changing legacy rows, and links facts/edges/findings/
contradictions through same-workspace composite FKs. Analyzer evidence without
an existing evidence UUID is materialized against that run's sanitized internal
SourceRecord; cross-workspace evidence is rejected. The migration downgrade
locks all RI tables and refuses non-empty state instead of silently deleting
durable intelligence.

RI-006 is verified only with synthetic PostgreSQL data. It adds no company
repository read, target execution, provider/network call, API, UI, portfolio
run or LLM call. RI-007 read APIs and UI remain separately approval-gated after
review/merge of this branch.

## DEC-121 - Setup Tokens And Provider Requests Stay Server-Bound

Decision (2026-08-02): one-time GitHub App manifest, installation and OAuth
state is persisted only as a domain-separated keyed digest derived from the
existing fail-closed secret-encryption key boundary. A raw SHA digest is not a
password hash, but it still permits offline verification of a stolen one-time
state candidate; keyed verification removes that unnecessary capability while
preserving the existing 64-character indexed database contract. Missing server
key material fails the setup flow closed rather than falling back to an
unkeyed digest.

New encrypted provider secrets use a versioned `fernet:v2` envelope whose key
is derived with HKDF and domain separation. Existing `fernet:v1` ciphertext is
read-only compatible so credential migration is non-destructive; all new writes
use v2.

GitHub App provider requests use an HTTP client whose origin is fixed to
`https://api.github.com`. Callback-derived manifest codes and installation IDs
must pass strict shape validation and are encoded only as relative path
segments. User-controlled input cannot select a request scheme, host, port or
absolute URL. Provider response and permission validation remain unchanged.

Operator-visible bootstrap output is a status-only receipt. Detailed migration
inventory remains available to in-process callers and the private
`migration-log.json`, but absolute local paths, environment-derived values and
secret-shaped material are never serialized to stdout. Frontend connector
errors are classified by exact backend error contracts, not by hostname
substrings, and URL expectations in tests do not use unanchored regular
expressions.

These changes resolve the critical/high CodeQL findings discovered while
preparing the accumulated FounderOS reset and RI-001–RI-005 branch for merge.
They do not enable provider reads, change production CORS defaults, begin
RI-006/RI-007 behavior or weaken existing encryption and workspace boundaries.
DEC-120 records the RI-006 persistence decision merged through PR #34 on
2026-08-02.

## ASK - Open Questions For The Human (not decided)

These are genuinely ambiguous and are NOT resolved by the playbook alone:

- **ASK-1 — ✅ RESOLVED → DEC-073/DEC-074.** Company World product intent and the
  physical `Person`/`Organization`/`Affiliation`/`Interaction` plus resolution
  boundary are now explicit. Playbook §6.24–§6.28 records the canonical shapes;
  the old informal model count is not used as a migration requirement.
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
