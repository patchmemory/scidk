"""API routes for Maps feature - saved maps and subgraph filtering."""

import logging
from typing import Any, Dict, List

from flask import Blueprint, jsonify, request, current_app

from scidk.services.saved_maps_service import get_saved_maps_service

logger = logging.getLogger(__name__)

bp = Blueprint("api_maps", __name__, url_prefix="/api/maps")


def _get_saved_maps_service():
    """Get SavedMapsService instance using settings DB path from config."""
    db_path = current_app.config.get('SCIDK_SETTINGS_DB', 'scidk_settings.db')
    return get_saved_maps_service(db_path=db_path)


@bp.route("/saved", methods=["GET"])
def list_saved_maps():
    """List all saved maps with optional pagination and sorting.

    Query Parameters:
        limit (int): Maximum number of maps to return (default: 100)
        offset (int): Number of maps to skip (default: 0)
        sort_by (str): Field to sort by (default: updated_at)
        order (str): Sort order ASC or DESC (default: DESC)

    Returns:
        JSON response with list of saved maps
    """
    try:
        limit = int(request.args.get("limit", 100))
        offset = int(request.args.get("offset", 0))
        sort_by = request.args.get("sort_by", "updated_at")
        order = request.args.get("order", "DESC")

        service = _get_saved_maps_service()
        maps = service.list_maps(limit=limit, offset=offset, sort_by=sort_by, order=order)

        return jsonify({
            "status": "ok",
            "maps": [m.to_dict() for m in maps],
            "count": len(maps),
        })
    except Exception as e:
        logger.exception("Error listing saved maps")
        return jsonify({"status": "error", "message": str(e)}), 500


@bp.route("/saved", methods=["POST"])
def create_saved_map():
    """Create a new saved map.

    Request Body:
        name (str): Display name for the map
        description (str, optional): Description
        query (str, optional): Cypher query
        filters (dict, optional): Filter configuration
        visualization (dict, optional): Visualization settings
        tags (str, optional): Comma-separated tags

    Returns:
        JSON response with created map
    """
    try:
        data = request.get_json() or {}

        name = data.get("name")
        if not name:
            return jsonify({
                "status": "error",
                "message": "Map name is required"
            }), 400

        service = _get_saved_maps_service()
        saved_map = service.save_map(
            name=name,
            description=data.get("description"),
            query=data.get("query"),
            filters=data.get("filters"),
            visualization=data.get("visualization"),
            tags=data.get("tags"),
        )

        return jsonify({
            "status": "ok",
            "map": saved_map.to_dict(),
        }), 201
    except Exception as e:
        logger.exception("Error creating saved map")
        return jsonify({"status": "error", "message": str(e)}), 500


@bp.route("/saved/<map_id>", methods=["GET"])
def get_saved_map(map_id: str):
    """Get a specific saved map by ID.

    Args:
        map_id: Unique map identifier

    Returns:
        JSON response with map details or 404 if not found
    """
    try:
        service = _get_saved_maps_service()
        saved_map = service.get_map(map_id)

        if not saved_map:
            return jsonify({
                "status": "error",
                "message": "Map not found"
            }), 404

        return jsonify({
            "status": "ok",
            "map": saved_map.to_dict(),
        })
    except Exception as e:
        logger.exception(f"Error getting saved map {map_id}")
        return jsonify({"status": "error", "message": str(e)}), 500


@bp.route("/saved/<map_id>", methods=["PUT"])
def update_saved_map(map_id: str):
    """Update a saved map.

    Args:
        map_id: Unique map identifier

    Request Body:
        Any combination of: name, description, query, filters, visualization, tags

    Returns:
        JSON response with updated map or 404 if not found
    """
    try:
        data = request.get_json() or {}

        service = _get_saved_maps_service()
        saved_map = service.update_map(map_id, **data)

        if not saved_map:
            return jsonify({
                "status": "error",
                "message": "Map not found"
            }), 404

        return jsonify({
            "status": "ok",
            "map": saved_map.to_dict(),
        })
    except Exception as e:
        logger.exception(f"Error updating saved map {map_id}")
        return jsonify({"status": "error", "message": str(e)}), 500


@bp.route("/saved/<map_id>", methods=["DELETE"])
def delete_saved_map(map_id: str):
    """Delete a saved map.

    Args:
        map_id: Unique map identifier

    Returns:
        JSON response confirming deletion or 404 if not found
    """
    try:
        service = _get_saved_maps_service()
        deleted = service.delete_map(map_id)

        if not deleted:
            return jsonify({
                "status": "error",
                "message": "Map not found"
            }), 404

        return jsonify({
            "status": "ok",
            "message": "Map deleted successfully"
        })
    except Exception as e:
        logger.exception(f"Error deleting saved map {map_id}")
        return jsonify({"status": "error", "message": str(e)}), 500


@bp.route("/saved/<map_id>/use", methods=["POST"])
def track_map_usage(map_id: str):
    """Track usage of a saved map (increment use_count, update last_used_at).

    Args:
        map_id: Unique map identifier

    Returns:
        JSON response confirming tracking or 404 if not found
    """
    try:
        service = _get_saved_maps_service()
        updated = service.track_usage(map_id)

        if not updated:
            return jsonify({
                "status": "error",
                "message": "Map not found"
            }), 404

        return jsonify({
            "status": "ok",
            "message": "Usage tracked"
        })
    except Exception as e:
        logger.exception(f"Error tracking usage for map {map_id}")
        return jsonify({"status": "error", "message": str(e)}), 500


@bp.route("/subgraph", methods=["POST"])
def get_filtered_subgraph():
    """Get filtered subgraph based on query, labels, rel types, and property filters.

    Request Body:
        query (str, optional): Custom Cypher query
        labels (list, optional): List of node labels to include
        rel_types (list, optional): List of relationship types to include
        property_filters (list, optional): List of property filter dicts
        mode (str, optional): Visualization mode (schema, instance, hybrid)
        limit (int, optional): Maximum nodes for instance mode (default: 500)

    Property filter format:
        {
            "label": "Sample",
            "property": "type",
            "operator": "=",  // =, contains, >, <, >=, <=, between
            "value": "blood",  // Single value or array for 'between'
            "data_type": "string"  // string, number, date, boolean
        }

    Returns:
        JSON response with filtered graph data
    """
    try:
        data = request.get_json() or {}

        # Extract filter parameters
        query = data.get("query")
        labels = data.get("labels", [])
        rel_types = data.get("rel_types", [])
        property_filters = data.get("property_filters", [])
        mode = data.get("mode", "schema")
        limit = data.get("limit", 500)

        # Build Cypher query if not provided
        if not query:
            query = _build_filter_query(labels, rel_types, property_filters, limit)

        # Import graph service to execute query
        from scidk.services.graph_service import get_graph_service
        graph_service = get_graph_service()

        # Execute query (this will use the appropriate Neo4j connection)
        # For now, return a placeholder - actual implementation depends on graph_service capabilities
        result = graph_service.execute_cypher(query)

        # Transform based on mode
        if mode == "schema":
            graph_data = _aggregate_to_schema(result)
        elif mode == "instance":
            graph_data = _format_instance_data(result, limit)
        elif mode == "hybrid":
            graph_data = _format_hybrid_data(result, limit)
        else:
            return jsonify({
                "status": "error",
                "message": f"Invalid mode: {mode}"
            }), 400

        return jsonify({
            "status": "ok",
            "nodes": graph_data["nodes"],
            "edges": graph_data["edges"],
            "mode": mode,
            "count": {
                "nodes": len(graph_data["nodes"]),
                "edges": len(graph_data["edges"]),
            },
        })
    except Exception as e:
        logger.exception("Error getting filtered subgraph")
        return jsonify({"status": "error", "message": str(e)}), 500


def _build_filter_query(
    labels: List[str],
    rel_types: List[str],
    property_filters: List[Dict[str, Any]],
    limit: int = 500,
) -> str:
    """Build Cypher query from filter parameters.

    Args:
        labels: List of node labels to include
        rel_types: List of relationship types to include
        property_filters: List of property filter specifications
        limit: Maximum number of results

    Returns:
        Generated Cypher query string
    """
    # Build node pattern
    if labels:
        label_str = ":".join(labels)
        node_pattern = f"(n:{label_str})"
    else:
        node_pattern = "(n)"

    # Build WHERE clause from property filters
    where_clauses = []
    for pf in property_filters:
        where_clauses.append(_build_where_clause(pf))

    where_str = ""
    if where_clauses:
        where_str = "WHERE " + " AND ".join(where_clauses)

    # Build relationship pattern
    if rel_types:
        rel_str = "|".join(rel_types)
        rel_pattern = f"-[r:{rel_str}]->"
    else:
        rel_pattern = "-[r]->"

    # Construct full query
    query = f"""
    MATCH {node_pattern}{rel_pattern}(m)
    {where_str}
    RETURN n, r, m
    LIMIT {limit}
    """

    return query.strip()


def _build_where_clause(filter_spec: Dict[str, Any]) -> str:
    """Build WHERE clause for a single property filter.

    Args:
        filter_spec: Property filter specification

    Returns:
        Cypher WHERE clause fragment
    """
    label = filter_spec.get("label", "n")
    prop = filter_spec.get("property")
    operator = filter_spec.get("operator", "=")
    value = filter_spec.get("value")
    data_type = filter_spec.get("data_type", "string")

    if operator == "=":
        if data_type == "string":
            return f"n.{prop} = '{value}'"
        else:
            return f"n.{prop} = {value}"

    elif operator == "contains":
        return f"n.{prop} CONTAINS '{value}'"

    elif operator in (">", "<", ">=", "<="):
        if data_type == "date":
            return f"n.{prop} {operator} datetime('{value}')"
        elif data_type == "string":
            return f"n.{prop} {operator} '{value}'"
        else:
            return f"n.{prop} {operator} {value}"

    elif operator == "between":
        if isinstance(value, list) and len(value) == 2:
            if data_type == "date":
                return f"n.{prop} >= datetime('{value[0]}') AND n.{prop} <= datetime('{value[1]}')"
            elif data_type == "string":
                return f"n.{prop} >= '{value[0]}' AND n.{prop} <= '{value[1]}'"
            else:
                return f"n.{prop} >= {value[0]} AND n.{prop} <= {value[1]}"

    return "true"  # Fallback


def _aggregate_to_schema(result: Any) -> Dict[str, Any]:
    """Aggregate query results to schema-level graph.

    Args:
        result: Query result from graph service

    Returns:
        Dictionary with nodes and edges arrays
    """
    # Placeholder implementation - would aggregate instances to schema
    return {"nodes": [], "edges": []}


def _format_instance_data(result: Any, limit: int) -> Dict[str, Any]:
    """Format query results as instance-level graph.

    Args:
        result: Query result from graph service
        limit: Maximum nodes to include

    Returns:
        Dictionary with nodes and edges arrays
    """
    # Placeholder implementation - would format actual instances
    return {"nodes": [], "edges": []}


def _format_hybrid_data(result: Any, limit: int) -> Dict[str, Any]:
    """Format query results as hybrid schema+instance graph.

    Args:
        result: Query result from graph service
        limit: Maximum instance nodes to include

    Returns:
        Dictionary with nodes and edges arrays
    """
    # Placeholder implementation - would combine schema and instances
    return {"nodes": [], "edges": []}
