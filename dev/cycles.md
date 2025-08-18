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
