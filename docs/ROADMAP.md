# FounderOS Roadmap

Status: roadmap aligned to `founderOS_MASTER_PLAYBOOK.md` after the repo
alignment audit.

The current project phase is approximately Phase 2 - Backend Core. The next
practical step is not new feature work; it is checkpoint/scope split of the
current dirty tree.

## Phase 0 - Project Setup

Current status: partially done.

Done:

- Repo alignment audit completed.
- Baseline checks from the audit were recorded.
- Alignment docs are now being added.
- Existing backend test/lint/migration checks were green during audit.

Missing:

- Current dirty tree is not checkpointed or split by scope.
- Decision docs and roadmap need to be treated as the working coordination
  layer.

Next step: finish FOS-AUD-02, then checkpoint a docs-only alignment commit or
otherwise isolate the six audit docs from the pre-existing dirty tree.

Definition of Done:

- `docs/ALIGNMENT_AUDIT.md`, `docs/DECISIONS.md`, `docs/ROADMAP.md`,
  `docs/TODO.md`, `docs/POST_MVP.md`, and
  `docs/CURRENT_DIRTY_TREE_PLAN.md` exist.
- Dirty tree plan is explicit.
- `git diff --check` passes.
- Docs tests pass if available.

## Phase 1 - Database / Core Models

Current status: partially done.

Done:

- Raw/event/source/evidence/attention/graph/audit-adjacent persistence exists.
- Existing migrations are present and were at head/current in the audit
  environment.
- Evidence refs are a repository invariant.

Missing:

- Canonical User, Workspace, Membership.
- Canonical IntegrationConnection and SyncJob.
- Canonical SourceRecord alignment.
- Briefing and BriefingItem.
- ActionProposal and ActionExecution.
- Explicit model reconciliation between existing implementation and master
  playbook.

Next step: FOS-DB-01 data-model reconciliation spec.

Definition of Done:

- Current models are mapped to master canonical models.
- Reuse/adapt/new decisions are explicit before migrations.
- No plaintext token fields are introduced.
- Future migrations have focused tests.

## Phase 2 - Backend Core

Current status: partly implemented and currently the closest confirmed phase.

Done:

- FastAPI app with modular routes and services.
- Provider execution guards and write-action guard foundations.
- Deterministic extraction, scoring, attention, source control, and Company
  Brain read models.
- LLM paths are gated/off by default.

Missing:

- Workspace-aware auth contract and route-level access model.
- Canonical connector service around IntegrationConnection.
- Canonical sync service around SyncJob.
- Canonical action service around ActionProposal/ActionExecution.
- Briefing service aligned to master MVP.

Next step: after FOS-DB-01 through FOS-DB-03, define FOS-BE-01
workspace-aware auth.

Definition of Done:

- Services are unit-tested.
- Provider logic is isolated from routes.
- No secrets in logs or browser payloads.
- Errors are typed/sanitized.
- External writes remain approval-gated.

## Phase 3 - Frontend Core

Current status: minimal master frontend shell exists, but the product flow is
not wired yet.

Done:

- Static `/ui` exists and is useful for local/operator workflows.
- Company Brain/repo audit and source/data views are visible in local UI.
- Minimal Next.js + TypeScript app exists in `web/`.
- App shell, sidebar, MVP placeholder pages, browser-local operator settings,
  and typed API client foundation exist.
- Frontend typecheck/build/lint scripts exist and pass.

Missing:

- Backend wiring for the GitHub-first flow.
- Tailwind/shadcn or final product UI system.
- Login page.
- Workspace onboarding.
- Product-grade loading/error/empty states.
- Browser/product E2E coverage.

Next step: FOS-FE-02 wire frontend to the existing backend GitHub-first flow.

Definition of Done:

- `web/` app runs locally.
- User can navigate through the MVP shell.
- Connector cards are visible.
- Empty states are helpful.
- Frontend lint/test/build checks exist and pass.

## Phase 4 - GitHub-First E2E

Current status: backend smoke path covered; frontend/product flow still
missing.

Done:

- Some GitHub read-only/evidence/source pieces exist.
- Repository source inventory and repo audit foundations exist.
- Provider boundaries are guarded by default.
- GitHub MVP integration path decision is documented as a hybrid staged path.
- Workspace-scoped GitHub repositories read API exists over the local
  source/evidence inventory bridge.
- Workspace-scoped GitHub connection list/status/detail contract exists over
  `IntegrationConnection`.
- Operator-protected provider-token bridge can create/update encrypted GitHub
  `IntegrationConnection` records without live provider calls.
- Manual GitHub SyncJob record API can create/list/detail queued local sync
  intents without live provider calls or worker execution.
- Local GitHub normalization projection can transform repository inventory into
  founderOS-compatible shape and update the manual `SyncJob` without live sync.
- Manual Founder Briefing v0 can return a deterministic, transient,
  evidence-aware briefing from local workspace GitHub signals.
- Local ActionProposal approval foundation can store, approve, and reject
  workspace-scoped proposals without external execution.
- Approved GitHub issue proposals can execute through the guarded backend path
  with local `ActionExecution` tracking.
- Backend E2E smoke coverage exercises the GitHub-first path from workspace
  bootstrap through mocked approved issue execution.

Missing:

- Full GitHub OAuth implementation path.
- Actual GitHub sync execution and persistent repos/issues/PR graph upsert
  through the product flow.
- SourceRecords/normalized entities aligned to master model.
- Dashboard with GitHub data.
- Company Brain over GitHub-first evidence.
- Product frontend flow for the GitHub-first MVP path.

Next step: FOS-FE-01 scaffold minimal frontend shell for the MVP backend flow.

Definition of Done:

- User connects GitHub through UI.
- Sync completes.
- Data is visible in Dashboard and Company Brain.
- Briefing is generated with evidence.
- Approved action creates a GitHub issue.
- External result is visible and audited.

## Phase 5 - Edge Cases & Polish

Current status: partially ahead of schedule in backend/operator surfaces.

Done:

- Some guarded error handling, retries, source receipts, source diagnostics,
  and stale/provenance labels exist.

Missing:

- Edge-case handling tied to the GitHub-first E2E.
- Token-expired handling in the product flow.
- Evidence drawer in the product frontend.
- Action failure UI in the product frontend.
- Filters/search/stale labels for the MVP web app.

Next step: wait until Phase 4 has a working E2E, then polish the actual path
users run.

Definition of Done:

- No dead-end screens in the GitHub-first flow.
- User understands sync/action failures.
- Retries are possible and safe.
- Evidence is inspectable from every factual claim.

## Phase 6 - Testing

Current status: strong backend coverage, incomplete product/E2E coverage.

Done:

- Full backend test suite passed during the audit.
- Lint and migration checks passed during the audit.
- Guard/evidence tests exist.
- GitHub-first backend E2E smoke test covers the local API path with mocked
  external provider execution.

Missing:

- Frontend checks.
- Browser/product GitHub-first E2E tests.
- Briefing validation tests aligned to master MVP.
- Action approval tests aligned to canonical ActionProposal.
- Manual QA checklist for MVP.

Next step: add focused tests with each implementation slice; do not add broad
test scaffolding before the relevant feature exists.

Definition of Done:

- Backend tests green.
- Frontend lint/test/build green.
- GitHub E2E covered.
- AI validation covered.
- Action approval path covered.

## Phase 7 - Deployment

Current status: partial/local only.

Done:

- Local dev startup path exists.
- Docker Compose Postgres/Redis exists.
- CI shape exists in the dirty tree.

Missing:

- Railway project.
- Production Postgres/Redis binding.
- Backend service.
- Worker service.
- Frontend service.
- Production env var contract.
- Deployment smoke tests.
- Domain/health checks.

Next step: defer until Phases 1-4 are aligned enough for a deployable MVP.

Definition of Done:

- Production URL works.
- Login works.
- GitHub connect works.
- Sync works.
- Briefing works.
- Logs are visible.
- Rollback path exists.

## Phase 8 - Post-launch

Current status: many post-MVP/operator pieces already exist but should remain
frozen.

Done or partially present:

- Telegram/manual pilot.
- Share packs/investor view.
- Jira planning/dry-run surfaces.
- Second opinion and advanced diagnostics.
- Role-like/operator read models.

Missing:

- Productized post-launch expansion after MVP validation.
- Usage-based prioritization.

Next step: do not expand until GitHub-first MVP E2E is complete and used.

Definition of Done:

- MVP is launched.
- GitHub-first flow is stable.
- Expansion item has a real usage case.
- New surface reuses evidence_refs, approval gates, and source-of-truth rules.
