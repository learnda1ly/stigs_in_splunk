# End-to-end tests (Playwright)

Playwright harness for Splunk Web against the local `stigs_in_splunk` app.

## Prerequisites

- Splunk Web reachable at the configured base URL (default `https://127.0.0.1:8000`)
- Node.js 18+

## Setup

```bash
cd e2e
npm install
npx playwright install chromium
```

## Environment variables

Export these before running tests (never commit credentials):

```bash
export SPLUNK_BASE_URL="https://127.0.0.1:8000"   # optional; this is the default
export SPLUNK_ADMIN_USER="admin"
export SPLUNK_ADMIN_PASSWORD="your-password"
```

`global-setup.js` logs in once and writes session state to `.auth/admin.json` (gitignored).

## Run tests

```bash
npm run test:smoke    # smoke only
npm test              # full suite
```

Organization journey (serial, multiple Splunk users; no admin storage state):

```bash
SPLUNK_BASE_URL=https://127.0.0.1:8000 SPLUNK_ADMIN_USER=admin SPLUNK_ADMIN_PASSWORD='your-password' \
  npx playwright test --project=org
```

## Artifacts

On failure, Playwright keeps traces, screenshots, and video under:

- `e2e/test-results/`
- HTML report: `e2e/playwright-report/` (after a run with the html reporter)

Open a trace: `npx playwright show-trace test-results/.../trace.zip`

## When a test fails

Fix the application or the test, then re-run until the suite passes. Do not leave broken tests as the expected state.
