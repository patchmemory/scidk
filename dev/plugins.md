# Plugins

## Vision Summary
- ID: vision:plugins
- Owner: Extensions Team
- Last Updated: 2025-08-21
- Related Docs: dev/vision/plugins.md

## Problem & Value
- Problem: Researchers need major feature extensions (literature, LIMS, scheduling) without bloating core.
- Value: Extensible platform that can add substantial capabilities via plugins with UI and API.

## Scope (In / Out)
- In: Plugin base, loader, registration hooks, route registration, basic handle_query.
- Out: Full-featured plugin marketplace and permissioning (later phases).

Provider plugins: Filesystem Providers (Local, Mounted, planned Rclone) are implemented via a pluggable ProviderRegistry. Future plugins can adopt a similar registration pattern and capability declaration.

## Phases
- [phase:plugins/mvp] Plugin Loader + PubMed Stub — Status: planned, Target: 2025-09-20

## Risks & Mitigations
- Risk: Plugin API churn → Mitigation: stabilize minimal interface and version it.

## Open Questions
- Should plugins be isolated processes vs. in-process modules at MVP?
