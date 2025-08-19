# Task: CSV Interpreter (MVP)

## Metadata
- ID: task:interpreters/mvp/csv-interpreter
- Vision: vision:interpreters
- Phase: phase:interpreters/mvp
- Status: done
- Priority: P1
- Owner: agent
- Created: 2025-08-18
- ETA: 2025-08-30
- Labels: [interpreter, csv]

## Goal
Provide a lightweight CSV interpreter to extract basic structure and summary: delimiter, headers, and row count.

## Requirements
- Map *.csv to csv interpreter via InterpreterRegistry.
- Detect delimiter (comma by default; try common delimiters ',', '\t', ';').
- Read first non-empty line as headers; compute total row count (excluding header).
- Limit file size to prevent heavy reads (e.g., <= 10 MB for MVP) and return error state if exceeded.
- Return an InterpretationResult with fields: {
  "type": "csv",
  "delimiter": ",",
  "headers": ["col1", "col2"],
  "row_count": 1234,
  "sample_rows": [optional small sample]
}

## Implementation Plan
- Add CsvInterpreter class (similar to PythonCodeInterpreter pattern) in scidk/interpreters/.
- Register interpreter in app/registry with rule for *.csv at reasonable priority.
- Update dataset detail page to render CSV summary nicely.
- Tests: unit test for small CSV; error path for oversized file.

## DoD
- For a sample CSV, interpretation yields headers and row count; visible in UI.
- Oversized file triggers safe error path, not crash.
- Tests for normal and error cases pass.

## Progress Log
- 2025-08-18: Drafted task and acceptance; to be implemented in upcoming cycle.
- 2025-08-18: Implemented CsvInterpreter with delimiter detection, headers, row count, size cap; registered *.csv; added tests; UI renders CSV summary; DoD met.
