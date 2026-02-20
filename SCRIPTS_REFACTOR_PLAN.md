# Scripts Page Refactor Plan

**Status**: In Progress
**Created**: 2026-02-19
**Last Updated**: 2026-02-19
**Owner**: Development Team

---

## Vision

Transform the **Analysis page** into a comprehensive **Scripts page** - a unified development workspace for all of SciDK's extensibility layers (interpreters, plugins, integrations, API endpoints, and ad-hoc analyses).

## Core Concept

**Scripts page = The IDE within SciDK**

Where users can:
- Write and edit Python/Cypher code in-browser
- Organize scripts into categories (Interpreters, Plugins, Integrations, API, Analyses)
- Hot-reload changes without restarting SciDK
- Version control via git (scripts as files)
- Auto-register API endpoints from Python functions
- Export/import script folders as .zip archives

---

## Current State (Phase 1 - Completed ✅)

### What We Have
- Analysis page at `/analyses` with 3-panel UI
- Database-stored scripts (SQLite: `analyses_scripts`, `analyses_results`)
- 7 built-in Cypher/Python analysis scripts
- Script execution engine (Cypher via Neo4j, Python via exec())
- Export to Jupyter notebooks (.ipynb)
- Import from Jupyter notebooks
- REST API at `/api/analyses/*`
- 22 passing unit tests

### Files Involved
- `scidk/core/analyses.py` - Core module (640 lines)
- `scidk/core/builtin_analyses.py` - Built-in scripts
- `scidk/web/routes/api_analyses.py` - REST API
- `scidk/ui/templates/analyses.html` - UI (685 lines)
- `tests/test_analyses.py` - Tests

---

## Refactor Goals (Phase 2)

### A. Rename Analyses → Scripts
**Goal**: Update terminology throughout codebase to reflect broader purpose

**Changes Required**:
- [ ] Rename navigation link: "Analyses" → "Scripts"
- [ ] Rename route: `/analyses` → `/scripts`
- [ ] Rename API prefix: `/api/analyses` → `/api/scripts`
- [ ] Rename database tables:
  - `analyses_scripts` → `scripts`
  - `analyses_results` → `script_executions`
- [ ] Add migration v17 for table renames
- [ ] Rename Python modules:
  - `analyses.py` → `scripts.py`
  - `builtin_analyses.py` → `builtin_scripts.py`
  - `api_analyses.py` → `api_scripts.py`
  - `test_analyses.py` → `test_scripts.py`
  - Template: `analyses.html` → `scripts.html`
- [ ] Update all internal references (imports, docstrings, comments)
- [ ] Update UI text ("Analysis" → "Script" throughout)

**Estimated Time**: 0.5d
**Priority**: High (foundation for other changes)

---

### B. Add File-Based Script Storage
**Goal**: Store scripts as actual `.py`/`.cypher` files instead of database records

**Directory Structure**:
```
scripts/                       # User scripts directory (git-trackable)
├── interpreters/              # File interpretation logic
│   ├── csv_interpreter.py
│   ├── ipynb_interpreter.py
│   ├── custom_eda/           # Complex interpreter with submodules
│   │   ├── __init__.py
│   │   ├── parser.py
│   │   └── validators.py
│   └── README.md
│
├── plugins/                   # Plugin implementations
│   ├── ilab_billing/
│   │   ├── __init__.py
│   │   ├── reconcile.py
│   │   ├── config.json
│   │   └── README.md
│   └── metrics_tracker/
│       └── ...
│
├── integrations/              # External service integrations
│   ├── slack_notifier/
│   │   ├── webhook.py
│   │   ├── templates.py
│   │   └── config.json
│   └── postgres_sync/
│       └── ...
│
├── api/                       # Custom API endpoints
│   ├── custom_query.py       # Auto-registers as /api/custom/query
│   ├── data_export.py        # Auto-registers as /api/custom/export
│   ├── webhooks.py           # Auto-registers as /api/webhooks/*
│   └── README.md
│
└── analyses/                  # Ad-hoc analysis scripts
    ├── builtin/              # Built-in analyses (shipped with SciDK)
    │   ├── file_distribution.cypher
    │   ├── scan_timeline.cypher
    │   ├── largest_files.cypher
    │   ├── interpretation_rates.cypher
    │   ├── neo4j_stats.cypher
    │   ├── orphaned_files.py
    │   └── schema_drift.py
    └── custom/               # User-created analyses
        ├── my_report.cypher
        └── weekly_stats.py
```

**Implementation Details**:

1. **Script Metadata** (YAML frontmatter in files):
```python
"""
---
id: file-distribution
name: File Distribution by Extension
description: Analyze file types across all scans
language: cypher
category: analyses/builtin
tags: [files, statistics, distribution]
parameters:
  - name: limit
    type: integer
    default: 100
    label: Max results
    required: false
---
"""
MATCH (f:File)
RETURN f.extension as extension, count(*) as count
ORDER BY count DESC
LIMIT $limit
```

2. **File Watcher**:
- `scidk/core/script_watcher.py` - Monitor `scripts/` directory for changes
- Hot-reload on file save (no restart needed)
- Trigger re-registration of API endpoints

3. **Script Registry**:
- `scidk/core/script_registry.py` - In-memory registry of all scripts
- Loads scripts from `scripts/` directory on startup
- Watches for changes and reloads

4. **Hybrid Storage**:
- **Execution results** still in database (`script_executions` table)
- **Script definitions** as files
- **Metadata cache** in database for fast queries (optional)

**Changes Required**:
- [ ] Create `scripts/` directory structure
- [ ] Implement `ScriptFileLoader` class (parse .py/.cypher files with YAML frontmatter)
- [ ] Implement `ScriptWatcher` class (watchdog library for file monitoring)
- [ ] Implement `ScriptRegistry` class (in-memory script catalog)
- [ ] Update `ScriptsManager` to load from files instead of database
- [ ] Add API endpoints for file operations:
  - `POST /api/scripts/files` - Create new script file
  - `PUT /api/scripts/files/{path}` - Update script file
  - `DELETE /api/scripts/files/{path}` - Delete script file
  - `GET /api/scripts/tree` - Get directory tree structure
- [ ] Update UI to support folder navigation (tree view in left panel)
- [ ] Migrate existing built-in scripts to files
- [ ] Add `.gitignore` for `scripts/custom/` (user scripts)
- [ ] Add export/import folder as .zip

**Estimated Time**: 2d
**Priority**: High (enables version control and modularity)

---

### C. Add Category Organization
**Goal**: Organize scripts into 5 categories with specialized behaviors

**Categories**:

1. **📊 Analyses** (What we built - no changes needed)
   - Ad-hoc queries and reports
   - Cypher and Python scripts
   - Run button executes and shows results
   - Export to Jupyter

2. **🔧 Interpreters** (New)
   - File parsing/interpretation logic
   - Must implement `interpret(file_path)` function
   - Returns structured metadata
   - Auto-registers with `InterpreterRegistry`
   - Example: `csv_interpreter.py`, `ipynb_interpreter.py`

3. **🔌 Plugins** (New)
   - Modular extensions with `__init__.py`
   - Can define custom labels, routes, settings UI
   - Example: `ilab_billing/`, `metrics_tracker/`
   - Integration with existing plugin system

4. **🔗 Integrations** (New)
   - External service connectors
   - OAuth/API key configuration
   - Webhook handlers
   - Example: `slack_notifier/`, `postgres_sync/`

5. **🌐 API Endpoints** (New)
   - Custom REST API routes
   - Auto-registered from Python functions
   - Decorator-based or explicit registration
   - Example: `/api/custom/myquery`

**UI Changes**:
- [ ] Add category tabs/filter in left panel
- [ ] Category-specific icons and colors
- [ ] Different "Run" button behavior per category:
  - Analyses: Run and show results
  - Interpreters: Run test interpretation on sample file
  - Plugins: Show plugin info and enable/disable
  - Integrations: Test connection
  - API: Show auto-generated API docs

**Changes Required**:
- [ ] Update `ScriptRegistry` to organize by category
- [ ] Add category-specific validation rules
- [ ] Update UI to show category-specific actions
- [ ] Add category field to script metadata
- [ ] Update search/filter to work across categories

**Estimated Time**: 1d
**Priority**: Medium (improves organization)

---

### D. Add API Endpoint Builder
**Goal**: Auto-register Flask routes from Python scripts in `scripts/api/`

**Decorator Pattern**:
```python
# scripts/api/custom_query.py
"""
---
id: custom-query-endpoint
name: Custom Query Endpoint
description: Execute custom Cypher queries
category: api
endpoint: /api/custom/query
methods: [POST]
auth_required: true
---
"""

from scidk.core.decorators import scidk_api_endpoint, requires_auth

@scidk_api_endpoint('/api/custom/query', methods=['POST'])
@requires_auth
def custom_query(request):
    """
    Execute a custom Cypher query

    Request Body:
        query (str): Cypher query to execute
        parameters (dict): Query parameters

    Returns:
        JSON response with query results
    """
    query = request.json.get('query')
    parameters = request.json.get('parameters', {})

    # Get Neo4j driver
    from flask import current_app
    driver = current_app.extensions['scidk']['graph'].driver

    with driver.session() as session:
        result = session.run(query, parameters)
        return {
            'status': 'ok',
            'results': [dict(record) for record in result]
        }
```

**Auto-Registration**:
- Scripts in `scripts/api/` automatically scanned on startup
- Functions with `@scidk_api_endpoint` decorator registered as Flask routes
- Hot-reload when files change

**OpenAPI Documentation**:
- Auto-generate Swagger/OpenAPI docs from docstrings
- Accessible at `/api/docs` (existing Swagger UI)
- Include custom endpoints alongside built-in endpoints

**Implementation**:
```python
# scidk/core/api_registry.py
class APIRegistry:
    def __init__(self, app):
        self.app = app
        self.endpoints = {}

    def register_from_directory(self, scripts_dir):
        """Scan scripts/api/ and register decorated functions"""
        for script_file in (scripts_dir / 'api').glob('*.py'):
            module = self._load_module(script_file)
            for name, func in inspect.getmembers(module, inspect.isfunction):
                if hasattr(func, '_scidk_endpoint'):
                    self._register_endpoint(func)

    def _register_endpoint(self, func):
        """Register function as Flask route"""
        endpoint_path = func._scidk_endpoint['path']
        methods = func._scidk_endpoint.get('methods', ['GET'])

        @self.app.route(endpoint_path, methods=methods)
        @functools.wraps(func)
        def wrapper():
            return jsonify(func(request))

        self.endpoints[endpoint_path] = {
            'function': func,
            'methods': methods,
            'doc': func.__doc__
        }
```

**Changes Required**:
- [ ] Create `scidk/core/api_registry.py`
- [ ] Create `scidk/core/decorators.py` with `@scidk_api_endpoint`
- [ ] Add API endpoint scanning to app initialization
- [ ] Add hot-reload for API scripts
- [ ] Update Swagger UI to include custom endpoints
- [ ] Add UI in Scripts page to view registered API endpoints
- [ ] Add "Test Endpoint" button in Scripts page (makes sample request)
- [ ] Add security validation (rate limiting, auth checks)

**Estimated Time**: 1.5d
**Priority**: Medium (powerful feature but not blocking)

---

## Implementation Order

### Phase 2A: Foundation (1.5d)
1. Rename Analyses → Scripts (0.5d)
2. Add file-based storage infrastructure (1d)

### Phase 2B: Organization (1d)
3. Add category organization (1d)

### Phase 2C: Advanced Features (1.5d)
4. Add API endpoint builder (1.5d)

**Total Estimated Time**: 4 days

---

## Technical Decisions

### File Format for Scripts

**Chosen**: YAML frontmatter + code body (like Jekyll/Hugo)

**Alternatives Considered**:
- Pure Python with decorators (less flexible for Cypher)
- JSON sidecar files (maintenance burden)
- Database-only (no version control)

**Rationale**: YAML frontmatter is:
- Human-readable and editable
- Language-agnostic (works for .py and .cypher)
- Git-friendly (diffs work well)
- Standard in static site generators

### Storage Strategy

**Chosen**: Hybrid (files for definitions, database for execution history)

**Rationale**:
- Scripts as files → version control, modularity, shareability
- Results in database → fast queries, historical analysis
- Best of both worlds

### API Endpoint Pattern

**Chosen**: Decorator-based with auto-registration

**Rationale**:
- Pythonic and familiar (Flask-like)
- Easy to understand and use
- Clear separation of concerns
- Hot-reload friendly

---

## Migration Strategy

### Database Migration (v17)

```sql
-- Rename tables
ALTER TABLE analyses_scripts RENAME TO scripts;
ALTER TABLE analyses_results RENAME TO script_executions;

-- Add new columns
ALTER TABLE scripts ADD COLUMN file_path TEXT;
ALTER TABLE scripts ADD COLUMN category TEXT DEFAULT 'analyses';
ALTER TABLE scripts ADD COLUMN is_file_based INTEGER DEFAULT 0;

-- Create new indexes
CREATE INDEX idx_scripts_category ON scripts(category);
CREATE INDEX idx_scripts_file_path ON scripts(file_path);
```

### Data Migration Steps

1. **Backup existing analyses**: Export all scripts to JSON
2. **Run migration v17**: Rename tables and add columns
3. **Convert built-in scripts to files**: Move 7 built-in scripts to `scripts/analyses/builtin/`
4. **Update references**: Search/replace in codebase
5. **Test thoroughly**: Run full test suite
6. **Document**: Update README and user docs

### Backwards Compatibility

**Goal**: Zero downtime, graceful migration

**Strategy**:
- Keep old `/api/analyses/*` routes as aliases for 1-2 releases (deprecated)
- Add `@deprecated` decorator with migration instructions
- Database migration is transparent (just table renames)
- UI route redirect: `/analyses` → `/scripts` (301 permanent redirect)

---

## Testing Strategy

### Unit Tests
- [ ] Test script file parsing (YAML frontmatter + code)
- [ ] Test file watcher (create/update/delete files)
- [ ] Test script registry (loading, caching, lookup)
- [ ] Test category-specific behaviors
- [ ] Test API endpoint registration
- [ ] Test hot-reload mechanism

### Integration Tests
- [ ] Test full script lifecycle (create → edit → execute → delete)
- [ ] Test cross-category operations (interpreter using plugin)
- [ ] Test API endpoint invocation from UI
- [ ] Test export/import of script folders

### E2E Tests
- [ ] Navigate to Scripts page
- [ ] Create script in each category
- [ ] Edit script and verify hot-reload
- [ ] Execute script and verify results
- [ ] Register custom API endpoint
- [ ] Test endpoint from Swagger UI

**Test Coverage Goal**: 85%+

---

## Documentation Requirements

### User Documentation
- [ ] Scripts page user guide (how to create/organize/run scripts)
- [ ] Interpreter development guide (how to write custom interpreters)
- [ ] Plugin development guide (how to structure plugins)
- [ ] Integration guide (how to connect external services)
- [ ] API endpoint guide (how to create custom APIs)
- [ ] Script organization best practices
- [ ] Version control guide (git workflows for scripts)

### Developer Documentation
- [ ] Script file format specification
- [ ] API endpoint decorator reference
- [ ] Hot-reload architecture diagram
- [ ] Script registry internals
- [ ] Category system design

### Migration Guide
- [ ] Upgrade from Analyses to Scripts (for existing users)
- [ ] Converting database scripts to files
- [ ] Migrating custom analyses

---

## Security Considerations

### Script Execution
- **Python exec() sandboxing**: Restricted globals, no file system access outside scripts/
- **Cypher query validation**: Prevent mutations in read-only scripts
- **Resource limits**: Timeout for long-running scripts, memory limits

### API Endpoint Registration
- **Auth enforcement**: All custom endpoints require authentication by default
- **Rate limiting**: Per-endpoint rate limits (configurable)
- **Input validation**: Automatic JSON schema validation from docstrings
- **CORS**: Configurable CORS policies per endpoint

### File System Access
- **Sandboxed directory**: Scripts can only read/write within `scripts/` directory
- **Path validation**: Prevent path traversal attacks (`../`)
- **File type restrictions**: Only `.py`, `.cypher`, `.json`, `.yaml` allowed
- **Size limits**: Max 1MB per script file

---

## Performance Considerations

### File Watching
- Use `watchdog` library (efficient inotify/FSEvents)
- Debounce rapid changes (wait 500ms after last change)
- Only watch `scripts/` directory (not entire project)

### Script Registry
- In-memory cache of all scripts (fast lookup)
- Lazy loading of script content (only load when needed)
- LRU cache for parsed metadata (avoid re-parsing)

### API Endpoint Registration
- Register on startup and on file change (not per request)
- Compiled route patterns (Flask's native routing)
- Minimal overhead vs native Flask routes

---

## Open Questions

### 1. Script Versioning
**Question**: Should scripts have version history within SciDK?

**Options**:
- A) Rely on git for version control (simplest)
- B) Store version history in database (more complex, more features)
- C) Hybrid: git for files, database for execution metadata

**Recommendation**: Option A for Phase 2, Option C for future

### 2. Script Sharing
**Question**: How should users share scripts with each other?

**Options**:
- A) Export/import folders as .zip
- B) Script marketplace (community repository)
- C) Git-based sharing (push/pull from remote repos)

**Recommendation**: Option A for Phase 2, Option B/C for future

### 3. Interpreter Hot-Reload
**Question**: Can we hot-reload interpreters without restarting SciDK?

**Complexity**: High (interpreters are registered globally, used by scanning system)

**Recommendation**: Defer to Phase 3, require restart for interpreter changes in Phase 2

### 4. Script Dependencies
**Question**: How do scripts declare Python package dependencies?

**Options**:
- A) Global virtualenv (current approach)
- B) Per-script `requirements.txt`
- C) Docker containers per script

**Recommendation**: Option A for Phase 2, Option B for future

---

## Success Criteria

### Phase 2A (Foundation)
- [ ] All references renamed from "Analyses" to "Scripts"
- [ ] Navigation shows "Scripts" instead of "Analyses"
- [ ] Database tables renamed successfully
- [ ] All tests passing with new names
- [ ] Scripts stored as files in `scripts/` directory
- [ ] Hot-reload working for script file changes
- [ ] Existing built-in scripts migrated to files

### Phase 2B (Organization)
- [ ] 5 categories implemented and functional
- [ ] UI shows category-specific actions
- [ ] Scripts organized in category folders
- [ ] Category filtering/search works

### Phase 2C (Advanced)
- [ ] Custom API endpoints auto-register from `scripts/api/`
- [ ] Decorator pattern working and documented
- [ ] Swagger UI shows custom endpoints
- [ ] Security measures in place (auth, rate limiting)

### Overall
- [ ] Zero data loss during migration
- [ ] Performance equivalent or better than Phase 1
- [ ] 85%+ test coverage maintained
- [ ] Documentation complete
- [ ] User-facing changes fully explained

---

## Rollback Plan

If issues arise during refactor:

1. **Database rollback**: Restore from backup, run reverse migration
2. **Code rollback**: Git revert to pre-refactor commit
3. **Data export**: All scripts exportable to JSON before migration
4. **Graceful degradation**: Old `/api/analyses` routes continue working

**Backup before starting Phase 2**: Complete database dump + git tag

---

## Future Enhancements (Phase 3+)

### Script Marketplace
- Community repository of shared scripts
- Rating/review system
- One-click install of popular scripts
- Featured scripts gallery

### Advanced API Features
- GraphQL support (alongside REST)
- WebSocket endpoints for real-time data
- Auto-generated client SDKs (Python, JavaScript)
- API usage analytics

### Collaborative Editing
- Real-time collaborative editing (like Google Docs)
- Script comments and annotations
- Version comparison tool (diff viewer)

### Advanced Interpreters
- Visual interpreter builder (drag-and-drop)
- Interpreter testing framework
- Performance profiling for interpreters

### Container Integration
- Docker-based script execution (full isolation)
- Per-script resource limits (CPU, memory)
- Multi-language support (R, Julia, Go)

---

## Notes & Decisions Log

### 2026-02-19
- **Decision**: Rename Analyses → Scripts
- **Rationale**: Better reflects broader purpose as development workspace
- **Approved by**: User

### 2026-02-19
- **Decision**: Use file-based storage + hybrid approach
- **Rationale**: Enables version control while keeping execution history in DB
- **Approved by**: User

### 2026-02-19
- **Decision**: Implement all 4 goals (A, B, C, D)
- **Rationale**: Comprehensive refactor delivers maximum value
- **Estimated time**: 4 days
- **Approved by**: User

---

## Contact & Ownership

**Primary Owner**: Development Team
**Questions**: See project README for contact info
**Plan Location**: `/SCRIPTS_REFACTOR_PLAN.md` (project root)
**Related Docs**:
- `/dev/tasks/ui/features/task-analyses-page.md` (original task)
- `/SESSION_HANDOFF_PROMPT.md` (session handoff template)

---

**Last Updated**: 2026-02-19
**Next Review**: After Phase 2A completion
**Status**: Ready to begin implementation ✅
