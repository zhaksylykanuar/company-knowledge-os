# Documentation Audit Before Consolidation

Date: 2026-06-23
Branch: `chore/docs-consolidation`
Removal mode requested: `archive`

## Scope And Inputs

Canonical incoming files found and read:

- `/Users/anuarzh/Downloads/founderOS_MASTER_PLAYBOOK.md`
- `/Users/anuarzh/Downloads/files1/FOUNDEROS_EXECUTION_PLAN.md`
- `/Users/anuarzh/Downloads/files1/PROGRESS.md`

Repository instructions read before edits:

- `docs/index.md`
- `AGENTS.md`
- `CLAUDE.md`

Tracked documentation/instruction inventory source:

- `git ls-files` filtered for `*.md`, `README*`, `AGENTS.md`, `CLAUDE.md`,
  `.cursorrules`, `.cursor/**`, `.github/**/*.md`, `docs/**`.

Out-of-scope local/generated markdown was observed but not read as source truth
or printed:

- `.operator_outputs/**/*.md`
- `.pytest_cache/README.md`
- `obsidian_vault/**/*.md`

These are local/generated/export artifacts, not consolidation targets.

## Current Repository State

| Area | Verified state before consolidation |
|---|---|
| Git | Clean worktree before this audit report. Started from `feat/platform-part2-computed-repo-brain`; created `chore/docs-consolidation` for this work. |
| Backend | FastAPI app under `app/` with many protected/local routes and service modules. |
| Database | SQLAlchemy model modules exist under `app/db/`; canonical identity, integration/sync, and action models now exist. |
| Migrations | 25 tracked Alembic migration files under `migrations/versions/`. |
| Frontend | Next.js shell exists under `web/`; current pages are dashboard, github, briefings, actions, settings, plus shared shell/components. |
| Static UI | Existing local/operator static UI remains in `app/static/founder_ui.html` and `/ui` routes. |
| Tests | 175 top-level `tests/test_*.py` files plus 3 eval tests were present in inventory. |
| Docs | 52 tracked documentation/instruction files, 14,052 lines total before incoming canonical files. |

## Code Map For Documentation Decisions

This audit does not modify code. Code was inspected only to understand whether
docs describe current behavior, target behavior, or stale generations.

Current DB model families observed:

- Core/event/source: `AuditLog`, `IngestedEvent`, `SourceDocument`,
  `DocumentChunk`, `SourceEvent`, `NormalizedActivityItemRecord`.
- Canonical MVP foundations now present: `User`, `Workspace`, `Membership`,
  `IntegrationConnection`, `SyncJob`, `ActionProposal`, `ActionExecution`.
- Graph/second-opinion/operator surfaces: `EntityRecord`, `EntityLinkRecord`,
  `EntityAliasRecord`, `SecondOpinionFinding`, `MetricSnapshot`,
  `StatusSnapshotRecord`, `SharePack`, `AgentProposal`, `DataAvailability`.
- Gmail/attention/extraction surfaces: `GmailThread`, `GmailMessage`,
  `GmailAttachment`, `EmailThreadState`, `AttentionTriageResultRecord`,
  `AttentionTriageFeedbackRecord`, `ExtractedTask`, `ExtractedDecision`,
  `ExtractedRisk`.

Current API families observed:

- MVP-ish workspace/GitHub/action/briefing routes under
  `/v1/workspaces/{workspace_id}/...`.
- Existing local founder/operator routes under `/v1/founder/...`,
  `/v1/inbox`, `/v1/knowledge/...`, `/v1/digest/...`.
- Compatibility Gmail/Drive request wrappers under `/v1/gmail/backfill` and
  `/v1/drive/backfill`.
- Local static UI routes `/`, `/ui`, `/overview`, `/status`, `/dev`.

Current frontend map observed:

- `web/` exists and is a minimal Next.js shell.
- `web/app/github/page.tsx` still states frontend API calls are not wired.
- `web/lib/api.ts` uses `X-FounderOS-API-Key`, `owner_email`, and browser-local
  operator settings.

## Mapping Against Incoming Playbook

The incoming `founderOS_MASTER_PLAYBOOK.md` wins over all older repo playbooks,
vision docs, and planning docs. The canonical MVP line is:

```text
Login
-> Create Workspace
-> Connect GitHub
-> Sync GitHub
-> See Dashboard
-> See Company Brain entities
-> Generate Founder Briefing
-> Open Evidence
-> Approve Action Proposal
-> See External Action Result
```

The incoming `EXECUTION_PLAN.md` defines the execution order:

```text
CHUNK 0 Audit & Docs
-> CHUNK 1 Data Foundation
-> CHUNK 2 Connector Framework
-> CHUNK 3 GitHub E2E
-> CHUNK 4 Briefing MVP
-> CHUNK 5 Action Approval
-> CHUNK 6 Remaining Connectors
-> CHUNK 7 Polish + Repo Audit UI
-> CHUNK 8 Testing Gate + Deploy
```

Required canonical docs from playbook section 15.5:

- `docs/DECISIONS.md`
- `docs/ROADMAP.md`
- `docs/TODO.md`
- `docs/POST_MVP.md`
- `docs/CHANGELOG.md`

Current status: the first four exist; `docs/CHANGELOG.md` is missing.

## Documentation Inventory

Verdicts:

- KEEP: keep as canonical or supporting current-truth doc.
- MERGE: move unique useful content into a canonical doc, then archive original.
- STALE: archive as old generation/history.
- DUPLICATE: archive because another canonical doc should own the content.
- CONTRADICTS: conflicts with incoming playbook; record decision and archive or
  rewrite.
- ASK: do not touch without human decision.

| File | Role | Verdict | Reason | Action |
|---|---|---|---|---|
| `AGENTS.md` | Agent operating rules | KEEP | Current repo instructions; no conflict with incoming playbook except start-doc path will need updating if `docs/index.md` moves. | Update links/rules only as needed. |
| `CLAUDE.md` | AI/extraction boundaries | KEEP | Matches playbook invariants: strict JSON, evidence, no direct mutation. | Keep. |
| `README.md` | Root project entry | MERGE | Useful current setup and layout, but must point to canonical trio and `docs/README.md`. | Update, keep. |
| `NOTES.md` | Pointer note | DUPLICATE | Already says not source of truth; becomes redundant after `docs/README.md`. | Archive after index is created. |
| `SECURITY_BASELINE.md` | Security summary | MERGE | Useful baseline; overlaps with playbook security and `docs/security/api-boundary.md`. | Keep short root baseline or merge to security docs; update links. |
| `docs/index.md` | Current docs index | MERGE | Useful navigation, but task requires one entry at `docs/README.md`. | Merge into `docs/README.md`, then archive or replace with pointer. |
| `docs/ALIGNMENT_AUDIT.md` | Previous repo/playbook audit | STALE | Point-in-time audit; already contradicted by current code state (`web/` and canonical models now exist). | Archive. |
| `docs/CURRENT_DIRTY_TREE_PLAN.md` | Previous dirty-tree plan | STALE | Worktree is currently clean; plan is a historical snapshot. | Archive. |
| `docs/DECISIONS.md` | Project decisions | KEEP | Required by playbook and already records master playbook precedence. | Update with this consolidation decision/conflicts. |
| `docs/ROADMAP.md` | Roadmap | KEEP | Required by playbook; mostly aligned but needs canonical chunk/order cleanup. | Update from incoming playbook/execution plan. |
| `docs/TODO.md` | Near-term tasks | KEEP | Required by playbook; current task list reflects later progress than old audit. | Update to canonical current chunk/task shape if needed. |
| `docs/POST_MVP.md` | Deferred ideas | KEEP | Required by playbook; correct place for post-MVP/operator surfaces. | Update with archived-generation references. |
| `docs/CHANGELOG.md` | Change history | KEEP | Required by playbook but missing. | Create. |
| `docs/backlog.md` | Old FOS ticket list | DUPLICATE | Overlaps `docs/TODO.md` and incoming `EXECUTION_PLAN.md`. | Merge any still-unique ticket IDs into `TODO` or `POST_MVP`, then archive. |
| `docs/playbook.md` | FounderOS Playbook v2 | CONTRADICTS | Older operating playbook with different phase model and Telegram/digest emphasis. Incoming master wins. | Merge reusable execution principles if absent, record conflict, archive. |
| `docs/playbook-digital-twin.md` | Digital twin target playbook v3 | CONTRADICTS | Large target architecture generation; not the MVP source of truth and conflicts with master MVP order. | Move unique future ideas to `POST_MVP`, record conflict, archive. |
| `docs/vision.md` | North star summary | CONTRADICTS | Short target map tied to older digital-twin/Telegram-first usage gates. | Merge non-conflicting future vision to `POST_MVP`, archive. |
| `docs/architecture.md` | Current and target architecture | MERGE | Useful current-truth/code map; target pipeline differs from incoming master order. | Split current truth into `docs/README.md` or `DECISIONS`; archive if redundant. |
| `docs/data-model.md` | Data-model reconciliation | KEEP | Useful current mapping between existing DB and playbook; current code confirms many canonical tables now exist. | Update if needed, keep as supporting doc. |
| `docs/github-integration-decision.md` | GitHub MVP path decision | KEEP | Current GitHub bridge decision explains code that exists now; aligned with safe staged path. | Keep or merge summary into `DECISIONS`. |
| `docs/coding-rules.md` | Coding rules | DUPLICATE | Mostly duplicates `AGENTS.md` and `CLAUDE.md`. | Merge any unique API-boundary notes, archive. |
| `docs/workflows.md` | Development workflow | MERGE | Useful docs-only/testing workflow; overlaps AGENTS and execution plan. | Merge critical rules, archive or keep as support if still linked. |
| `docs/dev-env.md` | Local dev runbook | KEEP | Current runtime setup; not replaced by playbook. | Keep and link from docs index. |
| `docs/mvp-quickstart.md` | Manual MVP quickstart | MERGE | Describes old manual ingestion MVP, not master GitHub-first MVP. | Move to archive or post-MVP/supporting runbook after preserving useful commands. |
| `docs/operator_runtime_setup.md` | Local operator setup | MERGE | Useful for current local operations but outside master user-facing MVP. | Keep as runbook or archive under support; mark non-canonical. |
| `docs/obsidian-bridge.md` | Obsidian bridge | KEEP | Current export-only behavior; aligns with invariant that Obsidian is not source truth. | Keep as supporting runbook. |
| `docs/decisions/0001-founder-os-core-architecture.md` | ADR | KEEP | Historical ADR still aligns with evidence/source-of-truth invariants. | Keep. |
| `docs/agents/chunking-agent.md` | Agent role stub | DUPLICATE | Small docs duplicate CLAUDE/feature docs; not part of incoming canonical set. | Merge role summary if useful, archive. |
| `docs/agents/digest-agent.md` | Agent role stub | DUPLICATE | Digest-specific old role doc; post-MVP relative to master. | Archive after POST_MVP mention. |
| `docs/agents/extraction-agent.md` | Agent role stub | DUPLICATE | Duplicates CLAUDE extraction contract. | Archive after preserving unique wording if any. |
| `docs/agents/ingestion-agent.md` | Agent role stub | DUPLICATE | Duplicates source/ingestion feature docs. | Archive. |
| `docs/agents/retrieval-agent.md` | Agent role stub | DUPLICATE | Duplicates retrieval feature docs. | Archive. |
| `docs/agents/validation-agent.md` | Agent role stub | DUPLICATE | Duplicates CLAUDE and API-boundary docs. | Archive. |
| `docs/features/ingestion.md` | Current ingestion feature | KEEP | Current behavior and invariants; supports existing code. | Keep as supporting feature doc. |
| `docs/features/extraction.md` | Current extraction feature | KEEP | Aligns with evidence/strict-validation invariants. | Keep. |
| `docs/features/retrieval.md` | Current retrieval feature | KEEP | Describes existing deterministic retrieval. | Keep as support; mark not master MVP spine if needed. |
| `docs/features/source-events.md` | Current source-events feature | KEEP | Important bridge between existing code and master source records. | Keep. |
| `docs/features/source-integrations.md` | Source integrations contract | KEEP | Current connector/credential safety; aligns with guarded sync posture. | Keep as supporting doc. |
| `docs/features/company-brain.md` | Company Brain contract | KEEP | Aligns with computed/provenance/evidence direction and repo-audit code. | Keep. |
| `docs/features/local-ui.md` | Static local UI contract | MERGE | Current code truth, but not the master Next.js product UI. | Keep only if clearly labelled local/operator; otherwise archive after index update. |
| `docs/features/gmail.md` | Gmail feature | KEEP | Current request-only/read-only behavior; master includes Gmail minimal later. | Keep as supporting current-truth doc. |
| `docs/features/drive.md` | Drive feature | KEEP | Current request-only/read-only behavior; master includes Drive minimal later. | Keep as supporting current-truth doc. |
| `docs/features/obsidian-export.md` | Obsidian export | KEEP | Matches export-only invariant. | Keep. |
| `docs/features/knowledge-graph.md` | Knowledge graph/second opinion | MERGE | Useful but mostly beyond master MVP order. | Move future/target portions to `POST_MVP`; keep only current-contract slice or archive. |
| `docs/features/attention.md` | Attention/digest ledger | MERGE | Has a current-status block but also a huge archived FOS ledger. | Preserve current behavior and archive historical ledger-heavy original. |
| `docs/features/telegram-digest.md` | Telegram digest contract/ledger | STALE | Telegram digest is post-MVP relative to incoming master; large historical ledger. | Move summary to `POST_MVP`, archive original. |
| `docs/runbooks/manual-pilot.md` | Manual pilot runbook | STALE | Manual digest/Telegram pilot is not the master GitHub-first MVP line. | Archive after POST_MVP note. |
| `docs/runbooks/google-local-backfill.md` | Google local backfill runbook | KEEP | Supports current Gmail/Drive safe local path; master has Gmail/Drive later. | Keep as supporting runbook. |
| `docs/runbooks/guarded-operations.md` | Guarded operations runbook | KEEP | Documents safety gates and local diagnostics; aligns with approval/read-only invariants. | Keep. |
| `docs/runbooks/jira-operating-model.md` | Jira operating model | KEEP | Useful Jira planning and reinforces repo != Jira project. | Keep as supporting runbook. |
| `docs/ops/jira-target-blueprint.md` | Jira target design | MERGE | Useful but not master MVP; belongs under post-MVP/Jira support. | Keep if labelled supporting, or archive after summary. |
| `docs/ops/jira-rebuild-audit.md` | Jira rebuild audit draft | STALE | Separate Jira migration generation, not current master MVP path. | Archive. |
| `docs/ops/jira-rebuild-runbook-draft.md` | Jira rebuild runbook draft | STALE | Future write migration draft outside master MVP. | Archive. |
| `docs/security/api-boundary.md` | API security boundary | KEEP | Current security contract; aligns with playbook baseline. | Keep. |
| `docs/source-connectors.md` | Connector runbook | KEEP | Current source connector safety and scoped sync rules. | Keep as supporting doc. |
| `web/README.md` | Next.js shell docs | KEEP | Current frontend shell exists and master requires web frontend. | Keep and update if links change. |
| `migrations/README` | Empty migration marker | ASK | Empty tracked file; may be intentional placeholder. | Do not touch unless human approves. |

## Generations From Rebuilds

| Generation | Representative docs | Character | Audit decision |
|---|---|---|---|
| G1: Knowledge OS/manual ingestion | `docs/mvp-quickstart.md`, `docs/backlog.md`, agent stubs | Manual text ingestion, extraction, Obsidian, deterministic search. | Preserve working invariants; archive duplicated planning docs. |
| G2: Local operator/digest/Telegram | `docs/playbook.md`, `docs/vision.md`, `docs/features/attention.md`, `docs/features/telegram-digest.md`, `docs/runbooks/manual-pilot.md` | Telegram/digest/status-engine direction with many FOS ledger entries. | Move to POST_MVP/history; not current MVP line. |
| G3: Digital twin target architecture | `docs/playbook-digital-twin.md` | Broad target architecture: company digital twin, graph, second opinion, Telegram Q&A. | Archive as target-generation document; incoming master wins for MVP. |
| G4: Previous alignment/dirty-tree audit | `docs/ALIGNMENT_AUDIT.md`, `docs/CURRENT_DIRTY_TREE_PLAN.md` | Point-in-time audit of an earlier dirty tree. | Archive because worktree and code state changed. |
| G5: Incoming master MVP line | incoming `founderOS_MASTER_PLAYBOOK.md`, `EXECUTION_PLAN.md`, `PROGRESS.md` | Modular monolith, UI-first GitHub E2E, evidence, human-approved actions. | Chosen as canonical line. |

Chosen line: G5. Supporting docs may remain only when they document current code
truth or safe operations and are clearly subordinate to the canonical trio.

## Code Duplicates / Conflicts To Report Only

Code is not changed by this documentation consolidation.

| Area | Observed duplication/drift | Why it matters | Proposed human decision |
|---|---|---|---|
| UI surfaces | Static `/ui` local/operator UI and Next.js `web/` shell both exist. | Master wants one user-facing web product; static UI is still useful local/operator code. | Keep static UI as local/operator until product `web/` is wired; avoid treating it as the MVP product UI. |
| API base paths | Incoming playbook says `/api/v1`; existing routes are mostly `/v1/...`. | Docs can overpromise a different API namespace. | Decide whether to adapt docs to current `/v1` during MVP or plan an `/api/v1` migration later. |
| Source model naming | Playbook uses `SourceRecord`; repo has `IngestedEvent`, `SourceDocument`, `DocumentChunk`, `SourceEvent`. | Risk of duplicate source-of-truth tables if docs blindly follow playbook names. | Keep data-model reconciliation as bridge; do not add duplicate tables without explicit schema task. |
| Entity model naming | Playbook uses `NormalizedEntity`; repo has `EntityRecord`, `NormalizedActivityItemRecord`, extracted task/risk/decision tables. | Docs can imply one canonical entity table while code has graph and activity projections. | Preserve reconciliation docs until schema contract is finalized. |
| GitHub path | Playbook product flow says OAuth + sync; current code includes provider-token bridge, manual local sync job, normalization-local, mocked E2E. | Current implementation is safer but not full product OAuth E2E. | Keep staged bridge decision or explicitly choose OAuth migration. |
| Post-MVP surfaces | Telegram digest, share packs, Jira rebuild planning, second opinion, attention ledgers exist before full GitHub product E2E. | Docs may keep agents expanding non-spine work. | Freeze as POST_MVP/supporting docs until GitHub E2E is product-usable. |

## Sources Of Truth To Keep

After consolidation, the intended canonical set is:

- `founderOS_MASTER_PLAYBOOK.md`
- `EXECUTION_PLAN.md`
- `PROGRESS.md`
- `AGENTS.md`
- `CLAUDE.md`
- `docs/README.md`
- `docs/DECISIONS.md`
- `docs/ROADMAP.md`
- `docs/TODO.md`
- `docs/POST_MVP.md`
- `docs/CHANGELOG.md`

Supporting current-truth docs may remain under `docs/features/`,
`docs/runbooks/`, and `docs/security/` only when they are explicitly subordinate
to the canonical set and do not claim to be the product source of truth.

## To Archive

Primary archive candidates:

- `NOTES.md`
- `docs/ALIGNMENT_AUDIT.md`
- `docs/CURRENT_DIRTY_TREE_PLAN.md`
- `docs/backlog.md`
- `docs/playbook.md`
- `docs/playbook-digital-twin.md`
- `docs/vision.md`
- `docs/features/telegram-digest.md`
- `docs/runbooks/manual-pilot.md`
- `docs/ops/jira-rebuild-audit.md`
- `docs/ops/jira-rebuild-runbook-draft.md`
- `docs/agents/*.md`

Possible archive after merge/label:

- `docs/coding-rules.md`
- `docs/workflows.md`
- `docs/mvp-quickstart.md`
- `docs/features/attention.md`
- `docs/features/knowledge-graph.md`
- `docs/ops/jira-target-blueprint.md`

ASK:

- `migrations/README` is empty and tracked. It is not documentation debt enough
  to remove during this docs consolidation without explicit human approval.

## Merged Into What

Planned merge targets:

| Source | Target |
|---|---|
| `docs/index.md` | `docs/README.md` |
| old playbooks/vision target ideas | `docs/POST_MVP.md` and `docs/DECISIONS.md` |
| current safe operation rules | `AGENTS.md`, `CLAUDE.md`, `docs/security/api-boundary.md`, `docs/runbooks/guarded-operations.md` |
| GitHub MVP bridge decisions | `docs/DECISIONS.md`, preserving `docs/github-integration-decision.md` if still useful |
| old FOS/backlog items | `docs/TODO.md` or `docs/POST_MVP.md` |
| attention/Telegram historical ledgers | archive manifest plus short POST_MVP entry |

## Human Decisions Needed

- Decide later whether the public API namespace should remain `/v1` or migrate
  toward playbook `/api/v1`.
- Decide later when the Next.js `web/` app replaces static `/ui` as the primary
  product surface.
- Decide later whether `migrations/README` should remain as a placeholder.

## Next Consolidation Actions

1. Commit this audit report by itself:
   `docs(audit): inventory of all docs before consolidation`.
2. Add the incoming canonical trio in one place, using root repo names:
   `founderOS_MASTER_PLAYBOOK.md`, `EXECUTION_PLAN.md`, `PROGRESS.md`.
3. Create/update required canonical docs, especially missing
   `docs/CHANGELOG.md` and new `docs/README.md`.
4. Archive STALE/DUPLICATE/CONTRADICTS docs to `docs/_archive/` with
   `docs/_archive/MANIFEST.md`.
5. Update links from root `README.md` and agent instructions.
6. Verify internal links and that `git diff` is docs-only.

---

## Code Reality vs FOS (audit 2026-06-24)

Verdict rubric: **DONE** = code + passing test/working endpoint meeting the FOS
acceptance criteria. **PARTIAL** = code exists but acceptance/canonical shape not
met. **MISSING** = no implementation under the canonical contract. Gate runs this
date: `alembic upgrade head` ✅ (head `f5a6b7c8d9e0`) · `ruff` ✅ · frontend
`next build` + `tsc` ✅ · `pytest` 1805 passed / 4 failed (doc-contract tests).

| FOS | Title | Status | Evidence (one line) |
|---|---|---|---|
| FOS-000 | Repo baseline audit | DONE | This audit; no code changed; PROGRESS/DECISIONS/_audit updated |
| FOS-001 | Project docs | DONE | `docs/{DECISIONS,ROADMAP,TODO,POST_MVP,CHANGELOG}.md` exist (4 doc-contract tests still red) |
| FOS-002 | Core DB models (22 §6) | PARTIAL | 8/22 canonical present; `tests/test_integration_models.py` green; 14 canonical tables absent |
| FOS-003 | Encryption utility | DONE | `app/services/secret_encryption.py` (Fernet); roundtrip in `tests/test_github_provider_token_connection.py` |
| FOS-004 | Connector base interface | MISSING | No `app/connectors/base.py` with ProviderClient/SyncResult/ProviderError contract |
| FOS-005 | Sync service | PARTIAL | No generic `sync_service.py`/SourceRecord; per-provider `app/services/github_sync_job_service.py` |
| FOS-006 | Normalization service | PARTIAL | No generic `normalization_service.py`/NormalizedEntity/EvidenceRef; `github_normalization_service.py` projects dicts |
| FOS-007 | GitHub OAuth | PARTIAL | No OAuth start/callback (§7.5); PAT-bridge connection, token encrypted; `tests/test_github_provider_token_connection.py` green |
| FOS-008 | GitHub sync repositories | DONE | `app/services/github_sync_job_service.py` + `/v1/.../github/repositories`; `tests/test_github_first_backend_e2e.py` (repos count==1) |
| FOS-009 | GitHub sync issues + PRs | PARTIAL | PR projection only; issues empty with warning (`github_normalization_service.py:26-27`) |
| FOS-010 | Connectors UI page | MISSING | No `web/app/connectors/page.tsx`; only stub `web/app/github/page.tsx` |
| FOS-011 | Dashboard v0 | PARTIAL | `app/services/founder_overview.py`; `web/app/dashboard/page.tsx` stub, not wired to live data |
| FOS-012 | Brain entity API + UI | PARTIAL | `app/api/company_brain.py` exists; no `web/app/brain` page |
| FOS-013 | Briefing backend | PARTIAL | `founder_briefing_service.py` deterministic/transient (no LLM, no Briefing rows); `tests/test_founder_briefing_api.py` green |
| FOS-014 | Briefing UI | MISSING | `web/app/briefings/page.tsx` 23-line stub; no evidence drawer |
| FOS-015 | Action proposal API | PARTIAL | `app/api/actions.py` approve/reject/execute + models + migration; `tests/test_action_proposals_api.py` green; no async worker |
| FOS-016 | GitHub create-issue action | PARTIAL | `github_issue_execution_service.py` + `tests/test_github_issue_execution_api.py` green; issue client mocked (no real write) |
| FOS-017 | Jira connector minimal | PARTIAL | `app/connectors/jira.py` + discovery/mapping; no `web/app/jira`; not in canonical Brain |
| FOS-018 | Gmail connector minimal | PARTIAL | `app/connectors/gmail.py` + gmail models + `app/api/gmail.py`; no `web/app/gmail` |
| FOS-019 | Drive connector minimal | PARTIAL | `app/connectors/google_drive.py` + `app/api/drive.py`; no `web/app/drive` |
| FOS-020 | Documents module | PARTIAL | `source_documents` (RAG) only; no canonical `Document` CRUD (§7.11); no `web/app/documents` |
| FOS-021 | Repo Audit UI | PARTIAL | `app/services/repo_audit.py` exists; no `web/app/repo-audit` page |
| FOS-022 | Smoke tests | PARTIAL | Backend `test_github_first_backend_e2e.py` + `test_external_connector_readonly_smoke.py` green; no `make smoke`/Makefile/prod smoke |

Totals: **DONE 4 · PARTIAL 16 · MISSING 3** (= 23). Strict progress 4/23 (17%).

Note on TODO drift: `docs/TODO.md` tracks a parallel scheme
(`FOS-AUD/DB/GH/BRF/ACT/E2E/FE-*`) with ~15 entries marked "done", which reads as
a near-complete backend MVP. Against the playbook's `FOS-000..022` that maps to
mostly PARTIAL backend work, not DONE.

Canonical model coverage (§6, 22 entities): present under canonical names = User,
Workspace, Membership, IntegrationConnection, SyncJob, ActionProposal,
ActionExecution, AuditLog (8). Absent as canonical tables (14) = SourceRecord,
EvidenceRef, NormalizedEntity, Project, Task, Repository, PullRequest,
MessageThread, DriveFile, Document, Goal, Insight, Briefing, BriefingItem.

Canonical frontend pages (§8): present (stubs) = `/dashboard`, `/github`,
`/briefings`, `/actions`, `/settings`. Absent = `/login`, `/connectors`,
`/brain`, `/jira`, `/gmail`, `/drive`, `/documents`, `/repo-audit`.

## Drift Resolved (audit 2026-06-24)

Decisions recorded in `docs/DECISIONS.md` (DEC-023..026) and ASK-1/ASK-2. No code,
migrations, tests, or config were changed.

| Drift | Verdict (playbook ref) | Where the conflict lives |
|---|---|---|
| API namespace `/v1` vs `/api/v1` | Canonical = `/api/v1` (§7.1) → **DEC-023**. `/api/v1` used nowhere; `/v1` everywhere | `app/main.py` + all `app/api/*.py` prefixes + `web/app/github/page.tsx` |
| SourceRecord vs source/event tables | Canonical = `SourceRecord`/`NormalizedEntity`/`EvidenceRef` (§6.7/6.9/6.8) → **DEC-024** | `app/db/event_models.py` (`source_events`), `graph_models.py` (`entities`), `source_models.py`, `models.py`; `EvidenceRef` only a Pydantic schema |
| Static `/ui` vs Next.js `web/` | Product frontend = Next.js `web/` (§8); legacy `founder_ui.html` (`/ui`) retired later → **DEC-025** (refines DEC-004/020) | `app/static/` page + `ui_page_router` in `app/main.py` vs `web/app/*` |
| Post-MVP surfaces built before GitHub E2E | No-go / out of scope (§3.3/3.4, EXECUTION_PLAN #5/#6) → **DEC-026** (concretizes DEC-006/022) | telegram/digest/share-pack/second-opinion/role-view/jira-write/attention/meeting/knowledge-QA services in `app/services/` |
| Genuinely ambiguous | Not decided → **ASK-1** (23rd model / missing `Person`), **ASK-2** (rename-migrate vs add-alongside foundation strategy) | §6 defines 22; `assignee_person_id`/`author_person_id` imply undefined Person |
