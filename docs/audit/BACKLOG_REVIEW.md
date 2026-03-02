# SciDK Backlog Review — 2026-02-24

## Summary

Total task files reviewed: 150+ across `dev/tasks/`, `dev/status/`, `dev/stories/`

### Status Overview
- **Done/Complete**: ~20 tasks (recent focus on Maps, monitoring, backups, docs, Swagger)
- **In Progress**: 1 task (API endpoint registry in Links settings)
- **Ready**: ~15 tasks (mostly UI enhancements, MCP deferred)
- **Backlog**: ~100+ tasks (selective scanning, plugins, interpreters, annotations, etc.)
- **Blocked**: 0 tasks explicitly marked as blocked

---

## Incomplete / In Progress

| Task | File | Priority | Notes |
|------|------|----------|-------|
| API endpoint registry in Links settings | `task:ui/links/settings-api-endpoints` | RICE: 96 | Started 2026-02-08, nearly complete. Allows users to register API endpoints with auth/JSONPath mapping |

---

## Backlogged (Not Started)

### Ready Queue (Demo-Critical)
| Task | File | Priority | Notes |
|------|------|----------|-------|
| Integrations page three-column layout with preview | `task:ui/integrations/three-column-layout-with-preview` | RICE: 75 | Preview/Existing/Conflicts tabs, pipeline execution |
| Table format registry in Links settings | `task:ui/links/settings-table-formats` | RICE: 72 | CSV/table import configuration |
| Analyses page for database analytics | `task:ui/features/analyses-page` | RICE: 70 | Read-only scripts, results export, 7 built-in analyses |
| Fuzzy matching options in Links settings | `task:ui/links/settings-fuzzy-matching` | RICE: 60 | Algorithm selection for matching |
| Rename Links to Integrations | `task:ui/integrations/rename-links-to-integrations` | RICE: 60 | Terminology refactor across codebase |
| EDA file interpreter | `task:ui/mvp/eda-file-interpreter` | RICE: 55 | Upload/import .eda designs |
| Update navigation structure | `task:ui/navigation/update-navigation-structure` | RICE: 50 | SciDK \| File \| Label \| Integrate \| Map \| Chat |
| Neo4j instance browser on Labels page | `task:ui/labels/neo4j-instance-browser` | RICE: 32 | Data grid CRUD for node instances |
| EDA to Arrows export | `task:ui/mvp/eda-arrows-export` | RICE: 30 | Export button |
| Expandable JSON textarea | `task:ui/labels/expandable-json-textarea` | RICE: 24 | Fullscreen JSON editor in modal |
| Instance preview on Push/Pull buttons | `task:ui/labels/push-pull-instance-preview` | RICE: 16 | Count display |
| Feature flags index generator | `task:ops/mvp/feature-flags-index` | RICE: 0.72 | CLI tool to scan SCIDK_*/NEO4J_* usage |

### MCP Integration (Deferred Post-MVP)
| Task | File | Priority | Notes |
|------|------|----------|-------|
| MCP Server foundation | `task:integrations/mcp/mcp-server-foundation` | RICE: 90 | Read-only tools, health check, graph stats |
| MCP Settings service | `task:integrations/mcp/mcp-settings-service` | RICE: 85 | Database-backed config |
| MCP Query tools | `task:integrations/mcp/mcp-query-tools` | RICE: 80 | PII filtering |
| MCP Settings UI | `task:integrations/mcp/mcp-settings-ui` | RICE: 75 | Settings page tab |
| MCP Audit/compliance | `task:integrations/mcp/mcp-audit-compliance` | RICE: 70 | Logging |
| MCP Docs/testing | `task:integrations/mcp/mcp-docs-testing` | RICE: 65 | E2E tests |

### Core Architecture Stories (In Progress / Proposed)
| Story | File | Status | Notes |
|-------|------|--------|-------|
| Core Architecture Reboot | `story:core-architecture-reboot` | In Progress | rclone + SQLite + RO-Crate |
| Providers MVP Multi-Source | `story:providers-mvp-multi-source-files` | In Progress | TXT/XLSX interpreters |
| Chat history storage | `story:chat-history-storage` | Proposed | Persistence for chat |
| Memory reduction strategy | `story:core-arch:memory-reduction` | Proposed | Optimize memory usage |
| Annotations page design | `story:annotations-page-design` | Proposed | UI for file annotations |
| Selective folder scanning | `story:selective-folder-scanning` | Proposed | Smart folder selection UI |
| Project context system | `story:project-context-system` | Proposed | One-click state management |
| Interpreters toggle system | `story:interpreters-toggle-system` | Proposed | Global/folder/runtime toggles |

### E2E Testing (Phases 01-05)
- Phase 00: Done ✅
- Phase 01: Helpers/dedupe (Backlog)
- Phase 02: Playwright scaffold (Backlog)
- Phase 03: Core flows (Backlog)
- Phase 04: Negatives (Backlog)
- Phase 05: CI/docs (Backlog)

### Major Component Areas (Backlog)
- **Plugins System**: ~12 tasks (instance framework, loader MVP, settings, label discovery/publishing, templates)
- **Interpreters**: ~7 tasks (iPython, streaming refactor, registry metadata, toggles, TXT/XLSX)
- **Annotations**: ~4 tasks (SQLite relationships, REST endpoints, UI, Neo4j sync)
- **Providers/Rclone**: ~5 tasks (provider, mount manager, docs, browse options, host/UI)
- **Selective Folder Scanning**: 7 phases (algorithm → UI → logic → API → core → filters → cache)
- **Research Objects**: ~2 tasks (RO-Crate referenced, ZIP export)
- **Additional UI/UX**: ~20 tasks (browse, search, polling, refactoring, cleanup, progress, chat persistence)

---

## Blocked

| Task | File | Blocker | Notes |
|------|------|---------|-------|
| *(none explicitly marked as blocked)* | - | - | - |

---

## Completed (Reference Only)

### Recent Completions (Feb 2026)
- Maps three-column layout with tabs (RICE: 85)
- Saved maps with filtering (RICE: 82)
- Visualization modes (Schema/Instance/Hybrid) (RICE: 78)
- Backup automation with scheduling (RICE: 30)
- Swagger/OpenAPI documentation (RICE: 28)
- Production documentation suite (RICE: 24)
- Metrics and logging (RICE: 3.0)
- User authentication & RBAC (PR #40)
- Configuration export/import (PR #41)
- Settings modularization (PR #43)
- Session auto-lock (PR #44)
- E2E Phase 00: Contracts/taxonomy (RICE: 999)

### Implementation Status Highlights
- SciDKData universal wrapper architecture (complete, 13/13 tests passing)
- Parameter system for scripts (GUI-driven input, type-safe validation)
- Script validation & plugin architecture (100% complete)
- Phase 2A: Scripts terminology and file-based storage (22/22 tests passing)

---

## Recommended Next Actions

### Top 5 Post-Demo Priorities

1. **Finish API endpoint registry** (RICE: 96, 0.5d remaining) — Close out in-flight work

2. **Integrations three-column layout** (RICE: 75, 2d) — High-impact UI showcase, builds on completed Maps work

3. **Analyses page** (RICE: 70, 1.5d) — Demonstrate read-only analytics capability with 7 built-in scripts

4. **Selective folder scanning story** (7 phases, ~2-4 weeks) — Critical user request, start with algorithm design phase

5. **Complete E2E testing phases 01-03** (Playwright scaffold → core flows, ~1-2 weeks) — Foundation for CI/CD confidence

---

## Notes

- **Phase 2B (Script Categories)**: Simplified approach — category tabs/filters in UI, defer advanced behaviors
- **Phase 2C (API Endpoint Builder)**: Auto-register Flask routes from `scripts/api/` — 2-3d estimate
- **Test Coverage**: Dedicated tracking in MAPS_TEST_COVERAGE.md
- **Documentation**: Production suite complete (DEPLOYMENT, OPERATIONS, TROUBLESHOOTING, API, SECURITY, ARCHITECTURE)
