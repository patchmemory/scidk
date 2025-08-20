# Story: MVP Multi-Provider Files + TXT/XLSX Interpreters

id: story:providers-mvp-multi-source-files
status: Done
owner: agent
created: 2025-08-20
completed: 2025-08-20

Overview
- Unify browsing and scanning of multiple filesystems (Local, Mounted vols; rclone-backed clouds like Dropbox, Google Drive, OneDrive/SharePoint, Box, S3-compatible; plus native REST like Globus later) via a pluggable Provider SDK.
- Add TXT and XLSX interpreters to complement CSV.
- Keep legacy local scanning working; ensure UI remains GUI-first and demoable at the end of the cycle.

Decision: Cloud integration approach (MVP)
- Adopt a hybrid approach centered on rclone where possible, with native REST providers added via plugins when needed.
- Prefer Option 2: RcloneProvider via subprocess (shelling out to `rclone lsjson`, `rclone cat`, etc.), no OAuth in-app; rely on rclone config.
- Treat all providers as plugins: a class of pluggable provider modules (e.g., RcloneProvider for many clouds, and native REST providers like Globus) that can be plugged into the Files experience.

E2E Objective (for this story’s initial cycle)
- The File page can browse Local and Mounted providers and scan a selected folder. Home is accessed from the SciDK logo and shows "Scanned Sources" with provider badges. TXT and XLSX interpreters produce summaries on dataset detail. ProviderRegistry is in place to enable future cloud providers.

Success Criteria
- APIs: /api/providers, /api/browse, /api/scan accept provider_id and work for Local + Mounted.
- UI: File page shows provider selector, roots, browser table, and Scan action. Home shows "Scanned Sources" with provider badges.
- Interpreters: .txt and .xlsx files produce summaries; .csv remains working.
- Backwards compat: Legacy /api/scan without provider_id still scans local.

Scope (In)
- Provider SDK contracts + registry; LocalFS and MountedFS providers
- Minimal browse and scan APIs; pagination support where feasible
- TXT and XLSX interpreters (summaries only)
- UI updates for provider-aware File and Home pages; Plugins and Interpreters sections live under Set (Settings) page

Scope (Out for MVP)
- In-app OAuth for cloud providers — use rclone config instead (RcloneProvider)
- Persistence of provider tokens or long-running background worker — planned
- Advanced UI polish, drag/drop, multi-select — later

Architecture: Filesystem Provider SDK
- ProviderDescriptor
  - id: local_fs | mounted_fs | rclone | dropbox | gdrive | office365 | globus | ...
  - display_name: Local Files | Mounted Volumes | Rclone Remotes | Dropbox | Google Drive | Microsoft 365 | Globus | ...
  - capabilities: [browse, read, list_roots, requires_auth, background_scan]
  - auth: { type: none|rclone-config|oauth2|keyfile }
- FilesystemProvider interface
  - initialize(app, config)
  - status(app) → { ok: bool, message, account? }
  - list_roots() → [DriveInfo]
  - list(root_id, path, page_token?, page_size?) → { entries: [Entry], next_page_token? }
  - get_entry(id) → Entry
  - open(entry_id) → stream/bytes (optional)
  - resolve_scan_target(input) → { provider_id, root_id, path, label }
  - enumerate_files(scan_target, recursive, progress_cb) → iterator<FileMeta>
- ProviderRegistry
  - register(provider), get(id), list(), feature flags: SCIDK_PROVIDERS=local_fs,mounted_fs[,rclone]

Rclone Integration (Option 2 — subprocess)
- Descriptor: id=rclone, display_name="Rclone Remotes", auth={ type: "rclone-config" }, capabilities=[browse, read, list_roots]
- list_roots → `rclone listremotes` (roots are remote names: `gdrive:`, `dropbox:`)
- list → `rclone lsjson <remote:path> --max-depth 1`
- open → `rclone cat <remote:path/to/file>` (stream)
- enumerate_files → `rclone lsjson <remote:path> --recursive` (respect MAX_FILES_PER_SCAN)
- Health: status() verifies `rclone version` on PATH and remote existence

Plugin model
- Providers are plugins. RcloneProvider covers many services; native REST providers (e.g., Globus) are separate plugins.
- Future REST APIs can be added as plugins without changing core DTOs.

Data Model Additions
- Dataset additions: provider_id, provider_ref, path, display_path
- Scan record additions: provider_id, root_id, root_label, source: "provider:<id>"
- Rename UI terminology from "Directories" → "Scanned Sources" (keep API alias for /api/directories)

API Surface (MVP)
- GET /api/providers → [{ id, display_name, capabilities, auth }]
- GET /api/browse?provider_id=local_fs&root_id=/&path=/home/user&page_token=...
  - → { entries: [ { id, name, type: file|folder, size, mtime } ], next_page_token }
- POST /api/scan { provider_id, root_id?, path, recursive? }
  - → { scan_id, file_count, source: "provider:<id>" }
- Legacy: POST /api/scan { path, recursive } defaults provider_id=local_fs

UI/UX Changes (MVP)
- Navigation Renames: Home → (SciDK logo only), Files → File, Map → Map, Chat → Chat, Settings → Set
- Move Plugins and Interpreters from header to Set page as sections (embed summaries; link to full pages)
- File page: provider selector, roots dropdown, browser table (Name, Type, Size, Modified, Provider badge), Scan panel with recursive toggle
- Home: "Scanned Sources" showing provider badge, root label/path, counts, recursive flag and source
- Dataset detail: show provider badge + display_path; .xlsx links to Workbook Viewer

Interpreters
- TxtInterpreter (id: txt)
  - Maps *.txt → { type: "txt", encoding?, line_count, preview: first N lines or 4KB }
  - Size cap (e.g., 10 MB); return safe message if exceeded
- XlsxInterpreter (id: xlsx)
  - Maps *.xlsx, *.xlsm → { type: "xlsx", total_sheets, sheets: [ { name, rows, cols } ], has_macros? }
  - UI: link dataset detail to Workbook Viewer

Feature Flags & Config
- SCIDK_PROVIDERS=local_fs,mounted_fs[,rclone]
- Limits: BROWSE_PAGE_SIZE, MAX_FILES_PER_SCAN, MAX_PREVIEW_BYTES

Risks & Mitigations
- Large listings → enforce page_size and server-side slicing; consider rclone `--fast-list` where supported
- Mounted detection variance across OSes → psutil.disk_partitions fallback and allow manual path
- Encoding for TXT → detect with chardet or try/except with utf-8 then latin-1

Phased Roadmap
- Phase 0 (Contracts + Local/Mounted)
  - Implement ProviderRegistry + FilesystemProvider interface
  - LocalFSProvider and MountedFSProvider
  - API: /api/providers, /api/browse, /api/scan with provider_id
  - UI: File provider selector; Home → "Scanned Sources"
  - Tests: registry unit tests; browse/list integration; scan flow
- Phase 1 (TXT + XLSX Interpreters)
  - Implement TxtInterpreter and XlsxInterpreter + tests; register rules; link .xlsx to viewer
- Phase 2 (RcloneProvider + Docs for mounts)
  - Add feature-flagged RcloneProvider (subprocess-based); roots=listremotes; browse=lsjson; open=cat; scan=lsjson --recursive
  - Document using rclone FUSE mounts as an alternative path (works with MountedFS)
- Phase 3 (Native REST Provider: Dropbox or Google Drive or Office365)
  - Introduce OAuth helper (Auth Code + PKCE); implement browse + scan; provider_ref stored
- Phase 4 (Globus Stub)
  - Endpoints listing + minimal enumeration; mark experimental

Acceptance & Demo Checklist (for Phase 0–1)
- [x] File page shows provider selector with Local + Mounted
- [x] Can browse and scan a mounted folder; shows progress or completes synchronously
- [x] Home shows Scanned Sources with provider badges
- [x] TXT and XLSX summaries render on dataset detail; .xlsx links to Workbook Viewer
- [x] /api/providers, /api/browse, /api/scan work with provider_id; legacy /api/scan without provider_id works for local

Operator Prompts (use these to drive the repo forward)

Phase 0 — Provider SDK, Local + Mounted
- Prompt 1: "Add a ProviderRegistry and FilesystemProvider interface to the backend. Implement LocalFSProvider wrapping existing filesystem logic and MountedFSProvider using psutil.disk_partitions. Expose GET /api/providers and GET /api/browse endpoints. Keep /api/scan backward-compatible but accept provider_id. Add minimal unit tests for registry and browse."
- Prompt 2: "Update the File page to include a provider selector (Local, Mounted) and a basic browser table bound to /api/browse. Add a Scan panel that posts to /api/scan with provider_id. Rename Home section to 'Scanned Sources' and include provider badges."
- Prompt 3: "Extend the dataset/scan data model with provider_id, provider_ref, display_path. Ensure legacy flows still work if provider_id is omitted."

Phase 1 — TXT and XLSX Interpreters
- Prompt 4: "Implement TxtInterpreter (id 'txt'): handle utf-8 with fallback, size cap, first 100 lines or 4KB preview, line_count. Register in InterpreterRegistry and render on dataset detail."
- Prompt 5: "Implement XlsxInterpreter (id 'xlsx'): read sheet names, rows, cols; detect macros; integrate link to Workbook Viewer in dataset detail. Add tests with small workbook fixture."

Phase 2 — RcloneProvider MVP
- Prompt 6: "Implement RcloneProvider (subprocess-based). descriptor id='rclone', display='Rclone Remotes'. list_roots=listremotes; list=lsjson; open=cat; enumerate_files=lsjson --recursive (with caps). Add feature flag SCIDK_PROVIDERS=rclone,local_fs,mounted_fs."

Phase 3 — Native REST Provider (Dropbox/GDrive/Office365)
- Prompt 7: "Introduce OAuth2 helper (Auth Code + PKCE). Implement provider with status, list_roots, list, enumerate_files. Add /api/providers/:id/auth/start and callback routes. UI gets a 'Connect' action and can browse and scan."

Phase 4 — Globus Stub
- Prompt 8: "Add a minimal Globus provider that lists endpoints and enumerates files for a selected endpoint. Mark experimental under feature flag."

Hardening & UX
- Prompt 9: "Introduce a simple tasks API for background scans with progress polling, then wire the File page to show progress for long scans. Add client error toasts for browse/scan failures."

Testing Prompts
- Prompt 10: "Add integration tests hitting /api/providers, /api/browse (Local + Mounted), and /api/scan with provider_id. Add interpreter unit tests for txt/xlsx including large file guardrails."

Traceability
- Related cycle: dev/cycles.md — Proposed Next Cycle (2025-08-25 → 2025-08-29)
- When implementing, tag PRs with story:providers-mvp-multi-source-files

Notes
- Keep feature flags and DTOs stable to ease onboarding of future cloud providers.
- Prefer small, demoable increments that keep GUI acceptance achievable each week.

Updates
- 2025-08-20: Phase 0–1 complete. Implemented ProviderRegistry with LocalFS and MountedFS providers; endpoints /api/providers, /api/provider_roots, /api/browse; updated /api/scan to accept provider_id with legacy default to local_fs; UI File page now has provider selector + browser + scan; Home shows Scanned Sources with provider badges; Txt/Xlsx interpreters registered and dataset detail rendering intact.
