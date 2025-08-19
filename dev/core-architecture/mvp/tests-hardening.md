# Task: Tests — Idempotency & Interpreter Error Handling

## Metadata
- ID: task:core-architecture/mvp/tests-hardening
- Vision: vision:core-architecture
- Phase: phase:core-architecture/mvp
- Status: done
- Priority: P1
- Owner: agent
- Created: 2025-08-18
- ETA: 2025-08-21
- Labels: [testing, quality]

## Goal
Add tests to ensure filesystem scan idempotency and robust interpreter error handling paths.

## Requirements
- Unit tests:
  - test_checksum_idempotency: rescanning same path does not create duplicate datasets (same checksum).
  - test_python_interpreter_syntax_error: malformed .py triggers error status, captured in graph.
  - test_interpreter_timeout: long-running code respects timeout (executor returns error/timeout status).
- Keep runtime fast; tests must pass in CI.

## Implementation Plan
- Extend tests in tests/ using existing fixtures in tests/conftest.py.
- Reuse InMemoryGraph; assert dataset counts and interpretation entries.
- For timeout, craft an interpreter that sleeps beyond configured timeout or simulate via PythonCodeInterpreter edge case.

## DoD
- All new tests pass locally with `pytest`.
- No flakiness observed across 3 runs.
- Documented in this task and referenced from dev/cycles.md.

## Progress Log
- 2025-08-18: Drafted task and outlined unit tests.
- 2025-08-18: Implemented rescan idempotency test (no duplicate datasets across rescans) and Python interpreter syntax error test; both passing.
- 2025-08-18: Added timeout coverage: SecureInterpreterExecutor inline python timeout and bash timeout; tests passing quickly.
