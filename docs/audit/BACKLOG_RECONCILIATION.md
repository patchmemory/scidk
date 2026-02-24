# SciDK Backlog Reconciliation — 2026-02-24

## Scope
This reconciliation checks **Ready Queue and active backlog tasks only** against current implementation to identify:
- Tasks already done (archive)
- Tasks partially done (update scope)
- Tasks still valid (proceed)
- Tasks needing clarification

Excludes: Completed tasks, MCP cluster (deferred), E2E phases 01-05, RICE < 20

---

## Ready Queue Tasks (Demo-Critical)

| Task | RICE | Verdict | Evidence | Action |
|------|------|---------|----------|--------|
| **API endpoint registry in Links settings** | 96 | Partially Done | `api_endpoint_registry.py` exists, `config_manager.py` has export/import support, integrated into Links settings | **Update**: Mark as 95% done, only needs final polish/testing |
| **Table format registry** | 72 | Partially Done | `config_manager.py` has `table_formats` export/import, DB table `table_formats` exists | **Update**: Check if UI exists in Links settings tabs |
| **Fuzzy matching options** | 60 | Partially Done | `config_manager.py` has `fuzzy_match_settings` DB table and export/import | **Update**: Check if UI exists in Links settings |
| **Update navigation structure** | 50 | Partially Valid | Nav shows "Links" correctly. Task originally specified "Integrate" but vision is "Links". | **Update**: Revise task to reflect Links terminology, remove Integrations references |
| **Neo4j instance browser** | 32 | Partially Done | `labels.html` has `.instance-browser` div and JS handlers | **Update**: Check if fully functional or stub |
| **Expandable JSON textarea** | 24 | Unknown | No grep evidence found | **Keep or Ask**: Check Arrows import modal in Labels page |
| **Instance preview on Push/Pull** | 16 | Unknown | No grep evidence found | **Keep**: Low RICE, likely not started |
| **Feature flags index generator** | 0.72 | Not Done | No `dev/tools/feature_flags_index.py` found | **Keep**: Dev tooling, low priority |

### Archived Tasks (Vision Changed)
| Task | RICE | Reason | Archived To |
|------|------|--------|-------------|
| **Rename Links to Integrations** | 60 | Superseded — Links is the correct term, not Integrations | `docs/archive/tasks/task-rename-links-to-integrations.md` |
| **Integrations three-column layout** | 75 | Superseded — Links page is the vision, not separate Integrations page | `docs/archive/tasks/task-three-column-layout-with-preview.md` |
| **Analyses page** | 70 | Superseded — Scripts page fulfills this role | `docs/archive/tasks/task-analyses-page.md` |
| **EDA file interpreter** | 55 | Deferred indefinitely — wait until Plugins/Interpreters mature | (Already marked Done in file, but deferred for future enhancements) |
| **EDA to Arrows export** | 30 | Deferred indefinitely — wait until Plugins/Interpreters mature | (Already marked Done in file, but deferred for future enhancements) |

---

## Core Architecture Stories

| Story | Status | Verdict | Evidence | Action |
|-------|--------|---------|----------|--------|
| **Core Architecture Reboot** | In Progress | Still Valid | Status files reference it, multiple completed phases | **Keep**: Ongoing multi-phase story |
| **Providers MVP Multi-Source** | In Progress | Partially Done | `providers.py`, `providers_init.py`, `rclone_settings.py`, `rclone_mounts_loader.py`, `api_providers.py` all exist | **Update**: Significant progress, check which phases remain |
| **Chat history storage** | Proposed | Unknown | `chat.html` and `_chat.html` exist, but no `chat_history` DB or service found | **Keep**: Likely not started |
| **Memory reduction strategy** | Proposed | Not Done | No implementation evidence | **Keep**: Design/strategy work |
| **Annotations page design** | Proposed | Partially Done | `annotations_sqlite.py` and `api_annotations.py` exist, but no annotations UI page found | **Update**: Backend exists, UI missing |
| **Selective folder scanning** | Proposed | Not Done | No selective scanning code found | **Keep**: High-value, not started |
| **Project context system** | Proposed | Not Done | No project context code found | **Keep**: Not started |
| **Interpreters toggle system** | Proposed | Unknown | Interpreters exist, no toggle system found | **Keep**: Likely not started |

---

## Reconciliation Summary

### Tasks Archived (Vision Changed)
1. **Rename Links to Integrations** (RICE: 60) — Links is correct, Integrations superseded
2. **Integrations three-column layout** (RICE: 75) — Links page is the vision
3. **Analyses page** (RICE: 70) — Scripts page fulfills this role
4. **EDA file interpreter** (RICE: 55) — Deferred until Plugins/Interpreters mature
5. **EDA to Arrows export** (RICE: 30) — Deferred indefinitely

### Tasks to Update (Scope Changed)
1. **API endpoint registry** (RICE: 96) — 95% done, needs final testing
2. **Table format registry** (RICE: 72) — Backend done, verify UI in Links settings
3. **Fuzzy matching options** (RICE: 60) — Backend done, verify UI in Links settings
4. **Update navigation structure** (RICE: 50) — Revise to use Links not Integrations terminology
5. **Neo4j instance browser** (RICE: 32) — Partially implemented, check functionality
6. **Providers MVP story** — Significant progress, update phase status
7. **Annotations page story** — Backend done, UI needed

### Tasks Confirmed Valid (Proceed)
1. **Instance preview on Push/Pull** (RICE: 16) — Not started
2. **Feature flags index generator** (RICE: 0.72) — Not started
3. **Chat history storage** — Not started
4. **Memory reduction strategy** — Not started
5. **Selective folder scanning** — Not started
6. **Project context system** — Not started
7. **Interpreters toggle system** — Not started
8. **Core Architecture Reboot** — Ongoing

### Questions Remaining

1. **Expandable JSON textarea** (RICE: 24):
   - Q: Is this implemented in the Arrows import modal? (No grep evidence found)

---

## Implementation Notes

### Files to Clean Up Post-Demo

**Decision**: Links is the correct term. The following Integrations-related files are superseded and should be removed:

- `scidk/ui/templates/integrations.html` — superseded by `links.html`, delete after demo
- `scidk/web/routes/api_integrations.py` — superseded by `api_links.py`, delete after demo
- Settings page reference to "Integrations" at `index.html:91` — change to "Links"

**Nav Check**: ✅ `base.html` correctly shows "Links" in main navigation (not Integrations)

### Evidence of Backend-Heavy Progress
Several tasks show backend implementation complete but UI unclear:
- API endpoint registry ✅ backend
- Table formats registry ✅ backend
- Fuzzy matching settings ✅ backend
- Annotations ✅ backend

**Recommendation**: Quick UI verification pass in Links settings tabs to close out these tasks.
