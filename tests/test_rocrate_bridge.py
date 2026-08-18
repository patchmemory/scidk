"""The graph <-> RO-Crate bridge (Cycle 7, Task A).

Three builders, three shapes of test:

* ``build_from_map`` is held to the golden masters in
  ``tests/test_rocrate_golden_master.py`` — byte-identical output is the whole
  point of the refactor, so it is asserted here directly rather than trusted.
* ``build_from_selection`` runs against a fake Neo4j that answers the bridge's
  actual Cypher, so the tests exercise identifier resolution and edge scoping
  rather than a stubbed return value.
* ``ingest_crate`` reads real crate directories written to tmp_path, including
  one SciDK produced itself, so the round trip is a fact rather than a hope.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from scidk import rocrate_bridge
from scidk.rocrate_bridge import (
    CRATE_KEY_PROPERTY,
    IMPORT_RECORD_SOURCE,
    METADATA_FILENAME,
    build_from_map,
    build_from_selection,
    crate_metadata_path,
    ingest_crate,
)
from tests.test_rocrate_golden_master import CASES, load_case

#: ``ingest_crate`` is the one path that needs the library. Skipping only those
#: tests, rather than the module, keeps the export coverage in an environment
#: that has not installed it yet.
needs_rocrate = pytest.mark.skipif(
    importlib.util.find_spec('rocrate') is None,
    reason='ingest_crate parses with the rocrate library (requirements.txt)',
)


# --------------------------------------------------------------------- fakes

class FakeNeo4j:
    """A Neo4j stand-in that answers the bridge's queries over a tiny graph.

    Answering the real Cypher — rather than returning canned rows for whatever
    is asked — is what makes these tests catch a mistake in the queries
    themselves: an identifier that resolves by the wrong predicate, or an edge
    pulled in from outside the selection.
    """

    def __init__(self, nodes=(), edges=()):
        #: [{element_id, labels, properties}]
        self.nodes = list(nodes)
        #: [(source_element_id, target_element_id, rel_type)]
        self.edges = list(edges)
        self.queries: list[str] = []
        self.written: list[tuple[list, list]] = []

    def _row(self, node):
        return {
            'element_id': node['element_id'],
            'labels': list(node['labels']),
            'properties': dict(node['properties']),
        }

    def execute_read(self, query, parameters=None):
        self.queries.append(query)
        ids = list((parameters or {}).get('ids') or [])
        if 'elementId(n) IN $ids' in query:
            return [self._row(n) for n in self.nodes if n['element_id'] in ids]
        if 'n.path IN $ids' in query:
            return [
                self._row(n) for n in self.nodes
                # The query restricts to PATH_LABELS; the fake honours that.
                if n['properties'].get('path') in ids
                and set(n['labels']) & set(rocrate_bridge.PATH_LABELS)
            ]
        if 'MATCH (a)-[r]->(b)' in query:
            return [
                {'source': s, 'target': t, 'relationship': rel}
                for s, t, rel in self.edges
                if s in ids and t in ids
            ]
        raise AssertionError(f'unexpected query: {query}')

    def write_declared_nodes(self, nodes, relationships):
        self.written.append((nodes, relationships))
        return {
            'written_nodes': len(nodes),
            'written_relationships': len(relationships),
            'errors': [],
        }


class FakeSavedMaps:
    def __init__(self, maps):
        self._maps = maps

    def get_map(self, map_id):
        return self._maps.get(map_id)


class FakeSavedMap:
    def __init__(self, name, snapshot_json):
        self.name = name
        self.snapshot_json = snapshot_json


#: A small graph: a folder holding two files, plus a Person attached to one of
#: them, plus a node nobody selected.
GRAPH_NODES = [
    {'element_id': '4:aipt:1', 'labels': ['Folder'],
     'properties': {'path': '/data/aipt/cohortA', 'host': 'ki-ed3g'}},
    {'element_id': '4:aipt:2', 'labels': ['File'],
     'properties': {'path': '/data/aipt/cohortA/slide_001.svs', 'filename': 'slide_001.svs',
                    'size_bytes': 4096, 'mime_type': 'image/tiff', 'modified': 1767225600.0,
                    'checksum': 'a1b2c3'}},
    {'element_id': '4:aipt:3', 'labels': ['File'],
     'properties': {'path': '/data/aipt/cohortA/manifest.csv', 'filename': 'manifest.csv',
                    'size_bytes': 120, 'mime_type': 'text/csv'}},
    {'element_id': '4:aipt:4', 'labels': ['Person'], 'properties': {'name': 'R. Curator'}},
    {'element_id': '4:aipt:9', 'labels': ['File'],
     'properties': {'path': '/data/elsewhere/other.txt', 'filename': 'other.txt'}},
]

GRAPH_EDGES = [
    ('4:aipt:1', '4:aipt:2', 'CONTAINS'),
    ('4:aipt:1', '4:aipt:3', 'CONTAINS'),
    ('4:aipt:4', '4:aipt:2', 'ATTACHED_TO'),
    ('4:aipt:2', '4:aipt:9', 'DERIVED_FROM'),
]


@pytest.fixture
def graph():
    return FakeNeo4j(GRAPH_NODES, GRAPH_EDGES)


def entities(text):
    return {e['@id']: e for e in json.loads(text)['@graph']}


# ---------------------------------------------------------- build_from_map

@pytest.mark.parametrize('name', CASES)
def test_build_from_map_reproduces_the_canvas_export_exactly(name):
    """The DoD for the refactor: same snapshot in, same bytes out."""
    from scidk.services.canvas_service import generate_rocrate_export

    snapshot, layer_name, expected = load_case(name)

    assert build_from_map(snapshot=snapshot, layer_name=layer_name) + '\n' == expected
    assert generate_rocrate_export(snapshot, layer_name) + '\n' == expected


def test_build_from_map_loads_a_saved_map_by_id():
    snapshot, _, _ = load_case('multi_parent')
    service = FakeSavedMaps({'map-7': FakeSavedMap('Cohort layer', snapshot)})

    text = build_from_map('map-7', service=service)

    # The saved map's own name titles the crate when none is given.
    assert entities(text)['./']['name'] == 'Cohort layer'
    assert text == build_from_map(snapshot=snapshot, layer_name='Cohort layer')


def test_build_from_map_layer_name_overrides_the_saved_name():
    service = FakeSavedMaps({'map-7': FakeSavedMap('Cohort layer', {'nodes': [], 'edges': []})})

    text = build_from_map('map-7', layer_name='Published cohort', service=service)

    assert entities(text)['./']['name'] == 'Published cohort'


def test_build_from_map_needs_something_to_export():
    with pytest.raises(ValueError, match='snapshot or a map_id'):
        build_from_map()


def test_build_from_map_rejects_an_unknown_map_id():
    with pytest.raises(ValueError, match='no saved map'):
        build_from_map('nope', service=FakeSavedMaps({}))


def test_a_saved_map_with_no_snapshot_yields_an_empty_crate():
    """A layer saved before snapshots existed has ``snapshot_json`` of None."""
    service = FakeSavedMaps({'old': FakeSavedMap('Old layer', None)})

    assert entities(build_from_map('old', service=service))['./']['hasPart'] == []


def test_output_dir_receives_the_metadata_document(tmp_path):
    snapshot, layer_name, _ = load_case('mixed')

    text = build_from_map(snapshot=snapshot, layer_name=layer_name, output_dir=str(tmp_path))

    written = crate_metadata_path(tmp_path)
    assert written.name == METADATA_FILENAME
    assert written.read_text(encoding='utf-8') == text


# ---------------------------------------------------- build_from_selection

def test_selection_resolves_element_ids_and_paths_together(graph):
    """The Files page knows paths; the graph pages know elementIds. Both work."""
    text = build_from_selection(
        ['4:aipt:1', '/data/aipt/cohortA/slide_001.svs', '/data/aipt/cohortA/manifest.csv'],
        graph,
    )
    by_id = entities(text)

    assert set(by_id) - {'./', METADATA_FILENAME} == {'4:aipt:1', '4:aipt:2', '4:aipt:3'}
    # Only the folder is top level; its two files hang off it, not off the root.
    assert by_id['./']['hasPart'] == [{'@id': '4:aipt:1'}]
    assert by_id['4:aipt:1']['hasPart'] == [{'@id': '4:aipt:2'}, {'@id': '4:aipt:3'}]


def test_a_path_only_matches_the_labels_a_file_browser_can_select(graph):
    """A Person's name is not a path, and an unlabelled path scan is expensive."""
    text = build_from_selection(['R. Curator'], graph)

    assert entities(text)['./']['hasPart'] == []


def test_file_labels_become_file_entities_pointing_at_their_bytes(graph):
    text = build_from_selection(['4:aipt:2'], graph)

    slide = entities(text)['4:aipt:2']
    assert slide['@type'] == 'File'
    assert slide['name'] == 'slide_001.svs'
    assert slide['contentUrl'] == 'file:///data/aipt/cohortA/slide_001.svs'
    assert slide['contentSize'] == 4096
    assert slide['encodingFormat'] == 'image/tiff'
    assert slide['dateModified'] == '2026-01-01T00:00:00Z'
    assert slide['sha256'] == 'a1b2c3'


def test_metadata_only_describes_the_files_without_locating_them(graph):
    """The toggle removes the pointer at the bytes, not the description of them."""
    slide = entities(build_from_selection(['4:aipt:2'], graph, include_files=False))['4:aipt:2']

    assert 'contentUrl' not in slide
    assert slide['contentSize'] == 4096
    assert slide['encodingFormat'] == 'image/tiff'
    # And no internal path leaks in by another route.
    assert '/data/aipt' not in json.dumps(slide)


def test_a_folder_with_no_name_property_is_named_after_its_path(graph):
    folder = entities(build_from_selection(['4:aipt:1'], graph))['4:aipt:1']

    assert folder['name'] == 'cohortA'
    assert folder['@type'] == 'Dataset'


def test_edges_leaving_the_selection_are_left_out(graph):
    """4:aipt:2 DERIVED_FROM 4:aipt:9, which nobody selected."""
    text = build_from_selection(['4:aipt:1', '4:aipt:2'], graph)

    assert '4:aipt:9' not in text
    assert 'relation' not in entities(text)['4:aipt:2']


def test_attached_to_becomes_mentions(graph):
    text = build_from_selection(['4:aipt:2', '4:aipt:4'], graph)

    assert entities(text)['4:aipt:4']['mentions'] == [{'@id': '4:aipt:2'}]


def test_the_root_carries_what_a_repository_asks_for(graph):
    text = build_from_selection(
        ['4:aipt:1'], graph,
        name='AIPT cohort A', license='CC BY 4.0',
        description='Whole-slide images', date_published='2026-08-04',
    )

    root = entities(text)['./']
    assert root['name'] == 'AIPT cohort A'
    assert root['license'] == 'CC BY 4.0'
    assert root['description'] == 'Whole-slide images'
    assert root['datePublished'] == '2026-08-04'


def test_date_published_defaults_to_today(graph):
    from datetime import datetime, timezone

    root = entities(build_from_selection(['4:aipt:1'], graph))['./']

    assert root['datePublished'] == datetime.now(timezone.utc).date().isoformat()


def test_an_empty_selection_asks_neo4j_nothing_and_builds_a_valid_crate(graph):
    text = build_from_selection([], graph)

    assert graph.queries == []
    doc = json.loads(text)
    assert doc['@graph'][1] == {
        '@id': './', '@type': 'Dataset', 'name': 'SciDK selection',
        'datePublished': doc['@graph'][1]['datePublished'], 'hasPart': [],
    }


def test_identifiers_that_resolve_to_nothing_are_simply_absent(graph):
    text = build_from_selection(['4:aipt:1', '/data/deleted/gone.txt'], graph)

    assert 'gone.txt' not in text
    assert entities(text)['./']['hasPart'] == [{'@id': '4:aipt:1'}]


def test_selection_writes_the_metadata_document_when_asked(tmp_path, graph):
    text = build_from_selection(['4:aipt:1'], graph, output_dir=str(tmp_path))

    assert crate_metadata_path(tmp_path).read_text(encoding='utf-8') == text


def test_an_rclone_remote_becomes_an_rclone_url():
    graph = FakeNeo4j([
        {'element_id': '4:x:1', 'labels': ['File'],
         'properties': {'path': 'sharepoint:Shared Documents/a.csv', 'filename': 'a.csv'}},
    ])

    entity = entities(build_from_selection(['4:x:1'], graph))['4:x:1']

    assert entity['contentUrl'] == 'rclone://sharepoint/Shared Documents/a.csv'


# ------------------------------------------------------------- ingest_crate

def write_crate(directory: Path, doc) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    text = doc if isinstance(doc, str) else json.dumps(doc, indent=2)
    (directory / METADATA_FILENAME).write_text(text, encoding='utf-8')
    return directory


EXTERNAL_CRATE = {
    '@context': 'https://w3id.org/ro/crate/1.1/context',
    '@graph': [
        {'@id': METADATA_FILENAME, '@type': 'CreativeWork',
         'conformsTo': {'@id': 'https://w3id.org/ro/crate/1.1'},
         'about': {'@id': './'}},
        {'@id': './', '@type': 'Dataset', 'name': 'Someone elses crate',
         'identifier': 'https://doi.org/10.5281/zenodo.123456',
         'license': 'CC BY 4.0', 'datePublished': '2026-03-01',
         'hasPart': [{'@id': 'reads.fastq'}], 'author': {'@id': '#alice'}},
        {'@id': 'reads.fastq', '@type': 'File', 'name': 'reads.fastq',
         'contentSize': 900, 'encodingFormat': 'text/plain',
         'keywords': ['rnaseq', 'mouse'],
         'schema:alternateName': 'not a cypher identifier'},
        {'@id': '#alice', '@type': 'Person', 'name': 'Alice', 'affiliation': {'@id': '#lab'}},
    ],
}


def decls(driver):
    """The single (nodes, relationships) pair handed to write_declared_nodes."""
    assert len(driver.written) == 1
    nodes, rels = driver.written[0]
    return {n['properties']['crate_entity_id']: n for n in nodes}, rels


@needs_rocrate
class TestIngestCrate:
    """Reading a crate back in. Each case writes a real crate to tmp_path."""

    def test_ingest_stamps_every_node_as_imported(self, tmp_path):
        driver = FakeNeo4j()
        result = ingest_crate(str(write_crate(tmp_path / 'ext', EXTERNAL_CRATE)), driver)

        nodes, _ = decls(driver)
        assert nodes
        for node in nodes.values():
            assert node['properties']['record_source'] == IMPORT_RECORD_SOURCE
            assert node['key_property'] == CRATE_KEY_PROPERTY
            assert node['properties'][CRATE_KEY_PROPERTY].startswith('https://doi.org/10.5281')
        assert result['written_nodes'] == len(nodes)


    def test_ingest_maps_crate_types_onto_scidk_labels(self, tmp_path):
        driver = FakeNeo4j()
        ingest_crate(str(write_crate(tmp_path / 'ext', EXTERNAL_CRATE)), driver)

        nodes, _ = decls(driver)
        # A crate Dataset is a directory, which is what :Folder means here. Other
        # types keep their own name.
        assert nodes['./']['label'] == 'Folder'
        assert nodes['reads.fastq']['label'] == 'File'
        assert nodes['#alice']['label'] == 'Person'


    def test_ingest_keeps_scalar_properties_and_lists(self, tmp_path):
        driver = FakeNeo4j()
        ingest_crate(str(write_crate(tmp_path / 'ext', EXTERNAL_CRATE)), driver)

        nodes, _ = decls(driver)
        props = nodes['reads.fastq']['properties']
        assert props['contentSize'] == 900
        assert props['encodingFormat'] == 'text/plain'
        assert props['keywords'] == ['rnaseq', 'mouse']


    def test_a_property_cypher_cannot_name_is_reported_not_mangled(self, tmp_path):
        driver = FakeNeo4j()
        result = ingest_crate(str(write_crate(tmp_path / 'ext', EXTERNAL_CRATE)), driver)

        nodes, _ = decls(driver)
        assert 'schema:alternateName' not in nodes['reads.fastq']['properties']
        assert any('schema:alternateName' in reason for reason in result['skipped'])
        assert result['status'] == 'partial'


    def test_ingest_turns_references_into_relationships(self, tmp_path):
        driver = FakeNeo4j()
        ingest_crate(str(write_crate(tmp_path / 'ext', EXTERNAL_CRATE)), driver)

        _, rels = decls(driver)
        by_type = {r['type'] for r in rels}
        # hasPart/mentions invert the export mapping; any other reference-valued
        # property becomes a relationship named after itself, so external structure
        # survives instead of being dropped.
        assert 'CONTAINS' in by_type
        assert 'AUTHOR' in by_type
        contains = next(r for r in rels if r['type'] == 'CONTAINS')
        assert contains['from_label'] == 'Folder'
        assert contains['to_label'] == 'File'


    def test_a_reference_to_something_outside_the_crate_is_reported(self, tmp_path):
        """``#lab`` is referenced by Alice but described nowhere."""
        driver = FakeNeo4j()
        result = ingest_crate(str(write_crate(tmp_path / 'ext', EXTERNAL_CRATE)), driver)

        _, rels = decls(driver)
        assert all('#lab' not in json.dumps(r) for r in rels)
        assert any('#lab' in reason for reason in result['skipped'])


    def test_re_ingesting_the_same_crate_produces_the_same_keys(self, tmp_path):
        """The reason ``crate_id`` is not the library's ``canonical_id()``.

        ``canonical_id()`` mints a fresh ``arcp://uuid,<random>`` base on every parse,
        so keying on it would duplicate the entire graph on a second import.
        """
        crate = write_crate(tmp_path / 'ext', EXTERNAL_CRATE)
        first, second = FakeNeo4j(), FakeNeo4j()

        ingest_crate(str(crate), first)
        ingest_crate(str(crate), second)

        keys = lambda d: sorted(n['properties'][CRATE_KEY_PROPERTY] for n in d.written[0][0])  # noqa: E731
        assert keys(first) == keys(second)


    def test_a_crate_with_no_persistent_identifier_is_keyed_by_location(self, tmp_path):
        doc = json.loads(json.dumps(EXTERNAL_CRATE))
        doc['@graph'][1].pop('identifier')
        crate = write_crate(tmp_path / 'local', doc)

        driver = FakeNeo4j()
        result = ingest_crate(str(crate), driver)

        assert result['crate_key'] == f'file://{crate.resolve()}'


    def test_a_crate_scidk_exported_round_trips_to_its_own_relationship_types(self, tmp_path):
        """``relation`` carries the original type in ``name``; import reads it back."""
        _, _, expected = load_case('provisional_only')
        driver = FakeNeo4j()

        ingest_crate(str(write_crate(tmp_path / 'own', expected)), driver)

        _, rels = decls(driver)
        assert {r['type'] for r in rels} == {'CONTAINS', 'ATTACHED_TO', 'DERIVED_FROM'}


    def test_the_metadata_descriptor_is_not_an_entity_to_write(self, tmp_path):
        driver = FakeNeo4j()
        ingest_crate(str(write_crate(tmp_path / 'ext', EXTERNAL_CRATE)), driver)

        nodes, _ = decls(driver)
        assert METADATA_FILENAME not in nodes


    def test_an_unreadable_crate_says_so(self, tmp_path):
        with pytest.raises(RuntimeError, match='could not read RO-Crate'):
            ingest_crate(str(tmp_path / 'does-not-exist'), FakeNeo4j())
