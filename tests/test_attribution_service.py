"""Attribution — anchor listing, property discovery, property-based filtering.

Every query in :class:`FolderAttributionService` interpolates a label or a
property key straight into Cypher, so what these tests mostly check is the
boundary: which identifiers get whitelisted before they reach the string, and
which values travel as bound parameters instead.

Matching and ordering themselves happen in the database. A fake driver cannot
execute Cypher, so where a test's subject is a `CONTAINS` or an `ORDER BY` it
asserts that the clause is in the query and that the method passes the rows
through untouched — the semantics need a live graph, and are not tested here.
"""
import pytest

from scidk.services.folder_attribution import (
    DEFAULT_ANCHOR_LABEL,
    FolderAttributionService,
)


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def __iter__(self):
        return iter(self._rows)


class _FakeSession:
    def __init__(self, driver):
        self._driver = driver

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def run(self, query, **params):
        self._driver.queries.append((query, params))
        return _FakeResult(self._driver.rows)


class _FakeDriver:
    """Returns canned rows for any query, and records every query it was given."""

    def __init__(self, rows=None):
        self.rows = rows or []
        self.queries = []

    def session(self, database=None):
        self.databases_used = getattr(self, 'databases_used', [])
        self.databases_used.append(database)
        return _FakeSession(self)


def _svc(rows=None, database=None):
    driver = _FakeDriver(rows)
    return FolderAttributionService(driver, database=database), driver


# ---------------------------------------------------------------------------
# list_anchor_properties
# ---------------------------------------------------------------------------

def test_list_anchor_properties_returns_keys_in_the_order_the_query_ranked_them():
    # Ordering is the database's job — the method must not re-sort the rows,
    # or the commonest-first contract the picker relies on is lost.
    svc, driver = _svc([
        {'key': 'name',  'cnt': 42},
        {'key': 'email', 'cnt': 30},
        {'key': 'lab',   'cnt': 4},
    ])
    assert svc.list_anchor_properties('Investigator') == ['name', 'email', 'lab']

    query, params = driver.queries[0]
    assert 'UNWIND keys(n) AS key' in query
    assert 'count(*) AS cnt' in query
    assert 'ORDER BY cnt DESC' in query
    assert params == {}


def test_list_anchor_properties_is_one_round_trip():
    svc, driver = _svc([{'key': 'name', 'cnt': 1}])
    svc.list_anchor_properties('Investigator')
    assert len(driver.queries) == 1


def test_list_anchor_properties_drops_empty_keys():
    svc, _ = _svc([
        {'key': 'email', 'cnt': 9},
        {'key': None,    'cnt': 2},
        {'key': '',      'cnt': 1},
    ])
    assert svc.list_anchor_properties('Investigator') == ['email']


def test_list_anchor_properties_on_a_label_with_no_nodes_is_empty():
    svc, _ = _svc([])
    assert svc.list_anchor_properties('Nothing') == []


def test_list_anchor_properties_matches_the_requested_label():
    svc, driver = _svc([])
    svc.list_anchor_properties('Lab')
    assert 'MATCH (n:Lab)' in driver.queries[0][0]


def test_list_anchor_properties_validates_the_label():
    svc, driver = _svc([])
    with pytest.raises(ValueError):
        svc.list_anchor_properties('Investigator) DETACH DELETE (n')
    assert driver.queries == []   # rejected before any query is issued


def test_list_anchor_properties_passes_the_database_through():
    svc, driver = _svc([], database='neo4j')
    svc.list_anchor_properties('Investigator')
    assert driver.databases_used == ['neo4j']


# ---------------------------------------------------------------------------
# list_anchor_property_values
# ---------------------------------------------------------------------------

def test_list_anchor_property_values_returns_the_values_the_query_sorted():
    # DISTINCT and ORDER BY are the database's job — the method must not re-sort
    # or re-dedupe, so a live graph's collation is what the picker shows.
    svc, driver = _svc([
        {'val': 'Chen Lab'}, {'val': 'Ito Lab'}, {'val': 'Zhang Lab'},
    ])
    assert svc.list_anchor_property_values('Investigator', 'lab') == [
        'Chen Lab', 'Ito Lab', 'Zhang Lab',
    ]

    query, params = driver.queries[0]
    assert 'MATCH (n:Investigator)' in query
    assert 'WHERE n.lab IS NOT NULL' in query
    assert 'RETURN DISTINCT toString(n.lab) AS val' in query
    assert 'ORDER BY val' in query
    assert params == {}


def test_list_anchor_property_values_is_one_round_trip():
    svc, driver = _svc([{'val': 'a'}])
    svc.list_anchor_property_values('Investigator', 'lab')
    assert len(driver.queries) == 1


def test_list_anchor_property_values_drops_empty_values():
    # ``IS NOT NULL`` is the database's filter; this is the belt to its braces,
    # for a property present but empty — a blank option is not selectable.
    svc, _ = _svc([{'val': 'Chen Lab'}, {'val': None}, {'val': ''}])
    assert svc.list_anchor_property_values('Investigator', 'lab') == ['Chen Lab']


def test_list_anchor_property_values_on_a_property_no_node_carries_is_empty():
    svc, _ = _svc([])
    assert svc.list_anchor_property_values('Investigator', 'orcid') == []


def test_list_anchor_property_values_matches_the_requested_label_and_property():
    svc, driver = _svc([])
    svc.list_anchor_property_values('Lab', 'building')
    query = driver.queries[0][0]
    assert 'MATCH (n:Lab)' in query
    assert 'n.building' in query


@pytest.mark.parametrize('bad_label', [
    'Investigator) DETACH DELETE (n',
    'Investigator RETURN 1',
    '',
])
def test_list_anchor_property_values_validates_the_label(bad_label):
    svc, driver = _svc([])
    with pytest.raises(ValueError):
        svc.list_anchor_property_values(bad_label, 'lab')
    assert driver.queries == []   # rejected before any query is issued


@pytest.mark.parametrize('bad_property', [
    'lab} RETURN n.password AS val //',
    'lab IS NOT NULL OR true',
    'lab-name',
    '',
])
def test_list_anchor_property_values_validates_the_property_key(bad_property):
    # The key is interpolated, not bound — a parameter cannot carry a property
    # name in Cypher — so it has to clear the whitelist first.
    svc, driver = _svc([])
    with pytest.raises(ValueError):
        svc.list_anchor_property_values('Investigator', bad_property)
    assert driver.queries == []


def test_list_anchor_property_values_passes_the_database_through():
    svc, driver = _svc([], database='neo4j')
    svc.list_anchor_property_values('Investigator', 'lab')
    assert driver.databases_used == ['neo4j']


# ---------------------------------------------------------------------------
# list_anchors — unfiltered
# ---------------------------------------------------------------------------

def test_list_anchors_without_a_filter_is_unchanged():
    svc, driver = _svc([{'name': 'Zhang', 'labels': ['Investigator', 'Person']}])
    assert svc.list_anchors() == [
        {'name': 'Zhang', 'labels': ['Investigator', 'Person']}
    ]

    query, params = driver.queries[0]
    assert f'MATCH (p:{DEFAULT_ANCHOR_LABEL})' in query
    assert 'WHERE p.name IS NOT NULL' in query
    assert 'ORDER BY p.name' in query
    assert 'CONTAINS' not in query
    assert params == {}


def test_list_anchors_ignores_a_value_with_no_property_to_match_it_against():
    svc, driver = _svc([])
    svc.list_anchors('Investigator', filter_value='zhang')
    assert 'CONTAINS' not in driver.queries[0][0]


def test_list_anchors_validates_the_anchor_label():
    svc, driver = _svc([])
    with pytest.raises(ValueError):
        svc.list_anchors('Investigator) DETACH DELETE (p')
    assert driver.queries == []


# ---------------------------------------------------------------------------
# list_anchors — filtered by property
# ---------------------------------------------------------------------------

def test_list_anchors_filters_on_the_named_property_case_insensitively():
    svc, driver = _svc([
        {'name': 'Zhang', 'labels': ['Investigator'],
         'matched_value': 'jz@mit.edu'},
    ])
    out = svc.list_anchors('Investigator',
                           filter_property='email', filter_value='MIT')

    assert out == [{'name': 'Zhang', 'labels': ['Investigator'],
                    'matched_value': 'jz@mit.edu'}]

    query, params = driver.queries[0]
    # The property key has to be interpolated (Cypher cannot bind a key), the
    # value must not be. Both halves lowercased, so the match ignores case.
    assert 'toLower(toString(p.email)) CONTAINS toLower($val)' in query
    assert params == {'val': 'MIT'}
    assert 'MIT' not in query


def test_list_anchors_filtered_requires_the_property_to_be_present():
    svc, driver = _svc([])
    svc.list_anchors('Investigator', filter_property='email', filter_value='x')
    assert 'p.email IS NOT NULL' in driver.queries[0][0]


def test_list_anchors_filtered_still_requires_a_name():
    # An anchor is searched and written back by name, so a nameless match would
    # be an unusable row in the picker.
    svc, driver = _svc([])
    svc.list_anchors('Investigator', filter_property='email', filter_value='x')
    assert 'p.name IS NOT NULL' in driver.queries[0][0]


def test_list_anchors_filtered_returns_the_value_that_matched():
    svc, driver = _svc([])
    svc.list_anchors('Investigator', filter_property='lab', filter_value='')
    assert 'p.lab AS matched_value' in driver.queries[0][0]


def test_list_anchors_filtered_stays_name_ordered():
    svc, driver = _svc([])
    svc.list_anchors('Investigator', filter_property='lab', filter_value='a')
    assert 'ORDER BY p.name' in driver.queries[0][0]


def test_list_anchors_with_an_empty_value_binds_an_empty_substring():
    # Every anchor that *has* the property — the useful reading of "filter by
    # email" before an email has been typed.
    svc, driver = _svc([])
    svc.list_anchors('Investigator', filter_property='email', filter_value=None)
    assert driver.queries[0][1] == {'val': ''}


@pytest.mark.parametrize('bad_property', [
    'email} RETURN p {',
    'email) DETACH DELETE (p',
    'email; DROP',
    'has space',
    '1email',
])
def test_list_anchors_validates_the_filter_property(bad_property):
    svc, driver = _svc([])
    with pytest.raises(ValueError):
        svc.list_anchors('Investigator', filter_property=bad_property,
                         filter_value='x')
    assert driver.queries == []


def test_list_anchors_filtered_is_one_round_trip():
    svc, driver = _svc([])
    svc.list_anchors('Investigator', filter_property='email', filter_value='x')
    assert len(driver.queries) == 1


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

class _StubService:
    """Stands in for the service so the routes can be tested without Neo4j."""

    def __init__(self, properties=None, anchors=None, values=None):
        self._properties = properties or []
        self._anchors = anchors or []
        self._values = values or []
        self.calls = []

    def list_anchor_properties(self, anchor_label):
        self.calls.append(('properties', anchor_label))
        from scidk.services.filter_builder import _validate_identifier
        _validate_identifier(anchor_label)
        return self._properties

    def list_anchor_property_values(self, anchor_label, property_key):
        self.calls.append(('values', anchor_label, property_key))
        from scidk.services.filter_builder import _validate_identifier
        _validate_identifier(anchor_label)
        _validate_identifier(property_key)
        return self._values

    def list_anchors(self, anchor_label=DEFAULT_ANCHOR_LABEL,
                     filter_property=None, filter_value=None):
        self.calls.append(('anchors', anchor_label, filter_property, filter_value))
        return self._anchors


@pytest.fixture()
def stub_service(monkeypatch):
    """Replace the route's service factory; return a setter for the stub."""
    from contextlib import contextmanager

    from scidk.web.routes import api_files

    holder = {}

    def _install(svc):
        @contextmanager
        def _fake_factory():
            yield svc

        monkeypatch.setattr(api_files, '_attribution_service', _fake_factory)
        holder['svc'] = svc
        return svc

    return _install


def test_anchor_properties_route_returns_the_properties(client, stub_service):
    svc = stub_service(_StubService(properties=['name', 'email']))
    resp = client.get('/api/files/attribution/anchor-properties'
                      '?anchor_label=Investigator')

    assert resp.status_code == 200
    assert resp.get_json() == {
        'anchor_label': 'Investigator',
        'properties': ['name', 'email'],
    }
    assert svc.calls == [('properties', 'Investigator')]


def test_anchor_properties_route_defaults_the_label(client, stub_service):
    svc = stub_service(_StubService(properties=[]))
    resp = client.get('/api/files/attribution/anchor-properties')

    assert resp.status_code == 200
    assert resp.get_json()['anchor_label'] == DEFAULT_ANCHOR_LABEL
    assert svc.calls == [('properties', DEFAULT_ANCHOR_LABEL)]


def test_anchor_properties_route_rejects_an_unsafe_label(client, stub_service):
    stub_service(_StubService())
    resp = client.get('/api/files/attribution/anchor-properties'
                      '?anchor_label=Investigator) DETACH DELETE (n')

    assert resp.status_code == 400
    assert 'error' in resp.get_json()


def test_anchor_properties_route_reports_neo4j_unconfigured(client, monkeypatch):
    from contextlib import contextmanager

    from scidk.web.routes import api_files

    @contextmanager
    def _no_service():
        yield None

    monkeypatch.setattr(api_files, '_attribution_service', _no_service)
    resp = client.get('/api/files/attribution/anchor-properties')

    assert resp.status_code == 501
    assert 'error' in resp.get_json()


def test_anchor_property_values_route_returns_the_values(client, stub_service):
    svc = stub_service(_StubService(values=['Chen Lab', 'Zhang Lab']))
    resp = client.get('/api/files/attribution/anchor-property-values'
                      '?anchor_label=Investigator&property_key=lab')

    assert resp.status_code == 200
    assert resp.get_json() == {
        'anchor_label': 'Investigator',
        'property_key': 'lab',
        'values': ['Chen Lab', 'Zhang Lab'],
    }
    assert svc.calls == [('values', 'Investigator', 'lab')]


@pytest.mark.parametrize('qs', [
    '',                                   # neither
    '?anchor_label=Investigator',         # no property_key
    '?property_key=lab',                  # no anchor_label
    '?anchor_label=%20&property_key=lab',  # blank is absent, not a label
])
def test_anchor_property_values_route_requires_both_params(client, stub_service, qs):
    # No default label here, unlike anchor-properties: a value list is only
    # meaningful for the label its property came from, so guessing one would
    # answer a question nobody asked.
    svc = stub_service(_StubService(values=['x']))
    resp = client.get('/api/files/attribution/anchor-property-values' + qs)

    assert resp.status_code == 400
    assert 'error' in resp.get_json()
    assert svc.calls == []


@pytest.mark.parametrize('qs', [
    '?anchor_label=Investigator) DETACH DELETE (n&property_key=lab',
    '?anchor_label=Investigator&property_key=lab} RETURN n.password AS val //',
])
def test_anchor_property_values_route_rejects_unsafe_identifiers(client, stub_service, qs):
    stub_service(_StubService())
    resp = client.get('/api/files/attribution/anchor-property-values' + qs)

    assert resp.status_code == 400
    assert 'error' in resp.get_json()


def test_anchor_property_values_route_reports_neo4j_unconfigured(client, monkeypatch):
    from contextlib import contextmanager

    from scidk.web.routes import api_files

    @contextmanager
    def _no_service():
        yield None

    monkeypatch.setattr(api_files, '_attribution_service', _no_service)
    resp = client.get('/api/files/attribution/anchor-property-values'
                      '?anchor_label=Investigator&property_key=lab')

    assert resp.status_code == 501
    assert 'error' in resp.get_json()


def test_anchor_property_values_route_reports_a_failed_query(client, stub_service):
    class _Boom(_StubService):
        def list_anchor_property_values(self, anchor_label, property_key):
            raise RuntimeError('bolt closed')

    stub_service(_Boom())
    resp = client.get('/api/files/attribution/anchor-property-values'
                      '?anchor_label=Investigator&property_key=lab')

    assert resp.status_code == 502
    assert 'bolt closed' in resp.get_json()['error']


def test_anchors_route_passes_the_property_filter_through(client, stub_service):
    svc = stub_service(_StubService(anchors=[
        {'name': 'Zhang', 'labels': ['Investigator'],
         'matched_value': 'jz@mit.edu'},
    ]))
    resp = client.get('/api/files/attribution/anchors'
                      '?anchor_label=Investigator'
                      '&filter_property=email&filter_value=mit')

    assert resp.status_code == 200
    assert resp.get_json()['anchors'][0]['matched_value'] == 'jz@mit.edu'
    assert svc.calls == [('anchors', 'Investigator', 'email', 'mit')]


def test_anchors_route_without_filter_params_is_unchanged(client, stub_service):
    # Existing callers pass neither param and must reach the unfiltered path.
    svc = stub_service(_StubService(anchors=[]))
    resp = client.get('/api/files/attribution/anchors?anchor_label=Investigator')

    assert resp.status_code == 200
    assert svc.calls == [('anchors', 'Investigator', None, None)]


def test_anchors_route_treats_blank_filter_params_as_absent(client, stub_service):
    svc = stub_service(_StubService(anchors=[]))
    resp = client.get('/api/files/attribution/anchors'
                      '?filter_property=%20&filter_value=%20')

    assert resp.status_code == 200
    assert svc.calls == [('anchors', DEFAULT_ANCHOR_LABEL, None, None)]


def test_attribution_routes_are_registered(client):
    # Without Neo4j these report "not configured" rather than 404.
    for path in ('/api/files/attribution/anchors',
                 '/api/files/attribution/anchor-properties',
                 '/api/files/attribution/anchor-property-values'
                 '?anchor_label=Investigator&property_key=lab'):
        assert client.get(path).status_code != 404
