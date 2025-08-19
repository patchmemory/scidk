# Task: Plugin Loader + PubMed Stub (MVP)

## Metadata
- ID: task:plugins/mvp/loader
- Vision: vision:plugins
- Phase: phase:plugins/mvp
- Status: planned
- Priority: P1
- Owner: agent
- Created: 2025-08-18
- ETA: 2025-09-06
- Labels: [plugins, extensibility]

## Goal
Implement a minimal plugin loader that can discover and register plugins (in-process), and ship a simple PubMed stub plugin exposing a handle_query endpoint that returns placeholder results.

## Requirements
- Plugin interface (MVP):
  - metadata(): id, name, version, category
  - register(app): optional hooks to add routes or commands
  - handle_query(query: str, context: dict) -> dict (optional)
- Loader discovers plugins from a local registry list (config or hard-coded MVP) and imports them.
- PubMed stub plugin:
  - Returns 2–3 hardcoded papers for a query string.
  - Exposes minimal route /api/plugins/pubmed/search for testing.
- UI exposure (MVP): list registered plugins on /plugins page (already scaffolded) with id and name.

## Plan
1. Define Plugin interface and Loader in core or plugins package.
2. Add a built-in stub plugin (pubmed) under scidk/plugins/pubmed_stub.py.
3. Integrate Loader in app startup; show registry on /plugins page.
4. Add simple API route to call pubmed stub for smoke test.
5. Document usage in dev/plugins.md and link to this task.

## DoD
- /plugins shows at least one plugin (PubMed Stub) with id and name.
- /api/plugins/pubmed/search?q=lung returns placeholder JSON.
- Minimal code-level interface documented; future external plugin loading deferred.

## Risks
- API churn → keep interface minimal and versioned in docs.

## Progress Log
- 2025-08-18: Drafted task; scheduled for upcoming cycle.
