id: story:providers-mvp-multi-source-files
title: MVP Multi-Provider Files + TXT/XLSX Interpreters
status: In progress
owner: agent
created: 2025-08-20
updated: 2025-08-21
success: Files page supports Local and Mounted providers; TXT/XLSX interpreters; groundwork for cloud providers via plugin SDK
scope_in: [providers, browse, scan, txt, xlsx]
scope_out: [oauth, persistence, advanced ui]
links:
  phases:
    - dev/stories/providers-mvp-multi-source-files/phases/phase-00-contracts-local-mounted.md
    - dev/stories/providers-mvp-multi-source-files/phases/phase-01-txt-xlsx-interpreters.md
    - dev/stories/providers-mvp-multi-source-files/phases/phase-02-rclone-provider.md
    - dev/stories/providers-mvp-multi-source-files/phases/phase-02b-rclone-docs-and-mount-manager.md
    - dev/stories/providers-mvp-multi-source-files/phases/phase-03-native-rest-provider.md
    - dev/stories/providers-mvp-multi-source-files/phases/phase-04-globus-stub.md
  related_features:
    - dev/features/providers/feature-provider-registry-and-interface.md
    - dev/features/ui/feature-files-page-and-scanned-sources.md
  cycles: [dev/cycles.md]

Narrative
- Unify browsing and scanning for multiple providers. Adopt Rclone as a pragmatic bridge for many clouds. Keep GUI-first milestones per phase and link tasks from a central backlog.
