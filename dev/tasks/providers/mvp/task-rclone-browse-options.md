id: task:providers/mvp/rclone-browse-options
title: Rclone browse options (recursive, max-depth, fast-list)
status: Ready
owner: agent
rice: 3.4
estimate: 0.5–1d
created: 2025-08-28
updated: 2025-08-28
dor: true
dod:
- api_flags_added
- ui_controls
- provider_support
- docs_updated
dependencies:
- task:providers/mvp/rclone-provider
tags:
- providers
- rclone
- browse
- performance
story: story:providers-mvp-multi-source-files
phase: phase:providers-mvp-multi-source-files/02b-rclone-docs-and-mount-manager
links:
  story:
  - dev/stories/providers-mvp-multi-source-files/story.md
  phases:
  - dev/stories/providers-mvp-multi-source-files/phases/phase-02b-rclone-docs-and-mount-manager.md
acceptance:
- API /api/browse accepts recursive=true/false, max_depth=N, fast_list=true/false for provider_id=rclone.
- Provider uses rclone lsjson flags accordingly and handles providers that don’t support fast-list.
- UI exposes checkboxes/inputs and passes through to API; defaults remain safe (non-recursive, depth=1).
- Docs describe tradeoffs and recommend direct listing for large trees.
