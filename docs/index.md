# FounderOS Docs Index

Navigation map for future Codex sessions.

## Current Truth vs Target Direction

- Current operating truth: `playbook.md`, feature docs' current-status/current
  behavior sections, and runbooks for guarded local/manual flows.
- Target direction: `playbook-digital-twin.md` and `vision.md`.
- Historical traceability: archived FOS ledgers and implementation inventories;
  they are not the current feature contract when they conflict with current
  behavior sections.

## Start Here

- `playbook-digital-twin.md`: FounderOS Digital Twin playbook v3 — target
  product and architecture direction (graph, state engine, second opinion, UI),
  not a complete statement of current implementation.
- `vision.md`: condensed north star; superseded in detail by
  `playbook-digital-twin.md`, kept as the short map.
- `playbook.md`: operating playbook v2 — phases, usage gates, weekly ritual,
  eval contract. Execution law: vertical slices, WIP=1.
- `../AGENTS.md`: agent operating rules.
- `../CLAUDE.md`: AI/token/extraction rules.
- `architecture.md`: system overview.
- `workflows.md`: common development workflows.
- `coding-rules.md`: repository coding rules.
- `data-model.md`: operational data model.
- `backlog.md`: small FOS tickets.
- `mvp-quickstart.md`: manual MVP knowledge processing quickstart.
- `../SECURITY_BASELINE.md`: threat model and security baseline.

## Security Docs

- `security/api-boundary.md`: API auth, rate-limit, signature-validation, and approval-boundary plan.

## Feature Docs

- `features/ingestion.md`: raw/document/event ingestion.
- `features/source-events.md`: normalized source event foundation.
- `features/source-integrations.md`: Source Control, external source identity, credentials, and activation contract.
- `source-connectors.md`: safe connector execution, Source Control requests, ingestion, normalization, and secret handling.
- `features/extraction.md`: task/risk/decision extraction.
- `features/retrieval.md`: search and Q&A.
- `features/attention.md`: scoring and attention dashboard.
- `features/telegram-digest.md`: Telegram founder interface and daily digest contract.
- `features/company-brain.md`: Company Brain preview, computed repo audit, provenance, and guardrails.
- `features/obsidian-export.md`: read-only Obsidian export.
- `obsidian-bridge.md`: native local Obsidian vault bridge and sync flow.
- `features/local-ui.md`: local founder command center at `/ui`.
- `features/knowledge-graph.md`: entity graph core, lift agents, approval queue, metric snapshots.
- `features/gmail.md`: Gmail connector status.
- `features/drive.md`: Drive connector status.

## Runbooks

- `operator_runtime_setup.md`: project-local `.env`, health checks, and Codex launcher setup.
- `dev-env.md`: automatic local workspace bootstrap, local env override, and local UI startup.
- `obsidian-bridge.md`: local Obsidian vault bridge, sync, and open-link flow.
- `runbooks/guarded-operations.md`: guarded execution boundaries, GitHub
  target-org migration metadata, and safe diagnostics.
- `runbooks/jira-operating-model.md`: safe Jira inventory diagnostics,
  operating model, and creation dry-run boundary.
- `ops/jira-target-blueprint.md`: clean from-scratch Jira target model
  (projects, boards, issue types, workflow, components, labels, ownership,
  DoR/DoD, repo↔project mapping, agent rules, rollout sequence).
- `ops/jira-rebuild-audit.md` / `ops/jira-rebuild-runbook-draft.md`:
  read-only audit, discovery package, and no-write migration runbook.
- `runbooks/google-local-backfill.md`: Google preflight and Gmail/Drive
  compatibility request-wrapper runbook; preferred operator path is Source
  Control.

## Doctor Scripts

- `../scripts/bootstrap_local_workspace.py`: creates the gitignored `.local/` workspace,
  preserves local env override secrets, and safely copies an existing Obsidian vault.
- `../scripts/start_local.py`: bootstraps local runtime files, runs migrations, and
  starts the local backend on `127.0.0.1:8765`.
- `../scripts/doctor_guarded_execution.py`: read-only guarded-execution safety preflight.
- `../scripts/doctor_external_connector_config.py`: read-only GitHub/Jira configuration doctor.
- `../scripts/report_guarded_execution_readiness.py`: read-only guarded-execution readiness report.
- `../scripts/check_external_connectors_readonly.py`: read-only GitHub/Jira connector smoke report.
- `../scripts/check_github_org_readonly_inventory.py`: read-only GitHub organization inventory and migration-readiness report.
- `../scripts/check_jira_readonly_inventory.py`: read-only Jira inventory and portfolio-mapping report.
- `../scripts/plan_jira_creation_dry_run.py`: no-live, no-write Jira creation dry-run report.
- `../scripts/plan_jira_write_readiness.py`: no-live, no-write Jira write-readiness report.
- `../scripts/report_ignored_file_cleanup_plan.py`: read-only ignored/local file cleanup planner.

## Examples

- `../.env.example`: placeholder-only project-local operator config template.

## Agent Workflows

- `agents/ingestion-agent.md`
- `agents/chunking-agent.md`
- `agents/extraction-agent.md`
- `agents/validation-agent.md`
- `agents/retrieval-agent.md`
- `agents/digest-agent.md`

## Decisions

- `decisions/0001-founder-os-core-architecture.md`

## Repo Navigation Rules

- Do not scan the whole repo unless explicitly needed.
- Prefer `rg`, `find`, and targeted files.
- Future behavior changes must update the relevant docs in the same task.
