import os
import textwrap
import pytest
from pathlib import Path

from scidk.app import create_app


@pytest.fixture()
def app():
    app = create_app()
    app.config.update({
        "TESTING": True,
    })
    yield app


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def sample_py_file(tmp_path: Path) -> Path:
    p = tmp_path / "example.py"
    p.write_text(textwrap.dedent(
        '''
        """Example module docstring"""
        import os
        import sys
        from collections import defaultdict

        def foo():
            pass

        class Bar:
            def baz(self):
                return 42
        '''
    ).strip() + "\n", encoding="utf-8")
    return p


@pytest.fixture()
def bad_py_file(tmp_path: Path) -> Path:
    p = tmp_path / "bad.py"
    # introduce a syntax error
    p.write_text("def oops(:\n    pass\n", encoding="utf-8")
    return p
