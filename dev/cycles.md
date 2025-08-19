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
