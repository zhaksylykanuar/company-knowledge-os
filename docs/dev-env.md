# Local dev environment

Run FounderOS locally and have the browser auto-connect — no manual API
key entry, no manual endpoint configuration.

## Setup

```bash
# 1. Create your local override (gitignored). Start from the template:
cp .env.example .env.local

# 2. In .env.local set the local dev bootstrap values:
#    APP_ENV=local
#    FOUNDEROS_API_BASE_URL=http://127.0.0.1:8765
#    FOUNDEROS_DEV_API_KEY=local-dev-key
#    FOUNDEROS_ENABLE_BROWSER_DEV_CONFIG=true
#    FOUNDEROS_API_KEYS=local-dev-key

# 3. Start the backend:
uv run uvicorn app.main:app --port 8765

# 4. Open the UI:
open http://127.0.0.1:8765/ui
```

FounderOS calls `GET /v1/dev/browser-config` (local-only), picks up the
dev key into a **session-only runtime variable** (never persisted to
`localStorage`), authenticates the local backend, and loads the Command
Center. A `LOCAL DEV` badge shows API / auth / view status.

## Config precedence

Highest wins: **real environment variables > `.env.local` > `.env` >
built-in defaults.** A missing file is skipped. `.env.local` and
`.env.*.local` are gitignored; `.env.example` is the committed template.

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

## Production

In any non-local deployment the dev endpoint is disabled (404), the dev
key is never handed out, and the UI uses normal auth /
`localStorage` / real deployment config. External secrets remain
backend-only everywhere.
