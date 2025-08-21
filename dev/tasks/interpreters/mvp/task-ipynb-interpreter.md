id: task:interpreters/mvp/ipynb-interpreter
title: IPYNB Interpreter (summary)
status: Ready
owner: agent
rice: 3.4
estimate: 1–2d
created: 2025-08-21
updated: 2025-08-21
dor: true
dod:
  - tests
  - docs
  - demo_steps
dependencies: []
tags: [interpreters, ipynb]
story: 
phase: 
links:
  cycles: [dev/cycles.md]
  plan: [dev/plans/plan-2025-08-21.md]
  story: []
  phase: []
acceptance:
  - Maps .ipynb to summary with cell counts and metadata
  - Handles large notebooks by size cap
notes: |
  Derived from dev/interpreters/mvp/ipynb-interpreter.md (legacy).
