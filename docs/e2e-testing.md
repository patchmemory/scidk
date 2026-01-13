# E2E Testing Quickstart

This guide explains how to run the smoke E2E tests and how they map to the active story/phase.

## Prerequisites
- Python environment set up (see README/requirements.txt)
- Playwright installed for the chosen variant (Python or TS). For Python,
  run: `pip install pytest pytest-playwright` then `playwright install --with-deps`
- Application can be started locally (default dev port assumed)

## Start the app server
- Local dev: `python -m scidk.app`
- Or use your preferred launcher (Makefile/script). Note the base URL shown in logs (e.g., http://localhost:5000).

## Environment for tests
- Set BASE_URL for E2E to point to the running server, for example:
  - Linux/macOS: `export BASE_URL="http://localhost:5000"`
  - Windows (Powershell): `$env:BASE_URL = "http://localhost:5000"`

## Running E2E smoke tests
- Python Playwright (pytest):
  - `pytest -q -m e2e --maxfail=1`
  - Or run a single spec: `pytest tests/e2e/test_home_scan.py -q`
- TypeScript Playwright:
  - `npx playwright test`

Notes:
- Smoke specs should run in <5s each and not require external services.
- Optional features (Neo4j/APOC/rclone) are gated behind feature flags.

## dev.cli helpers
- Show prioritized Ready Queue: `python -m dev.cli ready-queue`
- Validate a task file: `python -m dev.cli validate task:e2e:01-smoke-baseline`
- Start working on the top task: `python -m dev.cli start`
- Branch hygiene (non-blocking): `python -m dev.cli branch-guard` (add --json for machine-readable)
- Finish the git (stage, commit, push, print PR link): `python -m dev.cli git-finish -m "chore: update docs"` (add --json for structured output)

## Active Story & Phase
- See `dev/cycles.md` for the current Active Story/Phase pointer.
- E2E Story: `dev/stories/e2e-testing/story.md`
- Phases: `dev/stories/e2e-testing/phases/`
- Tasks: `dev/tasks/e2e/`

## Troubleshooting
- Ensure BASE_URL is set and reachable.
- If running headless in CI, confirm browsers are installed (`playwright install`).
- If optional deps (openpyxl/pyarrow) are not installed, related export tests will be skipped or should target CSV-only paths.
- Check server logs for endpoint errors during tests (`/api/interpreters*`, `/api/scans/<id>/interpret`).

## Process note
- We keep one active branch per contributor and rely on CI as the gate. See docs/branching-and-ci.md for details and a short PR checklist.
