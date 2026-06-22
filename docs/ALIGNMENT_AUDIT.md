# founderOS Repo Alignment Audit

Status: read-only alignment snapshot captured from the repository audit against
`founderOS_MASTER_PLAYBOOK.md`.

This document is an audit record, not an implementation plan. It must not be
used as approval to edit application code, run live providers, create
migrations, or execute external writes.

## 1. Executive Summary

The repository is technically healthy but not fully aligned with
`founderOS_MASTER_PLAYBOOK.md`.

- Current confirmed phase: approximately Phase 2 - Backend Core.
- The project should continue from the current base. Do not rewrite from
  scratch.
- The backend foundation is strong: FastAPI, SQLAlchemy, Alembic, Postgres,
  guarded providers, evidence-first extraction, and broad tests are present.
- Phase 1 canonical models are incomplete: the master playbook's User,
  Workspace, Membership, IntegrationConnection, SyncJob, Briefing,
  BriefingItem, ActionProposal, and ActionExecution models are not present as
  canonical SQLAlchemy tables/classes.
- Phase 3 Next.js frontend is absent: there is no `web/` app or root
  `package.json`; the current UI is a static local/operator SPA at `/ui`.
- Phase 4 GitHub-first E2E is absent: GitHub OAuth -> GitHub sync ->
  SourceRecords -> normalized entities -> Dashboard -> Company Brain ->
  Briefing -> approved GitHub issue creation is not implemented end to end.
- Main process risk: the dirty tree is broad and should be checkpointed and
  split by scope before further implementation.

## 2. Current Repository State

| Area | Current state |
| --- | --- |
| Stack | Python 3.12, FastAPI, SQLAlchemy async, Alembic, Postgres, Redis, Pydantic, OpenAI SDK gated, uv, ruff, pytest. |
| Backend | Modular FastAPI app with protected API routers, services, guarded provider boundaries, and local founder read models. |
| Frontend | Static local/operator UI at `/ui`; no master-playbook Next.js app yet. |
| Database | Event/source/attention/graph/agent proposal/source control/share pack models exist; canonical workspace/integration/briefing/action models are incomplete. |
| Migrations | Existing Alembic migrations are present and migration head/current were clean in the audit environment. |
| Tests | Large backend test suite passed during audit. |
| Connectors | GitHub/Jira/Gmail/Drive read-only and guarded surfaces exist; production OAuth/write E2E is not productized. |
| AI modules | Deterministic extraction exists; LLM paths are gated/off by default; evidence validation exists. |
| Docs | Current docs describe a v2 local/operator path that differs from the master playbook's MVP order. |
| CI/dev tools | CI/security/dependency automation files exist in the dirty tree and need separate review before checkpoint. |

## 3. Git Status Snapshot

Audit snapshot before these alignment docs:

- Modified tracked files: 77.
- Untracked files: 18.
- Staged files: none.
- Diff stat: 3483 insertions, 2445 deletions across 77 tracked files.

The dirty tree contained changes across CI, README/security docs, API routes,
configuration, services, static UI, docs, scripts, and tests. This is too broad
for one routine MVP task and should be split by scope before implementation
continues.

## 4. Mapping Against Playbook

| Phase | Current status | Done | Missing | Blocked or extra |
| --- | --- | --- | --- | --- |
| Phase 0 - Project Setup | Partially done | Repo audit completed; checks recorded; docs now being created. | Clean checkpoint and scope split. | Existing dirty tree is broad. |
| Phase 1 - Database / Core Models | Partially done | Event/source/evidence/attention/graph/audit-adjacent tables exist. | Canonical User, Workspace, Membership, IntegrationConnection, SyncJob, SourceRecord alignment, Briefing, ActionProposal, ActionExecution. | No migration should be created until reconciliation spec is approved. |
| Phase 2 - Backend Core | Mostly present but not master-complete | FastAPI services, guards, source control, evidence validation, read models. | Workspace-aware auth, canonical connector/sync/action services by playbook contract. | Some post-MVP/operator surfaces already exist. |
| Phase 3 - Frontend Core | Partially done | Static local/operator `/ui` exists. | Next.js + TypeScript + Tailwind + shadcn UI shell. | Do not scaffold web app in this audit docs task. |
| Phase 4 - GitHub-first E2E | Missing | Read-only GitHub evidence/source pieces exist. | GitHub OAuth, sync, normalized entities, dashboard, briefing, approved GitHub issue creation. | Must decide OAuth vs Source Control product path first. |
| Phase 5 - Edge Cases & Polish | Partially ahead of schedule | Guarded errors, source receipts, retries, data quality surfaces. | Polish for the first GitHub E2E. | Some polish exists before core E2E. |
| Phase 6 - Testing | Strong backend coverage | Full backend suite passed in audit. | Frontend build/lint/test and GitHub E2E tests. | No web app exists yet. |
| Phase 7 - Deployment | Partial/local | Local startup and CI shape exist. | Railway/prod backend, worker, frontend, env, migrations, smoke tests. | Production deployment not confirmed. |
| Phase 8 - Post-launch | Many pieces already present | Telegram/manual pilot, share packs, second opinion, Jira planners, diagnostics. | Should be frozen until MVP E2E is stable. | These are useful but outside current MVP focus. |

## 5. Keep / Adapt / Defer Decisions

| Area/File/Module | Current status | Decision | Reason | Action |
| --- | --- | --- | --- | --- |
| FastAPI backend | Healthy and tested | KEEP | Matches master backend stack. | Continue from current base. |
| SQLAlchemy/Alembic/Postgres | Implemented foundation | KEEP_AND_ADAPT | Matches stack but canonical models are incomplete. | Reconcile model contract before migrations. |
| Static `/ui` | Useful local/operator UI | KEEP_AND_ADAPT | Useful today, but not the playbook Next.js product UI. | Keep as local/operator UI. |
| Next.js `web/` app | Missing | KEEP_AND_ADAPT | Required by playbook. | Add later as separate scoped task. |
| Source Control | Implemented guarded request layer | KEEP_AND_ADAPT | Useful connector foundation; must align with GitHub-first MVP. | Do not expand beyond MVP path yet. |
| Company Brain / repo audit | Computed preview | KEEP | Matches evidence/provenance direction. | Keep provenance labels and no raw email. |
| Evidence-first extraction | Implemented | KEEP | Core invariant from playbook and repo rules. | Preserve evidence_refs requirements. |
| Telegram/manual pilot | Present | FREEZE / POST_MVP | Useful but not GitHub-first MVP. | Do not expand now. |
| Share packs/investor view | Present | FREEZE / POST_MVP | Outside current MVP. | Keep, do not expand now. |
| Jira write planning | Present | FREEZE / POST_MVP | Useful later, not first E2E. | Keep as planning, no writes. |
| Advanced diagnostics | Broad | FREEZE / POST_MVP | Useful only when tied to real use. | Avoid new diagnostics until MVP E2E. |
| Local/generated files | Ignored/local | DELETE_CANDIDATE only if generated | Examples: caches, `.DS_Store`, local env artifacts. | Do not touch in this task. |

## 6. Architecture Drift

- UI drift: master playbook requires a Next.js frontend; repo currently serves
  a static local/operator SPA.
- Data-model drift: repo has strong event/source/read-model foundations but
  not the master playbook's canonical workspace/integration/sync/briefing/action
  tables.
- Roadmap drift: repo docs describe a local/operator daily loop and manual
  pilot path, while master playbook prioritizes GitHub-first MVP E2E.
- Complexity drift: Telegram/manual pilot, share packs, investor view, Jira
  planners, and advanced diagnostics exist before the main GitHub E2E.
- Connector drift: live provider calls are guarded/read-only; production OAuth
  and approved GitHub write path are not yet productized.
- Positive alignment: evidence refs, strict LLM boundaries, default-deny guards,
  no direct AI writes, raw/Postgres source of truth, and provenance labels are
  aligned with the playbook.

## 7. MVP Gap List

### Critical MVP Gaps

- Login/user/workspace/membership model and flow.
- Canonical IntegrationConnection, SyncJob, SourceRecord, Briefing,
  BriefingItem, ActionProposal, and ActionExecution alignment.
- Next.js app shell and frontend checks.
- GitHub OAuth/connect/sync E2E through the UI.
- Founder Dashboard and Company Brain over GitHub-first evidence.
- Manual Founder Briefing v0 with evidence refs.
- Human-approved GitHub issue creation path.
- Deployment shape for backend, worker, frontend, Postgres, and Redis.

### Important But Not Blocking

- Align internal docs with `founderOS_MASTER_PLAYBOOK.md`.
- Split dirty tree into reviewable checkpoints.
- Decide GitHub OAuth vs existing Source Control product path.
- Preserve existing local/operator UI without making it the product frontend.

### Post-MVP

- Telegram/manual pilot expansion.
- Share packs and investor view.
- Jira write planning/execution.
- Scheduler/outbox expansion.
- Role agents.
- Multi-model council.
- Natural language rule compiler.
- Sandbox workflow execution.
- Advanced diagnostics.
- Compliance hardening beyond MVP.
- Marketplace/plugins and mobile app.

## 8. Current Phase Determination

The project is currently approximately at Phase 2 - Backend Core.

Reason: backend services, guards, API routes, migrations, and tests are strong,
but Phase 1 canonical models are incomplete, Phase 3 Next.js frontend is absent,
and Phase 4 GitHub-first E2E is absent.

## 9. Recommended Next 10 Tasks

| ID | Title | Goal | Files likely affected | Acceptance criteria | Checks to run |
| --- | --- | --- | --- | --- | --- |
| FOS-AUD-02 | Checkpoint/scope split current dirty tree | Make current work reviewable before new implementation. | Docs, git staging plan only. | Logical groups are documented; no app behavior changes. | `git status --short`, `git diff --check`. |
| FOS-DB-01 | Data-model reconciliation spec | Map current DB models to master canonical models. | `docs/data-model.md`, `docs/DECISIONS.md`. | Gaps and reuse decisions are explicit. | Docs test if available. |
| FOS-DB-02 | Add User/Workspace/Membership models | Add canonical identity/workspace foundation. | `app/db/*`, migrations, tests. | Models import; migration applies; no plaintext secrets. | Focused model tests, `alembic upgrade head`. |
| FOS-DB-03 | Add IntegrationConnection/SyncJob canonical models | Add provider connection and sync tracking foundation. | `app/db/*`, migrations, tests. | Tokens are encrypted/secret-safe by contract; sync jobs indexed. | Focused model tests, `alembic upgrade head`. |
| FOS-BE-01 | Workspace-aware auth contract | Define login/workspace access behavior before route changes. | Auth docs/tests first; then API code later. | Contract approved; no API mutation before approval. | Focused auth tests when implemented. |
| FOS-GH-01 | Decide GitHub OAuth vs Source Control path | Choose product path for GitHub-first MVP. | `docs/DECISIONS.md`, connector docs. | Decision records UX, storage, sync, and approval boundary. | Docs test if available. |
| FOS-GH-02 | GitHub repositories read API from evidence/source layer | Expose repo data for MVP without live calls by default. | API/service/tests. | Protected read API returns evidence-backed repos. | Focused API tests. |
| FOS-FE-01 | Minimal web shell plan | Plan Next.js shell without building it yet. | `docs/ROADMAP.md`, frontend spec docs. | Pages, data flow, and checks are defined. | Docs test if available. |
| FOS-BRF-01 | Manual Founder Briefing v0 with evidence refs | Generate manual briefing from stored evidence. | Service/API/UI/tests. | Briefing items have evidence refs; no unsupported claims. | Focused briefing tests. |
| FOS-ACT-01 | ActionProposal approval model/API | Add human approval foundation for external writes. | Models/API/service/tests. | External writes cannot bypass approval. | Focused approval/guard tests. |

## 10. Safety Notes

- Do not touch `.env`, `.env.local`, `.local`, `raw_storage`,
  `obsidian_vault`, `secrets`, caches, or generated local artifacts.
- Do not run live provider connectors, Telegram sends, scheduler/outbox
  execution, or external writes without explicit human approval.
- Do not create migrations before FOS-DB-01 is approved.
- Do not scaffold the Next.js app in FOS-AUD tasks.
- Do not delete useful working code. Mark out-of-scope areas as POST_MVP or
  FREEZE.
- Before implementation resumes, checkpoint and split the dirty tree.

## 11. Final Recommendation

Continue from the current codebase. Do not rewrite. The immediate practical
next step is FOS-AUD-02: checkpoint and split the current dirty tree by scope,
then proceed to FOS-DB-01 data-model reconciliation.

