# Interpreters

## Vision Summary
- ID: vision:interpreters
- Owner: Data Understanding Team
- Last Updated: 2025-08-18
- Related Docs: dev/vision/interpreters.md

## Problem & Value
- Problem: Multiple scientific data "languages" require pluggable understanding.
- Target Users: Researchers, Data Scientists, Core Staff
- Value Stories: See dev/vision/ux_stories.md

## Scope (In / Out)
- In: Interpreter registry, pattern rules, multi-runtime execution, sandbox stub, management UI (read-only MVP; editable later).
- Out: Full sandbox hardening and node/perl/R runtimes until Alpha.

## Phases
- [phase:interpreters/mvp] Core Interpreter Framework — Status: planned, Target: 2025-09-10
- [phase:interpreters/ui] Interpreter Management UI — Status: planned, Target: 2025-09-25

## Risks & Mitigations
- Risk: Untrusted code execution → Mitigation: strict timeouts, read-only assumption, block subprocess in MVP.
- Risk: Performance on large files → Mitigation: sampling strategies and max_file_size checks.

## Open Questions
- Which standard library interpreters are P0 for MVP? (.py, .tiff via bash, maybe .csv?)
- Preferred format for interpreters.yaml vs. per-file interpreter defs?
