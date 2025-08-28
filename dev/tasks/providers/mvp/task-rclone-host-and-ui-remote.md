id: task:providers/mvp/rclone-host-and-ui-remote
title: Host/provider tagging + Rclone Files UI (Remote + relative path)
status: Ready
owner: agent
rice: 3.7
estimate: 0.5–1d
created: 2025-08-28
updated: 2025-08-28
dor: true
dod:
- host_fields_on_nodes
- remote_path_utils
- ui_remote_relative
- neo4j_props_set
- demo_steps
dependencies:
- task:providers/mvp/rclone-provider
tags:
- providers
- rclone
- ui
- graph
story: story:providers-mvp-multi-source-files
phase: phase:providers-mvp-multi-source-files/02b-rclone-docs-and-mount-manager
links:
  story:
  - dev/stories/providers-mvp-multi-source-files/story.md
  phases:
  - dev/stories/providers-mvp-multi-source-files/phases/phase-02b-rclone-docs-and-mount-manager.md
acceptance:
- File/Folder/Scan carry provider_id, host_type, host_id; rclone sets host_id = rclone:<remote_name>.
- Central path utils handle remote paths: parse_remote_path, join_remote_path, parent_remote_path.
- Rclone scan uses join_remote_path to build folder entries; commit uses parent_remote_path for Folder nodes and CONTAINS edges; no Folder(path='.') created.
- Files page (rclone): label Root→Remote; Path is relative; client composes full path safely; no duplicate prefixes.
- Demo on Google Drive shows correct Folder nodes; Neo4j commit yields CONTAINS edges from remote root → first-level folders and to files.
demo_steps:
- Enable rclone: export SCIDK_PROVIDERS=local_fs,mounted_fs,rclone; start app.
- GUI: Files → Provider=Rclone Remotes → Remote=mit-google → Path="" → Go (remote root). Verify folders/files.
- Scan non-recursive; Commit to graph; verify Folder nodes for remote root and first-level, and CONTAINS edges in Neo4j.
