# Contributing to SciDK

Conventions for common changes. For setup and how to run the app, see the README ("Run the server" — `scidk-serve` is canonical).

## Add a new route

Routes live in per-area blueprints under `scidk/web/routes/`. Reuse an existing module when one fits; otherwise add a new file following the same pattern:

```python
# scidk/web/routes/api_widgets.py
from flask import Blueprint, jsonify
bp = Blueprint("api_widgets", __name__, url_prefix="/api")

@bp.get("/widgets")
def list_widgets():
    return jsonify([])
```

Then register it in `scidk/web/routes/__init__.py` inside `register_blueprints()`:

```python
from . import api_widgets
app.register_blueprint(api_widgets.bp)
```

Add `data-testid` attributes to any new interactive UI elements.

## Persist settings

Use the helpers in `scidk/core/settings.py` — do not write the `settings` table directly:

```python
from scidk.core.settings import get_setting, set_setting
set_setting("my_key", "value")
val = get_setting("my_key", default=None)
```

## Query Neo4j

Always go through `scidk/services/neo4j_client.py`; never instantiate `neo4j.GraphDatabase` drivers directly:

```python
from scidk.services.neo4j_client import get_neo4j_client
client = get_neo4j_client()
rows = client.execute_read("MATCH (n:File) RETURN count(n) AS c")
client.execute_write("MERGE (:Tag {name: $name})", {"name": "demo"})
```

This centralizes connection params, auth modes, and profiles.

## Add a migration

Schema lives in `scidk/core/migrations.py` and auto-runs on boot. Append a new versioned block at the end of `migrate()` — never edit past blocks:

```python
if version < 26:
    cur.execute("CREATE TABLE IF NOT EXISTS my_table (...);")
    conn.commit()
    _set_version(conn, 26)
    version = 26
```

`files`/index schema lives in `scidk/core/path_index_sqlite.py`.

## Logging

Use a module-level logger; do not use `print()`:

```python
import logging
logger = logging.getLogger(__name__)
logger.info("scan started: %s", path)
```

## Run tests

```bash
pytest tests/ -q          # unit + integration (what CI runs)
```

E2E (Playwright) is **local only** — disabled in CI as of Feb 2026:

```bash
npm run e2e               # or: pytest -m e2e
```
