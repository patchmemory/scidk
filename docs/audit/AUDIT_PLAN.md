# Codebase Audit Plan — SciDK

## Objective
Produce a read-only analysis report (`docs/audit/CODEBASE_AUDIT.md`) mapping what actually exists in the codebase vs. what was planned, to inform cleanup decisions before demo.

---

## Execution Strategy

**Key Principles:**
1. **Incremental writes** - Save after each major section (8 save points total)
2. **Simple tools only** - Bash for analysis, Write/Edit for file operations
3. **Fail gracefully** - Note failures and continue; estimate when exact data unavailable
4. **Read-only mode** - Zero modifications to source code or configs

---

## Section Breakdown

### Section 0: Setup (1 min)
- Create `docs/audit/` directory if missing
- Initialize `CODEBASE_AUDIT.md` with header and TOC
- Read architecture docs to understand intended design
- **Checkpoint: Empty report structure written**

### Section 1: Settings Inventory (3 min)
- Grep all `set_setting`/`get_setting` calls
- Grep all settings table SQL operations
- Grep frontend settings API calls
- Build table: Key | Where Written | Where Read | Category | Status
- Flag orphaned keys (write-only or read-only)
- **Checkpoint: Section 1 written to file**

### Section 2: Database Schema (2 min)
- Grep all `CREATE TABLE` statements
- Review `migrations.py` for schema evolution
- Document each table: name, purpose, data category, export eligibility, usage status
- **Checkpoint: Section 2 written to file**

### Section 3: Dead Code Detection (5 min)
- Extract all function definitions with grep
- Use Python script to cross-reference definitions vs. calls
- Report top 20 suspicious functions (defined once, called ≤1 times)
- Check for unused imports (if linter available)
- Count backend routes vs. frontend API calls for balance check
- **Checkpoint: Section 3 written to file**

### Section 4: Duplicate Functionality (3 min)
- Find functions with similar names (sort | uniq -d)
- List all API routes and flag semantic overlaps
- Find settings-related functions (common duplication area)
- Report instances of same data stored multiple ways
- **Checkpoint: Section 4 written to file**

### Section 5: Frontend/Backend Contract Gaps (2 min)
- Extract all backend routes: `@bp.(get|post|put|delete)`
- Extract all frontend API calls: `fetch('/api` patterns
- Diff to find:
  - Backend routes never called from frontend
  - Frontend calls with no matching backend route
- **Checkpoint: Section 5 written to file**

### Section 6: Documentation Currency (2 min)
- Find all markdown docs
- Check modification dates vs. recent code changes
- Grep for references to changed features (wizard steps, renderLinksList, etc.)
- Rate each doc: Current / Possibly Outdated / Likely Outdated
- **Checkpoint: Section 6 written to file**

### Section 7: Test Coverage Gaps (2 min)
- List all test files
- Find skipped tests and reasons
- Identify source files with no corresponding test file
- **Checkpoint: Section 7 written to file**

### Section 8: Project Bundle Requirements (3 min)
- Based on all findings above, define what `.scidk` export must include:
  - **MUST INCLUDE** (critical)
  - **SHOULD INCLUDE** (data loss risk)
  - **NICE TO HAVE** (convenience)
  - **EXPLICITLY EXCLUDE** (security/size)
- **Checkpoint: Section 8 written to file**

### Section 9: Recommended Actions (2 min)
- Synthesize findings into prioritized backlog:
  - **Before demo** (low-risk, high-value quick wins)
  - **After demo** (moderate-risk cleanup)
  - **Future sprint** (architectural improvements)
- Each recommendation must be actionable
- **Checkpoint: Final report complete**

---

## Deliverable

Single markdown file: `docs/audit/CODEBASE_AUDIT.md`

**Format:**
- Executive Summary (3-5 bullet findings)
- 8 detailed sections with tables and lists
- Recommended Actions with priority tiers
- Appendix with raw command outputs (if useful)

**Success Criteria:**
- Report is complete and scannable
- Every finding has a "what to do about it" recommendation
- No source code modifications made
- File safely written to disk with all sections intact

---

## Risk Mitigation

**If crashes occur again:**
- Each section is independently written, so partial progress is saved
- Can resume from last checkpoint by editing file instead of rewriting
- All grep commands are non-destructive and can be re-run

**If commands fail:**
- Note the failure in the report
- Provide estimate or qualitative assessment instead
- Continue to next section

---

**Total Estimated Time:** 25 minutes
**Total File Writes:** 9 (initial + 8 checkpoints)
**Source Code Changes:** 0

---

## Status

**Backlogged** - Ready to execute on approval. Agent will track progress with TodoWrite during execution.
