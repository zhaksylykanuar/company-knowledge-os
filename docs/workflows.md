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

## Local Services

- Postgres and Redis are defined in `docker-compose.yml`.
- DB-backed tests need Postgres on `localhost:5432`.
- If Postgres is not running, report DB tests as blocked.

## Docs-Only Changes

- Do not run pytest unless requested.
- Run `git status --short`.
- Do not edit generated Obsidian vault files.

## Forbidden Without Explicit Approval

- Large refactors.
- Unrelated edits.
- Secret or `.env` value edits.
- Migration changes.
- Raw storage edits.
