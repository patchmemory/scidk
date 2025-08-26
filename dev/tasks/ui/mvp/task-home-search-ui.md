id: task:ui/mvp/home-search-ui
title: Home search UI (quick filter over scanned sources)
status: Done
owner: agent
rice: 3.8
estimate: "0.5\u20131d"
created: 2025-08-21
updated: 2025-08-21
dor: true
dod:
- tests
- docs
- demo_steps
dependencies: []
tags:
- ui
- home
- search
story: story:providers-mvp-multi-source-files
phase: phase:providers-mvp-multi-source-files/00-contracts-local-mounted
links:
  cycles:
  - dev/cycles.md
  plan: []
  story:
  - dev/stories/providers-mvp-multi-source-files/story.md
  phase:
  - dev/stories/providers-mvp-multi-source-files/phases/phase-00-contracts-local-mounted.md
acceptance:
- Home page supports filtering by provider, path substring, recursive flag
- Works on session data and (later) persisted source registry
started_at: '2025-08-22T16:05:15Z'
branch: task/task-ui/mvp/home-search-ui
completed_at: '2025-08-22T16:07:02Z'
tests_passed: true