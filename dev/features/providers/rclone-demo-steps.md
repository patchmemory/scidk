# RcloneProvider Demo Steps (MVP)

Prereqs:
- rclone installed and configured with at least one remote (e.g., gdrive:)
- Start app: `scidk-serve` (or `python -m scidk.app`)
- Ensure feature flag includes rclone: `export SCIDK_PROVIDERS=local_fs,mounted_fs,rclone`

Steps:
1. Open http://127.0.0.1:5000/datasets and scroll to the Scan Files panel.
2. Click Provider and verify "Rclone Remotes" appears when SCIDK_PROVIDERS includes rclone.
3. Select Provider = rclone. Click "Load Roots" (UI calls GET /api/provider_roots) and verify your remotes appear (e.g., gdrive:).
4. In Path, enter an rclone path like `gdrive:some/folder` and click Browse to list first-level entries (GET /api/browse).
5. Click Scan to POST /api/scan with provider_id=rclone and your path. The MVP records a metadata-only scan (no files ingested yet) — check the Scanned Directories list updates and the scan appears under Background Tasks.
6. Try a remote that isn't configured or stop rclone availability: the API replies with a clear error in JSON and 500 status for provider_roots/browse.

Notes:
- This MVP does not ingest remote files into datasets yet; it records scan sessions, paving the way for background sync in a future phase.
