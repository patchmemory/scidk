"""Session fixtures for the LwM demo fixture (registered in tests/conftest.py).

    demo_tree       materialized stub folder tree (empty folders and dates restored)
    demo_files_db   (db_path, scan_id): files.db written by tools/scidk_scanner_opt.py
                    over demo_tree
"""
import pytest

from tests.fixtures.demo import demo_fixture


@pytest.fixture(scope="session")
def demo_tree(tmp_path_factory):
    return demo_fixture.materialize(tmp_path_factory.mktemp("demo") / "LungTumorDemo")


@pytest.fixture(scope="session")
def demo_files_db(demo_tree, tmp_path_factory):
    db = tmp_path_factory.mktemp("demo_db") / "files.db"
    return db, demo_fixture.build_files_db(db, demo_tree)
