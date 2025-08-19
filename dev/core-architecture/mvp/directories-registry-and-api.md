# Task: In-Session Directories Registry and API (MVP)

## Metadata
- ID: task:core-architecture/mvp/directories-registry-and-api
- Vision: vision:core-architecture
- Phase: phase:core-architecture/mvp
- Status: done
- Priority: P1
- Owner: agent
- Created: 2025-08-18
- ETA: 2025-08-18
- Labels: [api, storage, telemetry]

## Goal
Track scanned root directories during the app session and expose them via an API for the Home and Files pages.

## Requirements
- Maintain an in-memory registry on the Flask app instance at app.extensions['scidk']['directories'] keyed by path with fields: path, recursive, scanned (count), last_scanned (epoch seconds).
- Update registry on both POST /api/scan (API) and POST /scan (UI) flows.
- Provide GET /api/directories returning the list ordered by most recent scan (DESC).
- Non-persistent (session only) by design for MVP.

## Implementation
- scidk/app.py
  - api_scan: records telemetry for last scan and updates directories registry.
  - ui_scan: mirrors the same registry writes and redirects to Files page.
  - api_directories: returns directories as a JSON list sorted by last_scanned desc.

## DoD
- After scanning, GET /api/directories returns the scanned path with expected fields.
- Home page lists the directories; Files page shows collapsible history.
- Linked to cycle plan: mvp-iter-2025-08-18-2306 GUI Acceptance.

## Progress Log
- 2025-08-18: Implemented registry and /api/directories; verified ordering and fields in manual checks; aligned with UI templates.
