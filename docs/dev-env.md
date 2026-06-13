# Local dev environment

Run FounderOS locally and have the browser auto-connect — no manual API
key entry, no manual endpoint configuration.

## Setup

```bash
# 1. Bootstrap project-local runtime files. This creates .local/ and updates
#    .env.local without deleting existing local secrets.
uv run python scripts/bootstrap_local_workspace.py --apply

# 2. Start the local backend. This also checks bootstrap state and runs
#    alembic upgrade head before uvicorn.
uv run python scripts/start_local.py

# 3. Open the UI:
open http://127.0.0.1:8765/ui
```

The local workspace lives inside the repository and is gitignored:

```text
.local/
  obsidian/FounderOS Knowledge Vault/
  data/
  logs/
  tmp/
  exports/
  cache/
  backups/
  migration-log.json
```

FounderOS calls `GET /v1/dev/browser-config` (local-only), picks up the
dev key into a **session-only runtime variable** (never persisted to
`localStorage`), authenticates the local backend, and loads the Command
Center. A `LOCAL DEV` badge shows API / auth / view status.

## Config precedence

Highest wins: **real environment variables > `.env.local` > `.env` >
built-in defaults.** A missing file is skipped. `.env.local` and
`.env.*.local` are gitignored; `.env.example` is the committed template.

`scripts/bootstrap_local_workspace.py` writes a managed block in `.env.local`
for local browser bootstrap and Obsidian bridge paths. Existing custom lines
and backend-only secrets are preserved.

## Safety model

- `GET /v1/dev/browser-config` exists **only** when `APP_ENV=local` **and**
  `FOUNDEROS_ENABLE_BROWSER_DEV_CONFIG=true`; otherwise it is `404`.
- It returns **only** `api_base_url`, `dev_api_key`, `app_env`, `features`
  (built from an explicit allowlist in `sanitize_browser_config`).
- External / third-party secrets — `OPENAI_API_KEY`, `GITHUB_TOKEN`,
  `JIRA_API_TOKEN`, `GMAIL_CLIENT_SECRET`, OAuth secrets, connector
  credentials — stay **backend-only** and are never sent to the browser.
- The `dev_api_key` authenticates the **local backend only**.
- A manual key in `localStorage` always overrides the dev key.
- `.local/`, `.env.local`, generated vault files, logs, cache, backups and
  exports are local runtime artifacts and must not be committed.

## Production

In any non-local deployment the dev endpoint is disabled (404), the dev
key is never handed out, and the UI uses normal auth /
`localStorage` / real deployment config. External secrets remain
backend-only everywhere.
