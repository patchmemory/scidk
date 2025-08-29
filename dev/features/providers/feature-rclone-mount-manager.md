id: feature:providers/rclone-mount-manager
title: Rclone Mount Manager (Settings)
status: Draft
owner: agent
created: 2025-08-28
updated: 2025-08-28
goal: Enable users to start/stop/monitor rclone mounts safely from the app.
scope:
  - Feature-flagged API: list/start/stop/tail/health for mounts managed under ./data/mounts
  - Settings UI: New Mount form (Remote, Subpath, Name, Read-only), Mounts table (status, actions)
  - Safety rails: restrict mountpoints to app directory, validate remotes via listremotes
out_of_scope:
  - Credential management (covered by future rclone config import)
  - Cross-platform deep integration (Windows cmount nuances documented but not fully automated)
success_metrics:
  - Start/Stop works reliably on Linux/macOS; logs visible; health returns OK
links:
  stories: [story:providers-mvp-multi-source-files]
  phases: [phase:providers-mvp-multi-source-files/02b-rclone-docs-and-mount-manager]
  tasks:
    - task:providers/mvp/rclone-mount-manager-mvp
notes: |
  Default to read-only; require explicit toggle for RW. Expose common flags: --dir-cache-time, --poll-interval, --vfs-cache-mode.
