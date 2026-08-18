"""
Schema Intelligence Layer
Phases 1-3 + 6: Usage logging, property ranking, label profiles, semantic embeddings

The primary Neo4j graph is always the source of truth.
This layer only shapes how schema is surfaced to consumers.
"""

import json
import logging
import sqlite3
import re
from datetime import datetime
from typing import Optional, Dict, List, Any

import numpy as np
import requests

logger = logging.getLogger(__name__)

EMBED_MODEL = 'nomic-embed-text'
OLLAMA_EMBED_ENDPOINT = '/api/embeddings'
DEFAULT_TOP_K = 5


# ─────────────────────────────────────────────
# PHASE 0: Table Creation
# ─────────────────────────────────────────────
#
# These four tables live in scidk_settings.db, NOT files.db — do not route them
# through core/migrations.py. This module owns the DDL; it is the single source
# of truth. (An orphaned copy previously sat in core/migrations/schema_intelligence.sql
# with no caller, so on any clean deploy the whole layer silently degraded:
# log_query_usage swallowed its insert failure and get_ranked_properties fell
# back to unranked order.)

SI_TABLE_DDL = (
    # Phase 1: Raw usage event log (append-only)
    """
    CREATE TABLE IF NOT EXISTS usage_event (
        id              INTEGER PRIMARY KEY,
        event_type      TEXT NOT NULL,  -- 'query_executed' | 'concept_graph_plan'
        label_name      TEXT NOT NULL,
        property_name   TEXT,           -- NULL for label-level events
        session_id      TEXT,
        source          TEXT,           -- 'chat' | 'labels_ui'
        traversal_json  TEXT,           -- Concept Graph traversal metadata
        created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """,
    # Phase 2+3+6: Per-label enrichment, ranking, and embeddings
    """
    CREATE TABLE IF NOT EXISTS label_profile (
        id                INTEGER PRIMARY KEY,
        label_name        TEXT UNIQUE NOT NULL,
        description       TEXT,
        chat_context_mode TEXT DEFAULT 'top_n',  -- 'top_n'|'all'|'exclude'
        chat_context_n    INTEGER DEFAULT 5,
        always_include    TEXT,   -- JSON array: ["treatment", "genotype"]
        never_include     TEXT,   -- JSON array: ["_imported_stub"]
        embedding         BLOB,
        embedding_model   TEXT,
        embedding_text    TEXT,
        embedded_at       DATETIME,
        created_at        DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at        DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """,
    # Phase 2: Usage-weighted property ranking per label
    """
    CREATE TABLE IF NOT EXISTS property_ranking (
        id            INTEGER PRIMARY KEY,
        label_name    TEXT NOT NULL,
        property_name TEXT NOT NULL,
        query_count   INTEGER DEFAULT 0,
        session_count INTEGER DEFAULT 0,
        last_used_at  DATETIME,
        rank          REAL DEFAULT 0.0,
        UNIQUE (label_name, property_name)
    )
    """,
    # Phase 6: Relationship type embeddings
    """
    CREATE TABLE IF NOT EXISTS relationship_profile (
        id              INTEGER PRIMARY KEY,
        rel_type        TEXT UNIQUE NOT NULL,
        description     TEXT,
        embedding       BLOB,
        embedding_model TEXT,
        embedding_text  TEXT,
        embedded_at     DATETIME,
        created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """,
    # Indexes
    "CREATE INDEX IF NOT EXISTS idx_usage_event_label ON usage_event(label_name, property_name)",
    "CREATE INDEX IF NOT EXISTS idx_usage_event_session ON usage_event(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_property_ranking_label ON property_ranking(label_name)",
    "CREATE INDEX IF NOT EXISTS idx_label_profile_embedding "
    "ON label_profile(embedding) WHERE embedding IS NOT NULL",
)

# Columns added after a table's first release. Databases created before the
# column existed get it back-filled via ALTER TABLE; new databases already have
# it from SI_TABLE_DDL. Keyed by table, then column -> column definition.
SI_ADDED_COLUMNS = {
    'usage_event': {
        # Was migrations.py v25, which ALTERed a table that did not exist yet on
        # a clean deploy and swallowed the OperationalError.
        'traversal_json': 'TEXT',
    },
}


def ensure_schema_intelligence_tables(sqlite_conn: sqlite3.Connection) -> None:
    """Create the four Schema Intelligence tables if they are missing.

    Idempotent — safe to call on every startup. Uses CREATE TABLE IF NOT EXISTS
    for tables and PRAGMA table_info + ALTER TABLE for columns added to tables
    that already exist in older databases.

    Raises on failure: if the SI tables cannot be created the layer is inert,
    and callers at startup should see that rather than degrade silently.
    """
    cursor = sqlite_conn.cursor()

    for statement in SI_TABLE_DDL:
        cursor.execute(statement)

    for table, columns in SI_ADDED_COLUMNS.items():
        existing = {row[1] for row in
                    cursor.execute(f"PRAGMA table_info({table})").fetchall()}
        for column, coltype in columns.items():
            if column not in existing:
                cursor.execute(
                    f"ALTER TABLE {table} ADD COLUMN {column} {coltype}"
                )
                logger.info(
                    f"ensure_schema_intelligence_tables: added "
                    f"{table}.{column}"
                )

    sqlite_conn.commit()


# ─────────────────────────────────────────────
# PHASE 1: Usage Event Logging
# ─────────────────────────────────────────────

# A node pattern: optional alias, optional :Label chain, optional {prop: val} map.
# Matches (p:Project), (:Project), (p), (p:Project:Archived {id: 1}) — and also
# bare parens like the (n) inside count(n), which bind nothing and are harmless.
_NODE_PATTERN = re.compile(
    r'\(\s*(\w*)\s*((?::\s*\w+\s*)*)(?:\{([^}]*)\})?\s*\)'
)

# alias.property access. The alias must start with a letter or underscore so that
# numeric literals like 1.5 are not read as a property access.
_PROPERTY_ACCESS = re.compile(r'\b([A-Za-z_]\w*)\.(\w+)')


def extract_labels_and_properties(cypher: str) -> Dict[str, List[str]]:
    """
    Parse a Cypher query and extract which labels and properties
    were referenced. Returns dict: {label_name: [prop1, prop2, ...]}

    Properties are attributed to the label their alias is bound to, by reading
    the variable->label binding out of the node patterns. For

        MATCH (p:Project)-[:PI_OF]-(u:Person) RETURN p.cac_protocol, u.email

    cac_protocol is logged against Project only and email against Person only.

    Aliases that carry no label (``MATCH (n) RETURN n.foo``), aliases introduced
    downstream by ``WITH ... AS``, and relationship aliases (``r.since``) are not
    attributable to a label, so their properties are dropped rather than spread
    across every label in the query. Under-counting is the safe direction here:
    property_ranking feeds the chat schema context, where a wrong property costs
    more than a missing one.

    Simple regex approach — not a full Cypher parser, but covers the common
    patterns generated by the ReAct loop. It does not track alias rebinding or
    ignore string literals.
    """
    result: Dict[str, List[str]] = {}
    alias_to_labels: Dict[str, List[str]] = {}

    def record(label: str, prop: Optional[str] = None) -> None:
        props = result.setdefault(label, [])
        if prop and prop not in props:
            props.append(prop)

    # Pass 1: node patterns — collect labels, bind aliases, and take inline
    # {prop: val} properties, which belong to the labels on that same pattern.
    for match in _NODE_PATTERN.finditer(cypher):
        alias = match.group(1)
        labels = [seg.strip() for seg in (match.group(2) or '').split(':')
                  if seg.strip()]
        if not labels:
            # e.g. (n) in count(n), or an unlabelled MATCH (n) — binds nothing.
            continue

        inline = [p.split(':', 1)[0].strip()
                  for p in (match.group(3) or '').split(',') if ':' in p]

        for label in labels:
            record(label)
            for prop in inline:
                if prop:
                    record(label, prop)

        if alias:
            bound = alias_to_labels.setdefault(alias, [])
            for label in labels:
                if label not in bound:
                    bound.append(label)

    # Pass 2: alias.property access, attributed only to that alias's labels.
    # Anything not bound in pass 1 — relationship aliases (r.since), unlabelled
    # nodes, WITH ... AS aliases, procedure namespaces (db.labels) — resolves to
    # an empty label list and contributes nothing.
    for match in _PROPERTY_ACCESS.finditer(cypher):
        alias, prop = match.group(1), match.group(2)
        for label in alias_to_labels.get(alias, ()):
            record(label, prop)

    return result


def log_query_usage(cypher: str, session_id: str,
                    sqlite_conn: sqlite3.Connection,
                    source: str = 'chat') -> None:
    """
    Append usage_event rows for each label and property
    referenced in a Cypher query. Called after every query executes.

    Never fails — swallows all exceptions to protect query execution.
    """
    try:
        touched = extract_labels_and_properties(cypher)
        cursor = sqlite_conn.cursor()
        now = datetime.utcnow()

        for label, properties in touched.items():
            # Label-level event
            cursor.execute(
                "INSERT INTO usage_event "
                "(event_type, label_name, property_name, session_id, source, created_at) "
                "VALUES (?, ?, NULL, ?, ?, ?)",
                ('query_executed', label, session_id, source, now)
            )
            # Property-level events
            for prop in properties:
                cursor.execute(
                    "INSERT INTO usage_event "
                    "(event_type, label_name, property_name, session_id, source, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    ('query_executed', label, prop, session_id, source, now)
                )

        sqlite_conn.commit()
    except Exception as e:
        logger.warning(f"Failed to log query usage: {e}")
        # Never fail a query because of logging


# ─────────────────────────────────────────────
# PHASE 2: Ranking Computation
# ─────────────────────────────────────────────

def flush_rankings(sqlite_conn: sqlite3.Connection) -> Dict[str, int]:
    """
    Aggregate usage_event into property_ranking counts.
    rank = query_count * 1.0 + session_count * 2.0
    (session diversity weighted higher than raw count)

    Safe to call repeatedly — upserts.
    Run periodically (e.g. every 50 queries) or on demand.
    """
    cursor = sqlite_conn.cursor()

    # Aggregate from usage_event
    rows = cursor.execute("""
        SELECT label_name, property_name,
               COUNT(*) AS query_count,
               COUNT(DISTINCT session_id) AS session_count,
               MAX(created_at) AS last_used_at
        FROM usage_event
        WHERE event_type = 'query_executed'
          AND property_name IS NOT NULL
        GROUP BY label_name, property_name
    """).fetchall()

    updated = 0
    for label, prop, qcount, scount, last_used in rows:
        rank = qcount * 1.0 + scount * 2.0
        cursor.execute("""
            INSERT INTO property_ranking
                (label_name, property_name, query_count,
                 session_count, last_used_at, rank)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(label_name, property_name) DO UPDATE SET
                query_count = excluded.query_count,
                session_count = excluded.session_count,
                last_used_at = excluded.last_used_at,
                rank = excluded.rank
        """, (label, prop, qcount, scount, last_used, rank))
        updated += 1

    sqlite_conn.commit()
    logger.info(f"flush_rankings: updated {updated} property rankings")
    return {'updated': updated}


def get_ranked_properties(label_name: str,
                           sqlite_conn: sqlite3.Connection,
                           all_properties: List[str],
                           top_n: int = 5,
                           always_include: List[str] = None,
                           never_include: List[str] = None) -> List[str]:
    """
    Return properties for a label ordered by usage rank.
    Applies always_include pins and never_include exclusions.
    Falls back to original order if no ranking data exists.
    """
    always_include = always_include or []
    never_include = never_include or []

    # Get ranked properties from SQLite
    rows = sqlite_conn.cursor().execute("""
        SELECT property_name FROM property_ranking
        WHERE label_name = ?
        ORDER BY rank DESC
    """, (label_name,)).fetchall()

    ranked = [r[0] for r in rows]

    # Build final list: pinned first, then ranked, then unranked
    pinned = [p for p in always_include if p in all_properties
              and p not in never_include]
    ranked_filtered = [p for p in ranked
                       if p in all_properties
                       and p not in never_include
                       and p not in pinned]
    unranked = [p for p in all_properties
                if p not in ranked
                and p not in never_include
                and p not in pinned]

    combined = pinned + ranked_filtered + unranked

    # Apply top_n limit (but always keep pinned)
    if top_n and top_n > 0:
        result = pinned + [p for p in combined
                           if p not in pinned][:top_n - len(pinned)]
    else:
        result = combined

    return result if result else all_properties[:top_n]


# ─────────────────────────────────────────────
# PHASE 3: Label Profiles
# ─────────────────────────────────────────────

def get_label_profile(label_name: str,
                       sqlite_conn: sqlite3.Connection) -> Dict[str, Any]:
    """Return label profile dict, or defaults if none exists."""
    row = sqlite_conn.cursor().execute(
        "SELECT description, chat_context_mode, chat_context_n, "
        "always_include, never_include "
        "FROM label_profile WHERE label_name = ?",
        (label_name,)
    ).fetchone()

    if not row:
        return {
            'description': None,
            'chat_context_mode': 'top_n',
            'chat_context_n': 5,
            'always_include': [],
            'never_include': []
        }

    return {
        'description': row[0],
        'chat_context_mode': row[1] or 'top_n',
        'chat_context_n': row[2] or 5,
        'always_include': json.loads(row[3]) if row[3] else [],
        'never_include': json.loads(row[4]) if row[4] else []
    }


def get_enriched_schema_context(neo4j_driver,
                                  sqlite_conn: sqlite3.Connection,
                                  database: str = "neo4j") -> Dict[str, Any]:
    """
    Phase 2+3: Return schema context with ranked and filtered properties.
    Replaces raw get_schema_context() call.
    Falls back gracefully if SQLite data is unavailable.
    """
    # Import the existing schema function
    from ..ai.schema_context import get_schema_context
    raw = get_schema_context(neo4j_driver, database=database)

    enriched_properties = {}

    for label in raw.get('labels', []):
        profile = get_label_profile(label, sqlite_conn)

        if profile['chat_context_mode'] == 'exclude':
            continue  # Skip this label entirely

        all_props = raw.get('properties', {}).get(label, [])
        top_n = profile['chat_context_n']

        enriched_properties[label] = get_ranked_properties(
            label_name=label,
            sqlite_conn=sqlite_conn,
            all_properties=all_props,
            top_n=top_n,
            always_include=profile['always_include'],
            never_include=profile['never_include']
        )

    return {
        **raw,
        'properties': enriched_properties,
        'descriptions': {
            label: get_label_profile(label, sqlite_conn)['description']
            for label in raw.get('labels', [])
            if get_label_profile(label, sqlite_conn)['description']
        }
    }


# ─────────────────────────────────────────────
# PHASE 6: Semantic Schema Embeddings
# ─────────────────────────────────────────────

def embed_text(text: str, ollama_url: str,
               model: str = EMBED_MODEL) -> Optional[List[float]]:
    """Call Ollama embeddings API. Returns float list or None."""
    try:
        resp = requests.post(
            f"{ollama_url.rstrip('/')}{OLLAMA_EMBED_ENDPOINT}",
            json={"model": model, "prompt": text},
            timeout=30
        )
        resp.raise_for_status()
        return resp.json().get('embedding')
    except Exception as e:
        logger.warning(f"Embedding failed ({model}): {e}")
        return None


def _vector_to_blob(v: List[float]) -> bytes:
    """Convert float list to numpy blob for SQLite storage."""
    return np.array(v, dtype=np.float32).tobytes()


def _blob_to_vector(b: bytes) -> np.ndarray:
    """Convert SQLite blob back to numpy array."""
    return np.frombuffer(b, dtype=np.float32)


def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two vectors."""
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a / na, b / nb))


def build_label_embedding_text(label_name: str,
                                 properties: List[str],
                                 relationships: List[Dict[str, str]],
                                 description: Optional[str] = None) -> str:
    """Build natural language text for embedding a label."""
    parts = []
    if description:
        parts.append(description)
    else:
        parts.append(f"{label_name} nodes in the research knowledge graph.")
    if properties:
        parts.append(f"Properties: {', '.join(properties[:10])}.")
    if relationships:
        rel_strs = [f"{r.get('type', '?')} to {r.get('target', '?')}"
                    for r in relationships[:5]]
        parts.append(f"Connected via: {', '.join(rel_strs)}.")
    return ' '.join(parts)


def refresh_schema_embeddings(neo4j_driver,
                               sqlite_conn: sqlite3.Connection,
                               ollama_url: str,
                               database: str = "neo4j") -> Dict[str, int]:
    """
    Re-embed all labels and relationship types.
    Safe to call repeatedly — upserts.

    Trigger on: manual Settings refresh, new import, description edit.
    """
    from ..ai.schema_context import get_schema_context
    raw = get_schema_context(neo4j_driver, database=database)
    cursor = sqlite_conn.cursor()

    embedded, failed = 0, 0

    # Embed labels
    for label in raw.get('labels', []):
        profile = get_label_profile(label, sqlite_conn)
        props = raw.get('properties', {}).get(label, [])

        # Build relationship list for this label
        rels = []
        all_rels = raw.get('relationships', [])
        # Since raw schema just has relationship type strings, we construct minimal dicts
        for rel_type in all_rels:
            # Simplified: we don't have source/target in the basic schema
            # Just include the relationship type in embedding text
            rels.append({'type': rel_type, 'target': '?'})

        text = build_label_embedding_text(
            label, props, rels[:5], profile.get('description')
        )
        vector = embed_text(text, ollama_url)

        if vector is None:
            failed += 1
            continue

        cursor.execute("""
            INSERT INTO label_profile
                (label_name, embedding, embedding_model,
                 embedding_text, embedded_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(label_name) DO UPDATE SET
                embedding = excluded.embedding,
                embedding_model = excluded.embedding_model,
                embedding_text = excluded.embedding_text,
                embedded_at = excluded.embedded_at,
                updated_at = CURRENT_TIMESTAMP
        """, (label, _vector_to_blob(vector),
              EMBED_MODEL, text, datetime.utcnow()))
        embedded += 1

    # Embed relationship types
    for rel_type in raw.get('relationships', []):
        if not rel_type:
            continue
        # Build relationship embedding text (simplified without source/target)
        text = (f"{rel_type} is a relationship type "
                f"in the research knowledge graph.")
        vector = embed_text(text, ollama_url)

        if vector is None:
            failed += 1
            continue

        cursor.execute("""
            INSERT INTO relationship_profile
                (rel_type, embedding, embedding_model,
                 embedding_text, embedded_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(rel_type) DO UPDATE SET
                embedding = excluded.embedding,
                embedding_model = excluded.embedding_model,
                embedding_text = excluded.embedding_text,
                embedded_at = excluded.embedded_at
        """, (rel_type, _vector_to_blob(vector),
              EMBED_MODEL, text, datetime.utcnow()))
        embedded += 1

    sqlite_conn.commit()
    logger.info(f"refresh_schema_embeddings: {embedded} embedded, {failed} failed")

    # Clear schema cache so next request picks up fresh context
    from ..ai.schema_context import refresh_schema_cache
    refresh_schema_cache()
    logger.info("Schema cache cleared after embedding refresh")

    return {'embedded': embedded, 'failed': failed}


def get_relevant_schema_context(user_query: str,
                                  sqlite_conn: sqlite3.Connection,
                                  neo4j_driver,
                                  ollama_url: str,
                                  database: str = "neo4j",
                                  top_k: int = DEFAULT_TOP_K) -> Dict[str, Any]:
    """
    Phase 6: Retrieve only schema components relevant to user_query.
    Falls back to get_enriched_schema_context() if embeddings unavailable.
    """
    import os
    top_k = int(os.environ.get('SCIDK_SCHEMA_TOP_K', top_k))

    query_vector = embed_text(user_query, ollama_url)
    if query_vector is None:
        logger.debug("Schema retrieval: fallback (embed unavailable)")
        return get_enriched_schema_context(neo4j_driver, sqlite_conn, database)

    cursor = sqlite_conn.cursor()
    q = np.array(query_vector, dtype=np.float32)

    # Search labels
    label_rows = cursor.execute(
        "SELECT label_name, embedding, description "
        "FROM label_profile WHERE embedding IS NOT NULL"
    ).fetchall()

    if not label_rows:
        logger.debug("Schema retrieval: fallback (no embeddings)")
        return get_enriched_schema_context(neo4j_driver, sqlite_conn, database)

    label_scores = sorted(
        [(name, _cosine_sim(q, _blob_to_vector(blob)), desc)
         for name, blob, desc in label_rows],
        key=lambda x: x[1], reverse=True
    )
    top_labels = label_scores[:top_k]
    selected_names = [name for name, _, _ in top_labels]

    # Search relationships
    rel_rows = cursor.execute(
        "SELECT rel_type, embedding FROM relationship_profile "
        "WHERE embedding IS NOT NULL"
    ).fetchall()
    rel_scores = sorted(
        [(rt, _cosine_sim(q, _blob_to_vector(blob)))
         for rt, blob in rel_rows],
        key=lambda x: x[1], reverse=True
    )
    top_rels = [rt for rt, _ in rel_scores[:top_k]]

    # Get enriched properties for selected labels only
    from ..ai.schema_context import get_schema_context
    raw = get_schema_context(neo4j_driver, database=database)

    properties = {}
    for name in selected_names:
        profile = get_label_profile(name, sqlite_conn)
        all_props = raw.get('properties', {}).get(name, [])
        properties[name] = get_ranked_properties(
            label_name=name,
            sqlite_conn=sqlite_conn,
            all_properties=all_props,
            top_n=profile['chat_context_n'],
            always_include=profile['always_include'],
            never_include=profile['never_include']
        )

    scores = {name: round(score, 3) for name, score, _ in top_labels}
    logger.debug(f"Schema retrieval: {selected_names} scores={scores}")

    return {
        'labels': selected_names,
        'relationships': top_rels,
        'properties': properties,
        'descriptions': {name: desc for name, _, desc in top_labels if desc},
        'retrieval_method': 'semantic',
        'scores': scores,
        'cached': False,
        'cached_at': None
    }


# ─────────────────────────────────────────────
# PHASE 4+5: Export/Import Schema Layer
# ─────────────────────────────────────────────

def export_schema_layer(sqlite_conn: sqlite3.Connection) -> Dict[str, Any]:
    """
    Export complete schema intelligence layer to portable JSON.

    Returns:
        {
            "scidk_schema_layer": "1.0",
            "exported_at": ISO timestamp,
            "source_instance": hostname or "unknown",
            "label_profiles": [...],
            "property_rankings": {...}
        }
    """
    import socket
    cursor = sqlite_conn.cursor()

    # Get all label profiles
    label_profiles = []
    profile_rows = cursor.execute("""
        SELECT label_name, description, chat_context_mode, chat_context_n,
               always_include, never_include
        FROM label_profile
    """).fetchall()

    for row in profile_rows:
        label_profiles.append({
            'label': row[0],
            'description': row[1],
            'chat_context_mode': row[2] or 'top_n',
            'chat_context_n': row[3] or 5,
            'always_include': json.loads(row[4]) if row[4] else [],
            'never_include': json.loads(row[5]) if row[5] else []
        })

    # Get all property rankings
    property_rankings = {}
    ranking_rows = cursor.execute("""
        SELECT label_name, property_name, rank
        FROM property_ranking
        ORDER BY label_name, rank DESC
    """).fetchall()

    for row in ranking_rows:
        label = row[0]
        if label not in property_rankings:
            property_rankings[label] = []
        property_rankings[label].append({
            'property': row[1],
            'rank': row[2]
        })

    # Get hostname for source tracking
    try:
        hostname = socket.gethostname()
    except:
        hostname = "unknown"

    return {
        'scidk_schema_layer': '1.0',
        'exported_at': datetime.utcnow().isoformat() + 'Z',
        'source_instance': hostname,
        'label_profiles': label_profiles,
        'property_rankings': property_rankings
    }


def import_schema_layer(layer: Dict[str, Any],
                        sqlite_conn: sqlite3.Connection,
                        ollama_url: str = None) -> Dict[str, Any]:
    """
    Import schema intelligence layer from JSON.
    Non-destructive upsert — updates existing profiles, creates new ones.

    Args:
        layer: Exported schema layer JSON
        sqlite_conn: SQLite connection
        ollama_url: Ollama endpoint for re-embedding (optional)

    Returns:
        {
            imported_labels: int,
            updated_labels: int,
            skipped: int,
            embeddings_triggered: int
        }
    """
    if layer.get('scidk_schema_layer') != '1.0':
        raise ValueError("Invalid schema layer format")

    cursor = sqlite_conn.cursor()
    imported = 0
    updated = 0
    skipped = 0
    embeddings_triggered = 0

    # Import label profiles
    for profile in layer.get('label_profiles', []):
        label = profile.get('label')
        if not label:
            skipped += 1
            continue

        # Check if profile exists
        existing = cursor.execute(
            "SELECT description FROM label_profile WHERE label_name = ?",
            (label,)
        ).fetchone()

        description_changed = False
        if existing:
            updated += 1
            description_changed = existing[0] != profile.get('description')
        else:
            imported += 1

        # Upsert profile
        cursor.execute("""
            INSERT INTO label_profile
            (label_name, description, chat_context_mode, chat_context_n,
             always_include, never_include)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(label_name) DO UPDATE SET
                description = excluded.description,
                chat_context_mode = excluded.chat_context_mode,
                chat_context_n = excluded.chat_context_n,
                always_include = excluded.always_include,
                never_include = excluded.never_include,
                updated_at = CURRENT_TIMESTAMP
        """, (
            label,
            profile.get('description'),
            profile.get('chat_context_mode', 'top_n'),
            profile.get('chat_context_n', 5),
            json.dumps(profile.get('always_include', [])),
            json.dumps(profile.get('never_include', []))
        ))

        # Re-embed if description changed and we have Ollama
        if description_changed and profile.get('description') and ollama_url:
            vector = embed_text(profile.get('description'), ollama_url)
            if vector:
                cursor.execute("""
                    UPDATE label_profile
                    SET embedding = ?, embedded_at = ?
                    WHERE label_name = ?
                """, (_vector_to_blob(vector), datetime.utcnow(), label))
                embeddings_triggered += 1

    # Import property rankings
    for label, rankings in layer.get('property_rankings', {}).items():
        # Delete existing rankings for this label
        cursor.execute("DELETE FROM property_ranking WHERE label_name = ?", (label,))

        # Insert new rankings
        for ranking in rankings:
            cursor.execute("""
                INSERT INTO property_ranking (label_name, property_name, rank, query_count)
                VALUES (?, ?, ?, ?)
            """, (label, ranking['property'], ranking['rank'], 0))  # query_count is reset

    sqlite_conn.commit()

    return {
        'imported_labels': imported,
        'updated_labels': updated,
        'skipped': skipped,
        'embeddings_triggered': embeddings_triggered
    }
