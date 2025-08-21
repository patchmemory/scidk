id: task:ui/mvp/rename-extensions-to-interpreters
title: Rename "Extensions" page to "Interpreters" with redirect
status: Done
owner: agent
rice: 3.0
estimate: 0.25d
created: 2025-08-18
updated: 2025-08-21
dor: true
dod:
  - tests
  - docs
  - demo_steps
dependencies: []
tags: [ui]
story: 
phase: 
links:
  cycles: [dev/cycles.md]
  plan: [dev/plans/plan-2025-08-21.md]
  story: []
  phase: []
acceptance:
  - /interpreters route exists and renders
  - /extensions redirects to /interpreters
notes: |
  Derived from dev/ui/mvp/rename-extensions-to-interpreters.md (legacy).
