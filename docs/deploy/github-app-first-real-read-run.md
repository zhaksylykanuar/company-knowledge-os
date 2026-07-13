# GitHub App First Real Read Run Runbook

Status: **manual, human-approved, read-only runbook**. This document defines the
first explicitly approved GitHub App real-provider read run. It does not start a
read run, does not authorize any provider writes, and does not add automation.
The run itself remains a single admin-triggered, repository-scoped action a human
performs after the offline preflight passes.

This closes the "GitHub App real read run readiness" gap named in
`../TODO.md` (item 4) and in `../ROADMAP.md` Phases 2/3/4. It is the authoritative
next MVP milestone from `../../founderOS_MASTER_PLAYBOOK.md` section 1.4 (Sync
GitHub then see real data), gated behind DEC-052 and DEC-053.

## Boundaries

- Read-only. No provider writes. No auto-deploy. No LLM.
- One workspace, one installation, an explicit list of `owner/repo` names.
- Installation access tokens are minted just-in-time and never persisted
  (DEC-052).
- Webhooks stay deferred until raw-body signature verification and delivery
  dedupe exist (DEC-053).
- Do not paste secret values, token/key contents, database URLs, installation
  identifiers, or provider payloads into this repo, logs, or docs. Use env
  variable names and placeholder examples only.

## Prerequisites (offline)

1. A GitHub App exists and is installed on the target account/org with read
   access to the repositories you intend to read.
2. The backend environment provides the GitHub App config (names only):
   - `FOUNDEROS_GITHUB_APP_ID`
   - `FOUNDEROS_GITHUB_APP_SLUG` or `FOUNDEROS_GITHUB_APP_SETUP_URL`
   - `FOUNDEROS_GITHUB_APP_PRIVATE_KEY` or `FOUNDEROS_GITHUB_APP_PRIVATE_KEY_PATH`
3. A local repository surface exists (for example `.local/repos.json`) so the
   scoped read has explicit targets.

## Step 1 - Offline preflight

Run the offline, read-only preflight. It performs no provider calls and prints
presence booleans and the next step only:

```bash
uv run python scripts/github_app_real_read_run_preflight.py
# or machine-readable:
uv run python scripts/github_app_real_read_run_preflight.py --json
```

Proceed only when environment config is complete and the local repository surface
is non-empty. The preflight cannot verify the installation-connection record
offline; confirm that in-app in Step 2.

## Step 2 - Record the workspace-scoped installation connection

Record (or confirm) the workspace-scoped GitHub App installation connection via
the existing admin endpoint. This stores installation metadata only and starts no
provider read:

```txt
POST /api/v1/workspaces/{workspace_id}/github/connections/app-installation
```

The response returns `provider_sync_started: false` and
`installation_access_token_persisted: false`.

## Step 3 - Run one scoped real read sync (human-approved)

With an explicit, minimal repository list, trigger the polling-only read sync
(DEC-053). This is the human-approved real read run:

```txt
POST /api/v1/workspaces/{workspace_id}/github/connections/app-installation/sync
{
  "connection_id": "<connection-uuid>",
  "repositories": ["<owner>/<repo>"],
  "include_issues": true,
  "include_pull_requests": true
}
```

The endpoint mints a just-in-time installation token, reads only the requested
installation repositories/issues/PRs, persists through the existing idempotent
canonical normalization/upsert path, and returns
`external_write_performed: false`.

## Step 4 - Verify the real data landed

- Confirm Dashboard / Company Brain now show the read repositories, issues, and
  PRs with evidence refs.
- Generate a deterministic Founder Briefing and confirm evidence refs resolve.
- Keep the repository scope minimal for the first run; expand later, one explicit
  repository at a time.

## Rollback / safety

- The read run is read-only; there is nothing external to roll back.
- To stop reading, simply do not run the sync again. No background job runs.
- If a read fails, the API returns a sanitized provider status/message without
  leaking authorization headers, tokens, or provider payload dumps.
