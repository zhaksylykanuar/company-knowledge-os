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
5. Run `git diff --check`.
6. Run a direct diff secret scan.
7. Run a hidden/bidi/control Unicode audit for docs when relevant.
8. Commit locally.
9. Report the summary for human review.
10. Push `origin main` only after explicit human approval.

Do not create branches or Draft PRs for routine docs, config, test, or small implementation tickets.

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
