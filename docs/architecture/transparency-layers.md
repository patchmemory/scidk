# Transparency Layers Architecture

**Status:** Implemented
**Date:** 2025-02-20
**Version:** 1.0

---

## Overview

The transparency layer architecture makes intelligence visible at the point of use, not buried in Settings. Every page in SciDK has two layers:

1. **Data Layer** - What you're looking at (files, links, maps)
2. **Intelligence Layer** - What's shaping how you see it (interpreters, scripts, plugins)

The transparency layer makes the intelligence visible and auditable without getting in the way.

---

## Core Principle

> **Intelligence visible at point of use, not buried in Settings**

Users should be able to understand *what* the system is doing and *why* without navigating away from their current context.

---

## Design Principles

### 1. SQL for Infrastructure, KG for Data
- **SQL (SQLite)**: System dependencies, script relationships, infrastructure metadata
- **Knowledge Graph (Neo4j)**: Research data, file relationships, domain knowledge

Rationale: Dependencies between scripts are infrastructure concerns, not research data. Keeping them in SQL prevents the knowledge graph from being cluttered with plumbing.

### 2. Chat-Accessible by Design
Every tool built for users is accessible to Chat through clean query endpoints:
- `/api/system/plugin-dependencies/<id>` - What depends on this plugin?
- `/api/system/active-interpreters` - Which interpreters are running?
- `/api/system/script-status/<id>` - What's the status of this script?
- `/api/system/file-interpreter/<path>` - Which interpreter handles this file?

This enables Chat to answer questions like:
- "Which interpreter handles FASTQ files?"
- "What would break if I deactivate genomics_normalizer?"
- "Show me all active plugins"

### 3. Decoupled Preview + Commit
Interpretation and graph writes are separate operations:
- **Preview** (`/api/files/interpret`): Run interpreter, show results, no side effects
- **Commit** (`/api/files/interpret/commit`): Write to graph with hash verification

This enables:
- Non-destructive exploration before committing
- Future async execution for large files
- Race condition prevention via preview hash

### 4. Explicit Degraded States
"No interpreter assigned" is visible, not invisible. Empty states prompt users to explore available options rather than leaving them confused.

### 5. Transparency Without Clutter
Intelligence is visible where relevant but doesn't overwhelm:
- Files sidebar: "Interpreted by: FASTQ Interpreter ↗"
- Plugins page: "Used by: FASTQ Interpreter, 3 Link scripts"
- Scripts page: Developer workbench (authoring environment)

### 6. Validation Guarantees Dependencies
Only validated scripts appear in dependency tracking. Draft and failed scripts don't pollute the "Used by" displays.

---

## Implementation by Page

### Links Page (Already Implemented)
**Status:** ✅ Complete

Two intelligence types coexist:
- **Wizard Links**: Declarative rules visible in form
- **Script Links**: Code-based with validation status badge

**Transparency Mechanism:**
- Filter tabs show intelligence source (Wizard | Script | All)
- Validation badges (🟢 Validated | 🟡 Draft | 🔴 Failed)
- Preview/Execute buttons with safety confirmations

**Documentation:** [docs/architecture/links-system.md](./links-system.md)

---

### Files Page
**Status:** ✅ Complete (API + UI Implemented)

**When file has interpreter results:**
```
📄 sample_R1.fastq
─────────────────────────
Entity Type:  SequencingFile
Interpreted by: FASTQ Interpreter ↗
  read_count:     1,847,293
  format_version: 1.8
─────────────────────────
🔬 Interpreters          [▼]
```

**Degraded state (no interpreter):**
```
📄 unknown_file.xyz
─────────────────────────
⚠️ No interpreter assigned
[Assign Interpreter] button
─────────────────────────
🔬 Interpreters          [▼]
```

**Interpreter Modal Flow:**
1. User selects file → sidebar shows metadata + interpreter section
2. Click "Assign Interpreter" → modal opens with validated interpreters
3. Select interpreter → **Run Preview** → see metadata without commit
4. Click **Commit to Graph** → writes to graph with hash verification, closes modal
5. Sidebar updates automatically → shows "Interpreted by" attribution

**Implementation:**
- **Modal Component:** `scidk/ui/templates/files/_interpreter_modal.html` (~550 lines)
- **Integration:** Included in `datasets.html`, integrated with `showFileDetails()`
- **API Endpoints:**
  - `POST /api/files/interpret` - Preview interpreter results
  - `POST /api/files/interpret/commit` - Commit to graph with hash verification
- **Features:**
  - Accordion-style interpreter list
  - Non-destructive preview workflow
  - Hash verification prevents race conditions
  - Error handling with user-friendly messages
  - Sidebar updates after successful commit

**Configuration:**
- Interpreter assignment (extension rules) stays in Settings
- Sidebar shows **what** is running, Settings controls **configuration**

---

### Plugins Page
**Status:** ✅ Complete

**Three Sections:**

#### 1. **Active Plugins** 🟢 (validated + active)
Shows plugins currently shaping system behavior:
```
📦 genomics_normalizer          🟢 Active
   Normalizes genomic coordinate data
   Used by: FASTQ Interpreter, Variant Caller (Link), 2 other scripts
   [View in Scripts]
```

#### 2. **Available but Inactive** 🟡 (validated only)
Shows plugins ready to activate:
```
📦 pubmed_lookup                🟡 Validated, not active
   Enriches documents with PubMed metadata
   [→ Activate in Scripts]
```

#### 3. **Draft / Failed** 🔴 (needs attention)
Developer-facing section:
```
📦 embedding_similarity         🔴 Validation failed
   [→ Edit in Scripts]
```

**"Used By" Display:**
- Populated from `script_dependencies` SQL table
- Shows real dependency graph
- Only reflects validated scripts
- JavaScript loads dependencies async via `/api/plugins/dependencies/<id>`

**Transparency Goal:** A scientist who doesn't code can answer: "What is SciDK actually doing under the hood right now?"

---

### Scripts Page (Developer Workbench)
**Status:** ✅ Complete (validation architecture)

Scripts deliberately stays as the developer workbench. It's where things are **built**, not where they're **explained**.

**Validation Workflow:**
1. Author script
2. **Validate** → runs contract tests in sandbox
3. **Activate** → makes available to system
4. Appears on **Plugins** page (transparency layer)

**Dependency Tracking:**
- AST scans for `load_plugin()` calls during validation
- Dependencies written to `script_dependencies` table
- Editing a script clears dependencies (must re-validate)

---

### Scripts Page (Not a Transparency Layer)
Scripts is the **workbench** where intelligence is created. It's developer-facing and intentionally doesn't try to explain itself to non-coders.

The distinction matters:
- **Scripts**: Where things are built
- **Plugins**: Where things are explained

---

## Data Flow

```
Scripts Page (author)
    ↓
Validate (AST scan for dependencies)
    ↓
Activate (mark as active)
    ↓
Plugins Page (transparency)
    ↓
Files/Links/Maps (use)
```

### Dependency Tracking Flow

**On Validation Success:**
1. AST scans code for `load_plugin('plugin_id')` calls
2. Extract plugin IDs (Python 3.8+ compatible)
3. Write to `script_dependencies` table:
   - `dependent_id`: Script being validated
   - `dependency_id`: Plugin ID from code
   - `dependent_type`: 'interpreter', 'link', or 'plugin'
4. Appears in "Used by" on Plugins page

**On Edit:**
1. User changes code in Scripts page
2. `script.mark_as_edited()` called
3. Dependencies cleared from `script_dependencies`
4. Validation status → 'draft'
5. Must re-validate to restore dependencies

**On Query:**
- `/api/plugins/dependencies/<plugin_id>` joins table with script names
- Returns enriched list: `[{id, name, type, category}]`
- JavaScript renders on Plugins page

---

## Database Schema

### script_dependencies Table
```sql
CREATE TABLE script_dependencies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dependent_id TEXT NOT NULL,      -- script that calls load_plugin()
    dependency_id TEXT NOT NULL,     -- plugin being called
    dependent_type TEXT NOT NULL,    -- 'interpreter', 'link', 'plugin'
    created_at REAL NOT NULL,
    UNIQUE(dependent_id, dependency_id)
);

CREATE INDEX idx_dependencies_dependency ON script_dependencies(dependency_id);
CREATE INDEX idx_dependencies_dependent ON script_dependencies(dependent_id);
```

**Why SQL not Neo4j:**
- Infrastructure metadata, not research data
- Fast queries for UI rendering
- Prevents graph clutter with plumbing
- Keeps dependency tracking independent of domain model

---

## AST Dependency Scanner

**Location:** `scidk/core/script_validators.py`

**Function:** `extract_plugin_dependencies(code: str) -> List[str]`

**Compatibility:** Handles both `ast.Str` (Python <3.8) and `ast.Constant` (Python >=3.8)

**Example:**
```python
# Code:
from scidk.core.plugin_loader import load_plugin

def interpret(file_path):
    normalizer = load_plugin('genomics_normalizer', manager)
    return normalizer.process(file_path)

# Extracted: ['genomics_normalizer']
```

**Safety:**
- Silent failure on syntax errors (returns empty list)
- Only extracts string literal arguments
- Runs during validation, not execution

---

## Chat Integration (Future)

Chat can query system state through `/api/system/*` endpoints:

**Examples:**
```
User: "Which interpreter handles FASTQ files?"
Chat: GET /api/system/file-interpreter//path/sample.fastq
      → "FASTQ Interpreter (assigned by extension rule)"

User: "What would break if I deactivate genomics_normalizer?"
Chat: GET /api/system/plugin-dependencies/genomics_normalizer
      → "Used by: FASTQ Interpreter, Variant Caller (Link)"

User: "Show me all active plugins"
Chat: GET /api/system/active-interpreters
      → [list of validated + active interpreters]
```

**Design Goal:** Chat as unified interface for data + system state queries.

---

## Migration Path

### From Settings-Centric to Transparency-First

**Before:**
- Interpreters configured in Settings → Interpreters tab
- Plugins listed in Settings → Plugins tab
- No visibility into "Used by" relationships
- Configuration and transparency conflated

**After:**
- Interpreters: Configuration in Settings, transparency in Files sidebar
- Plugins: Full dedicated page with dependency graph
- Scripts: Developer workbench for authoring
- Clean separation of concerns

**Settings becomes:** Operational configuration (assign this interpreter to .fastq)

**Transparency pages become:** Readable, auditable surfaces (here's what's running and why)

---

## Testing Checklist

### Dependency Tracking
- ✅ Validating script with `load_plugin()` writes to `script_dependencies`
- ✅ Editing script clears dependencies
- ✅ Re-validating updates dependencies correctly
- ✅ UNIQUE constraint prevents duplicates

### Plugins Page
- ✅ Active plugins show validation badges (🟢)
- ✅ "Used by" displays correct dependency list
- ✅ Inactive validated plugins show "Activate" link (🟡)
- ✅ Draft/failed plugins show "Edit in Scripts" link (🔴)
- ✅ Empty sections show appropriate messages

### Files Page (API)
- ✅ `/api/files/interpret` returns preview with hash
- ✅ `/api/files/interpret/commit` verifies hash before writing
- ✅ Hash mismatch returns 409 Conflict
- 🚧 UI integration pending

### Chat Tools
- ✅ `/api/system/plugin-dependencies/<id>` returns correct data
- ✅ `/api/system/active-interpreters` lists validated + active
- ✅ `/api/system/script-status/<id>` returns full status
- ✅ `/api/system/file-interpreter/<path>` identifies interpreter

---

## Future Enhancements

### Files Page UI Completion
- Add interpreter modal to right sidebar
- JavaScript for preview/commit workflow
- "Interpreted by" link to interpreter details

### Chat Deep Integration
- Tool calling for system state queries
- Natural language dependency exploration
- "What if" scenario analysis

### Dependency Visualization
- Graph view of plugin → script relationships
- Impact analysis before deactivation
- Circular dependency detection

### Async Interpretation
- Background execution for large files
- Progress tracking in Files page
- Queue management for batch interpretation

---

## References

- **Links System:** [docs/architecture/links-system.md](./links-system.md)
- **Script Validation:** `scidk/core/script_validators.py`
- **Dependency Tracking:** `scidk/core/scripts.py` (ScriptsManager methods)
- **API Routes:**
  - `scidk/web/routes/api_plugins.py` - Plugin dependencies
  - `scidk/web/routes/api_files.py` - Interpreter preview/commit
  - `scidk/web/routes/api_system.py` - Chat tools

---

## Contributors

- **Architecture:** Agent + User collaboration
- **Implementation:** Phase 0-3 complete, Phase 3 UI pending
- **Date:** 2025-02-20

---

*This document defines the transparency layer architecture that makes SciDK's intelligence visible, auditable, and accessible to both humans and AI.*
