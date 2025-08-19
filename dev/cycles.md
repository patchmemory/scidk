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
      - 2025-08-18: Switched filesystem enumeration to prefer NCDU when available (with Python fallback); updated docs accordingly.
      - 2025-08-18: Implemented rule-based interpreter selection: PatternMatcher glob support and RuleEngine precedence integrated into InterpreterRegistry; registered default rule for *.py → python_code; all tests green.
      - 2025-08-18: Implemented XLSX Workbook Viewer using openpyxl with route /workbook/<dataset_id>, a new workbook.html template rendering sheet list and a 20x20 preview; added link from dataset detail for .xlsx/.xlsm.
      - 2025-08-18: Added Chat backend stub: POST /api/chat echoing messages and storing in-memory history on app; to be wired to UI in a future iteration.
      - 2025-08-18: Implemented rule-based selection: PatternMatcher glob support and RuleEngine precedence integrated into InterpreterRegistry; registered default rule for *.py → python_code; all tests green.
      - 2025-08-18: Graph Schema Summary improvements: added InMemoryGraph.schema_summary() with INTERPRETED_AS relation counts; index page now renders relations.
      - 2025-08-18: Extensions/Plugins/Settings pages now show real data: registry mappings, rules, interpreter counts, env info.
      - 2025-08-18: Finalized interpreter MVP scope; verified SecureInterpreterExecutor timeout behavior and empty env for bash; all tests green.
    - Status by Task:
      - [task:core-architecture/mvp/graph-inmemory]: Done (MVP in-memory adapter in scidk/core/graph.py).
      - [task:core-architecture/mvp/filesystem-scan]: Done (scan + dataset node + checksum idempotency).
      - [task:core-architecture/mvp/rest-ui]: Done (routes + templates + nav scaffold).
      - [task:interpreters/mvp/registry-and-executor]: Done (registry + rules + MVP executor with timeouts; further hardening and additional runtimes deferred).

- Next Up (prioritized):
  1) [task:core-architecture/mvp/tests-hardening] Add tests: checksum idempotency (no duplicate datasets across rescans) and interpreter error handling (timeout and syntax error paths). Status: in-progress
  2) Add basic Chat UI on Home page: simple input + conversation history using /api/chat. Status: planned
  3) Improve dataset_detail rendering: human-friendly interpretation sections and error states. Status: planned
  4) Prepare for Neo4j adapter: define Graph interface boundary and document migration steps in dev/deployment.md. Status: planned
  5) Add CSV interpreter stub (list headers, row count) and map to .csv via registry. Status: planned

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

---

## Next Cycle (2025-08-26 → 2025-08-30)
- Theme: Quality hardening, UX polish, and groundwork for Neo4j.
- Goals:
  - Raise baseline quality via tests for idempotency and interpreter error paths.
  - Deliver visible UX improvements: Chat UI (hooked to stub), clearer dataset detail.
  - Expand interpreter coverage with CSV insights (headers, row counts).
  - Define Graph interface boundary and migration steps toward Neo4j adapter.
- GUI Acceptance:
  - Home page includes a basic Chat UI wired to /api/chat, showing conversation history.
  - Dataset detail page renders human-friendly interpretation sections with error states.
- Stories:
  - [story:quality-and-ux] Quality + UX slice
    - Scope: [task:core-architecture/mvp/tests-hardening], [task:ui/mvp/chat-ui], [task:ui/mvp/dataset-detail-ux]
    - Success: Tests pass reliably; Chat UI works; dataset detail is readable and shows errors gracefully.
    - Timeline: 2025-08-26 → 2025-08-30
    - Updates:
      - 2025-08-18: Drafted tasks for Chat UI and Dataset Detail UX, linked to cycles; aligned scope with MVP.
  - [story:csv-expansion] CSV Interpreter MVP
    - Scope: [task:interpreters/mvp/csv-interpreter]
    - Success: For .csv datasets, interpreter extracts delimiter, headers (first row), and row count; visible in UI.
    - Timeline: 2025-08-26 → 2025-08-30
    - Updates:
      - 2025-08-18: Drafted CSV interpreter task; planned registry mapping *.csv → csv interpreter.
  - [story:neo4j-prep] Graph Interface & Migration
    - Scope: [task:core-architecture/mvp/neo4j-adapter-prep]
    - Success: Documented Graph interface boundary, adapter shim outline, and migration steps in dev/deployment.md; no runtime switch yet.
    - Timeline: 2025-08-26 → 2025-08-28
    - Updates:
      - 2025-08-18: Drafted migration prep task; identified API surface in scidk/core/graph.py.
- Risks:
  - Scope creep on UI polish; keep to MVP increments.
  - CSV parsing variability; constrain to utf-8 and simple delimiter detection for MVP.
- Exit Criteria:
  - New tests added and passing; Chat UI and dataset detail improvements visible; CSV interpreter integrated; migration doc updated.
