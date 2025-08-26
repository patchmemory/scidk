id: task:providers/mvp/rclone-provider
title: Feature-flagged RcloneProvider (subprocess-based)
status: In Progress
owner: agent
rice: 4.0
estimate: "2\u20133d"
created: 2025-08-21
updated: 2025-08-21
dor: true
dod:
- tests
- docs
- demo_steps
dependencies: []
tags:
- providers
- rclone
- browse
- scan
story: story:providers-mvp-multi-source-files
phase: phase:providers-mvp-multi-source-files/02-rclone-provider
links:
  cycles:
  - dev/cycles.md
  plan:
  - dev/plans/plan-2025-08-21.md
  story:
  - dev/stories/providers-mvp-multi-source-files/story.md
  phase:
  - dev/stories/providers-mvp-multi-source-files/phases/phase-02-rclone-provider.md
acceptance:
- /api/providers lists rclone when SCIDK_PROVIDERS includes rclone
- /api/provider_roots returns listremotes
- /api/browse and /api/scan work with rclone paths
- Clear errors when rclone not installed or remote not configured
started_at: '2025-08-26T19:36:14Z'
branch: task/task-providers/mvp/rclone-provider