# Local Founder UI

Read-only founder command center served by the local API.

## Status

- Implemented: SPA at `/ui` (root `/` redirects there) with sections for the
  command center, Company Brain, sources/data control, data quality, Obsidian
  graph, Action Center, notification center, operating rhythm, share packs,
  role views, investor view, strategy, product, growth, sales, finance, team,
  tasks, and metrics.
- Live data: project status snapshots, attention actions/risks,
  extracted decisions, normalized activity, operational metrics —
  via `GET /v1/founder/overview`.
- Manual sections (strategy, growth, sales, finance, team roles, KPIs,
  weekly focus, investor summary) are edited in the page and stored in
  browser `localStorage` only; they never reach the server. Manual-only
  sections are visibly marked as local and not evidence-backed.
- The overview browser cache is stored under `fos_overview_cache` as an
  envelope with `cached_at` and `overview_generated_at`; stale cached views are
  labelled in the top bar until a fresh server read-model loads.
- Project code metrics (`commits_7d`, PR counts) include source-event
  provenance: the mapped-repository scope, seven-day window, source event
  count, last observed event time, and recent source run IDs.
- Command Center next actions preserve backend provenance from the overview
  read model (`source_document_id`, reasons, evidence status). If the browser
  synthesizes a navigation fallback because the backend returned no actions,
  the UI labels it as `UI fallback · not evidence-backed`.
- Company Brain surfaces are preview/computed read models; they do not call the
  network, write DB rows, expose raw email, or imply that founder-confirmed
  ownership exists before confirmation. The computed repo audit also shows the
  local discovery snapshot mtime/age and marks stale snapshots instead of
  presenting every computed response as fresh.

## How to open

One command bootstraps the gitignored `.local/` workspace and local env
override, runs migrations, and starts the local backend:

```bash
uv run python scripts/start_local.py
# then open http://127.0.0.1:8765/ui
```

In local dev the page auto-loads its dev API key from the local-only
`GET /v1/dev/browser-config` endpoint, so no manual key entry is needed; a
`LOCAL DEV` badge shows API / auth / view status. See `../dev-env.md` for the
full local setup and safety model.

If `API_AUTH_ENABLED=true` without the browser dev bootstrap, click the key
button in the top bar and paste `API_AUTH_KEY`; the auth header NAME is
injected into the page from `API_AUTH_HEADER_NAME`, and the key is stored in
`localStorage` only.

## Endpoints

| Endpoint | Purpose |
| --- | --- |
| `GET /ui` | static shell, no data, unauthenticated (like `/health`) |
| `GET /v1/founder/overview` | composed read model for all live blocks |
| `GET /v1/founder/status` | Telegram-bot `/status` text (digest overlay) |
| `GET /v1/founder/dev` | Telegram-bot `/dev` text |
| `GET /v1/knowledge/search` | Cmd+K search overlay |
| `GET /v1/founder/company-brain/*` | Company Brain preview, people, second opinion, unresolved questions, repo audit |
| `GET /v1/founder/sources` | source configuration and readiness |
| `GET /v1/founder/data-quality` | data-quality center |
| `GET /v1/founder/source-runs` | source-run queue and receipts |
| `GET /v1/founder/action-center` | proposal/action center read model |
| `GET /v1/founder/share-packs` | share-pack summaries |

## Boundaries

- `app/services/founder_overview.py` reuses the same public read-model builders
  as the Telegram bot but does not persist status snapshots for UI GET reads.
- No LLM calls, no external API calls, no production mutations.
- The page contains no data and no secrets; every data call goes
  through the protected API.
