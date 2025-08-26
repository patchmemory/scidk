id: task:ui/mvp/home-search-ui
title: Home search UI (quick filter over scanned sources)
status: Ready
owner: agent
rice: 3.8
estimate: 0.5–1d
created: 2025-08-21
updated: 2025-08-21
dor: true
dod:
  - tests
  - docs
  - demo_steps
dependencies: []
tags: [ui, home, search]
story: story:providers-mvp-multi-source-files
phase: phase:providers-mvp-ui-home-search
links:
  cycles: [dev/cycles.md]
  plan: []
  story: [dev/stories/providers-mvp-multi-source-files/story.md]
  phase: [dev/stories/providers-mvp-multi-source-files/phases/phase-05-ui-home-search.md]
acceptance:
  - Home page supports filtering by provider, path substring, recursive flag
  - Works on session data and (later) persisted source registry
