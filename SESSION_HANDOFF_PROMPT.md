# Production MVP Development Session - Handoff Prompt

## Context

I'm continuing work on the **production-mvp** branch to prepare SciDK for demo deployment. This is a clean session continuation with all planning documentation prepared.

## Current State

- **Branch**: `production-mvp` (22 commits ahead of main)
- **Base**: Includes all production infrastructure from PR #49
- **Status**: PR #51 ready to merge (685 tests passing)
- **Recent work**: Cross-database transfer V2, GraphRAG feedback, Files page redesign, task planning

## Planning Documents to Review

**Required reading before starting implementation**:

1. **`dev/PRODUCTION_MVP_STATUS.md`** - Complete status snapshot
   - Current branch state and PR #51 status
   - Recently completed features
   - Ready Queue with 10 demo-critical tasks
   - Test suite status (685 passing)
   - Development workflow guide

2. **`dev/plans/production-mvp-roadmap.md`** - Phase breakdown and timeline
   - 4-phase structure (UI polish, integrations, data import, demo prep)
   - Timeline estimates (7-18 developer days)
   - Deferred features (MCP integration)
   - Open questions and decisions needed

3. **`dev/tasks/index.md`** - Ready Queue (RICE-sorted)
   - 10 demo-critical tasks
   - Task status synchronized with actual files
   - MCP tasks in separate deferred section

4. **`dev/README-planning.md`** - Development workflow
   - "Turn the Crank" workflow
   - Task management with Dev CLI
   - Story/Phase/Task structure

5. **`dev/prompts.md`** - AI agent prompting guide
   - Dev CLI commands
   - Testing requirements
   - E2E test guidelines

## Next Tasks (RICE-Prioritized)

The Ready Queue contains 10 demo-critical tasks. **Recommended starting point**:

### 1. Maps Query Panel (RICE 80, 1 day) ⭐ **RECOMMENDED FIRST**
- **Task ID**: `task:ui/features/maps-query-panel`
- **File**: `dev/tasks/ui/features/task-maps-query-panel.md`
- **Goal**: Add Cypher query editor to Maps page
- **Key features**:
  - Query textarea with Run/Save/Load buttons
  - Integration with Chat's query library (shared backend)
  - Results display (table format)
  - Schema-aware querying
- **Why first**: High impact (RICE 80), reasonable scope (1d), enables powerful workflow

### 2. Analyses Page (RICE 70, 1.5 days)
- **Task ID**: `task:ui/features/analyses-page`
- **File**: `dev/tasks/ui/features/task-analyses-page.md`
- **Goal**: Create read-only analytics dashboard
- **Key features**:
  - Three-panel layout (script library | editor | results)
  - 7 built-in analysis scripts
  - Export to CSV/JSON/PDF
  - Custom script creation
- **Why second**: Production-ready feature, clear requirements, demo showcase

### 3. Navigation Update (RICE 50, 0.5 days)
- **Task ID**: `task:ui/navigation/update-navigation-structure`
- **File**: `dev/tasks/ui/navigation/task-update-navigation-structure.md`
- **Goal**: Update navigation to: File | Label | Integrate | Map | Chat
- **Why third**: Quick win, improves UX consistency

### Other Ready Tasks
- Integrations three-column layout (RICE 75, 2d)
- Links settings enhancements (RICE 60-96, 1-1.5d each)
- EDA file interpreter (RICE 55, 1.5d)
- Neo4j instance browser (RICE 32, 2-3d)

## Development Workflow

### Using Dev CLI (Recommended)

```bash
# View Ready Queue
python dev_cli.py ready-queue

# Start a task (creates branch, shows context)
python dev_cli.py start task:ui/features/maps-query-panel

# Get full implementation context
python dev_cli.py context task:ui/features/maps-query-panel

# After implementation, mark complete
python dev_cli.py complete task:ui/features/maps-query-panel

# Commit dev submodule updates to main repo
cd .. && git add dev && git commit -m "chore(dev): Mark maps-query-panel Done"
```

### Manual Workflow (Alternative)

1. **Read task spec**: `dev/tasks/ui/features/task-maps-query-panel.md`
2. **Implement features** according to acceptance criteria
3. **Write tests**: Unit tests + E2E tests (Playwright in `e2e/*.spec.ts`)
4. **Run tests**: `python3 -m pytest -xvs` and `npm run e2e` (local only)
5. **Update task status** in `dev/tasks/ui/features/task-maps-query-panel.md` (status: Done, completed: date)
6. **Update Ready Queue** in `dev/tasks/index.md` (move to completed section)
7. **Commit changes** to both main repo and dev submodule

## Key Points

### Branch Strategy
- Work on `production-mvp` branch
- All commits stay on `production-mvp` until MVP complete
- Can create feature branches if helpful (e.g., `feature/maps-query-panel`)
- PR #51 can merge separately (same baseline)

### Testing Requirements
**All UI features MUST include**:
1. ✅ Unit tests (backend logic) - run in CI
2. ✅ E2E tests (Playwright TypeScript) - run locally only
3. ✅ Manual testing verification

**E2E Test Notes**:
- Write tests in `e2e/*.spec.ts`
- Use `data-testid` attributes for selectors
- Run locally: `npm run e2e` or `npm run e2e:headed`
- CI does NOT run E2E tests (stability issues deferred)

### Dev Submodule Synchronization
**IMPORTANT**: Keep dev submodule synchronized as tasks complete!

```bash
# After task completion, in dev submodule:
cd dev
git add tasks/
git commit -m "chore: Mark task-id as Done"
git push origin feature/ilab-plugin-and-demo-seeding

# In main repo:
cd ..
git add dev
git commit -m "chore(dev): Update submodule - task-id marked Done"
git push origin production-mvp
```

## Questions to Address During Session

### 1. Demo Use Cases (High Priority)
**Question**: Which 2-3 specific workflows should drive feature prioritization?

**Suggested Examples**:
- File-to-Graph: Scan files → Browse/filter → Commit to Neo4j → Visualize
- Cross-Database Integration: Transfer from read-only → Query → Analyze
- Label Management: Define schema → Browse instances → Create relationships

**Action**: Define in `dev/plans/production-mvp-roadmap.md` or discuss with user

### 2. MCP Integration
**Question**: Should MCP integration be part of MVP or defer post-MVP?

**Current stance**: Deferred (6 tasks, ~8.5 days)
**Rationale**: Not essential for core demo workflows

**Action**: Confirm with user if needed

### 3. Merge Strategy
**Question**: Merge PR #51 to main before continuing, or keep working on production-mvp?

**Options**:
- **Option A**: Merge PR #51 first (cleaner history, but requires approval)
- **Option B**: Continue on production-mvp (faster start, sync later)

**Recommendation**: Continue on production-mvp (branches are equivalent)

### 4. Task Scope Confirmation
**Question**: Should Maps Query Panel include all features or MVP subset?

**Full spec includes**:
- Query editor with Run/Save/Load/Clear buttons
- Query library modal (reuse from Chat)
- Schema-aware features (node click → pre-populate query)
- Results display (table format)

**MVP subset could skip**:
- Schema-aware features (defer to phase 2)
- Advanced results views (just table, no charts)

**Action**: Confirm scope or proceed with full spec (1d estimate includes full)

## Implementation Tips

### Maps Query Panel Specific
- **Reuse Chat code**: Query library modal is already implemented in `scidk/ui/templates/chat.html`
- **Extract or duplicate**: Can extract into shared partial or duplicate for MVP
- **API endpoints exist**: `/api/graph/query` and `/api/queries` already work
- **Styling**: Match Maps page aesthetic (clean, professional)

### Analyses Page Specific
- **Three-panel layout**: Similar to Chat page layout pattern
- **Script registry pattern**: Create `scidk/core/analyses/registry.py`
- **Built-in scripts**: Start with 3-4 simple ones (file distribution, scan timeline)
- **Export**: Use pandas for CSV, json module for JSON

### General Tips
- **Read existing code first**: Check similar pages for patterns
- **Test incrementally**: Don't wait until end to run tests
- **Use data-testid**: Add to all interactive elements for E2E tests
- **Check FEATURE_INDEX.md**: See what features exist already
- **Ask questions**: If requirements unclear, ask user for clarification

## Expected Outcomes

By end of session, ideally complete **1-2 tasks**:
1. ✅ Maps Query Panel implemented and tested
2. ✅ (Optional) Analyses page started or Navigation update completed

**Deliverables**:
- Working features committed to `production-mvp`
- Tests passing (unit + E2E locally)
- Task status updated in dev submodule
- Dev submodule synchronized with main repo

## Quick Reference

### Important Files
- **Maps page**: `scidk/ui/templates/map.html`
- **Chat page** (for reference): `scidk/ui/templates/chat.html`
- **API routes**: `scidk/web/routes/api_graph.py`, `api_chat.py`
- **Task specs**: `dev/tasks/ui/features/*.md`

### Key Commands
```bash
# Git status
git branch -vv
git log --oneline -5

# Run tests
python3 -m pytest -xvs
npm run e2e

# Dev CLI
python dev_cli.py ready-queue
python dev_cli.py start <task-id>
python dev_cli.py context <task-id>
python dev_cli.py complete <task-id>
```

### Useful Links
- **PR #51**: https://github.com/patchmemory/scidk/pull/51
- **Branch**: `production-mvp` (origin/production-mvp)
- **Dev submodule**: `feature/ilab-plugin-and-demo-seeding` branch

## Start Here

**Recommended first action**:
1. ✅ Review `dev/PRODUCTION_MVP_STATUS.md` (5 min)
2. ✅ Review `dev/tasks/ui/features/task-maps-query-panel.md` (10 min)
3. ✅ Run `python dev_cli.py context task:ui/features/maps-query-panel` (if using Dev CLI)
4. ✅ Confirm approach with user or start implementation
5. ✅ Begin coding Maps Query Panel feature

---

**Ready to start?** Begin by reviewing the status document and confirming the approach before implementation. Good luck! 🚀
