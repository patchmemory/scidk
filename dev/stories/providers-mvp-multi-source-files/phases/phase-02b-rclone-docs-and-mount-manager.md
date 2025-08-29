id: phase:providers-mvp-multi-source-files/02b-rclone-docs-and-mount-manager
story: story:providers-mvp-multi-source-files
order: 2.1
status: Planned
owner: agent
created: 2025-08-28
updated: 2025-08-28
e2e_objective: Rclone documentation + Mount Manager MVP to operationalize rclone usage in GUI and CLI
acceptance:
  - README-ready quickstart and troubleshooting
  - In-app (or CLI) mount management MVP behind a feature flag
  - Optional browse options (recursive/fast-list) spec’ed and tasks linked
scope_in: [docs, rclone, mounts, browse-options]
scope_out: [oauth, secret-vault]
selected_tasks:
  - task:providers/mvp/rclone-docs-and-readme
  - task:providers/mvp/rclone-mount-manager-mvp
  - task:providers/mvp/rclone-browse-options
dependencies:
  - phase:providers-mvp-multi-source-files/02-rclone-provider
demo_checklist:
  - Show the quickstart working for Google Drive
  - Start/stop a mount from the app/CLI and tail logs
  - Demonstrate browse with recursive/fast-list options (if implemented in this phase)
links:
  cycle: dev/cycles.md
