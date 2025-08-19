# Scan Sessions MVP

Goal: Allow users to initiate a directory scan on the Files page, store that scan as a first-class session entity, summarize recent scans on Home, and reopen a specific scan in Files.

Status: Implemented for MVP (in-memory, session-scoped). Membership list captures newly added datasets from a scan (pre/post diff). A future enhancement will capture all files seen in the scan.

## Concepts

- Scan Session
  - id: short sha1 of `<path>|<started>`
  - path: scanned root directory
  - recursive: boolean
  - started, ended, duration_sec
  - file_count: number of files the scanner iterated over in this run
  - checksums: list of dataset checksums added by this scan (MVP)
  - by_ext: map of extension → count derived from `checksums`
  - errors: list of error strings (reserved, unused in MVP)

- Registries (in-memory)
  - `app.extensions['scidk']['scans']`: scan_id → Scan Session
  - `app.extensions['scidk']['directories']`: path → aggregate info { path, recursive, scanned, last_scanned, scan_ids[] }
  - `app.extensions['scidk']['telemetry'].last_scan`: prior lightweight telemetry retained for Home

## UX

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

## API

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

## Implementation Notes

- MVP membership computed via pre/post diff:
  - before = set(all checksums)
  - run scan
  - after = set(all checksums)
  - checksums = list(after - before)
  - This means re-scanning a directory with previously-seen files will produce an empty membership list. The Files page indicates this in a note when filtered list is empty.

- Upgrade path to full correctness:
  - Extend FilesystemManager to provide callbacks or return `seen_checksums` for every file enumerated during that run, even if already in memory. Then store that set into Scan Session.

## Small Fix

- Updated dataset_detail workbook link to use `dataset.id` (the route `/workbook/<dataset_id>` resolves by id, not checksum).

## Dev Testing

- Manual flow:
  1) Start app: `python -m scidk.app`
  2) Visit /datasets; run a scan of a small folder.
  3) You should be redirected to `/datasets?scan_id=<id>` showing only datasets added by that run.
  4) Visit Home (/) and see the Recent Scans list; click a scan to open it in Files.
  5) Call `GET /api/scans` and `GET /api/scans/<id>` to inspect registry state.

- Notes: All state is in-memory and resets on server restart.
