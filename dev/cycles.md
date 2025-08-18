# SciDK Delivery Cycles & Stories

## Cycle Protocol
- Cadence: Weekly sprints (Mon–Fri).
- Ceremony:
  1) Plan: Select tasks (P0/P1) to in-progress. Update owners/ETAs.
  2) Execute: Coding agent works tasks; update Progress Log in each task file.
  3) Review: PR/CI green + DoD validated; move to review/done.
  4) Learn: Retrospective notes; update risks and templates.
- Principle: GUI-first. Each cycle must end with a runnable GUI demonstrating current capabilities (even if minimal).

## Story Structure
- story:<id>
  - Title: <narrative aligned to UX/value>
  - Scope: [task:... across one or more visions/phases]
  - Success Criteria: <measurable outcome>
  - Timeline: <dates>
  - Updates: diary of progress

## Current Cycle (2025-08-19 → 2025-08-23)
- Goals: End-to-end scan → dataset → interpret(.py) → list in UI.
- GUI Acceptance: 
  - A simple web UI starts locally and shows datasets and at least one interpretation field.
- Stories:
  - [story:setup-e2e] MVP end-to-end spike
    - Scope: [task:core-architecture/mvp/graph-inmemory], [task:core-architecture/mvp/filesystem-scan], [task:interpreters/mvp/registry-and-executor], [task:core-architecture/mvp/rest-ui]
    - Success: User sees interpreted imports for a Python file in UI.
    - Timeline: 2025-08-19 → 2025-08-23
    - Updates:
      - 2025-08-18: Scaffolded Flask app factory with UI routes (/ , /datasets, /datasets/<id>) and API (/api/scan, /api/datasets, /api/datasets/<id>). Basic templates created (index.html, datasets.html, dataset_detail.html).
      - 2025-08-18: Implemented InMemoryGraph with dataset upsert and interpretation caching. Implemented FilesystemManager.scan_directory and dataset creation with checksum.
      - 2025-08-18: Added PythonCodeInterpreter and wired via simple extension-based InterpreterRegistry (.py → python_code). UI shows interpretation keys and dataset detail renders interpretation JSON.
      - 2025-08-18: Added POST /api/interpret with dataset_id and optional interpreter_id; extended InterpreterRegistry with get_by_id and select_for_dataset. Added stubs for SecureInterpreterExecutor and PatternMatcher/RuleEngine to host future logic.
      - 2025-08-18: Added a shared base layout with top navigation (Home, Files, Plugins, Extensions, Settings). Implemented UI routes (/plugins, /extensions, /settings) with placeholder pages; refactored templates to extend base.
      - 2025-08-18: Verified GUI Acceptance — local UI starts, scanning populates datasets, dataset detail renders interpretation JSON for .py files; API endpoints (/api/scan, /api/datasets, /api/datasets/<id>, /api/interpret) respond as expected.
      - 2025-08-18: Added pytest test suite (unit + API), configured pyproject for pytest, and documented testing workflow in README.
      - 2025-08-18: Added requirements.txt and requirements-dev.txt; updated README to include installation via requirements and confirm pytest install path.
      - 2025-08-18: Removed requirements-dev.txt; unified requirements so dev == release (pytest included) and updated README accordingly.
      - 2025-08-18: Enhanced landing page with: saved scan/dataset summary (counts and by extension), Graph Schema Summary placeholder, Workbook Viewer (XLSX) placeholder, and Chat UI placeholder; updated index route to compute lightweight summaries.
      - 2025-08-18: Added minimal telemetry/logging for scan: API and UI scan now record path, recursive flag, files scanned, duration seconds, and timestamps; surfaced on Home page under "Last Scan Telemetry"; tests remain green.
    - Status by Task:
      - [task:core-architecture/mvp/graph-inmemory]: Done (MVP in-memory adapter in scidk/core/graph.py).
      - [task:core-architecture/mvp/filesystem-scan]: Done (scan + dataset node + checksum idempotency).
      - [task:core-architecture/mvp/rest-ui]: Done (routes + templates + nav scaffold).
      - [task:interpreters/mvp/registry-and-executor]: In-progress (basic registry by extension + POST /api/interpret done; pattern rules + secure executor hardening pending).

- Next Up (prioritized):
  1) Extend InterpreterRegistry with pattern rules and precedence; integrate simple PatternMatcher/RuleEngine into selection flow.
  2) [Done this cycle] Minimal telemetry/logging for scan duration and counts; surfaced on UI Home as "Last Scan Telemetry".
  3) Implement XLSX Workbook Viewer page: read .xlsx via openpyxl, render sheet tabs and table preview; link from dataset detail when extension==.xlsx.
  4) Add Chat backend stub: POST /api/chat that echoes or routes to a future LLM; store conversation in-memory per session.
  5) Graph Schema Summary improvements: compute simple relationship stubs and show counts; prepare for Neo4j adapter.
  6) Flesh out Plugins/Extensions/Settings pages (content + active nav states) and wire to real data where applicable.

- Retro Notes:
  - What went well: GUI-first approach clarified integration points; end-to-end flow verified quickly.
  - What to improve: Add lightweight tests for checksum idempotency and interpreter error handling next cycle.

## Agent Prompts Cheat Sheet
Use these prompts to accelerate dev cycles.

- Planning
  - "List all tasks in phase:core-architecture/mvp and mark dependencies; set status in-progress for P0 tasks."
  - "Create a new task spec for implementing a minimal Flask UI scaffold with two pages (list, detail)."
- Execution
  - "Implement code per task:core-architecture/mvp/rest-ui; add routes / and /datasets; render minimal templates."
  - "Run integration tests for scan → datasets; report failures and update task Progress Log."
- Graph & Deployment
  - "Start Neo4j via docker-compose.neo4j.yml, verify APOC and n10s availability, and document commands in dev/deployment.md."
- Interpreters
  - "Add a PythonCodeInterpreter per spec, wire into registry, and demonstrate one interpretation result in UI."
- Testing
  - "Run tests with: pytest"
  - "Add/extend unit tests in tests/ for each change; use fixtures from tests/conftest.py."
- Review
  - "Validate DoD for task:<id>; move status to review and summarize changes."
- Retro
  - "Append one learning to dev/cycles.md Retro notes; propose one improvement to templates."

## Backlog Grooming
- Add new tasks from discoveries; ensure each has Goal, DoD, Owner.
