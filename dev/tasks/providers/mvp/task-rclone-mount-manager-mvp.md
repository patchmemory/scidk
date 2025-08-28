id: task:providers/mvp/rclone-mount-manager-mvp
title: Settings → Rclone Mount Manager (MVP)
status: Ready
owner: agent
rice: 3.9
estimate: 1–2d
created: 2025-08-28
updated: 2025-08-28
dor: true
dod:
- feature_flagged
- api_endpoints
- basic_ui
- safety_guardrails
- logs_access
- demo_steps
dependencies:
- task:providers/mvp/rclone-provider
tags:
- providers
- rclone
- mounts
- ui
- ops
story: story:providers-mvp-multi-source-files
phase: phase:providers-mvp-multi-source-files/02b-rclone-docs-and-mount-manager
links:
  story:
  - dev/stories/providers-mvp-multi-source-files/story.md
  phases:
  - dev/stories/providers-mvp-multi-source-files/phases/phase-02b-rclone-docs-and-mount-manager.md
acceptance:
- API exists under feature flag to manage mounts:
  - GET /api/rclone/mounts → list managed mounts
  - POST /api/rclone/mounts { remote, subpath, name, read_only } → start mount under ./data/mounts/<name>
  - DELETE /api/rclone/mounts/<id> → unmount
  - GET /api/rclone/mounts/<id>/logs?tail=N → tail
  - GET /api/rclone/mounts/<id>/health → process alive + path listable
- UI (Settings → Rclone) with New Mount form and Mounts table; RO default, RW explicit.
- Safety: restrict mountpoint to ./data/mounts; validate remote via listremotes.
- Works on Linux/macOS; docs note Windows differences (cmount/WinFsp).
demo_steps:
- Enable feature flag and start app.
- Create a mount for an existing remote; verify it appears and logs tail works.
- Unmount via UI and confirm path is unmounted.
