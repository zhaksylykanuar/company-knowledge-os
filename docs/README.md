# FounderOS Docs

This is the single navigation entry for the active FounderOS 2.0 documentation.
The product is an AI partner with evidence-backed company memory. Superseded
Command Center documentation is not part of the active set.

## Reading Order

1. [`../README.md`](../README.md) - human/developer onboarding and local run
   path.
2. [`../founderOS_MASTER_PLAYBOOK.md`](../founderOS_MASTER_PLAYBOOK.md) -
   canonical product/MVP scope (**what** to build). Its status block is
   summarized from the live docs; it is not the live task tracker.
3. [`../PROGRESS.md`](../PROGRESS.md) - live state, gate health, and next task
   pointer (**where** we are).
4. [`DECISIONS.md`](DECISIONS.md) - durable repo decisions and explicit conflict
   resolutions (**why**).
5. [`ROADMAP.md`](ROADMAP.md), [`TODO.md`](TODO.md),
   [`POST_MVP.md`](POST_MVP.md), and [`CHANGELOG.md`](CHANGELOG.md) - planning,
   near-term backlog, deferred scope, and dated change history.
6. [`AI_FOUNDEROS_ACCEPTANCE.md`](AI_FOUNDEROS_ACCEPTANCE.md) - executable
   acceptance ledger for the AI-first product reset.

## Source-of-truth Matrix

| Question | Use |
|---|---|
| What is this project and how do I run it? | [`../README.md`](../README.md) |
| What is the MVP/product scope? | [`../founderOS_MASTER_PLAYBOOK.md`](../founderOS_MASTER_PLAYBOOK.md) |
| What is implemented right now and what is next? | [`../PROGRESS.md`](../PROGRESS.md) |
| Why was an architecture/product choice made? | [`DECISIONS.md`](DECISIONS.md) |
| What is the current development workflow for agents? | [`../AGENTS.md`](../AGENTS.md) and [`../CLAUDE.md`](../CLAUDE.md) |
| What are the safety/security boundaries? | [`../AGENTS.md`](../AGENTS.md), [`../CLAUDE.md`](../CLAUDE.md), [`../SECURITY_BASELINE.md`](../SECURITY_BASELINE.md) |
| What should be built next? | [`../PROGRESS.md`](../PROGRESS.md), then [`TODO.md`](TODO.md) |
| How is the AI-first product reset verified? | [`AI_FOUNDEROS_ACCEPTANCE.md`](AI_FOUNDEROS_ACCEPTANCE.md) |
| What is intentionally deferred? | [`POST_MVP.md`](POST_MVP.md) |
| How should FounderOS learn what every repository does and how repositories relate? | [`REPOSITORY_INTELLIGENCE_IMPLEMENTATION_PLAN.md`](REPOSITORY_INTELLIGENCE_IMPLEMENTATION_PLAN.md) |
| How should Repository Intelligence be prepared and launched operationally? | [`REPOSITORY_INTELLIGENCE_FULL_GUIDE_RU.md`](REPOSITORY_INTELLIGENCE_FULL_GUIDE_RU.md) |
| How do we validate the private L0/L1 portfolio manifest without starting a repository read? | [`deploy/repository-intelligence-portfolio-dry-run.md`](deploy/repository-intelligence-portfolio-dry-run.md) |
| How do we run, verify, back up, and stop FounderOS? | [`operations/local-runtime.md`](operations/local-runtime.md) |
| How do we recover after loss of the FounderOS machine? | [`operations/disaster-recovery.md`](operations/disaster-recovery.md) |
| Where do secrets and runtime settings belong? | [`operations/secrets-and-environment.md`](operations/secrets-and-environment.md) |
| How are connector credentials saved and verified in the product? | [`integrations-control-center.md`](integrations-control-center.md) |
| How do we prove a bounded provider read or external action? | [`deploy/github-app-first-real-read-run.md`](deploy/github-app-first-real-read-run.md) and [`deploy/external-action-result-smoke.md`](deploy/external-action-result-smoke.md) |

## Operations And Human-Gated Runbooks

- [`integrations-control-center.md`](integrations-control-center.md) - secure
  owner/admin configuration, fixed provider read probes, dry-run write
  readiness, runtime gates, and explicitly missing OAuth/write capabilities.
- [`operations/local-runtime.md`](operations/local-runtime.md) - canonical local start, doctor, smoke, backup/restore, stop, recovery, and external-resource deletion boundary.
- [`operations/disaster-recovery.md`](operations/disaster-recovery.md) -
  encrypted independent copy, restore drills, recovery objectives, retention,
  and explicit human-operated boundaries.
- [`operations/secrets-and-environment.md`](operations/secrets-and-environment.md) -
  the single `.env.local` bootstrap boundary and the encrypted, UI-only
  provider credential lifecycle.
- [`deploy/github-app-first-real-read-run.md`](deploy/github-app-first-real-read-run.md) - human-approved first-read runbook through the managed `/settings/integrations/github` flow.
- [`deploy/repository-intelligence-portfolio-dry-run.md`](deploy/repository-intelligence-portfolio-dry-run.md) - preparation-only validation for a private exact-SHA L0/L1 manifest; performs zero provider/repository reads and leaves L2 disabled.
- [`deploy/external-action-result-smoke.md`](deploy/external-action-result-smoke.md) - manual, human-approved, one-action write smoke for proving the final "Approve Action Proposal -> See External Action Result" MVP step after local acceptance and read-only provider proof.
- `make local-readiness` is the sanitized repository-evidence report;
  `make release-handoff` and `scripts/private_beta_release_handoff.py` remain
  compatibility aliases for that same local report, not hosted-runtime paths.

The former private-beta/Railway runbooks and placeholder hosting templates were
removed by DEC-077. They remain recoverable from git history but must not be used
as current operating instructions.

## Required Control Docs

- [`DECISIONS.md`](DECISIONS.md)
- [`ROADMAP.md`](ROADMAP.md)
- [`TODO.md`](TODO.md)
- [`POST_MVP.md`](POST_MVP.md)
- [`CHANGELOG.md`](CHANGELOG.md)
- [`AI_FOUNDEROS_ACCEPTANCE.md`](AI_FOUNDEROS_ACCEPTANCE.md)

## Audit Trail

- [`_audit/DOCS_AUDIT.md`](_audit/DOCS_AUDIT.md) - documentation consolidation +
  code-reality reconciliation.
- [`_audit/PURGE_AUDIT.md`](_audit/PURGE_AUDIT.md) - Lineage-2 purge
  classification and recovery instructions (tag `pre-purge-20260624`).

Older supporting/feature/runbook docs and the archive were removed in the
Lineage-2 purge; recover any from git tag `pre-purge-20260624` if needed.

## Future Agent Documentation Rules

- Update docs in the same task as the behavior change; do not leave a separate
  "docs later" task unless the current task is explicitly read-only.
- Keep `PROGRESS.md` short at the top: current state, gate health, next step.
  Historical session detail may stay below, newest first.
- Keep `TODO.md` focused on near-term work. Move deferred ideas to
  `POST_MVP.md` and remove completed task scaffolding when it becomes noise.
- Add a `DECISIONS.md` entry for durable architecture, security, deploy,
  data-model, or scope changes. Do not use changelog entries as substitutes for
  decisions.
- Do not write real secrets, token values, database URLs, provider payloads, raw
  private source bodies, chat IDs, or production smoke outputs into docs.
- Use placeholder env examples only (`<placeholder>`). `.env.example` is a
  template, not real config.
- Delete obsolete docs only when they are clearly superseded or recoverable from
  git history/tag. If unsure, preserve the file and document the uncertainty.
