id: task:core-architecture/mvp/tests-hardening
title: Tests hardening for search and scan flows
status: Ready
owner: agent
rice: 1.5
estimate: 0.5–1d
created: 2025-08-21
updated: 2025-08-21
dor: true
dod:
  - tests
  - docs
  - demo_steps
dependencies: []
tags: [tests, api]
story: 
phase: 
links:
  cycles: [dev/cycles.md]
  plan: [dev/plans/plan-2025-08-21.md]
  story: []
  phase: []
acceptance:
  - Add focused tests for /api/search (filename and interpreter matches, empty results)
  - Verify idempotent scan behavior and edge cases
notes: |
  Derived from dev/core-architecture/mvp/tests-hardening.md (legacy).
