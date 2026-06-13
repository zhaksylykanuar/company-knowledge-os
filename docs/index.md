# FounderOS Docs Index

Navigation map for future Codex sessions.

## Start Here

- `playbook-digital-twin.md`: FounderOS Digital Twin playbook v3 — full product
  and architecture source of truth (graph, state engine, second opinion, UI).
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
- `features/source-integrations.md`: external source identity, credentials, and activation contract.
- `source-connectors.md`: safe connector execution, ingestion, normalization, and secret handling.
- `features/extraction.md`: task/risk/decision extraction.
- `features/retrieval.md`: search and Q&A.
- `features/attention.md`: scoring and attention dashboard.
- `features/telegram-digest.md`: future Telegram interface and daily digest contract.
- `features/obsidian-export.md`: read-only Obsidian export.
- `obsidian-bridge.md`: native local Obsidian vault bridge and sync flow.
- `features/local-ui.md`: local founder command center at `/ui`.
- `features/knowledge-graph.md`: entity graph core, lift agents, approval queue, metric snapshots.
- `features/gmail.md`: Gmail connector status.
- `features/drive.md`: Drive connector status.

## Runbooks

- `operator_runtime_setup.md`: project-local `.env`, health checks, and Codex launcher setup.
- `runbooks/guarded-operations.md`: guarded execution boundaries, GitHub
  target-org migration metadata, and safe diagnostics.
- `runbooks/jira-operating-model.md`: safe Jira inventory diagnostics,
  operating model, and creation dry-run boundary.
- `runbooks/google-local-backfill.md`: safe local Gmail and Drive manual backfill runbook.

## Doctor Scripts

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
