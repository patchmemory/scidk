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
    - Status by Task:
      - [task:core-architecture/mvp/graph-inmemory]: Done (MVP in-memory adapter in scidk/core/graph.py).
      - [task:core-architecture/mvp/filesystem-scan]: Done (scan + dataset node + checksum idempotency).
      - [task:core-architecture/mvp/rest-ui]: Done (routes + templates minimal).
      - [task:interpreters/mvp/registry-and-executor]: In-progress (basic registry by extension done; pattern rules + secure executor stub pending).

- Next Up (prioritized):
  1) Extend InterpreterRegistry with pattern rules and precedence; add SecureExecutor stub with timeouts.
  2) Add POST /api/interpret to run a specific interpreter for a dataset id (optional for this cycle if time permits).
  3) Add minimal telemetry/logging for scan duration and counts.

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
- Review
  - "Validate DoD for task:<id>; move status to review and summarize changes."
- Retro
  - "Append one learning to dev/cycles.md Retro notes; propose one improvement to templates."

## Backlog Grooming
- Add new tasks from discoveries; ensure each has Goal, DoD, Owner.
