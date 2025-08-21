id: phase:providers-mvp-multi-source-files/00-contracts-local-mounted
story: story:providers-mvp-multi-source-files
order: 0
status: Done
owner: agent
created: 2025-08-20
updated: 2025-08-21
e2e_objective: Provider SDK + Local and Mounted browsing and scanning
acceptance:
  - ProviderRegistry and FilesystemProvider interface implemented
  - LocalFS and MountedFS providers work via /api/providers, /api/browse, /api/scan
  - UI File page shows provider selector and browser; Home shows Scanned Sources
scope_in: [registry, local, mounted, browse, scan]
scope_out: [oauth]
selected_tasks: []
dependencies: []
demo_checklist:
  - Start app and browse Local and Mounted
  - Scan a mounted path; show in Home Scanned Sources
links:
  cycle: dev/cycles.md
