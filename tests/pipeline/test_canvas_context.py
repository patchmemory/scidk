"""The ``canvas_session`` context key, its migration, and the user key.

Two changes with a shared motivation: per-user, per-canvas state was keyed by a
string whose meaning was decided at the call site. ``canvas_session`` had a
single-column primary key, so a Pipeline source's schema canvas would have
overwritten the user's main Maps canvas; and ``_current_user_id`` mixed a row id,
a username and a literal behind one name.

The migration is the risky part — SQLite cannot alter a primary key in place, so
it is a rebuild-and-copy that runs on a table which may already hold live
sessions, on every service construction.
"""
from __future__ import annotations

import json
import sqlite3

import pytest

from scidk.services.canvas_service import (
    DEFAULT_CONTEXT_ID,
    CanvasService,
    pipeline_source_context,
)


@pytest.fixture
def db(tmp_path) -> str:
    return str(tmp_path / "scidk_settings.db")


@pytest.fixture
def service(db) -> CanvasService:
    return CanvasService(db)


def make_pre_context_table(db: str, rows) -> None:
    """Build canvas_session exactly as it shipped, with rows in it."""
    conn = sqlite3.connect(db)
    try:
        conn.execute(
            """
            CREATE TABLE canvas_session (
                user_id TEXT PRIMARY KEY,
                canvas_json TEXT,
                updated_at REAL
            )
            """
        )
        conn.executemany(
            "INSERT INTO canvas_session (user_id, canvas_json, updated_at) VALUES (?, ?, ?)",
            rows,
        )
        conn.commit()
    finally:
        conn.close()


def primary_key_columns(db: str) -> list:
    conn = sqlite3.connect(db)
    try:
        return [r[1] for r in conn.execute("PRAGMA table_info(canvas_session)") if r[5]]
    finally:
        conn.close()


# --------------------------------------------------------------- migration

def test_a_fresh_database_gets_the_composite_key(service, db):
    assert primary_key_columns(db) == ["user_id", "context_id"]


def test_an_existing_table_is_upgraded_in_place(db):
    make_pre_context_table(db, [("42", json.dumps({"nodes": [{"id": "n1"}]}), 1000.0)])
    assert primary_key_columns(db) == ["user_id"]

    service = CanvasService(db)

    assert primary_key_columns(db) == ["user_id", "context_id"]
    session = service.load_session("42")
    assert session["canvas"] == {"nodes": [{"id": "n1"}]}
    assert session["updated_at"] == 1000.0


def test_existing_rows_land_on_the_main_canvas_not_a_new_context(db):
    """A user with a canvas open across the upgrade still finds it where it was."""
    make_pre_context_table(db, [("42", json.dumps({"nodes": []}), 1.0)])
    CanvasService(db)

    conn = sqlite3.connect(db)
    try:
        contexts = [r[0] for r in conn.execute("SELECT context_id FROM canvas_session")]
    finally:
        conn.close()
    assert contexts == [DEFAULT_CONTEXT_ID]


def test_the_upgrade_is_idempotent(db):
    make_pre_context_table(db, [("42", json.dumps({"nodes": [1]}), 1.0)])
    for _ in range(3):
        CanvasService(db)

    conn = sqlite3.connect(db)
    try:
        assert conn.execute("SELECT COUNT(*) FROM canvas_session").fetchone()[0] == 1
        leftovers = [
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE name LIKE 'canvas_session%'"
            )
        ]
    finally:
        conn.close()
    assert leftovers == ["canvas_session"], f"scratch table left behind: {leftovers}"


def test_the_upgrade_preserves_every_row(db):
    make_pre_context_table(
        db, [(str(i), json.dumps({"n": i}), float(i)) for i in range(25)]
    )
    service = CanvasService(db)
    for i in range(25):
        assert service.load_session(str(i))["canvas"] == {"n": i}


# ----------------------------------------------------------------- contexts

def test_two_contexts_for_one_user_do_not_overwrite_each_other(service):
    """The whole reason the primary key had to change."""
    context = pipeline_source_context("abc-123")
    service.save_session("42", {"nodes": ["main"]})
    service.save_session("42", {"nodes": ["schema"]}, context)

    assert service.load_session("42")["canvas"] == {"nodes": ["main"]}
    assert service.load_session("42", context)["canvas"] == {"nodes": ["schema"]}


def test_two_users_in_one_context_do_not_overwrite_each_other(service):
    context = pipeline_source_context("abc-123")
    service.save_session("1", {"nodes": ["ada"]}, context)
    service.save_session("2", {"nodes": ["bob"]}, context)

    assert service.load_session("1", context)["canvas"] == {"nodes": ["ada"]}
    assert service.load_session("2", context)["canvas"] == {"nodes": ["bob"]}


def test_saving_twice_in_one_context_updates_rather_than_duplicates(service, db):
    service.save_session("42", {"v": 1})
    service.save_session("42", {"v": 2})

    assert service.load_session("42")["canvas"] == {"v": 2}
    conn = sqlite3.connect(db)
    try:
        assert conn.execute("SELECT COUNT(*) FROM canvas_session").fetchone()[0] == 1
    finally:
        conn.close()


def test_loading_a_context_with_no_session_is_none_not_an_error(service):
    assert service.load_session("42", pipeline_source_context("nope")) is None


def test_clear_session_removes_only_the_named_context(service):
    context = pipeline_source_context("abc-123")
    service.save_session("42", {"nodes": ["main"]})
    service.save_session("42", {"nodes": ["schema"]}, context)

    assert service.clear_session("42", context) is True
    assert service.load_session("42", context) is None
    assert service.load_session("42") is not None, "the main canvas was collateral damage"


def test_context_ids_are_namespaced_so_scopes_cannot_be_confused():
    assert pipeline_source_context("abc") == "pipeline_source:abc"
    assert pipeline_source_context("abc") != "abc"


# ------------------------------------------------------------- clear_context

def test_clear_context_removes_every_users_session_for_a_deleted_owner(service):
    """Deleting a Pipeline source must not orphan its schema canvases forever."""
    context = pipeline_source_context("abc-123")
    service.save_session("1", {"nodes": ["ada"]}, context)
    service.save_session("2", {"nodes": ["bob"]}, context)
    service.save_session("1", {"nodes": ["main"]})

    assert service.clear_context(context) == 2
    assert service.load_session("1", context) is None
    assert service.load_session("2", context) is None
    assert service.load_session("1") is not None


def test_clear_context_refuses_to_wipe_every_main_canvas(service):
    """An empty context_id reaching a cleanup path must not delete everyone's work."""
    service.save_session("1", {"nodes": ["main"]})
    for blank in ("", "   ", None):
        with pytest.raises(ValueError, match="refusing"):
            service.clear_context(blank)
    assert service.load_session("1") is not None


def test_clear_context_for_an_unused_context_is_zero_not_an_error(service):
    assert service.clear_context(pipeline_source_context("never-used")) == 0


def test_list_contexts_reports_where_a_user_has_canvases(service):
    service.save_session("42", {"v": 1}, pipeline_source_context("a"))
    service.save_session("42", {"v": 2})
    contexts = {c["context_id"] for c in service.list_contexts("42")}
    assert contexts == {DEFAULT_CONTEXT_ID, pipeline_source_context("a")}
    assert service.list_contexts("other") == []


# --------------------------------------------------------------- user key

def test_current_user_key_prefers_the_row_id():
    from flask import Flask, g

    from scidk.web.user_context import current_user_key

    app = Flask(__name__)
    with app.test_request_context():
        g.scidk_user_id = 7
        g.scidk_user = "ada"
        assert current_user_key() == "7"


def test_a_row_id_of_zero_is_a_user_not_an_anonymous_fallback():
    """The bug in the old `or` chain: 0 is falsy but it is somebody."""
    from flask import Flask, g

    from scidk.web.user_context import current_user_key

    app = Flask(__name__)
    with app.test_request_context():
        g.scidk_user_id = 0
        g.scidk_user = "ada"
        assert current_user_key() == "0"


def test_the_username_is_used_when_there_is_no_row_id():
    from flask import Flask, g

    from scidk.web.user_context import current_user_key

    app = Flask(__name__)
    with app.test_request_context():
        g.scidk_user = "ada"
        assert current_user_key() == "ada"


def test_anonymous_only_when_auth_is_genuinely_off():
    from flask import Flask

    from scidk.web.user_context import current_user_key, is_anonymous

    app = Flask(__name__)
    with app.test_request_context():
        assert current_user_key() == "anonymous"
        assert is_anonymous() is True


def test_the_key_is_always_a_non_empty_string():
    from flask import Flask, g

    from scidk.web.user_context import current_user_key

    app = Flask(__name__)
    for user_id, username in [(None, "  "), ("  ", None), (None, None), ("", "")]:
        with app.test_request_context():
            g.scidk_user_id = user_id
            g.scidk_user = username
            key = current_user_key()
            assert isinstance(key, str) and key.strip()


def test_the_key_is_answerable_outside_a_request_context():
    """A background job asking who the user is has its answer: nobody."""
    from scidk.web.user_context import current_user_key

    assert current_user_key() == "anonymous"
