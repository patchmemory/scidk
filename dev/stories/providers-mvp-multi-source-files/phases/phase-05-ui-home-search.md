id: phase:providers-mvp-ui-home-search
Title: UI Home Search and Filters
status: Done
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
demo_steps:
  - Start app: python -m scidk.app and open http://localhost:5000/
  - Go to Files page and run a scan on a directory (choose recursive or not)
  - Return to Home page: expand "Scanned Sources"
  - Use filters: select Provider, type a path substring, toggle Recursive selector
  - Observe list updates instantly client-side; items show provider badge and recursive flag
  - Optional: Use Search section to query filenames or interpreter ids
