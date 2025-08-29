# Interpreters

## Vision Summary
- ID: vision:interpreters
- Owner: Data Understanding Team
- Last Updated: 2025-08-21
- Related Docs: dev/vision/interpreters.md

## Problem & Value
- Problem: Multiple scientific data "languages" require pluggable understanding.
- Target Users: Researchers, Data Scientists, Core Staff
- Value Stories: See dev/vision/ux_stories.md

## Scope (In / Out)
- In: Interpreter registry, pattern rules, multi-runtime execution, sandbox stub, management UI (read-only MVP; editable later).
- Out: Full sandbox hardening and node/perl/R runtimes until Alpha.

## Phases
- [phase:interpreters/mvp] Core Interpreter Framework — Status: in-progress, Target: 2025-09-10
- [phase:interpreters/ui] Interpreter Management UI — Status: planned, Target: 2025-09-25

## Supported Interpreters (MVP)
- python_code — imports, functions, classes, docstring
- csv — headers, row count
- json — top-level keys/preview
- yaml — top-level keys/preview (graceful when PyYAML missing)
- txt — encoding fallback, line_count, preview with size caps
- xlsx/xlsm — sheet list, rows/cols, macros flag; linked Workbook Viewer
- ipynb — metadata and cell counts (summary only)

## Risks & Mitigations
- Risk: Untrusted code execution → Mitigation: strict timeouts, read-only assumption, block subprocess in MVP.
- Risk: Performance on large files → Mitigation: sampling strategies and max_file_size checks.
- Execution safety: A SecureInterpreterExecutor enforces timeouts and caps for inline Python and bash helpers.

## Open Questions
- Preferred format for interpreters.yaml vs. per-file interpreter defs?
