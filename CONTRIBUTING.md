# Contributing to FounderOS

FounderOS is a private owner-controlled repository. Contribution access does
not grant a license to use or redistribute the code.

## Before changing code

1. Read `AGENTS.md`, `CLAUDE.md`, and `docs/README.md`.
2. Check `PROGRESS.md` and `docs/TODO.md` for the current task boundary.
3. Check `git status --short` and preserve unrelated work.
4. For a non-trivial change, agree on a short plan before implementation.

Use direct `main` work only for small, focused changes. Use a branch and review
for migrations, dependency or lockfile changes, persistence behavior, risky
authentication/security work, production mutation logic, or large refactors.
Do not push without the owner's explicit approval.

## Required invariants

- Raw storage plus PostgreSQL are the source of truth.
- Obsidian is export-only.
- Extracted tasks, risks, decisions, and AI claims require `evidence_refs`.
- Pipeline LLM output must be strict JSON validated before persistence.
- Missing evidence produces `null`, an empty array, or
  `insufficient evidence`.
- LLMs do not directly mutate production data.
- Never commit secrets, `.env` values, raw source bodies, provider payloads,
  database exports, or generated Obsidian vault files.

## Verification

Install the repository-owned local hook once:

```bash
make hooks-install
```

Use a dedicated loopback PostgreSQL test database whose name contains a
standalone test marker:

```bash
FOUNDEROS_TEST_DATABASE_URL='<loopback-postgresql-test-url>' make backend-check
make frontend-check
git diff --check
```

Run focused tests first while developing. Documentation-only changes do not
need pytest unless requested. If PostgreSQL is unavailable, report DB-backed
tests as blocked; never point tests at FounderOS product data.

## Change documentation

Update behavior and its documentation together. Maintain `PROGRESS.md`,
`docs/TODO.md`, `docs/CHANGELOG.md`, and `docs/DECISIONS.md` according to
`AGENTS.md`. Pull requests and commits must stay scoped and must explain what
was verified.
