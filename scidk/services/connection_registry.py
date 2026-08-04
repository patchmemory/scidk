"""Registry of the graph backends SciDK talks to.

Cycle 4, Task A. Settings → Connections shows every graph backend as a peer
card, and this module is the single place that knows what those backends are.
Adding one — a UBERON or MGI reference brain, say — means appending one
:class:`GraphBackend` here; the API and the template are driven off
:func:`list_backends` and need no edit.

Nothing in this module opens its own Neo4j connection from scratch. Each backend
already has a canonical client factory that the rest of the app uses, and the
registry reuses it:

===============  =========================================================
backend          client factory
===============  =========================================================
research_graph   :func:`scidk.services.neo4j_client.get_neo4j_client`
chat_history     :func:`scidk.services.chat_neo4j_client.get_chat_neo4j_client`
concept_graph    ``app.extensions['scidk']['concept_driver']``, falling back
                 to :func:`scidk.services.concept_graph_service.get_concept_driver`
===============  =========================================================

so "Test Connection" exercises exactly the path a real query would take. The
three factories return three unrelated types, so each is wrapped in a
:class:`_Probe` that exposes one ``run(cypher)`` method.

Three levels of cost, kept separate on purpose:

``describe()``  pure config read, no I/O — safe on page load for every backend.
``verify()``    one ``RETURN 1`` round trip — the Test Connection button.
``counts()``    two aggregate queries that scan the whole store — on demand only,
                because on a large graph they are not cheap.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

#: Settings key holding the last time ``verify()`` succeeded for a backend.
#: Stored in the settings DB via :mod:`scidk.core.settings`, one row per
#: backend — no new table, no new model.
LAST_VERIFIED_KEY_PREFIX = 'connection_last_verified_'


class NotConfigured(Exception):
    """Raised by a probe factory when the backend has no connection details."""


class _Probe:
    """Uniform read-only handle over one backend's native client.

    ``owned`` is False for the app-level concept graph driver, which is shared
    across requests and must outlive this probe — closing it would break every
    later chat request.
    """

    def __init__(self, run: Callable[[str], List[Dict[str, Any]]],
                 close: Callable[[], None], owned: bool = True):
        self._run = run
        self._close = close
        self._owned = owned

    def run(self, cypher: str) -> List[Dict[str, Any]]:
        return self._run(cypher)

    def close(self) -> None:
        if not self._owned:
            return
        try:
            self._close()
        except Exception:
            pass


# ─────────────────────────────────────────────
# Per-backend config readers and probe factories
# ─────────────────────────────────────────────

def _describe_research_graph() -> Dict[str, Any]:
    from .neo4j_client import get_neo4j_params
    app = _current_app()
    uri, user, _pwd, database, auth_mode = get_neo4j_params(app)
    return {
        'configured': bool(uri),
        'uri': uri or '',
        'user': user or '',
        'database': database or '',
        'auth_mode': auth_mode,
    }


def _probe_research_graph() -> _Probe:
    from .neo4j_client import get_neo4j_client
    client = get_neo4j_client()
    if client is None:
        raise NotConfigured(
            'No Neo4j URI configured. Set one under Research Graph, or set NEO4J_URI.'
        )
    return _Probe(lambda q: client.execute_read(q), client.close)


def _describe_chat_history() -> Dict[str, Any]:
    from .chat_neo4j_client import get_chat_neo4j_params
    uri, user, _pwd = get_chat_neo4j_params()
    return {
        'configured': bool(uri),
        'uri': uri or '',
        'user': user or '',
        'database': '',
        'auth_mode': 'basic' if user else 'none',
    }


def _probe_chat_history() -> _Probe:
    from .chat_neo4j_client import get_chat_neo4j_client, get_chat_neo4j_params
    client = get_chat_neo4j_client()
    if client is None:
        uri, _user, _pwd = get_chat_neo4j_params()
        if not uri:
            raise NotConfigured(
                'Chat Neo4j not configured. Set CHAT_NEO4J_URI and CHAT_NEO4J_AUTH.'
            )
        raise RuntimeError('Chat Neo4j client could not be created — see server log.')
    return _Probe(lambda q: client.execute_read(q), client.close)


def _describe_concept_graph() -> Dict[str, Any]:
    # Mirrors the defaults in concept_graph_service.get_concept_driver() so the
    # card shows the URI that would actually be dialled, not a blank field.
    uri = os.environ.get('SCIDK_CONCEPT_NEO4J_URI', 'bolt://localhost:7689')
    auth_str = os.environ.get('SCIDK_CONCEPT_NEO4J_AUTH', 'neo4j/concept-graph-password')
    if auth_str.lower() == 'none':
        user, auth_mode = '', 'none'
    else:
        user = auth_str.split('/', 1)[0]
        auth_mode = 'basic'
    return {
        'configured': bool(uri),
        'uri': uri,
        'user': user,
        'database': '',
        'auth_mode': auth_mode,
    }


def _probe_concept_graph() -> _Probe:
    driver, owned = _concept_driver()
    if driver is None:
        raise RuntimeError(
            'Concept graph driver unavailable. Check SCIDK_CONCEPT_NEO4J_URI / '
            'SCIDK_CONCEPT_NEO4J_AUTH and the server log.'
        )

    def _run(cypher: str) -> List[Dict[str, Any]]:
        with driver.session() as session:
            return [dict(rec) for rec in session.run(cypher)]

    return _Probe(_run, driver.close, owned=owned)


def _concept_driver() -> Tuple[Optional[Any], bool]:
    """Return ``(driver, owned)``, preferring the app-level shared driver."""
    app = _current_app()
    if app is not None:
        try:
            shared = app.extensions['scidk'].get('concept_driver')
        except Exception:
            shared = None
        if shared is not None:
            return shared, False
    from .concept_graph_service import get_concept_driver
    return get_concept_driver(app), True


# ─────────────────────────────────────────────
# The registry
# ─────────────────────────────────────────────

@dataclass(frozen=True)
class GraphBackend:
    """One graph backend, as shown on a Connections card."""

    id: str
    name: str
    role: str
    description: str
    #: Sidebar subsection the card's "Manage" button jumps to, or '' for none.
    nav_section: str
    #: Environment variables that configure this backend, shown on the card when
    #: it is unconfigured so the fix is discoverable without reading the docs.
    env_vars: Tuple[str, ...]
    #: Returns the connection config as a dict. Pure read, no I/O.
    read_config: Callable[[], Dict[str, Any]] = field(repr=False)
    #: Opens a probe over this backend's canonical client factory.
    open_probe: Callable[[], _Probe] = field(repr=False)


BACKENDS: Tuple[GraphBackend, ...] = (
    GraphBackend(
        id='research_graph',
        name='Research Graph',
        role='Research data',
        description='Primary Neo4j store — scanned files, folders, datasets, and '
                    'everything committed from the Files and Maps pages.',
        nav_section='connections-neo4j',
        env_vars=('NEO4J_URI', 'NEO4J_USER', 'NEO4J_PASSWORD', 'SCIDK_NEO4J_DATABASE'),
        read_config=_describe_research_graph,
        open_probe=_probe_research_graph,
    ),
    GraphBackend(
        id='chat_history',
        name='Chat History',
        role='Chat audit graph',
        description='Chat sessions, messages, and query provenance — the audit '
                    'trail behind the Chat page.',
        nav_section='connections-chat-history',
        env_vars=('CHAT_NEO4J_URI', 'CHAT_NEO4J_AUTH'),
        read_config=_describe_chat_history,
        open_probe=_probe_chat_history,
    ),
    GraphBackend(
        id='concept_graph',
        name='Concept Graph',
        role='System self-knowledge',
        description='Intents, tools, and learned weights used to plan queries.',
        nav_section='connections-concept-graph',
        env_vars=('SCIDK_CONCEPT_NEO4J_URI', 'SCIDK_CONCEPT_NEO4J_AUTH'),
        read_config=_describe_concept_graph,
        open_probe=_probe_concept_graph,
    ),
)


def list_backends() -> Tuple[GraphBackend, ...]:
    """Every registered graph backend, in display order."""
    return BACKENDS


def get_backend(backend_id: str) -> Optional[GraphBackend]:
    for backend in BACKENDS:
        if backend.id == backend_id:
            return backend
    return None


# ─────────────────────────────────────────────
# Describe / verify / counts
# ─────────────────────────────────────────────

def describe(backend: GraphBackend) -> Dict[str, Any]:
    """Config-only view of one backend. No network I/O, never raises."""
    info: Dict[str, Any] = {
        'id': backend.id,
        'name': backend.name,
        'role': backend.role,
        'description': backend.description,
        'nav_section': backend.nav_section,
        'env_vars': list(backend.env_vars),
        'configured': False,
        'uri': '',
        'user': '',
        'database': '',
        'auth_mode': 'basic',
        'config_error': None,
        'last_verified': get_last_verified(backend.id),
    }
    try:
        info.update(backend.read_config())
    except Exception as e:  # a broken config must not blank the whole page
        logger.warning("Could not read config for backend %s: %s", backend.id, e)
        info['config_error'] = str(e)
    return info


def describe_all() -> List[Dict[str, Any]]:
    return [describe(b) for b in list_backends()]


def verify(backend: GraphBackend) -> Dict[str, Any]:
    """Round-trip ``RETURN 1`` through the backend's own client factory.

    Returns ``{ok, error, latency_ms}``. Never raises — a Connections page that
    500s because one backend is down would be worse than useless.
    """
    started = time.time()
    probe = None
    try:
        probe = backend.open_probe()
        rows = probe.run('RETURN 1 AS ok')
        ok = bool(rows) and rows[0].get('ok') == 1
        latency_ms = int((time.time() - started) * 1000)
        if not ok:
            return {'ok': False, 'error': 'Probe query returned no result', 'latency_ms': latency_ms}
        touch_last_verified(backend.id)
        return {'ok': True, 'error': None, 'latency_ms': latency_ms}
    except NotConfigured as e:
        return {'ok': False, 'error': str(e), 'latency_ms': None}
    except Exception as e:
        return {
            'ok': False,
            'error': str(e) or e.__class__.__name__,
            'latency_ms': int((time.time() - started) * 1000),
        }
    finally:
        if probe is not None:
            probe.close()


def counts(backend: GraphBackend) -> Dict[str, Any]:
    """Node and relationship totals. Returns ``{nodes, edges, error}``.

    The relationship pattern is directed on purpose: ``MATCH ()-[r]-()`` matches
    each relationship once per direction and reports double the real count.
    """
    probe = None
    try:
        probe = backend.open_probe()
        node_rows = probe.run('MATCH (n) RETURN count(n) AS c')
        edge_rows = probe.run('MATCH ()-[r]->() RETURN count(r) AS c')
        return {
            'nodes': int(node_rows[0]['c']) if node_rows else None,
            'edges': int(edge_rows[0]['c']) if edge_rows else None,
            'error': None,
        }
    except NotConfigured as e:
        return {'nodes': None, 'edges': None, 'error': str(e)}
    except Exception as e:
        return {'nodes': None, 'edges': None, 'error': str(e) or e.__class__.__name__}
    finally:
        if probe is not None:
            probe.close()


# ─────────────────────────────────────────────
# "Last verified" persistence
# ─────────────────────────────────────────────

def get_last_verified(backend_id: str) -> Optional[str]:
    try:
        from ..core.settings import get_setting
        return get_setting(LAST_VERIFIED_KEY_PREFIX + backend_id)
    except Exception:
        return None


def touch_last_verified(backend_id: str) -> Optional[str]:
    """Record a successful verification. Best-effort — failure is not fatal."""
    stamp = datetime.now(tz=timezone.utc).isoformat()
    try:
        from ..core.settings import set_setting
        set_setting(LAST_VERIFIED_KEY_PREFIX + backend_id, stamp)
        return stamp
    except Exception as e:
        logger.warning("Could not persist last_verified for %s: %s", backend_id, e)
        return None


def _current_app():
    try:
        from flask import current_app
        return current_app._get_current_object()
    except Exception:
        return None
