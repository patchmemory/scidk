# Task: JSON and YAML Interpreters (MVP)

## Metadata
- ID: task:interpreters/mvp/json-yaml
- Vision: vision:interpreters
- Phase: phase:interpreters/mvp
- Status: done
- Priority: P2
- Owner: agent
- Created: 2025-08-18
- ETA: 2025-08-18
- Labels: [interpreter, json, yaml]

## Goal
Add simple interpreters for JSON (.json) and YAML (.yml/.yaml) to extract top-level keys, types summary, and small samples.

## Requirements
- Map extensions to interpreters via registry rules.
- File size limit (<= 5 MB) and depth limit (e.g., summarize only first-level keys and primitive counts).
- Return InterpretationResult fields (example):
  {
    "type": "json",
    "top_level_keys": ["config", "data"],
    "key_types": {"config": "object", "data": "array"},
    "preview": {"config": {"version": 3}}
  }
- YAML handled via safe loader (no code execution).
- Unit tests: tiny fixture files and error paths for malformed/oversized inputs.

## Plan
1. Implement JsonInterpreter and YamlInterpreter in scidk/interpreters/.
2. Register *.json, *.yml, *.yaml rules in registry.
3. Render in dataset detail via existing JSON pretty-print.
4. Add tests in tests/.

## DoD
- Sample JSON and YAML files yield summaries visible in UI.
- Malformed files return a safe error state without crashing.

## Progress Log
- 2025-08-18: Implemented JsonInterpreter and YamlInterpreter; registered .json, .yml, .yaml in registry. UI renders summaries on dataset detail.
- 2025-08-18: Error handling: oversized files and parse errors return structured error states; no crashes observed.
