# Task: Rename "Extensions" to "Interpreters" (UI Navigation and Page)

## Metadata
- ID: task:ui/mvp/rename-extensions-to-interpreters
- Vision: vision:ux
- Phase: phase:ui/mvp
- Status: done
- Priority: P1
- Owner: agent
- Created: 2025-08-18
- ETA: 2025-08-18
- Labels: [frontend, navigation, routing]

## Goal
Rename the UI section and navigation from "Extensions" to "Interpreters" while maintaining backward compatibility (redirect from /extensions to /interpreters). Ensure the page lists registry mappings and selection rules.

## Requirements
- Top navigation shows "Interpreters" and links to /interpreters.
- Visiting /extensions redirects to /interpreters (legacy route kept).
- The Interpreters page renders current registry mappings by extension and the active selection rules.
- Smoke testable via Flask test client.

## Implementation
- Routes added/updated in scidk/app.py:
  - ui.interpreters at GET /interpreters renders extensions.html with mappings and rules from InterpreterRegistry.
  - ui.extensions_legacy at GET /extensions performs redirect to /interpreters.
- Template reuse: extensions.html continues to serve the Interpreters page (showing mappings and rules).

## DoD
- GET /interpreters returns 200 and shows mappings for .py, .csv, .json, .yml/.yaml.
- GET /extensions returns 302 redirecting to /interpreters.
- Visible in the top navigation as "Interpreters".
- Matches Iteration Plan: mvp-iter-2025-08-18-2259.

## Progress Log
- 2025-08-18: Implemented route and redirect; verified manually in browser and via simple smoke tests.
