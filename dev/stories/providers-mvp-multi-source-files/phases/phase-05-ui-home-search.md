id: phase:providers-mvp-ui-home-search
Title: UI Home Search and Filters
status: In progress
owner: agent
created: 2025-08-21
updated: 2025-08-26
objective: Provide Home page quick search over scanned sources with provider/path/recursive filters.
scope:
  - Home page search/filter UI bound to /api/search
  - Provider selector, path substring input, recursive toggle
  - Uses session data; persistence out of scope
links:
  story: dev/stories/providers-mvp-multi-source-files/story.md
  features: [dev/features/ui/feature-files-page-and-scanned-sources.md]
notes:
  - Keep implementation minimal to satisfy acceptance; polish later.
