"""
Chat session persistence service.

Provides database-backed storage for chat sessions and messages,
enabling users to save, load, organize, and share conversations.
"""
import json
import sqlite3
import time
import uuid
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Any

from ..core import path_index_sqlite as pix


@dataclass
class ChatMessage:
    """A single message in a chat session."""
    id: str
    session_id: str
    role: str  # 'user' or 'assistant'
    content: str
    timestamp: float
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'id': self.id,
            'session_id': self.session_id,
            'role': self.role,
            'content': self.content,
            'timestamp': self.timestamp,
            'metadata': self.metadata or {}
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ChatMessage':
        """Create from dictionary."""
        return cls(
            id=data['id'],
            session_id=data['session_id'],
            role=data['role'],
            content=data['content'],
            timestamp=data['timestamp'],
            metadata=data.get('metadata')
        )


@dataclass
class ChatSession:
    """A chat session containing multiple messages."""
    id: str
    name: str
    created_at: float
    updated_at: float
    message_count: int = 0
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'id': self.id,
            'name': self.name,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'message_count': self.message_count,
            'metadata': self.metadata or {}
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ChatSession':
        """Create from dictionary."""
        return cls(
            id=data['id'],
            name=data['name'],
            created_at=data['created_at'],
            updated_at=data['updated_at'],
            message_count=data.get('message_count', 0),
            metadata=data.get('metadata')
        )


class ChatService:
    """Service for managing chat sessions and messages."""

    def __init__(self, db_path: Optional[str] = None):
        """Initialize chat service.

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
        """Ensure chat tables exist by running migrations."""
        from ..core.migrations import migrate
        conn = self._get_conn()
        try:
            migrate(conn)
        finally:
            conn.close()

    # ========== Session Management ==========

    def create_session(self, name: str, metadata: Optional[Dict[str, Any]] = None) -> ChatSession:
        """Create a new chat session.

        Args:
            name: Name/title for the session
            metadata: Optional metadata dictionary (tags, description, etc.)

        Returns:
            Created ChatSession
        """
        session_id = str(uuid.uuid4())
        now = time.time()

        conn = self._get_conn()
        try:
            conn.execute(
                """
                INSERT INTO chat_sessions (id, name, created_at, updated_at, message_count, metadata)
                VALUES (?, ?, ?, ?, 0, ?)
                """,
                (session_id, name, now, now, json.dumps(metadata) if metadata else None)
            )
            conn.commit()

            return ChatSession(
                id=session_id,
                name=name,
                created_at=now,
                updated_at=now,
                message_count=0,
                metadata=metadata
            )
        finally:
            conn.close()

    def get_session(self, session_id: str) -> Optional[ChatSession]:
        """Get a session by ID.

        Args:
            session_id: Session UUID

        Returns:
            ChatSession if found, None otherwise
        """
        conn = self._get_conn()
        try:
            cur = conn.execute(
                """
                SELECT id, name, created_at, updated_at, message_count, metadata
                FROM chat_sessions
                WHERE id = ?
                """,
                (session_id,)
            )
            row = cur.fetchone()
            if not row:
                return None

            return ChatSession(
                id=row['id'],
                name=row['name'],
                created_at=row['created_at'],
                updated_at=row['updated_at'],
                message_count=row['message_count'],
                metadata=json.loads(row['metadata']) if row['metadata'] else None
            )
        finally:
            conn.close()

    def list_sessions(self, limit: int = 100, offset: int = 0) -> List[ChatSession]:
        """List all sessions, ordered by most recently updated.

        Args:
            limit: Maximum number of sessions to return
            offset: Number of sessions to skip (for pagination)

        Returns:
            List of ChatSession objects
        """
        conn = self._get_conn()
        try:
            cur = conn.execute(
                """
                SELECT id, name, created_at, updated_at, message_count, metadata
                FROM chat_sessions
                ORDER BY updated_at DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset)
            )

            sessions = []
            for row in cur.fetchall():
                sessions.append(ChatSession(
                    id=row['id'],
                    name=row['name'],
                    created_at=row['created_at'],
                    updated_at=row['updated_at'],
                    message_count=row['message_count'],
                    metadata=json.loads(row['metadata']) if row['metadata'] else None
                ))

            return sessions
        finally:
            conn.close()

    def update_session(self, session_id: str, name: Optional[str] = None,
                      metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Update session metadata.

        Args:
            session_id: Session UUID
            name: New name (if provided)
            metadata: New metadata (if provided)

        Returns:
            True if session was updated, False if not found
        """
        conn = self._get_conn()
        try:
            updates = []
            params = []

            if name is not None:
                updates.append("name = ?")
                params.append(name)

            if metadata is not None:
                updates.append("metadata = ?")
                params.append(json.dumps(metadata))

            if not updates:
                return True  # Nothing to update

            updates.append("updated_at = ?")
            params.append(time.time())
            params.append(session_id)

            query = f"UPDATE chat_sessions SET {', '.join(updates)} WHERE id = ?"
            cur = conn.execute(query, params)
            conn.commit()

            return cur.rowcount > 0
        finally:
            conn.close()

    def delete_session(self, session_id: str) -> bool:
        """Delete a session and all its messages.

        Args:
            session_id: Session UUID

        Returns:
            True if session was deleted, False if not found
        """
        conn = self._get_conn()
        try:
            # Messages will be cascade deleted due to FOREIGN KEY constraint
            cur = conn.execute("DELETE FROM chat_sessions WHERE id = ?", (session_id,))
            conn.commit()

            return cur.rowcount > 0
        finally:
            conn.close()

    def delete_test_sessions(self, test_id: Optional[str] = None) -> int:
        """Delete all test sessions (for e2e test cleanup).

        Args:
            test_id: Optional test run identifier. If provided, only delete sessions
                    with matching test_id in metadata. If None, delete all sessions
                    marked as test_session=true.

        Returns:
            Number of sessions deleted
        """
        conn = self._get_conn()
        try:
            if test_id:
                # Delete sessions with specific test_id
                cur = conn.execute(
                    """
                    DELETE FROM chat_sessions
                    WHERE json_extract(metadata, '$.test_id') = ?
                    """,
                    (test_id,)
                )
            else:
                # Delete all test sessions
                cur = conn.execute(
                    """
                    DELETE FROM chat_sessions
                    WHERE json_extract(metadata, '$.test_session') = 1
                    """
                )
            conn.commit()
            return cur.rowcount
        finally:
            conn.close()

    # ========== Message Management ==========

    def add_message(self, session_id: str, role: str, content: str,
                   metadata: Optional[Dict[str, Any]] = None) -> ChatMessage:
        """Add a message to a session.

        Args:
            session_id: Session UUID
            role: Message role ('user' or 'assistant')
            content: Message text content
            metadata: Optional metadata (entities, cypher_query, etc.)

        Returns:
            Created ChatMessage
        """
        message_id = str(uuid.uuid4())
        now = time.time()

        conn = self._get_conn()
        try:
            # Insert message
            conn.execute(
                """
                INSERT INTO chat_messages (id, session_id, role, content, metadata, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (message_id, session_id, role, content, json.dumps(metadata) if metadata else None, now)
            )

            # Update session message count and updated_at
            conn.execute(
                """
                UPDATE chat_sessions
                SET message_count = message_count + 1, updated_at = ?
                WHERE id = ?
                """,
                (now, session_id)
            )

            conn.commit()

            return ChatMessage(
                id=message_id,
                session_id=session_id,
                role=role,
                content=content,
                timestamp=now,
                metadata=metadata
            )
        finally:
            conn.close()

    def get_messages(self, session_id: str, limit: Optional[int] = None,
                    offset: int = 0) -> List[ChatMessage]:
        """Get messages for a session.

        Args:
            session_id: Session UUID
            limit: Maximum number of messages (None = all)
            offset: Number of messages to skip

        Returns:
            List of ChatMessage objects, ordered by timestamp
        """
        conn = self._get_conn()
        try:
            if limit is not None:
                query = """
                    SELECT id, session_id, role, content, metadata, timestamp
                    FROM chat_messages
                    WHERE session_id = ?
                    ORDER BY timestamp ASC
                    LIMIT ? OFFSET ?
                """
                params = (session_id, limit, offset)
            else:
                query = """
                    SELECT id, session_id, role, content, metadata, timestamp
                    FROM chat_messages
                    WHERE session_id = ?
                    ORDER BY timestamp ASC
                """
                params = (session_id,)

            cur = conn.execute(query, params)

            messages = []
            for row in cur.fetchall():
                messages.append(ChatMessage(
                    id=row['id'],
                    session_id=row['session_id'],
                    role=row['role'],
                    content=row['content'],
                    timestamp=row['timestamp'],
                    metadata=json.loads(row['metadata']) if row['metadata'] else None
                ))

            return messages
        finally:
            conn.close()

    # ========== Export/Import ==========

    def export_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Export a session and its messages as JSON.

        Args:
            session_id: Session UUID

        Returns:
            Dictionary with session and messages, None if not found
        """
        session = self.get_session(session_id)
        if not session:
            return None

        messages = self.get_messages(session_id)

        return {
            'session': session.to_dict(),
            'messages': [msg.to_dict() for msg in messages]
        }

    def import_session(self, data: Dict[str, Any], new_name: Optional[str] = None) -> ChatSession:
        """Import a session from exported JSON.

        Args:
            data: Exported session data
            new_name: Optional new name for imported session

        Returns:
            Imported ChatSession with new ID
        """
        # Create new session (with new ID to avoid conflicts)
        session_data = data['session']
        name = new_name if new_name else session_data['name']
        metadata = session_data.get('metadata')

        session = self.create_session(name=name, metadata=metadata)

        # Import messages
        for msg_data in data.get('messages', []):
            self.add_message(
                session_id=session.id,
                role=msg_data['role'],
                content=msg_data['content'],
                metadata=msg_data.get('metadata')
            )

        # Refresh session to get updated message count
        return self.get_session(session.id)


def get_chat_service(db_path: Optional[str] = None) -> ChatService:
    """Factory function to get ChatService instance.

    Args:
        db_path: Optional database path. If None, uses default.

    Returns:
        ChatService instance
    """
    return ChatService(db_path=db_path)
