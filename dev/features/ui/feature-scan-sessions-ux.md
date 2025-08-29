id: feature:ui/scan-sessions-ux
title: Scan Sessions — UX and Flows
status: Draft
owner: agent
created: 2025-08-21
updated: 2025-08-21
goal: Allow users to initiate a directory scan on the Files page, view recent scans on Home, and reopen a specific scan in Files.
links:
  backend: [feature:core-architecture/scan-sessions-registry]
notes: |
  Migrated from dev/ui/mvp/scan-sessions.md.

# UX

- Files (/datasets)
  - Contains the Scan form.
  - Shows a "Recent scans" dropdown. Selecting an item navigates to `/datasets?scan_id=<id>`.
  - When a scan filter is active, shows a banner with scan id, path, and recursive flag, plus a "Clear filter" link.
  - Table lists datasets filtered to the selected scan. Note: MVP shows only datasets newly added by that scan.
  - After submitting the Scan form, user is redirected to the filtered view for that run.

- Home (/)
  - Shows a "Recent Scans" list (most recent first), with a link to open each run in Files.
  - Keeps a collapsible "Scanned Directories (aggregate)" section for the legacy path-level summary.
  - Continues to show Last Scan Telemetry and global dataset summaries.

# API (UI-facing contract)

- POST /api/scan
  - Body: { path, recursive }
  - Returns: { status, scan_id, scanned, duration_sec, path, recursive }
  - Side effects: updates scans, directories (adds scan_id), telemetry.last_scan

- GET /api/scans
  - Returns list of recent scans (summary fields only + checksum_count).

- GET /api/scans/<scan_id>
  - Returns full scan session including `checksums`.

- GET /datasets?scan_id=<id>
  - UI route; filters dataset list by scan membership.

# Implementation Notes (UX)

- MVP membership computed via pre/post diff; Files page should indicate when a filtered list is empty due to no new items.
- Upgrade path: when backend provides `seen_checksums` for every file enumerated, show complete per-run coverage.

# Dev Testing

- Manual flow:
  1) Start app: `python -m scidk.app`
  2) Visit /datasets; run a scan of a small folder.
  3) You should be redirected to `/datasets?scan_id=<id>` showing only datasets added by that run.
  4) Visit Home (/) and see the Recent Scans list; click a scan to open it in Files.
  5) Call `GET /api/scans` and `GET /api/scans/<id>` to inspect registry state.

# Status

- MVP: In-memory; state resets on server restart.
