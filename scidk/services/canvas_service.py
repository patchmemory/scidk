"""Service for Maps Canvas (Push 2) persistence.

Owns two SQLite tables in the settings DB (scidk_settings.db), colocated with
saved_maps — NOT the path-index DB that scidk/core/migrations.py targets:

- canvas_query_library: reusable Cypher snippets for building canvas layers.
- canvas_session: per-user in-progress canvas state, so a canvas survives a
  browser refresh without touching Neo4j or a named saved map.

Named saved layers (with display_mode/layers/snapshot_json) live in saved_maps
and are handled by SavedMapsService, not here.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import time
import uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class CanvasService:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or "scidk_settings.db"
        self._ensure_tables_exist()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_tables_exist(self) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS canvas_query_library (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    cypher TEXT NOT NULL,
                    created_by TEXT,
                    created_at REAL,
                    updated_at REAL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS canvas_session (
                    user_id TEXT PRIMARY KEY,
                    canvas_json TEXT,
                    updated_at REAL
                )
                """
            )
            conn.commit()
            logger.debug("Ensured canvas_query_library and canvas_session tables exist")
        finally:
            conn.close()

    # --- canvas_query_library ---
    def list_queries(self, limit: int = 100) -> List[Dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM canvas_query_library ORDER BY updated_at DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def create_query(self, name: str, cypher: str, created_by: Optional[str] = None) -> Dict[str, Any]:
        qid = str(uuid.uuid4())
        now = time.time()
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO canvas_query_library (id, name, cypher, created_by, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (qid, name, cypher, created_by, now, now),
            )
            conn.commit()
        finally:
            conn.close()
        return {
            "id": qid,
            "name": name,
            "cypher": cypher,
            "created_by": created_by,
            "created_at": now,
            "updated_at": now,
        }

    def get_query(self, query_id: str) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM canvas_query_library WHERE id = ?", (query_id,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def delete_query(self, query_id: str) -> bool:
        conn = self._connect()
        try:
            cur = conn.execute("DELETE FROM canvas_query_library WHERE id = ?", (query_id,))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    # --- canvas_session (per-user in-progress canvas) ---
    def save_session(self, user_id: str, canvas: Dict[str, Any]) -> float:
        """Upsert the user's current canvas JSON. Returns the save timestamp."""
        now = time.time()
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO canvas_session (user_id, canvas_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    canvas_json = excluded.canvas_json,
                    updated_at = excluded.updated_at
                """,
                (user_id, json.dumps(canvas or {}), now),
            )
            conn.commit()
        finally:
            conn.close()
        return now

    def load_session(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Return {canvas, updated_at} for the user, or None if no session saved."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT canvas_json, updated_at FROM canvas_session WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if not row:
                return None
            raw = row["canvas_json"]
            return {
                "canvas": json.loads(raw) if raw else {},
                "updated_at": row["updated_at"],
            }
        finally:
            conn.close()

    def clear_session(self, user_id: str) -> bool:
        conn = self._connect()
        try:
            cur = conn.execute("DELETE FROM canvas_session WHERE user_id = ?", (user_id,))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()


_canvas_service: Optional[CanvasService] = None


def get_canvas_service(db_path: Optional[str] = None) -> CanvasService:
    global _canvas_service
    if _canvas_service is None or db_path is not None:
        _canvas_service = CanvasService(db_path)
    return _canvas_service
