"""API endpoints for Results page."""

import json
import logging
from flask import Blueprint, jsonify, current_app

from scidk.core import path_index_sqlite as pix

logger = logging.getLogger(__name__)

bp = Blueprint("results_api", __name__, url_prefix="/api/results")


@bp.route("/schema-summary", methods=["GET"])
def get_schema_summary():
    """
    Get current knowledge graph schema summary.

    Queries Neo4j for node labels and relationship types with counts.
    Returns format matching Maps page for consistency.

    Returns:
        {
            "status": "ok",
            "schema": {
                "node_count": 1234,
                "relationship_count": 567,
                "labels": ["File", "Folder", "Sample"],
                "relationship_types": ["HAS_SAMPLE", "CONTAINS"]
            }
        }
    """
    try:
        from scidk.services.neo4j_client import get_neo4j_params
        from neo4j import GraphDatabase

        # Get Neo4j connection
        uri, user, pwd, database, auth_mode = get_neo4j_params(current_app)

        if not uri:
            return jsonify({
                "status": "ok",
                "schema": {
                    "node_count": 0,
                    "relationship_count": 0,
                    "labels": [],
                    "relationship_types": []
                }
            })

        auth = None if auth_mode == 'none' else (user, pwd)
        driver = GraphDatabase.driver(uri, auth=auth)

        try:
            with driver.session(database=database) as session:
                # Get total node count
                node_count_result = session.run("MATCH (n) RETURN count(n) as count")
                node_count = node_count_result.single()['count']

                # Get total relationship count
                rel_count_result = session.run("MATCH ()-[r]->() RETURN count(r) as count")
                relationship_count = rel_count_result.single()['count']

                # Get unique labels
                labels_result = session.run("""
                    MATCH (n)
                    UNWIND labels(n) as label
                    RETURN DISTINCT label
                    ORDER BY label
                """)
                labels = [record['label'] for record in labels_result]

                # Get unique relationship types
                rel_types_result = session.run("""
                    MATCH ()-[r]->()
                    RETURN DISTINCT type(r) as type
                    ORDER BY type
                """)
                relationship_types = [record['type'] for record in rel_types_result]

            return jsonify({
                "status": "ok",
                "schema": {
                    "node_count": node_count,
                    "relationship_count": relationship_count,
                    "labels": labels,
                    "relationship_types": relationship_types
                }
            })
        finally:
            driver.close()

    except Exception as e:
        logger.exception("Error fetching schema summary")
        return jsonify({"status": "error", "message": str(e)}), 500


@bp.route("/panels", methods=["GET"])
def get_panels():
    """
    Get all analysis panels for Results page.

    Returns panels ordered by ran_at DESC (most recent first).

    Returns:
        {
            "status": "ok",
            "panels": [
                {
                    "id": "...",
                    "script_id": "...",
                    "script_name": "...",
                    "ran_at": 1708531200.0,
                    "panel_type": "table",
                    "title": "...",
                    "panel_data": "{...}",
                    "visualization": "bar_chart",
                    "status": "success"
                },
                ...
            ]
        }
    """
    try:
        conn = pix.connect()
        try:
            cur = conn.cursor()
            rows = cur.execute("""
                SELECT id, script_id, script_name, ran_at, panel_type, title,
                       panel_data, visualization, status, error_message
                FROM analysis_panels
                ORDER BY ran_at DESC
            """).fetchall()

            panels = [
                {
                    'id': row[0],
                    'script_id': row[1],
                    'script_name': row[2],
                    'ran_at': row[3],
                    'panel_type': row[4],
                    'title': row[5],
                    'panel_data': row[6],
                    'visualization': row[7],
                    'status': row[8],
                    'error_message': row[9]
                }
                for row in rows
            ]

            return jsonify({
                "status": "ok",
                "panels": panels,
                "count": len(panels)
            })
        finally:
            conn.close()

    except Exception as e:
        logger.exception("Error fetching panels")
        return jsonify({"status": "error", "message": str(e)}), 500


@bp.route("/panels/<panel_id>", methods=["DELETE"])
def delete_panel(panel_id: str):
    """
    Remove a panel from Results page.

    Returns:
        {"status": "ok"}
    """
    try:
        conn = pix.connect()
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM analysis_panels WHERE id = ?", (panel_id,))
            conn.commit()

            return jsonify({"status": "ok"})
        finally:
            conn.close()

    except Exception as e:
        logger.exception(f"Error deleting panel {panel_id}")
        return jsonify({"status": "error", "message": str(e)}), 500
