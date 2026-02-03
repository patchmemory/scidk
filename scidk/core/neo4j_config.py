"""Neo4j configuration and backend initialization.

This module extracts Neo4j parameter parsing and graph backend creation
from app.py to keep application initialization modular.
"""

import os
from typing import Tuple, Optional


def get_neo4j_params(app) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str], str]:
    """Read Neo4j configuration, preferring in-app settings over environment.

    Args:
        app: Flask application instance with extensions['scidk']['neo4j_config']

    Returns:
        tuple: (uri, user, password, database, auth_mode)
        auth_mode: 'basic' (username+password) or 'none' (no authentication)
    """
    cfg = app.extensions['scidk'].get('neo4j_config', {})
    uri = cfg.get('uri') or os.environ.get('NEO4J_URI') or os.environ.get('BOLT_URI')
    user = cfg.get('user') or os.environ.get('NEO4J_USER') or os.environ.get('NEO4J_USERNAME')
    pwd = cfg.get('password') or os.environ.get('NEO4J_PASSWORD')
    database = cfg.get('database') or os.environ.get('SCIDK_NEO4J_DATABASE') or None

    # Parse NEO4J_AUTH env var if provided (formats: "user/pass" or "none")
    neo4j_auth = (os.environ.get('NEO4J_AUTH') or '').strip()
    if neo4j_auth:
        if neo4j_auth.lower() == 'none':
            user = user or None
            pwd = pwd or None
            auth_mode = 'none'
        else:
            try:
                # Expecting user/password
                parts = neo4j_auth.split('/')
                if len(parts) >= 2 and not (user and pwd):
                    user = user or parts[0]
                    pwd = pwd or '/'.join(parts[1:])
            except Exception:
                pass

    # If user/password still missing, try to parse from URI (bolt://user:pass@host:port)
    auth_mode = 'basic'
    try:
        if uri and (not user or not pwd):
            from urllib.parse import urlparse, unquote
            parsed = urlparse(uri)
            if parsed.username and parsed.password:
                user = user or unquote(parsed.username)
                pwd = pwd or unquote(parsed.password)
    except Exception:
        pass

    # Determine auth mode: none only when explicitly set via NEO4J_AUTH=none
    if (os.environ.get('NEO4J_AUTH') or '').strip().lower() == 'none':
        auth_mode = 'none'
    else:
        auth_mode = 'basic'

    return uri, user, pwd, database, auth_mode


def create_graph_backend(app):
    """Create and configure the graph backend (Neo4j or InMemory).

    Args:
        app: Flask application instance with logger

    Returns:
        Graph backend instance (Neo4jGraph or InMemoryGraph)
        Also sets backend name on app for reference
    """
    from ..core.graph import InMemoryGraph

    backend = (os.environ.get('SCIDK_GRAPH_BACKEND') or 'memory').strip().lower()

    if backend == 'neo4j':
        try:
            uri, user, pwd, database, auth_mode = get_neo4j_params(app)
            if not uri:
                raise ValueError("NEO4J_URI not configured")
            if auth_mode != 'none' and (not user or not pwd):
                raise ValueError("NEO4J credentials incomplete (NEO4J_USER/NEO4J_PASSWORD required)")

            from ..core.neo4j_graph import Neo4jGraph
            auth = None if auth_mode == 'none' else (user, pwd)
            graph = Neo4jGraph(uri=uri, auth=auth, database=database, auth_mode=auth_mode)
            app.logger.info(f"Graph backend: neo4j (uri={uri}, database={database})")
            app.config['graph_backend'] = 'neo4j'
            return graph
        except Exception as e:
            # Fallback to in-memory if neo4j params invalid
            app.logger.warning(f"SCIDK_GRAPH_BACKEND=neo4j but env incomplete or invalid ({e}); falling back to in-memory")
            graph = InMemoryGraph()
            app.config['graph_backend'] = 'memory'
            return graph
    else:
        graph = InMemoryGraph()
        if backend != 'memory':
            app.logger.warning(f"Unknown SCIDK_GRAPH_BACKEND={backend}; using in-memory")
        else:
            app.logger.info("Graph backend: in-memory")
        app.config['graph_backend'] = 'memory'
        return graph
