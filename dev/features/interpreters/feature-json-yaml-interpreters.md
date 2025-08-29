id: feature:interpreters/json-yaml-interpreters
title: JSON and YAML Interpreters
status: Draft
owner: agent
created: 2025-08-21
updated: 2025-08-21
goal: Provide basic summaries for .json and .yaml files in dataset detail.
scope:
  - JsonInterpreter with top-level keys/preview
  - YamlInterpreter with top-level keys/preview (graceful when PyYAML missing)
out_of_scope:
  - Advanced schema inference
success_metrics:
  - Datasets with these extensions show summaries reliably
links:
  stories: [story:providers-mvp-multi-source-files]
  tasks: []
notes: |
  Source reference docs: dev/interpreters/mvp/json-yaml-interpreters.md and dev/interpreters/mvp/json-yaml.md (legacy).
