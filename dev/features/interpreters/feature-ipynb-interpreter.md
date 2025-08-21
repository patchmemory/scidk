id: feature:interpreters/ipynb-interpreter
title: IPYNB Interpreter (Notebook Summary)
status: Draft
owner: agent
created: 2025-08-21
updated: 2025-08-21
goal: Provide a safe, non-executing interpreter for .ipynb notebooks that extracts lightweight metadata and structure.
scope:
  - Map *.ipynb to an ipynb interpreter via the InterpreterRegistry
  - Parse notebook JSON safely (no code execution)
  - Return fields: { type, kernel, language, cells: {code, markdown, raw}, first_headings[], imports[] }
  - Enforce file size cap (e.g., <= 5 MB for MVP) and return a structured error when exceeded
out_of_scope:
  - Executing notebook code cells
  - Rendering cells beyond simple metadata/summary in MVP
success_metrics:
  - For a small sample notebook, interpreter returns kernel, language, and accurate cell counts
  - Oversized or malformed notebooks handled gracefully with structured errors
links:
  stories: []
  tasks: [task:interpreters/mvp/ipynb-interpreter]
notes: |
  Derived from legacy doc dev/interpreters/mvp/ipynb-interpreter.md (removed during cleanup). This feature preserves the specification while the execution task lives in dev/tasks/.

Acceptance sketch (for reference)
- Maps .ipynb to summary with cell counts and metadata
- Handles large notebooks by size cap
