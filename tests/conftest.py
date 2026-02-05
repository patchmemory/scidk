import os
import tempfile
from pathlib import Path
import pytest


@pytest.fixture(scope="session", autouse=True)
def _pin_repo_local_test_env():
    """Force all unit/integration test temp & DB paths into the repo.
    This avoids writing to /tmp or the user HOME during tests.
    E2E has its own conftest; this one applies to non-E2E test tiers.
    """
    # Detect repo root from this file
    repo_root = Path(__file__).resolve().parents[1]
    tmp_root = repo_root / "dev/test-runs/tmp"
    pytest_tmp = repo_root / "dev/test-runs/pytest-tmp"
    db_dir = repo_root / "dev/test-runs/db"
    for d in (tmp_root, pytest_tmp, db_dir):
        d.mkdir(parents=True, exist_ok=True)

    # Clean up old pytest session directories (keep only 3 most recent)
    _cleanup_old_pytest_sessions(tmp_root / "pytest-of-patch", keep_last=3)

    # Clean up test scans from SQLite database
    _cleanup_test_scans_from_db(db_dir / 'unit_integration.db')

    # Clean up test labels from SQLite database
    _cleanup_test_labels_from_db(db_dir / 'unit_integration.db')

    # OS temp for tempfile and libraries
    os.environ.setdefault("TMPDIR", str(tmp_root))
    os.environ.setdefault("TMP", str(tmp_root))
    os.environ.setdefault("TEMP", str(tmp_root))
    # Also force Python's tempfile module to use this dir in-process
    tempfile.tempdir = str(tmp_root)

    # SQLite DB used by selections/annotations and other sqlite-backed helpers
    os.environ.setdefault("SCIDK_DB_PATH", f"sqlite:///{(db_dir / 'unit_integration.db').as_posix()}")
    # Prefer sqlite-backed state for tests by default
    os.environ.setdefault("SCIDK_STATE_BACKEND", "sqlite")

    # Providers and auth safe defaults
    os.environ.setdefault("SCIDK_PROVIDERS", "local_fs,mounted_fs")
    os.environ.setdefault("NEO4J_AUTH", "none")

    # Nothing to yield; env remains for the session
    return


def _cleanup_old_pytest_sessions(pytest_user_dir: Path, keep_last: int = 3):
    """Remove old pytest session directories, keeping only the N most recent.

    Args:
        pytest_user_dir: Path to pytest-of-{user} directory
        keep_last: Number of recent sessions to keep (default: 3)
    """
    if not pytest_user_dir.exists():
        return

    try:
        # Find all pytest-{num} directories
        session_dirs = [
            d for d in pytest_user_dir.iterdir()
            if d.is_dir() and d.name.startswith('pytest-') and d.name[7:].isdigit()
        ]

        if len(session_dirs) <= keep_last:
            return

        # Sort by modification time (newest first)
        session_dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)

        # Remove old sessions
        for old_dir in session_dirs[keep_last:]:
            try:
                import shutil
                shutil.rmtree(old_dir)
            except Exception:
                pass  # Ignore cleanup errors
    except Exception:
        pass  # Don't fail tests if cleanup fails


def _cleanup_test_scans_from_db(db_path: Path):
    """Remove test scans from the SQLite database before test runs.

    This prevents accumulation of test scans that show up in the UI
    when running scidk-serve after tests have run.

    Args:
        db_path: Path to the SQLite database file
    """
    if not db_path.exists():
        return

    try:
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        try:
            cur = conn.cursor()

            # Check if scans table exists
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='scans'")
            if not cur.fetchone():
                return

            # Delete test scans (paths with /tmp/, /nonexistent/, or scidk-e2e)
            cur.execute("""
                DELETE FROM scans
                WHERE root LIKE '%/tmp/%'
                   OR root LIKE '%nonexistent%'
                   OR root LIKE '%scidk-e2e%'
            """)

            # Also clean up orphaned scan_items and scan_progress
            # (scans that were deleted but left dangling records)
            cur.execute("""
                DELETE FROM scan_items
                WHERE scan_id NOT IN (SELECT id FROM scans)
            """)
            cur.execute("""
                DELETE FROM scan_progress
                WHERE scan_id NOT IN (SELECT id FROM scans)
            """)

            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass  # Silently fail; don't break test runs


def _cleanup_test_labels_from_db(db_path: Path):
    """Remove test labels from the SQLite database before test runs.

    This prevents accumulation of test labels that show up in the UI
    when running scidk-serve after tests have run.

    Args:
        db_path: Path to the SQLite database file
    """
    if not db_path.exists():
        return

    try:
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        try:
            cur = conn.cursor()

            # Check if label_definitions table exists
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='label_definitions'")
            if not cur.fetchone():
                return

            # List of test label patterns to delete
            test_patterns = [
                'E2E%',  # E2E test labels
                'Test%',  # TestLabel, TestNode, etc
                'Person%',  # From arrows test
                'Company%',  # From arrows test
                'Project%',  # Multiple test uses
                'Export%',  # ExportProject, ExportTask
                'Layout%',  # LayoutTestLabel
                'Roundtrip%',  # RoundtripAuthor, RoundtripBook
                'Label%',  # Label1, Label2, Label3
                'AllTypes%',  # AllTypes
                'File%',  # File from relationship tests
                'Directory%',  # Directory from relationship tests
                'User%',  # User from relationship tests
                'Update%',  # UpdateTest
                'Delete%',  # DeleteTest
                'Bad%',  # BadLabel
                'Node%',  # TestNode, OtherNode, NodeA, NodeB
            ]

            # Delete test labels
            for pattern in test_patterns:
                cur.execute("DELETE FROM label_definitions WHERE name LIKE ?", (pattern,))

            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass  # Silently fail; don't break test runs


# --- Flask app + test client fixtures expected by unit/integration tests ---
@pytest.fixture(scope="function")
def app():
    """Provide a Flask app for unit/integration tests."""
    from scidk.app import create_app
    application = create_app()
    # Ensure TESTING mode and propagate state backend toggle into app.config
    application.config.update({
        "TESTING": True,
        "state.backend": (os.environ.get("SCIDK_STATE_BACKEND") or "sqlite").lower(),
    })
    ctx = application.app_context()
    ctx.push()
    try:
        yield application
    finally:
        ctx.pop()


@pytest.fixture()
def client(app):
    """Flask test client used by many unit tests."""
    return app.test_client()


# --- File fixtures used by interpreter/filesystem tests ---
@pytest.fixture()
def sample_py_file(tmp_path: Path) -> Path:
    p = tmp_path / "sample.py"
    p.write_text(
        (
            "\"\"\"Example module docstring\"\"\"\n"
            "# sample python\n"
            "import os\n"
            "import sys\n"
            "from collections import defaultdict\n\n"
            "x = 1\n"
            "def foo():\n    return x\n\n"
            "class Bar:\n    def __init__(self):\n        self.v = 42\n\n"
            "print(x)\n"
        ),
        encoding="utf-8",
    )
    return p


@pytest.fixture()
def bad_py_file(tmp_path: Path) -> Path:
    p = tmp_path / "bad.py"
    # intentional syntax error
    p.write_text("def broken(:\n    pass\n", encoding="utf-8")
    return p
