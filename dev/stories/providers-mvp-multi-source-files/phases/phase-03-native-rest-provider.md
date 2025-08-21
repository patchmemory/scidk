id: phase:providers-mvp-multi-source-files/03-native-rest-provider
story: story:providers-mvp-multi-source-files
order: 3
status: Planned
owner: agent
created: 2025-08-21
updated: 2025-08-21
e2e_objective: Add one native REST provider (Dropbox/GDrive/Office365) with browse and scan
acceptance:
  - OAuth helper available (Auth Code + PKCE) and basic connect flow
  - Browse and scan functional for one provider; provider_ref stored
scope_in: [oauth, rest-provider]
scope_out: [background-jobs]
selected_tasks: []
dependencies: []
demo_checklist:
  - Connect account; browse; scan and view datasets with provider badge
links:
  cycle: dev/cycles.md
