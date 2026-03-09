"""
Chat Neo4j Client - isolated connection management for chat intelligence graph.

Separate from neo4j_client.py to maintain clean separation between:
- Research data (Neo4j on port 7687)
- Chat metadata/intelligence (Chat Neo4j on port 7688)

This client is specifically for chat history, context retrieval, and staleness tracking.
"""
from typing import Optional, Tuple, Dict, Any, List
import os
from neo4j import GraphDatabase  # type: ignore


def get_chat_neo4j_params() -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Read Chat Neo4j connection parameters from environment.

    Returns:
        (uri, user, password) tuple. Returns (None, None, None) if not configured.
    """
    import logging
    logger = logging.getLogger(__name__)

    uri = os.environ.get('CHAT_NEO4J_URI', '').strip()

    # Parse CHAT_NEO4J_AUTH env var (format: "user/password")
    auth_str = os.environ.get('CHAT_NEO4J_AUTH', '').strip()
    user = None
    password = None

    if auth_str:
        if '/' in auth_str:
            parts = auth_str.split('/', 1)
            user = parts[0]
            password = parts[1]
        else:
            logger.warning(
                "CHAT_NEO4J_AUTH is set but invalid format (expected 'user/password'). "
                "Chat Neo4j will be disabled."
            )
            return None, None, None
    else:
        # Fallback to separate env vars if AUTH format not used
        user = os.environ.get('CHAT_NEO4J_USER', '').strip()
        password = os.environ.get('CHAT_NEO4J_PASSWORD', '').strip()

    # Validate: all or nothing
    if not uri and not user and not password:
        # Not configured - graceful degradation
        logger.info("Chat Neo4j not configured (CHAT_NEO4J_URI/CHAT_NEO4J_AUTH missing). Chat context features disabled.")
        return None, None, None

    if not uri:
        logger.warning("CHAT_NEO4J_URI missing. Chat Neo4j disabled.")
        return None, None, None

    if not user or not password:
        logger.warning(
            "CHAT_NEO4J_AUTH incomplete (user or password missing). "
            "Chat Neo4j disabled. Set CHAT_NEO4J_AUTH=user/password"
        )
        return None, None, None

    return uri, user, password


class ChatNeo4jClient:
    """
    Thin client for Chat Neo4j operations.

    Provides connection management and basic query execution for chat intelligence.
    Does NOT handle research data - only chat metadata.
    """

    def __init__(self, uri: Optional[str] = None, user: Optional[str] = None,
                 password: Optional[str] = None):
        """
        Initialize Chat Neo4j client.

        Args:
            uri: Bolt URI (defaults to CHAT_NEO4J_URI env var)
            user: Username (defaults to parsed from CHAT_NEO4J_AUTH)
            password: Password (defaults to parsed from CHAT_NEO4J_AUTH)
        """
        # Use provided params or fall back to environment
        if uri is None or user is None or password is None:
            env_uri, env_user, env_password = get_chat_neo4j_params()
            self._uri = uri or env_uri
            self._user = user or env_user
            self._password = password or env_password
        else:
            self._uri = uri
            self._user = user
            self._password = password

        self._driver = None

    def connect(self):
        """Establish connection to Chat Neo4j."""
        if not self._uri:
            raise ValueError("Chat Neo4j URI not configured. Set CHAT_NEO4J_URI environment variable.")

        auth = (self._user, self._password) if self._user and self._password else None
        self._driver = GraphDatabase.driver(self._uri, auth=auth)
        return self

    def close(self):
        """Close connection to Chat Neo4j."""
        try:
            if self._driver is not None:
                self._driver.close()
        except Exception:
            pass

    def _session(self):
        """Get a session from the driver."""
        if self._driver is None:
            raise RuntimeError("ChatNeo4jClient not connected. Call connect() first.")
        return self._driver.session()

    def execute_read(self, query: str, parameters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Execute a read query and return results as list of dicts.

        Args:
            query: Cypher query string
            parameters: Optional query parameters

        Returns:
            List of records as dictionaries
        """
        with self._session() as session:
            result = session.run(query, parameters or {})
            return [dict(record) for record in result]

    def execute_write(self, query: str, parameters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Execute a write query and return results as list of dicts.

        Args:
            query: Cypher query string
            parameters: Optional query parameters

        Returns:
            List of records as dictionaries
        """
        with self._session() as session:
            result = session.run(query, parameters or {})
            records = [dict(record) for record in result]
            return records

    def ensure_schema(self):
        """
        Create Chat Neo4j schema: indexes and constraints.

        This is idempotent - safe to call multiple times.
        Creates indexes for:
        - ChatMessage: session_id, timestamp, finding_type
        - ChatMessage: vector embedding index
        - ChatSession: session_id
        """
        with self._session() as session:
            # Index on session_id for fast filtering
            try:
                session.run("""
                    CREATE INDEX chat_message_session IF NOT EXISTS
                    FOR (m:ChatMessage) ON (m.session_id)
                """).consume()
            except Exception:
                pass  # May already exist

            # Index on timestamp for temporal queries
            try:
                session.run("""
                    CREATE INDEX chat_message_timestamp IF NOT EXISTS
                    FOR (m:ChatMessage) ON (m.timestamp)
                """).consume()
            except Exception:
                pass

            # Index on finding_type for staleness filtering
            try:
                session.run("""
                    CREATE INDEX chat_message_finding_type IF NOT EXISTS
                    FOR (m:ChatMessage) ON (m.finding_type)
                """).consume()
            except Exception:
                pass

            # Vector index for semantic search (nomic-embed-text: 768 dimensions)
            try:
                session.run("""
                    CREATE VECTOR INDEX chat_message_embedding IF NOT EXISTS
                    FOR (m:ChatMessage) ON (m.embedding)
                    OPTIONS {indexConfig: {
                        `vector.dimensions`: 768,
                        `vector.similarity_function`: 'cosine'
                    }}
                """).consume()
            except Exception:
                # Vector indexes may not be supported in all Neo4j versions
                # Gracefully degrade - semantic search will be skipped
                pass

            # Index on ChatSession session_id for fast lookup
            try:
                session.run("""
                    CREATE INDEX chat_session_id IF NOT EXISTS
                    FOR (s:ChatSession) ON (s.session_id)
                """).consume()
            except Exception:
                pass

    def verify_connection(self) -> bool:
        """
        Verify Chat Neo4j is accessible and responsive.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            with self._session() as session:
                result = session.run("RETURN 1 AS test")
                record = result.single()
                return record is not None and record["test"] == 1
        except Exception:
            return False


def get_chat_neo4j_client() -> Optional[ChatNeo4jClient]:
    """
    Get or create Chat Neo4j client instance.

    Returns:
        Connected ChatNeo4jClient instance if connection parameters are available,
        None otherwise (graceful degradation - chat context features disabled)
    """
    uri, user, password = get_chat_neo4j_params()

    # get_chat_neo4j_params returns (None, None, None) if not configured
    if uri is None:
        return None

    try:
        client = ChatNeo4jClient(uri, user, password)
        client.connect()
        return client
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Chat Neo4j connection failed: {e}. Chat context features disabled.")
        return None
