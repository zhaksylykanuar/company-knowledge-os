# Current Dirty Tree Plan

Status: FOS-AUD-02 planning document. This records how to handle the dirty tree
observed during the alignment audit.

No cleanup, deletion, staging, or refactor is authorized by this document.

## Snapshot

Audit snapshot before the FOS-AUD docs task:

- Modified tracked files: 77.
- Untracked files: 18.
- Staged files: none.
- Tracked diff stat: 3483 insertions, 2445 deletions.

The current docs task adds these expected new docs:

- `docs/ALIGNMENT_AUDIT.md`
- `docs/DECISIONS.md`
- `docs/ROADMAP.md`
- `docs/TODO.md`
- `docs/POST_MVP.md`
- `docs/CURRENT_DIRTY_TREE_PLAN.md`

## Modified Tracked Files

Observed modified tracked files before this docs task:

```text
.github/workflows/ci.yml
README.md
SECURITY_BASELINE.md
app/api/company_brain.py
app/api/drive.py
app/api/gmail.py
app/api/ui.py
app/core/config.py
app/services/action_center.py
app/services/browser_config.py
app/services/command_center.py
app/services/company_brain_preview.py
app/services/connector_clients.py
app/services/connector_diagnostics.py
app/services/connector_scope.py
app/services/data_quality_center.py
app/services/external_connector_registry.py
app/services/founder_overview.py
app/services/github_org_inventory.py
app/services/jira_creation_dry_run.py
app/services/project_status_view.py
app/services/repository_portfolio.py
app/services/source_connectors.py
app/services/source_control.py
app/services/source_run_orchestrator.py
static founder UI HTML file under app/static
docs/architecture.md
docs/data-model.md
docs/features/attention.md
docs/features/drive.md
docs/features/gmail.md
docs/features/ingestion.md
docs/features/knowledge-graph.md
docs/features/local-ui.md
docs/features/source-events.md
docs/features/source-integrations.md
docs/features/telegram-digest.md
docs/index.md
docs/mvp-quickstart.md
docs/ops/jira-target-blueprint.md
docs/playbook-digital-twin.md
docs/playbook.md
docs/runbooks/google-local-backfill.md
docs/runbooks/manual-pilot.md
docs/source-connectors.md
scripts/check_external_connectors_readonly.py
scripts/check_no_secrets.sh
scripts/run_source_requests.py
scripts/sync_github_activity.py
scripts/sync_jira_issues.py
tests/test_api_route_auth.py
tests/test_drive_backfill.py
tests/test_external_connector_readonly_smoke.py
tests/test_external_connector_registry.py
tests/test_founder_ui_api.py
tests/test_github_graph_sync.py
tests/test_github_org_inventory.py
tests/test_github_org_readonly_inventory_cli.py
tests/test_gmail_backfill.py
tests/test_guarded_execution_contracts.py
tests/test_guarded_execution_readiness_report.py
tests/test_jira_graph_sync.py
tests/test_jira_operating_model.py
tests/test_production_operation_guard.py
tests/test_repository_portfolio.py
tests/test_stage14_connector_clients.py
tests/test_stage15_email_and_diagnostics.py
tests/test_stage15_real_connector_gating.py
tests/test_stage16_dq_actions.py
tests/test_stage16_runbook.py
tests/test_stage16_ui_obsidian.py
tests/test_stage17_orchestrator_scope_preview.py
tests/test_stage17_ui_dq_obsidian.py
tests/test_stage19_ui_clarity.py
tests/test_stage23_company_brain.py
tests/test_stage5.py
tests/test_stage9_source_control.py
```

## Untracked Files

Observed untracked files before this docs task:

```text
.github/dependabot.yml
.github/workflows/codeql.yml
.github/workflows/dependency-review.yml
.github/workflows/scorecard.yml
.github/workflows/uv-dependency-submission.yml
.python-version
app/services/repo_audit.py
app/services/repository_source_inventory.py
docs/features/company-brain.md
renovate.json
tests/evals/test_company_brain_repo_audit_eval.py
tests/test_ci_workflow_contract.py
tests/test_docs_navigation_integrity.py
tests/test_founder_overview.py
tests/test_repository_source_inventory.py
tests/test_secret_scan_script.py
tests/test_stage28_company_brain_repo_audit_api.py
tests/test_stage28_repo_audit.py
```

## Logical Groups For Future Commits

### Group A - Alignment Docs

Files:

- `docs/ALIGNMENT_AUDIT.md`
- `docs/DECISIONS.md`
- `docs/ROADMAP.md`
- `docs/TODO.md`
- `docs/POST_MVP.md`
- `docs/CURRENT_DIRTY_TREE_PLAN.md`

Decision: checkpoint first if checks pass.

Reason: docs-only, no behavior change, unlocks scoped future work.

### Group B - CI/Supply Chain Baseline

Files:

- `.github/workflows/ci.yml`
- `.github/dependabot.yml`
- `.github/workflows/codeql.yml`
- `.github/workflows/dependency-review.yml`
- `.github/workflows/scorecard.yml`
- `.github/workflows/uv-dependency-submission.yml`
- `.python-version`
- `renovate.json`
- `scripts/check_no_secrets.sh`
- `tests/test_ci_workflow_contract.py`
- `tests/test_secret_scan_script.py`

Decision: review later as a separate hardening checkpoint.

Reason: valuable but broad; should not be bundled with product alignment.

### Group C - Company Brain / Repo Audit

Files:

- `app/api/company_brain.py`
- `app/services/company_brain_preview.py`
- `app/services/repo_audit.py`
- `app/services/repository_source_inventory.py`
- `app/services/repository_portfolio.py`
- static founder UI HTML file under `app/static/`
- `docs/features/company-brain.md`
- `tests/evals/test_company_brain_repo_audit_eval.py`
- `tests/test_stage23_company_brain.py`
- `tests/test_stage28_company_brain_repo_audit_api.py`
- `tests/test_stage28_repo_audit.py`
- `tests/test_repository_source_inventory.py`

Decision: keep and review as an evidence-first read-model checkpoint.

Reason: aligns with provenance, no raw email, repo as component/evidence, and
computed Company Brain direction.

### Group D - Source Control / Connector Guarding

Files:

- `app/api/drive.py`
- `app/api/gmail.py`
- `app/core/config.py`
- `app/services/connector_clients.py`
- `app/services/connector_diagnostics.py`
- `app/services/connector_scope.py`
- `app/services/external_connector_registry.py`
- `app/services/github_org_inventory.py`
- `app/services/source_connectors.py`
- `app/services/source_control.py`
- `app/services/source_run_orchestrator.py`
- `scripts/check_external_connectors_readonly.py`
- `scripts/run_source_requests.py`
- `scripts/sync_github_activity.py`
- `scripts/sync_jira_issues.py`
- related connector tests.

Decision: keep but freeze expansion until GitHub-first MVP path is decided.

Reason: useful guarded infrastructure, but it must not pull the project away
from the master playbook's first E2E.

### Group E - Local Founder UI / Overview Read Models

Files:

- `app/api/ui.py`
- `app/services/action_center.py`
- `app/services/browser_config.py`
- `app/services/command_center.py`
- `app/services/data_quality_center.py`
- `app/services/founder_overview.py`
- `app/services/project_status_view.py`
- static founder UI HTML file under `app/static/`
- `tests/test_founder_overview.py`
- `tests/test_founder_ui_api.py`

Decision: keep as local/operator UI; do not treat as final Next.js product UI.

Reason: useful current workflow, but Phase 3 still needs a separate Next.js web
app.

### Group F - Existing Docs Updates

Files:

- `README.md`
- `SECURITY_BASELINE.md`
- `docs/architecture.md`
- `docs/data-model.md`
- `docs/features/*`
- `docs/index.md`
- `docs/mvp-quickstart.md`
- `docs/ops/jira-target-blueprint.md`
- `docs/playbook-digital-twin.md`
- `docs/playbook.md`
- `docs/runbooks/*`
- `docs/source-connectors.md`
- `tests/test_docs_navigation_integrity.py`

Decision: review after Group A. Keep current-vs-target boundaries explicit.

Reason: docs are useful, but they currently describe a v2 local/operator
roadmap that must be reconciled with the master playbook.

### Group G - Broad Tests

Files:

- Modified tests not already covered by Groups B-F.

Decision: review with their matching implementation groups.

Reason: tests should travel with the code behavior they verify.

## What Should Be Checkpointed

Checkpoint first:

- Group A alignment docs.

Checkpoint later, in separate scopes:

- CI/supply chain baseline.
- Company Brain/repo audit read model.
- Source Control/connector guard changes.
- Local founder UI/read-model changes.
- Existing docs boundary updates.
- Tests paired with their implementation groups.

## What Should Never Be Committed

Never commit secrets or local/private data:

- `.env`
- project-local env override files
- `.env.*` with local/operator values
- `.local/`
- `raw_storage/`
- `obsidian_vault/`
- `secrets/`
- `operator_outputs/`
- `.operator_outputs/`
- `.venv/`
- `.pytest_cache/`
- `.ruff_cache/`
- `.mypy_cache/`
- `__pycache__/`
- `.DS_Store`

These are local/generated/secret-bearing paths and should stay ignored.

## What Must Not Be Deleted Yet

Do not delete:

- Existing application code.
- Existing source/control connector logic.
- Static `/ui`.
- Company Brain/repo audit work.
- Telegram/manual pilot code.
- Share pack/investor view code.
- Jira planning/dry-run code.
- Existing tests.

Reason: some of these are post-MVP or out of order, but they may contain
working logic and safety contracts.

## What Can Be Reviewed Later

Review later:

- CI/security/dependency automation.
- Existing local/operator docs.
- Advanced diagnostics.
- Telegram/manual pilot flows.
- Share packs/investor view.
- Jira planning/dry-run surfaces.
- Source Control live-provider execution path.

## Post-MVP But Frozen

These areas should remain in the repository if useful, but not expand before
GitHub-first MVP E2E:

- Telegram/manual pilot.
- Share packs/investor view.
- Jira write planning.
- Scheduler/outbox expansion.
- Role agents.
- Multi-model council.
- Natural language rule compiler.
- Sandbox workflow execution.
- Advanced diagnostics.
- Compliance hardening beyond MVP.
- Marketplace/plugins.
- Mobile app.

## Delete Candidate Policy

Use DELETE_CANDIDATE only for clearly generated or local-only artifacts, for
example `.DS_Store`, caches, or accidental local outputs. Do not mark working
source code as DELETE_CANDIDATE during alignment cleanup.
