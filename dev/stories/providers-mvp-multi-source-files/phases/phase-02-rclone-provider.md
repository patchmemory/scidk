id: phase:providers-mvp-multi-source-files/02-rclone-provider
story: story:providers-mvp-multi-source-files
order: 2
status: Planned
owner: agent
created: 2025-08-21
updated: 2025-08-21
e2e_objective: Feature-flagged RcloneProvider enabling browse and scan of remotes
acceptance:
  - /api/providers includes rclone when enabled by SCIDK_PROVIDERS
  - /api/provider_roots lists configured remotes
  - /api/browse and /api/scan work with rclone paths; clear errors when rclone unavailable
scope_in: [rclone, browse, scan]
scope_out: [oauth]
selected_tasks:
  - task:providers/mvp/rclone-provider
dependencies: []
demo_checklist:
  - Show rclone in providers list; browse a remote; scan a small remote folder
links:
  cycle: dev/cycles.md
