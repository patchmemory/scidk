id: vision:rclone-integration
title: Rclone Integration Vision
status: Draft
owner: agent
created: 2025-08-28
updated: 2025-08-28
summary: |
  Make cloud storage accessible through rclone with a safe, performant, and simple UX. Start with a
  feature-flagged RcloneProvider for direct listing/scan and evolve toward in-app configuration and
  optional mount management, while keeping the app read-only by design.

north_star:
  - Direct browse/scan across many cloud providers without bespoke SDKs.
  - Read-only by default; zero destructive file operations in the app.
  - Fast discovery for large trees (prefer lsjson with recursive/fast-list over FUSE traversal).
  - Optional POSIX-like access via mounts managed safely from Settings.

phases:
  - id: phase:providers-mvp-multi-source-files/02-rclone-provider
    objective: Feature-flagged RcloneProvider (listremotes, lsjson depth=1, scan metadata-only)
    ship_criteria:
      - API endpoints live; GUI integration on Files page
      - Tests and docs for enabling provider
  - id: phase:providers-mvp-multi-source-files/02b-rclone-docs-and-mount-manager
    objective: Operationalize rclone usage via docs and a Mount Manager MVP
    ship_criteria:
      - Quickstart docs + README snippet
      - Feature-flagged mount manager API/UI with safety rails
      - Optional browse options spec (recursive, max-depth, fast-list)
  - id: phase:future/rclone-config-in-app
    objective: Settings to import/paste rclone.conf and create key-based remotes (no OAuth)
    ship_criteria:
      - Server-side secrets only; RO defaults; health check on save
  - id: phase:future/rclone-oauth
    objective: Guided OAuth for Drive/OneDrive/Dropbox (device code or app-managed)
    ship_criteria:
      - Token storage protection; audit; admin-only enablement

security_considerations:
  - Prefer read-only scopes (e.g., drive.readonly) for discovery; app never issues writes/deletes.
  - Keep rclone.conf outside VCS (e.g., .secrets/), with limited file permissions; optional rclone config password.
  - For mount manager, restrict mountpoints to a safe subtree and validate remotes exist.

performance_notes:
  - Large listings: use rclone lsjson with --recursive and --fast-list; page results in API.
  - Mounts are convenient but slower for enumeration; tune --dir-cache-time and polling when used.

ux_principles:
  - Simple defaults; advanced flags optional.
  - Clear, actionable errors (surface rclone stderr).
  - Status and logs visible for mounts; easy unmount.

links:
  stories:
    - dev/stories/providers-mvp-multi-source-files/story.md
  phases:
    - dev/stories/providers-mvp-multi-source-files/phases/phase-02-rclone-provider.md
    - dev/stories/providers-mvp-multi-source-files/phases/phase-02b-rclone-docs-and-mount-manager.md
  tasks:
    - dev/tasks/providers/mvp/task-rclone-provider.md
    - dev/tasks/providers/mvp/task-rclone-docs-and-readme.md
    - dev/tasks/providers/mvp/task-rclone-mount-manager-mvp.md
    - dev/tasks/providers/mvp/task-rclone-browse-options.md
