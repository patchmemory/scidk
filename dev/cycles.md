# SciDK Delivery Cycles & Stories

## Cycle Protocol
- Cadence: Weekly sprints (Mon–Fri). GUI-first: each cycle ends with a runnable GUI demonstrating the e2e objective.
- Selection Rules
  - Maintain a short Ready Queue (8–12 items) with RICE scores; select only from Ready Queue unless a production risk forces a swap.
  - Cap at 5 tasks per cycle; all selected tasks must meet Definition of Ready (DoR).
  - One e2e objective per cycle; GUI Acceptance must demonstrate it.
- Definition of Ready (DoR)
  - Clear user outcome and GUI Acceptance written.
  - Dependencies listed and either done or timeboxed with fallbacks.
  - Test approach stated (unit/integration/skip conditions).
  - Owner + time estimate; acceptance data source (which page/API demonstrates it).
- Definition of Done (DoD)
  - Tests added/passing; docs/README updated; visible demo path; telemetry if relevant.
  - PR merged, CI green, and a screenshot/GIF or demo steps attached.
- Planning Protocol (15–20 minutes)
  1) State the e2e objective and GUI Acceptance.
  2) Pick from Ready Queue by highest RICE on the path to the e2e objective.
  3) Map a single dependency table; drop anything blocked.
  4) Select max 5 tasks that complete the e2e within capacity.
  5) Write the Demo Checklist steps.
- Execution
  - Daily: update Progress/Decision Log; if a task threatens GUI acceptance, invoke cut lines immediately and swap in a smaller alternative from Ready Queue.
- Automation (lightweight)
  - PR template includes DoR/DoD checklist and “Demo Steps.”
  - CI runs pytest and a smoke script that hits key endpoints.
  - Weekly demo tag: `mvp-week-YYYY-MM-DD`.

## Story Structure
- story:<id>
  - Title: <narrative aligned to UX/value>
  - Scope: [task:... across one or more visions/phases]
  - Success Criteria: <measurable outcome>
  - Timeline: <dates>
  - Updates: diary of progress

## Current Cycle (2025-08-18 → 2025-08-23)

### Iteration Plan (mvp-iter-2025-08-18-2306)
1) E2E Objective
   - Improve the file scanning setup so that when a directory is scanned it is saved and recallable as a "directory" entry. The Home page lists a summary of scanned root directories; the Files page hosts the directory load (scan) action and the files list. 
2) Capacity
   - 8h
3) GUI Acceptance
   - Home shows a "Scanned Directories" list with path, file count, and recursive flag; persists for the app session.
   - Files page contains the Scan form for loading directories; Home has no scan form.
   - API GET /api/directories returns a JSON list of scanned directory entries.
4) Candidates (Ready Queue excerpt with RICE)
   - task:core-architecture/mvp/search-index — RICE 4.0
   - task:ui/mvp/home-search-ui — RICE 3.6
   - task:core-architecture/mvp/neo4j-adapter-prep — RICE 3.2
   - task:core-architecture/mvp/tests-hardening — RICE 1.5
   - task:ops/mvp/error-toasts — RICE 1.2
5) Dependencies
   - None (UI updates and ephemeral storage in app memory)
6) Risks & Cut Lines
   - Cut order: Remove directories list grouping details → keep only last_scan card if constrained.

### Planning Protocol Outputs (mvp-iter-2025-08-18-2306)
- Selected Tasks Table
  - id: task:ui/mvp/home-search-ui; ETA: 2025-08-18; RICE: 3.6; dependencies: none; test approach: Flask test client to validate GET /api/directories and page rendering moves
  - id: task:core-architecture/mvp/tests-hardening; ETA: 2025-08-18; RICE: 1.5; dependencies: none; test approach: new test for /api/directories after scan
- Dependency Table
  - None
- Demo Checklist
  1) Start app (python -m scidk.app)
  2) Go to Files page (/datasets): see Scan form; scan a temp folder
  3) Go to Home (/): see Scanned Directories list showing the scanned path and counts
  4) Call /api/directories and verify JSON includes the scanned path
- Decision & Risk Log
  - 2025-08-18: Decided to store directories in an in-memory app registry keyed by path to stay within MVP scope; persistence to disk is out of scope for this iteration.
- Tag to create: mvp-iter-2025-08-18-2306

### Execution Updates (mvp-iter-2025-08-18-2306)
- Implemented per plan:
  - UI: Moved Scan form to Files page (/datasets); Home page now shows Scanned Directories list.
  - API: Added GET /api/directories returning session-scanned directories (most recent first).
  - Session storage: In-memory app.extensions['scidk']['directories'] updated on both API and UI scan flows.
- Artifacts updated:
  - Code: scidk/app.py, scidk/ui/templates/index.html, scidk/ui/templates/datasets.html
  - Docs: dev/ui/mvp/files-scan-ui-and-home-directories.md; dev/core-architecture/mvp/directories-registry-and-api.md
- GUI Acceptance: Verified manually — Home shows Scanned Directories; Files hosts the scan form; /api/directories returns expected JSON.
- Tests: Covered indirectly via existing scan APIs; targeted unit tests can be added in follow-up if needed.
- Added Test: tests/test_directories_api.py validates that scanned directories are returned by GET /api/directories.

### Retro (mvp-iter-2025-08-18-2306)
- What Worked
  - GUI-first split between Home (directories list) and Files (scan action) kept scope focused and demoable.
  - Lightweight in-memory registry for scanned directories enabled quick API/UI parity.
  - Small, targeted API test (GET /api/directories) increased confidence with minimal overhead.
- What Slowed Us
  - Early ambiguity around persistence vs. session-only storage; resolved by deferring persistence.
  - Minor rework moving scan form to Files page and updating links; some template churn.
- Scope Adjustments
  - Deferred persisted storage and advanced grouping/sorting of directories; shipped session-only list and basic fields.
  - Cut rich grouping details per pre-defined cut line; kept a simple card/list.
- Carry-overs
  - Persistence for scanned directories across restarts (disk or DB-backed registry).
  - UI polish for directories list (grouping, sorting, badges for source when external scanners in play).
  - Additional unit tests for edge cases (duplicate scans, large trees) — optional if covered elsewhere.
- Next Cycle Candidates (Updated RICE)
  - task:core-architecture/mvp/search-index — RICE 4.2
  - task:ui/mvp/home-search-ui — RICE 3.8
  - task:core-architecture/mvp/neo4j-adapter-prep — RICE 3.3
  - task:interpreters/mvp/ipynb-interpreter — RICE 3.4
  - task:ops/mvp/error-toasts — RICE 1.3

### Proposed Next Cycle (2025-08-25 → 2025-08-29)
Story: providers-mvp-multi-source-files — see dev/stories/story-mvp-multi-provider-files-and-interpreters.md
- E2E Objective
  - A user can search datasets by filename or interpreter id from the Home page; retain a documented, switchable graph boundary to prepare for Neo4j. GUI-first: demo shows search working end-to-end.
- Top 5 Tasks
  1) task:core-architecture/mvp/search-index — Implement simple in-memory index and /api/search with fields: id, path, filename, extension, interpreter_id, matched_on. Owner: agent; RICE: 4.2.
  2) task:ui/mvp/home-search-ui — Add Home search box + results list bound to /api/search; link to dataset detail. Owner: agent; RICE: 3.8.
  3) task:core-architecture/mvp/neo4j-adapter-prep — Finalize adapter boundary docs + feature flag plan; ensure current usage audit complete. Owner: agent; RICE: 3.3.
  4) task:core-architecture/mvp/tests-hardening — Add focused tests for /api/search (filename and interpreter matches, empty results) and idempotent scan behavior. Owner: agent; RICE: 1.5.
  5) task:ops/mvp/error-toasts — Minimal client-side error toasts/log clarity for API calls (search, scan). Owner: agent; RICE: 1.3.

### Iteration Plan (mvp-iter-2025-08-18-2259)
1) E2E Objective
   - Add more Interpreters and refactor "Extensions" to "Interpreters" for the page name and links; ensure legacy links still work.
2) Capacity
   - 8h
3) GUI Acceptance
   - Top navigation shows "Interpreters" linking to /interpreters; visiting /extensions redirects to /interpreters. 
   - Interpreters page lists registry mappings and rules, including new .json and .yml/.yaml entries.
   - Scanning a directory with .json and .yaml files results in interpretations visible on the dataset detail page (summary data present).
4) Candidates (Ready Queue excerpt with RICE)
   - task:interpreters/mvp/ipynb-interpreter — RICE 3.5
   - task:interpreters/mvp/json-yaml — RICE 2.8
   - task:core-architecture/mvp/tests-hardening — RICE 1.5
   - task:core-architecture/mvp/search-index — RICE 4.0 (out of scope this iteration)
   - task:ui/mvp/home-search-ui — RICE 3.6 (out of scope this iteration)
   - task:core-architecture/mvp/neo4j-adapter-prep — RICE 3.2 (out of scope this iteration)
   - task:ops/mvp/error-toasts — RICE 1.2 (cut if time-constrained)
5) Dependencies
   - None critical; json-yaml has no external deps beyond PyYAML (optional; handled gracefully).
6) Risks & Cut Lines
   - Cut order: ipynb-interpreter → tests-hardening follow-ups → any non-essential UI polish.

### Planning Protocol Outputs (mvp-iter-2025-08-18-2259)
- Selected Tasks Table
  - id: task:interpreters/mvp/json-yaml; ETA: 2025-08-18; RICE: 2.8; dependencies: none; test approach: unit tests with tiny JSON/YAML fixtures and error paths; manual GUI check on dataset detail
  - id: task:ui/mvp/rename-extensions-to-interpreters; ETA: 2025-08-18; RICE: 3.0; dependencies: none; test approach: smoke via Flask test client (GET /interpreters and redirect from /extensions)
  - id: task:core-architecture/mvp/tests-hardening; ETA: 2025-08-18; RICE: 1.5; dependencies: none; test approach: run existing tests; add small additions only if needed
- Dependency Table
  - No hard dependencies; YAML interpreter optionally depends on PyYAML. If missing, interpreter returns a safe error state and UI remains stable.
- Demo Checklist
  1) Start app (python -m scidk.app)
  2) Visit /interpreters — see mappings for .py, .csv, .json, .yml/.yaml and rules listed
  3) Visit /extensions — confirm redirect to /interpreters
  4) Prepare a folder with sample.json and sample.yaml; POST /api/scan with path
  5) Open Datasets; pick the JSON/YAML items; confirm interpretation summary appears in dataset detail (top-level keys/preview)
- Decision & Risk Log
  - 2025-08-18: Decided to implement JSON and YAML interpreters first due to lower complexity and high user value for config/data files; defer ipynb to next iteration if time-constrained.
  - 2025-08-18: Implemented legacy redirect from /extensions to /interpreters to avoid broken bookmarks.
- Tag to create: mvp-iter-2025-08-18-2259

### Execution Updates (mvp-iter-2025-08-18-2259)
- Implemented per plan:
  - Interpreters: Added JSON and YAML interpreters; registered mappings and rules; dataset detail renders summaries; graceful error paths for oversize and missing PyYAML.
  - UI: Renamed Extensions page to Interpreters; kept /extensions as a redirect to /interpreters; Interpreters page lists registry mappings and rules.
- Artifacts updated:
  - Docs: dev/interpreters/mvp/json-yaml.md; dev/ui/mvp/rename-extensions-to-interpreters.md
- GUI Acceptance: Verified manually — /interpreters shows mappings; /extensions redirects; sample JSON/YAML datasets show summaries in detail view.
- Tests: Smoke-tested via Flask client for routing; interpreter logic covered by existing patterns; YAML missing-dep path manually verified when PyYAML absent.

### Iteration Plan (mvp-iter-2025-08-18)
1) E2E Objective
   - [objective]: A fresh user can search datasets by filename or interpreter id from the Home page and click through to details.
2) Capacity
   - 8h
3) GUI Acceptance
   - Home page shows a Search input; submitting a term displays matching datasets by filename or interpreter id.
   - API GET /api/search?q=term returns a JSON list with dataset id, filename/path, extension, and matched_on fields.
4) Candidates (Ready Queue excerpt with RICE)
   - task:core-architecture/mvp/search-index — RICE 4.0
   - task:ui/mvp/home-search-ui — RICE 3.6
   - task:core-architecture/mvp/neo4j-adapter-prep — RICE 3.2
   - task:core-architecture/mvp/tests-hardening — RICE 1.5
   - task:ops/mvp/error-toasts — RICE 1.2
5) Dependencies
   - home-search-ui depends on search-index
6) Risks & Cut Lines
   - Cut order: ops/mvp/error-toasts → tests-hardening follow-ups → non-essential search snippets/highlighting.

### Planning Protocol Outputs
- Selected Tasks Table
  - id: task:core-architecture/mvp/search-index; ETA: 2025-08-18; RICE: 4.0; dependencies: none; test approach: API route unit/integration via pytest (GET /api/search and flow after POST /api/scan)
  - id: task:ui/mvp/home-search-ui; ETA: 2025-08-18; RICE: 3.6; dependencies: search-index; test approach: smoke via requests to /api/search and DOM exist checks (manual/demo)
  - id: task:core-architecture/mvp/tests-hardening; ETA: 2025-08-18; RICE: 1.5; dependencies: none; test approach: extend pytest to cover error and idempotency (kept green)
- Dependency Table
  - home-search-ui → search-index (resolved in-session)
- Demo Checklist
  1) Start app (python -m scidk.app) 2) POST /api/scan with a dir containing .py and .csv 3) On Home, search for "python_code" and a known filename 4) Click a result to open dataset detail 5) Verify /api/search returns JSON with matched_on
- Decision & Risk Log
  - 2025-08-18: Decided to implement a minimal in-memory search over current datasets instead of a separate inverted index to fit 8h capacity; acceptable for GUI MVP; will revisit indexing later.
  - 2025-08-18: Added pytest coverage for /api/search (filename and interpreter_id matches) to solidify DoD for search MVP; all tests green.
- Tag to create: mvp-iter-2025-08-18-2258
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
      - 2025-08-18: Implemented CSV Interpreter MVP with registry mapping (*.csv → csv); added unit tests and dataset detail rendering.
      - 2025-08-18: Added Chat UI widget to Home page wired to /api/chat; added API test; basic UX validated.
      - 2025-08-18: Improved Dataset Detail UX with status badges, friendly sections for python/csv, and error details.
      - 2025-08-18: Added test for rescan idempotency (no duplicate datasets); expanded test coverage for CSV interpreter and chat API.
      - 2025-08-18: Added tests for interpreter syntax errors and executor timeouts (python inline and bash); all tests green.
      - 2025-08-18: FilesystemManager now uses registry.select_for_dataset during scan to honor rule precedence; aligns scan-time interpretation with app API selection.
      - 2025-08-18: Implemented /api/search and Home page Search UI; returns datasets by filename/path and interpreter_id; added simple ordering and GUI validated.
    - Status by Task:
      - [task:core-architecture/mvp/graph-inmemory]: Done (MVP in-memory adapter in scidk/core/graph.py).
      - [task:core-architecture/mvp/filesystem-scan]: Done (scan + dataset node + checksum idempotency).
      - [task:core-architecture/mvp/rest-ui]: Done (routes + templates + nav scaffold).
      - [task:interpreters/mvp/registry-and-executor]: Done (registry + rules + MVP executor with timeouts; further hardening and additional runtimes deferred).

- Next Up (prioritized):
  1) [task:core-architecture/mvp/tests-hardening] Add tests: checksum idempotency (no duplicate datasets across rescans) and interpreter error handling (timeout and syntax error paths). Status: done (rescan idempotency, syntax error, and timeout tests added and passing)
  2) Add basic Chat UI on Home page: simple input + conversation history using /api/chat. Status: done
  3) Improve dataset_detail rendering: human-friendly interpretation sections and error states. Status: done
  4) Prepare for Neo4j adapter: define Graph interface boundary and document migration steps in dev/deployment.md. Status: planned
  5) Add CSV interpreter stub (list headers, row count) and map to .csv via registry. Status: done

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
- Theme: Basic Search (UI-visible) + Neo4j Adapter Prep
- E2E Objective: A user can search for datasets by filename or interpreter in the UI; and we have a documented, switchable graph boundary for future Neo4j.
- Capacity: 24h (single agent)
- GUI Acceptance:
  - Home page search returns datasets by filename or interpreter_id via /api/search.
  - dev/deployment.md contains a "Migration Plan" with adapter interface documented and a feature-flag plan.

- Selected Stories
  - [story:search-and-neo4j-prep] Thin slice for user-visible search and backend prep
    - Success Criteria: Search box works end-to-end; migration plan written with clear adapter boundary and env flags.
    - Timeline: 2025-08-26 → 2025-08-30
    - Tasks (max 5):
      1) task:core-architecture/mvp/search-index — Implement indexer + /api/search
         - Owner: agent; ETA: 2025-08-28; RICE: 4.0
         - Dependencies: InMemoryGraph events/hooks; tests scaffold
      2) task:ui/mvp/home-search-ui — Add Home search input + results list bound to /api/search
         - Owner: agent; ETA: 2025-08-29; RICE: 3.6
         - Dependencies: task:core-architecture/mvp/search-index
      3) task:core-architecture/mvp/neo4j-adapter-prep — Document boundary + migration plan
         - Owner: agent; ETA: 2025-08-28; RICE: 3.2
         - Dependencies: current Graph usage survey (available)
      4) task:core-architecture/mvp/tests-hardening — Follow-ups only if gaps discovered
         - Owner: agent; ETA: 2025-08-30; RICE: 1.5
         - Dependencies: none; skip if no gaps
      5) task:ops/mvp/error-toasts — Small ops polish (error toasts/log clarity) — Cut first if needed
         - Owner: agent; ETA: 2025-08-30; RICE: 1.2
         - Dependencies: none

- Dependency Table
  - home-search-ui depends on search-index; status: planned
  - neo4j-adapter-prep depends on current graph interface being identified; status: available
  - tests-hardening follow-ups depend on discovered gaps; status: conditional

- Demo Checklist
  1) Start app
  2) Run POST /api/scan on sample dir (small test data)
  3) Visit Home page; enter a term matching a dataset filename and an interpreter_id (e.g., "python_code" or "csv")
  4) Observe results list with clickable items leading to dataset detail
  5) Open dev/deployment.md and verify "Migration Plan" section with adapter interface and feature flag

- Risks & Cut Lines
  - Cut order: (5) ops polish → (4) tests follow-ups → non-essential search fields/snippets.
  - Mitigations: Keep search index minimal (filename, extension, interpreter_id) for MVP.

- Decision & Risk Log
  - 2025-08-18: Adopted RICE + Ready Queue selection protocol for weekly planning.
  - 2025-08-19: Ingested new vision docs; added tasks for NCDU/GDU Filesystem Scanner and RO-Crate MVP to Ready Queue; aligned Filesystem Scan design to prefer NCDU with GDU/Python fallback.

- Pre-Work Completed (as of 2025-08-18)
  - task:core-architecture/mvp/neo4j-adapter-prep — Completed documentation of the migration plan and adapter boundary. See dev/deployment.md ("Migration Plan: InMemoryGraph → Neo4jAdapter") and dev/core-architecture/mvp/neo4j-adapter-prep.md (Status: done).

## Cycle After Next (2025-09-01 → 2025-09-05)
- Theme: Graph backend implementation, extensibility, and interpreter expansion.
- Goals:
  - Implement Neo4jGraphAdapter behind a feature flag and validate parity with InMemoryGraph.
  - Introduce Plugin Loader MVP and a PubMed stub to prove extensibility.
  - Expand interpreter coverage to Jupyter notebooks and JSON/YAML.
  - Add a basic in-memory search index powering a simple UI search.
- GUI Acceptance:
  - Settings/Extensions shows registered plugins including PubMed Stub.
  - Home page includes a search box that returns dataset results.
  - Dataset detail shows notebook summaries (kernel, cell counts) when applicable.
- Stories:
  - [story:neo4j-adapter] Neo4j Adapter MVP
    - Scope: [task:core-architecture/mvp/neo4j-adapter-impl]
    - Success: With GRAPH_BACKEND=neo4j and Neo4j running, scan/interpret flows work and UI reflects data; fallback to inmemory on failure.
    - Timeline: 2025-09-01 → 2025-09-04
    - Updates:
      - 2025-08-18: Drafted implementation task, aligned with deployment migration plan.
  - [story:plugin-loader] Plugin Loader + PubMed Stub
    - Scope: [task:plugins/mvp/loader]
    - Success: /plugins lists PubMed Stub; /api/plugins/pubmed/search returns placeholder results.
    - Timeline: 2025-09-01 → 2025-09-03
    - Updates:
      - 2025-08-18: Drafted loader task and UI exposure plan.
  - [story:interpreter-expansion] Notebook + JSON/YAML Interpreters
    - Scope: [task:interpreters/mvp/ipynb-interpreter], [task:interpreters/mvp/json-yaml]
    - Success: .ipynb files show summary in UI; JSON/YAML show top-level summaries; size/malformed errors handled.
    - Timeline: 2025-09-02 → 2025-09-05
    - Updates:
      - 2025-08-18: Drafted interpreter tasks and DoD.
  - [story:search-mvp] Basic Search Index
    - Scope: [task:core-architecture/mvp/search-index]
    - Success: Home page search returns datasets by filename/extension/interpreter id; index updates on new scans.
    - Timeline: 2025-09-02 → 2025-09-05
    - Updates:
      - 2025-08-18: Drafted indexing task and UI plan.
- Risks:
  - Competing priorities between adapter and UI features; timebox and prioritize adapter parity first.
  - Parsing variability for notebooks and YAML; constrain to safe parsing and small summaries.
- Exit Criteria:
  - Neo4j adapter functioning behind flag; plugins visible and stub callable; new interpreters integrated; search working in UI; tests updated.


## Ready Queue (Scored, Not Scheduled This Week)
- task:core-architecture/mvp/search-index — RICE 4.0
- task:core-architecture/mvp/neo4j-adapter-prep — RICE 3.2
- task:core-architecture/mvp/neo4j-adapter-impl — RICE 3.0 (will increase after prep completes)
- task:interpreters/mvp/ipynb-interpreter — RICE 3.5
- task:interpreters/mvp/json-yaml — RICE 2.8
- task:plugins/mvp/loader (+ pubmed stub) — RICE 2.4
- task:core-architecture/mvp/filesystem-scanner-gdu-ncdu — RICE 3.9 (Vision: dev/vision/ncdu_filesystem_scanner.md; ncdu-first)
- task:core-architecture/mvp/research-objects-ro-crate — RICE 3.4 (Vision: dev/vision/research_objects.md)



---

Note: See also dev/cycle-review-2025-08-18.md for a consolidated review and next-cycle plan derived from this document.


## Proposed Immediate Cycle (2025-08-21 → 2025-08-23)
Story: ro-crate-integration-mvp — Embed Crate-O and expose minimal RO-Crate endpoints
- E2E Objective
  - From the Files page, select a folder and open it in an embedded RO-Crate viewer which loads metadata from `/api/rocrate`; small files stream via `/files` for previews/downloads.
- GUI Acceptance
  - With `SCIDK_FILES_VIEWER=rocrate`, the Files page shows an "Open in RO-Crate Viewer" button and an iframe appears, loading a wrapper that points to `/api/rocrate?...`.
  - Calling `/api/rocrate` on a temp directory returns a valid JSON-LD crate with the directory as dataset and its immediate children as entities (capped list, depth=1).
  - `/files` streams a small file and denies traversal.
- Tasks (max 5)
  1) task:ui/mvp/rocrate-embedding — Implementation guide and UI plan
     - Owner: agent; ETA: 2025-08-21
     - Artifact: dev/ui/mvp/rocrate-embedding.md (this doc) + Jinja flag placement plan
  2) task:core-architecture/mvp/rocrate-endpoints — API contracts and test plan
     - Owner: agent; ETA: 2025-08-22
     - Deliverables: API spec for `/api/rocrate` and `/files` including caps and security notes; unit test outline
  3) task:vision/describo-integration — Product vision doc for Describo
     - Owner: agent; ETA: 2025-08-21
     - Deliverable: dev/vision/describo-integration.md
  4) task:docs/link-readme — Link new docs from README and cycles
     - Owner: agent; ETA: 2025-08-21
     - Deliverable: README section pointing to RO-Crate docs
  5) task:core-architecture/mvp/rocrate-neo4j-import-plan — Outline graph import
     - Owner: agent; ETA: 2025-08-22
     - Deliverable: brief plan appended to dev/ui/mvp/rocrate-embedding.md (Future Enhancements)
- Definition of Ready (DoR)
  - Viewer choice and embed method decided (iframe for MVP). Dependencies: none external.
  - Endpoint contracts drafted with caps/security noted. Test approach stated.
- Definition of Done (DoD)
  - Docs added: rocrate-embedding.md, describo-integration.md.
  - cycles.md updated with this cycle.
  - README references added.
  - Tests to be implemented next cycle alongside endpoint code.
- Demo Checklist
  1) Start app with `SCIDK_FILES_VIEWER=rocrate` (once implemented)
  2) Navigate to Files → select a small folder → click Open in RO-Crate Viewer
  3) Observe iframe; manual call to `/api/rocrate` returns JSON-LD
  4) Call `/files` for a known file returns bytes; traversal blocked


### Iteration Plan (mvp-iter-2025-08-19-0010)
1) E2E Objective
   - Add a Jupyter Notebook interpreter (ipynb) and surface notebook summaries on the Dataset Detail page. Keep GUI-first with a simple demo path.
2) Capacity
   - 8h
3) GUI Acceptance
   - Scanning a directory with at least one .ipynb yields a dataset entry.
   - Visiting that dataset’s detail page shows a Notebook Summary with: kernel, language, cell counts by type, and first headings/imports (when available).
   - Interpreters page lists a mapping for *.ipynb → ipynb.
   - Oversized notebooks (>5MB for MVP) return a safe error state in the UI (no crash).
4) Candidates (Ready Queue excerpt with RICE)
   - task:interpreters/mvp/ipynb-interpreter — RICE 3.5
   - task:core-architecture/mvp/tests-hardening — RICE 1.5
   - task:ops/mvp/error-toasts — RICE 1.2 (cut if time-constrained)
   - task:ui/mvp/home-search-ui — RICE 3.6 (out of scope for this iteration)
5) Dependencies
   - None external (parsing is JSON-only; no notebook execution).
6) Risks & Cut Lines
   - Cut order: imports/headings extraction → keep only kernel+cell counts → keep only counts if constrained.

### Planning Protocol Outputs (mvp-iter-2025-08-19-0010)
- Selected Tasks Table
  - id: task:interpreters/mvp/ipynb-interpreter; ETA: 2025-08-19; RICE: 3.5; dependencies: none; test approach: unit tests with tiny fixture .ipynb and oversized error path
  - id: task:ui/mvp/dataset-notebook-render; ETA: 2025-08-19; RICE: 2.2; dependencies: task:interpreters/mvp/ipynb-interpreter; test approach: Flask client render smoke for notebook sections
  - id: task:core-architecture/mvp/tests-hardening; ETA: 2025-08-19; RICE: 1.5; dependencies: none; test approach: extend pytest to cover normal and error paths for ipynb
- Dependency Table
  - dataset-notebook-render → ipynb-interpreter (resolved in-session)
- Demo Checklist
  1) Start app (python -m scidk.app)
  2) Prepare a folder with sample.ipynb (small JSON notebook); POST /api/scan with that path
  3) Open Datasets; click the notebook dataset; confirm Notebook Summary (kernel, cell counts, headings/imports if present)
  4) Visit /interpreters and verify *.ipynb mapping appears
  5) Try an oversized notebook (>5MB) and confirm safe error state on detail view
- Decision & Risk Log
  - 2025-08-18: Decided to parse ipynb as JSON only (no execution) to stay safe and within capacity; cut advanced parsing if time-constrained.
- Tag to create: mvp-iter-2025-08-19-0010

### Planning Protocol (mvp-iter-2025-08-19-gdu-ncdu)
1) E2E Objective and GUI Acceptance
   - Objective: Integrate NCDU/GDU-backed filesystem scanning so that scans use external tools when available, with a GUI-first demo proving the behavior end-to-end.
   - GUI Acceptance: From the Files page, running a scan on a folder completes and Home shows a "Scanned Directories" list. When ncdu is installed, the scan path and file counts reflect ncdu output (with a small ncdu badge in the telemetry note); if ncdu is not found, gdu is used; if neither is found, the Python fallback runs. The API /api/scan and /api/directories remain stable.
2) Capacity
   - 8h
3) Selected Tasks Table with DoR (owner, ETA, RICE, dependencies, test approach)
   - id: task:core-architecture/mvp/filesystem-scanner-gdu-ncdu; owner: agent; ETA: 2025-08-19; RICE: 3.9; dependencies: ncdu or gdu binary presence (with Python fallback); test approach: unit tests for tool detection and JSON parser; integration test scanning a tmp dir when tools absent; mock subprocess for ncdu/gdu JSON paths.
   - id: task:core-architecture/mvp/tests-hardening; owner: agent; ETA: 2025-08-19; RICE: 1.5; dependencies: none; test approach: extend pytest to verify /api/scan completes and directories registry is updated; add negative path when tools error to ensure fallback engages.
4) Dependency Table
   - filesystem-scanner-gdu-ncdu → external: ncdu (preferred) or gdu; fallback: Python traversal (available)
5) Demo Checklist
   1) Start app (python -m scidk.app)
   2) On Files page (/datasets), run a scan on a small folder.
   3) If ncdu is installed, verify Home shows Scanned Directories with ncdu badge in telemetry; otherwise gdu badge if gdu is installed; otherwise generic badge (Python) appears.
   4) Call GET /api/directories to confirm the scanned path appears and includes source indicator (ncdu/gdu/python).
6) Risks & Cut Lines
   - Risks: External tool absence or JSON format drift; long scans on very large trees; permissions errors.
   - Cut lines: If badges are not ready, drop badges and keep only scan source text; if external tools fail, ship with Python fallback only and document install steps.
7) Decision & Risk Log entry
   - 2025-08-19: Decided to prefer ncdu for reliability with gdu as secondary and Python as fallback; GUI will surface which source ran to improve transparency and supportability.
8) Tag to create
   - mvp-iter-2025-08-19-gdu-ncdu

### Demo Prep (mvp-iter-2025-08-19-gdu-ncdu)
- Test Data Setup
  - Create a temporary directory with tiny files: sample.py, data.csv, sample.json. ✓
  - Script: scripts/demo-mvp-iter-2025-08-19-gdu-ncdu.sh (creates /tmp/scidk_demo_XXXX). ✓
- Single Demo Script (shell + URLs)
  - Run: ./scripts/demo-mvp-iter-2025-08-19-gdu-ncdu.sh ✓
  - Outputs: app URLs, API checkpoints, scan_id-specific URL, and detected fallback path (ncdu → gdu → python). ✓
- Fallback Paths
  - Preferred: ncdu; if not present, gdu; else python traversal. The app surfaces the chosen source via badges and API fields. ✓
- GUI Acceptance Verification (numbered steps with expected results)
  1) Start the app (script auto-starts if needed) — Expected: GET /api/datasets responds 200 []. ✓
  2) Prepare demo data (script auto-creates files) — Expected: three files present in the temp directory. ✓
  3) Trigger scan via POST /api/scan {path: <temp>, recursive: false} — Expected: 200, payload includes scan_id, scanned >= 3. ✓
  4) Home (/) — Expected: "Recent Scans" shows the scanned path with a small badge indicating source (ncdu|gdu|python); "Scanned Directories" includes the path with counts and the same badge. ✓
  5) Files (/datasets?scan_id=<id>) — Expected: page filters to newly added datasets from this scan; top helper line shows scan id/path; directories list shows source badge. ✓
  6) Telemetry (Home) — Expected: "Last Scan Telemetry" lists path, counts, duration, and Source badge. ✓
  7) API GET /api/directories — Expected: JSON array includes entry { path, scanned >= 3, recursive: false, source: <ncdu|gdu|python> }. ✓
  8) API GET /api/scans — Expected: latest item summary includes { id, path, file_count, by_ext, source }. ✓
  9) Optional: API GET /api/search?q=python_code — Expected: includes sample.py with matched_on containing interpreter_id. ✓
- URLs for the Demo
  - /, /datasets, /datasets?scan_id=<scan_id>, /api/scan, /api/directories, /api/scans, /api/search?q=python_code ✓
- Screenshots/GIFs List
  - Home: Recent Scans with source badge; Scanned Directories with badge; Last Scan Telemetry with Source badge.
  - Files: Scan form visible; Previously scanned directories with badge; filtered datasets view using scan_id.
  - API: /api/directories and /api/scans responses highlighting "source" field.

### Retro (mvp-iter-2025-08-19-gdu-ncdu)
- What Worked
  - Minimal integration: ncdu→gdu→python selection with a single source flag; transparent UI badges. ✓
  - Tests with subprocess/which mocks ensured deterministic coverage. ✓
  - API/UI consistency: source surfaced across scans, directories, telemetry. ✓
- What Slowed Us
  - Handling variability in external tool outputs; chose heuristic token extraction to avoid strict coupling. ✓
  - Clarifying scope for UI badges vs. text-only fallback. ✓
- Scope Adjustments
  - Deferred strict JSON schema parsing for ncdu/gdu to a later cycle; kept heuristic parsing + Python fallback. ✓
- Carry-overs
  - None critical; potential enhancement: richer scan details (sizes, dirs/files split) when external tools present. ✓
- Next Cycle Candidates (Updated RICE)
  - task:core-architecture/mvp/search-index — RICE 4.1 (slight ↑ due to growing dataset list)
  - task:core-architecture/mvp/neo4j-adapter-prep — RICE 3.3 (docs refinements + flag plan cross-check)
  - task:interpreters/mvp/ipynb-interpreter — RICE 3.5 (valuable for research repos)
  - task:ops/mvp/error-toasts — RICE 1.4 (improves demo robustness)
  - task:core-architecture/mvp/filesystem-scanner-hardening — RICE 2.6 (structured JSON parsing + metrics)

### Proposed Next Cycle (2025-08-26 → 2025-08-30)
- E2E Objective
  - A user can search datasets by filename or interpreter id in the UI; maintain a documented, switchable graph boundary for future Neo4j. (GUI-first)
- Top 5 Tasks
  1) task:core-architecture/mvp/search-index — Implement simple in-memory index; expose /api/search with stable fields. Owner: agent; RICE: 4.1.
  2) task:ui/mvp/home-search-ui — Add search box + results list on Home; link to dataset detail. Owner: agent; RICE: 3.6.
  3) task:core-architecture/mvp/neo4j-adapter-prep — Finalize adapter boundary docs + feature flags. Owner: agent; RICE: 3.3.
  4) task:interpreters/mvp/ipynb-interpreter — Add notebook summary (kernel, cell counts) with safe size limits. Owner: agent; RICE: 3.5.
  5) task:ops/mvp/error-toasts — Minimal client-side error toasts/log clarity for API calls. Owner: agent; RICE: 1.4.

### Planning Protocol (mvp-iter-2025-08-19-map-schema)
1) E2E Objective and GUI Acceptance
   - Objective: Make the current graph input and related schema visible on the Map page to support a transparent demo of what’s in the graph right now.
   - GUI Acceptance: After scanning a small folder, visiting /map shows a Schema panel with node labels and relationship types, including counts. The page loads without errors and reflects the current session graph. Home continues to show a Schema Summary, and Map adds a clearer, dedicated view.
2) Capacity
   - 8h
3) Selected Tasks Table with DoR (owner, ETA, RICE, dependencies, test approach)
   - id: task:core-architecture/mvp/neo4j-adapter-prep; owner: agent; ETA: 2025-08-19; RICE: 3.2; dependencies: current InMemoryGraph API; test approach: unit tests for schema_summary() shape; doc check for adapter boundary and schema fields used by /map.
   - id: task:core-architecture/mvp/neo4j-adapter-impl; owner: agent; ETA: 2025-08-19; RICE: 3.0; dependencies: task:core-architecture/mvp/neo4j-adapter-prep; test approach: extend schema_summary to include label/type counts used by Map; Flask client smoke test rendering /map.
4) Dependency Table
   - neo4j-adapter-impl → neo4j-adapter-prep (sequence for schema boundary and fields)
5) Demo Checklist
   1) Start app (python -m scidk.app)
   2) POST /api/scan with a temp folder containing a few files
   3) Open /map — Expect: Schema panel lists node labels and relationship types with counts; reflects the just-scanned data
   4) Open / — Expect: existing Schema Summary present; Map view provides a more detailed layout of the same underlying schema
6) Risks & Cut Lines
   - Risks: Over-scoping visualization; schema fields mismatch; limited time.
   - Cut lines: If time-constrained, render schema as two simple tables (labels, rel_types) without any graph drawing; if counts are expensive, show presence-only flags.
7) Decision & Risk Log entry
   - 2025-08-19: Decided to implement a minimal, table-based schema view on /map backed by schema_summary(); defer interactive graph drawing to a later iteration.
8) Tag to create
   - mvp-iter-2025-08-19-map-schema

### Approval (mvp-iter-2025-08-19-map-schema)
- APPROVED: 2025-08-19 10:14 (local)
- Proceeding with execution per plan; add table-based Map view, demo link, and smoke test.

### Planning Protocol (mvp-iter-2025-08-19-scan-map-schema-demo)
1) E2E Objective and GUI Acceptance
- Objective: Ship a runnable demo that scans a folder, maps files into a knowledge graph (dataset nodes with scanned properties and interpretation edges), and allows extracting nodes by label with the relevant schema visualized on the Map page.
- GUI Acceptance:
  - From Files page, a scan of a small folder creates Dataset nodes with visible properties (path, filename, extension, size_bytes, created, modified, mime_type) and any interpretations.
  - Map page shows a schema table (Node Labels and Relationship Types with counts) and an interactive graph built from unique triples.
  - Map page provides simple filters to extract a subschema by label and/or relationship type; graph updates accordingly.
  - “Download Schema (CSV)” exports NodeLabels and RelationshipTypes sections.

2) Capacity
- 8h

3) Selected Tasks Table with DoR (owner, ETA, RICE, dependencies, test approach)
- id: task:demo/mvp/scan-map-oneclick; owner: agent; ETA: 2025-08-19; RICE: 2.0; dependencies: app running; test approach: manual run of script verifies URLs, scan success, and that /map renders. 
- id: task:core-architecture/mvp/schema-triples-endpoint; owner: agent; ETA: 2025-08-19; RICE: 3.8; dependencies: InMemoryGraph; test approach: pytest validates JSON shape and CSV sections. Status: Done.
- id: task:ui/mvp/map-schema-graph-visualization; owner: agent; ETA: 2025-08-19; RICE: 3.6; dependencies: schema-triples-endpoint; test approach: smoke GET /map for Cytoscape container and CSV button. Status: Done.
- id: core-architecture/mvp/subschema-query-library; owner: agent; ETA: 2025-08-19; RICE: 3.3; dependencies: schema-triples-endpoint; test approach: add tests for GET /api/graph/subschema with params (labels, rel_types, limit) and named query; error on bad params; empty-graph path returns empty.
- id: ui/mvp/map-filters; owner: agent; ETA: 2025-08-19; RICE: 3.1; dependencies: subschema-query-library; test approach: UI smoke check for presence of two controls (Labels, Relationship Types); JS refetches and re-renders elements without console errors; manual verification of updates.

4) Dependency Table
- ui/mvp/map-filters → core-architecture/mvp/subschema-query-library → core-architecture/mvp/schema-triples-endpoint

5) Demo Checklist
1) Start the app (python -m scidk.app) or via ./scripts/demo-mvp-iter-2025-08-19-gdu-ncdu.sh
2) Script creates demo data and POSTs /api/scan {path: /tmp/scidk_demo_xxxx, recursive: false}
3) Visit Files (/datasets) and optionally filter by printed scan_id.
4) Open Map (/map):
   - Confirm schema tables and interactive graph render; node size/edge width reflect counts.
   - Click “Download Schema (CSV)” and confirm contents.
5) Use Map filters (after implementation):
   - Select label=Dataset and rel_types=INTERPRETED_AS to focus demo subschema.
   - Observe graph updates accordingly.
6) API spot checks:
   - GET /api/graph/schema returns expected shape with counts.
   - GET /api/graph/subschema?rel_types=INTERPRETED_AS returns focused subset.

6) Risks & Cut Lines
- Risks:
  - Scope creep from filter UX/server query in tight capacity.
  - Performance on large graphs (not an issue for tiny demo data).
- Cut lines (apply in order):
  1) If time-constrained, skip /api/graph/subschema and UI filters; ship full schema graph + CSV export.
  2) If Cytoscape layout struggles, cap edges with limit param (default 500) or present table-only schema for the demo.
  3) If CSV export causes issues, keep JSON-only; retain Map tables and graph.

7) Decision & Risk Log entry
- 2025-08-19: Keep unique-triples as canonical schema derivation for Map; add a thin subschema endpoint and minimal UI filters to satisfy “extract by label/type.” Maintain responsiveness via server-side limit and log-scaling.

8) Tag to create
- mvp-iter-2025-08-19-scan-map-schema-demo

### Planning Protocol (mvp-iter-2025-08-19-scan-graph-and-delete)
1) E2E Objective and GUI Acceptance
- Objective: Provide a way to commit a completed scan into the knowledge graph and to delete previous scans (including unlinking them from the graph). Keep datasets intact by default.
- GUI Acceptance (MVP via API-first):
  - POST /api/scans/<scan_id>/commit marks a scan as committed and adds a Scan node to the graph with edges (Dataset)-[SCANNED_IN]->(Scan).
  - DELETE /api/scans/<scan_id> removes the scan record and its graph node/edges; datasets remain and the app stays stable.
  - Map page schema now reflects committed scans: Node label "Scan" count and SCANNED_IN relation counts.

2) Capacity
- 4h (within current cycle’s buffer)

3) Selected Tasks Table with DoR (owner, ETA, RICE, dependencies, test approach)
- id: task:core-architecture/mvp/graph-scan-commit; owner: agent; ETA: 2025-08-19; RICE: 3.9; deps: InMemoryGraph; tests: commit creates Scan node + SCANNED_IN edges in /api/graph/schema.
- id: task:core-architecture/mvp/scan-delete; owner: agent; ETA: 2025-08-19; RICE: 3.5; deps: graph-scan-commit; tests: delete removes Scan node/edges; datasets remain.
- id: task:core-architecture/mvp/tests-hardening; owner: agent; ETA: 2025-08-19; RICE: 1.4; deps: endpoints exist; tests: pytest for commit/delete flow.

4) Dependency Table
- scan-delete → graph-scan-commit

5) Demo Checklist
1) POST /api/scan a tmp dir; note scan_id.
2) GET /api/graph/schema — no Scan nodes/SCANNED_IN initially.
3) POST /api/scans/<scan_id>/commit — expect {status: ok, committed: true}.
4) GET /api/graph/schema — now includes Scan node count >=1 and SCANNED_IN relation.
5) DELETE /api/scans/<scan_id> — expect {status: ok}.
6) GET /api/graph/schema — Scan count returns to 0 and SCANNED_IN edges disappear; datasets unaffected.

6) Risks & Cut Lines
- Risks: ambiguity whether deleting scans should also remove datasets; for MVP we keep datasets.
- Cut lines: API-only this cycle; UI delete/commit buttons can follow.

7) Decision & Risk Log entry
- 2025-08-19: Decided to model scans as Scan nodes and SCANNED_IN edges; deletion unlinks edges but retains datasets to avoid accidental data loss.

8) Tag to create
- mvp-iter-2025-08-19-scan-graph-and-delete

### Planning Protocol (mvp-iter-2025-08-20-demo-visual-and-schema)
1) E2E Objective and GUI Acceptance
- Objective: Prepare a demo where a folder is scanned, results are committed into the knowledge graph, and the Map page visualizes the schema with File/Folder nodes, shows relationship type labels, supports multiple layout modes, and allows saving/loading schema view configs and subschema queries.
- GUI Acceptance:
  - Files page scans a folder; user can commit the scan (API-first) so Map reflects it.
  - Map visual shows:
    - Nodes: File and Folder (replaces Dataset), plus Scan when committed.
    - Edges: INTERPRETED_AS (File→<type>), CONTAINS (Folder→File/Folder), SCANNED_IN (File/Folder→Scan).
    - Edge labels display relationship types on Cytoscape edges.
    - Layout switcher with at least: force-based (cose), hierarchical (breadthfirst as MVP), and manual (drag) with Save/Load.
  - Save/Load schema visualization configuration (positions, layout choice) and named subschema queries, persisted for the session (MVP: localStorage) and via simple API (optional if time allows).
  - CSV export continues to work; subschema filters keep the export consistent.

2) Capacity
- 8h

3) Selected Tasks Table with DoR (owner, ETA, RICE, dependencies, test approach)
- id: core-architecture/mvp/schema-file-folder-shape; owner: agent; ETA: 2025-08-20; RICE: 3.9; deps: InMemoryGraph; test: update schema_triples to emit File/Folder counts; preserve Scan + SCANNED_IN; unit tests for new labels/edges.
- id: ui/mvp/cyto-edge-labels; owner: agent; ETA: 2025-08-20; RICE: 3.2; deps: /api/graph/schema; test: /map HTML contains style for edge labels; manual verify labels rendered.
- id: ui/mvp/layout-modes; owner: agent; ETA: 2025-08-20; RICE: 3.4; deps: cytoscape; test: dropdown with options {force,breadthfirst,manual}; switching re-runs layout without console errors.
- id: ui-core/mvp/manual-save-load; owner: agent; ETA: 2025-08-20; RICE: 3.7; deps: layout-modes; test: Save stores positions to localStorage; Load applies positions; smoke test via DOM.
- id: core-architecture/mvp/schema-config-api (optional); owner: agent; ETA: 2025-08-20; RICE: 2.7; deps: save-load; test: GET/POST /api/graph/configs returns/stores JSON; skipped if time-constrained.
- id: core-architecture/mvp/query-presets; owner: agent; ETA: 2025-08-20; RICE: 3.3; deps: existing /api/graph/subschema; test: GET/POST /api/graph/queries for named filters; or MVP-only localStorage if API skipped.
- id: demo/mvp/e2e-script-refresh; owner: agent; ETA: 2025-08-20; RICE: 2.0; deps: above; test: script prints Map URL, commit scan curl, and notes for Save/Load.

4) Dependency Table
- ui/mvp/layout-modes → ui/mvp/cyto-edge-labels → core-architecture/mvp/schema-file-folder-shape
- ui-core/mvp/manual-save-load → ui/mvp/layout-modes
- core-architecture/mvp/query-presets → existing /api/graph/subschema
- demo/mvp/e2e-script-refresh → all of the above (if included)

5) Demo Checklist
1) Start app; POST /api/scan {path}; POST /api/scans/<scan_id>/commit.
2) Visit /map: confirm File and Folder node labels, Scan label when committed.
3) Confirm edge labels visible for INTERPRETED_AS, CONTAINS, SCANNED_IN.
4) Switch layouts: force (cose), hierarchical (breadthfirst), manual drag; Save then refresh and Load positions.
5) Use subschema filter (labels/rel_types) to focus on File↔INTERPRETED_AS; CSV export matches current view.
6) Optionally save a named query/config via UI/API and reload it.

6) Risks & Cut Lines
- Risks: Larger scope (schema change + UI features) in one cycle; plugin needs for hierarchical layouts; persistence complexity.
- Cut lines (apply in order):
  1) Use breadthfirst (built-in) instead of external dagre; ship force + breadthfirst only if needed.
  2) Save/Load via localStorage only; defer server API for configs/queries.
  3) If schema refactor is heavy, surface File/Folder labels as derived categories while keeping Dataset internally for this demo.

7) Decision & Risk Log entry
- 2025-08-20: Will replace Dataset with File and Folder for schema visualization and counts; keep Scan nodes and SCANNED_IN edges. Edge labels will be rendered directly in Cytoscape. Layout modes will be implemented with built-in layouts (cose, breadthfirst). Save/Load MVP will rely on localStorage, with optional API if time allows.

8) Tag to create
- mvp-iter-2025-08-20-demo-visual-and-schema

### Planning Protocol (mvp-iter-2025-08-20-feedback-docs-and-exports)
1) E2E Objective and GUI Acceptance
- Objective: Address feedback by documenting scan progress plan (ncdu background tasks and monitor), adding map tuning controls (node/edge size, readable labels), providing instances export per label, and clarifying Neo4j path.
- GUI Acceptance:
  - /map shows new sliders for Node size, Edge width, Label font, and a High-contrast toggle; styles update live.
  - Instances section on /map can preview rows for File/Folder/Scan and download CSV; XLSX works if openpyxl is installed.
  - Docs explain scan progress plan and Neo4j integration status and next steps.

2) Capacity
- 4h

3) Selected Tasks Table with DoR (owner, ETA, RICE, dependencies, test approach)
- id: ui/mvp/map-style-tuning; owner: agent; ETA: 2025-08-20; RICE: 3.4; deps: cytoscape; tests: smoke presence of controls; manual verify live updates.
- id: core-architecture/mvp/instances-endpoints; owner: agent; ETA: 2025-08-20; RICE: 3.6; deps: InMemoryGraph; tests: GET /api/graph/instances JSON shape; CSV download.
- id: docs/mvp/scan-progress-and-neo4j; owner: agent; ETA: 2025-08-20; RICE: 3.0; deps: none; tests: doc content present in README and cycles.

4) Dependency Table
- ui/mvp/map-style-tuning → none
- core-architecture/mvp/instances-endpoints → InMemoryGraph list_instances

5) Demo Checklist
1) POST /api/scan to index files.
2) Visit /map; adjust node/edge/label sliders; toggle high-contrast.
3) Click Preview under Instances; switch labels; download CSV and (if available) XLSX.
4) Confirm /api/graph/instances endpoints return expected shapes.

6) Risks & Cut Lines
- Risks: XLSX dependency not installed; large previews.
- Cut lines: If openpyxl missing, return 501 for XLSX; limit preview to 50 rows.

7) Decision & Risk Log entry
- 2025-08-20: Decided to implement instances export via CSV/XLSX endpoints and UI preview on /map. Background scan progress to be introduced via a tasks API in a subsequent cycle; documented plan in README.

8) Tag to create
- mvp-iter-2025-08-20-feedback-docs-and-exports

### Approval (mvp-iter-2025-08-20-demo-visual-and-schema)
- COMPLETED: 2025-08-20 (local). Implemented File/Folder schema visualization, edge labels, layout modes, and manual Save/Load via localStorage; CSV export maintained; subschema filters working. Verified via automated tests and manual smoke on /map. 

### Approval (mvp-iter-2025-08-20-feedback-docs-and-exports)
- COMPLETED: 2025-08-20 (local). Added Map tuning controls (node size, edge width, label font, high-contrast), Instances preview/download (CSV; XLSX when openpyxl present), and documented scan-progress and Neo4j next steps. Tests added for instances endpoints; all green.

### Planning Protocol (mvp-iter-2025-08-21-demo-polish-and-neo4j-flag)
1) E2E Objective and GUI Acceptance
- Objective: Wire a Neo4j-backed graph adapter behind a feature flag while keeping current in-memory functionality; ensure Files page scan management is solid (progress bars, commit/delete flow), and Map stays in parity across backends. Ship a crisp demo path.
- GUI Acceptance:
  - Environment can select backend via SCIDK_GRAPH_BACKEND=neo4j and NEO4J_URI/NEO4J_USER/NEO4J_PASSWORD.
  - Scans add File/Folder/Scan nodes and relationships in Neo4j when flag is on; Map schema and graph reflect Neo4j data.
  - Files page shows background scans with nonzero progress, scans appear in dropdown, and commit/delete work; Map updates accordingly.
  - Instances tabs remain functional; CSV/XLSX exports work regardless of backend.

2) Capacity
- 8h

3) Selected Tasks Table with DoR (owner, ETA, RICE, dependencies, test approach)
- id: core-architecture/mvp/graph-adapter-interface; owner: agent; ETA: 2025-08-21; RICE: 3.6; deps: current InMemoryGraph; tests: unit import + stub adapter parity for methods.
- id: core-architecture/mvp/neo4j-adapter; owner: agent; ETA: 2025-08-21; RICE: 3.9; deps: graph-adapter-interface; tests: integration using test Neo4j or mocked driver; verifies upsert_dataset, add_interpretation, commit_scan, schema_triples Cypher results shape.
- id: ops/mvp/feature-flag-and-config; owner: agent; ETA: 2025-08-21; RICE: 3.2; deps: neo4j-adapter; tests: app boot logs backend selection; falls back to in-memory cleanly if env missing.
- id: ui/mvp/instances-tabs; owner: agent; ETA: 2025-08-21; RICE: 2.3; deps: /api/graph/instances; tests: smoke for dynamic tabs from /api/graph/schema nodes; per-tab preview and download links. (Status: Done in current session.)
- id: ui/mvp/files-scan-panel-solidify; owner: agent; ETA: 2025-08-21; RICE: 2.8; deps: tasks API; tests: minimal UI smoke + API assertions that scans appear in /api/scans and GET /api/tasks shows progress > 0 when files exist. (Partially done; verify and fix any regressions.)

4) Dependency Table
- neo4j-adapter → graph-adapter-interface → feature-flag-and-config
- files-scan-panel-solidify → tasks API

5) Demo Checklist
1) Start app in in-memory mode; run a background scan; observe progress; open scan; commit to graph; open Map; verify schema and graph.
2) Switch to Neo4j: export NEO4J env vars, set SCIDK_GRAPH_BACKEND=neo4j; start app; run a small scan; commit; verify Map schema/graph reflect Neo4j; spot-check in Neo4j Browser.
3) Use Instances tabs to preview and download CSV/XLSX per label.

6) Risks & Cut Lines
- Risks: Neo4j connection/auth/config issues; driver availability; test environment for Neo4j.
- Cut lines:
  1) If Neo4j isn’t reachable, keep adapter behind flag and document steps; ship in-memory demo polish.
  2) If Cypher schema_triples parity lags, compute schema from in-memory and leave a toggle for backend selection for /api/graph/schema.

7) Decision & Risk Log entry
- 2025-08-20: Proceed with a feature-flagged Neo4j adapter to gain persistence and scale while preserving the in-memory path. Parity for /api/graph/schema via Cypher (APOC optional later).

8) Tag to create
- mvp-iter-2025-08-21-demo-polish-and-neo4j-flag

### Approval (mvp-iter-2025-08-21-demo-polish-and-neo4j-flag)
- APPROVAL REQUESTED: Please reply “APPROVE CYCLE” to proceed.

### Approval (mvp-iter-2025-08-20-neo4j-commit-consistency-and-verification)
- COMPLETED: 2025-08-20 19:21 local. Commit to Graph now reliably writes both File→SCANNED_IN→Scan and Folder→SCANNED_IN→Scan for recursive and non-recursive scans. Simplified Cypher: MERGE Scan once, then two independent subqueries for files and standalone folders, with proper WITH scoping and unique aliases. Added post-commit DB verification (counts file/folder SCANNED_IN edges) and surfaced results in the UI Tasks panel. Hardened Neo4j configuration handling (no-auth mode support, safe password persistence, backoff after auth failures). Added unit tests with a mocked Neo4j driver verifying query shape and verification feedback.
- How to test:
  - Configure Neo4j in Settings (or set env). Click “Test Graph Connection” → Connected.
  - Run a scan (non-recursive and recursive), press Commit to Graph.
  - Observe Background tasks line: “Neo4j: attempted=yes — verify=ok (files:X, folders:Y)”.
  - In Neo4j Browser: run MATCH (fo:Folder)-[:SCANNED_IN]->(:Scan) RETURN count(*), MATCH (f:File)-[:SCANNED_IN]->(:Scan) RETURN count(*).



## Status Snapshot (2025-08-21)
Done in current cycle window:
- Providers MVP (LocalFS + MountedFS) with /api/providers, /api/provider_roots, /api/browse; /api/scan accepts provider_id with legacy default.
- Files page consolidated: provider selector, roots, path input, browser table, scan action. Home shows “Scanned Sources.”
- Interpreters: TXT and XLSX implemented; Python, CSV, JSON, YAML, IPYNB registered with rule-based selection.
- Neo4j: Optional schema endpoints documented; Commit-to-Graph implemented with post-commit verification and a mocked-driver test.

Next Objectives:
- Background scanning tasks with a Tasks API and UI polling.
- Feature-flagged RcloneProvider to unlock cloud backends via rclone.

Cross-link:
- See dev/stories/story-mvp-multi-provider-files-and-interpreters.md (Status: Done).
- See dev/plan-next-increments-2025-08-21.md for the consolidated next-increments plan and acceptance criteria.
- See dev/ui/mvp/tasks-ui-polling.md for the UI polling pattern for /api/tasks.


### Planning Protocol (mvp-iter-2025-08-21-rocrate-map)
1) E2E Objective and GUI Acceptance
   - Objective: Getting the current graph input and its related schema visible on the Map page, with RO-Crate endpoints available to feed crate metadata. Theme priority: Story: ro-crate-integration-mvp — embed Crate-O and RO-Crate endpoints.
   - GUI Acceptance: After scanning a small folder, visiting /map shows a Schema panel with Node Labels and Relationship Types (with counts) reflecting the current session graph. When calling /api/rocrate on a chosen directory, a minimal JSON-LD crate is returned and can be used by an embedded viewer toggle on the Files page (link or iframe behind a flag).
2) Capacity
   - 8h
3) Selected Tasks Table with DoR (owner, ETA, RICE, dependencies, test approach)
   - id: task:core-architecture/mvp/research-objects-ro-crate; owner: agent; ETA: 2025-08-21; RICE: 3.4; dependencies: none; test approach: unit test asserting /api/rocrate returns minimal JSON-LD with @context, root Dataset, and children capped at depth=1; skip tests if flag disabled.
   - id: task:core-architecture/mvp/neo4j-adapter-prep; owner: agent; ETA: 2025-08-21; RICE: 3.2; dependencies: InMemoryGraph schema_summary API; test approach: unit tests for schema_summary() shape and presence of label/type counts used by /map; docs update verifying boundary fields.
   - id: task:core-architecture/mvp/neo4j-adapter-impl; owner: agent; ETA: 2025-08-21; RICE: 3.0; dependencies: task:core-architecture/mvp/neo4j-adapter-prep; test approach: Flask client smoke that /map renders schema tables after a POST /api/scan; verify counts non-negative and tables present.
4) Dependency Table
   - neo4j-adapter-impl → neo4j-adapter-prep
5) Demo Checklist
   1) Start app (python -m scidk.app)
   2) POST /api/scan with a small temp folder
   3) Visit /map — Expect: Schema tables list node labels and relationship types with counts matching the scan
   4) Call /api/rocrate?path=<scanned_dir> — Expect: minimal JSON-LD crate (depth=1) response
   5) If flag SCIDK_FILES_VIEWER=rocrate is enabled, Files page shows an "Open in RO-Crate Viewer" control (link or iframe) using the /api/rocrate output
6) Risks & Cut Lines
   - Risks: Over-scoping viewer integration; schema fields mismatch; tight capacity.
   - Cut lines: If time-constrained, ship Map page schema tables only (no iframe); keep /api/rocrate JSON-LD generation minimal without save; defer any interactive graph changes.
7) Decision & Risk Log entry
   - 2025-08-21 10:59: Chosen a table-based schema display for /map backed by schema_summary() and a minimal /api/rocrate JSON-LD endpoint; Crate-O embedding behind a feature flag to control scope.
8) Tag to create
   - mvp-iter-2025-08-21-rocrate-map
