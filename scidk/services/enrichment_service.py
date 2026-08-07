"""Post-scan enrichment dispatcher.

A scan records *that* a file could be interpreted; it does not always run the
interpreter. This walks the index afterwards and does, in two passes:

* **Pass 1** — file-level interpreters. Each produces an
  :class:`~scidk.interpreters.base.InterpretationResult`, which is written to
  three places: the ``files`` row (SQLite), an ``Interpretation`` node with its
  ``INTERPRETED_AS`` edge, and the declared domain node itself (``FCSFile``,
  ``HistologySlide``).
* **Pass 2** — directory-level interpreters, over the parents of everything
  pass 1 touched, handed the pass-1 results as ``sibling_interpretations``. A
  session node cannot be built from a directory listing; it is a roll-up of the
  files inside it, so it has to run second and it has to see pass 1's output.

Usage (standalone)::

    python -m scidk.services.enrichment_service --interpreter fcs_interpreter \\
                                                --limit 500 [--scan-id <id>]

Usage (HTTP)::

    POST /api/enrichment/run   {"interpreter": "fcs_interpreter", "limit": 500}

Finding work
------------
The design intent was "files whose ``interpreted_as`` is set but which have no
rich ``Interpretation`` node yet". That covers files scanned before the
interpretation payload was persisted, and files re-scanned after a new
interpreter landed.

It is not sufficient on its own. On the AIPT index — 27M rows — **zero** rows
have ``interpreted_as`` set, because the rows predate the column: the 1,334
``.fcs`` and 82 ``.svs`` files that this exists to enrich would all be invisible
to that query. So a row also qualifies when its extension maps to the requested
interpreter through ``scanner_formats.KNOWN_INTERPRETERS``, which is the same
table the scanner would have used. ``interpreted_as`` still wins when set —
it records what the scanner actually decided, including a magic-byte match on a
file with no extension.

Neither predicate is indexed (``idx_files_scan_ext`` is on
``(scan_id, file_extension)``), so an unfiltered run full-scans the table:
roughly 6 seconds for 27M rows. Passing ``--scan-id`` uses the index.
"""
from __future__ import annotations

import argparse
import inspect
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

__all__ = ["run_enrichment"]

#: Neo4j is asked about already-enriched paths in chunks; a 500-element IN list
#: is comfortable and the default limit fits in one round trip.
_PATH_CHUNK = 500


# ─────────────────────────────────────────────────────────────────────────────
# Work discovery
# ─────────────────────────────────────────────────────────────────────────────

def _extensions_for(interpreter_id: Optional[str]) -> List[str]:
    """Extensions that ``KNOWN_INTERPRETERS`` routes to this interpreter.

    With no interpreter given, every extension that names *some* interpreter —
    the None values there mean "recognised, nothing reads it" and are gaps by
    definition, not work.
    """
    from ..core.scanner_formats import KNOWN_INTERPRETERS
    return sorted(
        ext for ext, interp in KNOWN_INTERPRETERS.items()
        if interp and (interpreter_id is None or interp == interpreter_id)
    )


def _row_host(remote: Optional[str]) -> str:
    """The host a file's ``:File`` node is keyed on. Comes from ``files.remote``.

    Getting this right is not cosmetic. ``(path, host)`` is the File node's
    identity and the composite ``file_identity`` index covers both properties;
    Neo4j cannot serve a composite index from a partial pattern, so a lookup
    missing the host full-scans the label. Measured against 5.5M File nodes:
    3.72s by path alone, 0.01s by ``(path, host)`` — and enrichment pays it
    twice per file, once for the Interpretation edge and once for the
    provenance edge, which is the whole 8–12s/file cost.

    ``files.remote`` holds the host per row (``mounted:/mnt/server`` across all
    23.7M rows of the AIPT mount scan) and matches ``:File.host``, which
    ``neo4j_client.write_scan`` sets from the scan's ``host_id``. Reading it off
    the row also drops a join against ``scans`` on a 27M-row table — and that
    join was unusable here anyway: one of the two scans holding the imaging
    files has no ``scans`` row at all.
    """
    return (remote or '').strip()


def _find_work(
    conn,
    interpreter_id: Optional[str],
    limit: int,
    scan_id: Optional[str],
) -> List[Dict[str, Any]]:
    """Candidate file rows, newest scans first is not required — order is
    whatever the index gives; ``limit`` bounds the run, not the selection."""
    extensions = _extensions_for(interpreter_id)

    where = ["f.type = 'file'"]
    params: List[Any] = []

    interpreted_clause = "f.interpreted_as IS NOT NULL"
    if interpreter_id:
        interpreted_clause = "f.interpreted_as = ?"
        params.append(interpreter_id)

    if extensions:
        placeholders = ','.join('?' for _ in extensions)
        where.append(f"({interpreted_clause} OR lower(f.file_extension) IN ({placeholders}))")
        params.extend(extensions)
    else:
        where.append(f"({interpreted_clause})")

    if scan_id:
        where.append("f.scan_id = ?")
        params.append(scan_id)

    sql = (
        "SELECT f.path, f.interpreted_as, f.file_extension, f.hash, f.scan_id, "
        "       COALESCE(f.remote, '') AS host "
        "FROM files f "
        f"WHERE {' AND '.join(where)} "
        "LIMIT ?"
    )
    params.append(int(limit))

    rows = []
    for path, interpreted_as, extension, file_hash, row_scan_id, remote in conn.execute(sql, params):
        rows.append({
            'path': path,
            'interpreted_as': interpreted_as,
            'file_extension': extension,
            'hash': file_hash,
            'scan_id': row_scan_id,
            'host': _row_host(remote),
        })
    return rows


def _resolve_interpreter_id(row: Dict[str, Any]) -> Optional[str]:
    """What the scanner decided, or what the extension table would decide."""
    if row.get('interpreted_as'):
        return row['interpreted_as']
    from ..core.scanner_formats import KNOWN_INTERPRETERS
    return KNOWN_INTERPRETERS.get((row.get('file_extension') or '').lower())


def _already_enriched(graph, paths: List[str]) -> Set[str]:
    """Paths that already carry an Interpretation node with a payload.

    An Interpretation with a null ``data_json`` is one of the empty nodes the
    pre-fix pipeline left behind, and is work rather than a reason to skip.
    """
    done: Set[str] = set()
    session_factory = getattr(graph, '_session', None)
    if not callable(session_factory) or not paths:
        return done
    try:
        with session_factory() as session:
            for start in range(0, len(paths), _PATH_CHUNK):
                chunk = paths[start:start + _PATH_CHUNK]
                result = session.run(
                    "MATCH (f:File)-[:INTERPRETED_AS]->(i:Interpretation) "
                    "WHERE f.path IN $paths AND i.data_json IS NOT NULL AND i.data_json <> '{}' "
                    "RETURN DISTINCT f.path AS path",
                    paths=chunk,
                )
                done.update(record['path'] for record in result)
    except Exception:
        # No graph, or an unreachable one. Enriching a file twice is idempotent
        # (every write is a MERGE); refusing to enrich anything is not.
        logger.debug("already-enriched lookup failed; treating all paths as work", exc_info=True)
    return done


# ─────────────────────────────────────────────────────────────────────────────
# Backends
# ─────────────────────────────────────────────────────────────────────────────

def _get_graph():
    """The Neo4j-backed graph, from the app if there is one, else from env.

    ``create_graph_backend`` needs a Flask app only for ``app.extensions`` and
    ``app.logger``; standalone, the config comes from the environment that
    ``.env`` already populates for every other entry point.
    """
    try:
        from flask import current_app
        if current_app:
            graph = current_app.extensions['scidk'].get('graph')
            if graph is not None:
                return graph
    except Exception:
        pass

    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        pass

    from ..core.neo4j_config import get_neo4j_params
    from ..core.neo4j_graph import Neo4jGraph

    class _Shim:
        extensions = {'scidk': {}}

    uri, user, password, database, auth_mode = get_neo4j_params(_Shim())
    if not uri:
        return None
    auth = None if auth_mode == 'none' else (user, password)
    return Neo4jGraph(uri=uri, auth=auth, database=database, auth_mode=auth_mode)


def _get_client(graph):
    """A connected ``Neo4jClient`` for ``write_declared_nodes``.

    ``Neo4jGraph`` records the Interpretation node but has no way to write the
    domain nodes an interpreter declares — that is ``write_declared_nodes``, and
    without it no ``FCSFile`` or ``HistologySlide`` ever reaches the graph.
    """
    if graph is None:
        return None
    try:
        from .neo4j_client import Neo4jClient
        auth = getattr(graph, '_auth', None)
        return Neo4jClient(
            graph._uri,
            auth[0] if auth else None,
            auth[1] if auth else None,
            getattr(graph, '_db', None),
            getattr(graph, '_auth_mode', 'basic'),
        ).connect()
    except Exception:
        logger.warning("Neo4j client unavailable; declared nodes will not be written", exc_info=True)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Writing
# ─────────────────────────────────────────────────────────────────────────────

def _invoke(interpreter, path: Path, context: dict):
    """Call an interpreter with or without context, whichever it accepts.

    The eleven interpreters that predate ``BaseInterpreter`` are
    ``interpret(self, file_path)`` and return the legacy dict. They are still
    valid interpreters and ``interpreted_as`` still points at them, so the
    dispatcher has to be able to run them — calling every interpreter with two
    arguments would make ``python_code`` and ``csv`` permanently unenrichable.
    Inspecting the signature rather than catching ``TypeError`` keeps a
    ``TypeError`` raised *inside* an interpreter from being read as "takes one
    argument" and retried.
    """
    method = interpreter.interpret
    try:
        positional = [
            p for p in inspect.signature(method).parameters.values()
            if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
        ]
        takes_context = len(positional) >= 2
    except (TypeError, ValueError):
        takes_context = False
    return method(path, context) if takes_context else method(path)


def _payload_of(result) -> Dict[str, Any]:
    """The stored envelope for either result shape."""
    from ..core.interpreter_persistence import build_payload

    if hasattr(result, 'to_legacy_dict'):
        return result.to_legacy_dict()
    return build_payload(result if isinstance(result, dict) else {})


def _write_result(conn, graph, client, path: Path, row: Dict[str, Any],
                  interpreter, result) -> List[str]:
    """Persist one interpretation to SQLite and Neo4j. Returns error strings."""
    from ..core.interpreter_persistence import persist_interpretation

    errors: List[str] = []
    payload = _payload_of(result)
    interpreter_id = getattr(interpreter, 'id', '') or getattr(interpreter, 'name', '')
    version = getattr(interpreter, 'version', '0.0.1')

    if conn is not None:
        try:
            persist_interpretation(
                conn, row['path'], row['scan_id'], interpreter_id, payload,
                interpreter_version=version,
                # The index key is whatever the scanner wrote. A resolved
                # absolute path is the usual second guess when it differs.
                fallback_paths=(str(path.resolve()) if path.exists() else '',),
            )
        except Exception as e:
            errors.append(f"sqlite {row['path']}: {e}")

    if graph is not None:
        try:
            graph.add_interpretation(
                row.get('hash') or row['path'], interpreter_id, payload,
                file_path=row['path'], host=row.get('host') or None,
            )
        except Exception as e:
            errors.append(f"interpretation node {row['path']}: {e}")

    errors.extend(_write_declared(client, payload))
    return errors


def _write_declared(client, payload: Dict[str, Any]) -> List[str]:
    """Hand the declared nodes and edges to ``write_declared_nodes``.

    That call never raises — it accumulates into ``errors`` and continues — so
    the errors have to be read back out or a failed write looks like a
    successful one.
    """
    nodes = payload.get('nodes') or []
    relationships = payload.get('relationships') or []
    if client is None or not (nodes or relationships):
        return []
    try:
        written = client.write_declared_nodes(nodes, relationships)
        return list(written.get('errors') or [])
    except Exception as e:
        return [f"write_declared_nodes: {e}"]


def _write_directory_result(conn, graph, client, directory: Path,
                            interpreter, result, scan_id: Optional[str],
                            host: str) -> List[str]:
    """As :func:`_write_result`, for a folder row.

    ``row_type=None`` because the index stores the directory with
    ``type='folder'``; the default ``'file'`` filter would match no row and the
    session would exist in Neo4j but not in SQLite.
    """
    from ..core.interpreter_persistence import persist_interpretation

    errors: List[str] = []
    payload = _payload_of(result)
    interpreter_id = getattr(interpreter, 'id', '') or getattr(interpreter, 'name', '')

    if conn is not None and scan_id:
        try:
            persist_interpretation(
                conn, str(directory), scan_id, interpreter_id, payload,
                interpreter_version=getattr(interpreter, 'version', '0.0.1'),
                row_type=None,
            )
        except Exception as e:
            errors.append(f"sqlite {directory}: {e}")

    if graph is not None:
        try:
            graph.add_interpretation(
                str(directory), interpreter_id, payload,
                file_path=str(directory), host=host or None,
            )
        except Exception as e:
            errors.append(f"interpretation node {directory}: {e}")

    errors.extend(_write_declared(client, payload))
    return errors


# ─────────────────────────────────────────────────────────────────────────────
# Dispatch
# ─────────────────────────────────────────────────────────────────────────────

def _detect_directory_interpreter(directory: Path, listing: Tuple[List[str], List[str]]) -> Optional[str]:
    """Interpreter id for a directory, via the same tables the scanner uses."""
    from ..core.scanner_formats import detect_directory_pattern, interpreter_for_dir_pattern

    child_names, _files = listing
    pattern = detect_directory_pattern(child_names)
    return interpreter_for_dir_pattern(pattern)


def _list_directory(directory: Path, cache: Dict[Path, Tuple[List[str], List[str]]]):
    """``(all child names, file names)`` for a directory, listed once.

    Pass 1 asks for a directory's siblings once per file in it; on a 96-well
    plate that is 96 identical ``iterdir()`` calls over NFS.
    """
    if directory in cache:
        return cache[directory]
    children: List[str] = []
    files: List[str] = []
    try:
        for entry in directory.iterdir():
            children.append(entry.name)
            try:
                if entry.is_file():
                    files.append(entry.name)
            except OSError:
                continue
    except Exception:
        pass
    cache[directory] = (children, files)
    return cache[directory]


def run_enrichment(
    interpreter_id: Optional[str] = None,
    limit: int = 500,
    scan_id: Optional[str] = None,
    db_conn=None,
    force: bool = False,
) -> Dict[str, Any]:
    """Run both passes and report what happened.

    Args:
        interpreter_id: Restrict to one interpreter, by registry id.
        limit: Maximum file rows to consider.
        scan_id: Restrict to one scan. Uses the index; strongly preferred on a
            large ``files.db``.
        db_conn: An open ``path_index_sqlite`` connection. One is opened and
            committed here when not supplied.
        force: Re-enrich files that already have a populated Interpretation
            node. Without it a second run over the same scan is a no-op.

    Returns:
        Counts, the interpreters that ran, and every warning and error raised.
        Errors are collected rather than thrown: one unreadable slide in a tray
        of thirty should not abandon the other twenty-nine.
    """
    from ..core import path_index_sqlite as pix
    from ..interpreters.registry import get_interpreter_by_id

    owns_conn = db_conn is None
    conn = db_conn
    if owns_conn:
        conn = pix.connect()
        pix.init_db(conn)

    graph = _get_graph()
    client = _get_client(graph)

    errors: List[str] = []
    warnings: List[str] = []
    interpreters_used: Set[str] = set()
    pass1_results: Dict[str, Any] = {}
    skipped_no_interpreter = 0
    directories_processed = 0
    listings: Dict[Path, Tuple[List[str], List[str]]] = {}
    directories: Dict[Path, Dict[str, Any]] = {}

    try:
        rows = _find_work(conn, interpreter_id, limit, scan_id)

        enriched = set() if force else _already_enriched(graph, [r['path'] for r in rows])
        rows = [r for r in rows if r['path'] not in enriched]

        # ---- Pass 1: file-level -------------------------------------------
        for row in rows:
            resolved_id = _resolve_interpreter_id(row)
            interpreter = get_interpreter_by_id(resolved_id)
            if interpreter is None or getattr(interpreter, 'dispatch', 'file') != 'file':
                skipped_no_interpreter += 1
                continue

            path = Path(row['path'])
            _children, sibling_files = _list_directory(path.parent, listings)
            context = {
                'sibling_files': sibling_files,
                'sibling_interpretations': {},
                'host': row.get('host', ''),
                'scan_id': row.get('scan_id'),
            }

            try:
                result = _invoke(interpreter, path, context)
            except Exception as e:
                # The ABC says interpreters do not raise; the pre-ABC ones make
                # no such promise. Honour it on their behalf rather than losing
                # the rest of the batch.
                result = (interpreter._stub(path, f"{type(e).__name__}: {e}")
                          if hasattr(interpreter, '_stub')
                          else {'status': 'error', 'data': {'error': f"{type(e).__name__}: {e}"}})
            if result is None:
                errors.append(f"{row['path']}: interpreter returned nothing")
                continue

            interpreters_used.add(getattr(interpreter, 'id', resolved_id))
            pass1_results[row['path']] = result
            warnings.extend(f"{row['path']}: {w}" for w in getattr(result, 'warnings', []))
            errors.extend(_write_result(conn, graph, client, path, row, interpreter, result))

            # Pass 2 needs the same host for the same reason pass 1 does. Take
            # it from the first sibling that actually has one rather than the
            # first sibling seen — a single row with a null `remote` would
            # otherwise cost the directory write a full label scan.
            meta = directories.setdefault(
                path.parent, {'scan_id': row.get('scan_id'), 'host': ''})
            if not meta['host'] and row.get('host'):
                meta['host'] = row['host']

        # ---- Pass 2: directory-level --------------------------------------
        for directory, meta in directories.items():
            listing = _list_directory(directory, listings)
            dir_interpreter_id = _detect_directory_interpreter(directory, listing)
            dir_interpreter = get_interpreter_by_id(dir_interpreter_id)
            if dir_interpreter is None or getattr(dir_interpreter, 'dispatch', 'file') != 'directory':
                continue

            siblings = {
                Path(p).name: r for p, r in pass1_results.items()
                if Path(p).parent == directory
            }
            context = {
                'sibling_files': listing[1],
                'sibling_interpretations': siblings,
                'host': meta.get('host', ''),
                'scan_id': meta.get('scan_id'),
            }

            try:
                result = dir_interpreter.interpret(directory, context)
            except Exception as e:
                errors.append(f"{directory}: {type(e).__name__}: {e}")
                continue
            if result is None or getattr(result, 'confidence', '') == 'stub':
                warnings.extend(f"{directory}: {w}" for w in getattr(result, 'warnings', []))
                continue

            interpreters_used.add(getattr(dir_interpreter, 'id', dir_interpreter_id))
            directories_processed += 1
            errors.extend(_write_directory_result(
                conn, graph, client, directory, dir_interpreter, result,
                meta.get('scan_id'), meta.get('host', ''),
            ))

        if owns_conn:
            conn.commit()
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass
        if owns_conn and conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    return {
        'files_processed': len(pass1_results),
        'directories_processed': directories_processed,
        'directories_examined': len(directories),
        'files_skipped_no_interpreter': skipped_no_interpreter,
        'interpreters_used': sorted(interpreters_used),
        'graph_connected': graph is not None,
        'declared_nodes_written': client is not None,
        'warnings': warnings,
        'errors': errors,
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--interpreter', help='registry id, e.g. fcs_interpreter')
    parser.add_argument('--limit', type=int, default=500)
    parser.add_argument('--scan-id', dest='scan_id')
    parser.add_argument('--force', action='store_true',
                        help='re-enrich files that already have an Interpretation payload')
    args = parser.parse_args()

    logging.basicConfig(
        level=os.environ.get('SCIDK_LOG_LEVEL', 'INFO'),
        format='%(levelname)s %(name)s: %(message)s',
    )
    print(json.dumps(
        run_enrichment(args.interpreter, args.limit, args.scan_id, force=args.force),
        indent=2, default=str,
    ))
