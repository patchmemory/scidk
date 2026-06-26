"""Post-commit creation of :Dataset nodes from matched scan directories.

The rclone scan loop writes file metadata to SQLite only; the Neo4j commit is a
separate step (``api_neo4j.api_scan_commit`` -> ``commit_to_neo4j`` ->
``Neo4jClient.write_scan``) that creates the ``(:File {path, host})`` and
``(:Folder {path, host})`` nodes.

This module runs *after* ``write_scan`` has committed those nodes. It reads the
scan's file rows back from SQLite, groups them by parent directory, matches each
directory against the loaded dataset profiles, and — for matched directories —
writes a single ``(:Dataset {path, host})`` node linked to its files via
``(:Dataset)-[:CONTAINS]->(:File)``.

Matching uses the *most specific* (deepest inheritance) profile that matches a
directory, so a directory of ``.tif`` files becomes a ``TIFFCollection`` rather
than something more generic. Two classes of profile are skipped entirely:

  - **Abstract** profiles (``abstract: true``, e.g. ``file_collection``) exist only
    to be inherited; they have an empty trigger that matches every directory and
    would otherwise tag everything generically.
  - **Disabled** profiles (``enabled: false``, or overridden off in SQLite settings
    via ``profile_enabled_<id>``).

One directory yields at most one :Dataset node.

The ``host`` passed in must be the exact value ``write_scan`` set on the File
nodes (``scan['host_id']``, bound to the ``node_host`` Cypher parameter) so the
``MATCH (f:File {path, host})`` used for linking resolves correctly.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..core import path_index_sqlite as pix
from ..core.profile_matcher import match as profile_match

logger = logging.getLogger(__name__)


def _dir_name(dir_path: str) -> str:
    """Best-effort basename for a (possibly remote) directory path."""
    try:
        from ..core.path_utils import parse_remote_path

        info = parse_remote_path(dir_path)
        if info.get("is_remote"):
            parts = info.get("parts") or []
            return parts[-1] if parts else (info.get("remote_name") or dir_path)
    except Exception:
        pass
    try:
        return Path(dir_path).name or dir_path
    except Exception:
        return dir_path


def _is_connected(neo4j_client: Any) -> bool:
    """A Neo4jClient is usable once ``connect()`` has set its driver."""
    if neo4j_client is None:
        return False
    # Neo4jClient exposes the underlying driver as ``_driver`` (None until connect()).
    if hasattr(neo4j_client, "_driver"):
        return getattr(neo4j_client, "_driver") is not None
    # Unknown client shape (e.g. a test double): assume usable.
    return True


def _read_scan_rows(scan_id: str) -> List[Dict[str, Any]]:
    """Read this scan's file/folder rows back from the SQLite path index."""
    conn = pix.connect()
    pix.init_db(conn)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT path, parent_path, name, type, size FROM files WHERE scan_id = ?",
            (scan_id,),
        )
        items = cur.fetchall()
    finally:
        try:
            conn.close()
        except Exception:
            pass

    rows: List[Dict[str, Any]] = []
    for (path, parent_path, name, typ, size) in items:
        rows.append(
            {
                "path": path,
                "parent_path": parent_path or "",
                "name": name or _dir_name(path),
                "type": typ,
                "size": int(size or 0),
            }
        )
    return rows


def _group_by_directory(rows: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Group rows by their parent directory path.

    Each value is the list of lsjson-style entries (``Name``/``Path``/``Size``/
    ``IsDir``) that live directly under that directory — exactly the shape
    ``profile_matcher.match`` expects.
    """
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        parent = r.get("parent_path") or ""
        if not parent:
            continue
        grouped.setdefault(parent, []).append(
            {
                "Name": r.get("name"),
                "Path": r.get("path"),
                "Size": r.get("size", 0),
                "IsDir": (r.get("type") == "folder"),
            }
        )
    return grouped


def _profile_enabled(profile: dict) -> bool:
    """Effective enabled state for a profile.

    A preference stored in SQLite settings (``profile_enabled_<id>``, set via the
    Settings UI) takes precedence over the YAML ``enabled`` field. Missing in both
    places defaults to enabled.
    """
    pid = profile.get("profile_id")
    override = None
    if pid:
        try:
            from ..core.settings import get_setting

            override = get_setting(f"profile_enabled_{pid}")
        except Exception:
            override = None
    if override is not None:
        return str(override).strip().lower() in ("1", "true", "yes", "on")
    return bool(profile.get("enabled", True))


def _best_profile(dir_path: str, entries: List[Dict[str, Any]], profile_registry) -> Optional[dict]:
    """Return the most specific (deepest) matching profile, or None.

    Abstract profiles (e.g. ``file_collection``) never emit a Dataset node, and
    disabled profiles are skipped entirely.
    """
    best: Optional[dict] = None
    best_depth = -1
    for profile in profile_registry.ordered_profiles():
        if profile.get("abstract"):
            continue
        if not _profile_enabled(profile):
            continue
        res = profile_match(dir_path, entries, profile)
        if not res.get("matched"):
            continue
        depth = int(profile.get("_depth", 0))
        if depth > best_depth:
            best = profile
            best_depth = depth
    return best


def write_dataset_nodes(scan_id: str, host: str, neo4j_client, profile_registry) -> dict:
    """Create :Dataset nodes for matched directories and link them to File nodes.

    Run this immediately after ``write_scan`` succeeds so the ``(:File {path, host})``
    nodes the datasets link to already exist.

    Returns ``{created: int, updated: int, errors: list}``. If Neo4j is unavailable
    (client is None or not connected) this returns early with a warning and does not
    raise — commit behaviour is then completely unchanged.
    """
    result: Dict[str, Any] = {"created": 0, "updated": 0, "errors": []}

    if not _is_connected(neo4j_client):
        logger.warning(
            "write_dataset_nodes: Neo4j client unavailable/not connected; "
            "skipping Dataset node creation for scan %s",
            scan_id,
        )
        return result

    if profile_registry is None:
        logger.warning("write_dataset_nodes: no profile registry; skipping scan %s", scan_id)
        return result

    try:
        rows = _read_scan_rows(scan_id)
    except Exception as e:  # pragma: no cover - defensive
        logger.exception("write_dataset_nodes: failed to read scan rows for %s", scan_id)
        result["errors"].append(f"read_rows: {e}")
        return result

    grouped = _group_by_directory(rows)

    for dir_path, entries in grouped.items():
        profile = _best_profile(dir_path, entries, profile_registry)
        if profile is None:
            continue  # no profile matched -> no Dataset node for this directory

        graph_props = (profile.get("graph") or {}).get("properties") or {}
        ds_type = graph_props.get("type") or profile.get("profile_id")
        profile_id = profile.get("profile_id")
        name = _dir_name(dir_path)

        # File paths directly under this directory (exclude subdirectories).
        file_paths = [
            e.get("Path") for e in entries if not e.get("IsDir") and e.get("Path")
        ]

        try:
            merge_q = (
                "MERGE (d:Dataset {path: $dir_path, host: $host}) "
                "ON CREATE SET d.created_at = timestamp() "
                "SET d.name = $name, d.type = $type, d.profile = $profile_id, "
                "    d.scan_id = $scan_id, d.updated_at = timestamp() "
                "RETURN d.created_at = d.updated_at AS created"
            )
            recs = neo4j_client.execute_write(
                merge_q,
                {
                    "dir_path": dir_path,
                    "host": host,
                    "name": name,
                    "type": ds_type,
                    "profile_id": profile_id,
                    "scan_id": scan_id,
                },
            )
            was_created = bool(recs[0].get("created")) if recs else False
            if was_created:
                result["created"] += 1
            else:
                result["updated"] += 1

            if file_paths:
                link_q = (
                    "MATCH (d:Dataset {path: $dir_path, host: $host}) "
                    "UNWIND $file_paths AS fp "
                    "MATCH (f:File {path: fp, host: $host}) "
                    "MERGE (d)-[:CONTAINS]->(f)"
                )
                neo4j_client.execute_write(
                    link_q,
                    {"dir_path": dir_path, "host": host, "file_paths": file_paths},
                )

            logger.info(
                "Dataset node created: %s at %s (%d files linked)",
                profile_id,
                dir_path,
                len(file_paths),
            )
        except Exception as e:
            logger.exception(
                "write_dataset_nodes: failed to write Dataset for %s", dir_path
            )
            result["errors"].append(f"{dir_path}: {e}")

    return result
