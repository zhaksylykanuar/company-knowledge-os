# Purge Classification (before deletion) — 2026-06-24

Branch `chore/purge-legacy`. Goal: remove frozen Lineage-2 / dead weight / non-
playbook docs. Canon = GitHub spine (Lineage 1) + canonical §6 tables (DEC-028).

## Recovery anchor

- Tag **`pre-purge-20260624`** placed at `f2b8fb0` BEFORE any deletion.
- Restore any deleted file: `git restore --source pre-purge-20260624 -- <path>`.
- Restore everything: `git checkout pre-purge-20260624` (detached) or cherry-revert
  the purge commits. Historical alembic migrations are never deleted.

## Method

AST import-graph over `app/**/*.py`. Canonical ROOTS = the mounted canonical
routers (`health`, `auth`, `workspaces`, `github`, `briefings`, `actions`,
`company_brain`, `dev`) + `canonical_models` + `integration_models` +
`action_models` + `identity_models` + `models` (AuditLog) + `core.config` +
`secret_encryption`. KEEP = transitive import closure of ROOTS. DELETE = `app/`
modules not in the closure. Counts: 178 total, **33 KEEP**, **145 not-in-closure**.

## KEEP (spine closure, 33) + manual keeps

Closure: `app.api.{health,auth,workspaces,workspace_auth,github,briefings,actions,
company_brain,dev}`, `app.core.config`, `app.db.{base,canonical_models,
integration_models,action_models,identity_models,models,event_models}`,
`app.services.{action_proposal_service,browser_config,company_brain_preview,
founder_briefing_service,github_connection_service,github_issue_client,
github_issue_execution_service,github_normalization_service,
github_repository_read_service,github_sync_job_service,identity_service,
operator_output_sanitizer,repo_audit,repository_portfolio,
repository_source_inventory,secret_encryption}`.

Manual keeps (closure marks them DELETE only because nothing imports the entry
point / package markers): **`app/main.py`** (app factory — edit to unmount legacy
routers, do not delete) and package `__init__.py` for packages that survive
(`app`, `app.api`, `app.db`, `app.services`, `app.core`).

## DELETE — clean (no spine coupling), entities-graph + pure Lineage-2

None of these are reachable from the canonical ROOTS; deleting them cannot break
spine imports. (Edit `app/main.py` to unmount their routers first.)

- **api routers (10, unmount+delete):** `digest`, `drive`, `events`, `extraction`,
  `gmail`, `google`, `inbox`, `knowledge`, `share_packs`, `view_guard`.
  (`ui` — see SHARED-ASK #3.)
- **db legacy models (clean, 11):** `graph_models` (entities + entity_aliases +
  entity_links + entity_source_accounts), `agent_models`, `attention_models`,
  `declaration_models`, `gmail_models`, `score_models`, `second_opinion_models`,
  `share_pack_models`, `source_control_models`, `source_models`, `status_models`,
  `task_models`.
- **connectors (4):** `github`, `gmail`, `google_drive`, `jira`.
- **integrations (3):** `connector_ingestion`, `payload_mapper`, `source_registry`.
- **agents (4):** `evidence_validator`, `llm_runner`, `runner`, `schemas`.
- **events (1):** `schemas`.
- **services (~99):** knowledge-graph (`knowledge_graph(_view)`, `entity_identity`,
  `entity_resolution`, `graph_gardener`, `gardener_apply`, `graph_lift`,
  `graph_tree`, `evidence_graph_lift`, `evidence_trail`, `evidence_explorer`,
  `metric_collector`, `*_graph_mapping`); knowledge/RAG (`knowledge_*`,
  `chunking`, `extraction_processor`); digest/inbox/telegram (`digest*`,
  `inbox*`, `telegram_*`, `notification_center`, `command_center`,
  `operating_rhythm`); founder-views (`founder_overview`, `founder_digest_rendering`,
  `sales_view`, `sales_signal_agent`, `team_view`, `product_view`,
  `execution_view`, `role_views`, `project_status_view`, `curated_updates`,
  `visibility`); email/meeting (`email_*`, `meeting_*`); jira (`jira_*`,
  `atlassian_api_profiles`); second-opinion (`second_opinion`); attention
  (`attention_*`); declarations (`declaration*`); source/discovery
  (`source_activity`, `source_connectors`, `source_control`, `source_events`,
  `source_ingestion`, `source_run_*`, `discovery_*`, `github_discovery`,
  `github_org_inventory`, `local_repo_discovery`, `normalized_activity`);
  share-packs (`share_packs`); obsidian (`obsidian_*`); guards used only by legacy
  (`production_operation_guard`, `provider_execution_guard`,
  `scheduler_execution_guard`, `guarded_execution_*`, `write_action_guard`);
  misc legacy utils (`raw_storage`, `run_context`, `confidence`, `secret_patterns`,
  `connector_*`, `external_connector_*`, `data_availability`, `data_quality_center`,
  `agent_proposals`, `agent_run_log`, `action_center`, `status_engine`,
  `status_snapshot_repository`, `metric_collector`). Full machine list in the
  audit transcript; regenerate with the closure script.

## Tables — drop classification

- **Safe to drop** (no KEEP code references): `entities`, `entity_aliases`,
  `entity_links`, `entity_source_accounts`, `knowledge_scores`,
  `second_opinion_findings`, `gmail_threads`, `gmail_messages`,
  `gmail_attachments`, `email_thread_states`, `source_documents`,
  `document_chunks`, `agent_proposals`, `metric_snapshots`, `agent_run_logs`,
  `data_availability`, `attention_triage_results`, `attention_triage_feedback`,
  `founder_declarations`, `status_snapshots`, `share_packs`,
  `source_control_states`, `source_run_requests`, `agent_runs`, `extracted_tasks`,
  `extracted_decisions`, `extracted_risks`.
- **HELD — do NOT drop (SHARED, read by spine):** `source_events`,
  `normalized_activity_items`, `ingested_events` — see SHARED-ASK #1.

## SHARED-ASK (blocks a clean cut — ФАЗА 2 STOP)

**#1 — `source_events` substrate is read by the canonical Brain / Repo-Audit.**
Reachability chain (all KEEP):
`app.api.company_brain` → `company_brain_preview` → `repo_audit` →
`repository_portfolio` → `repository_source_inventory` → `app.db.event_models`
(`SourceEvent`). `repository_source_inventory.py:122` runs
`select(SourceEvent).where(SourceEvent.source_system=='github')` as the **primary**
repo-inventory source ("SourceEvent/Postgres first, GitHub discovery snapshot
fallback"). So `event_models` (`source_events`, `normalized_activity_items`) and
the `repository_source_inventory`/`repository_portfolio` bridge are inside the
spine closure. Dropping `source_events` would break repo-audit/Brain.
- Question: leave `source_events` + `event_models` + the inventory bridge as canon
  for now (drop only the clean entities-graph + pure Lineage-2), OR refactor
  `repository_source_inventory` to read the new canonical `source_records`/
  `repositories` so `source_events` can be dropped (bigger, FOS-008/009 territory)?

**#2 — Mixed model file `app/db/models.py`.** Holds `AuditLog` (§6.23, canonical
KEEP) AND `IngestedEvent` (`ingested_events`, Lineage-2; FK target of
`source_events`). Cannot `git rm`. Resolution depends on #1.

**#3 — Mixed router file `app/api/ui.py`** (not in closure). Holds `page_router`
(static `/ui` operator UI + `app/static/founder_ui.html`) AND `views_router`
(`/api/v1/founder/*` overview — Lineage-2). DEC-025 said retire `/ui` in a
*separate later* task, not now.
- Question: delete `/ui` now (overriding DEC-025's "later"), or keep the static
  operator UI and delete only `views_router`?

**#4 — Doc-contract tests guard to-be-deleted docs.** `test_ci_workflow_contract`
(KEEP — guards SHA-pinned CI) also asserts `docs/playbook.md` + the README CI
section; `test_jira_operating_model` asserts `docs/ops/jira-target-blueprint.md`;
`test_stage13_local_launch` asserts `docs/dev-env.md`/`obsidian-bridge.md`/
`features/local-ui.md`; `test_docs_navigation_integrity` asserts README/`index.md`
links + several `docs/features/*` contents. Deleting those docs breaks KEEP/infra
tests (these were just restored in this branch for the doc-contract gate).
- Question: delete non-canon docs and also trim/remove their guarding assertions
  (incl. the doc parts of the KEEP CI test), or keep the minimal docs those tests
  assert?

## Docs DELETE candidates (pending #4)

Keep (canon): `founderOS_MASTER_PLAYBOOK.md`, `EXECUTION_PLAN.md`, `PROGRESS.md`,
`docs/{README,DECISIONS,ROADMAP,TODO,POST_MVP,CHANGELOG}.md`, `docs/_audit/*`.
Delete candidates: `docs/_archive/**` (entire), `docs/architecture.md`,
`docs/data-model.md`, `docs/decisions/*`, `docs/dev-env.md`, `docs/features/*`,
`docs/github-integration-decision.md`, `docs/index.md`, `docs/obsidian-bridge.md`,
`docs/operator_runtime_setup.md`, `docs/ops/*`, `docs/playbook.md`,
`docs/runbooks/*`, `docs/security/*`, `docs/source-connectors.md`. Stray root
instruction files to review: `AGENTS.md`, `CLAUDE.md`, `SECURITY_BASELINE.md`
(CLAUDE.md is repo guidance — likely KEEP; flag in #4 decision).

## SHARED-ASK #5 — spine TESTS depend on legacy modules (found during test mapping)

The spine's own API tests import legacy modules slated for deletion:
- `tests/test_github_first_backend_e2e.py` (the critical spine E2E),
  `test_action_proposals_api.py`, `test_founder_briefing_api.py`,
  `test_github_connection_contract.py`, `test_github_provider_token_connection.py`,
  `test_github_repositories_api.py`, `test_github_sync_jobs_api.py`,
  `test_github_normalization_api.py`, `test_github_issue_execution_api.py`
  import `app.connectors.github` and/or `app.services.source_control`
  (and some import `app.db.graph_models` / `app.db.source_control_models`).
- Usage is mostly **negative guards**: `monkeypatch.setattr(source_control_service,
  "request_source_action", fail_source_action)` and
  `monkeypatch.setattr(github_connector, "list_repository_events", fail_live_connector)`
  asserting the canonical path does **not** call legacy. The spine **runtime**
  does not import these (confirmed).

Footprint if kept: `closure({connectors.github, source_control})` = **17 modules**,
including legacy model files `agent_models`, `declaration_models`,
`second_opinion_models`, `share_pack_models`, `source_control_models`,
`source_models` — keeping them blocks dropping those 6 tables.

- Question: (a) delete `connectors.github` + `source_control` + orphaned subtree
  and **surgically trim the moot negative-guard lines** from the ~9 spine test
  files (all positive spine assertions kept) — full purge, but edits spine tests;
  or (b) **keep** `connectors.github` + `source_control` (+17-module subtree, 6
  legacy tables not dropped) so spine tests stay untouched.

This conflicts with the "do not touch spine tests" rule, so it is escalated, not
guessed.

## Status

ФАЗА 1 complete. SHARED set is **non-empty** (#1, #2, #5 are real spine
couplings; #3, #4 are mixed-file/doc-test entanglements). Per ФАЗА 2, **STOP
before any deletion** pending human decisions on #1–#5. No files deleted, no
tables dropped. Recovery tag `pre-purge-20260624`.
