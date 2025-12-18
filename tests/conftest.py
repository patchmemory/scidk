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
