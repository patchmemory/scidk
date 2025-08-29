id: task:providers/mvp/rclone-docs-and-readme
title: Rclone Quickstart Docs + README-ready Snippet
status: Ready
owner: agent
rice: 3.6
estimate: 0.5–1d
created: 2025-08-28
updated: 2025-08-28
dor: true
dod:
- docs_added
- instructions_verified
- links_in_story
- demo_steps
dependencies:
- task:providers/mvp/rclone-provider
tags:
- providers
- rclone
- docs
- readme
story: story:providers-mvp-multi-source-files
phase: phase:providers-mvp-multi-source-files/02b-rclone-docs-and-mount-manager
links:
  story:
  - dev/stories/providers-mvp-multi-source-files/story.md
  phases:
  - dev/stories/providers-mvp-multi-source-files/phases/phase-02b-rclone-docs-and-mount-manager.md
  features:
  - dev/features/providers/feature-provider-registry-and-interface.md
acceptance:
- A README-ready snippet exists covering enabling rclone provider, GUI usage, and API endpoints.
- Quickstart covers installing rclone, configuring popular providers (Drive/Dropbox/S3), verification commands, and troubleshooting.
- Docs explain both direct Rclone provider flow and optional FUSE mount flow with safe defaults.
- Links to systemd template and mount commands are provided in dev/ (not necessarily in README yet).
demo_steps:
- Follow the quickstart to configure one remote (e.g., Google Drive) and verify with `rclone ls`.
- Enable provider (SCIDK_PROVIDERS=local_fs,mounted_fs,rclone) and browse/scan in GUI.
- Optionally mount remote read-only under data/ and scan via Local Filesystem provider.
