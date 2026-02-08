"""
Service for managing saved Cypher queries.

Provides CRUD operations for user's query library with usage tracking.
"""
import json
import sqlite3
import time
import uuid
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Any

try:
    from .. import path_index_sqlite as pix
except (ImportError, ValueError):
    pix = None


@dataclass
class SavedQuery:
    """Represents a saved Cypher query."""
    id: str
    name: str
    query: str
    description: Optional[str]
    tags: Optional[List[str]]
    created_at: float
    updated_at: float
    last_used_at: Optional[float]
    use_count: int
    metadata: Optional[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'id': self.id,
            'name': self.name,
            'query': self.query,
            'description': self.description,
            'tags': self.tags,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'last_used_at': self.last_used_at,
            'use_count': self.use_count,
            'metadata': self.metadata
        }

    @staticmethod
    def from_row(row: sqlite3.Row) -> 'SavedQuery':
        """Create from database row."""
        tags = json.loads(row['tags']) if row['tags'] else None
        metadata = json.loads(row['metadata']) if row['metadata'] else None

        return SavedQuery(
            id=row['id'],
            name=row['name'],
            query=row['query'],
            description=row['description'],
            tags=tags,
            created_at=row['created_at'],
            updated_at=row['updated_at'],
            last_used_at=row['last_used_at'],
            use_count=row['use_count'] or 0,
            metadata=metadata
        )


class QueryService:
    """Service for managing saved queries."""

    def __init__(self, db_path: Optional[str] = None):
        """Initialize query service.

        Args:
            db_path: Path to SQLite database. If None, uses default from path_index_sqlite.
        """
        self.db_path = db_path
        self._ensure_tables()

    def _get_conn(self) -> sqlite3.Connection:
        """Get database connection."""
        if self.db_path:
            conn = sqlite3.connect(self.db_path)
        else:
            conn = pix.connect()
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_tables(self):
        """Ensure query tables exist by running migrations."""
        from ..core.migrations import migrate
        conn = self._get_conn()
        try:
            migrate(conn)
        finally:
            conn.close()

    # ========== Query Management ==========

    def save_query(self, name: str, query: str, description: Optional[str] = None,
                   tags: Optional[List[str]] = None, metadata: Optional[Dict[str, Any]] = None) -> SavedQuery:
        """Save a new query to the library.

        Args:
            name: Query name
            query: Cypher query text
            description: Optional description
            tags: Optional list of tags
            metadata: Optional metadata (e.g., source_chat_session_id, result_count, etc.)

        Returns:
            Created SavedQuery
        """
        query_id = str(uuid.uuid4())
        now = time.time()

        conn = self._get_conn()
        try:
            conn.execute(
                """
                INSERT INTO saved_queries
                (id, name, query, description, tags, created_at, updated_at, use_count, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)
                """,
                (
                    query_id,
                    name,
                    query,
                    description,
                    json.dumps(tags) if tags else None,
                    now,
                    now,
                    json.dumps(metadata) if metadata else None
                )
            )
            conn.commit()

            return SavedQuery(
                id=query_id,
                name=name,
                query=query,
                description=description,
                tags=tags,
                created_at=now,
                updated_at=now,
                last_used_at=None,
                use_count=0,
                metadata=metadata
            )
        finally:
            conn.close()

    def get_query(self, query_id: str) -> Optional[SavedQuery]:
        """Get a query by ID.

        Args:
            query_id: Query UUID

        Returns:
            SavedQuery if found, None otherwise
        """
        conn = self._get_conn()
        try:
            cur = conn.execute(
                """
                SELECT * FROM saved_queries WHERE id = ?
                """,
                (query_id,)
            )
            row = cur.fetchone()
            return SavedQuery.from_row(row) if row else None
        finally:
            conn.close()

    def list_queries(self, limit: int = 100, offset: int = 0,
                     sort_by: str = 'updated_at') -> List[SavedQuery]:
        """List all saved queries.

        Args:
            limit: Maximum number of queries to return
            offset: Number of queries to skip
            sort_by: Sort field ('updated_at', 'last_used_at', 'name', 'use_count')

        Returns:
            List of SavedQuery objects
        """
        valid_sorts = {'updated_at', 'last_used_at', 'name', 'use_count'}
        if sort_by not in valid_sorts:
            sort_by = 'updated_at'

        sort_order = 'DESC' if sort_by in {'updated_at', 'last_used_at', 'use_count'} else 'ASC'

        conn = self._get_conn()
        try:
            cur = conn.execute(
                f"""
                SELECT * FROM saved_queries
                ORDER BY {sort_by} {sort_order}
                LIMIT ? OFFSET ?
                """,
                (limit, offset)
            )
            return [SavedQuery.from_row(row) for row in cur.fetchall()]
        finally:
            conn.close()

    def update_query(self, query_id: str, name: Optional[str] = None,
                     query: Optional[str] = None, description: Optional[str] = None,
                     tags: Optional[List[str]] = None, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Update a saved query.

        Args:
            query_id: Query UUID
            name: New name (optional)
            query: New query text (optional)
            description: New description (optional)
            tags: New tags list (optional)
            metadata: New metadata (optional)

        Returns:
            True if query was updated, False if not found
        """
        conn = self._get_conn()
        try:
            updates = []
            params = []

            if name is not None:
                updates.append("name = ?")
                params.append(name)

            if query is not None:
                updates.append("query = ?")
                params.append(query)

            if description is not None:
                updates.append("description = ?")
                params.append(description)

            if tags is not None:
                updates.append("tags = ?")
                params.append(json.dumps(tags))

            if metadata is not None:
                updates.append("metadata = ?")
                params.append(json.dumps(metadata))

            if not updates:
                return True  # Nothing to update

            updates.append("updated_at = ?")
            params.append(time.time())
            params.append(query_id)

            query_str = f"UPDATE saved_queries SET {', '.join(updates)} WHERE id = ?"
            cur = conn.execute(query_str, params)
            conn.commit()

            return cur.rowcount > 0
        finally:
            conn.close()

    def delete_query(self, query_id: str) -> bool:
        """Delete a saved query.

        Args:
            query_id: Query UUID

        Returns:
            True if query was deleted, False if not found
        """
        conn = self._get_conn()
        try:
            cur = conn.execute("DELETE FROM saved_queries WHERE id = ?", (query_id,))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def record_usage(self, query_id: str) -> bool:
        """Record that a query was used (increments use_count, updates last_used_at).

        Args:
            query_id: Query UUID

        Returns:
            True if updated successfully
        """
        conn = self._get_conn()
        try:
            cur = conn.execute(
                """
                UPDATE saved_queries
                SET use_count = use_count + 1,
                    last_used_at = ?
                WHERE id = ?
                """,
                (time.time(), query_id)
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def search_queries(self, search_term: str, limit: int = 50) -> List[SavedQuery]:
        """Search queries by name, query text, or description.

        Args:
            search_term: Text to search for
            limit: Maximum number of results

        Returns:
            List of matching SavedQuery objects
        """
        conn = self._get_conn()
        try:
            cur = conn.execute(
                """
                SELECT * FROM saved_queries
                WHERE name LIKE ? OR query LIKE ? OR description LIKE ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (f'%{search_term}%', f'%{search_term}%', f'%{search_term}%', limit)
            )
            return [SavedQuery.from_row(row) for row in cur.fetchall()]
        finally:
            conn.close()


# Global instance cache
_query_service_instance: Optional[QueryService] = None


def get_query_service(db_path: Optional[str] = None) -> QueryService:
    """Get or create QueryService instance.

    Args:
        db_path: Optional database path. If None, uses default.

    Returns:
        QueryService instance
    """
    global _query_service_instance

    if _query_service_instance is None or db_path:
        _query_service_instance = QueryService(db_path=db_path)

    return _query_service_instance
