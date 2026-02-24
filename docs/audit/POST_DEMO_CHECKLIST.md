# Post-Demo Cleanup Checklist

## Code Cleanup
- [ ] Delete `scidk/web/routes/api_integrations.py` (superseded by api_links.py)
- [ ] Delete archived templates in `scidk/ui/templates/_archive/` after confirming no breakage
- [ ] Remove `index_old_home.html` from `_archive/` if truly obsolete

## Settings Terminology
- [ ] Keep "Integrations" as settings section name (correct — refers to API/table/fuzzy integrations for Links)
- [ ] No changes needed — terminology is consistent

## Backlog Tasks Status — Verified 2026-02-24

### ✅ Complete (Close Tasks)
- **API endpoint registry** (RICE: 96) — Full UI exists in settings/_integrations.html with:
  - Add/edit/delete endpoints
  - Test connection button
  - Encrypted auth storage
  - Field mappings to Labels
  - Plugin-registered endpoints view

- **Table format registry** (RICE: 72) — Full UI exists in settings/_integrations.html with:
  - Add custom formats (CSV/TSV/Excel/Parquet)
  - Delimiter, encoding, target label configuration
  - List of registered formats

- **Fuzzy matching options** (RICE: 60) — Full UI exists in settings/_integrations.html with:
  - Phase 1 (client-side rapidfuzz) settings
  - Phase 2 (server-side Neo4j APOC) settings
  - Algorithm selection

### ⚠️ Partial (Needs Completion)
- **Neo4j instance browser** (RICE: 32) — Stub exists in labels.html:
  - Div structure present (`.instance-browser` at line 520)
  - Show/hide logic exists
  - ❓ **Verify**: Is data grid/CRUD functional or just placeholder?

### ✅ Valid (Not Started)
- **Instance preview on Push/Pull** (RICE: 16) — Not started, low priority
- **Expandable JSON textarea** (RICE: 24) — Unknown status
- **Feature flags index generator** (RICE: 0.72) — Not started, dev tooling

## Architecture
- [ ] Remove `/integrations` route from `ui.py` if confirmed dead
- [ ] Run full E2E test suite against demo data
- [ ] Verify all links in navigation work post-cleanup

## Task Files to Update
- [ ] Mark `task:ui/links/settings-api-endpoints` as **Done** (was In Progress)
- [ ] Mark `task:ui/links/settings-table-formats` as **Done** (was Ready)
- [ ] Mark `task:ui/links/settings-fuzzy-matching` as **Done** (was Ready)
- [ ] Update `dev/tasks/index.md` to remove completed tasks from Ready Queue

## Findings Summary

**Good News**: Three "Ready Queue" tasks (RICE 60-96) are actually **complete** with full UI implementations in the settings/_integrations.html panel. They were marked as Ready/In Progress but the work is done.

**Action**: Close out these tasks immediately post-demo to clean up the backlog.
