"""Tests for the schema-aware filter builder.

The Cypher generator is pure, so it is tested directly with no Neo4j. Property
type inference is tested against a fake driver that records the queries it was
asked to run — the point is as much that inference stays one bounded round trip
as that it classifies correctly.
"""
import pytest

from scidk.services.filter_builder import (
    PropertyInfo,
    generate_count_cypher,
    generate_cypher,
    infer_property_types,
)


# ---------------------------------------------------------------------------
# Cypher generation
# ---------------------------------------------------------------------------

def test_single_block_single_condition():
    cypher, params = generate_cypher({
        "blocks": [{"label": "Investigator", "match": "ALL",
                    "conditions": [{"property": "name", "operator": "contains",
                                    "value": "Zhang"}]}]
    })
    assert "MATCH (n0:Investigator)" in cypher
    assert "n0.name CONTAINS $v0" in cypher
    assert params["v0"] == "Zhang"
    assert "RETURN DISTINCT n0" in cypher
    # The value is bound, never spliced into the query text.
    assert "Zhang" not in cypher


def test_two_blocks_with_relationship_connector():
    cypher, params = generate_cypher({
        "blocks": [
            {"label": "Investigator", "match": "ALL",
             "conditions": [{"property": "name", "operator": "contains",
                             "value": "Zhang"}]},
            {"via": {"type": "MEMBER_OF", "min_hops": 1, "max_hops": 1},
             "label": "Lab", "match": "ALL",
             "conditions": [{"property": "name", "operator": "equals",
                             "value": "Koch"}]},
        ]
    })
    assert "-[:MEMBER_OF]->" in cypher
    assert "n1.name = $v1" in cypher
    assert params == {"v0": "Zhang", "v1": "Koch"}
    assert "RETURN DISTINCT n0, n1" in cypher


def test_variable_length_hops():
    cypher, _ = generate_cypher({
        "blocks": [
            {"label": "Folder", "conditions": []},
            {"via": {"type": "CONTAINS", "min_hops": 1, "max_hops": 3},
             "label": "File", "conditions": []},
        ]
    })
    assert "-[:CONTAINS*1..3]->" in cypher

    cypher, _ = generate_cypher({
        "blocks": [
            {"label": "Folder", "conditions": []},
            {"via": {"type": "CONTAINS", "min_hops": 2, "max_hops": 2},
             "label": "File", "conditions": []},
        ]
    })
    assert "-[:CONTAINS*2]->" in cypher


def test_between_operator_coerces_numeric_strings():
    cypher, params = generate_cypher({
        "blocks": [{"label": "File", "match": "ALL",
                    "conditions": [{"property": "size", "operator": "between",
                                    "value": ["1000", "5000"]}]}]
    })
    assert "n0.size >= $v0 AND n0.size <= $v1" in cypher
    assert params["v0"] == 1000.0 and params["v1"] == 5000.0


def test_date_comparisons_keep_iso_strings():
    # float('2024-01-01') would raise; ISO strings compare correctly as strings.
    cypher, params = generate_cypher({
        "blocks": [{"label": "Scan", "match": "ALL",
                    "conditions": [
                        {"property": "created", "operator": "after",
                         "value": "2024-01-01"},
                        {"property": "created", "operator": "between",
                         "value": ["2024-01-01", "2024-12-31"]},
                    ]}]
    })
    assert "n0.created > $v0" in cypher
    assert params["v0"] == "2024-01-01"
    assert params["v1"] == "2024-01-01" and params["v2"] == "2024-12-31"


def test_numeric_operators_reject_non_numbers():
    with pytest.raises(ValueError):
        generate_cypher({
            "blocks": [{"label": "File",
                        "conditions": [{"property": "size", "operator": "gt",
                                        "value": "not-a-number"}]}]
        })


def test_match_any_joins_with_or_and_parenthesizes():
    cypher, _ = generate_cypher({
        "blocks": [{"label": "Investigator", "match": "ANY",
                    "conditions": [
                        {"property": "name", "operator": "contains", "value": "a"},
                        {"property": "email", "operator": "is_not_null"},
                    ]}]
    })
    assert "(n0.name CONTAINS $v0 OR n0.email IS NOT NULL)" in cypher


def test_valueless_operators_bind_no_params():
    cypher, params = generate_cypher({
        "blocks": [{"label": "Folder",
                    "conditions": [
                        {"property": "path", "operator": "is_not_null"},
                        {"property": "archived", "operator": "is_true"},
                    ]}]
    })
    assert "n0.path IS NOT NULL" in cypher
    assert "n0.archived = true" in cypher
    assert params == {}


def test_no_conditions_emits_no_where_clause():
    cypher, params = generate_cypher({"blocks": [{"label": "Folder"}]})
    assert "WHERE" not in cypher
    assert params == {}


def test_count_cypher_shares_the_match_and_where():
    filter_def = {
        "blocks": [{"label": "Investigator", "match": "ALL",
                    "conditions": [{"property": "name", "operator": "contains",
                                    "value": "Zhang"}]}]
    }
    full, full_params = generate_cypher(filter_def)
    count, count_params = generate_count_cypher(filter_def)
    assert count.endswith("RETURN count(*) AS total")
    assert count_params == full_params
    assert count.split("RETURN")[0] == full.split("RETURN")[0]


def test_count_cypher_survives_a_rel_type_containing_return():
    # A naive rsplit('RETURN') on the finished query would be fine here, but the
    # generator builds the body once instead of rewriting text — assert it.
    count, _ = generate_count_cypher({
        "blocks": [
            {"label": "Result", "conditions": []},
            {"via": {"type": "RETURNED_BY"}, "label": "Script", "conditions": []},
        ]
    })
    assert "-[:RETURNED_BY]->" in count
    assert count.endswith("RETURN count(*) AS total")


@pytest.mark.parametrize("bad_def", [
    {"blocks": [{"label": "Folder; DROP", "conditions": []}]},
    {"blocks": [{"label": "Folder",
                 "conditions": [{"property": "path) RETURN n //",
                                 "operator": "equals", "value": "x"}]}]},
    {"blocks": [
        {"label": "Folder", "conditions": []},
        {"via": {"type": "R]-() DETACH DELETE n //"}, "label": "File",
         "conditions": []},
    ]},
    {"blocks": [{"label": "", "conditions": []}]},
    {"blocks": [{"label": "9Lives", "conditions": []}]},
])
def test_injection_attempts_are_rejected(bad_def):
    with pytest.raises(ValueError):
        generate_cypher(bad_def)


def test_unknown_operator_is_rejected():
    with pytest.raises(ValueError):
        generate_cypher({
            "blocks": [{"label": "Folder",
                        "conditions": [{"property": "path",
                                        "operator": "sounds_like",
                                        "value": "x"}]}]
        })


def test_empty_filter_def_is_rejected():
    with pytest.raises(ValueError):
        generate_cypher({"blocks": []})
    with pytest.raises(ValueError):
        generate_cypher({})


# ---------------------------------------------------------------------------
# Property type inference
# ---------------------------------------------------------------------------

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

    def run(self, query, params=None):
        self._driver.queries.append((query, params))
        return _FakeResult([{'props': p} for p in self._driver.nodes])


class _FakeDriver:
    """Returns a canned node sample and records every query it was given."""

    def __init__(self, nodes):
        self.nodes = nodes
        self.queries = []

    def session(self, database=None):
        self.databases_used = getattr(self, 'databases_used', [])
        self.databases_used.append(database)
        return _FakeSession(self)


def _by_name(infos):
    return {i.name: i for i in infos}


def test_infer_property_types_classifies_each_type():
    driver = _FakeDriver([
        {'name': 'Zhang', 'count': 3, 'active': True, 'created': '2024-01-05'},
        {'name': 'Sanchez', 'count': 7, 'active': False,
         'created': '2024-02-06T10:30:00'},
    ])
    infos = _by_name(infer_property_types(driver, 'Investigator'))

    assert infos['name'].type == 'string'
    assert infos['count'].type == 'number'
    assert infos['active'].type == 'boolean'
    assert infos['created'].type == 'date'
    assert infos['name'].sample == 'Zhang'


def test_infer_property_types_marks_partially_present_props_nullable():
    driver = _FakeDriver([
        {'path': '/a', 'label': 'A'},
        {'path': '/b'},
    ])
    infos = _by_name(infer_property_types(driver, 'Folder'))

    assert infos['path'].nullable is False
    # Neo4j stores no nulls: a node without the key is the "value is null" case.
    assert infos['label'].nullable is True


def test_infer_property_types_reports_all_null_property_as_null_type():
    driver = _FakeDriver([{'path': '/a', 'last_modified': None}])
    infos = _by_name(infer_property_types(driver, 'Folder'))

    assert infos['last_modified'].type == 'null'
    assert infos['last_modified'].nullable is True
    assert infos['last_modified'].sample is None


def test_infer_property_types_is_sorted_and_bounded():
    driver = _FakeDriver([{'z': 1, 'a': 2, 'm': 3}])
    infos = infer_property_types(driver, 'Thing', database='neo4j', sample_size=25)

    assert [i.name for i in infos] == ['a', 'm', 'z']
    # One round trip regardless of property count — no per-property scans.
    assert len(driver.queries) == 1
    query, params = driver.queries[0]
    assert 'LIMIT $limit' in query
    assert params == {'limit': 25}
    assert driver.databases_used == ['neo4j']


def test_infer_property_types_on_empty_label():
    assert infer_property_types(_FakeDriver([]), 'Nothing') == []


def test_infer_property_types_validates_the_label():
    with pytest.raises(ValueError):
        infer_property_types(_FakeDriver([]), 'Folder) DETACH DELETE (n')


def test_property_info_is_a_dataclass_with_the_documented_fields():
    p = PropertyInfo(name='x', type='string', nullable=False, sample='v')
    assert (p.name, p.type, p.nullable, p.sample) == ('x', 'string', False, 'v')


# ---------------------------------------------------------------------------
# Routes — the paths that need no live Neo4j
# ---------------------------------------------------------------------------

def test_filter_preview_rejects_an_unsafe_label(client):
    resp = client.post('/api/schema/filter-preview', json={
        "blocks": [{"label": "Folder; DROP", "conditions": []}]
    })
    assert resp.status_code == 400
    assert 'error' in resp.get_json()


def test_filter_preview_rejects_an_empty_definition(client):
    resp = client.post('/api/schema/filter-preview', json={})
    assert resp.status_code == 400
    assert 'error' in resp.get_json()


def test_property_types_requires_a_label(client):
    resp = client.get('/api/schema/property-types')
    assert resp.status_code == 400
    assert 'error' in resp.get_json()


def test_schema_routes_are_registered(client):
    # Without Neo4j configured these report "not configured" rather than 404.
    for path in ('/api/schema/labels', '/api/schema/relationship-types'):
        assert client.get(path).status_code != 404
