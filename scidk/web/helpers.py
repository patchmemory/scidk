"""
Helper functions for web routes that need access to app context.
These functions are used across multiple blueprint modules.
"""
from flask import current_app
from pathlib import Path as _P
import os
import time as _time
import random as _random
from typing import Dict, Any, List, Tuple, Optional, Iterable, Callable


def get_neo4j_params() -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str], str]:
    """
    Helper to read Neo4j configuration, preferring in-app settings over environment.

    Returns:
        tuple: (uri, user, password, database, auth_mode)
        auth_mode: 'basic' (username+password) or 'none' (no authentication)
    """
    cfg = current_app.extensions['scidk'].get('neo4j_config', {})
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


def build_commit_rows(scan: Dict[str, Any], ds_map: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Build rows for commit: files (rows) and standalone folders (folder_rows).
    Legacy builder from in-memory datasets.

    Args:
        scan: Scan metadata dictionary
        ds_map: Dataset map (checksum -> dataset)

    Returns:
        tuple: (file_rows, folder_rows)
    """
    try:
        from ..services.commit_service import CommitService
        return CommitService().build_rows_legacy_from_datasets(scan, ds_map)
    except Exception:
        # Fallback to empty on unexpected import/runtime error
        return [], []


def commit_to_neo4j(rows: List[Dict[str, Any]], folder_rows: List[Dict[str, Any]],
                   scan: Dict[str, Any], neo4j_params: Tuple) -> Dict[str, Any]:
    """
    Execute Neo4j commit using simplified, idempotent Cypher.

    Args:
        rows: File rows to commit
        folder_rows: Folder rows to commit
        scan: Scan metadata
        neo4j_params: Tuple of (uri, user, pwd, database, auth_mode)

    Returns:
        dict: Result with keys: attempted, written_files, written_folders, error
    """
    # Support 4-tuple (backward compat) and 5-tuple with auth_mode
    try:
        uri, user, pwd, database, auth_mode = neo4j_params
    except Exception:
        uri, user, pwd, database = neo4j_params  # type: ignore
        auth_mode = 'basic'
    result = {'attempted': False, 'written_files': 0, 'written_folders': 0, 'error': None}
    if not uri:
        return result
    # Decide if we can attempt a connection
    can_basic = bool(user and pwd)
    can_connect = (auth_mode == 'none') or can_basic
    if not can_connect:
        return result
    # Backoff on recent auth failures to avoid rate limiting
    st = current_app.extensions['scidk'].setdefault('neo4j_state', {})
    import time as _t
    now = _t.time()
    next_after = float(st.get('next_connect_after') or 0)
    if next_after and now < next_after:
        result['error'] = f"neo4j connect backoff active; retry after {int(next_after-now)}s"
        return result
    result['attempted'] = True
    try:
        from ..services.neo4j_client import Neo4jClient
        client = Neo4jClient(uri, user, pwd, database, auth_mode).connect()
        try:
            client.ensure_constraints()
            wres = client.write_scan(rows, folder_rows, scan)
            result['written_files'] = wres.get('written_files', 0)
            result['written_folders'] = wres.get('written_folders', 0)
            vres = client.verify(scan.get('id'))
            result.update(vres)
        finally:
            client.close()
    except Exception as e:
        msg = str(e)
        result['error'] = msg
        # On auth-related errors, set a backoff to avoid rate limiting
        try:
            emsg = msg.lower()
            if ('unauthorized' in emsg) or ('authentication' in emsg):
                # Exponential-ish backoff min 20s
                prev = float(st.get('next_connect_after') or 0)
                base = 20.0
                delay = base
                if prev and now < prev:
                    # increase delay up to 120s
                    rem = prev - now
                    delay = min(max(base*2, rem*2), 120.0)
                st['next_connect_after'] = now + delay
                st['last_error'] = msg
        except Exception:
            pass
    return result


def get_or_build_scan_index(scan_id: str) -> Optional[Dict[str, Any]]:
    """
    Build or fetch per-scan filesystem index for snapshot navigation.

    Args:
        scan_id: The scan ID to build index for

    Returns:
        dict: Index with folder_info, children_folders, children_files, roots
    """
    cache = current_app.extensions['scidk'].setdefault('scan_fs', {})
    if scan_id in cache:
        return cache[scan_id]
    scans = current_app.extensions['scidk'].get('scans', {})
    s = scans.get(scan_id)
    if not s:
        return None
    checksums = s.get('checksums') or []
    ds_map = current_app.extensions['scidk']['graph'].datasets  # checksum -> dataset

    from ..core.path_utils import parse_remote_path, parent_remote_path

    folder_info = {}
    children_files = {}

    def ensure_complete_parent_chain(path_str: str):
        """Ensure all parent folders exist in folder_info for any given path"""
        if not path_str or path_str in folder_info:
            return

        info = parse_remote_path(path_str)
        if info.get('is_remote'):
            parent = parent_remote_path(path_str)
            name = (info.get('parts')[-1] if info.get('parts') else info.get('remote_name') or path_str)
        else:
            try:
                p = _P(path_str)
                parent = str(p.parent)
                name = p.name or path_str
            except Exception:
                parent = ''
                name = path_str

        folder_info[path_str] = {
            'path': path_str,
            'name': name,
            'parent': parent,
        }

        if parent and parent != path_str:
            ensure_complete_parent_chain(parent)

    # Seed scan base path (stable roots even on empty scans)
    try:
        base_path = s.get('path') or ''
        if base_path:
            ensure_complete_parent_chain(base_path)
    except Exception:
        pass

    # Process files and ensure their parent chains exist
    for ch in checksums:
        d = ds_map.get(ch)
        if not d:
            continue
        file_path = d.get('path')
        if not file_path:
            continue

        info = parse_remote_path(file_path)
        if info.get('is_remote'):
            parent = parent_remote_path(file_path)
            filename = (info.get('parts')[-1] if info.get('parts') else info.get('remote_name') or file_path)
        else:
            try:
                p = _P(file_path)
                parent = str(p.parent)
                filename = p.name or file_path
            except Exception:
                parent = ''
                filename = file_path

        file_entry = {
            'id': d.get('id'),
            'path': file_path,
            'filename': d.get('filename') or filename,
            'extension': d.get('extension'),
            'size_bytes': int(d.get('size_bytes') or 0),
            'modified': float(d.get('modified') or 0),
            'mime_type': d.get('mime_type'),
            'checksum': d.get('checksum'),
        }
        children_files.setdefault(parent, []).append(file_entry)

        if parent:
            ensure_complete_parent_chain(parent)

    # Process explicitly recorded folders
    for f in (s.get('folders') or []):
        path = f.get('path')
        if path:
            ensure_complete_parent_chain(path)

    # Build children_folders map
    children_folders = {}
    for fpath, info in folder_info.items():
        par = info.get('parent')
        if par and par in folder_info:
            children_folders.setdefault(par, []).append(fpath)

    # Find actual roots
    roots = sorted([fp for fp, info in folder_info.items()
                    if not info.get('parent') or info.get('parent') not in folder_info])

    # Prefer scan base as visible root and drop its ancestors
    try:
        base_path = s.get('path') or ''
        if base_path and base_path in folder_info:
            if base_path not in roots:
                roots.append(base_path)
            def _is_ancestor(candidate: str, child: str) -> bool:
                if not candidate or candidate == child:
                    return False
                cinf = parse_remote_path(candidate)
                chinf = parse_remote_path(child)
                if chinf.get('is_remote') and cinf.get('is_remote'):
                    return child.startswith(candidate.rstrip('/') + '/')
                try:
                    return str(_P(child)).startswith(str(_P(candidate)) + '/')
                except Exception:
                    return False
            roots = [r for r in roots if not _is_ancestor(r, base_path) or r == base_path]
            roots = sorted(list(dict.fromkeys(roots)))
    except Exception:
        pass

    # Sort children deterministically
    for k in list(children_folders.keys()):
        children_folders[k].sort(key=lambda p: folder_info.get(p, {}).get('name', '').lower())
    for k in list(children_files.keys()):
        children_files[k].sort(key=lambda f: (f.get('filename') or '').lower())

    idx = {
        'folder_info': folder_info,
        'children_folders': children_folders,
        'children_files': children_files,
        'roots': roots,
    }
    cache[scan_id] = idx
    return idx
def _chunked_list(seq: List[Dict[str, Any]], size: int) -> Iterable[List[Dict[str, Any]]]:
    size = max(1, int(size or 1))
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def _neo4j_progress_default(event: str, payload: Dict[str, Any]) -> None:
    try:
        print(f"[neo4j:{event}] {payload}")
    except Exception:
        pass


def commit_to_neo4j_batched(
    rows: List[Dict[str, Any]],
    folder_rows: List[Dict[str, Any]],
    scan: Dict[str, Any],
    neo4j_params: Tuple[str, str, str, str, Optional[str]],
    file_batch_size: int = 5000,
    folder_batch_size: int = 5000,
    max_retries: int = 2,
    on_progress: Callable[[str, Dict[str, Any]], None] = _neo4j_progress_default,
):
    """
    Batched Neo4j commit with per-batch retries and progress reporting.
    Expects rows to include keys: path, filename, extension, size_bytes, created, modified, mime_type, folder
    Expects folder_rows to include keys: path, name, parent
    """
    # Unpack params (support both 4 and 5 tuple forms)
    try:
        uri, user, pwd, database, auth_mode = neo4j_params
    except Exception:
        uri, user, pwd, database = neo4j_params  # type: ignore
        auth_mode = "basic"

    result: Dict[str, Any] = {
        "attempted": False,
        "written_files": 0,
        "written_folders": 0,
        "batches_total": 0,
        "batches_ok": 0,
        "batches_failed": 0,
        "errors": [],
        "error": None,
        "db_scan_exists": None,
        "db_files": None,
        "db_folders": None,
        "db_verified": False,
    }

    if not uri:
        return result

    can_basic = bool(user and pwd)
    if not (auth_mode == "none" or can_basic):
        return result

    # Backoff state
    try:
        from flask import current_app as _cap
        st = _cap.extensions["scidk"].setdefault("neo4j_state", {})
    except Exception:
        st = {"next_connect_after": 0}
    now = _time.time()
    next_after = float(st.get("next_connect_after") or 0)
    if next_after and now < next_after:
        wait_s = int(next_after - now)
        msg = f"neo4j connect backoff active; retry after {wait_s}s"
        result["errors"].append(msg)
        result["error"] = msg
        return result

    result["attempted"] = True

    # Derive host id for composite identity
    node_host = scan.get("host_id")

    from neo4j import GraphDatabase  # type: ignore  # noqa
    driver = None
    try:
        driver = GraphDatabase.driver(uri, auth=None if auth_mode == "none" else (user, pwd))
        with driver.session(database=database) as sess:
            # Emit non-secret connection info for diagnostics
            try:
                on_progress("neo4j_params", {
                    "uri": (uri.split("@")[-1] if uri else None),
                    "auth_mode": auth_mode,
                    "database": database or None,
                })
            except Exception:
                pass
            # Constraints (safe on 5.x; ignore errors otherwise)
            for cql in (
                "CREATE CONSTRAINT file_identity IF NOT EXISTS FOR (f:File) REQUIRE (f.path, f.host) IS UNIQUE",
                "CREATE CONSTRAINT folder_identity IF NOT EXISTS FOR (d:Folder) REQUIRE (d.path, d.host) IS UNIQUE",
            ):
                try:
                    sess.run(cql).consume()
                except Exception:
                    pass

            # Upsert Scan once
            scan_upsert = (
                "MERGE (s:Scan {id: $scan_id}) "
                "SET s.path = $scan_path, s.started = $scan_started, s.ended = $scan_ended, "
                "    s.provider_id = $scan_provider, s.host_type = $scan_host_type, s.host_id = $scan_host_id, "
                "    s.root_id = $scan_root_id, s.root_label = $scan_root_label, s.scan_source = $scan_source "
                "RETURN s.id AS scan_id"
            )
            sess.run(
                scan_upsert,
                scan_id=scan.get("id"),
                scan_path=scan.get("path"),
                scan_started=scan.get("started"),
                scan_ended=scan.get("ended"),
                scan_provider=scan.get("provider_id"),
                scan_host_type=scan.get("host_type"),
                scan_host_id=scan.get("host_id"),
                scan_root_id=scan.get("root_id"),
                scan_root_label=scan.get("root_label"),
                scan_source=scan.get("scan_source") or scan.get("source"),
            ).consume()

            # Cypher templates
            folders_upsert_cql = (
                "WITH $folders AS folders, $node_host AS node_host, $scan AS scan_id, $scan_provider AS scan_provider, $scan_host_type AS scan_host_type, $scan_host_id AS scan_host_id "
                "UNWIND folders AS folder "
                "MERGE (fo:Folder {path: folder.path, host: node_host}) "
                "  SET fo.name = folder.name, fo.provider_id = scan_provider, fo.host_type = scan_host_type, fo.host_id = scan_host_id "
                "WITH fo, scan_id "
                "OPTIONAL MATCH (s:Scan {id: scan_id}) "
                "MERGE (fo)-[:SCANNED_IN]->(s)"
            )

            folders_link_cql = (
                "WITH $folders AS folders, $node_host AS node_host "
                "UNWIND folders AS folder "
                "WITH folder, node_host "
                "WHERE folder.parent IS NOT NULL AND folder.parent <> '' AND folder.parent <> folder.path "
                "MERGE (parent:Folder {path: folder.parent, host: node_host}) "
                "MERGE (child:Folder {path: folder.path, host: node_host}) "
                "MERGE (parent)-[:CONTAINS]->(child)"
            )

            # Optional safety net to compute folder from file path when missing (feature-flagged)
            _files_fallback = (os.environ.get('SCIDK_FILES_COMPUTE_FOLDER_FALLBACK') or '').strip().lower() in ('1','true','yes','y','on')
            if _files_fallback:
                files_cql = (
                    "WITH $rows AS rows, $node_host AS node_host, $scan AS scan_id, $scan_provider AS scan_provider, $scan_host_type AS scan_host_type, $scan_host_id AS scan_host_id "
                    "UNWIND rows AS r "
                    "MERGE (f:File {path: r.path, host: node_host}) "
                    "  SET f.filename = r.filename, f.extension = r.extension, f.size_bytes = r.size_bytes, "
                    "      f.created = r.created, f.modified = r.modified, f.mime_type = r.mime_type, "
                    "      f.provider_id = scan_provider, f.host_type = scan_host_type, f.host_id = scan_host_id "
                    "WITH r, f, scan_id, node_host, CASE WHEN r.folder IS NOT NULL AND r.folder <> '' THEN r.folder ELSE substring(r.path, 0, size(r.path) - size(last(split(r.path, '/'))) - 1) END AS folder_path "
                    "OPTIONAL MATCH (s:Scan {id: scan_id}) "
                    "MERGE (f)-[:SCANNED_IN]->(s) "
                    "WITH folder_path, f, node_host WHERE folder_path IS NOT NULL AND folder_path <> '' "
                    "MERGE (fo:Folder {path: folder_path, host: node_host}) "
                    "MERGE (fo)-[:CONTAINS]->(f)"
                )
            else:
                files_cql = (
                    "WITH $rows AS rows, $node_host AS node_host, $scan AS scan_id, $scan_provider AS scan_provider, $scan_host_type AS scan_host_type, $scan_host_id AS scan_host_id "
                    "UNWIND rows AS r "
                    "MERGE (f:File {path: r.path, host: node_host}) "
                    "  SET f.filename = r.filename, f.extension = r.extension, f.size_bytes = r.size_bytes, "
                    "      f.created = r.created, f.modified = r.modified, f.mime_type = r.mime_type, "
                    "      f.provider_id = scan_provider, f.host_type = scan_host_type, f.host_id = scan_host_id "
                    "WITH r, f, scan_id, node_host "
                    "OPTIONAL MATCH (s:Scan {id: scan_id}) "
                    "MERGE (f)-[:SCANNED_IN]->(s) "
                    "WITH r, f, node_host "
                    "WHERE r.folder IS NOT NULL AND r.folder <> '' "
                    "MERGE (fo:Folder {path: r.folder, host: node_host}) "
                    "MERGE (fo)-[:CONTAINS]->(f)"
                )

            def _run_with_retry(cql: str, params: Dict[str, Any], kind: str, index: int):
                attempt = 0
                while True:
                    try:
                        sess.run(cql, **params).consume()
                        return True, None
                    except Exception as ex:
                        attempt += 1
                        if attempt > max_retries:
                            return False, str(ex)
                        sleep_s = min(1.5 * attempt + _random.random(), 5.0)
                        on_progress("retry", {"batch_kind": kind, "batch_index": index, "attempt": attempt, "sleep_s": round(sleep_s, 2), "error": str(ex)[:200]})
                        _time.sleep(sleep_s)

            folder_batches = list(_chunked_list(folder_rows, folder_batch_size))
            file_batches = list(_chunked_list(rows, file_batch_size))
            result["batches_total"] = len(folder_batches) + len(file_batches)

            # Debug first 10 examples of folder/file mappings
            try:
                sample_files = [{"path": r.get("path"), "folder": r.get("folder")} for r in (rows[:10] if rows else [])]
                sample_folders = [{"path": r.get("path"), "parent": r.get("parent")} for r in (folder_rows[:10] if folder_rows else [])]
                on_progress("debug_rows", {"sample_files": sample_files, "sample_folders": sample_folders})
            except Exception:
                pass

            on_progress("start", {
                "scan_id": scan.get("id"),
                "folders": len(folder_rows),
                "files": len(rows),
                "folder_batches": len(folder_batches),
                "file_batches": len(file_batches),
                "batch_sizes": {"folders": folder_batch_size, "files": file_batch_size},
            })

            common = {
                "scan": scan.get("id"),
                "node_host": node_host,
                "scan_provider": scan.get("provider_id"),
                "scan_host_type": scan.get("host_type"),
                "scan_host_id": scan.get("host_id"),
            }

            # Folders first: upsert nodes and attach to scan
            for i, batch in enumerate(folder_batches, start=1):
                t0 = _time.time()
                ok, err = _run_with_retry(folders_upsert_cql, {"folders": batch, **common}, kind="folders_upsert", index=i)
                dt = _time.time() - t0
                if not ok:
                    result["batches_failed"] += 1
                    result["errors"].append(f"folders upsert batch {i}: {err}")
                    on_progress("batch_error", {"batch_kind": "folders_upsert", "batch_index": i, "items": len(batch), "error": err})
                    continue
                # Link parent-child hierarchy in a second step
                t1 = _time.time()
                ok2, err2 = _run_with_retry(folders_link_cql, {"folders": batch, **common}, kind="folders_link", index=i)
                dt2 = _time.time() - t1
                if ok2:
                    result["batches_ok"] += 2  # count both successful sub-steps
                    result["written_folders"] += len(batch)
                    on_progress("batch_done", {"batch_kind": "folders_upsert", "batch_index": i, "items": len(batch), "sec": round(dt, 3)})
                    on_progress("batch_done", {"batch_kind": "folders_link", "batch_index": i, "items": len(batch), "sec": round(dt2, 3)})
                else:
                    result["batches_ok"] += 1  # upsert ok
                    result["batches_failed"] += 1
                    result["errors"].append(f"folders link batch {i}: {err2}")
                    on_progress("batch_done", {"batch_kind": "folders_upsert", "batch_index": i, "items": len(batch), "sec": round(dt, 3)})
                    on_progress("batch_error", {"batch_kind": "folders_link", "batch_index": i, "items": len(batch), "error": err2})

            # Files
            for i, batch in enumerate(file_batches, start=1):
                t0 = _time.time()
                ok, err = _run_with_retry(files_cql, {"rows": batch, **common}, kind="files", index=i)
                dt = _time.time() - t0
                if ok:
                    result["batches_ok"] += 1
                    result["written_files"] += len(batch)
                    on_progress("batch_done", {"batch_kind": "files", "batch_index": i, "items": len(batch), "sec": round(dt, 3)})
                else:
                    result["batches_failed"] += 1
                    result["errors"].append(f"files batch {i}: {err}")
                    on_progress("batch_error", {"batch_kind": "files", "batch_index": i, "items": len(batch), "error": err})

            # Verify
            verify_q = (
                "OPTIONAL MATCH (s:Scan {id: $scan_id}) "
                "WITH s "
                "OPTIONAL MATCH (s)<-[:SCANNED_IN]-(f:File) "
                "WITH s, count(DISTINCT f) AS files_cnt "
                "OPTIONAL MATCH (s)<-[:SCANNED_IN]-(fo:Folder) "
                "RETURN coalesce(s IS NOT NULL, false) AS scan_exists, files_cnt AS files_cnt, count(DISTINCT fo) AS folders_cnt"
            )
            vrec = sess.run(verify_q, scan_id=scan.get("id")).single()
            if vrec:
                scan_exists = bool(vrec.get("scan_exists"))
                files_cnt = int(vrec.get("files_cnt") or 0)
                folders_cnt = int(vrec.get("folders_cnt") or 0)
                result["db_scan_exists"] = scan_exists
                result["db_files"] = files_cnt
                result["db_folders"] = folders_cnt
                result["db_verified"] = bool(scan_exists and (files_cnt > 0 or folders_cnt > 0))

            on_progress("done", {
                "scan_id": scan.get("id"),
                "written_files": result["written_files"],
                "written_folders": result["written_folders"],
                "batches_ok": result["batches_ok"],
                "batches_failed": result["batches_failed"],
                "db_verified": result["db_verified"],
                "db_files": result["db_files"],
                "db_folders": result["db_folders"],
            })

    except Exception as e:
        msg = str(e)
        result["error"] = msg
        result["errors"].append(msg)
        # auth backoff
        try:
            emsg = msg.lower()
            if ("unauthorized" in emsg) or ("authentication" in emsg):
                prev = float(st.get("next_connect_after") or 0)
                base = 20.0
                delay = base
                now2 = _time.time()
                if prev and now2 < prev:
                    rem = prev - now2
                    delay = min(max(base * 2, rem * 2), 120.0)
                st["next_connect_after"] = now2 + delay
                st["last_error"] = msg
        except Exception:
            pass
    finally:
        try:
            if driver is not None:
                driver.close()
        except Exception:
            pass

    return result

