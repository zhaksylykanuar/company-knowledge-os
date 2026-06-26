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
The backend must allow the frontend origin through `FOUNDEROS_CORS_ALLOWED_ORIGINS`
when the browser calls a separately hosted API.

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

Optional public backend base URL:

```bash
NEXT_PUBLIC_API_BASE_URL=<backend-public-base-url>
```

If `NEXT_PUBLIC_API_BASE_URL` is not set, the frontend uses its built-in local
fallback. Local operator settings entered in the Settings page can override this
value in the browser.

## Local operator settings

The operator API key, owner email, workspace ID, and API base URL are entered in
the browser Settings page and stored in browser local storage for local MVP use.
Do not commit secrets, API keys, provider tokens, local environment files, or
copied Settings values.

The API key is sent to the backend with the configured `API_AUTH_HEADER_NAME`
header. The frontend never calls GitHub, Jira, Gmail, Drive, or other providers
directly.

## Private-beta notes

The current frontend is still an operator/private-beta shell. Before broader
private beta, production auth/session handling and GitHub onboarding must replace
browser-local operator key entry.
