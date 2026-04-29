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
