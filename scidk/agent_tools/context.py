"""Build a ToolContext inside the web app (HTTP adapter, SciDK's own chat)."""
from __future__ import annotations

import threading
from typing import Any, Optional

from .registry import ToolContext

_lock = threading.Lock()


def _driver(app) -> Any:
    """A Neo4j driver for the configured graph, reused across calls; None if no
    graph is configured. Rebuilt when the connection settings change."""
    from ..services.neo4j_client import get_neo4j_params
    uri, user, password, database, auth_mode = get_neo4j_params(app)
    if not uri:
        return None, None
    key = (uri, user, password, auth_mode)
    ext = app.extensions.setdefault('scidk', {})
    with _lock:
        cached = ext.get('agent_neo4j')
        if cached and cached[0] == key:
            return cached[1], database
        from neo4j import GraphDatabase
        auth = None if auth_mode == 'none' or not user else (user, password)
        driver = GraphDatabase.driver(uri, auth=auth)
        if cached:
            try:
                cached[1].close()
            except Exception:  # noqa: BLE001
                pass
        ext['agent_neo4j'] = (key, driver)
        return driver, database


def context_from_app(app, user: Optional[str] = None) -> ToolContext:
    from .security import identity_from_request
    db = app.config.get('SCIDK_SETTINGS_DB', 'scidk_settings.db')
    try:
        identity = identity_from_request(db, channel='http')
    except Exception:
        identity = None
    # Refused legacy queries must not initialize graph drivers or touch files.db.
    return ToolContext(settings_db=db, identity=identity)
