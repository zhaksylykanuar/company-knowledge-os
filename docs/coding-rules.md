# Coding Rules

## Status

- Python 3.12 backend: implemented
- Async SQLAlchemy style: implemented
- Deterministic-first processing: implemented
- Strict auth boundary: partial

## Repo Rules

- Prefer existing patterns over new abstractions.
- Keep changes scoped to the requested behavior.
- No large refactors without explicit approval.
- No unrelated edits.
- Do not scan the whole repo unless explicitly needed.
- Prefer `rg`, `find`, and targeted files.

## Data Rules

- Raw storage + Postgres are the source of truth.
- Obsidian is export-only.
- Every extracted task/risk/decision must have `evidence_refs`.
- Never persist unsupported claims.

## AI Rules

- LLM outputs used in pipelines must be strict JSON.
- LLM output must be validated before persistence.
- If evidence is missing, return `null`, an empty array, or `insufficient evidence`.
- LLM must not directly mutate production data.

## Files To Avoid Unless Requested

- `.env` and secrets.
- `raw_storage/`.
- `obsidian_vault/`.
- `migrations/`.
- `NOTES.md`.
- `SECURITY_BASELINE.md`.
