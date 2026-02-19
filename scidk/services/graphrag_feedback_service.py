"""
GraphRAG Feedback service for collecting and analyzing query feedback.

Stores structured feedback about GraphRAG query results to improve:
- Entity extraction accuracy
- Query understanding
- Result relevance
- Schema terminology mapping
"""
import json
import sqlite3
import time
import uuid
from dataclasses import dataclass
from typing import List, Optional, Dict, Any

from ..core import path_index_sqlite as pix


@dataclass
class GraphRAGFeedback:
    """Feedback entry for a GraphRAG query."""
    id: str
    session_id: Optional[str]
    message_id: Optional[str]
    query: str
    entities_extracted: Dict[str, Any]
    cypher_generated: Optional[str]
    feedback: Dict[str, Any]
    timestamp: float

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'id': self.id,
            'session_id': self.session_id,
            'message_id': self.message_id,
            'query': self.query,
            'entities_extracted': self.entities_extracted,
            'cypher_generated': self.cypher_generated,
            'feedback': self.feedback,
            'timestamp': self.timestamp
        }


class GraphRAGFeedbackService:
    """Service for managing GraphRAG feedback."""

    def __init__(self, db_path: Optional[str] = None):
        """Initialize feedback service.

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
        """Ensure feedback table exists."""
        from ..core.migrations import migrate
        conn = self._get_conn()
        try:
            migrate(conn)
        finally:
            conn.close()

    # ========== Feedback Management ==========

    def add_feedback(
        self,
        query: str,
        entities_extracted: Dict[str, Any],
        feedback: Dict[str, Any],
        session_id: Optional[str] = None,
        message_id: Optional[str] = None,
        cypher_generated: Optional[str] = None
    ) -> GraphRAGFeedback:
        """Add feedback for a GraphRAG query.

        Args:
            query: Original natural language query
            entities_extracted: Entities extracted by the system
            feedback: Structured feedback dictionary containing:
                - answered_question: bool - Did the query answer the question?
                - entity_corrections: Dict with 'removed' and 'added' lists
                - query_corrections: str - User's corrected/reformulated query
                - missing_results: str - Description of missing results
                - schema_terminology: Dict mapping user terms to schema terms
                - notes: str - Free text feedback
            session_id: Optional chat session ID
            message_id: Optional message ID
            cypher_generated: Optional Cypher query that was generated

        Returns:
            Created GraphRAGFeedback object
        """
        feedback_id = str(uuid.uuid4())
        now = time.time()

        conn = self._get_conn()
        try:
            conn.execute(
                """
                INSERT INTO graphrag_feedback (
                    id, session_id, message_id, query, entities_extracted,
                    cypher_generated, feedback, timestamp
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    feedback_id,
                    session_id,
                    message_id,
                    query,
                    json.dumps(entities_extracted),
                    cypher_generated,
                    json.dumps(feedback),
                    now
                )
            )
            conn.commit()

            return GraphRAGFeedback(
                id=feedback_id,
                session_id=session_id,
                message_id=message_id,
                query=query,
                entities_extracted=entities_extracted,
                cypher_generated=cypher_generated,
                feedback=feedback,
                timestamp=now
            )
        finally:
            conn.close()

    def get_feedback(self, feedback_id: str) -> Optional[GraphRAGFeedback]:
        """Get feedback by ID.

        Args:
            feedback_id: Feedback UUID

        Returns:
            GraphRAGFeedback if found, None otherwise
        """
        conn = self._get_conn()
        try:
            cur = conn.execute(
                """
                SELECT id, session_id, message_id, query, entities_extracted,
                       cypher_generated, feedback, timestamp
                FROM graphrag_feedback
                WHERE id = ?
                """,
                (feedback_id,)
            )
            row = cur.fetchone()
            if not row:
                return None

            return GraphRAGFeedback(
                id=row['id'],
                session_id=row['session_id'],
                message_id=row['message_id'],
                query=row['query'],
                entities_extracted=json.loads(row['entities_extracted']),
                cypher_generated=row['cypher_generated'],
                feedback=json.loads(row['feedback']),
                timestamp=row['timestamp']
            )
        finally:
            conn.close()

    def list_feedback(
        self,
        session_id: Optional[str] = None,
        answered_question: Optional[bool] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[GraphRAGFeedback]:
        """List feedback entries with optional filters.

        Args:
            session_id: Filter by session ID
            answered_question: Filter by whether question was answered (True/False/None)
            limit: Maximum number of entries
            offset: Number of entries to skip

        Returns:
            List of GraphRAGFeedback objects
        """
        conn = self._get_conn()
        try:
            query_parts = ["""
                SELECT id, session_id, message_id, query, entities_extracted,
                       cypher_generated, feedback, timestamp
                FROM graphrag_feedback
            """]
            params = []
            where_clauses = []

            if session_id:
                where_clauses.append("session_id = ?")
                params.append(session_id)

            if answered_question is not None:
                # Use JSON extraction for SQLite
                where_clauses.append("json_extract(feedback, '$.answered_question') = ?")
                params.append(1 if answered_question else 0)

            if where_clauses:
                query_parts.append("WHERE " + " AND ".join(where_clauses))

            query_parts.append("ORDER BY timestamp DESC LIMIT ? OFFSET ?")
            params.extend([limit, offset])

            cur = conn.execute(" ".join(query_parts), params)

            feedback_list = []
            for row in cur.fetchall():
                feedback_list.append(GraphRAGFeedback(
                    id=row['id'],
                    session_id=row['session_id'],
                    message_id=row['message_id'],
                    query=row['query'],
                    entities_extracted=json.loads(row['entities_extracted']),
                    cypher_generated=row['cypher_generated'],
                    feedback=json.loads(row['feedback']),
                    timestamp=row['timestamp']
                ))

            return feedback_list
        finally:
            conn.close()

    def get_feedback_stats(self) -> Dict[str, Any]:
        """Get aggregated feedback statistics.

        Returns:
            Dictionary with:
                - total_feedback_count: Total feedback entries
                - answered_yes_count: Queries that answered the question
                - answered_no_count: Queries that did not answer
                - entity_corrections_count: Feedback with entity corrections
                - query_corrections_count: Feedback with query reformulations
                - terminology_corrections_count: Feedback with terminology mappings
        """
        conn = self._get_conn()
        try:
            # Total count
            cur = conn.execute("SELECT COUNT(*) as total FROM graphrag_feedback")
            total = cur.fetchone()['total']

            # Answered yes
            cur = conn.execute(
                "SELECT COUNT(*) as count FROM graphrag_feedback WHERE json_extract(feedback, '$.answered_question') = 1"
            )
            answered_yes = cur.fetchone()['count']

            # Answered no
            cur = conn.execute(
                "SELECT COUNT(*) as count FROM graphrag_feedback WHERE json_extract(feedback, '$.answered_question') = 0"
            )
            answered_no = cur.fetchone()['count']

            # Entity corrections
            cur = conn.execute(
                """
                SELECT COUNT(*) as count FROM graphrag_feedback
                WHERE json_extract(feedback, '$.entity_corrections') IS NOT NULL
                """
            )
            entity_corrections = cur.fetchone()['count']

            # Query corrections
            cur = conn.execute(
                """
                SELECT COUNT(*) as count FROM graphrag_feedback
                WHERE json_extract(feedback, '$.query_corrections') IS NOT NULL
                  AND json_extract(feedback, '$.query_corrections') != ''
                """
            )
            query_corrections = cur.fetchone()['count']

            # Terminology corrections
            cur = conn.execute(
                """
                SELECT COUNT(*) as count FROM graphrag_feedback
                WHERE json_extract(feedback, '$.schema_terminology') IS NOT NULL
                """
            )
            terminology_corrections = cur.fetchone()['count']

            return {
                'total_feedback_count': total,
                'answered_yes_count': answered_yes,
                'answered_no_count': answered_no,
                'entity_corrections_count': entity_corrections,
                'query_corrections_count': query_corrections,
                'terminology_corrections_count': terminology_corrections,
                'answer_rate': round(answered_yes / total * 100, 1) if total > 0 else 0
            }
        finally:
            conn.close()

    # ========== Analysis Utilities ==========

    def get_entity_corrections(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get all entity corrections for analysis.

        Returns:
            List of dictionaries with:
                - query: Original query
                - extracted: Entities extracted by system
                - corrections: User corrections (removed/added)
                - timestamp: When feedback was given
        """
        conn = self._get_conn()
        try:
            cur = conn.execute(
                """
                SELECT query, entities_extracted, feedback, timestamp
                FROM graphrag_feedback
                WHERE json_extract(feedback, '$.entity_corrections') IS NOT NULL
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (limit,)
            )

            corrections = []
            for row in cur.fetchall():
                feedback_data = json.loads(row['feedback'])
                corrections.append({
                    'query': row['query'],
                    'extracted': json.loads(row['entities_extracted']),
                    'corrections': feedback_data.get('entity_corrections', {}),
                    'timestamp': row['timestamp']
                })

            return corrections
        finally:
            conn.close()

    def get_query_reformulations(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get query reformulations for training data.

        Returns:
            List of dictionaries with:
                - original_query: User's original query
                - corrected_query: User's reformulated query
                - entities_extracted: What system extracted
                - timestamp: When feedback was given
        """
        conn = self._get_conn()
        try:
            cur = conn.execute(
                """
                SELECT query, entities_extracted, feedback, timestamp
                FROM graphrag_feedback
                WHERE json_extract(feedback, '$.query_corrections') IS NOT NULL
                  AND json_extract(feedback, '$.query_corrections') != ''
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (limit,)
            )

            reformulations = []
            for row in cur.fetchall():
                feedback_data = json.loads(row['feedback'])
                reformulations.append({
                    'original_query': row['query'],
                    'corrected_query': feedback_data.get('query_corrections', ''),
                    'entities_extracted': json.loads(row['entities_extracted']),
                    'timestamp': row['timestamp']
                })

            return reformulations
        finally:
            conn.close()

    def get_terminology_mappings(self) -> Dict[str, str]:
        """Get schema terminology mappings from feedback.

        Returns:
            Dictionary mapping user terms to schema terms:
            {'experiments': 'Assays', 'samples': 'Specimens', ...}
        """
        conn = self._get_conn()
        try:
            cur = conn.execute(
                """
                SELECT feedback
                FROM graphrag_feedback
                WHERE json_extract(feedback, '$.schema_terminology') IS NOT NULL
                """
            )

            mappings = {}
            for row in cur.fetchall():
                feedback_data = json.loads(row['feedback'])
                terminology = feedback_data.get('schema_terminology', {})
                if isinstance(terminology, dict):
                    mappings.update(terminology)

            return mappings
        finally:
            conn.close()


def get_graphrag_feedback_service(db_path: Optional[str] = None) -> GraphRAGFeedbackService:
    """Factory function to get GraphRAGFeedbackService instance.

    Args:
        db_path: Optional database path. If None, uses default.

    Returns:
        GraphRAGFeedbackService instance
    """
    return GraphRAGFeedbackService(db_path=db_path)
