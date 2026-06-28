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

- `docs/deploy/railway-private-beta.md` is the target-specific dry-run plan.
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

## ASK - Open Questions For The Human (not decided)

These are genuinely ambiguous and are NOT resolved by the playbook alone:

- **ASK-1 — The "23 models" count and the missing `Person` entity.** §6 defines
  22 entity sections (6.2–6.23); the historical EXECUTION_PLAN/FOS-002 wording
  said "23 модели". §6.9
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
