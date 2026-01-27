# SciDK Web Routes - Blueprint Architecture

This directory contains modular Flask blueprints that organize SciDK's web API and UI routes.

## Blueprint Organization

### UI Routes (`ui.py`)
**12 routes** for web interface pages:
- `GET /` - Homepage with scan summaries
- `GET /datasets` - Files page (provider browser, scan management)
- `GET /map` - Graph visualization
- `GET /chat` - LLM chat interface
- `GET /settings` - Configuration page
- `GET /workbook/<id>` - Excel file preview
- Plus: health check, static content, redirects

### API Blueprints

**`api_files.py`** (38 routes)
- File system operations: browse, list, scan
- Dataset management: CRUD operations
- Scan history: GET /scans, /scans/<id>, /scans/<id>/status
- Research objects and annotations
- File preview and download

**`api_tasks.py`** (5 routes)
- Background task management
- POST /tasks - Create scan/commit tasks
- GET /tasks, /tasks/<id> - Monitor progress
- DELETE /tasks/<id> - Cancel tasks

**`api_graph.py`** (15 routes)
- Graph schema introspection and export
- CSV/Excel/Arrow/Pickle instance exports
- RO-Crate generation (GET /rocrate, POST /ro-crates/*)
- Commit preview and hierarchy endpoints

**`api_neo4j.py`** (9 routes)
- Neo4j settings and connection management
- Commit operations (scan data → Neo4j graph)
- Disconnect and test endpoints

**`api_providers.py`** (8 routes)
- Provider management (local_fs, mounted_fs, rclone)
- Root/mount point listing
- Health checks

**`api_chat.py`** (6 routes)
- LLM chat interface
- Conversation history
- Message streaming

**`api_admin.py`** (5 routes)
- Health checks (GET /health)
- Operational logs (GET /logs)
- System metrics (GET /metrics)

**`api_interpreters.py`** (4 routes)
- Interpreter registry CRUD
- Test and configuration endpoints

## Code Patterns

### Blueprint Helper Function
All blueprints use `_get_ext()` to access Flask extensions:

```python
def _get_ext():
    """Get SciDK extensions from current Flask app."""
    return current_app.extensions['scidk']

@bp.get('/example')
def example_route():
    graph = _get_ext()['graph']
    fs = _get_ext()['fs']
    # ... use extensions
```

### Background Thread Pattern
Routes that spawn threads must capture app context:

```python
@bp.post('/tasks')
def create_task():
    app = current_app._get_current_object()

    def _worker():
        with app.app_context():
            # Full Flask context available
            graph = current_app.extensions['scidk']['graph']
            # ... worker code

    threading.Thread(target=_worker, daemon=True).start()
```

### Import Patterns
- Lazy imports inside routes: `from ...core import module`
- Blueprint registration: See `__init__.py`
- Shared helpers: `from ..helpers import function_name`

## Adding New Routes

1. **Choose appropriate blueprint** based on functional area
2. **Add route decorator**: `@bp.get('/path')` or `@bp.post('/path')`
3. **Use `_get_ext()`** to access app extensions
4. **Import lazily** when possible to avoid circular imports
5. **Test thoroughly** - run full test suite

Example:
```python
@bp.get('/new-endpoint')
def api_new_endpoint():
    """Brief description."""
    ext = _get_ext()
    # Your logic here
    return jsonify(result), 200
```

## Blueprint Registration

See `__init__.py` for registration:
```python
def register_blueprints(app):
    from . import ui, api_files, api_tasks, ...
    app.register_blueprint(ui.bp)
    app.register_blueprint(api_files.bp)
    # ...
```

Called from `app.py:create_app()`.

## Metrics

- **Total routes**: 91 across 9 blueprints
- **Lines of code**: ~4,400 lines (down from 5,781 monolithic)
- **Test coverage**: 128/136 tests passing (94%)

## Migration Notes

Routes were extracted from monolithic `app.py` in 2026-01-26 refactor:
- All variable scoping converted: `app.` → `current_app.`, `fs.` → `_get_ext()['fs'].`
- All imports fixed: `.core` → `...core`, `.services` → `...services`
- Flask app context properly handled in background threads

See `BLUEPRINT_REFACTOR_PROGRESS.md` for detailed migration history.
