# Workflows

## Status

- Local app workflow: partial
- Docker Postgres/Redis workflow: implemented
- Docs-update workflow: implemented by policy
- Production deployment workflow: unknown

## Standard Task Workflow

1. Read `docs/index.md`, `AGENTS.md`, and relevant feature docs.
2. Use targeted `rg`/`find` inspection.
3. Make only scoped changes requested by the task.
4. Update relevant docs when behavior changes.
5. Run focused checks appropriate to the change.
6. Report blocked checks explicitly.

## Solo Trunk Workflow

Use this as the default for small focused tickets while this project has one active developer:

1. Work directly on `main`.
2. Start with a clean worktree and run `git pull --ff-only origin main`.
3. Make one small focused change.
4. Run focused checks only.
5. Commit locally.
6. Report the summary for human review.
7. Push `origin main` only after explicit human approval.

Do not create branches or Draft PRs for routine docs, config, test, or small implementation tickets.

### Risk-Based Check Profiles

Use the lightest check profile that still matches the ticket risk. Avoid
duplicating equivalent git checks unless the user asks for an audit-style
review.

#### Lightweight Docs-Only Checks

Use this profile for routine docs-only and process-only changes.

Before editing:

- `git branch --show-current`
- `git status --short`
- `git pull --ff-only origin main`
- `git log -1 --format=%H%n%s`

Before commit:

- `git diff --name-only`
- `git diff --check`
- Review `git diff` for intended docs-only content and no sensitive data.

After commit:

- `git status --short`
- `git log -1 --format=%H%n%s`

Before push:

- `git fetch --prune origin main`
- `git rev-list --left-right --count HEAD...origin/main`
- Push only when the local branch is ahead by 1 commit and behind by 0.

After push:

- `git status --short`
- `git rev-list --left-right --count HEAD...origin/main`
- Expected result: `0 0`.

Do not run pytest for docs-only changes unless the user explicitly requests it
or the docs change includes generated artifacts that need a dedicated verifier.

#### Small Code Change Checks

- Use the same solo trunk git flow.
- Run only focused tests relevant to the changed behavior first.
- Broaden checks only when the changed surface is shared or high risk.
- Update docs in the same ticket when behavior changes.

#### Sensitive Google, Raw Storage, Or Security Checks

- Keep stricter focused safety checks for Google, raw storage, auth, webhook,
  LLM pipeline, and production data boundaries.
- Include guardrail, redaction, limit, auth, and persistence tests when
  relevant to the changed behavior.
- Do not call real external APIs unless the ticket explicitly allows it.
- Do not directly mutate production data through LLM workflows.
- Do not commit secrets, credentials, tokens, or private metadata.

#### Risky Or Large Changes

- Use a branch and PR instead of direct `main`.
- Require explicit approval before large refactors.
- Prefer CI or external review before merging changes with broad blast radius.

#### Command Hygiene

- Avoid commands that print author emails, local machine metadata, or private
  provider metadata when they are not needed.
- Prefer `git log -1 --format=%H%n%s` for latest-commit verification.
- Do not use `git show --format=fuller` in normal workflow prompts.
- Keep command output in task reports limited to the fields needed for the
  decision.

### Use Branches Or PRs For

- Migrations or schema changes.
- Dependency or lockfile changes.
- Large refactors.
- Raw storage or Postgres persistence behavior changes.
- LLM pipeline persistence behavior changes.
- Production data mutation logic.
- Risky auth or security changes.
- Large diffs that need GitHub review.
- Any change where CI or external review should gate merge.

### Safety Gates

- Keep the worktree clean before starting.
- Keep tickets small.
- Do not commit secrets.
- Do not edit `.env` values.
- Do not edit `raw_storage/` or `obsidian_vault/` unless explicitly approved.
- Do not run full pytest unless justified.
- Use focused tests and checks.
- Update docs when behavior changes.
- Do not push until the human says to push.

### Invariants

- Raw storage and Postgres are the source of truth.
- Obsidian is export-only.
- Every extracted task, risk, and decision must have `evidence_refs`.
- Hallucinated facts must not be persisted.
- LLM pipeline outputs must be strict JSON and validated before persistence.
- LLMs must not directly mutate production data.
- No large refactors without explicit approval.

## Local Services

- Postgres and Redis are defined in `docker-compose.yml`.
- DB-backed tests need Postgres on `localhost:5432`.
- If Postgres is not running, report DB tests as blocked.

## Docs-Only Changes

- Do not run pytest unless requested.
- Run `git status --short`.
- Use the lightweight docs-only check profile above.
- Do not edit generated Obsidian vault files.

## API Security Workflow

1. Classify the endpoint as public, protected, webhook, or write/action.
2. Define auth, signature-validation, and rate-limit expectations.
3. Add focused tests when enforcement is implemented.
4. Update `SECURITY_BASELINE.md` and the relevant feature docs.

## Forbidden Without Explicit Approval

- Large refactors.
- Unrelated edits.
- Secret or `.env` value edits.
- Migration changes.
- Raw storage edits.
