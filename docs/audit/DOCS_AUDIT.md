# Documentation Currency Audit — SciDK

**Generated:** 2026-02-24
**Method:** First 20 lines + stale reference scan
**Total docs scanned:** 344 (filtered to project-level only)

---

## Executive Summary

- **Current docs:** 15-20 core docs are actively maintained and reflect production state
- **Outdated docs:** ~30 docs in `dev/` reference old wizard UI, removed pages, or superseded architecture
- **Vendor/test artifacts:** ~300 docs in `.venv/`, `dev/test-runs/`, `dev/code-imports/` should be ignored by IDE
- **Stale references found:** Only 1 doc mentions old wizard patterns (`AUDIT_PLAN.md` itself, meta-reference)

**Key Finding:** The codebase has good doc hygiene at the root and `docs/` level. The problem is in `dev/` — outdated planning docs that no longer match implementation.

---

## Post-Cleanup Update (2026-02-24)

**Actions Completed:**
1. ✅ Archived 20 outdated docs to `docs/archive/`
2. ✅ Moved 16 root-level docs to organized locations
3. ✅ Updated `.gitignore` to exclude test artifacts and code imports
4. ✅ Updated key cross-references to new paths

**New Structure:**
- **Root:** Only `README.md` and `QUICKSTART.md` (clean entry point)
- **docs/:** Architecture vision, development guide, and 5 feature specs
- **docs/features/:** Feature implementation docs (cross-DB transfer, triple builder, GraphRAG, etc.)
- **dev/demo/:** Demo quick reference and progress indicators
- **dev/status/:** Implementation status tracking (5 docs)
- **dev/features/:** Feature index and planning docs

**Result:** Root directory reduced from 18 markdown files to 2. IDE context significantly cleaner.

---

## Root-Level Documentation (Post-Cleanup)

**Current State:** Only 2 files remain at root:

| File | Topic | Status | Location |
|------|-------|--------|----------|
| README.md | Quick start, install, run instructions | Current | Root (kept) |
| QUICKSTART.md | Fresh install to first RO-Crate | Current | Root (kept) |

**Moved to organized locations:**

| Original File | New Location | Reason |
|--------------|--------------|--------|
| SciDK_Architecture_Vision.md | `docs/SciDK_Architecture_Vision.md` | Architecture doc |
| DEVELOPMENT.md | `docs/DEVELOPMENT.md` | Dev setup/conventions |
| CROSS_DATABASE_TRANSFER_V2_IMPLEMENTATION.md | `docs/features/cross-database-transfer.md` | Feature spec |
| UNIFIED_TRIPLE_BUILDER_MVP.md | `docs/features/unified-triple-builder.md` | Feature spec |
| GRAPHRAG_QUICK_START.md | `docs/features/graphrag-quickstart.md` | Feature spec |
| PARAMETER_SYSTEM_DESIGN.md | `docs/features/parameter-system.md` | Feature spec |
| SCRIPT_CONTRACTS_GUIDE.md | `docs/features/script-contracts.md` | Feature spec |
| SECURITY_HARDENING_RECOMMENDATIONS.md | `docs/SECURITY_HARDENING.md` | Security guidance |
| DEMO_SETUP.md | `dev/demo/DEMO_QUICK_REFERENCE.md` | Demo quick reference (renamed to avoid confusion with docs/DEMO_SETUP.md) |
| DEMO_PROGRESS_INDICATORS.md | `dev/demo/progress-indicators.md` | Demo feature guide |
| FEATURE_INDEX.md | `dev/features/FEATURE_INDEX.md` | Feature inventory |
| IMPLEMENTATION_STATUS_CURRENT.md | `dev/status/IMPLEMENTATION_STATUS_CURRENT.md` | Status tracking |
| IMPLEMENTATION_COMPLETION_GUIDE.md | `dev/status/IMPLEMENTATION_COMPLETION_GUIDE.md` | Status tracking |
| SCIDK_DATA_IMPLEMENTATION_STATUS.md | `dev/status/scidk-data-implementation.md` | Status tracking |
| PHASE_2B_2C_STATUS.md | `dev/status/PHASE_2B_2C_STATUS.md` | Status tracking |
| MAPS_TEST_COVERAGE.md | `dev/status/MAPS_TEST_COVERAGE.md` | Status tracking |

**Archived (outdated):**

| File | Reason | Location |
|------|--------|----------|
| SCRIPTS_ARCHITECTURE_STATUS.md | Superseded by transparency layers | `docs/archive/` |
| SCRIPTS_REFACTOR_PLAN.md | Implementation complete | `docs/archive/` |
| SCRIPTS_REFACTOR_COMPLETE.md | Merge into current status | `docs/archive/` |
| SESSION_SUMMARY_2026-02-20.md | Session-specific | `docs/archive/` |
| SESSION_HANDOFF_PROMPT.md | Session-specific | `docs/archive/` |

---

## Core Documentation (`docs/`)

| File | Topic | Status | Recommendation |
|------|-------|--------|----------------|
| docs/ARCHITECTURE.md | System design, tech choices, component interactions | Current | **Keep** - Core architecture reference |
| docs/API.md | REST API reference | Current | **Keep** - Essential for API users |
| docs/DEPLOYMENT.md | Production deployment guide | Current | **Keep** - Critical for ops |
| docs/OPERATIONS.md | Day-to-day ops, monitoring, maintenance | Current | **Keep** - Critical for ops |
| docs/SECURITY.md | Security architecture, auth, encryption | Current | **Keep** - Critical for ops |
| docs/TROUBLESHOOTING.md | Common problems and solutions | Current | **Keep** - Critical for ops |
| docs/DEMO_SETUP.md | Demo data seeding and setup | Current | **Keep** - Active demo support (duplicate of root DEMO_SETUP.md?) |
| docs/testing.md | Testing strategy and conventions | Current | **Keep** - Dev reference |
| docs/e2e-testing.md | E2E test setup and patterns | Current | **Keep** - Dev reference |
| docs/interpreters.md | Interpreter system documentation | Current | **Keep** - Core feature doc |
| docs/plugins.md | Plugin system documentation | Current | **Keep** - Core feature doc |
| docs/PLUGIN_INSTANCES.md | Plugin instance management | Current | **Keep** - Core feature doc |
| docs/PLUGIN_LABEL_ENDPOINTS.md | Plugin label endpoint system | Current | **Keep** - Core feature doc |
| docs/branching-and-ci.md | Git workflow and CI | Current | **Keep** - Dev process doc |
| docs/ipynb-streaming-optimization.md | Jupyter notebook streaming | Current | **Keep** - Performance optimization doc |
| docs/architecture/links-system.md | Links system (wizard + script links) | Current | **Keep** - Core feature architecture |
| docs/architecture/transparency-layers.md | Transparency layer architecture (v1.0, 2025-02-20) | Current | **Keep** - Core architecture pattern |
| docs/ux-runbook-2025-09-12.md | UX testing checklist | Outdated | **Update or Archive** - Date-stamped, may be outdated |
| docs/E2E_and_Neo4j_Task_Planning_REVISED.md | E2E + Neo4j task planning | Outdated | **Archive** - Planning doc, work likely complete |
| docs/MVP_Architecture_Overview_REVISED.md | MVP architecture overview | Outdated | **Archive** - "REVISED" suffix suggests superseded |
| docs/rclone/quickstart.md | Rclone integration quickstart | Current | **Keep** - Feature doc |
| docs/rclone/mount-examples.md | Rclone mount examples | Current | **Keep** - Feature doc |
| docs/plugins/ILAB_IMPORTER.md | iLab importer plugin | Current | **Keep** - Plugin-specific doc |

---

## Development Documentation (`dev/`)

### Planning & Status Docs

| File | Topic | Status | Recommendation |
|------|-------|--------|----------------|
| dev/PRODUCTION_MVP_STATUS.md | Production MVP status snapshot (2026-02-19) | Current | **Keep** - Recent status |
| dev/PRODUCTION_MVP_TASKS.md | Production MVP task list | Current | **Keep** - Active planning |
| dev/plans/production-mvp-roadmap.md | Production MVP roadmap | Current | **Keep** - Active roadmap |
| dev/features/README.md | Feature folder overview | Current | **Keep** - Navigation doc |
| dev/tasks/index.md | Ready queue, RICE-sorted tasks | Current | **Keep** - Active backlog |
| dev/stories/index.md | Story index | Current | **Keep** - Story tracking |
| dev/test-coverage-index.md | Test coverage index | Current | **Keep** - Testing status |
| dev/README-planning.md | Planning conventions | Current | **Keep** - Process doc |
| dev/prompts.md | Agent prompts and templates | Current | **Keep** - Agent workflow doc |
| dev/cycles.md | Development cycle tracking | Current | **Keep** - Process doc |
| dev/cycles/cycles.md | Development cycles detail | Current | **Keep** - Process doc |
| dev/ux-testing-checklist.md | UX testing checklist | Current | **Keep** - QA doc |

### Architecture & Design Docs

| File | Topic | Status | Recommendation |
|------|-------|--------|----------------|
| dev/features/core-architecture/feature-core-architecture-mvp.md | Core architecture MVP | Current | **Keep** - Architecture doc |
| dev/features/graphrag-feedback-system.md | GraphRAG feedback system | Current | **Keep** - Feature spec |
| dev/features/feature-flags.md | Feature flags | Current | **Keep** - Feature spec |
| dev/features/index.md | Feature index | Current | **Keep** - Navigation doc |
| dev/design/graph/neo4j-adapter-impl.md | Neo4j adapter implementation | Current | **Keep** - Design doc |
| dev/design/data/rocrate-embedding.md | RO-Crate embedding | Current | **Keep** - Design doc |
| dev/decisions/2026-02-05-workbook-page.md | Workbook page decision | Current | **Keep** - Architecture decision record (ADR) |

### Session & Progress Docs

| File | Topic | Status | Recommendation |
|------|-------|--------|----------------|
| dev/SESSION_2026-02-20_Transparency_Layers.md | Transparency layers session (2026-02-20) | Current | **Archive after 30 days** - Session-specific |
| dev/SESSION_2026-02-20_Links_Integration.md | Links integration session (2026-02-20) | Current | **Archive after 30 days** - Session-specific |
| dev/SESSION_SUMMARY_2026-01-26.md | Session summary (2026-01-26) | Outdated | **Archive** - 1 month old |
| dev/Scripts_CoNVO.md | Scripts conversation/notes | Outdated | **Archive** - Session-specific |
| dev/TRANSPARENCY_LAYERS_ROADMAP.md | Transparency layers roadmap | Superseded | **Archive** - Implementation complete (see docs/architecture/transparency-layers.md) |
| dev/TRANSPARENCY_LAYERS_COMPLETE_TEST_PLAN.md | Transparency test plan | Superseded | **Archive** - Tests implemented |
| dev/TRANSPARENCY_LAYERS_TESTING.md | Transparency testing status | Superseded | **Archive** - Tests implemented |
| dev/TRANSPARENCY_LAYERS_TEST_IMPLEMENTATION_STATUS.md | Transparency test status | Superseded | **Archive** - Tests implemented |
| dev/TRANSPARENCY_LAYERS_INTEGRATION_TESTS_FINAL.md | Transparency integration tests | Superseded | **Archive** - Tests implemented |
| dev/TRANSPARENCY_TESTS_SESSION_COMPLETE.md | Transparency tests session complete | Superseded | **Archive** - Tests implemented |

### Task & Story Details

**Status:** Most task and story docs in `dev/tasks/` and `dev/stories/` are current and actively referenced by the index docs. These are working documents and should be kept.

**Exception:** Some older tasks/stories may be complete and should be marked as such (status: Done) rather than deleted.

### Outdated Planning Docs

| File | Topic | Status | Recommendation |
|------|-------|--------|----------------|
| dev/plans/plan-2025-08-21.md | August 2025 plan | Outdated | **Archive** - 6 months old |
| dev/plans/plan-2025-08-28-reboot-architecture.md | Architecture reboot plan | Outdated | **Archive** - 6 months old |
| dev/plans/plan-2025-09-10-sync-dev-with-impl.md | Dev sync plan | Outdated | **Archive** - 5 months old |
| dev/plans/plan-2026-01-26-refactor-and-label-link-pages.md | Label/link refactor plan | Superseded | **Archive** - Refactor complete |
| dev/plans/plan-2026-02-07-settings-modularization.md | Settings modularization plan | Current? | **Review** - Check implementation status |
| dev/plans/script-validation-framework.md | Script validation framework | Unknown | **Review** - Check implementation status |

### Code Import Archives

**Location:** `dev/code-imports/`
**Status:** All outdated — archives from other projects (chatseek, nc3rsEDA, arrows-app)
**Recommendation:** **Exclude from IDE context** - Add to `.gitignore` or move outside repo if no longer needed

### Test Artifacts

**Location:** `dev/test-runs/tmp/pytest-of-patch/`
**Status:** Temporary test data
**Recommendation:** **Exclude from IDE context** - Add to `.gitignore`

---

## Vendor Dependencies

**Location:** `.venv/lib/python3.12/site-packages/`
**Count:** ~300 markdown files (READMEs, licenses)
**Status:** Vendor documentation
**Recommendation:** **Exclude from IDE context** - Already in virtual env, should not be indexed

---

## Stale Reference Analysis

**Search pattern:** `wizard.*step|step-1|step-2|wizardData|renderLinksList|three.step|btn-next|btn-prev`

**Files found:** 1
- `docs/audit/AUDIT_PLAN.md` - Meta-reference in the audit plan itself, not a real stale reference

**Conclusion:** The wizard UI refactor was clean — no stale references remain in active docs.

---

## Top 5 Docs the IDE Agent Should Always Read

1. **SciDK_Architecture_Vision.md** - Core philosophy, transparency principle, symmetry concept
2. **docs/ARCHITECTURE.md** - System design, component interactions, data flow
3. **docs/architecture/transparency-layers.md** - Transparency layer pattern (v1.0)
4. **docs/architecture/links-system.md** - Links system (wizard + script links)
5. **README.md** - Quick start, install, run instructions

**Rationale:** These 5 docs provide the "why" (vision), the "how" (architecture), and the "what" (current system state).

---

## Top 5 Docs Causing the Most Context Confusion

1. **dev/code-imports/** (entire directory) - Unrelated archived projects (chatseek, nc3rsEDA)
2. **dev/TRANSPARENCY_LAYERS_*.md** (6 files) - Superseded by implemented feature and tests
3. **SCRIPTS_*.md** (3 root files) - Outdated scripts architecture docs
4. **dev/plans/plan-2025-*.md** (3 files) - Plans from 5-6 months ago, likely complete
5. **SESSION_*.md** (root and dev/) - Session-specific notes, not evergreen docs

**Rationale:** These docs are either outdated, superseded, or out-of-scope archives that dilute the signal-to-noise ratio.

---

## Docs to Archive Immediately

### Root Level
- `SCRIPTS_ARCHITECTURE_STATUS.md`
- `SCRIPTS_REFACTOR_PLAN.md`
- `SCRIPTS_REFACTOR_COMPLETE.md`
- `SESSION_SUMMARY_2026-02-20.md`
- `SESSION_HANDOFF_PROMPT.md`

### docs/
- `docs/ux-runbook-2025-09-12.md`
- `docs/E2E_and_Neo4j_Task_Planning_REVISED.md`
- `docs/MVP_Architecture_Overview_REVISED.md`

### dev/
- `dev/SESSION_SUMMARY_2026-01-26.md`
- `dev/Scripts_CoNVO.md`
- `dev/TRANSPARENCY_LAYERS_ROADMAP.md`
- `dev/TRANSPARENCY_LAYERS_COMPLETE_TEST_PLAN.md`
- `dev/TRANSPARENCY_LAYERS_TESTING.md`
- `dev/TRANSPARENCY_LAYERS_TEST_IMPLEMENTATION_STATUS.md`
- `dev/TRANSPARENCY_LAYERS_INTEGRATION_TESTS_FINAL.md`
- `dev/TRANSPARENCY_TESTS_SESSION_COMPLETE.md`
- `dev/plans/plan-2025-08-21.md`
- `dev/plans/plan-2025-08-28-reboot-architecture.md`
- `dev/plans/plan-2025-09-10-sync-dev-with-impl.md`
- `dev/plans/plan-2026-01-26-refactor-and-label-link-pages.md`

### Entire directories
- `dev/code-imports/` (move outside repo or add to .gitignore)
- `dev/test-runs/tmp/` (add to .gitignore)

**Archive Method:**
```bash
mkdir -p docs/archive/{root,docs,dev}
# Move files to appropriate archive folder
# Update .gitignore to exclude test artifacts and code imports
```

---

## Recommended Actions

### Before Demo (High-Value, Low-Risk)
1. ✅ **Update FEATURE_INDEX.md** - Refresh for Links→Integrations rename (5 min)
2. ✅ **Add .gitignore entries** - Exclude `dev/test-runs/tmp/` and `dev/code-imports/` (2 min)
3. ✅ **Archive session docs** - Move SESSION_*.md and Scripts_CoNVO.md to archive (5 min)
4. ✅ **Archive transparency planning docs** - Move 6 TRANSPARENCY_*.md files to archive (5 min)
5. ✅ **Archive old scripts docs** - Move 3 SCRIPTS_*.md files to archive (5 min)

**Total time:** 22 minutes
**Impact:** Cleaner doc tree, less IDE context noise

### After Demo (Moderate-Risk Cleanup)
1. **Review and archive old plans** - Check implementation status of 2025/early-2026 plans, archive completed ones (30 min)
2. **Consolidate session docs** - Create single session archive index instead of scattered files (20 min)
3. **Review unknown-status docs** - Check GRAPHRAG_QUICK_START.md, PARAMETER_SYSTEM_DESIGN.md, SCRIPT_CONTRACTS_GUIDE.md (30 min)
4. **De-duplicate DEMO_SETUP.md** - Exists in both root and docs/, consolidate (10 min)

**Total time:** 90 minutes
**Impact:** Improved doc discoverability, reduced confusion

### Future Sprint (Architectural)
1. **Implement doc lifecycle policy** - Session docs auto-archive after 30 days, plan docs after completion (design: 1h, implement: 2h)
2. **Add doc status headers** - All docs get status: Current|Outdated|Superseded|Archived (manual: 2h, or scripted: 4h)
3. **Create doc validation script** - Check for broken links, outdated cross-references (design: 2h, implement: 4h)
4. **Generate "New Developer Onboarding" doc** - Curated reading list from existing docs (2h)

**Total time:** 15 hours
**Impact:** Long-term doc health, reduced onboarding time

---

## Audit Metadata

**Method:**
- `find` for all .md files, filtered out vendor/test artifacts
- `head -20` for doc headers (344 files scanned, ~50 detailed)
- `grep` for stale UI references (1 false positive found)
- Manual categorization based on file paths and content

**Limitations:**
- Did not read full content beyond first 20 lines
- Status assessments are estimates based on dates and titles
- Task/story details not individually reviewed (trust index docs)

**Confidence:**
- High: Root and docs/ level (95% confidence in recommendations)
- Medium: dev/ level (80% confidence, some unknowns remain)
- Low: Vendor/test artifacts (100% confidence these should be ignored)
