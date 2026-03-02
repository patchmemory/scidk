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
            conn.commit()
            logger.debug("Ensured saved_maps table exists")
        finally:
            conn.close()

    def save_map(
        self,
        name: str,
        description: Optional[str] = None,
        query: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        visualization: Optional[Dict[str, Any]] = None,
        tags: Optional[str] = None,
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

        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                """
                INSERT INTO saved_maps
                (id, name, description, query, filters, visualization,
                 created_at, updated_at, use_count, last_used_at, tags)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, NULL, ?)
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

            maps = []
            for row in rows:
                maps.append(
                    SavedMap(
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
                    )
                )
            return maps
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
            )
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
        }
        updates = {k: v for k, v in kwargs.items() if k in allowed_fields}

        if not updates:
            return existing

        # Serialize JSON fields
        if "filters" in updates:
            updates["filters"] = json.dumps(updates["filters"])
        if "visualization" in updates:
            updates["visualization"] = json.dumps(updates["visualization"])

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
