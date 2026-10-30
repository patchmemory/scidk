"""Offline tests for demo_data/nextseek/fill_sample_stubs.py (no network, no database)."""
import importlib.util
from collections import Counter
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / 'demo_data' / 'nextseek' / 'fill_sample_stubs.py'
spec = importlib.util.spec_from_file_location('fill_sample_stubs', SCRIPT)
fill = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fill)


class FakeClient:
    def __init__(self, table):
        self.table = table  # (label, key) -> list of remote property dicts
        self.statements = []

    def query(self, statement, params=None):
        self.statements.append(statement)
        import re
        label, key = re.search(r'\(n:`(\w+)`\) WHERE n\.`(\w+)` IN', statement).groups()
        wanted = set(params['values'])
        return [{'p': p} for p in self.table.get((label, key), []) if p.get(key) in wanted]


def test_plan_node_never_overwrites_and_reports_conflicts():
    conflicts, skipped = Counter(), Counter()
    local = {'uuid': 'S1', '_imported_stub': True, 'name': 'keep me'}
    remote = {'uuid': 'S1', 'name': 'other', 'kind': 'DNA', 'meta': {'a': 1},
              'source': 'x', 'synced_at': 'y', '_imported_stub': False}
    props = fill.plan_node(local, remote, conflicts, skipped)
    assert props == {'kind': 'DNA'}
    assert conflicts == {'name': 1}
    assert set(skipped) == {'meta (not a storable type)', 'source (reserved)',
                            'synced_at (reserved)', '_imported_stub (reserved)'}


def test_plan_node_equal_value_is_not_a_conflict():
    conflicts = Counter()
    fill.plan_node({'uuid': 'S1', 'name': 'same'}, {'uuid': 'S1', 'name': 'same'}, conflicts, Counter())
    assert not conflicts


def test_build_plan_counts_matched_unmatched_ambiguous():
    client = FakeClient({('Sample', 'uuid'): [
        {'uuid': 'A', 'kind': 'x'}, {'uuid': 'B', 'kind': 'y'}, {'uuid': 'B', 'kind': 'z'}]})
    nodes = [{'uuid': u, '_imported_stub': True} for u in ('A', 'B', 'C')]
    plan = fill.build_plan(client, nodes, 'Sample', 'uuid', 'uuid')
    assert (plan['matched'], plan['ambiguous'], plan['unmatched']) == (1, 1, 1)
    assert plan['updates'] == [{'key': 'A', 'props': {'kind': 'x'}}]
    assert plan['key_counts']['kind'] == 1


def test_key_probe_finds_differently_named_key():
    client = FakeClient({('Sample', 'sample_id'): [{'sample_id': 'A', 'uuid': 'zzz'}],
                         ('Sample', 'other'): []})
    real_query = client.query

    def query(statement, params=None):
        if 'LIMIT 1000' in statement and 'IN $values' not in statement:
            return [{'p': {'sample_id': 'A', 'uuid': 'zzz', 'other': 'q'}}]
        return real_query(statement, params)

    client.query = query
    key, tried = fill.find_remote_key(client, 'Sample', 'uuid', ['A'])
    assert key == 'sample_id'
    assert ('uuid', 0) in tried


def test_apply_statement_is_match_only_and_batched():
    seen = []

    class Session:
        def run(self, statement, **kw):
            seen.append((statement, kw))

            class R:
                def single(self_inner):
                    return {'filled': len(kw['rows'])}
            return R()

    plan = {'label': 'Sample', 'match_key': 'uuid',
            'updates': [{'key': str(i), 'props': {'k': i}} for i in range(2500)]}
    assert fill.apply_plan(Session(), plan, '2026-01-01T00:00:00+00:00') == 2500
    assert [len(kw['rows']) for _, kw in seen] == [1000, 1000, 500]
    statement = seen[0][0].upper()
    for forbidden in ('CREATE', 'MERGE', 'DELETE', 'DETACH', ' -[', ']-'):
        assert forbidden not in statement
    assert 'REMOVE N.`_IMPORTED_STUB`' in statement
    assert 'WHERE N.`_IMPORTED_STUB` IS NOT NULL' in statement


def test_unsafe_identifier_rejected():
    with pytest.raises(ValueError):
        fill.ident('x`) DETACH DELETE (n')


def test_missing_credentials_exit_cleanly(monkeypatch, tmp_path, capsys):
    for name in ('NEXTSEEK_HTTP_URL', 'NEXTSEEK_USER', 'NEXTSEEK_PASSWORD'):
        monkeypatch.delenv(name, raising=False)
    assert fill.main(['--env-file', str(tmp_path / 'none.env')]) == 2
    assert 'NEXTSEEK_HTTP_URL' in capsys.readouterr().err
