id: feature:providers/provider-registry-and-interface
title: Provider Registry and Filesystem Provider Interface
status: Draft
owner: agent
created: 2025-08-21
updated: 2025-08-21
goal: Define a stable provider SDK to support Local, Mounted, and future cloud providers.
scope:
  - ProviderDescriptor and FilesystemProvider contracts
  - ProviderRegistry with feature flags
  - Minimal browse/scan API contracts
out_of_scope:
  - OAuth flows (covered in native REST provider feature)
  - Background jobs
success_metrics:
  - Providers can be swapped at runtime via flag
  - UI and API remain stable across providers
links:
  stories: [story:providers-mvp-multi-source-files]
  tasks: [task:providers/mvp/rclone-provider]
notes: |
  See dev/stories/providers-mvp-multi-source-files/story.md and phases for staged delivery.
