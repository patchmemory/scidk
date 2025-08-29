id: feature:interpreters/interpreter-registry-and-executor
title: Interpreter Registry and Executor
status: Draft
owner: agent
created: 2025-08-21
updated: 2025-08-21
goal: Provide a pluggable interpreter registry and safe executor.
scope:
  - Registration of interpreters and mapping rules
  - Executor with timeouts and caps
  - Integration with scan pipeline
out_of_scope:
  - Multi-runtime isolation beyond MVP
success_metrics:
  - Interpreters are registered and executed safely with predictable outputs
links:
  stories: [story:providers-mvp-multi-source-files]
  tasks: []
notes: |
  Source reference doc: dev/interpreters/mvp/registry-and-executor.md (legacy).