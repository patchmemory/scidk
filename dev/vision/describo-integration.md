# Describo Integration — Product Vision (Draft)

Status: Draft (2025-08-21)
Owner: agent

## Why Describo
Describo Desktop provides rich, AI-assisted RO-Crate authoring. Instead of rebuilding that capability, SciDK will interoperate to let researchers seamlessly move between SciDK-managed datasets and Describo for deep metadata enhancement.

## Goals
- Launch Describo on a selected dataset/folder with context.
- Round-trip RO-Crate metadata back into SciDK (persist crate; update status).
- Avoid conflicts when multiple editors (Crate-O, Describo, Excel) touch the same crate.
- Feed updated crates into Neo4j for knowledge graph queries.

## User Flows
1) Launch from SciDK
- User selects a folder in Files page, clicks "Open in Describo".
- SciDK ensures a current RO-Crate exists (create minimal if absent) and shows a modal with instructions: path, crate location, and a copy button.
- Optionally, SciDK can write a `.describo` project config if supported.

2) Edit in Describo
- User performs edits; saves `ro-crate-metadata.json` within the folder.

3) Sync Back
- Back in SciDK, user clicks "Sync from Describo"; or SciDK detects file change (mtime) and offers to sync.
- SciDK imports JSON-LD, updates internal status, and (optionally) syncs to Neo4j (Graph Import).

## Conflict Handling
- Single Source of Truth: Store crate alongside data in the folder (preferred) or in an app-managed sidecar store with a path reference.
- Locking Approach (lightweight):
  - On "Open in ...", create `.sci-lock` (JSON: editor, pid, timestamp). Show a warning if lock exists from another editor/session.
  - On save/sync, remove lock if same owner or timeout (e.g., 2h).
- Merge Strategy:
  - Prefer most recent mtime when no lock exists.
  - If concurrent divergent edits detected (hash mismatch), present a conflict modal with options: keep mine, take theirs, or export both.

## Technical Interfaces
- Ensure endpoints:
  - GET `/api/rocrate` — generate minimal crate if missing (view)
  - POST `/api/rocrate/save` — accept crate JSON and persist
  - POST `/api/rocrate/sync` — import to Neo4j; return summary (nodes/edges added)
- CLI helpers (optional):
  - `scidk rocrate save --path <dir> <file.json>`
  - `scidk rocrate sync --path <dir>`

## Milestones
1) MVP (Cycle N)
- Instructional modal + manual sync flow
- Save crate to disk; no autolocking

2) Locking + Detection (Cycle N+1)
- Implement `.sci-lock` and warning UX
- Basic mtime/hash conflict prompts

3) Deep Integration (Cycle N+2)
- Describo project files support (if applicable)
- Auto-detect changes and background sync to Neo4j
- Metadata quality scoring and suggestions

## Open Questions
- Describo project config format and detection; confirm best way to pre-open a folder.
- Cross-platform path handling and permissions (Windows/macOS/Linux).
- Large crate performance considerations.

## References
- Describo: https://arkisto-platform.github.io/describo/
- RO-Crate: https://www.researchobject.org/ro-crate/
