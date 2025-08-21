id: feature:ui/files-page-and-scanned-sources
title: Files page and Scanned Sources UX
status: Draft
owner: agent
created: 2025-08-21
updated: 2025-08-21
goal: Provide a clear Files experience with provider browsing and scanning; Home shows Scanned Sources.
scope:
  - Files page with provider selector, roots, browser table, and Scan panel
  - Home page Scanned Sources list with provider badges
  - Dataset detail shows provider badge and display_path
out_of_scope:
  - Advanced UI polish (drag/drop, breadcrumbs API)
  - Background scan progress (tracked as a task)
success_metrics:
  - User can browse Local/Mounted and scan a directory; sources appear on Home
links:
  stories: [story:providers-mvp-multi-source-files]
  tasks: [task:ui/mvp/tasks-ui-polling, task:ui/mvp/home-search-ui]
