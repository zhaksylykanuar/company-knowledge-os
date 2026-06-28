# founderOS Web

Minimal Next.js shell for the FounderOS MVP backend flow.

## Install

```bash
npm install
```

## Run locally

Start the backend first from the repository root, then run the frontend:

```bash
npm run dev
```

The app starts on the Next.js default port unless you pass a port to `next dev`.
The browser talks to the backend **same-origin**: `web/next.config.mjs` proxies
`/api/*` and `/health` to the backend (see Environment below), so the session
cookie stays first-party and no browser CORS is needed for the normal path.
(`FOUNDEROS_CORS_ALLOWED_ORIGINS` only matters if the browser is pointed at a
separately hosted API instead of the proxy.)

## Build and deploy-readiness checks

```bash
npm test
npm run build
npm run typecheck
npm run lint
```

These commands are enforced by the repository CI deploy-readiness workflow. They
do not require provider credentials or live backend/provider calls.

## Environment

The frontend proxies `/api/*` and `/health` to the backend so the session cookie
is first-party. Configure the proxy target (server-only):

```bash
FOUNDEROS_API_PROXY_TARGET=<backend-internal-base-url>
```

It falls back to `NEXT_PUBLIC_API_BASE_URL`, then to `http://localhost:8000` if
neither is set:

```bash
NEXT_PUBLIC_API_BASE_URL=<backend-public-base-url>
```

## Authentication

The app is gated behind email+password login on server-side sessions:

- A `/login` page calls `POST /api/v1/auth/login`; an `AuthGate` redirects
  unauthenticated users to `/login`.
- The session is an httpOnly first-party cookie (set by the backend); the
  workspace is derived from the session, not entered in the browser.
- The Settings page is an account / change-password page
  (`POST /api/v1/auth/change-password`), not an operator-key/owner-email config
  page. Provision the founder account from the repository root with
  `scripts/create_admin_user.py` (see the root README).

The browser sends no operator API key and no owner email; the operator API key is
for server/CI/admin tooling only. The frontend never calls GitHub, Jira, Gmail,
Drive, or other providers directly. Do not commit secrets, API keys, provider
tokens, or local environment files.

All user-facing copy is centralized in `web/lib/messages.ts` (Russian).

## Private-beta notes

See [`../docs/deploy/private-beta.md`](../docs/deploy/private-beta.md) for the manual split-service deploy runbook and [`../docs/deploy/railway-private-beta.md`](../docs/deploy/railway-private-beta.md) for the current Railway dry-run target map.

The frontend is a private-beta shell. Production auth/session handling is now in
place (email+password login on server-side sessions); the remaining gaps before
broader private beta are GitHub onboarding and the first production deploy of the
auth phase.
