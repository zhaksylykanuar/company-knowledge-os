# AGENTS.md

Operational rules for Codex and other AI agents working in FounderOS.

## Start Here

- Read `docs/index.md`, this file, and `CLAUDE.md` before making changes.
- Use targeted inspection with `rg`, `find`, and specific files.
- Do not scan the whole repo unless the task explicitly requires it.
- Check `git status --short` before edits and do not overwrite unrelated work.

## Plan First

- For non-trivial code changes, first restate the task, list relevant files, propose a short plan, and wait for approval.
- Inspect at most 8 implementation files before planning unless the task clearly requires more.
- If more files are needed, explain why before expanding scope.

## Task Prompts

- Task prompts must be short: `Goal / Context / Constraints / Done when`.
- Durable rules live in this file and `CLAUDE.md`; do not re-paste them into
  task prompts. A task prompt references AGENTS.md instead of copying it.
- Task-specific constraints belong in the prompt only when they are not already
  covered here.
- `Done when` must include verifiable checks, normally
  `uv run ruff check .` and `uv run pytest -q` green.

## Sanitization Scope

- Never print, stage, or commit secrets: tokens, API keys, credential values,
  webhook values, chat IDs, `.env` contents, raw private source bodies, or
  provider payloads containing private data.
- Git metadata of this repository is NOT secret: commit hashes, branch names,
  file paths, diffs of tracked source files, and the repo name may be printed
  and inspected freely. Hiding them reduces auditability; do not redirect or
  suppress normal git output.

## Default Git Workflow

- Default to solo trunk-based work for small focused tickets.
- Work directly on `main` after `git pull --ff-only origin main`.
- Make one scoped change, run focused checks, commit locally, and report for human review.
- Do not push until the human explicitly says to push.
- Do not create branches or Draft PRs for routine docs, config, test, or small implementation tickets.
- Use a branch and PR for migrations, dependency or lockfile changes, large refactors, raw storage or Postgres persistence behavior changes, LLM pipeline persistence behavior changes, production data mutation logic, risky auth/security changes, large diffs, or any change that needs CI or external review before merge.

## Core Invariants

- Raw storage + Postgres are the source of truth.
- Obsidian is export-only.
- Every extracted task/risk/decision must have `evidence_refs`.
- LLM outputs used in pipelines must be strict JSON and validated before persistence.
- If evidence is missing, return `null`, an empty array, or `insufficient evidence`.
- LLM must not directly mutate production data.

## Change Rules

- No large refactors without explicit approval.
- No unrelated edits.
- Never edit secrets, `.env` values, raw storage, or generated Obsidian vault files.
- Do not edit migrations unless the task explicitly requires a schema change.
- Future behavior changes must update the relevant docs in the same task.

## Verification

- For code changes, prefer focused tests first, then broader checks when needed.
- For docs-only changes, do not run pytest unless requested.
- If Postgres is unavailable, report DB-backed tests as blocked rather than hiding failures.
