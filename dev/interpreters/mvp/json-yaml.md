# Task: JSON and YAML Interpreters (MVP)

## Metadata
- ID: task:interpreters/mvp/json-yaml
- Vision: vision:interpreters
- Phase: phase:interpreters/mvp
- Status: done
- Priority: P1
- Owner: agent
- Created: 2025-08-18
- ETA: 2025-08-18
- Labels: [interpreter, json, yaml]

## Goal
Add lightweight interpreters for .json and .yml/.yaml files to extract top-level summaries for quick dataset understanding.

## Requirements
- Map *.json to json interpreter and *.yml/*.yaml to yaml interpreter via InterpreterRegistry.
- Return safe summaries with size caps (~5MB) and clear error states for oversized or malformed content.
- YAML interpreter must handle missing PyYAML dependency gracefully.
- Appear in UI dataset detail and on the Interpreters page mappings.

## Implementation
- scidk/interpreters/json_interpreter.py: Parses JSON with size limit; returns top-level keys, key types, and a shallow preview. Handles JSONDecodeError.
- scidk/interpreters/yaml_interpreter.py: Uses yaml.safe_load if available; returns similar summary, with explicit error if PyYAML is missing or file too large.
- scidk/app.py: Registered interpreters and selection rules; added mappings for .json, .yml, .yaml.

## DoD
- Scanning a directory with sample.json and sample.yaml adds datasets; dataset detail shows summaries from respective interpreters.
- Interpreters listed on /interpreters page.
- Error paths: oversized files and missing PyYAML handled without crashing.
- Matches Iteration Plan: mvp-iter-2025-08-18-2259.

## Progress Log
- 2025-08-18: Implemented JSON and YAML interpreters; registered mappings and rules; performed manual smoke tests on small fixtures.
