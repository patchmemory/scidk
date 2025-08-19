# Task: Registry, Rules, Executor Stub

## Metadata
- ID: task:interpreters/mvp/registry-and-executor
- Vision: vision:interpreters
- Phase: phase:interpreters/mvp
- Status: done
- Priority: P0
- Owner: agent
- Created: 2025-08-18
- ETA: 2025-08-24
- Labels: [interpreter, security]

## Goal
Selectable interpreters by extension and pattern; execution via secure stub with timeout.

## Context
Based on Interpreter Registry & Pattern Rules in dev/vision/interpreters.md and the SciDK Interpreter Management System design.

## Requirements
- InterpreterDefinition support (runtime, capabilities, script_type, script).
- Pattern-based rules priority sorting; sibling/parent file checks; file size expressions.
- Executor with read-only assumption + timeout; blocked operations (subprocess, network) in MVP.

## Interfaces
- Data: interpreters.yaml (registry + rules).
- API: POST /api/interpret { dataset_id, interpreter_id? }

## Implementation Plan
- Steps:
  1. Implement InterpreterRegistry with extension mapping and rules precedence.
  2. Implement PatternMatcher and rule evaluation helpers.
  3. Implement SecureInterpreterExecutor stub (timeouts, safe subprocess for bash; restricted exec for python inline).
  4. Wire into FilesystemManager.interpret_dataset.
- Code Touchpoints:
  - scidk/core/registry.py
  - scidk/core/pattern_matcher.py
  - scidk/core/security.py
  - scidk/core/filesystem.py

## Test Plan
- Unit: rule priority resolution; extension fallback; timeout triggers on long-running script.
- Integration: run PythonCodeInterpreter and Bash TIFF interpreter; verify graph caching and versioning.
- Acceptance (DoD): Registry can select PythonCode for .py and TIFF Bash for .tif with rule override; execution returns InterpretationResult and caches in graph.

## Dependencies
- Blocks: [task:core-architecture/mvp/rest-ui]
- Blocked by: [task:core-architecture/mvp/graph-inmemory]

## Risk & Rollback
- Risks: unsafe code paths; ensure blocked operations and timeouts.
- Rollback: feature-flag interpreter execution; disable risky runtimes.

## Progress Log
- 2025-08-18: Created task spec.
- 2025-08-18: Implemented minimal InterpreterRegistry (extension mapping) and PythonCodeInterpreter; executor and pattern rules pending.
- 2025-08-18: Added stubs for SecureInterpreterExecutor and PatternMatcher/RuleEngine. Extended InterpreterRegistry with get_by_id and select_for_dataset. Added POST /api/interpret endpoint (dataset_id, optional interpreter_id) wiring to registry and graph.
- 2025-08-18: Implemented rule-based selection: PatternMatcher glob support, Rule model with interpreter_id and priority, RuleEngine precedence; integrated into InterpreterRegistry.select_for_dataset with extension fallback. Registered default *.py rule in app; tests pass.

- 2025-08-18:  Confirmed executor timeout path (python inline and bash), ensured empty env for bash runner, and validated registry rule precedence; tests green. MVP DoD met for interpreters.
