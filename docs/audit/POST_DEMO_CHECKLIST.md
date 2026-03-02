# Post-Demo Cleanup Checklist

## Immediate (Week After Demo)
- [ ] Close completed tasks: API endpoint registry, table formats, fuzzy matching
- [ ] Delete `scidk/web/routes/api_integrations.py` (deprecated, superseded by api_links.py)
- [ ] Remove archived templates in `scidk/ui/templates/_archive/` after confirming no breakage
- [ ] Verify Neo4j instance browser is functional or scope the remaining work

## Backlog Tasks to Update
- [x] Update `dev/tasks/ui/links/task-links-settings-api-endpoints.md` → Done (2026-02-24)
- [x] Update `dev/tasks/ui/links/task-links-settings-table-formats.md` → Done (2026-02-24)
- [x] Update `dev/tasks/ui/links/task-links-settings-fuzzy-matching.md` → Done (2026-02-24)
- [ ] Update `dev/tasks/index.md` to remove completed tasks from Ready Queue

## Architecture (Post-Demo Sprint)
- [ ] GPU detection in health check → model recommendations in Chat settings
- [ ] Chat provider switching UI (Ollama, Claude, OpenAI)
- [ ] Wire `chat_service.py` to local LLM provider
- [ ] Query library UI in Chat (view/edit/save queries from responses)
- [ ] Remove `/integrations` route from `ui.py` after confirming dead
- [ ] Run full E2E test suite against demo datasets

## Terminology
- [x] Audit settings tabs for any remaining Integrations/Links confusion (2026-02-24: confirmed correct)
- [ ] Update FEATURE_INDEX.md with current page inventory

## Demo Week Priorities (Before Demo)
- [ ] Chat — local Ollama provider connected and tested on workstation
- [ ] Results/Scripts — end to end verification with Dataset 1
- [ ] Docker Compose — three Neo4j containers for dataset switching
- [ ] Full run-through of Dataset 1 demo flow, timed

## Completed Today (2026-02-24)
- [x] Backlog reconciliation audit (150+ task files reviewed)
- [x] Archive superseded tasks (rename to Integrations, Analyses page, EDA)
- [x] Archive dead templates (integrations.html, map_backup.html, map_v2.html)
- [x] Verify three high-RICE tasks complete (API endpoints, table formats, fuzzy matching)
- [x] Terminology decision documented (Links page vs Integrations settings)
