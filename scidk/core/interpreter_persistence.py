"""One place that writes interpreter output into the ``files`` table.

Two scan paths run interpreters — ``web/routes/api_files.py`` and
``services/scans_service.py`` — and they disagreed about persistence: the first
wrote a truncated payload, the second wrote nothing at all. Having the envelope
built in one function is the point of this module, because the shape is a
contract with a reader in a different file
(``commit_service.extract_declared_nodes_from_scan``) that looks for ``nodes``
and ``relationships`` at the top level.

The UPDATE deliberately does not commit. Callers own the transaction so the row
lands with the rest of the work for that file.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Iterable, Optional

__all__ = ["build_payload", "persist_interpretation"]


def build_payload(result: Dict[str, Any], interpreter_version: Optional[str] = None) -> Dict[str, Any]:
    """Normalise an interpreter's return value into the stored envelope.

    ``nodes`` and ``relationships`` are siblings of ``data`` in what an
    interpreter returns, and both have to survive: they are the only record of
    the domain nodes it declared.
    """
    payload: Dict[str, Any] = {
        'status': result.get('status', 'success'),
        'data': result.get('data', {}),
        'nodes': result.get('nodes', []),
        'relationships': result.get('relationships', []),
    }
    if interpreter_version is not None:
        payload['interpreter_version'] = interpreter_version
    return payload


def persist_interpretation(
    conn,
    path: str,
    scan_id: str,
    interpreter_id: str,
    result: Dict[str, Any],
    interpreter_version: Optional[str] = None,
    row_type: Optional[str] = 'file',
    fallback_paths: Iterable[str] = (),
) -> int:
    """Write interpreter output to the files table. Idempotent.

    Args:
        conn: Open ``path_index_sqlite`` connection. Not committed here.
        path: Index key for the row. Must match ``files.path`` exactly — remote
            scans store canonical ``remote:rel/path`` strings, local scans store
            a resolved absolute path.
        scan_id: Scan the row belongs to.
        interpreter_id: Registry id, written to ``interpreted_as``.
        result: The interpreter's raw return value.
        interpreter_version: Recorded in the payload when given.
        row_type: Restrict to rows of this ``type``; None matches any, which is
            what a directory-level interpretation needs.
        fallback_paths: Alternate keys to retry with if ``path`` matches no row.
            ``create_dataset_node`` reports an unresolved path while the index
            stores a resolved one, so the obvious key can silently miss.

    Returns:
        Number of rows updated. Zero means the key did not match — the caller's
        path is not the one the index recorded.
    """
    payload = build_payload(result, interpreter_version)
    # default=str so one unserialisable value in `data` cannot cost the whole
    # row; a plain dumps() here would raise into a caller that swallows it.
    payload_json = json.dumps(payload, default=str)

    sql = "UPDATE files SET interpreted_as = ?, interpretation_json = ? WHERE path = ? AND scan_id = ?"
    if row_type:
        sql += " AND type = ?"

    for candidate in (path, *fallback_paths):
        if not candidate:
            continue
        params = [interpreter_id, payload_json, candidate, scan_id]
        if row_type:
            params.append(row_type)
        cur = conn.execute(sql, params)
        if cur.rowcount:
            return cur.rowcount
    return 0
