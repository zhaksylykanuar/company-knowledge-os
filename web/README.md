# founderOS Web

Minimal Next.js shell for the founderOS MVP backend flow.

## Install

```bash
npm install
```

## Run locally

```bash
npm run dev
```

The app starts on the Next.js default port unless you pass a port to `next dev`.

## Build

```bash
npm run typecheck
npm run build
npm run lint
```

## Environment

Optional public backend base URL:

```bash
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

If the variable is not set, the frontend defaults to `http://localhost:8000`.
Local operator settings entered in the Settings page can override this value in
the browser.

## Local operator settings

The operator API key, owner email, workspace ID, and API base URL are entered in
the browser Settings page and stored in browser local storage for local MVP use.
Do not commit secrets, API keys, provider tokens, or local environment files.

The API key is sent to the backend with the existing `X-FounderOS-API-Key`
header. The frontend never calls GitHub, Jira, Gmail, Drive, or other providers
directly.
