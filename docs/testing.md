SciDK testing overview

This repository uses pytest for unit, API, and integration-like tests that are hermetic by default (no external services required). The goal is fast feedback with realistic behavior via controlled monkeypatching.

How to run
- Preferred: python3 -m pytest -q
- Virtualenv: If you use .venv, activate it first; pytest is in requirements.txt and [project] dependencies.
- Dev CLI: python3 -m dev.cli test (calls pytest with sensible fallbacks). Some subcommands also run tests as part of DoD checks.
- Pytest config: Defined in pyproject.toml
  - testpaths = ["tests"]
  - addopts = "-q"

Quickstart: API contracts (phase 00)
- Minimal contracts live under tests/contracts/.
- Example: tests/contracts/test_api_contracts.py::test_providers_contract
  - Run: python -m pytest tests/contracts/test_api_contracts.py -q

Quickstart: Playwright E2E smoke (phase 02)
- Requires Node.js. Install Playwright deps once:
  - npm install
  - npm run e2e:install
- Run smoke locally:
  - npm run e2e
- The Playwright config uses e2e/global-setup.ts to spawn the Flask server and exports BASE_URL. See e2e/smoke.spec.ts for the first spec.

Dev CLI flows (validate/context/start)
- Inspect Ready Queue ordering (E2E tasks are top via RICE=999 and DoR):
  - python -m dev.cli ready-queue
- Validate Definition of Ready for a task:
  - python -m dev.cli validate task:e2e:02-playwright-scaffold
- Print the context for prompting/PR:
  - python -m dev.cli context task:e2e:02-playwright-scaffold
- Start the task (creates branch if in git, updates status to In Progress with a timezone-aware ISO8601 timestamp):
  - python -m dev.cli start task:e2e:02-playwright-scaffold

Test layout and conventions
- Location: tests/
- Shared fixtures: tests/conftest.py
  - app() -> Flask app with TESTING=True, created via scidk.app.create_app
  - client(app) -> Flask test client
  - sample_py_file/tmp files -> helper fixtures for interpreter tests
- Style: Each test file focuses on a feature area (API endpoints, providers, interpreters, scan/index, graph/neo4j, tasks, UI smoke).
- Naming: test_*.py, functions starting with test_*.

External dependency strategy (mock-first)
Many features integrate with tools/services such as rclone and Neo4j. The test suite isolates these by mocking at process or module boundaries:
- rclone
  - Enable provider via env: SCIDK_PROVIDERS=local_fs,mounted_fs,rclone
  - Pretend binary exists: monkeypatch shutil.which('rclone') to a fake path
  - Simulate commands: monkeypatch subprocess.run to return canned outputs for
    - rclone version
    - rclone listremotes
    - rclone lsjson <target> [--max-depth N | --recursive]
  - Tests verify API behavior (providers list, roots, browse) and error messages when rclone is “not installed”. No real rclone needed.
- Neo4j
  - Fake driver module by injecting a stub into sys.modules['neo4j'] with GraphDatabase.driver → fake driver/session
  - Session.run records Cypher and returns synthetic rows for verification queries
  - Tests assert that commit flow fires expected Cypher and that post-commit verification reports counts/flags
  - Tests can set env like NEO4J_URI, NEO4J_AUTH=none for the app to attempt a Neo4j path without requiring the real driver
- SQLite and filesystem
  - Uses tmp_path for isolated file trees
  - Batch inserts and migrations exercised against ephemeral databases; WAL mode is default in app config

What the tests cover (representative)
- API surface: /api/providers, /api/provider_roots, /api/browse, /api/scan, /api/scans/<id>/status|fs|commit, /api/graph/*, files/folders/instances exports, health/metrics
- Providers: local_fs, mounted_fs, rclone (mocked subprocess), rclone scan ingest and recursive hierarchy
- Interpreters: Python, CSV, IPYNB basic parsing and UI rendering
- Graph: in-memory schema endpoints; optional Neo4j schema and commit verification (mocked driver)
- Tasks: background task queue limits, cancel, status
- UI smoke: basic route existence for map/interpreters pages

Environment variables commonly used in tests
- SCIDK_PROVIDERS: Feature-flag providers set (e.g., local_fs,mounted_fs,rclone)
- NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD / NEO4J_AUTH: Used to steer code paths; tests often set NEO4J_AUTH=none with a fake neo4j module
- SCIDK_RCLONE_MOUNTS or SCIDK_FEATURE_RCLONE_MOUNTS: Enables rclone mount manager endpoints (tests mock subprocess)

Running subsets and debugging
- Run a single file: python3 -m pytest tests/test_rclone_provider.py -q
- Run a test node: python3 -m pytest tests/test_neo4j_commit.py::test_standard_scan_and_commit_with_mock_neo4j -q
- Increase verbosity temporarily: add -vv; drop -q if needed

Notes and tips
- The test suite avoids network or real external binaries by default. If you wish to run against real services, do so manually in an isolated environment; this is outside normal CI/local flows.
- Cached artifacts under pytest-of-patch/ are output from past runs and are not part of the active suite.
- If your shell lacks a pytest command, always prefer python3 -m pytest.

Maintenance guidelines
- When adding new features, create tests in tests/ alongside related areas and reuse existing fixtures/mocking patterns
- Prefer monkeypatch at the highest useful boundary (subprocess/module) rather than deep internals to keep tests robust
- Keep tests deterministic and independent; rely on tmp_path and in-memory/synthetic data

UI selectors for E2E
- Stable hooks are provided via data-testid attributes on key elements:
  - Header/nav/main in scidk/ui/templates/base.html (e.g., [data-testid="nav-files"]).
  - Home page recent scans section in scidk/ui/templates/index.html (data-testid="home-recent-scans").
  - Files page root container and title in scidk/ui/templates/datasets.html (data-testid="files-root", "files-title").
- In Playwright, prefer page.getByTestId('nav-files') etc. over brittle CSS paths.

SciDK testing overview

This repository uses pytest for unit, API, and integration-like tests that are hermetic by default (no external services required). The goal is fast feedback with realistic behavior via controlled monkeypatching.

How to run
- Preferred: python3 -m pytest -q
- Virtualenv: If you use .venv, activate it first; pytest is in requirements.txt and [project] dependencies.
- Dev CLI: python3 -m dev.cli test (calls pytest with sensible fallbacks). Some subcommands also run tests as part of DoD checks.
- Pytest config: Defined in pyproject.toml
  - testpaths = ["tests"]
  - addopts = "-q"

Quickstart: API contracts (phase 00)
- Minimal contracts live under tests/contracts/.
- Example: tests/contracts/test_api_contracts.py::test_providers_contract
  - Run: python -m pytest tests/contracts/test_api_contracts.py -q

Quickstart: Playwright E2E smoke (phase 02)
- Requires Node.js. Install Playwright deps once:
  - npm install
  - npm run e2e:install
- Run smoke locally:
  - npm run e2e
- The Playwright config uses e2e/global-setup.ts to spawn the Flask server and exports BASE_URL. See e2e/smoke.spec.ts for the first spec.

Dev CLI flows (validate/context/start)
- Inspect Ready Queue ordering (E2E tasks are top via RICE=999 and DoR):
  - python -m dev.cli ready-queue
- Validate Definition of Ready for a task:
  - python -m dev.cli validate task:e2e:02-playwright-scaffold
- Print the context for prompting/PR:
  - python -m dev.cli context task:e2e:02-playwright-scaffold
- Start the task (creates branch if in git, updates status to In Progress with a timezone-aware ISO8601 timestamp):
  - python -m dev.cli start task:e2e:02-playwright-scaffold

Test layout and conventions
- Location: tests/
- Shared fixtures: tests/conftest.py
  - app() -> Flask app with TESTING=True, created via scidk.app.create_app
  - client(app) -> Flask test client
  - sample_py_file/tmp files -> helper fixtures for interpreter tests
- Style: Each test file focuses on a feature area (API endpoints, providers, interpreters, scan/index, graph/neo4j, tasks, UI smoke).
- Naming: test_*.py, functions starting with test_*.

External dependency strategy (mock-first)
Many features integrate with tools/services such as rclone and Neo4j. The test suite isolates these by mocking at process or module boundaries:
- rclone
  - Enable provider via env: SCIDK_PROVIDERS=local_fs,mounted_fs,rclone
  - Pretend binary exists: monkeypatch shutil.which('rclone') to a fake path
  - Simulate commands: monkeypatch subprocess.run to return canned outputs for
    - rclone version
    - rclone listremotes
    - rclone lsjson <target> [--max-depth N | --recursive]
  - Tests verify API behavior (providers list, roots, browse) and error messages when rclone is “not installed”. No real rclone needed.
- Neo4j
  - Fake driver module by injecting a stub into sys.modules['neo4j'] with GraphDatabase.driver → fake driver/session
  - Session.run records Cypher and returns synthetic rows for verification queries
  - Tests assert that commit flow fires expected Cypher and that post-commit verification reports counts/flags
  - Tests can set env like NEO4J_URI, NEO4J_AUTH=none for the app to attempt a Neo4j path without requiring the real driver
- SQLite and filesystem
  - Uses tmp_path for isolated file trees
  - Batch inserts and migrations exercised against ephemeral databases; WAL mode is default in app config

What the tests cover (representative)
- API surface: /api/providers, /api/provider_roots, /api/browse, /api/scan, /api/scans/<id>/status|fs|commit, /api/graph/*, files/folders/instances exports, health/metrics
- Providers: local_fs, mounted_fs, rclone (mocked subprocess), rclone scan ingest and recursive hierarchy
- Interpreters: Python, CSV, IPYNB basic parsing and UI rendering
- Graph: in-memory schema endpoints; optional Neo4j schema and commit verification (mocked driver)
- Tasks: background task queue limits, cancel, status
- UI smoke: basic route existence for map/interpreters pages

Environment variables commonly used in tests
- SCIDK_PROVIDERS: Feature-flag providers set (e.g., local_fs,mounted_fs,rclone)
- NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD / NEO4J_AUTH: Used to steer code paths; tests often set NEO4J_AUTH=none with a fake neo4j module
- SCIDK_RCLONE_MOUNTS or SCIDK_FEATURE_RCLONE_MOUNTS: Enables rclone mount manager endpoints (tests mock subprocess)

Running subsets and debugging
- Run a single file: python3 -m pytest tests/test_rclone_provider.py -q
- Run a test node: python3 -m pytest tests/test_neo4j_commit.py::test_standard_scan_and_commit_with_mock_neo4j -q
- Increase verbosity temporarily: add -vv; drop -q if needed

Notes and tips
- The test suite avoids network or real external binaries by default. If you wish to run against real services, do so manually in an isolated environment; this is outside normal CI/local flows.
- Cached artifacts under pytest-of-patch/ are output from past runs and are not part of the active suite.
- If your shell lacks a pytest command, always prefer python3 -m pytest.

Maintenance guidelines
- When adding new features, create tests in tests/ alongside related areas and reuse existing fixtures/mocking patterns
- Prefer monkeypatch at the highest useful boundary (subprocess/module) rather than deep internals to keep tests robust
- Keep tests deterministic and independent; rely on tmp_path and in-memory/synthetic data

UI selectors for E2E
- Stable hooks are provided via data-testid attributes on key elements:
  - Header/nav/main in scidk/ui/templates/base.html (e.g., [data-testid="nav-files"]).
  - Home page recent scans section in scidk/ui/templates/index.html (data-testid="home-recent-scans").
  - Files page root container and title in scidk/ui/templates/datasets.html (data-testid="files-root", "files-title").
- In Playwright, prefer page.getByTestId('nav-files') etc. over brittle CSS paths.

CI (phase 05)
- A GitHub Actions workflow is provided at .github/workflows/ci.yml
- Jobs:
  - Python tests (pytest): sets up Python 3.11, installs deps (requirements.txt / pyproject), runs python -m pytest -q
  - E2E smoke (Playwright): sets up Node 18, installs deps, installs browsers with npx playwright install --with-deps, runs npm run e2e
- Environment: SCIDK_PROVIDERS=local_fs is used during E2E to avoid external dependencies.
- Continue-on-error: E2E job is marked continue-on-error: true during bring-up; tighten later when stable.
- To run the same locally:
  - python -m pytest -q
  - npm install && npx playwright install --with-deps && npm run e2e
