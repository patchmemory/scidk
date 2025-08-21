# RO-Crate Viewer Embedding (Crate-O) — MVP Guide

Status: Draft (2025-08-21)
Owner: agent

## Goal
Embed a web RO-Crate viewer (starting with Crate-O) into the Files page to visualize/edit RO-Crate metadata for a selected folder. Keep existing scan/task panels; gate behind a feature flag.

## Feature Flag
- Env: `SCIDK_FILES_VIEWER`
  - Values: `classic` (default), `rocrate`
  - When `rocrate`, render embedded viewer section on /datasets.

## Backend Endpoints (MVP)
1) GET `/api/rocrate`
   - Query: `provider_id` (default `local_fs`), `root_id`, `path`
   - Returns: JSON-LD object for RO-Crate 1.1 with minimal graph:
     - Dataset (root folder) entity
     - Data entities for immediate children (files/folders)
     - Fields: name, contentSize, dateModified, encodingFormat (best-effort), and `url` pointing to `/files` for bytes
   - Caps: return at most 1000 children; depth = 1; include a `meta` section noting truncation if applied.

2) GET `/files`
   - Query: `provider_id`, `root_id`, `path`
   - Streams file bytes with correct Content-Type (best-effort by extension)
   - Security: reject path traversal, enforce that `path` resides under the normalized provider root
   - Limits: size cap (e.g., 32 MB) and timeouts; return 413/504 on caps

Optional for edit/save in later iterations:
- POST `/api/rocrate/save` — accept JSON-LD and persist to disk as `ro-crate-metadata.json` in the folder or sidecar in an app-managed store.

## Integration Pattern Options

A) Iframe (lowest friction)
- Add a small Flask route `/ui/rocrate_view` serving a wrapper HTML that loads the Crate-O app (from CDN or local copy) and points it at `/api/rocrate?...`.
- On /datasets, when user selects provider/root/path and clicks "Open in RO-Crate", set iframe `src` to `/ui/rocrate_view?provider_id=...&root_id=...&path=...`.
- Pros: fast to ship, decoupled; Cons: limited styling, need postMessage for advanced interactions.

B) In-page bundled viewer
- Place viewer assets under `scidk/ui/static/rocrate-viewer/`.
- Include `<script src="/static/rocrate-viewer/bundle.js"></script>` in datasets.html when flag is `rocrate`.
- Initialize with:
  ```js
  window.initCrateViewer({ metadataUrl: `/api/rocrate?provider_id=${pid}&root_id=${rid}&path=${encodeURIComponent(path)}` });
  ```
- Pros: same-origin, better UX; Cons: copy assets and track updates.

MVP choice: Start with A (iframe) to minimize asset management, then consider B.

## UI Changes (datasets.html)
- Keep the existing provider/root/path selector and Scan controls.
- Add a small section (feature-flagged) with:
  - A button: "Open in RO-Crate Viewer"
  - An `<iframe id="rocrate-frame" style="width:100%; height:70vh; border:1px solid #ddd;">` populated on click
- Hide/Show via `SCIDK_FILES_VIEWER` flag at render time (Jinja).

## Error Handling
- If `/api/rocrate` returns 4xx/5xx, display a friendly banner above the iframe area with the message and a link to open the classic list.
- For large folders, show a notice: "Showing first N items. Refine selection or run a background scan for full coverage."

## Testing Plan
- Flask test client:
  - `/api/rocrate` returns minimal JSON-LD for a temp directory with two files and one subfolder.
  - `/files` streams a small text file and blocks traversal attempts (e.g., `path=../../etc/passwd`).
- UI smoke:
  - Render datasets page with flag set; ensure iframe container exists and that clicking the button constructs the correct URL.

## Future Enhancements
- Add `/api/rocrate/save` and wire Save from viewer back to disk or app store.
- Enrich metadata via rocrate-py for correctness (authors, license, contextual entities).
- Persist crate as part of a Scan record and enable Export.
- Neo4j sync: `/api/rocrate/sync` to import JSON-LD into the graph.

## References
- RO-Crate 1.1 spec: https://w3id.org/ro/crate/1.1
- Crate-O viewer: https://github.com/ResearchObject/Crate-O (confirm embed options, license)
