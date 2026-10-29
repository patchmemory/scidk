import sqlite3

import pytest

from scidk.curation.contracts import CONTRACT, ConflictError
from scidk.curation.ledger import Ledger, _DDL, migrate
from scidk.curation.ontology import Ontology


def test_explicit_upgrade_preserves_v1_rows(tmp_path):
    path = tmp_path / 'v1.sqlite'
    with sqlite3.connect(path) as conn:
        conn.executescript(_DDL)
        conn.execute('INSERT INTO curation_schema VALUES (?,?)', (1, CONTRACT))
        conn.execute('INSERT INTO evidence VALUES (?,?,?)', ('original', '{}', 'original-time'))
        conn.execute("CREATE TRIGGER immutable_evidence_delete BEFORE DELETE ON evidence "
                     "BEGIN SELECT RAISE(ABORT, 'append-only'); END")
    with pytest.raises(ConflictError):
        Ledger(path, Ontology([], []), lambda *args: True)
    migrate(path)
    migrate(path)
    with sqlite3.connect(path) as conn:
        assert conn.execute('SELECT * FROM evidence').fetchall() == [('original', '{}', 'original-time')]
        assert conn.execute('SELECT version FROM curation_schema ORDER BY version').fetchall() == [(1,), (2,)]
        assert conn.execute('SELECT count(*) FROM receipts').fetchone()[0] == 0
        with pytest.raises(sqlite3.IntegrityError, match='append-only'):
            conn.execute('DELETE FROM evidence')
    Ledger(path, Ontology([], []), lambda *args: True)


def test_unknown_future_schema_refused(tmp_path):
    path = tmp_path / 'future.sqlite'
    with sqlite3.connect(path) as conn:
        conn.executescript(_DDL)
        conn.execute('INSERT INTO curation_schema VALUES (?,?)', (99, CONTRACT))
    with pytest.raises(ConflictError):
        migrate(path)
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT name FROM sqlite_master WHERE name='outbox'").fetchall() == []
