# Local Founder UI

Read-only founder command center served by the local API.

## Status

- Implemented: SPA at `/ui` (root `/` redirects there) with sections
  Command center, Strategy, Product, Growth, Sales, Finance, Team,
  Tasks, Metrics, Investor view.
- Live data: project status snapshots, attention actions/risks,
  extracted decisions, normalized activity, operational metrics —
  via `GET /v1/founder/overview`.
- Manual sections (strategy, growth, sales, finance, team roles, KPIs,
  weekly focus, investor summary) are edited in the page and stored in
  browser `localStorage` only; they never reach the server.

## How to open

```bash
uv run uvicorn app.main:app --reload
# then open http://localhost:8000/ui
```

If `API_AUTH_ENABLED=true`, click the key button in the top bar and
paste `API_AUTH_KEY`; the auth header NAME is injected into the page
from `API_AUTH_HEADER_NAME`, the key is stored in `localStorage` only.

## Endpoints

| Endpoint | Purpose |
| --- | --- |
| `GET /ui` | static shell, no data, unauthenticated (like `/health`) |
| `GET /v1/founder/overview` | composed read model for all live blocks |
| `GET /v1/founder/status` | Telegram-bot `/status` text (digest overlay) |
| `GET /v1/founder/dev` | Telegram-bot `/dev` text |
| `GET /v1/knowledge/search` | Cmd+K search overlay |

## Boundaries

- `app/services/founder_overview.py` reuses the same public read-model
  builders as the Telegram bot and persists status snapshots the same
  way; it creates no drafts, intentions, or results.
- No LLM calls, no external API calls, no production mutations.
- The page contains no data and no secrets; every data call goes
  through the protected API.
