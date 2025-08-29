id: feature:ui/rocrate-viewer-embedding
title: RO-Crate Viewer Embedding (Crate-O) — Files Page
status: Draft
owner: agent
created: 2025-08-21
updated: 2025-08-21
goal: Embed a web RO-Crate viewer (Crate-O) into the Files page to visualize/edit RO-Crate metadata for a selected folder, gated by a feature flag.
links:
  design: [dev/design/data/rocrate-embedding.md]
notes: |
  Migrated from dev/ui/mvp/rocrate-embedding.md.

## Feature Flag
- Env: `SCIDK_FILES_VIEWER`
  - Values: `classic` (default), `rocrate`
  - When `rocrate`, render embedded viewer section on /datasets.

## Backend Endpoints (MVP)
1) GET `/api/rocrate`
   - Query: `provider_id` (default `local_fs`), `root_id`, `path`
   - Returns: JSON-LD for RO-Crate 1.1 (root dataset + immediate children). Caps: max 1000 children; depth=1; include `meta` on truncation.

2) GET `/files`
   - Streams file bytes; validates provider/root/path; size cap and timeouts.

Optional later:
- POST `/api/rocrate/save` to persist JSON-LD as `ro-crate-metadata.json`.

## Integration Options

A) Iframe (initial choice)
- Serve wrapper `/ui/rocrate_view` that loads Crate-O and points to `/api/rocrate?...`.
- Pros: fast; Cons: styling and messaging limitations.

B) In-page bundled viewer
- Static assets under `scidk/ui/static/rocrate-viewer/` and init via script.
- Pros: better UX; Cons: asset maintenance.

## UI Changes (datasets.html)
- Keep provider/root/path selector and Scan controls.
- Add feature-flagged section with:
  - Button: "Open in RO-Crate Viewer"
  - `<iframe id="rocrate-frame" style="width:100%; height:70vh; border:1px solid #ddd;">`

## Error Handling
- Show banner for 4xx/5xx from `/api/rocrate`; provide link to classic list.
- For large folders, show truncation notice.

## Testing
- Flask test client: validate `/api/rocrate` minimal JSON-LD and `/files` traversal protection.
- UI smoke: with flag set, iframe container exists and URL constructed.

## Future Enhancements
- Add save endpoint; enrich metadata (via rocrate-py); persist crate with scan; Neo4j sync of JSON-LD.
