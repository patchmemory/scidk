id: task:interpreters/mvp/ipynb-interpreter
title: IPYNB Interpreter (summary)
status: Done
owner: agent
rice: 3.4
estimate: "1\u20132d"
created: 2025-08-21
updated: 2025-08-21
dor: true
dod:
- tests
- docs
- demo_steps
dependencies: []
tags:
- interpreters
- ipynb
story: story:interpreter-expansion
phase: interpreter-expansion/00-ipynb
links:
  cycles:
  - dev/cycles.md
  plan:
  - dev/plans/plan-2025-08-21.md
  story: []
  phase: []
acceptance:
- Maps .ipynb to summary with cell counts and metadata
- Handles large notebooks by size cap
notes: Derived from dev/interpreters/mvp/ipynb-interpreter.md (legacy).
started_at: '2025-08-26T19:12:07Z'
branch: task/task-interpreters/mvp/ipynb-interpreter
completed_at: '2025-08-26T19:12:39Z'
tests_passed: true