"""Unit tests for the read-only Neo4j HTTP Query API client. HTTP is fully mocked."""
import pytest
import requests

from scidk.services.neo4j_http_client import (
    Neo4jHttpClient, Neo4jHttpError, ReadOnlyViolation, check_read_only, chunked,
)

SECRET = 'not-a-real-password'


class FakeResponse:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise ValueError('no json')
        return self._payload


class FakeSession:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def post(self, url, json=None, auth=None, timeout=None, headers=None):
        self.calls.append(dict(url=url, json=json, auth=auth, timeout=timeout))
        outcome = self.outcomes.pop(0) if len(self.outcomes) > 1 else self.outcomes[0]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def ok(fields, values):
    return FakeResponse(200, {'data': {'fields': fields, 'values': values}})


def make(session, **kw):
    return Neo4jHttpClient('https://example.invalid/', 'u', SECRET, session=session,
                           sleep=lambda s: None, **kw)


def test_parses_fields_and_values_into_dicts():
    session = FakeSession(ok(['n', 'c'], [['Sample', 3], ['SampleType', 1]]))
    rows = make(session).query('MATCH (n) RETURN n, count(*) AS c LIMIT 10')
    assert rows == [{'n': 'Sample', 'c': 3}, {'n': 'SampleType', 'c': 1}]


def test_request_shape_read_mode_timeout_and_endpoint():
    session = FakeSession(ok(['x'], [[1]]))
    make(session).query('RETURN $a AS x', {'a': 1})
    call = session.calls[0]
    assert call['url'] == 'https://example.invalid/db/neo4j/query/v2'
    assert call['json'] == {'statement': 'RETURN $a AS x', 'parameters': {'a': 1}, 'accessMode': 'Read'}
    assert call['timeout'] == 30
    assert call['auth'] == ('u', SECRET)


def test_full_query_url_is_accepted():
    session = FakeSession(ok(['x'], []))
    Neo4jHttpClient('https://h/db/neo4j/query/v2', 'u', 'p', session=session).query('RETURN 1 AS x')
    assert session.calls[0]['url'] == 'https://h/db/neo4j/query/v2'


@pytest.mark.parametrize('statement', [
    'CREATE (n:X)', 'merge (n:X)', 'MATCH (n) SET n.a = 1', 'MATCH (n) DELETE n',
    'MATCH (n) DETACH DELETE n', 'MATCH (n) REMOVE n.a', 'DROP INDEX foo',
    'LOAD CSV FROM "file:///x" AS r RETURN r',
    'CALL { MATCH (n) RETURN n } IN TRANSACTIONS',
    'MATCH (n) RETURN n\nSET n.x = 1',
])
def test_write_statements_refused_without_sending(statement):
    session = FakeSession(ok(['x'], []))
    with pytest.raises(ReadOnlyViolation):
        make(session).query(statement)
    assert session.calls == []


def test_write_keywords_inside_strings_and_comments_are_not_refused():
    check_read_only("MATCH (n) WHERE n.name = 'CREATE ME' RETURN n LIMIT 1")
    check_read_only('MATCH (n) RETURN n LIMIT 1 // delete later')
    check_read_only('MATCH (n:`Set`) RETURN n LIMIT 1')


def test_batching_splits_into_1000_row_chunks():
    assert [len(b) for b in chunked(list(range(2500)))] == [1000, 1000, 500]
    session = FakeSession(ok(['uuid'], [['a']]))
    rows = make(session).query_batched(
        'MATCH (s:Sample) WHERE s.uuid IN $uuids RETURN s.uuid AS uuid', 'uuids',
        [f'u{i}' for i in range(2001)])
    assert len(session.calls) == 3
    assert [len(c['json']['parameters']['uuids']) for c in session.calls] == [1000, 1000, 1]
    assert len(rows) == 3


def test_retries_network_errors_then_succeeds():
    session = FakeSession(requests.ConnectionError('boom'), requests.Timeout('slow'), ok(['x'], [[1]]))
    assert make(session).query('RETURN 1 AS x') == [{'x': 1}]
    assert len(session.calls) == 3


def test_gives_up_after_three_attempts_without_leaking_credentials():
    session = FakeSession(requests.ConnectionError(f'https://u:{SECRET}@h refused'))
    with pytest.raises(Neo4jHttpError) as err:
        make(session).query('RETURN 1 AS x')
    assert len(session.calls) == 3
    assert SECRET not in str(err.value)


def test_retries_on_5xx_but_not_on_4xx():
    session = FakeSession(FakeResponse(503), ok(['x'], [[1]]))
    assert make(session).query('RETURN 1 AS x') == [{'x': 1}]
    assert len(session.calls) == 2
    session = FakeSession(FakeResponse(401, {'errors': []}))
    with pytest.raises(Neo4jHttpError, match='401'):
        make(session).query('RETURN 1 AS x')
    assert len(session.calls) == 1


def test_api_errors_are_raised():
    payload = {'errors': [{'code': 'Neo.ClientError.Statement.SyntaxError', 'message': 'bad'}]}
    with pytest.raises(Neo4jHttpError, match='SyntaxError'):
        make(FakeSession(FakeResponse(400, payload))).query('RETURN')


def test_unexpected_shape_raises():
    with pytest.raises(Neo4jHttpError):
        make(FakeSession(FakeResponse(200, {'nope': 1}))).query('RETURN 1')


def test_from_env_requires_all_variables_and_repr_has_no_secret():
    with pytest.raises(Neo4jHttpError, match='NEXTSEEK_PASSWORD'):
        Neo4jHttpClient.from_env({'NEXTSEEK_HTTP_URL': 'https://h', 'NEXTSEEK_USER': 'u'})
    client = Neo4jHttpClient.from_env({'NEXTSEEK_HTTP_URL': 'https://h', 'NEXTSEEK_USER': 'u',
                                       'NEXTSEEK_PASSWORD': SECRET})
    assert SECRET not in repr(client)
