# SciDK Testing Overview

This repository uses pytest for unit, API, and integration-like tests that are hermetic by default (no external services required). The goal is fast feedback with realistic behavior via controlled monkeypatching.

## How to Run

- Preferred: `python3 -m pytest -q`
- Virtualenv: If you use .venv, activate it first; pytest is in requirements.txt and [project] dependencies.
- Dev CLI: `python3 -m dev.cli test` (calls pytest with sensible fallbacks). Some subcommands also run tests as part of DoD checks.
- Pytest config: Defined in pyproject.toml
  - testpaths = ["tests"]
  - addopts = "-q"

## Test Taxonomy and Organization

The test suite is organized into several layers with different purposes:

### Unit Tests
- **Purpose:** Fast, isolated tests of individual functions/classes
- **Characteristics:** No I/O, mocked dependencies, deterministic
- **Location:** Throughout `tests/` directory
- **Example:** Testing interpreter parsing logic with in-memory strings

### Contract Tests
- **Purpose:** Validate API endpoint shapes and response structures
- **Location:** `tests/contracts/`
- **Focus:** JSON structure, HTTP status codes, required fields
- **Examples:**
  - `/api/providers` returns list with `id` + `display_name`
  - `/api/scan` returns dict with `id`
  - `/api/scans/<id>/status` returns dict with `status`/`state`/`done`
- **Why:** Catch breaking changes to API contracts early
- **Run:** `python -m pytest tests/contracts/test_api_contracts.py -q`

### Integration Tests
- **Purpose:** Test feature interactions with mocked external services
- **Characteristics:** Use monkeypatch at process/module boundaries
- **Examples:**
  - rclone provider with mocked subprocess
  - Neo4j commit with fake driver
  - SQLite batch operations with temp databases
- **Markers:** `@pytest.mark.integration` (when needed)

### E2E Tests
- **Purpose:** Full user workflows through the browser
- **Locations:**
  - TypeScript Playwright: `e2e/*.spec.ts` (preferred for UI flows)
  - Python pytest-playwright: `tests/e2e/` (alternative for same scenarios)
- **Focus:** User-visible outcomes, navigation flows, data persistence across pages
- **Examples:** scan a folder → browse results → verify file details appear
- **Markers:** `@pytest.mark.e2e`
- **Run:**
  - TypeScript: `npm run e2e`
  - Python: `SCIDK_E2E=1 python -m pytest -m e2e -q`

### Smoke Tests
- **Purpose:** Minimal health checks to catch catastrophic failures quickly
- **Characteristics:**
  - Page loads without errors
  - Critical elements present
  - No console errors
- **Location:** `e2e/smoke.spec.ts`, `tests/e2e/test_*`
- **CI:** Run on every PR to gate merges

## Test Markers (pytest -m)

- `@pytest.mark.e2e`: End-to-end tests requiring a running Flask app (skipped unless `SCIDK_E2E=1` or CI)
- `@pytest.mark.integration`: Tests that require environment setup or mocked external services
- No marker (default): Fast unit/API tests that run in every CI job

## Quickstart Examples

### API Contracts (Phase 00)
```bash
# Run all contract tests
python -m pytest tests/contracts/test_api_contracts.py -q

# Run specific contract
python -m pytest tests/contracts/test_api_contracts.py::test_providers_contract -q
```

### Playwright E2E Smoke (Phase 02)
Requires Node.js. Install Playwright deps once:
```bash
npm install
npm run e2e:install
```

Run smoke locally:
```bash
npm run e2e          # headless
npm run e2e:headed   # with browser window
```

The Playwright config uses `e2e/global-setup.ts` to spawn the Flask server and exports BASE_URL. See `e2e/smoke.spec.ts` for the first spec.

## Dev CLI Flows

Inspect Ready Queue ordering (E2E tasks are top via RICE=999 and DoR):
```bash
python -m dev.cli ready-queue
```

Validate Definition of Ready for a task:
```bash
python -m dev.cli validate task:e2e:02-playwright-scaffold
```

Print the context for prompting/PR:
```bash
python -m dev.cli context task:e2e:02-playwright-scaffold
```

Start the task (creates branch if in git, updates status to In Progress):
```bash
python -m dev.cli start task:e2e:02-playwright-scaffold
```

## Test Layout and Conventions

- **Location:** `tests/`
- **Shared fixtures:** `tests/conftest.py`
  - `app()` → Flask app with TESTING=True, created via `scidk.app.create_app`
  - `client(app)` → Flask test client
  - `sample_py_file`/tmp files → helper fixtures for interpreter tests
- **Style:** Each test file focuses on a feature area (API endpoints, providers, interpreters, scan/index, graph/neo4j, tasks, UI smoke)
- **Naming:** `test_*.py`, functions starting with `test_*`

## External Dependency Strategy (Mock-First)

Many features integrate with tools/services such as rclone and Neo4j. The test suite isolates these by mocking at process or module boundaries:

### rclone
- Enable provider via env: `SCIDK_PROVIDERS=local_fs,mounted_fs,rclone`
- Pretend binary exists: monkeypatch `shutil.which('rclone')` to a fake path
- Simulate commands: monkeypatch `subprocess.run` to return canned outputs for:
  - `rclone version`
  - `rclone listremotes`
  - `rclone lsjson <target> [--max-depth N | --recursive]`
- Tests verify API behavior (providers list, roots, browse) and error messages when rclone is "not installed". No real rclone needed.
- **Helper:** `tests/helpers/rclone.py` provides `rclone_env()` fixture

### Neo4j
- Fake driver module by injecting a stub into `sys.modules['neo4j']` with `GraphDatabase.driver` → fake driver/session
- Session.run records Cypher and returns synthetic rows for verification queries
- Tests assert that commit flow fires expected Cypher and that post-commit verification reports counts/flags
- Tests can set env like `NEO4J_URI`, `NEO4J_AUTH=none` for the app to attempt a Neo4j path without requiring the real driver
- **Helper:** `tests/helpers/neo4j.py` provides `inject_fake_neo4j()` and `CypherRecorder`

### SQLite and Filesystem
- Uses `tmp_path` for isolated file trees
- Batch inserts and migrations exercised against ephemeral databases; WAL mode is default in app config
- **Helper:** `tests/helpers/builders.py` provides file structure builders

## What the Tests Cover

- **API surface:** `/api/providers`, `/api/provider_roots`, `/api/browse`, `/api/scan`, `/api/scans/<id>/status|fs|commit`, `/api/graph/*`, files/folders/instances exports, health/metrics
- **Providers:** local_fs, mounted_fs, rclone (mocked subprocess), rclone scan ingest and recursive hierarchy
- **Interpreters:** Python, CSV, IPYNB basic parsing and UI rendering
- **Graph:** in-memory schema endpoints; optional Neo4j schema and commit verification (mocked driver)
- **Tasks:** background task queue limits, cancel, status
- **UI smoke:** basic route existence for map/interpreters pages

## Environment Variables in Tests

- `SCIDK_PROVIDERS`: Feature-flag providers set (e.g., `local_fs,mounted_fs,rclone`)
- `NEO4J_URI` / `NEO4J_USER` / `NEO4J_PASSWORD` / `NEO4J_AUTH`: Used to steer code paths; tests often set `NEO4J_AUTH=none` with a fake neo4j module
- `SCIDK_RCLONE_MOUNTS` or `SCIDK_FEATURE_RCLONE_MOUNTS`: Enables rclone mount manager endpoints (tests mock subprocess)
- `SCIDK_E2E`: Set to `1` to enable E2E tests in local runs (automatically set in CI)

## Running Subsets and Debugging

Run a single file:
```bash
python3 -m pytest tests/test_rclone_provider.py -q
```

Run a specific test:
```bash
python3 -m pytest tests/test_neo4j_commit.py::test_standard_scan_and_commit_with_mock_neo4j -q
```

Increase verbosity:
```bash
python3 -m pytest tests/test_rclone_provider.py -vv
```

Run only contract tests:
```bash
python3 -m pytest tests/contracts/ -q
```

Skip E2E tests:
```bash
python3 -m pytest -m "not e2e" -q
```

## UI Selectors for E2E

Stable hooks are provided via `data-testid` attributes on key elements:
- Header/nav/main in `scidk/ui/templates/base.html`:
  - `data-testid="header"` - Main header element
  - `data-testid="nav"` - Navigation container
  - `data-testid="nav-home"` - Home/Settings link (landing page)
  - `data-testid="nav-files"` - Files link
  - `data-testid="nav-maps"` - Maps link
  - `data-testid="nav-chats"` - Chats link
  - `data-testid="nav-settings"` - Settings link
  - `data-testid="main"` - Main content area
- Settings page (landing page) in `scidk/ui/templates/index.html`:
  - Settings sections with various configuration options
- Files page in `scidk/ui/templates/datasets.html`:
  - `data-testid="files-root"` - Root container
  - `data-testid="files-title"` - Page title

**Best practice:** In Playwright, prefer `page.getByTestId('nav-files')` over brittle CSS paths.

## CI Configuration (Phase 05)

A GitHub Actions workflow is provided at `.github/workflows/ci.yml`

### Jobs

**Python tests (pytest):**
- Sets up Python 3.12
- Installs deps (`requirements.txt` / `pyproject.toml`)
- Runs `python -m pytest -q -m "not e2e"`
- Fast feedback on API/unit/contract tests

**E2E smoke (Playwright):**
- Sets up Python 3.12 (for Flask app)
- Sets up Node 18
- Installs deps and Playwright browsers (`npx playwright install --with-deps`)
- Runs `npm run e2e`
- Environment: `SCIDK_PROVIDERS=local_fs` to avoid external dependencies
- Strict (no continue-on-error) now that smoke and core flows are stable

### Running Locally (CI-equivalent)

```bash
# Python tests
python -m pytest -q -m "not e2e"

# E2E tests
npm install
npx playwright install --with-deps
npm run e2e
```

## Notes and Tips

- The test suite avoids network or real external binaries by default. If you wish to run against real services, do so manually in an isolated environment; this is outside normal CI/local flows.
- Cached artifacts under `pytest-of-patch/` are output from past runs and are not part of the active suite.
- If your shell lacks a pytest command, always prefer `python3 -m pytest`.

## Maintenance Guidelines

- When adding new features, create tests in `tests/` alongside related areas and reuse existing fixtures/mocking patterns
- Prefer monkeypatch at the highest useful boundary (subprocess/module) rather than deep internals to keep tests robust
- Keep tests deterministic and independent; rely on `tmp_path` and in-memory/synthetic data
- Add `data-testid` attributes to new UI elements that will be tested in E2E specs
- Update contract tests when API response shapes change
- Keep E2E specs focused on user-visible outcomes, not implementation details

## Recent Updates

### Phase 03 (Core Flows)
New API contracts added under `tests/contracts/test_api_contracts.py`:
- `test_scan_contract_local_fs`: POST `/api/scan` returns a payload with an `id` or `ok`
- `test_scan_status_contract`: GET `/api/scans/<id>/status` returns a dict with a `status`/`state`/`done` field
- `test_directories_contract`: GET `/api/directories` returns a list with items containing `path`

New Playwright specs:
- `e2e/browse.spec.ts`: navigates to Files and verifies stable hooks, no console errors
- `e2e/scan.spec.ts`: posts `/api/scan` for a temp directory and verifies scan completion

### How to Run New Tests

Contracts subset:
```bash
python -m pytest tests/contracts/test_api_contracts.py::test_scan_contract_local_fs -q
python -m pytest tests/contracts/test_api_contracts.py::test_scan_status_contract -q
python -m pytest tests/contracts/test_api_contracts.py::test_directories_contract -q
```

E2E specs:
```bash
npm run e2e          # runs all specs including smoke, browse, scan
npm run e2e:headed   # optional, debug mode
```

**Note:** E2E relies on BASE_URL from global-setup (spawns Flask). `SCIDK_PROVIDERS` defaults to `local_fs` in CI. The scan E2E uses a real temp directory under the runner OS temp path and triggers a synchronous scan via `/api/scan`.

## E2E Testing Complete Guide

### Quick Start

1. **Install dependencies** (one-time setup):
   ```bash
   npm install
   npm run e2e:install  # Installs Playwright browsers
   ```

2. **Run all E2E tests**:
   ```bash
   npm run e2e          # Headless (recommended for CI/local verification)
   npm run e2e:headed   # With visible browser (useful for debugging)
   ```

3. **Run specific test files**:
   ```bash
   npm run e2e -- e2e/smoke.spec.ts
   npm run e2e -- e2e/core-flows.spec.ts
   npm run e2e -- e2e/negative.spec.ts
   ```

### Available Test Suites

- **`e2e/smoke.spec.ts`**: Basic page load and navigation smoke tests
- **`e2e/core-flows.spec.ts`**: Full user workflows (scan → browse → details)
- **`e2e/scan.spec.ts`**: Directory scanning functionality
- **`e2e/browse.spec.ts`**: File browsing and navigation
- **`e2e/negative.spec.ts`**: Error handling, empty states, edge cases

### CI Integration

E2E tests run automatically in GitHub Actions on every push and PR. See `.github/workflows/ci.yml`:

- **Job: `e2e`**: Runs Playwright tests with `SCIDK_PROVIDERS=local_fs`
- **On failure**: Uploads Playwright report and traces as artifacts
- **Access artifacts**: Go to Actions → failed run → download `playwright-report`

To view traces locally:
```bash
npx playwright show-trace test-results/<test-name>/trace.zip
```

## Troubleshooting

### E2E Tests

**Problem: `spawn python ENOENT` or Python not found**
- **Cause**: Playwright global-setup can't find Python executable
- **Fix**: The `e2e/global-setup.ts` uses `python3` on Linux/Mac, `python` on Windows
- **Verify**: `which python3` (Linux/Mac) or `where python` (Windows)

**Problem: Tests fail with "element not found" or timeouts**
- **Cause**: Page load too slow, or elements missing `data-testid` attributes
- **Fix 1**: Check Flask server logs in test output for errors
- **Fix 2**: Run with headed mode to see what's happening: `npm run e2e:headed`
- **Fix 3**: Verify `data-testid` attributes exist in templates (`scidk/ui/templates/`)

**Problem: "Port already in use" error**
- **Cause**: Previous Flask server didn't shut down cleanly
- **Fix**: Kill stale processes: `pkill -f "python.*scidk.app"` or `lsof -ti:5000 | xargs kill`

**Problem: Tests pass locally but fail in CI**
- **Cause**: Different providers enabled, or timing differences
- **Check**: CI uses `SCIDK_PROVIDERS=local_fs` only (see `.github/workflows/ci.yml`)
- **Fix**: Run locally with same env: `SCIDK_PROVIDERS=local_fs npm run e2e`

### pytest Tests

**Problem: `ModuleNotFoundError` for scidk package**
- **Cause**: Package not installed in editable mode
- **Fix**: `pip install -e .[dev]`

**Problem: Tests fail with "No such file or directory" for temp files**
- **Cause**: Tests didn't clean up properly, or timing issue with `tmp_path`
- **Fix**: Use pytest's `tmp_path` fixture, which auto-cleans after each test

**Problem: "RuntimeError: Working outside of application context"**
- **Cause**: Flask test missing `app` or `client` fixture
- **Fix**: Add `def test_something(client):` to use Flask test client

**Problem: Neo4j or rclone tests fail**
- **Cause**: Missing mocks/fakes for external dependencies
- **Fix**: Use helpers from `tests/helpers/`:
  - `from tests.helpers.neo4j import inject_fake_neo4j`
  - `from tests.helpers.rclone import rclone_env`

**Problem: Slow tests or database locks**
- **Cause**: SQLite WAL mode or concurrent access
- **Fix**: Use `tmp_path` for isolated test databases, avoid shared state between tests

### General Tips

- **Run tests verbosely**: `python -m pytest -v` or `npm run e2e -- --debug`
- **Run single test**: `python -m pytest tests/test_foo.py::test_bar -v`
- **Skip slow tests**: `python -m pytest -m "not e2e" -q`
- **Clear pytest cache**: `rm -rf .pytest_cache`
- **Check logs**: E2E server logs appear inline with test output
- **Update snapshots**: If visual regression tests exist, use `npm run e2e -- --update-snapshots`
