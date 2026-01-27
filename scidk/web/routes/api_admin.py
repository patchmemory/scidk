"""
Blueprint for Health/metrics/logs API routes.
"""
from flask import Blueprint, jsonify, request, current_app
from pathlib import Path
import json
import os
import time

from ..helpers import get_neo4j_params, build_commit_rows, commit_to_neo4j, get_or_build_scan_index
bp = Blueprint('admin', __name__, url_prefix='/api')

def _get_ext():
    """Get SciDK extensions from current Flask current_app."""
    return current_app.extensions['scidk']

@bp.get('/health/graph')
def api_health_graph():
        """Basic health for graph backend. In-memory is always OK; if Neo4j settings/env are provided, try a connection."""
        backend = os.environ.get('SCIDK_GRAPH_BACKEND', 'in_memory').lower() or 'in_memory'
        info = {
            'backend': backend,
            'in_memory_ok': True,
            'neo4j': {
                'configured': False,
                'connectable': False,
                'error': None,
            }
        }
        uri, user, pwd, database, auth_mode = get_neo4j_params()
        if uri:
            info['neo4j']['configured'] = True
            try:
                from neo4j import GraphDatabase  # type: ignore
            except Exception as e:
                info['neo4j']['error'] = f"neo4j driver not installed: {e}"
                return jsonify(info), 200
            # Respect auth-failure backoff
            st = _get_ext().setdefault('neo4j_state', {})
            import time as _t
            now = _t.time()
            next_after = float(st.get('next_connect_after') or 0)
            if next_after and now < next_after:
                info['neo4j']['error'] = f"backoff active; retry after {int(next_after-now)}s"
                return jsonify(info), 200
            try:
                driver = None
                try:
                    driver = GraphDatabase.driver(uri, auth=None if auth_mode == 'none' else (user, pwd))
                    with driver.session(database=database) as sess:
                        rec = sess.run("RETURN 1 AS ok").single()
                        if rec and rec.get('ok') == 1:
                            info['neo4j']['connectable'] = True
                finally:
                    try:
                        if driver is not None:
                            driver.close()
                    except Exception:
                        pass
            except Exception as e:
                info['neo4j']['error'] = str(e)
        return jsonify(info), 200


@bp.get('/health')
def api_health():
        """Overall health focusing on SQLite availability and WAL mode."""
        from ...core import path_index_sqlite as pix
        from ...core import migrations as _migs
        info = {
            'sqlite': {
                'path': None,
                'exists': False,
                'journal_mode': None,
                'wal_mode': None,
                'schema_version': None,
                'select1': False,
                'error': None,
            }
        }
        try:
            dbp = pix._db_path()
            info['sqlite']['path'] = str(dbp)
            conn = pix.connect()
            try:
                # Ensure schema and capture version
                try:
                    v = _migs.migrate(conn)
                    info['sqlite']['schema_version'] = int(v)
                except Exception:
                    try:
                        row_ver = conn.execute('SELECT version FROM schema_migrations LIMIT 1').fetchone()
                        if row_ver and row_ver[0] is not None:
                            info['sqlite']['schema_version'] = int(row_ver[0])
                    except Exception:
                        pass
                mode = (conn.execute('PRAGMA journal_mode;').fetchone() or [''])[0]
                if isinstance(mode, str):
                    jm = mode.lower()
                    info['sqlite']['journal_mode'] = jm
                    info['sqlite']['wal_mode'] = jm
                row = conn.execute('SELECT 1').fetchone()
                info['sqlite']['select1'] = bool(row and row[0] == 1)
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
            # After connecting, the DB file should exist on disk
            try:
                from pathlib import Path as _P
                info['sqlite']['exists'] = _P(info['sqlite']['path']).exists()
            except Exception:
                pass
        except Exception as e:
            info['sqlite']['error'] = str(e)
        # Always return 200 so UIs can render details; clients can decide on status
        return jsonify(info), 200


@bp.get('/metrics')
def api_metrics():
        try:
            from ...services.metrics import collect_metrics
            m = collect_metrics(current_app)
            return jsonify(m), 200
        except Exception as e:
            return jsonify({'error': str(e)}), 500


@bp.get('/logs')
def api_logs():
        """
        Browse operational logs with pagination and filters.
        Query params: limit, offset, level, since_ts
        Privacy: No sensitive file paths or user data exposed.
        """
        try:
            from ...core import path_index_sqlite as pix
            limit = min(int(request.args.get('limit', 100)), 1000)
            offset = int(request.args.get('offset', 0))
            level = request.args.get('level', '').strip().upper() or None
            since_ts = request.args.get('since_ts', '').strip() or None

            conn = pix.connect()
            try:
                cur = conn.cursor()
                # Build query with filters
                conditions = []
                params = []
                if level:
                    conditions.append("level = ?")
                    params.append(level)
                if since_ts:
                    try:
                        ts_val = float(since_ts)
                        conditions.append("ts >= ?")
                        params.append(ts_val)
                    except Exception:
                        pass

                where_clause = ""
                if conditions:
                    where_clause = " WHERE " + " AND ".join(conditions)

                # Get total count
                count_query = f"SELECT COUNT(*) FROM logs{where_clause}"
                cur.execute(count_query, params)
                row = cur.fetchone()
                total = row[0] if row else 0

                # Get logs (most recent first)
                query = f"""
                    SELECT ts, level, message, context
                    FROM logs{where_clause}
                    ORDER BY ts DESC
                    LIMIT ? OFFSET ?
                """
                cur.execute(query, params + [limit, offset])
                rows = cur.fetchall()

                logs = []
                for row in rows:
                    logs.append({
                        'ts': row[0],
                        'level': row[1],
                        'message': row[2],
                        'context': row[3]
                    })

                return jsonify({
                    'logs': logs,
                    'total': total,
                    'limit': limit,
                    'offset': offset
                }), 200
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    # Rclone interpretation settings (GET/POST)

