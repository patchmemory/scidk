"""Service for managing saved map configurations.

Saved maps allow users to persist graph visualization states including:
- Cypher queries
- Filter selections (labels, relationship types, properties)
- Visualization settings (mode, layout, styles)
"""

import logging
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class SavedMap:
    """Represents a saved map configuration."""

    id: str
    name: str
    description: Optional[str] = None
    query: Optional[str] = None
    filters: Dict[str, Any] = field(default_factory=dict)
    visualization: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    use_count: int = 0
    last_used_at: Optional[float] = None
    tags: str = ""
    # Canvas (Push 2) fields
    display_mode: str = "instance"  # 'schema' | 'instance'
    layers: List[Dict[str, Any]] = field(default_factory=list)
    snapshot_json: Optional[Dict[str, Any]] = None
    snapshot_saved_at: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "query": self.query,
            "filters": self.filters,
            "visualization": self.visualization,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "use_count": self.use_count,
            "last_used_at": self.last_used_at,
            "tags": self.tags,
            "display_mode": self.display_mode,
            "layers": self.layers,
            "snapshot_json": self.snapshot_json,
            "snapshot_saved_at": self.snapshot_saved_at,
        }


class SavedMapsService:
    """Service for managing saved map configurations."""

    def __init__(self, db_path: Optional[str] = None):
        """Initialize service with optional custom database path."""
        self.db_path = db_path or 'scidk_settings.db'
        self._ensure_table_exists()

    def _ensure_table_exists(self):
        """Create saved_maps table if it doesn't exist."""
        import json

        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS saved_maps (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    query TEXT,
                    filters TEXT,
                    visualization TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    use_count INTEGER DEFAULT 0,
                    last_used_at REAL,
                    tags TEXT
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_saved_maps_updated
                ON saved_maps(updated_at DESC)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_saved_maps_used
                ON saved_maps(last_used_at DESC)
            """)
            # Canvas (Push 2) columns — added idempotently so pre-existing tables
            # upgrade in place. saved_maps lives in scidk_settings.db, NOT the
            # path-index DB that scidk/core/migrations.py targets, so this is the
            # correct place to evolve its schema.
            existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(saved_maps)")}
            canvas_cols = {
                "display_mode": "TEXT",       # 'schema' | 'instance' (default 'instance')
                "layers": "TEXT",             # JSON array of {layer_id,name,cypher,enabled}
                "snapshot_json": "TEXT",      # JSON {nodes:[...],edges:[...]}
                "snapshot_saved_at": "REAL",  # epoch seconds; NULL until first snapshot
            }
            for col, col_type in canvas_cols.items():
                if col not in existing_cols:
                    conn.execute(f"ALTER TABLE saved_maps ADD COLUMN {col} {col_type}")
            conn.commit()
            logger.debug("Ensured saved_maps table exists")
        finally:
            conn.close()

    @staticmethod
    def _row_to_map(row: sqlite3.Row) -> "SavedMap":
        """Build a SavedMap from a sqlite Row, tolerating rows missing the
        canvas columns (older DBs read before _ensure_table_exists upgrade)."""
        import json

        keys = set(row.keys())

        def _col(name, default=None):
            return row[name] if name in keys else default

        raw_layers = _col("layers")
        raw_snapshot = _col("snapshot_json")
        return SavedMap(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            query=row["query"],
            filters=json.loads(row["filters"] or "{}"),
            visualization=json.loads(row["visualization"] or "{}"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            use_count=row["use_count"],
            last_used_at=row["last_used_at"],
            tags=row["tags"] or "",
            display_mode=_col("display_mode") or "instance",
            layers=json.loads(raw_layers) if raw_layers else [],
            snapshot_json=json.loads(raw_snapshot) if raw_snapshot else None,
            snapshot_saved_at=_col("snapshot_saved_at"),
        )

    def save_map(
        self,
        name: str,
        description: Optional[str] = None,
        query: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        visualization: Optional[Dict[str, Any]] = None,
        tags: Optional[str] = None,
        display_mode: str = "instance",
        layers: Optional[List[Dict[str, Any]]] = None,
        snapshot_json: Optional[Dict[str, Any]] = None,
    ) -> SavedMap:
        """Create new saved map.

        Args:
            name: Display name for the map
            description: Optional description
            query: Cypher query or None for full graph
            filters: Filter configuration (labels, rel_types, properties)
            visualization: Visualization settings (mode, layout, styles)
            tags: Comma-separated tags for organization

        Returns:
            SavedMap instance with generated ID
        """
        import json

        map_id = str(uuid.uuid4())
        now = time.time()

        filters = filters or {}
        visualization = visualization or {}
        layers = layers or []
        display_mode = display_mode if display_mode in ("schema", "instance") else "instance"
        snapshot_saved_at = now if snapshot_json is not None else None

        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                """
                INSERT INTO saved_maps
                (id, name, description, query, filters, visualization,
                 created_at, updated_at, use_count, last_used_at, tags,
                 display_mode, layers, snapshot_json, snapshot_saved_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, NULL, ?, ?, ?, ?, ?)
                """,
                (
                    map_id,
                    name,
                    description,
                    query,
                    json.dumps(filters),
                    json.dumps(visualization),
                    now,
                    now,
                    tags or "",
                    display_mode,
                    json.dumps(layers),
                    json.dumps(snapshot_json) if snapshot_json is not None else None,
                    snapshot_saved_at,
                ),
            )
            conn.commit()
            logger.info(f"Saved map '{name}' with ID {map_id}")
        finally:
            conn.close()

        return SavedMap(
            id=map_id,
            name=name,
            description=description,
            query=query,
            filters=filters,
            visualization=visualization,
            created_at=now,
            updated_at=now,
            use_count=0,
            last_used_at=None,
            tags=tags or "",
            display_mode=display_mode,
            layers=layers,
            snapshot_json=snapshot_json,
            snapshot_saved_at=snapshot_saved_at,
        )

    def list_maps(
        self,
        limit: int = 100,
        offset: int = 0,
        sort_by: str = "updated_at",
        order: str = "DESC",
    ) -> List[SavedMap]:
        """List saved maps with pagination and sorting.

        Args:
            limit: Maximum number of maps to return
            offset: Number of maps to skip
            sort_by: Field to sort by (updated_at, created_at, last_used_at, name, use_count)
            order: Sort order (ASC or DESC)

        Returns:
            List of SavedMap instances
        """
        import json

        valid_sort_fields = {
            "updated_at",
            "created_at",
            "last_used_at",
            "name",
            "use_count",
        }
        if sort_by not in valid_sort_fields:
            sort_by = "updated_at"
        if order.upper() not in ("ASC", "DESC"):
            order = "DESC"

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.execute(
                f"""
                SELECT * FROM saved_maps
                ORDER BY {sort_by} {order}
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            )
            rows = cursor.fetchall()

            return [self._row_to_map(row) for row in rows]
        finally:
            conn.close()

    def get_map(self, map_id: str) -> Optional[SavedMap]:
        """Get specific map by ID.

        Args:
            map_id: Unique map identifier

        Returns:
            SavedMap instance or None if not found
        """
        import json

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.execute(
                "SELECT * FROM saved_maps WHERE id = ?", (map_id,)
            )
            row = cursor.fetchone()

            if not row:
                return None

            return self._row_to_map(row)
        finally:
            conn.close()

    def update_map(self, map_id: str, **kwargs) -> Optional[SavedMap]:
        """Update map configuration.

        Args:
            map_id: Unique map identifier
            **kwargs: Fields to update (name, description, query, filters, visualization, tags)

        Returns:
            Updated SavedMap instance or None if not found
        """
        import json

        existing = self.get_map(map_id)
        if not existing:
            return None

        allowed_fields = {
            "name",
            "description",
            "query",
            "filters",
            "visualization",
            "tags",
            "display_mode",
            "layers",
            "snapshot_json",
        }
        updates = {k: v for k, v in kwargs.items() if k in allowed_fields}

        if not updates:
            return existing

        # Serialize JSON fields
        if "filters" in updates:
            updates["filters"] = json.dumps(updates["filters"])
        if "visualization" in updates:
            updates["visualization"] = json.dumps(updates["visualization"])
        if "layers" in updates:
            updates["layers"] = json.dumps(updates["layers"] or [])
        if "display_mode" in updates and updates["display_mode"] not in ("schema", "instance"):
            updates["display_mode"] = "instance"
        if "snapshot_json" in updates:
            snap = updates["snapshot_json"]
            updates["snapshot_json"] = json.dumps(snap) if snap is not None else None
            # Refreshing the snapshot stamps its save time (addendum: explicit Refresh).
            updates["snapshot_saved_at"] = time.time()

        updates["updated_at"] = time.time()

        # Build UPDATE query
        set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
        values = list(updates.values()) + [map_id]

        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                f"UPDATE saved_maps SET {set_clause} WHERE id = ?", values
            )
            conn.commit()
            logger.info(f"Updated map {map_id}")
        finally:
            conn.close()

        return self.get_map(map_id)

    def delete_map(self, map_id: str) -> bool:
        """Delete saved map.

        Args:
            map_id: Unique map identifier

        Returns:
            True if deleted, False if not found
        """
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute("DELETE FROM saved_maps WHERE id = ?", (map_id,))
            conn.commit()
            deleted = cursor.rowcount > 0
            if deleted:
                logger.info(f"Deleted map {map_id}")
            return deleted
        finally:
            conn.close()

    def track_usage(self, map_id: str) -> bool:
        """Increment use_count and update last_used_at.

        Args:
            map_id: Unique map identifier

        Returns:
            True if updated, False if map not found
        """
        now = time.time()
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute(
                """
                UPDATE saved_maps
                SET use_count = use_count + 1, last_used_at = ?
                WHERE id = ?
                """,
                (now, map_id),
            )
            conn.commit()
            updated = cursor.rowcount > 0
            if updated:
                logger.debug(f"Tracked usage for map {map_id}")
            return updated
        finally:
            conn.close()


# Singleton instance
_saved_maps_service: Optional[SavedMapsService] = None


def get_saved_maps_service(db_path: Optional[str] = None) -> SavedMapsService:
    """Get or create SavedMapsService singleton instance.

    Args:
        db_path: Optional custom database path

    Returns:
        SavedMapsService instance
    """
    global _saved_maps_service
    if _saved_maps_service is None or db_path is not None:
        _saved_maps_service = SavedMapsService(db_path)
    return _saved_maps_service
