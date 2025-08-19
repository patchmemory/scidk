# Task: Files Scan UI and Home Directories List (MVP)

## Metadata
- ID: task:ui/mvp/files-scan-ui-and-home-directories
- Vision: vision:ux
- Phase: phase:ui/mvp
- Status: done
- Priority: P1
- Owner: agent
- Created: 2025-08-18
- ETA: 2025-08-18
- Labels: [frontend, ux, files, directories]

## Goal
Move the directory Scan form to the Files page and show a "Scanned Directories" list on the Home page summarizing scans performed during the session.

## Context
Earlier the Scan form was accessible from the Home page. The cycle target repositions scanning to the Files page (/datasets) and uses the Home page for session summaries and discovery (including chat and search).

## Requirements
- Files page (/datasets) contains a Scan form (path input, recursive checkbox) and lists previously scanned directories (session memory).
- Home page (/) shows a Scanned Directories list including path, files scanned, and recursive flag; ordered by most recent scan.
- Acceptance paired with API: GET /api/directories returns the same data.

## Implementation
- Templates
  - scidk/ui/templates/datasets.html: Added "Load Directory" form posting to /scan; shows session directories under a collapsible section.
  - scidk/ui/templates/index.html: Added "Scanned Directories" section listing entries.
- Routes
  - UI POST /scan handled by ui_scan (in scidk/app.py) redirects back to Files page after scan; updates session telemetry and directories registry.

## DoD
- Manual demo path:
  1. Start app (python -m scidk.app)
  2. Open Files page (/datasets). Submit Scan form for a small directory.
  3. Home page (/) shows the scanned directory entry; Files page shows it under "Previously scanned".
  4. GET /api/directories returns the entry.
- Matches Current Cycle Iteration Plan: mvp-iter-2025-08-18-2306.

## Progress Log
- 2025-08-18: Implemented UI changes and verified in browser; acceptance criteria met.
